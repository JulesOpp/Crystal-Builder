"""
xtal.ff.coordinates
===================
The coordinates a relaxed scan can hold: a distance, an angle, a
torsion, the angle between two planes, and the cell's own parameters.

Two decisions shape the whole module.

**An endpoint is a group of atoms, not an atom.**  A group of one is
an atom; a group of many is its centroid, recomputed from wherever its
atoms are at the time.  A dummy atom would have been the obvious way to
say "the middle of that ring" -- the application can place one -- but a
placed centroid is a *snapshot* (nothing re-fits it when its neighbours
move) and every engine holds markers back at the door, so a marker
feels no force.  Constraining a distance to one would be satisfied by
sliding the marker at no energy cost: a flat profile that looks like a
result.  A group is the same idea with the atoms still in it, and it
follows the precedent :class:`xtal.core.measure.Plane` already set --
defined by its atoms, re-fitted whenever they move.

**The periodic images are chosen once and then held.**  Every
measurement in :mod:`xtal.core.measure` re-decides the nearest image on
every call, which is right for a number in a panel and wrong for a
constraint: an atom that drifts past the half-cell mid-relaxation would
make the coordinate jump by a lattice vector, and an optimiser cannot
descend a function with a step in it.  So an anchor resolves its images
to *integer lattice translations* against the structure it was defined
on, and from then on the coordinate is a smooth function of the
positions and the cell -- which is what makes its gradient meaningful
and its constraint solvable.
"""

from __future__ import annotations

import itertools
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np

from xtal.core import elements, transforms
from xtal.core.lattice import PARAMETER_NAMES, Lattice

#: Step used for the plane-angle gradient, in Angstrom.  It
#: differentiates arithmetic rather than an energy, so it costs
#: microseconds and the usual worry about a finite difference -- that
#: each evaluation is expensive and noisy -- does not apply.
PLANE_STEP = 1e-5

#: How distinctly a plane's normal must be the direction its atoms
#: vary along least, as a fraction of their spread in the plane.  See
#: :func:`_normal`.
PLANE_TOLERANCE = 1e-3

_SHIFTS = np.array(list(itertools.product((-1, 0, 1), repeat=3)))


class CoordinateError(ValueError):
    """A coordinate that cannot be built or cannot be held."""


# ======================================================================
#  ANCHORS
# ======================================================================

def _nearest_image(frac_a, frac_b, lattice) -> np.ndarray:
    """The integer translation putting ``b`` in the image nearest ``a``.

    The same 27 candidates :func:`xtal.core.neighbors.min_image_vector`
    uses, but the *translation* is returned rather than the vector,
    because it is the translation an anchor keeps.
    """
    a = np.asarray(frac_a, dtype=float)
    b = np.asarray(frac_b, dtype=float)
    base = -np.round(b - a)
    candidates = lattice.to_cart((b - a) + base + _SHIFTS)
    best = int(np.argmin(np.linalg.norm(candidates, axis=1)))
    return base + _SHIFTS[best]


@dataclass(frozen=True)
class Anchor:
    """A point a coordinate is measured to: atoms and their images.

    ``shifts`` is one integer lattice translation per atom, so the
    cartesian point is ``mean(positions[atoms] + shifts @ matrix)`` --
    linear in both, which is what every gradient here relies on.
    """

    atoms: tuple[int, ...]
    shifts: np.ndarray = field(
        default_factory=lambda: np.zeros((0, 3), dtype=int))

    def __post_init__(self) -> None:
        if not self.atoms:
            raise CoordinateError("an anchor needs at least one atom")
        if len(self.shifts) != len(self.atoms):
            raise CoordinateError(
                "an anchor needs one image shift per atom")

    @property
    def size(self) -> int:
        return len(self.atoms)

    @property
    def is_atom(self) -> bool:
        return len(self.atoms) == 1

    def position(self, positions, matrix) -> np.ndarray:
        """The cartesian point, at these positions and this cell."""
        points = (np.asarray(positions)[list(self.atoms)]
                  + self.shifts @ np.asarray(matrix))
        return points.mean(axis=0)

    def points(self, positions, matrix) -> np.ndarray:
        """Every atom of the group, in its own held image."""
        return (np.asarray(positions)[list(self.atoms)]
                + self.shifts @ np.asarray(matrix))

    def scatter(self, into, vector) -> None:
        """Add ``vector``'s share of a gradient to each atom.

        A centroid spreads a derivative evenly over its atoms --
        ``d(mean)/d(atom) = 1/n`` -- which is the whole of the chain
        rule for a group.  ``np.add.at`` rather than fancy-index
        assignment because an atom may appear in the group twice.
        """
        np.add.at(into, list(self.atoms),
                  np.asarray(vector) / float(self.size))


