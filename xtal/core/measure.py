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

from xtal.core import neighbors

# Kinds of measurement, by how many atoms they take.
KINDS = {2: "distance", 3: "angle", 4: "torsion"}
UNITS = {"distance": "A", "angle": "deg", "torsion": "deg"}


@dataclass(frozen=True)
class Measurement:
    """One measurement over atoms of the P1 cell."""

    atoms: tuple[int, ...]
    kind: str
    value: float
    labels: tuple[str, ...] = ()

    @property
    def unit(self) -> str:
        return UNITS[self.kind]

    def text(self) -> str:
        names = " - ".join(self.labels or
                           [str(a) for a in self.atoms])
        digits = 4 if self.kind == "distance" else 2
        return f"{names}   {self.value:.{digits}f} {self.unit}"

    def to_dict(self) -> dict:
        return {"atoms": list(self.atoms), "kind": self.kind,
                "value": self.value, "labels": list(self.labels)}

    @classmethod
    def from_dict(cls, d: dict) -> Measurement:
        return cls(tuple(d["atoms"]), d["kind"], float(d["value"]),
                   tuple(d.get("labels", ())))


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
