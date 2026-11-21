"""
xtal.printing.field
===================
The balls and sticks as two signed-distance fields on one grid: ``f1``
the distance to the nearest colour-1 primitive, ``f2`` to the nearest
colour-2 one, negative inside.

**Sparse, a block at a time.**  A framework is mostly pore: MFU-4l's
cut is 40 million grid points at 0.1 A and a few per cent of them are
anywhere near an atom.  The grid is split into blocks of
:data:`BLOCK` cells, and a block exists only where some primitive's
box reaches it; every other point is outside.

**And every point gets the same value whichever block computes it.**
Two neighbouring blocks share a face of points, and a mesh vertex on
an edge there is placed from those values -- if the two blocks had
summed different primitives the vertex would be in two places and the
mesh would crack.  So a value is clamped to :func:`ceiling` (two grid
steps), and a primitive is handed to every block that has a point
closer to it than that: past the ceiling every block agrees on the
ceiling, and short of it every block has the primitive.  Nothing that
places a vertex ever reads a clamped value, because the field moves
by at most one step along an edge and a vertex sits on an edge with
one end inside.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from xtal.printing.primitives import BALL, Primitives

#: Cells along each side of a block.
BLOCK = 16


def ceiling(voxel: float) -> float:
    return 2.0 * voxel


@dataclass(frozen=True)
class Grid:
    """Points ``origin + voxel * (i, j, k)`` for ``0 <= i < shape``."""

    origin: np.ndarray
    voxel: float
    shape: tuple

    @classmethod
    def around(cls, primitives: Primitives, voxel: float) -> Grid:
        lo, hi = primitives.bounds()
        margin = 2 * ceiling(voxel)
        origin = lo.min(axis=0) - margin
        extent = hi.max(axis=0) + margin - origin
        shape = tuple(int(n) for n in np.ceil(extent / voxel) + 1)
        return cls(origin=origin, voxel=float(voxel), shape=shape)

    @property
    def blocks(self) -> tuple:
        """Blocks along each axis; block ``b`` holds cells ``b * BLOCK``
        up to the last cell, ``shape - 2``."""
        return tuple(-(-(n - 1) // BLOCK) for n in self.shape)

    def point_id(self, i, j, k):
        _ni, nj, nk = self.shape
        return (np.asarray(i, np.int64) * nj + j) * nk + k


@dataclass
class Block:
    """One block's points: ``start`` is the grid index of its first,
    and ``f1``, ``f2`` are ``(BLOCK + 1,) * 3`` arrays (fewer at the far
    edge of the grid)."""

    start: tuple
    f1: np.ndarray
    f2: np.ndarray

    @property
    def union(self) -> np.ndarray:
        return np.minimum(self.f1, self.f2)

    @property
    def labels(self) -> np.ndarray:
        """0 outside, else the colour of the nearer body: 1 wins a tie,
        which matches the sign of ``f1 - f2`` the interface is placed
        by."""
        out = np.where(self.f1 <= self.f2, 1, 2).astype(np.int8)
        out[self.union >= 0] = 0
        return out


def blocks(primitives: Primitives, grid: Grid):
    """Every block some primitive reaches, with its fields."""
    roof = ceiling(grid.voxel)
    lo, hi = primitives.bounds()
    first = np.ceil((lo - roof - grid.origin) / grid.voxel).astype(int)
    last = np.floor((hi + roof - grid.origin) / grid.voxel).astype(int)
    first = np.maximum(first, 0)
    last = np.minimum(last, np.asarray(grid.shape) - 1)
    nblocks = np.asarray(grid.blocks)

    touching: dict[tuple, list] = {}
    for p in range(len(primitives)):
        # Block b's points run b*BLOCK .. b*BLOCK + BLOCK.
        b_lo = np.maximum((first[p] - 1) // BLOCK, 0)
        b_hi = np.minimum(last[p] // BLOCK, nblocks - 1)
        for bi in range(b_lo[0], b_hi[0] + 1):
            for bj in range(b_lo[1], b_hi[1] + 1):
                for bk in range(b_lo[2], b_hi[2] + 1):
                    touching.setdefault((bi, bj, bk), []).append(p)

    for key in sorted(touching):
        yield _block(primitives, grid, key, touching[key], first, last,
                     roof)


def _block(primitives, grid, key, members, first, last, roof) -> Block:
    start = np.asarray(key) * BLOCK
    stop = np.minimum(start + BLOCK + 1, grid.shape)
    shape = tuple(stop - start)
    f = {1: np.full(shape, roof), 2: np.full(shape, roof)}
    for p in members:
        lo = np.maximum(first[p], start)
        hi = np.minimum(last[p] + 1, stop)
        if np.any(hi <= lo):
            continue
        axes = [grid.origin[d] + grid.voxel * np.arange(lo[d], hi[d])
                for d in range(3)]
        x, y, z = np.meshgrid(*axes, indexing="ij")
        points = np.stack((x, y, z), axis=-1)
        d = _distance(primitives, p, points)
        window = tuple(slice(lo[n] - start[n], hi[n] - start[n])
                       for n in range(3))
        target = f[int(primitives.colour[p])]
        np.minimum(target[window], d, out=target[window])
    return Block(start=tuple(int(s) for s in start), f1=f[1], f2=f[2])


def _distance(primitives: Primitives, p: int, points) -> np.ndarray:
    a = primitives.a[p]
    r = primitives.radius[p]
    if primitives.kind[p] == BALL:
        return np.linalg.norm(points - a, axis=-1) - r
    return capped_cylinder(points, a, primitives.b[p], r)


def capped_cylinder(points, a, b, r) -> np.ndarray:
    """Signed distance to the flat-ended cylinder of radius ``r`` from
    ``a`` to ``b`` -- exact outside and in."""
    axis = b - a
    length = float(np.linalg.norm(axis))
    u = axis / length
    rel = points - a
    along = rel @ u
    radial = np.linalg.norm(rel - along[..., None] * u, axis=-1) - r
    end = np.abs(along - length / 2) - length / 2
    outside = np.hypot(np.maximum(radial, 0), np.maximum(end, 0))
    return outside + np.minimum(np.maximum(radial, end), 0)
