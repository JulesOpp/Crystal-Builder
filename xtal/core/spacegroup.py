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

    @property
    def triplets(self) -> list[str]:
        """Operation triplets, as written in a CIF symmetry loop."""
        return [op.triplet for op in self.operations]

    def apply_all(self, frac) -> np.ndarray:
        """Apply every operation to one point -> (order, 3) array.

        No de-duplication: points on a special position repeat.  Use
        ``xtal.core.symmetry.orbit`` for the unique set."""
        f = np.asarray(frac, dtype=float).reshape(3)
        return np.array([op.apply(f) for op in self.operations])

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
