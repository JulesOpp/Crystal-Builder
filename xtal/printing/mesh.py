"""
xtal.printing.mesh
==================
Two closed bodies, colour 1 and colour 2, marched from one labelled
grid so that they meet without overlapping and without a gap.

**Why one grid.**  A slicer takes a two-colour model as two parts and
needs each part to be a closed solid and the two not to fight over the
same plastic.  Meshing each colour on its own -- or one remesh and a
boolean, which is what Blender would offer -- gives two surfaces that
were never told about each other: where they should meet they overlap
by a fraction of a voxel or leave a crack, and that is the
"non-manifold" or "overlapping volumes" complaint.  Here every grid
point is *labelled* -- outside, colour 1 or colour 2 (the nearer
body, :class:`~xtal.printing.field.Block.labels`) -- and each body is
the boundary of its own label.  Where 1 meets 2 the same triangles
are written into both bodies, wound oppositely, so the interface is
one surface with two names.

**Multi-material marching tetrahedra.**  Each cube is the Kuhn six
tetrahedra of :mod:`xtal.analysis.isosurface`.  A vertex goes on every
tetrahedron edge whose ends differ: where the union field crosses zero
if one end is outside, where ``f1 - f2`` does if the ends are the two
colours.  A tetrahedron with two labels gets the ordinary marching
triangles.  One with three -- only where the interface reaches the
outside, a ring round every colour boundary -- has two corners of one
label and one each of the others; a vertex is added at the middle of
each of its two three-label faces and at its own middle, and the three
boundaries are the polygons through them (:func:`_three`).  A face
point depends only on the face, so the two tetrahedra either side of
it agree, and the bodies stay closed through the ring.

**Vertices are welded by what they are, never by where.**  An edge
vertex is keyed by its edge (lower grid point and direction), a face
vertex by its face (lower point and the two steps to the others) and
a middle by its tetrahedron, so a vertex two blocks or two bodies
share is one vertex by construction and nothing is compared to a
tolerance.  A vertex is never put closer than :data:`CLAMP` of an
edge to a grid point, so no triangle is degenerate.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from xtal.analysis.isosurface import _CASES, _EDGES, CORNERS, TETRAHEDRA
from xtal.printing import field as fields

#: The nearest a vertex comes to either end of its edge, as a fraction
#: of the edge.
CLAMP = 1e-3

#: Kinds of vertex, the low two bits of a key.
_ON_EDGE, _ON_FACE, _MIDDLE = 0, 1, 2


def _code(offset) -> np.ndarray:
    """``(di, dj, dk)`` in {0, 1} as one number, 1 to 7."""
    offset = np.asarray(offset)
    return offset[..., 0] * 4 + offset[..., 1] * 2 + offset[..., 2]


@dataclass(frozen=True)
class TwoBodies:
    """``vertices`` (V, 3) in Angstrom; ``bodies[0]`` and ``bodies[1]``
    triangles ``(T, 3)`` into them, wound outward, for colours 1 and
    2.  Interface vertices are shared by both bodies."""

    vertices: np.ndarray
    bodies: tuple

    def body(self, colour: int) -> tuple[np.ndarray, np.ndarray]:
        """One body on its own: ``(vertices, triangles)`` with only the
        vertices it uses."""
        triangles = self.bodies[colour - 1]
        if not len(triangles):
            return np.zeros((0, 3)), np.zeros((0, 3), dtype=int)
        used, inverse = np.unique(triangles, return_inverse=True)
        return self.vertices[used], inverse.reshape(-1, 3)


def two_bodies(primitives, voxel: float) -> TwoBodies:
    grid = fields.Grid.around(primitives, voxel)
    keys, positions = [], []
    bodies = ([], [])
    for block in fields.blocks(primitives, grid):
        _march_block(grid, block, keys, positions, bodies)
    return _weld(keys, positions, bodies)


def _weld(keys, positions, bodies) -> TwoBodies:
    if not keys:
        empty = np.zeros((0, 3), dtype=int)
        return TwoBodies(np.zeros((0, 3)), (empty, empty))
    keys = np.concatenate(keys)
    positions = np.concatenate(positions)
    unique, first = np.unique(keys, return_index=True)
    vertices = positions[first]
    out = []
    for body in bodies:
        if not body:
            out.append(np.zeros((0, 3), dtype=int))
            continue
        tri_keys = np.concatenate(body)
        index = np.searchsorted(unique, tri_keys.ravel())
        assert np.array_equal(unique[index], tri_keys.ravel())
        out.append(index.reshape(-1, 3))
    return TwoBodies(vertices, tuple(out))


def _march_block(grid, block, keys, positions, bodies) -> None:
    labels = block.labels
    cells = np.asarray(labels.shape) - 1
    if np.any(cells < 1):
        return
    # Cells whose corners are not all one label.
    lo = np.full(tuple(cells), 3, dtype=np.int8)
    hi = np.full(tuple(cells), -1, dtype=np.int8)
    for c in CORNERS:
        view = labels[c[0]:c[0] + cells[0], c[1]:c[1] + cells[1],
                      c[2]:c[2] + cells[2]]
        np.minimum(lo, view, out=lo)
        np.maximum(hi, view, out=hi)
    mixed = np.argwhere(lo != hi)
    if not len(mixed):
        return
    start = np.asarray(block.start)
    offsets = CORNERS[np.asarray(TETRAHEDRA)]               # (6, 4, 3)
    local = (mixed[:, None, None, :]
             + offsets[None, :, :, :]).reshape(-1, 4, 3)    # (6n, 4, 3)
    index = tuple(local[..., d] for d in range(3))
    ijk = local + start
    cell = grid.point_id(*(mixed + start).T)
    corners = _Corners(
        labels=labels[index].astype(np.int8),
        union=block.union[index], gap=(block.f1 - block.f2)[index],
        xyz=grid.origin + grid.voxel * ijk.astype(float),
        pid=grid.point_id(ijk[..., 0], ijk[..., 1], ijk[..., 2]),
        offsets=np.broadcast_to(offsets, (len(mixed), 6, 4, 3))
        .reshape(-1, 4, 3),
        tetra=(cell[:, None] * 6 + np.arange(6)).ravel())
    count = _distinct(corners.labels)
    out = _Triangles()
    two = np.flatnonzero(count == 2)
    if len(two):
        _two(corners.subset(two), out)
    three = np.flatnonzero(count == 3)
    if len(three):
        _three(corners.subset(three), out)
    out.emit(keys, positions, bodies)


def _distinct(labels) -> np.ndarray:
    ordered = np.sort(labels, axis=1)
    return 1 + np.count_nonzero(np.diff(ordered, axis=1), axis=1)


class _Corners:
    """The four corners of ``n`` tetrahedra: their labels, both
    fields, positions, grid point ids and offsets in their cube, and
    an id for each tetrahedron."""

    def __init__(self, labels, union, gap, xyz, pid, offsets, tetra):
        self.labels, self.union, self.gap = labels, union, gap
        self.xyz, self.pid, self.offsets = xyz, pid, offsets
        self.tetra = tetra

    def subset(self, rows) -> _Corners:
        return _Corners(self.labels[rows], self.union[rows],
                        self.gap[rows], self.xyz[rows], self.pid[rows],
                        self.offsets[rows], self.tetra[rows])

    def __len__(self) -> int:
        return len(self.labels)

    def edges(self):
        """``(keys, positions, ideal)``, ``(n, 6)``, ``(n, 6, 3)`` and
        ``(n, 6, 3)``: the vertex on each edge of every tetrahedron --
        meaningful only where its ends differ.  ``ideal`` is the edge's
        middle, which is where the winding is decided
        (:meth:`_Triangles.emit`)."""
        u, v = np.asarray(_EDGES).T          # u < v: u is the lower point
        lu, lv = self.labels[:, u], self.labels[:, v]
        across = (lu == 0) | (lv == 0)
        fu = np.where(across, self.union[:, u], self.gap[:, u])
        fv = np.where(across, self.union[:, v], self.gap[:, v])
        with np.errstate(divide="ignore", invalid="ignore"):
            t = fu / (fu - fv)
        t = np.clip(np.nan_to_num(t, nan=0.5), CLAMP, 1 - CLAMP)
        a, b = self.xyz[:, u], self.xyz[:, v]
        xyz = a + t[..., None] * (b - a)
        step = _code(self.offsets[:, v] - self.offsets[:, u])
        keys = (self.pid[:, u] * 8 + step) * 4 + _ON_EDGE
        return keys, xyz, (a + b) / 2


class _Triangles:
    """Triangles gathered over a block, emitted at once: keys,
    positions and ideal positions ``(T, 3[, 3])``, the corners of the
    tetrahedron each came from, and the two labels it separates."""

    def __init__(self):
        self.parts = []

    def add(self, k, p, ideal, labels, xyz, top, bottom) -> None:
        self.parts.append((k, p, ideal, labels, xyz, top, bottom))

    def emit(self, keys, positions, bodies) -> None:
        """Into each coloured body, wound away from that body's
        corners.

        The winding is read off ``ideal`` -- every edge vertex at its
        edge's middle -- and not off the positions.  It is the same
        surface combinatorially, so the windings agree across every
        edge either way; but a vertex placed a thousandth of an edge
        from a corner makes a sliver whose normal points anywhere, and
        one sliver wound the wrong way is an edge used twice in one
        direction."""
        if not self.parts:
            return
        k, p, ideal, labels, xyz, top, bottom = (
            np.concatenate(column) for column in zip(*self.parts,
                                                     strict=True))
        keys.append(k.ravel())
        positions.append(p.reshape(-1, 3))
        normal = np.cross(ideal[:, 1] - ideal[:, 0],
                          ideal[:, 2] - ideal[:, 0])
        middle = ideal.mean(axis=1)
        for label in (1, 2):
            mine = (top == label) | (bottom == label)
            if not mine.any():
                continue
            corners = labels[mine] == label
            centre = ((xyz[mine] * corners[..., None]).sum(axis=1)
                      / corners.sum(axis=1)[:, None])
            outward = np.einsum("ij,ij->i", normal[mine],
                                middle[mine] - centre)
            tri = k[mine]
            tri = np.where((outward < 0)[:, None], tri[:, ::-1], tri)
            bodies[label - 1].append(tri)


def _two(c: _Corners, out: _Triangles) -> None:
    """Tetrahedra with two labels: the ordinary marching triangles."""
    top = c.labels.max(axis=1)
    bottom = c.labels.min(axis=1)
    inside = c.labels == top[:, None]
    pattern = (inside * (1 << np.arange(4))).sum(axis=1)
    keys, xyz, ideal = c.edges()
    for code, rows in _CASES.items():
        picked = np.flatnonzero(pattern == code)
        if not len(picked):
            continue
        for row in rows:
            row = list(row)
            out.add(keys[picked][:, row], xyz[picked][:, row],
                    ideal[picked][:, row], c.labels[picked],
                    c.xyz[picked], top[picked], bottom[picked])


#: Edge number of corners (u, v), either way round.
_EDGE_INDEX = np.full((4, 4), -1, dtype=int)
for _n, (_u, _v) in enumerate(_EDGES):
    _EDGE_INDEX[_u, _v] = _EDGE_INDEX[_v, _u] = _n


def _three(c: _Corners, out: _Triangles) -> None:
    """Tetrahedra with three labels, two corners sharing one.

    Corners P, Q share label x; R is y, S is z.  Faces PRS and QRS
    carry all three labels and get a middle vertex each (F_P and F_Q,
    named for the corner of x each keeps); the tetrahedron gets its
    own, M.  The three boundaries are the loops

    - x|y: E_PR, E_QR, F_Q, M, F_P
    - x|z: E_PS, E_QS, F_Q, M, F_P
    - y|z: E_RS, F_Q, M, F_P

    each fanned from M: eight triangles.
    """
    n = len(c)
    rows = np.arange(n)
    lab = c.labels
    u, v = np.asarray(_EDGES).T
    same = np.flatnonzero((lab[:, u] == lab[:, v]).ravel()) % 6
    P, Q = u[same], v[same]
    others = np.sort(np.where(
        (np.arange(4)[None, :] == P[:, None])
        | (np.arange(4)[None, :] == Q[:, None]), 9, np.arange(4)),
        axis=1)[:, :2]
    R, S = others[:, 0], others[:, 1]
    x = lab[rows, P]

    keys, xyz, ideal = c.edges()

    def edge(a, b):
        e = _EDGE_INDEX[a, b]
        return keys[rows, e], xyz[rows, e], ideal[rows, e]

    def face(keep):
        three = np.sort(np.stack([keep, R, S], axis=1), axis=1)
        c0, c1, c2 = three.T
        k = ((c.pid[rows, c0] * 8
              + _code(c.offsets[rows, c1] - c.offsets[rows, c0])) * 8
             + _code(c.offsets[rows, c2] - c.offsets[rows, c0]))
        sides = [edge(c0, c1), edge(c0, c2), edge(c1, c2)]
        return (k * 4 + _ON_FACE,
                np.mean([s[1] for s in sides], axis=0),
                np.mean([s[2] for s in sides], axis=0))

    e_pr, e_qr, e_ps, e_qs, e_rs = (edge(P, R), edge(Q, R), edge(P, S),
                                    edge(Q, S), edge(R, S))
    around = (e_pr, e_qr, e_ps, e_qs, e_rs)
    m = (c.tetra * 4 + _MIDDLE,
         np.mean([a[1] for a in around], axis=0),
         np.mean([a[2] for a in around], axis=0))
    f_p, f_q = face(P), face(Q)
    y, z = lab[rows, R], lab[rows, S]
    fans = ((x, y, (f_p, e_pr, e_qr, f_q)),
            (x, z, (f_p, e_ps, e_qs, f_q)),
            (y, z, (f_p, e_rs, f_q)))
    for a, b, ring in fans:
        for first, second in zip(ring[:-1], ring[1:], strict=True):
            tri = (m, first, second)
            out.add(*(np.stack([t[part] for t in tri], axis=1)
                      for part in range(3)),
                    lab, c.xyz, np.maximum(a, b), np.minimum(a, b))
