"""
xtal.core.spacegroup
====================
A thin, immutable value object over gemmi's space-group tables.

The **Hall symbol is the identity** of a space group here, not the
number and not the Hermann-Mauguin symbol.  A number alone does not
determine the operations: number 227 alone cannot tell you whether the
origin is at -43m or at -3m, and number 146 cannot tell you hexagonal
axes from rhombohedral.  Carrying the Hall symbol everywhere is what
stops the app from silently producing a structure that looks plausible
and is wrong.

Everything else -- expanding an asymmetric unit, detecting symmetry,
assigning Wyckoff letters -- lives in ``xtal.core.symmetry``.  This
module only answers "what are the operations of this group?".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import gemmi
import numpy as np

DEN = float(gemmi.Op.DEN)          # gemmi stores ops as ints / 24


# ======================================================================
#  SYMMETRY OPERATION
# ======================================================================

@dataclass(frozen=True)
class SymOp:
    """One symmetry operation: x' = rot @ x + trans (fractional)."""

    rot: np.ndarray                 # (3,3) float, integer-valued
    trans: np.ndarray               # (3,) float in [0,1)
    triplet: str                    # "-x,y+1/2,-z+1/2"

    def apply(self, frac) -> np.ndarray:
        """Apply to (3,) or (N,3) fractional coordinates."""
        f = np.asarray(frac, dtype=float)
        return f @ self.rot.T + self.trans

    def is_identity(self) -> bool:
        return (np.array_equal(self.rot, np.eye(3))
                and not np.any(self.trans))

    def __repr__(self) -> str:
        return f"SymOp({self.triplet})"


def _ops_from_gemmi(sg: gemmi.SpaceGroup) -> tuple[SymOp, ...]:
    out = []
    for op in sg.operations():
        rot = np.array(op.rot, dtype=float) / DEN
        trans = np.mod(np.array(op.tran, dtype=float) / DEN, 1.0)
        out.append(SymOp(rot, trans, op.triplet()))
    for o in out:                      # ops are shared, keep them read-only
        o.rot.flags.writeable = False
        o.trans.flags.writeable = False
    return tuple(out)


@lru_cache(maxsize=512)
def _lookup(hall: str) -> gemmi.SpaceGroup:
    # gemmi raises RuntimeError on malformed Hall symbols; every
    # lookup failure in this module surfaces as ValueError so callers
    # need only one except clause.
    try:
        sg = gemmi.find_spacegroup_by_ops(gemmi.symops_from_hall(hall))
    except RuntimeError as exc:
        raise ValueError(f"unknown Hall symbol: {hall!r}") from exc
    if sg is None:
        raise ValueError(f"unknown Hall symbol: {hall!r}")
    return sg


def _rotation_key(rot: np.ndarray) -> tuple:
    # A space group's rotations are integer in the fractional basis,
    # so rounding them is an exact key and not a tolerance.
    return tuple(np.rint(rot).astype(int).ravel())


@lru_cache(maxsize=512)
def _inverses(hall: str) -> tuple:
    """Every operation's ``(m, shift)`` inverse, for one Hall symbol.

    Keyed on the group and not held by the instance, because the table
    is a function of the operations alone and every CIF read, project
    load and Reduce to P1 makes a fresh ``SpaceGroup``: Fm-3m's table
    was 36 864 ``np.allclose`` calls, 0.2 s, paid again each time.
    Looking the rotation up by its integer entries makes it one pass.
    """
    ops = _ops_from_gemmi(_lookup(hall))
    by_rotation: dict = {}
    for m, op in enumerate(ops):
        by_rotation.setdefault(_rotation_key(op.rot), []).append(m)
    out = []
    for op in ops:
        rot = np.linalg.inv(op.rot)
        for m in by_rotation.get(_rotation_key(rot), ()):
            candidate = ops[m]
            shift = candidate.rot @ op.trans + candidate.trans
            if np.allclose(shift, np.round(shift), atol=1e-9):
                closing = np.round(shift).astype(int)
                closing.flags.writeable = False     # shared by callers
                out.append((m, closing))
                break
        else:                                       # pragma: no cover
            raise ValueError(
                f"{hall} is not closed under inversion; "
                f"{op.triplet} has no inverse in the group")
    return tuple(out)


# ======================================================================
#  SPACE GROUP
# ======================================================================