def resolve(structure, cell, groups) -> tuple[Anchor, ...]:
    """Anchors for ``groups``, with their images chosen once.

    Within a group every atom is taken in the image nearest the
    group's first -- a star, as :func:`xtal.core.measure.centroid`
    does, because a selection has no order worth chaining.  Between
    groups the anchors are chained, each nearest the one before it, as
    :func:`xtal.core.measure.unwrapped_positions` does, so a torsion
    across a molecule that straddles the boundary follows the molecule.

    Dummy atoms are refused here.  This is the door, and the message
    has to name the way through it: the marker was almost certainly
    placed as a centroid, and the group it was the centroid *of* is
    what to hand in instead.
    """
    lattice = structure.lattice
    symbols = cell.elements
    n_atoms = cell.n_atoms
    anchors: list[Anchor] = []
    previous: np.ndarray | None = None
    # Chained in *fractional* space, and deliberately.  Going out to
    # cartesian and back through the inverse matrix costs about 1e-16
    # of a cell, which is nothing at all until four images are exactly
    # equidistant -- an atom half a cell away along two axes, which is
    # every second atom in a cubic crystal.  Then the noise is the
    # whole answer, and this function and the Measure panel pick
    # different images of the same atom.
    for group in groups:
        atoms = tuple(int(a) for a in group)
        if not atoms:
            raise CoordinateError("an anchor needs at least one atom")
        for a in atoms:
            if not 0 <= a < n_atoms:
                raise CoordinateError(
                    f"atom {a} is not in a cell of {n_atoms}")
            if elements.is_dummy(symbols[a]):
                raise CoordinateError(
                    f"atom {a} is a dummy marker, and a marker feels "
                    "no force from any engine -- holding a coordinate "
                    "to one would be satisfied by moving the marker.  "
                    "Give the atoms it marks instead: a group of them "
                    "is its centroid, and it follows them.")
        first = cell.frac[atoms[0]]
        shifts = np.array(
            [_nearest_image(first, cell.frac[a], lattice)
             for a in atoms], dtype=int)
        here = np.mean(cell.frac[list(atoms)] + shifts, axis=0)
        if previous is not None:
            step = _nearest_image(previous, here, lattice)
            shifts = shifts + step.astype(int)
            here = here + step
        anchors.append(Anchor(atoms, shifts))
        previous = here
    return tuple(anchors)


# ======================================================================
#  COORDINATES
# ======================================================================

class Coordinate(ABC):
    """Something a scan can set and an optimiser can hold fixed."""

    #: ``True`` for a coordinate of the cell rather than of the atoms.
    #: Those are held by restricting the strain (see
    #: :class:`xtal.ff.optimize.CellFreedom`) rather than by a
    #: constraint on the positions, because a cell parameter is not a
    #: function of where the atoms are at all.
    is_cell = False

    units = ""

    @property
    def tolerance(self) -> float:
        """How close to its target the coordinate has to be held.

        In the coordinate's own units, and looser for an angle than a
        length because a degree is a smaller thing than an Angstrom
        over the arm it turns: a thousandth of a degree at the end of
        a five-Angstrom linker is a ten-thousandth of an Angstrom.
        """
        return 1e-5 if self.units == "deg" else 1e-7

    @property
    @abstractmethod
    def label(self) -> str:
        """How the axis is named in a report and a dialog."""

    @property
    def atoms(self) -> tuple[int, ...]:
        """Every P1 atom the value depends on."""
        return ()

    @abstractmethod
    def value(self, positions, matrix) -> float:
        ...

    @abstractmethod
    def gradient(self, positions, matrix) -> np.ndarray:
        """``d(value)/d(position)``, one row per atom of the cell."""


