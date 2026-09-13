"""
xtal.analysis.overlays
======================
What a run can draw over a crystal that is not part of it, beside the
pore network: atomic charges, and an orbital's two lobes.

Both follow the pore network's rules (:class:`~xtal.analysis.porosity.
PoreNetwork`), and for the same reason: each is a calculation's answer
*about* one arrangement of one set of atoms.  Put there by a run, not
an edit and not on the undo stack; dropped the moment the atoms move
or change, because a charge on an atom that has moved is a number
about somewhere else.

**Charges are saved into a project; an orbital is not.**  A charge is
a number per atom and a session's worth of JSON costs nothing.  An
orbital is a surface of tens of thousands of triangles marched from a
cube file that is still in the run folder, and writing it into the
project would be the pore surface's 59 MB mistake again.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class AtomCharges:
    """One charge in e per atom of the P1 cell, positive for electrons
    lost."""

    values: np.ndarray = field(default_factory=lambda: np.zeros(0))
    label: str = "Mulliken charge"

    @property
    def n_atoms(self) -> int:
        return len(self.values)

    @property
    def scale(self) -> float:
        """The largest magnitude, which the colour map is scaled to --
        symmetric, so zero is always the neutral colour."""
        return float(np.abs(self.values).max()) if self.n_atoms else 0.0

    def colors(self) -> np.ndarray:
        """``(N, 3)`` uint8: blue for negative, white for neutral, red
        for positive -- a diverging map, because the sign is the
        information and a rainbow would bury it."""
        scale = self.scale or 1.0
        t = np.clip(np.asarray(self.values, float) / scale, -1.0, 1.0)
        white = np.array([245.0, 245.0, 245.0])
        red = np.array([200.0, 40.0, 40.0])
        blue = np.array([40.0, 80.0, 200.0])
        out = np.where(t[:, None] >= 0,
                       white + t[:, None] * (red - white),
                       white - t[:, None] * (blue - white))
        return np.round(out).astype(np.uint8)

    def to_dict(self) -> dict:
        return {"values": [float(v) for v in self.values],
                "label": self.label}

    @classmethod
    def from_dict(cls, data: dict) -> AtomCharges:
        return cls(np.array(data.get("values", ()), dtype=float),
                   str(data.get("label", "Mulliken charge")))


#: The lobes' colours: positive and negative phase.
POSITIVE = (210, 60, 60)
NEGATIVE = (60, 90, 210)


@dataclass(frozen=True)
class OrbitalSurface:
    """The two isosurfaces of one orbital, in fractional coordinates.

    ``signs`` is +1 or -1 per triangle, which is the phase and the only
    thing the colour says.  ``level`` is the value the surfaces were cut
    at, reported beside the picture because an orbital with no level is
    a shape of no particular size.
    """

    points: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))
    faces: np.ndarray = field(
        default_factory=lambda: np.zeros((0, 3), int))
    signs: np.ndarray = field(default_factory=lambda: np.zeros(0, int))
    level: float = 0.0
    label: str = ""

    @property
    def n_faces(self) -> int:
        return len(self.faces)

    def colors(self) -> np.ndarray:
        return np.where(np.asarray(self.signs)[:, None] > 0,
                        np.array(POSITIVE, np.uint8),
                        np.array(NEGATIVE, np.uint8)).astype(np.uint8)


def orbital_surface(cube, lattice, level: float,
                    label: str = "") -> OrbitalSurface:
    """March both phases of a cube's field at ``+level`` and ``-level``
    and carry them into ``lattice``'s fractional coordinates.

    :func:`~xtal.analysis.isosurface.isosurface` answers in fractions of
    the *grid*; a waveplot grid is laid over the unit cell but its
    origin and step are its own, so each point goes through the cube's
    axes to Angstrom and back into the cell.
    """
    from xtal.analysis.isosurface import isosurface

    shape = np.array(cube.shape, dtype=float)
    points, faces, signs = [], [], []
    base = 0
    for sign in (1, -1):
        grid_frac, triangles = isosurface(sign * cube.values, lattice,
                                          abs(level))
        if not len(triangles):
            continue
        # The marcher hands back every edge point of every cut cell and
        # indexes only the crossed ones; the rest can lie anywhere, and
        # a surface that carried them would carry their bounds too.
        used, triangles = np.unique(triangles, return_inverse=True)
        triangles = triangles.reshape(-1, 3)
        grid_frac = grid_frac[used]
        cart = cube.origin + (grid_frac * shape) @ cube.axes
        points.append(lattice.to_frac(cart))
        faces.append(triangles + base)
        signs.append(np.full(len(triangles), sign))
        base += len(grid_frac)
    if not points:
        return OrbitalSurface(level=level, label=label)
    return OrbitalSurface(np.vstack(points), np.vstack(faces),
                          np.concatenate(signs), level, label)
