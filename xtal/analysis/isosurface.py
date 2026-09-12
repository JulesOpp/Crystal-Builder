"""
xtal.analysis.isosurface
========================
A scalar grid to a triangle mesh, periodically.

One function: :func:`isosurface` takes the field
:mod:`xtal.analysis.grid` samples, a level, and the lattice it was
sampled in, and returns points and triangles in fractional
coordinates.  What that draws for a porosity run is the accessible
surface -- the boundary of everywhere a probe of that radius can put
its centre.

**Marching tetrahedra, not marching cubes**, and the reason is not
performance.  A cube has 256 sign patterns and fourteen of them are
*ambiguous*: the same eight signs describe two different surfaces, and
choosing wrong leaves a hole.  Every published fix is a second table.
A tetrahedron has sixteen patterns, three of them up to symmetry, and
none is ambiguous -- so a cube split into six tetrahedra gives a
watertight surface out of thirty lines and a table nobody has to
trust.  It costs about twice the triangles, which for a pore surface
nobody is going to 3D print is not a cost.

**And periodic, which is most of the work.**  The grid wraps: index
``na`` is index ``0`` of the next cell.  A surface marched over the
interior only would be a box with six open faces, and one closed by
padding the array would be a box with six *flat* faces -- a cavity
sliced off square at the cell wall rather than continuing into the
next one.  So the corner lookup wraps and the far corners' fractional
coordinates carry the ``+1`` that wrapping cost them; a triangle that
crosses a face comes out sticking a little way outside the cell, which
is exactly where it belongs and exactly what a half bond does.
"""

from __future__ import annotations

import numpy as np

#: A cube split into six tetrahedra about its main diagonal 0-7.  The
#: standard Kuhn decomposition: every tetrahedron has that diagonal,
#: they tile the cube exactly, and neighbouring cubes agree on the
#: faces they share -- which is what makes the whole surface
#: watertight rather than each cube's piece watertight on its own.
TETRAHEDRA = ((0, 1, 3, 7), (0, 1, 5, 7), (0, 2, 3, 7),
              (0, 2, 6, 7), (0, 4, 5, 7), (0, 4, 6, 7))

#: Corner c of a cube, as the (di, dj, dk) offset its bits name.
CORNERS = np.array([[(c >> 2) & 1, (c >> 1) & 1, c & 1]
                    for c in range(8)], dtype=int)

#: The six edges of a tetrahedron, as pairs of its own corners.
_EDGES = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))

#: Which edges a tetrahedron's surface crosses, per sign pattern.
#: Bit ``i`` of the pattern is "corner ``i`` is inside".  One triangle
#: when a single corner is on its own, two when they split two and
#: two, and nothing when they are all on one side.
#:
#: A pattern and its complement cut the same edges and get the same
#: row -- which side of the sheet is "in" changes nothing about where
#: the sheet is.  Which way each triangle *faces* is not settled here
#: at all: it is fixed afterwards against the inside corners, because
#: a table that has to be wound correctly in fourteen places is a
#: table with a flipped triangle in it.
_CASES = {
    0b0001: ((0, 1, 2),), 0b1110: ((0, 1, 2),),
    0b0010: ((0, 3, 4),), 0b1101: ((0, 3, 4),),
    0b0100: ((1, 3, 5),), 0b1011: ((1, 3, 5),),
    0b1000: ((2, 4, 5),), 0b0111: ((2, 4, 5),),
    0b0011: ((1, 2, 4), (1, 4, 3)),
    0b1100: ((1, 2, 4), (1, 4, 3)),
    0b0101: ((0, 2, 5), (0, 5, 3)),
    0b1010: ((0, 2, 5), (0, 5, 3)),
    0b1001: ((0, 1, 5), (0, 5, 4)),
    0b0110: ((0, 1, 5), (0, 5, 4)),
}


def isosurface(grid, lattice, level: float) -> tuple:
    """``(points, triangles)`` of the ``level`` surface of ``grid``.

    ``points`` are ``(P, 3)`` **fractional** coordinates -- a little
    outside ``[0, 1)`` where a triangle crosses a cell face -- and
    ``triangles`` are ``(T, 3)`` indices into them.  ``lattice`` is
    taken for its shape only; nothing here works in Angstrom, because
    a surface stored in fractions is one the display range can repeat.

    Vertices are shared between the triangles of one tetrahedron and
    not between tetrahedra: welding them would cost a hash of every
    point to save a third of the memory of a mesh that is already
    thrown away on the next run.
    """
    grid = np.asarray(grid, float)
    if grid.ndim != 3 or min(grid.shape) < 2:
        return _nothing()
    inside = grid >= level
    if inside.all() or not inside.any():
        # No surface: the level is outside the range of the field.
        # Not an error -- a probe too big for any pore in a dense
        # solid is a real answer and it is "nothing to draw".
        return _nothing()

    corners, values = _corner_arrays(grid)
    points, triangles = [], []
    base = 0
    for tetra in TETRAHEDRA:
        got = _march(tetra, corners, values, level)
        if got is None:
            continue
        vertices, faces = got
        points.append(vertices)
        triangles.append(faces + base)
        base += len(vertices)
    if not points:
        return _nothing()
    return (np.vstack(points).astype(np.float32),
            np.vstack(triangles).astype(int))