@dataclass(frozen=True)
class _Between(Coordinate):
    """The shared part of every coordinate taken between anchors."""

    anchors: tuple[Anchor, ...]

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        """What this kind needs of its anchors.

        It lives here rather than in each subclass's own
        ``__post_init__`` because the subclasses are not themselves
        dataclasses: they inherit this class's generated ``__init__``,
        and that ``__init__`` was written to call the
        ``__post_init__`` that existed when *this* class was
        decorated.  A subclass defining its own would be ignored in
        silence.
        """

    @property
    def atoms(self) -> tuple[int, ...]:
        out: list[int] = []
        for anchor in self.anchors:
            out.extend(anchor.atoms)
        return tuple(dict.fromkeys(out))

    def _name(self) -> str:
        parts = []
        for anchor in self.anchors:
            parts.append(str(anchor.atoms[0]) if anchor.is_atom
                         else "{" + "+".join(
                             str(a) for a in anchor.atoms) + "}")
        return "-".join(parts)

    def _empty(self, positions) -> np.ndarray:
        return np.zeros_like(np.asarray(positions, dtype=float))


class Distance(_Between):
    """The distance between two anchors, in Angstrom."""

    units = "A"

    @property
    def label(self) -> str:
        return f"distance {self._name()}"

    def value(self, positions, matrix) -> float:
        first, second = (a.position(positions, matrix)
                         for a in self.anchors)
        return float(np.linalg.norm(second - first))

    def gradient(self, positions, matrix) -> np.ndarray:
        first, second = (a.position(positions, matrix)
                         for a in self.anchors)
        vector = second - first
        length = float(np.linalg.norm(vector))
        out = self._empty(positions)
        if length < 1e-12:
            return out
        unit = vector / length
        self.anchors[0].scatter(out, -unit)
        self.anchors[1].scatter(out, unit)
        return out


class Angle(_Between):
    """The angle across three anchors, in degrees, vertex in the
    middle."""

    units = "deg"

    @property
    def label(self) -> str:
        return f"angle {self._name()}"

    def value(self, positions, matrix) -> float:
        p = [a.position(positions, matrix) for a in self.anchors]
        u, v = p[0] - p[1], p[2] - p[1]
        scale = np.linalg.norm(u) * np.linalg.norm(v)
        if scale < 1e-12:
            return float("nan")
        cosine = float(np.clip((u @ v) / scale, -1.0, 1.0))
        return float(np.degrees(np.arccos(cosine)))

    def gradient(self, positions, matrix) -> np.ndarray:
        p = [a.position(positions, matrix) for a in self.anchors]
        u, v = p[0] - p[1], p[2] - p[1]
        lu, lv = float(np.linalg.norm(u)), float(np.linalg.norm(v))
        out = self._empty(positions)
        if lu < 1e-12 or lv < 1e-12:
            return out
        uh, vh = u / lu, v / lv
        cosine = float(np.clip(uh @ vh, -1.0, 1.0))
        sine = float(np.sqrt(max(1.0 - cosine * cosine, 0.0)))
        if sine < 1e-9:                 # linear: the angle is flat
            return out
        scale = np.degrees(1.0)
        first = (cosine * uh - vh) / (lu * sine) * scale
        third = (cosine * vh - uh) / (lv * sine) * scale
        self.anchors[0].scatter(out, first)
        self.anchors[1].scatter(out, -(first + third))
        self.anchors[2].scatter(out, third)
        return out


