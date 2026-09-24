"""
xtal.analysis.kpath
===================
Where a band structure goes: the Brillouin zone, and a path through it.

**The special points are this cell's, not a textbook's.**  Gamma, X,
M and L are defined for a standard setting, and the same letter is a
different vector in a cell that is not in it -- a fractional k of
(0.5, 0, 0) is X in one fcc setting and nothing in particular in the
primitive cell a user actually has open.  ASE's ``Cell.bandpath``
works out the Bravais type and returns the points already expressed
in the reciprocal basis of the cell it was handed, which is the only
basis DFTB+ can be given them in.  It is the ``ase`` extra, and the
band-structure entry greys out naming it; the check is ``find_spec``.

**The zone itself needs nothing but scipy.**  It is the Wigner-Seitz
cell of the reciprocal lattice -- every point nearer the origin than
any other reciprocal lattice point -- which is the Voronoi cell of the
origin among its neighbours.  A fcc crystal's is the truncated
octahedron, fourteen faces and twenty-four corners, and that is the
test.

Positions along the path are cartesian reciprocal distances, in 1/A
including the 2 pi, so a band structure's x axis is to scale and a
long segment looks long.
"""

from __future__ import annotations

import importlib.util
import itertools
from dataclasses import dataclass, field

import numpy as np
from scipy.spatial import ConvexHull, Voronoi

from xtal import install
from xtal.ff.dftb.hsd import KLines

#: Points per reciprocal Angstrom along the path.
DEFAULT_DENSITY = 40

#: How a label is shown.  ASE spells Gamma ``G``.
GREEK = {"G": "Γ"}

MISSING = ("the band path needs ASE, which works out the special "
           f"points of this cell: {install.command('ase')}")


def installed() -> bool:
    return importlib.util.find_spec("ase") is not None


def reciprocal(lattice) -> np.ndarray:
    """The reciprocal vectors as rows, with the 2 pi."""
    return 2 * np.pi * np.linalg.inv(
        np.asarray(lattice.matrix, dtype=float)).T


def pretty(label: str) -> str:
    return GREEK.get(label, label)


# ======================================================================
#  THE PATH
# ======================================================================

@dataclass(frozen=True)
class BandPath:
    """Named points in fractions of the reciprocal vectors, and the
    runs of them the path visits -- a new run is a jump, drawn as one
    tick labelled ``U|K``."""

    points: dict = field(default_factory=dict)
    runs: tuple = ()

    @property
    def text(self) -> str:
        return ",".join("".join(run) for run in self.runs)

    def with_text(self, text: str) -> BandPath:
        return BandPath(self.points, parse_path(text, self.points))


def band_path(lattice) -> BandPath:
    """ASE's recommended path for this cell."""
    if not installed():
        raise RuntimeError(MISSING)
    from ase.cell import Cell
    path = Cell(np.asarray(lattice.matrix, dtype=float)).bandpath(
        npoints=0)
    points = {name: tuple(float(v) for v in k)
              for name, k in path.special_points.items()}
    return BandPath(points, parse_path(path.path, points))


def parse_path(text: str, points) -> tuple:
    """``"GXWKGL,UX"`` into runs of point names.

    Longest name first, because ASE has ``X`` and ``X1`` in the same
    lattice and reading ``X1`` as ``X`` then ``1`` is not an error it
    would otherwise report.
    """
    names = sorted(points, key=len, reverse=True)
    runs = []
    for chunk in str(text).replace(" ", "").split(","):
        run, rest = [], chunk
        while rest:
            for name in names:
                if rest.startswith(name):
                    run.append(name)
                    rest = rest[len(name):]
                    break
            else:
                raise ValueError(
                    f"{rest[:3]!r} is not a point of this cell; it has "
                    f"{', '.join(sorted(points))}")
        if run:
            runs.append(tuple(run))
    if not runs or sum(len(run) for run in runs) < 2:
        raise ValueError("a band path needs at least two points")
    return tuple(runs)


