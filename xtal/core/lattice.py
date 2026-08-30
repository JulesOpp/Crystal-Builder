"""
xtal.core.lattice
=================
The unit cell: a 3x3 matrix whose ROWS are the lattice vectors a, b, c
in Angstrom, plus everything derived from it.

Conventions, fixed here once so nothing downstream has to guess:

* rows are vectors -- ``matrix[0]`` is **a**, ``matrix[1]`` is **b**,
  ``matrix[2]`` is **c**.
* fractional -> cartesian is ``frac @ matrix`` (row-vector convention,
  so an (N,3) block of coordinates transforms in one matmul).
* the standard orientation puts **a** along +x and **b** in the xy
  plane with positive y; ``from_parameters`` builds that orientation.
* the reciprocal lattice uses the CRYSTALLOGRAPHIC convention without
  2*pi, so ``a . a* = 1`` and ``d(hkl) = 1 / |hkl @ reciprocal|``.
  Pass ``two_pi=True`` for the physics convention.

Lattice is immutable: every operation returns a new Lattice.  That is
what lets commands store an old cell as their undo data for free.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

DEG = math.pi / 180.0


# ======================================================================
#  LATTICE
# ======================================================================

@dataclass(frozen=True, eq=False)
class Lattice:
    """A unit cell.  Construct from a matrix, or from parameters via
    :meth:`from_parameters`."""

    matrix: np.ndarray
    _cache: dict = field(default_factory=dict, repr=False, compare=False)

    # -- construction --------------------------------------------------

    def __post_init__(self):
        m = np.array(self.matrix, dtype=float)
        if m.shape != (3, 3):
            raise ValueError(f"lattice matrix must be 3x3, got {m.shape}")
        if not np.all(np.isfinite(m)):
            raise ValueError("lattice matrix contains non-finite values")
        if abs(np.linalg.det(m)) < 1e-9:
            raise ValueError("lattice matrix is singular (zero volume)")
        m.flags.writeable = False
        object.__setattr__(self, "matrix", m)

    @classmethod
    def from_parameters(cls, a, b, c, alpha, beta, gamma) -> Lattice:
        """Build the standard-orientation cell from (a, b, c) in
        Angstrom and (alpha, beta, gamma) in degrees."""
        for name, v in (("a", a), ("b", b), ("c", c)):
            if v <= 0:
                raise ValueError(f"cell edge {name} must be positive")
        for name, v in (("alpha", alpha), ("beta", beta),
                        ("gamma", gamma)):
            if not 0 < v < 180:
                raise ValueError(f"cell angle {name} must be in (0,180)")
        ca, cb = math.cos(alpha * DEG), math.cos(beta * DEG)
        cg, sg = math.cos(gamma * DEG), math.sin(gamma * DEG)
        cx = cb
        cy = (ca - cb * cg) / sg
        cz2 = 1.0 - cx * cx - cy * cy
        if cz2 <= 0:
            raise ValueError(
                "cell angles are geometrically impossible "
                f"({alpha}, {beta}, {gamma})"
            )
        return cls(np.array([
            [a, 0.0, 0.0],
            [b * cg, b * sg, 0.0],
            [c * cx, c * cy, c * math.sqrt(cz2)],
        ]))

    @classmethod
    def cubic(cls, a) -> Lattice:
        return cls.from_parameters(a, a, a, 90.0, 90.0, 90.0)

    @classmethod
    def orthorhombic(cls, a, b, c) -> Lattice:
        return cls.from_parameters(a, b, c, 90.0, 90.0, 90.0)

    # -- parameters ----------------------------------------------------

    @property
    def lengths(self) -> tuple[float, float, float]:
        return tuple(np.linalg.norm(self.matrix, axis=1))

    @property
    def angles(self) -> tuple[float, float, float]:
        """(alpha, beta, gamma) in degrees."""
        m, (a, b, c) = self.matrix, self.lengths
        alpha = math.degrees(math.acos(
            np.clip(np.dot(m[1], m[2]) / (b * c), -1.0, 1.0)))
        beta = math.degrees(math.acos(
            np.clip(np.dot(m[0], m[2]) / (a * c), -1.0, 1.0)))
        gamma = math.degrees(math.acos(
            np.clip(np.dot(m[0], m[1]) / (a * b), -1.0, 1.0)))
        return (alpha, beta, gamma)

    @property
    def parameters(self) -> tuple[float, ...]:
        """(a, b, c, alpha, beta, gamma) -- Angstrom and degrees."""
        return (*self.lengths, *self.angles)

    @property
    def volume(self) -> float:
        return abs(float(np.linalg.det(self.matrix)))

    @property
    def inverse(self) -> np.ndarray:
        """Cached inverse; cartesian -> fractional is ``cart @ inv``."""
        inv = self._cache.get("inv")
        if inv is None:
            inv = np.linalg.inv(self.matrix)
            inv.flags.writeable = False
            self._cache["inv"] = inv
        return inv

    @property
    def metric_tensor(self) -> np.ndarray:
        """G = M M^T; ``frac @ G @ frac`` is a squared length."""
        return self.matrix @ self.matrix.T

    def reciprocal(self, two_pi: bool = False) -> Lattice:
        """Reciprocal cell, rows a*, b*, c*."""
        rec = self.inverse.T
        return Lattice(rec * (2.0 * math.pi) if two_pi else rec)

    def d_spacing(self, hkl) -> float:
        """Interplanar spacing for a Miller index, in Angstrom."""
        g = np.asarray(hkl, dtype=float) @ self.reciprocal().matrix
        n = float(np.linalg.norm(g))
        if n == 0.0:
            raise ValueError("d-spacing undefined for hkl = (0,0,0)")
        return 1.0 / n

    # -- coordinate conversion ----------------------------------------

    def to_cart(self, frac) -> np.ndarray:
        """Fractional -> cartesian.  Accepts (3,) or (N,3)."""
        return np.asarray(frac, dtype=float) @ self.matrix

    def to_frac(self, cart) -> np.ndarray:
        """Cartesian -> fractional.  Accepts (3,) or (N,3)."""
        return np.asarray(cart, dtype=float) @ self.inverse

    @staticmethod
    def wrap(frac) -> np.ndarray:
        """Wrap fractional coordinates into [0, 1)."""
        return np.mod(np.asarray(frac, dtype=float), 1.0)

    # -- derived cells -------------------------------------------------

    def transform(self, p) -> Lattice:
        """Apply a cell transformation matrix P (rows = new vectors in
        units of the old ones): ``M' = P @ M``.

        ``Lattice.cubic(4).transform(np.diag([2,2,2]))`` is a 2x2x2
        supercell; a general integer P with |det P| > 1 is a supercell,
        |det P| < 1 a subcell.
        """
        p = np.asarray(p, dtype=float)
        if p.shape != (3, 3):
            raise ValueError("transformation matrix must be 3x3")
        det = float(np.linalg.det(p))
        if abs(det) < 1e-9:
            raise ValueError("transformation matrix is singular")
        if det < 0:
            raise ValueError(
                "transformation matrix has negative determinant "
                "(it would flip handedness)"
            )
        return Lattice(p @ self.matrix)

    def strained(self, eps) -> Lattice:
        """Apply a cartesian strain tensor: ``M' = M (I + eps)^T``.

        A scalar means isotropic strain."""
        e = np.asarray(eps, dtype=float)
        if e.ndim == 0:
            e = float(e) * np.eye(3)
        if e.shape != (3, 3):
            raise ValueError("strain must be a scalar or a 3x3 tensor")
        return Lattice(self.matrix @ (np.eye(3) + e).T)

    def scaled_to_volume(self, volume: float) -> Lattice:
        """Isotropically rescale to a target volume."""
        if volume <= 0:
            raise ValueError("target volume must be positive")
        return Lattice(self.matrix * (volume / self.volume) ** (1 / 3))

    def with_parameters(self, a=None, b=None, c=None, alpha=None,
                        beta=None, gamma=None) -> Lattice:
        """Copy with some parameters replaced; the result is in
        standard orientation."""
        old = self.parameters
        new = [v if v is not None else old[i] for i, v in
               enumerate((a, b, c, alpha, beta, gamma))]
        return Lattice.from_parameters(*new)

    def standard_orientation(self) -> Lattice:
        """Same cell parameters, rebuilt with a along +x.  Removes any
        rigid rotation the matrix happens to carry."""
        return Lattice.from_parameters(*self.parameters)

    @property
    def is_right_handed(self) -> bool:
        return float(np.linalg.det(self.matrix)) > 0

    # -- serialisation / comparison ------------------------------------

    def to_dict(self) -> dict:
        return {"matrix": self.matrix.tolist()}

    @classmethod
    def from_dict(cls, d: dict) -> Lattice:
        return cls(np.array(d["matrix"], dtype=float))

    def almost_equal(self, other: Lattice, tol: float = 1e-6) -> bool:
        return bool(np.allclose(self.matrix, other.matrix, atol=tol))

    def __eq__(self, other) -> bool:
        if not isinstance(other, Lattice):
            return NotImplemented
        return self.almost_equal(other)

    def __hash__(self) -> int:
        return hash(np.round(self.matrix, 9).tobytes())

    def __repr__(self) -> str:
        a, b, c, al, be, ga = self.parameters
        return (f"Lattice(a={a:.4f}, b={b:.4f}, c={c:.4f}, "
                f"alpha={al:.3f}, beta={be:.3f}, gamma={ga:.3f})")


# ======================================================================
#  SYMMETRY-ALLOWED CELL SHAPES
# ======================================================================
#
# A space group does not merely describe a cell, it constrains one.  In
# a hexagonal group a and b are the same length by construction and
# gamma is 120 degrees; typing a different b does not give a hexagonal
# crystal with an odd cell, it gives a structure whose symmetry
# operations no longer map it onto itself.  So the editor has to know
# which of the six numbers are really free.

PARAMETER_NAMES = ("a", "b", "c", "alpha", "beta", "gamma")


@dataclass(frozen=True)
class CellConstraint:
    """Which cell parameters a space group leaves free.

    ``ties`` has one entry per parameter, in the order a, b, c, alpha,
    beta, gamma:

    * ``None``  -- free to edit;
    * an ``int``   -- must equal the parameter at that index;
    * a ``float`` -- fixed at that value.

    A tie always points at an earlier parameter, so resolving them in
    order takes one pass.
    """

    ties: tuple = (None,) * 6
    system: str = "triclinic"

    def is_free(self, index: int) -> bool:
        return self.ties[index] is None

    def follows(self, index: int) -> int | None:
        """The parameter this one must equal, if any."""
        tie = self.ties[index]
        return tie if isinstance(tie, int) else None

    def fixed_at(self, index: int) -> float | None:
        tie = self.ties[index]
        return float(tie) if isinstance(tie, float) else None

    @property
    def free_names(self) -> tuple:
        return tuple(PARAMETER_NAMES[i] for i in range(6)
                     if self.is_free(i))

    def apply(self, parameters) -> tuple:
        """The nearest cell of this shape: free parameters as given,
        the rest made to follow."""
        out = [float(v) for v in parameters]
        for index, tie in enumerate(self.ties):
            if isinstance(tie, int):
                out[index] = out[tie]
            elif isinstance(tie, float):
                out[index] = tie
        return tuple(out)

    def allows(self, parameters, tol: float = 1e-6) -> bool:
        """Is this cell already of the shape the group demands?"""
        return all(abs(a - b) <= tol for a, b in
                   zip(parameters, self.apply(parameters),
                       strict=True))

    def describe(self) -> str:
        parts = []
        for index, tie in enumerate(self.ties):
            name = PARAMETER_NAMES[index]
            if isinstance(tie, int):
                parts.append(f"{name} = {PARAMETER_NAMES[tie]}")
            elif isinstance(tie, float):
                parts.append(f"{name} = {tie:g}")
        return ", ".join(parts) if parts else "all six are free"

    @classmethod
    def free(cls) -> CellConstraint:
        return cls()


# The metric tensor as six numbers, in the order this module works in:
#   G11 = a.a, G22 = b.b, G33 = c.c, G23 = b.c, G13 = a.c, G12 = a.b
_G_INDEX = ((0, 0), (1, 1), (2, 2), (1, 2), (0, 2), (0, 1))


def _metric_vector(matrix: np.ndarray) -> np.ndarray:
    g = matrix @ matrix.T
    return np.array([g[i, j] for i, j in _G_INDEX])


def _metric_constraints(rotations) -> np.ndarray:
    """Rows of a linear system ``M g = 0`` satisfied by every metric
    tensor the given rotations preserve.

    A cell is compatible with a symmetry operation R exactly when
    ``R^T G R = G``.  (That transpose is not decorative: the other way
    round constrains the *reciprocal* metric, whose hexagonal angle is
    60 degrees rather than 120.)  The condition is linear in the six
    independent components of G, so the cells a group allows form a
    subspace -- and reading the constraints off that subspace is how
    the editor learns that a and b must match, without anyone writing
    down a table of the seven crystal systems and their settings.
    """
    blocks = []
    for rotation in rotations:
        r = np.asarray(rotation, dtype=float)
        # One column per basis component of G: where that component
        # goes under the operation.
        columns = []
        for component in range(6):
            basis = np.zeros((3, 3))
            i, j = _G_INDEX[component]
            basis[i, j] = basis[j, i] = 1.0
            moved = r.T @ basis @ r
            columns.append([moved[i, j] for i, j in _G_INDEX])
        blocks.append(np.array(columns).T - np.eye(6))
    if not blocks:
        return np.zeros((0, 6))
    return np.vstack(blocks)


def _forced(system: np.ndarray, relation) -> bool:
    """Is ``relation . g = 0`` implied by the system?

    True when the relation lies in the row space -- that is, when it
    adds nothing the constraints did not already say.
    """
    relation = np.asarray(relation, dtype=float)
    if not system.size:
        return False
    solution, *_ = np.linalg.lstsq(system.T, relation, rcond=None)
    return bool(np.allclose(system.T @ solution, relation, atol=1e-8))


def constraint_from_rotations(rotations,
                              system: str = "") -> CellConstraint:
    """Work out which cell parameters the given rotations leave free.

    Only the rotation parts matter: a translation moves a cell, it does
    not reshape one.
    """
    equations = _metric_constraints(rotations)
    ties: list = [None] * 6

    #  a = b, b = c: equal diagonal components of the metric.
    for later, earlier in ((1, 0), (2, 1), (2, 0)):
        if ties[later] is not None:
            continue
        relation = np.zeros(6)
        relation[later], relation[earlier] = 1.0, -1.0
        if _forced(equations, relation):
            ties[later] = earlier

    # An off-diagonal component of zero is a right angle; one that is
    # minus half a diagonal is 120 degrees, the hexagonal case.
    for angle, (off, first, second) in enumerate(
            ((3, 1, 2), (4, 0, 2), (5, 0, 1))):
        relation = np.zeros(6)
        relation[off] = 1.0
        if _forced(equations, relation):
            ties[3 + angle] = 90.0
            continue
        for diagonal in (first, second):
            hexagonal = np.zeros(6)
            hexagonal[off], hexagonal[diagonal] = 2.0, 1.0
            if _forced(equations, hexagonal):
                ties[3 + angle] = 120.0
                break

    # Rhombohedral: no angle is fixed, but they must all be equal.
    for later, earlier in ((4, 3), (5, 4), (5, 3)):
        if ties[later] is not None or ties[earlier] is not None:
            continue
        relation = np.zeros(6)
        relation[later], relation[earlier] = 1.0, -1.0
        if _forced(equations, relation):
            ties[later] = earlier

    return CellConstraint(tuple(ties), system or "triclinic")

