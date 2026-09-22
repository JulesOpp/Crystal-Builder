"""
xtal.analysis.grid
==================
How far every point in the cell is from the nearest atom.

One scalar field, sampled on a regular grid in fractional coordinates,
holding the distance from each point to the *surface* of the nearest
atom -- centre distance minus that atom's radius.  Its zero set is the
van der Waals surface; its ``r`` set is where the centre of a probe of
radius ``r`` can sit, which is the boundary of the accessible volume
Zeo++'s ``-vol`` measures.

**Ours rather than Zeo++'s, and not by preference.**  Zeo++ 0.3 writes
a distance grid two ways and neither can be used: ``-gridGAI`` aborts
with *"Need to resample in grid calc"* on MFU-4l, and ``-gridG`` ran
for six minutes on the same file without writing anything.  A KD-tree
over the cell and its periodic images answers in a second, and it
answers with the radii table the caller names -- which is what lets the
drawn surface and the quoted volume be the same measurement.

Qt-free and VTK-free, like everything in :mod:`xtal.analysis`.
"""

from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from xtal.core import p1

#: Grid spacing in Angstrom.  0.4 is fine enough that a 3 A window
#: reads as a window rather than as a staircase, and coarse enough
#: that a 30 A framework is under half a million points.
DEFAULT_SPACING = 0.4

#: The smallest grid worth marching.  Below this the surface is a
#: handful of triangles and says nothing.
MIN_POINTS = 8


def shape_for(lattice, spacing: float = DEFAULT_SPACING) -> tuple:
    """How many samples along each axis, at about ``spacing``.

    From the cell *lengths* and not the volume, so an anisotropic cell
    is sampled evenly in space rather than evenly in fractions -- a
    layered structure with c = 30 A and a = 5 A wants six times as
    many planes as rows, and a fixed count per axis would give it the
    same and draw a surface finer in one direction than the other.
    """
    lengths = np.linalg.norm(np.asarray(lattice.matrix, float), axis=1)
    return tuple(int(max(MIN_POINTS, round(length / max(spacing, 0.05))))
                 for length in lengths)


def distance_grid(structure, radius_of, spacing: float = DEFAULT_SPACING,
                  shape: tuple | None = None) -> np.ndarray:
    """Distance to the nearest atom surface, on a periodic grid.

    ``radius_of`` is called with an element symbol and returns its
    radius -- :func:`xtal.analysis.porosity.zeo_radius`, or this
    application's own table.  It is a parameter and not a default
    because every number a porosity run reports is a function of it,
    and a picture drawn with a different one is a picture of a
    different crystal.

    Returns a ``(na, nb, nc)`` float32 array of Angstrom, negative
    inside an atom.  Index ``(i, j, k)`` is the point at fractional
    ``(i/na, j/nb, k/nc)``, so the array wraps: the caller marches it
    periodically and no padding is needed at the faces.  Single
    precision because it is a distance on a 0.4 A grid, and 1e-7 of
    one is not a thing a surface can show.
    """
    lattice = structure.lattice
    shape = shape or shape_for(lattice, spacing)
    cell = p1.expand(structure)
    if not cell.n_atoms:
        return np.full(shape, np.inf, dtype=np.float32)

    centres, radii = _images(cell, lattice, radius_of)
    tree = cKDTree(centres)
    frac = _sample_points(shape)

    # The nearest atom *surface* is not the nearest atom centre: a
    # large atom a little further away can still be the one whose skin
    # is closest.  So the k nearest centres are asked for and the
    # radius is taken off each, which is exact as long as k covers the
    # spread of radii -- and the spread over a periodic crystal is one
    # coordination shell, not the whole cell.
    #
    # A block of points at a time: the k-nearest answer for the whole
    # of MFU-4l's 475 000 points was four (N, 8) arrays at once.
    k = min(_NEIGHBOURS, len(centres))
    out = np.empty(len(frac), dtype=np.float32)
    for start in range(0, len(frac), _POINT_BLOCK):
        points = lattice.to_cart(frac[start:start + _POINT_BLOCK])
        distances, index = tree.query(points, k=k)
        distances = distances.reshape(len(points), -1)
        index = index.reshape(len(points), -1)
        out[start:start + len(points)] = (
            distances - radii[index]).min(axis=1)
    return out.reshape(shape)


#: Grid points per KD-tree query in :func:`distance_grid`.
_POINT_BLOCK = 32768


#: How many neighbouring centres to consider per grid point.  Eight is
#: more than a coordination shell and covers any spread of radii a
#: real table has: the correction a ninth neighbour could make is the
#: difference between the largest and smallest radius, and it would
#: have to be nearer than the eighth already found.
_NEIGHBOURS = 8


def _sample_points(shape) -> np.ndarray:
    """The grid, as ``(N, 3)`` fractional coordinates in C order."""
    axes = [np.arange(n, dtype=float) / n for n in shape]
    mesh = np.meshgrid(*axes, indexing="ij")
    return np.stack([m.ravel() for m in mesh], axis=1)


def _images(cell, lattice, radius_of) -> tuple:
    """Every atom of the cell and of its 26 neighbouring cells.

    The whole shell rather than a minimum-image convention, because a
    grid point near a face is nearer to an atom in the next cell than
    to anything in this one, and a KD-tree has no idea the box repeats.
    Twenty-seven copies of a framework is tens of thousands of points,
    which a tree handles without noticing.
    """
    shifts = np.array([[a, b, c]
                       for a in (-1, 0, 1)
                       for b in (-1, 0, 1)
                       for c in (-1, 0, 1)], dtype=float)
    frac = (cell.frac[None, :, :] + shifts[:, None, :]).reshape(-1, 3)
    one_cell = np.array([float(radius_of(e)) for e in cell.elements])
    return lattice.to_cart(frac), np.tile(one_cell, len(shifts))
