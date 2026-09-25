"""
xtal.analysis.voids
===================
Which of the space a probe fits into it can reach from outside.

The distance grid (:mod:`xtal.analysis.grid`) says where a probe's
centre can *sit*: everywhere the field is at least the probe radius.
It does not say where the probe can *go*.  A sealed cage is as roomy
as a channel and holds nothing a simulation or an isotherm will ever
put there, so Zeo++ splits every number into the part a probe can
reach (a **channel**, which runs through the crystal) and the part it
cannot (a **pocket**).  This module makes the same split on the grid.

**Two grid points are joined only if the probe can travel the straight
line between them.**  Joining face neighbours alone closes windows
that are open -- HKUST-1 came out with 104 false pockets, UiO-66 with
no channel at all.  Joining all 26 neighbours on the strength of the
endpoints alone steps diagonally past atoms: N2 walked through
ZIF-8's 3.27 A windows, which it needs 3.72 A to pass.  So the field
is also asked at the segment's middle.  With both ends and the middle
clear, each half is a chord of at most half a grid step, and a chord
``c`` long dips into a sphere of radius ``R`` by at most ``c^2 / 8R``
-- 0.005 A for a 0.35 A half-step and the smallest expanded sphere
there is, which is well inside what the grid can resolve anyway.  Only
segments whose ends are close to an atom are asked (the field changes
by at most 1 A per A, being a distance), and the answer does not
depend on the probe, so it is asked once for both passes below.
Asking the atoms along the whole segment gave the same split on every
sample and took MFU-4l 4.5 s against 0.5.

**A channel is a component that meets its own periodic image.**  The
grid is labelled without wrapping, then the links across the cell's
faces join the labels in a union-find that carries each label's cell
offset.  Two paths to the same label with different offsets are a
path from a point to its own image one cell over -- that is what
percolating means, and it is Zeo++'s ``CHANNEL::findChannels`` test.

**A window the grid cannot see is flagged, not guessed.**  Where a
window is wider than the probe by less than a grid step, whether any
grid point falls inside the gap is luck: UiO-66's windows clear N2 by
0.045 A on the radius, and the answer flips between a 0.4 A and a
0.3 A grid.  So the split is made again with the probe half a grid
step smaller, and if any pocket then opens, :attr:`Voids.borderline`
says so and the report says to settle it with Zeo++'s pore
diameters, which has the exact decomposition.

Qt-free and VTK-free, like everything in :mod:`xtal.analysis`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from xtal.analysis import grid as grids
from xtal.core import p1


@dataclass(frozen=True)
class Voids:
    """The reachable and the sealed space of one grid, at one probe."""

    channels: np.ndarray        # (na, nb, nc) bool: reachable
    pockets: np.ndarray         # (na, nb, nc) bool: sealed
    n_channels: int
    n_pockets: int
    probe: float
    #: A pocket opens when the probe is half a grid step smaller: a
    #: window within the grid's resolution of the probe's size.
    borderline: bool = False

    def summary(self) -> str:
        def count(n, what):
            return f"{n} {what}{'' if n == 1 else 's'}"
        return (f"{count(self.n_channels, 'channel')}, "
                f"{count(self.n_pockets, 'pocket')}")


def classify(structure, field: np.ndarray, radius_of,
             probe: float) -> Voids:
    """Channels and pockets of ``field`` for a probe of ``probe``.

    ``field`` is :func:`xtal.analysis.grid.distance_grid` of
    ``structure`` with the same ``radius_of`` -- segment middles are
    measured against the atoms themselves, so a field built with
    another table would be split along windows of a different crystal.
    """
    lattice = structure.lattice
    shape = field.shape
    cell = p1.expand(structure)
    if not cell.n_atoms:
        everywhere = np.ones(shape, dtype=bool)
        return Voids(everywhere, ~everywhere, 1, 0, float(probe))
    centres, radii = grids.images(cell, lattice, radius_of)
    tree = cKDTree(centres)

    step = max(np.linalg.norm(lattice.to_cart(np.eye(3)), axis=1)
               / np.array(shape))
    looser = probe - step / 2
    links = _links(field, lattice, tree, radii, looser, probe)
    channels, pockets, n_channels, n_pockets = _split(field, links, probe)
    opened = _split(field, links, looser)[0]
    borderline = bool((pockets & opened).any()
                      or (n_channels == 0 and opened.any()))
    return Voids(channels, pockets, n_channels, n_pockets,
                 float(probe), borderline)


def _links(field, lattice, tree, radii, lowest, highest) -> list:
    """Every segment between neighbouring points the lowest probe could
    use, as ``(start, end, wrap, gate)`` flat-index arrays: the segment
    is open to any probe up to ``gate``, the field's least value at its
    two ends and its middle.  A middle is measured only where some
    probe up to ``highest`` needs it."""
    shape = np.array(field.shape)
    flat = field.ravel()
    start = np.flatnonzero(flat >= lowest)
    ijk = np.unravel_index(start, field.shape)
    strides = (field.shape[1] * field.shape[2], field.shape[2], 1)
    # Per axis and per step of -1, 0 or +1: where an index lands, and
    # which cell it lands in, as lookups rather than arithmetic on
    # every point thirteen times over.
    lands = [{d: (np.arange(n) + d) % n for d in (-1, 0, 1)}
             for n in field.shape]
    cells = [{d: (np.arange(n) + d) // n + 1 for d in (-1, 0, 1)}
             for n in field.shape]
    links = []
    for step in _HALF_NEIGHBOURS:
        end = sum(lands[axis][d][ijk[axis]] * strides[axis]
                  for axis, d in enumerate(step))
        usable = flat[end] >= lowest
        if not usable.any():
            continue
        a, b = start[usable], end[usable]
        wrap = sum(cells[axis][d][ijk[axis][usable]] * _WRAP_CODE[axis]
                   for axis, d in enumerate(step)).astype(np.int8)
        ends = flat[a], flat[b]
        gate = np.minimum(*ends)

        # The middle can only be inside a sphere if the two ends are
        # together within one segment length of it.
        length = float(np.linalg.norm(lattice.to_cart(step / shape)))
        ask = np.flatnonzero(ends[0] + ends[1] < 2 * highest + length)
        if len(ask):
            here = np.column_stack([ijk[axis][usable][ask]
                                    for axis in range(3)])
            middle = (here + step / 2) / shape
            gate[ask] = np.minimum(
                gate[ask],
                grids.surface_distance(tree, radii, lattice, middle))
        links.append((a, b, wrap, gate))
    return links


def _split(field, links, probe):
    """``(channels, pockets, n_channels, n_pockets)`` at ``probe``."""
    flat = field.ravel()
    open_ = flat >= probe
    count = int(open_.sum())
    if not count:
        nothing = np.zeros(field.shape, dtype=bool)
        return nothing, nothing, 0, 0
    node = np.full(len(flat), -1, dtype=np.int64)
    node[open_] = np.arange(count)

    inside_a, inside_b, across = [], [], []
    for a, b, wrap, gate in links:
        keep = gate >= probe
        a, b, wrap = node[a[keep]], node[b[keep]], wrap[keep]
        same = wrap == _NO_WRAP
        inside_a.append(a[same])
        inside_b.append(b[same])
        across.append((a[~same], b[~same], wrap[~same]))
    a = np.concatenate(inside_a)
    b = np.concatenate(inside_b)
    graph = coo_matrix((np.ones(len(a), dtype=np.int8), (a, b)),
                       shape=(count, count))
    n_labels, label = connected_components(graph, directed=False)
    offsets = _percolating(n_labels, label, across)

    root = np.array([offsets.find(i)[0] for i in range(n_labels)])
    in_channel = np.isin(root, list(offsets.through))[label]
    channels = np.zeros(len(flat), dtype=bool)
    pockets = np.zeros(len(flat), dtype=bool)
    channels[open_] = in_channel
    pockets[open_] = ~in_channel
    n_channels = len(offsets.through)
    n_pockets = len(np.unique(root)) - n_channels
    return (channels.reshape(field.shape), pockets.reshape(field.shape),
            n_channels, n_pockets)


class _Offsets:
    """Union-find over labels, carrying each label's cell offset from
    its root; a label joined to itself at a non-zero offset percolates.
    """

    def __init__(self, n):
        self.parent = list(range(n))
        self.offset = np.zeros((n, 3), dtype=np.int64)
        self.through: set[int] = set()

    def find(self, x):
        path = []
        while self.parent[x] != x:
            path.append(x)
            x = self.parent[x]
        # Compress, accumulating offsets from the far end inwards.
        total = np.zeros(3, dtype=np.int64)
        for y in reversed(path):
            total = total + self.offset[y]
            self.offset[y] = total
            self.parent[y] = x
        return x, (self.offset[path[0]].copy() if path
                   else np.zeros(3, dtype=np.int64))

    def join(self, a, b, shift):
        """``b``'s copy ``shift`` cells over is linked to ``a``."""
        ra, oa = self.find(a)
        rb, ob = self.find(b)
        if ra == rb:
            if np.any(oa + shift - ob):
                self.through.add(ra)
            return
        self.parent[rb] = ra
        self.offset[rb] = oa + shift - ob
        if rb in self.through:
            self.through.discard(rb)
            self.through.add(ra)