class Torsion(_Between):
    """The dihedral across four anchors, in degrees, in (-180, 180].

    Signed by the same IUPAC convention
    :func:`xtal.core.measure.torsion` uses, so the number a scan holds
    is the number the Measure panel shows.
    """

    units = "deg"

    @property
    def label(self) -> str:
        return f"torsion {self._name()}"

    def value(self, positions, matrix) -> float:
        p = [a.position(positions, matrix) for a in self.anchors]
        b1, b2, b3 = p[1] - p[0], p[2] - p[1], p[3] - p[2]
        n1, n2 = np.cross(b1, b2), np.cross(b2, b3)
        length = float(np.linalg.norm(b2))
        if (length < 1e-9 or np.linalg.norm(n1) < 1e-9
                or np.linalg.norm(n2) < 1e-9):
            return float("nan")
        x = float(n1 @ n2)
        y = float((np.cross(n1, n2) @ b2) / length)
        return float(np.degrees(np.arctan2(y, x)))

    def gradient(self, positions, matrix) -> np.ndarray:
        p = [a.position(positions, matrix) for a in self.anchors]
        b1, b2, b3 = p[1] - p[0], p[2] - p[1], p[3] - p[2]
        n1, n2 = np.cross(b1, b2), np.cross(b2, b3)
        l2 = float(np.linalg.norm(b2))
        s1, s2 = float(n1 @ n1), float(n2 @ n2)
        out = self._empty(positions)
        if l2 < 1e-9 or s1 < 1e-18 or s2 < 1e-18:
            return out
        scale = np.degrees(1.0)
        # Blondel and Karplus' form.  The two end atoms move the
        # dihedral on their own normals; the two middle ones take what
        # is left, which is what makes the four derivatives sum to
        # zero -- a torsion does not change when the whole fragment is
        # translated, and a gradient that failed to say so would drag
        # the crystal sideways one step at a time.
        #
        # The published form writes its first bond from the second
        # atom outwards, where ``b1`` here runs the other way with the
        # chain; that is one sign, on ``a`` alone, and getting it
        # wrong leaves the two end derivatives perfect and the two
        # middle ones quietly wrong -- which is why the test differs
        # every atom rather than spot-checking one.
        first = -(l2 / s1) * n1 * scale
        fourth = (l2 / s2) * n2 * scale
        a = float(b1 @ b2) / (l2 * l2)
        b = float(b3 @ b2) / (l2 * l2)
        second = -(a + 1.0) * first + b * fourth
        third = a * first - (b + 1.0) * fourth
        self.anchors[0].scatter(out, first)
        self.anchors[1].scatter(out, second)
        self.anchors[2].scatter(out, third)
        self.anchors[3].scatter(out, fourth)
        return out


def _normal(points) -> np.ndarray | None:
    """The best-fit normal, or ``None`` when the points do not fix one.

    A least-squares normal is the direction the points vary along
    least, and it only means anything when they vary along it
    *distinctly* less than along the two in the plane.  Four atoms
    round a symmetric site have three equal spreads and every
    direction is equally the normal; a linear molecule has two.  The
    fitted answer in both cases is whichever way the rounding error
    pointed, and its derivative is enormous and meaningless -- the
    kind of number that produces a confident landscape of nothing.

    So the two smallest singular values are compared, and a normal
    that is not separated from the plane by :data:`PLANE_TOLERANCE` is
    refused as no normal at all.  A scan then cannot hold the
    coordinate, which is the honest outcome.
    """
    points = np.asarray(points, dtype=float).reshape(-1, 3)
    if len(points) < 3:                                # pragma: no cover
        return None
    values = np.linalg.svd(points - points.mean(axis=0))[1]
    if values[1] <= PLANE_TOLERANCE * values[0]:
        return None                   # collinear: no plane at all
    if values[2] > (1.0 - PLANE_TOLERANCE) * values[1]:
        return None                   # isotropic: every way is normal
    return transforms.best_fit_plane(points)[1]