@dataclass(frozen=True, eq=False)
class SpaceGroup:
    """A space group in a definite setting, identified by Hall symbol."""

    hall: str
    _cache: dict = field(default_factory=dict, repr=False, compare=False)

    # -- construction --------------------------------------------------

    @classmethod
    def from_hall(cls, hall: str) -> SpaceGroup:
        return cls(_lookup(hall).hall)

    @classmethod
    def from_name(cls, name: str) -> SpaceGroup:
        """From a Hermann-Mauguin symbol, with or without a setting
        qualifier: 'P21/c', 'P 1 21/c 1', 'Fd-3m:2', 'R-3c:H'."""
        sg = gemmi.find_spacegroup_by_name(name)
        if sg is None:
            raise ValueError(f"unknown space-group name: {name!r}")
        return cls(sg.hall)

    @classmethod
    def from_number(cls, number: int, setting: str = "") -> SpaceGroup:
        """From an international number (1-230).  ``setting`` is the
        gemmi/CIF extension: '1' or '2' for origin choice, 'H' or 'R'
        for trigonal axes."""
        if not 1 <= int(number) <= 230:
            raise ValueError(f"space-group number out of range: {number}")
        if setting:
            sg = gemmi.find_spacegroup_by_name(
                f"{gemmi.find_spacegroup_by_number(int(number)).hm}"
                f":{setting}")
            if sg is None:
                raise ValueError(
                    f"space group {number} has no setting {setting!r}")
        else:
            sg = gemmi.find_spacegroup_by_number(int(number))
        return cls(sg.hall)

    @classmethod
    def p1(cls) -> SpaceGroup:
        return cls.from_number(1)

    @classmethod
    def from_any(cls, value) -> SpaceGroup:
        """Accept a SpaceGroup, a gemmi.SpaceGroup, a number, a H-M
        name, a Hall symbol, or None (-> P1)."""
        if value is None:
            return cls.p1()
        if isinstance(value, SpaceGroup):
            return value
        if isinstance(value, gemmi.SpaceGroup):
            return cls(value.hall)
        if isinstance(value, int | np.integer):
            return cls.from_number(int(value))
        if isinstance(value, str):
            try:
                return cls.from_name(value)
            except ValueError:
                return cls.from_hall(value)
        raise TypeError(f"cannot read a space group from {value!r}")

    # -- identity ------------------------------------------------------

    @property
    def _sg(self) -> gemmi.SpaceGroup:
        return _lookup(self.hall)

    @property
    def number(self) -> int:
        return self._sg.number

    @property
    def hm(self) -> str:
        """Full H-M symbol including setting, e.g. 'P 1 21/c 1'."""
        return self._sg.xhm()

    @property
    def short_name(self) -> str:
        """Compact H-M symbol, e.g. 'P21/c'."""
        return self._sg.short_name()

    @property
    def setting(self) -> str:
        """Setting qualifier ('', '1', '2', 'H', 'R')."""
        return self._sg.ext

    @property
    def crystal_system(self) -> str:
        return self._sg.crystal_system_str()

    @property
    def point_group(self) -> str:
        return self._sg.point_group_hm()

    @property
    def laue_class(self) -> str:
        return self._sg.laue_str()

    @property
    def cell_constraint(self):
        """Which of the six cell parameters this group leaves free.

        Derived from the operations rather than looked up by crystal
        system, so every setting is right: P21/c constrains beta and
        P1121/a constrains gamma, and both are the same group number.
        """
        constraint = self._cache.get("cell_constraint")
        if constraint is None:
            from xtal.core.lattice import constraint_from_rotations
            constraint = constraint_from_rotations(
                [op.rot for op in self.operations],
                self.crystal_system)
            self._cache["cell_constraint"] = constraint
        return constraint

    @property
    def centring(self) -> str:
        """Lattice centring letter: P, A, B, C, I, F, R."""
        return str(self._sg.centring_type())

    # -- operations ----------------------------------------------------

    @property
    def operations(self) -> tuple[SymOp, ...]:
        """All operations including lattice centring, identity first."""
        ops = self._cache.get("ops")
        if ops is None:
            ops = _ops_from_gemmi(self._sg)
            self._cache["ops"] = ops
        return ops

    @property
    def order(self) -> int:
        """Number of operations = maximum site multiplicity."""
        return len(self.operations)

    def inverse_of(self, k: int) -> tuple[int, np.ndarray]:
        """``(m, shift)`` such that ``op_m(op_k(x)) == x + shift``.

        Operations form a group only *modulo lattice translations*, so
        the inverse of one comes with the integer vector that closes
        the loop.  Anything that has to read a relationship between two
        atoms backwards needs this -- most of all a bond, which is the
        same bond whichever end you name first.
        """
        return _inverses(self.hall)[int(k)]

    @property
    def triplets(self) -> list[str]:
        """Operation triplets, as written in a CIF symmetry loop."""
        return [op.triplet for op in self.operations]

    def apply_all(self, frac) -> np.ndarray:
        """Apply every operation to one point -> (order, 3) array.

        No de-duplication: points on a special position repeat.  Use
        ``xtal.core.symmetry.orbit`` for the unique set."""
        rotations, translations = self.stacked
        f = np.asarray(frac, dtype=float).reshape(3)
        return rotations @ f + translations

    @property
    def stacked(self) -> tuple[np.ndarray, np.ndarray]:
        """Every rotation as one ``(order, 3, 3)`` array and every
        translation as one ``(order, 3)``, in operation order.

        For code that asks the same question of every operation: a
        Python loop of 192 small matrix products per point is what
        made mapping a bond through Fm-3m cost a millisecond.
        """
        stacked = self._cache.get("stacked")
        if stacked is None:
            ops = self.operations
            rotations = np.array([op.rot for op in ops])
            translations = np.array([op.trans for op in ops])
            rotations.flags.writeable = False
            translations.flags.writeable = False
            stacked = self._cache["stacked"] = (rotations, translations)
        return stacked

    # -- flags ---------------------------------------------------------

    @property
    def is_p1(self) -> bool:
        return self._sg.number == 1 and len(self.operations) == 1

    @property
    def is_centrosymmetric(self) -> bool:
        return self._sg.operations().is_centrosymmetric()

    @property
    def is_chiral(self) -> bool:
        """Sohncke group: only rotations, so it can host a chiral
        structure."""
        return self._sg.is_sohncke()

    # -- serialisation / comparison ------------------------------------

    def to_dict(self) -> dict:
        return {"hall": self.hall, "hm": self.hm, "number": self.number}

    @classmethod
    def from_dict(cls, d: dict) -> SpaceGroup:
        return cls.from_hall(d["hall"])

    def __eq__(self, other) -> bool:
        if not isinstance(other, SpaceGroup):
            return NotImplemented
        return self.hall == other.hall

    def __hash__(self) -> int:
        return hash(self.hall)

    def __repr__(self) -> str:
        return f"SpaceGroup({self.short_name} #{self.number})"