def _nothing():
    return np.zeros((0, 3), np.float32), np.zeros((0, 3), int)


def _corner_arrays(grid):
    """``(corner_frac, corner_value)`` for every cell of the grid.

    ``corner_frac`` is ``(8, N, 3)`` fractional coordinates and
    ``corner_value`` is ``(8, N)``.  The coordinates are *unwrapped* --
    the corner at index ``na`` keeps its fractional 1.0 rather than
    coming back as 0.0 -- while the values are read with the wrap, so a
    cell straddling a face has both.
    """
    shape = np.array(grid.shape)
    axes = [np.arange(n) for n in shape]
    i, j, k = np.meshgrid(*axes, indexing="ij")
    origin = np.stack([i.ravel(), j.ravel(), k.ravel()], axis=1)

    frac, value = [], []
    for offset in CORNERS:
        index = origin + offset
        frac.append(index / shape)
        wrapped = index % shape
        value.append(grid[wrapped[:, 0], wrapped[:, 1], wrapped[:, 2]])
    return np.stack(frac), np.stack(value)


def _march(tetra, corners, values, level: float):
    """The triangles of one of the six tetrahedra, over every cell.

    Vectorised over cells rather than looped: a 78-cubed grid is
    475 000 cells and six of these, and a Python loop over them takes
    minutes where this takes a second.
    """
    a = np.stack([values[c] for c in tetra])            # (4, N)
    signs = (a >= level)
    pattern = (signs[0].astype(int) | signs[1].astype(int) << 1
               | signs[2].astype(int) << 2 | signs[3].astype(int) << 3)

    points, faces = [], []
    base = 0
    for code, triangles in _CASES.items():
        picked = np.nonzero(pattern == code)[0]
        if not len(picked):
            continue
        crossings = _crossings(tetra, corners, values, level, picked)
        middle = _inside_centre(tetra, corners, code, picked)
        offsets = base + np.arange(len(picked)) * 6
        for triangle in triangles:
            rows = np.stack([offsets + edge for edge in triangle],
                            axis=1)
            faces.append(_facing_out(
                rows, crossings[:, triangle, :], middle))
        points.append(crossings.reshape(-1, 3))
        base += len(picked) * 6
    if not points:
        return None
    return np.vstack(points), np.vstack(faces)


def _inside_centre(tetra, corners, code: int, picked):
    """The middle of the corners this pattern calls inside.

    Only ever used as a direction to face *away* from, so which of a
    pattern and its complement is "inside" does not matter -- both
    give the same sheet, and both give it a consistent orientation.
    """
    chosen = [tetra[c] for c in range(4) if code >> c & 1]
    return np.mean([corners[c][picked] for c in chosen], axis=0)


def _facing_out(rows, vertices, middle):
    """Wind each triangle so its normal points away from ``middle``.

    Against a reference point rather than out of the table, because
    the table is indexed by a sign pattern and the same row serves a
    pattern and its complement: no fixed winding can be right for
    both.  A surface wound half one way and half the other lights as
    a patchwork of bright and black facets, which is what this is for
    -- the geometry is identical either way.
    """
    normal = np.cross(vertices[:, 1] - vertices[:, 0],
                      vertices[:, 2] - vertices[:, 0])
    outward = np.einsum(
        "ij,ij->i", normal, vertices.mean(axis=1) - middle)
    flip = outward < 0
    rows = rows.copy()
    rows[flip] = rows[flip][:, [0, 2, 1]]
    return rows


def _crossings(tetra, corners, values, level: float, picked):
    """``(len(picked), 6, 3)``: where the surface cuts each edge.

    All six edges of the tetrahedron for every chosen cell, whether or
    not the surface crosses them.  Wasteful by a factor of two and
    worth it: the alternative is a per-case gather, and the vertices
    the cases never index cost one lerp each and are never drawn.
    """
    out = np.empty((len(picked), 6, 3), float)
    for slot, (u, v) in enumerate(_EDGES):
        cu, cv = tetra[u], tetra[v]
        fu = corners[cu][picked]
        fv = corners[cv][picked]
        au = values[cu][picked]
        av = values[cv][picked]
        # A zero denominator means both ends sit exactly on the level,
        # which no sign pattern in _CASES can reach -- but a grid of
        # constant value would divide by it on the way to producing
        # nothing, so the midpoint stands in.
        span = av - au
        t = np.where(np.abs(span) < 1e-12, 0.5,
                     (level - au) / np.where(span == 0, 1.0, span))
        out[:, slot, :] = fu + t[:, None] * (fv - fu)
    return out