def klines(path: BandPath, lattice,
           density: float = DEFAULT_DENSITY) -> KLines:
    """The path as DFTB+'s ``Klines``, sampled at ``density`` points
    per reciprocal Angstrom and never fewer than two a segment."""
    b = reciprocal(lattice)
    segments, labels = [], []
    previous = None
    for run in path.runs:
        for number, name in enumerate(run):
            k = np.array(path.points[name])
            if previous is None or number == 0:
                segments.append((1, tuple(float(v) for v in k)))
            else:
                length = float(np.linalg.norm((k - previous) @ b))
                segments.append((max(2, int(round(length * density))),
                                 tuple(float(v) for v in k)))
            labels.append(name)
            previous = k
    return KLines(tuple(segments), tuple(labels))


def positions(lines: KLines, lattice) -> tuple[np.ndarray, list]:
    """``(x, ticks)``: each k-point's distance along the path in 1/A,
    and ``(x, label)`` at every named point, a jump's two names joined
    with a bar."""
    b = reciprocal(lattice)
    x, ticks = [], []
    here, previous = 0.0, None
    for (count, k), label in zip(lines.segments, lines.labels,
                                 strict=True):
        k = np.array(k, dtype=float)
        if previous is None or count == 1:
            x.append(here)
            name = pretty(label)
            if ticks and np.isclose(ticks[-1][0], here):
                ticks[-1] = (here, f"{ticks[-1][1]}|{name}")
            else:
                ticks.append((here, name))
        else:
            step = float(np.linalg.norm((k - previous) @ b)) / count
            x.extend(here + step * (i + 1) for i in range(count))
            here += step * count
            ticks.append((here, pretty(label)))
        previous = k
    return np.array(x), ticks


# ======================================================================
#  THE ZONE
# ======================================================================

@dataclass(frozen=True)
class Zone:
    """The first Brillouin zone: corners in cartesian 1/A, faces as
    loops of corner indices in order, and each edge once."""

    vertices: np.ndarray
    faces: tuple
    edges: tuple


def brillouin_zone(lattice) -> Zone:
    b = reciprocal(lattice)
    shifts = np.array(list(itertools.product(range(-2, 3), repeat=3)))
    points = shifts @ b
    origin = int(np.flatnonzero(~shifts.any(axis=1))[0])
    voronoi = Voronoi(points)
    region = voronoi.regions[voronoi.point_region[origin]]
    if -1 in region or not region:
        raise ValueError("the Brillouin zone did not close; the "
                         "reciprocal cell is degenerate")
    corners = voronoi.vertices[region]
    # A Voronoi cell is convex, so its hull is the zone; the hull's
    # triangles are merged back into the flat faces they tile.
    hull = ConvexHull(corners)
    faces = _flat_faces(corners, hull)
    edges = sorted({tuple(sorted((face[i], face[(i + 1) % len(face)])))
                    for face in faces for i in range(len(face))})
    return Zone(corners, tuple(faces), tuple(edges))


def _flat_faces(corners, hull) -> list[tuple]:
    planes: dict[tuple, set] = {}
    for simplex, equation in zip(hull.simplices, hull.equations,
                                 strict=True):
        key = tuple(np.round(equation, 6))
        planes.setdefault(key, set()).update(int(v) for v in simplex)
    faces = []
    for key, members in planes.items():
        normal = np.array(key[:3])
        ids = sorted(members)
        centre = corners[ids].mean(axis=0)
        u = corners[ids[0]] - centre
        u /= np.linalg.norm(u)
        v = np.cross(normal, u)
        angle = [np.arctan2((corners[i] - centre) @ v,
                            (corners[i] - centre) @ u) for i in ids]
        faces.append(tuple(i for _a, i in sorted(zip(angle, ids,
                                                     strict=True))))
    return faces