# ======================================================================
#  THE TABLE
# ======================================================================
#
# A picker needs the whole list, and the whole list is not 230 entries
# -- it is every *setting* of every group, because P21/c and P21/n are
# the same group seen down different axes and picking the wrong one
# silently produces the wrong structure.  gemmi carries them all.

def table() -> tuple[SpaceGroup, ...]:
    """Every space-group setting, in number order."""
    cached = _TABLE.get("all")
    if cached is None:
        cached = tuple(sorted(
            (SpaceGroup(entry.hall)
             for entry in gemmi.spacegroup_table() if entry.number),
            key=lambda g: (g.number, g.hm)))
        _TABLE["all"] = cached
    return cached


def search(text: str = "", groups=None) -> list[SpaceGroup]:
    """Settings matching a typed query.

    A number ("62"), a Hermann-Mauguin symbol with or without spaces
    ("P21/c", "P 1 21/c 1"), a Hall symbol, or a crystal system
    ("tetragonal") all work, because a user reaching for this dialog
    knows the group by exactly one of those and should not have to
    guess which.
    """
    groups = table() if groups is None else groups
    query = text.strip().lower()
    if not query:
        return list(groups)
    if query.isdigit():
        number = int(query)
        return [g for g in groups if g.number == number]
    squashed = query.replace(" ", "")
    out = []
    for g in groups:
        haystack = (f"{g.number} {g.hm} {g.short_name} {g.hall} "
                    f"{g.crystal_system}").lower()
        if query in haystack or squashed in haystack.replace(" ", ""):
            out.append(g)
    return out


_TABLE: dict = {}