def _percolating(n_labels, label, across) -> _Offsets:
    found = _Offsets(n_labels)
    a = label[np.concatenate([x[0] for x in across])]
    b = label[np.concatenate([x[1] for x in across])]
    wrap = np.concatenate([x[2] for x in across]).astype(np.int64)
    # One join per distinct (label, label, wrap): the faces carry
    # thousands of links and a handful of distinct ones.
    key = np.unique((a * n_labels + b) * 27 + wrap)
    for pair, code in zip(key // 27, key % 27, strict=True):
        la, lb = divmod(int(pair), n_labels)
        found.join(la, lb, _SHIFTS[code])
    found.through = {found.find(r)[0] for r in found.through}
    return found


#: The thirteen neighbours on one side of a grid point: all 26 joined
#: once each.
_HALF_NEIGHBOURS = [np.array(d) for d in
                    ((i, j, k) for i in (-1, 0, 1) for j in (-1, 0, 1)
                     for k in (-1, 0, 1))
                    if d > (0, 0, 0)]

#: A cell shift of -1, 0 or +1 along each axis as one number, 0-26.
_WRAP_CODE = np.array([9, 3, 1])
_NO_WRAP = 13
_SHIFTS = np.array([(i, j, k) for i in (-1, 0, 1) for j in (-1, 0, 1)
                    for k in (-1, 0, 1)], dtype=np.int64)