class PlaneAngle(_Between):
    """The angle between the best-fit planes of two anchors, in
    degrees, folded onto ``[0, 90]``.

    The gradient is central differences over the defining atoms, and
    that is a deliberate choice rather than a shortcut.  The analytic
    derivative of a least-squares normal is an eigenvector
    perturbation -- correct, fiddly, and degenerate exactly when the
    two smallest singular values meet, which is a nearly spherical
    group of atoms.  Differencing costs six evaluations per atom of
    *arithmetic*, not of energy: microseconds, against the seconds an
    engine takes for one force call.
    """

    units = "deg"

    def _validate(self) -> None:
        for anchor in self.anchors:
            if anchor.size < 3:
                raise CoordinateError(
                    "a plane needs at least three atoms; this anchor "
                    f"has {anchor.size}")

    @property
    def label(self) -> str:
        return f"plane angle {self._name()}"

    def value(self, positions, matrix) -> float:
        normals = []
        for anchor in self.anchors:
            normal = _normal(anchor.points(positions, matrix))
            if normal is None:
                return float("nan")
            normals.append(normal)
        cosine = float(np.clip(abs(normals[0] @ normals[1]), 0.0, 1.0))
        return float(np.degrees(np.arccos(cosine)))

    def gradient(self, positions, matrix) -> np.ndarray:
        base = np.asarray(positions, dtype=float)
        out = self._empty(positions)
        if not np.isfinite(self.value(base, matrix)):
            return out
        for atom in self.atoms:
            for axis in range(3):
                moved = base.copy()
                moved[atom, axis] += PLANE_STEP
                high = self.value(moved, matrix)
                moved[atom, axis] -= 2.0 * PLANE_STEP
                low = self.value(moved, matrix)
                out[atom, axis] = (high - low) / (2.0 * PLANE_STEP)
        return out


# ======================================================================
#  THE CELL
# ======================================================================

@dataclass(frozen=True)
class CellParameter(Coordinate):
    """One of a, b, c, alpha, beta, gamma."""

    name: str
    is_cell = True

    def __post_init__(self) -> None:
        if self.name not in PARAMETER_NAMES:
            raise CoordinateError(
                f"{self.name!r} is not a cell parameter; expected one "
                f"of {', '.join(PARAMETER_NAMES)}")

    @property
    def index(self) -> int:
        return PARAMETER_NAMES.index(self.name)

    @property
    def label(self) -> str:
        return self.name

    @property
    def units(self) -> str:
        return "A" if self.index < 3 else "deg"

    def value(self, positions, matrix) -> float:
        return float(Lattice(np.asarray(matrix)).parameters[self.index])

    def gradient(self, positions, matrix) -> np.ndarray:
        return np.zeros_like(np.asarray(positions, dtype=float))


@dataclass(frozen=True)
class CellVolume(Coordinate):
    """The cell volume, with its shape left free.

    The axis the literature actually uses for a flexible framework:
    relaxing the cell *shape* at each fixed volume is what keeps the
    profile from being an artefact of whichever shape was frozen.
    """

    is_cell = True
    units = "A^3"

    @property
    def label(self) -> str:
        return "volume"

    def value(self, positions, matrix) -> float:
        return float(abs(np.linalg.det(np.asarray(matrix))))

    def gradient(self, positions, matrix) -> np.ndarray:
        return np.zeros_like(np.asarray(positions, dtype=float))


# ======================================================================
#  BUILDING ONE
# ======================================================================

#: How many anchors each kind of internal coordinate takes.
BETWEEN = {"distance": 2, "angle": 3, "torsion": 4, "plane angle": 2}

_CLASSES = {"distance": Distance, "angle": Angle, "torsion": Torsion,
            "plane angle": PlaneAngle}


def internal(structure, cell, kind, groups) -> Coordinate:
    """A coordinate of ``kind`` over ``groups`` of P1 atoms.

    The one door in: it resolves the images once (see the module
    docstring) and refuses a group count the kind cannot use, so that
    no caller has to know how many anchors a torsion takes.
    """
    if kind not in _CLASSES:
        raise CoordinateError(
            f"{kind!r} is not a coordinate; expected one of "
            f"{', '.join(sorted(_CLASSES))}")
    groups = tuple(tuple(int(a) for a in g) for g in groups)
    wanted = BETWEEN[kind]
    if len(groups) != wanted:
        raise CoordinateError(
            f"a {kind} takes {wanted} anchors, not {len(groups)}")
    return _CLASSES[kind](resolve(structure, cell, groups))
