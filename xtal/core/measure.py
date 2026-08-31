"""
xtal.core.measure
=================
Distances, angles and torsions between atoms of the cell.

Every one of them is computed on the **minimum-image** vector between
the atoms, not on the difference of their fractional coordinates.  In a
crystal those are not the same thing: two atoms bonded across the cell
boundary sit at x = 0.02 and x = 0.98, and subtracting the coordinates
gives 0.96 of a cell -- the long way round, through the vacuum -- where
the bond is 0.04.  A measurement tool that reports the long way round
is worse than no measurement tool, because the number looks plausible.

Angles and torsions chain the same rule: each successive atom is placed
in the image nearest the one before it, so a measurement across a
molecule that straddles the boundary follows the molecule rather than
jumping.  That is the only interpretation under which the numbers mean
what a chemist means by them.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from xtal.core import neighbors, transforms

# Kinds of measurement, by how many atoms they take.
KINDS = {2: "distance", 3: "angle", 4: "torsion"}

#: An angle between two *planes*, which is not taken between atoms at
#: all and so has no entry in :data:`KINDS`.  It is a measurement like
#: any other once it exists -- it follows the crystal, it is dropped
#: when its atoms are, and it is written into the project.
PLANE_ANGLE = "plane angle"

UNITS = {"distance": "A", "angle": "deg", "torsion": "deg",
         PLANE_ANGLE: "deg"}


@dataclass(frozen=True)
class Measurement:
    """One measurement over atoms of the P1 cell.

    ``planes`` is empty for the measurements taken between atoms, and
    holds the two atom groups for an interplanar angle.  ``atoms`` is
    still every atom the measurement depends on either way, which is
    what lets one rule -- "drop it when one of its atoms goes" --
    cover both.
    """

    atoms: tuple[int, ...]
    kind: str
    value: float
    labels: tuple[str, ...] = ()
    planes: tuple[tuple[int, ...], ...] = ()

    @property
    def unit(self) -> str:
        return UNITS[self.kind]

    def text(self) -> str:
        joiner = " ^ " if self.planes else " - "
        names = joiner.join(self.labels or
                            [str(a) for a in self.atoms])
        digits = 4 if self.kind == "distance" else 2
        return f"{names}   {self.value:.{digits}f} {self.unit}"

    def to_dict(self) -> dict:
        out = {"atoms": list(self.atoms), "kind": self.kind,
               "value": self.value, "labels": list(self.labels)}
        if self.planes:
            out["planes"] = [list(group) for group in self.planes]
        return out

    @classmethod
    def from_dict(cls, d: dict) -> Measurement:
        return cls(tuple(d["atoms"]), d["kind"], float(d["value"]),
                   tuple(d.get("labels", ())),
                   tuple(tuple(int(a) for a in group)
                         for group in d.get("planes", ())))


# ======================================================================
#  THE CHAIN
# ======================================================================

def unwrapped_positions(cell, lattice, atoms) -> np.ndarray:
    """Cartesian positions of ``atoms``, each in the periodic image
    nearest the atom before it.

    This is what makes a measurement follow a molecule across the cell
    boundary instead of jumping to the far side of the box.
    """
    indices = [int(a) for a in atoms]
    points = [lattice.to_cart(cell.frac[indices[0]])]
    for previous, current in zip(indices, indices[1:],
                                 strict=False):
        step = neighbors.min_image_vector(cell.frac[previous],
                                          cell.frac[current], lattice)
        points.append(points[-1] + step)
    return np.array(points)


def distance(cell, lattice, i: int, j: int) -> float:
    """Minimum-image distance in Angstrom."""
    return neighbors.min_image_distance(cell.frac[int(i)],
                                        cell.frac[int(j)], lattice)


def angle(cell, lattice, i: int, j: int, k: int) -> float:
    """The i-j-k angle in degrees, with ``j`` at the vertex."""
    points = unwrapped_positions(cell, lattice, (i, j, k))
    first = points[0] - points[1]
    second = points[2] - points[1]
    return _angle_between(first, second)


def torsion(cell, lattice, i: int, j: int, k: int, m: int) -> float:
    """The i-j-k-m dihedral in degrees, in (-180, 180].

    Signed by the IUPAC convention: looking along j->k, positive when
    the far bond is rotated clockwise from the near one.
    """
    p = unwrapped_positions(cell, lattice, (i, j, k, m))
    b1, b2, b3 = p[1] - p[0], p[2] - p[1], p[3] - p[2]
    normal1 = np.cross(b1, b2)
    normal2 = np.cross(b2, b3)
    length = np.linalg.norm(b2)
    if (length < 1e-9 or np.linalg.norm(normal1) < 1e-9
            or np.linalg.norm(normal2) < 1e-9):
        return float("nan")             # collinear: no plane, no angle
    x = float(normal1 @ normal2)
    y = float((np.cross(normal1, normal2) @ b2) / length)
    return float(np.degrees(np.arctan2(y, x)))


def _angle_between(first, second) -> float:
    scale = np.linalg.norm(first) * np.linalg.norm(second)
    if scale < 1e-12:
        return float("nan")
    cosine = float(np.clip((first @ second) / scale, -1.0, 1.0))
    return float(np.degrees(np.arccos(cosine)))


# ======================================================================
#  PLANES
# ======================================================================
#
# A plane is defined by the atoms that lie in it, not by four numbers:
# the atoms are what the user picked, they are what the plane has to
# follow when the crystal changes, and re-fitting three floats from
# them costs nothing.

@dataclass(eq=False)
class Plane:
    """A least-squares plane through three or more atoms of the cell.

    Three atoms determine a plane exactly; more than three are fitted,
    which is the case that matters -- a phenyl ring, a coordination
    square, a layer -- and is why ``deviation`` is carried alongside.
    A benzene ring reports 0.00 A and a badly refined one reports 0.11,
    and the angle to the next plane means something quite different in
    the two cases.

    The positions are taken with :func:`unwrapped_positions`, so a ring
    lying across a cell face is fitted as the ring it is rather than as
    two halves on opposite sides of the box.
    """

    atoms: tuple[int, ...]
    centroid: np.ndarray
    normal: np.ndarray
    deviation: float
    labels: tuple[str, ...] = ()
    name: str = ""

    def text(self) -> str:
        atoms = ", ".join(self.labels or [str(a) for a in self.atoms])
        return (f"{self.name or 'plane'}: {atoms}"
                f"   rms {self.deviation:.3f} A")

    def to_dict(self) -> dict:
        return {"atoms": list(self.atoms), "name": self.name,
                "labels": list(self.labels)}


def plane(cell, lattice, atoms, labels=None, name: str = "") -> Plane:
    """Fit a plane through three or more atoms of the P1 cell."""
    indices = tuple(int(a) for a in atoms)
    if len(set(indices)) != len(indices):
        raise ValueError("an atom cannot be named twice in a plane")
    if len(indices) < 3:
        raise ValueError(
            f"a plane needs at least three atoms, not {len(indices)}")
    points = unwrapped_positions(cell, lattice, indices)
    centroid, normal = transforms.best_fit_plane(points)
    if labels is None:
        labels = tuple(cell.labels[a] or cell.elements[a]
                       for a in indices)
    return Plane(indices, centroid, normal,
                 transforms.plane_deviation(points), tuple(labels),
                 name)


def plane_angle(first: Plane, second: Plane) -> float:
    """The angle between two planes, in degrees, in [0, 90].

    A plane has no side: its normal could as well have been computed
    pointing the other way, and the fit does not decide which.  So the
    obtuse answer is folded onto the acute one -- 175 degrees between
    two normals is 5 degrees between the planes, which is what anybody
    reading "the two rings are nearly parallel" means.
    """
    angle_between = _angle_between(first.normal, second.normal)
    if angle_between != angle_between:               # nan
        return angle_between
    return angle_between if angle_between <= 90.0 else 180.0 - angle_between


def interplanar_angle(first: Plane, second: Plane) -> Measurement:
    """The angle between two planes, as a measurement.

    Its ``atoms`` are the atoms of both planes, so it is pruned and
    recomputed by the same rules as every other measurement.
    """
    atoms = tuple(dict.fromkeys(first.atoms + second.atoms))
    names = (first.name or "plane 1", second.name or "plane 2")
    return Measurement(atoms, PLANE_ANGLE,
                       plane_angle(first, second), names,
                       (first.atoms, second.atoms))


# ======================================================================
#  THE FRONT DOOR
# ======================================================================

def measure(cell, lattice, atoms, labels=None) -> Measurement:
    """Measure two, three or four atoms -- whichever it is.

    The number of atoms picked is the whole of the choice between a
    distance, an angle and a torsion, so nothing above this has to ask.
    """
    indices = tuple(int(a) for a in atoms)
    kind = KINDS.get(len(indices))
    if kind is None:
        raise ValueError(
            f"measure 2, 3 or 4 atoms, not {len(indices)}")
    if len(set(indices)) != len(indices):
        raise ValueError("an atom cannot be measured against itself")

    function = {"distance": distance, "angle": angle,
                "torsion": torsion}[kind]
    value = function(cell, lattice, *indices)
    if labels is None:
        labels = tuple(cell.labels[a] or cell.elements[a]
                       for a in indices)
    return Measurement(indices, kind, value, tuple(labels))
