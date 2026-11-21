"""
xtal.printing.check
===================
Whether a triangle mesh is a solid a slicer will take: what the
slicers' own repair dialogs count, counted first.

A body is printable when every edge is used by exactly two triangles
and in opposite directions (closed, and wound consistently), no
triangle has zero area, and the volume it encloses is positive (wound
outward).  The run refuses to write a body that fails, so nothing a
slicer would have to repair ever leaves the application.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Report:
    triangles: int
    open_edges: int          # used once, or twice the same way
    crowded_edges: int       # used by more than two triangles
    degenerate: int
    volume: float

    @property
    def ok(self) -> bool:
        return (self.open_edges == 0 and self.crowded_edges == 0
                and self.degenerate == 0 and self.volume > 0)

    def says(self) -> str:
        if self.ok:
            return "closed"
        parts = []
        if self.open_edges:
            parts.append(f"{self.open_edges} open edges")
        if self.crowded_edges:
            parts.append(f"{self.crowded_edges} edges shared by more "
                         f"than two triangles")
        if self.degenerate:
            parts.append(f"{self.degenerate} zero-area triangles")
        if self.volume <= 0:
            parts.append("wound inside out")
        return ", ".join(parts)


def volume(vertices, triangles) -> float:
    """The signed volume enclosed, by the divergence theorem."""
    if not len(triangles):
        return 0.0
    v = np.asarray(vertices, float)[np.asarray(triangles)]
    return float(np.einsum("ij,ij->i", v[:, 0],
                           np.cross(v[:, 1], v[:, 2])).sum() / 6)


def report(vertices, triangles) -> Report:
    triangles = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
    vertices = np.asarray(vertices, float)
    if not len(triangles):
        return Report(0, 0, 0, 0, 0.0)
    directed = np.concatenate([triangles[:, [0, 1]],
                               triangles[:, [1, 2]],
                               triangles[:, [2, 0]]])
    undirected = np.sort(directed, axis=1)
    pairs, uses = np.unique(undirected, axis=0, return_counts=True)
    crowded = int(np.count_nonzero(uses > 2))
    open_ = int(np.count_nonzero(uses == 1))
    # Twice, but the same way round: the two triangles disagree about
    # which side is out.
    _same, same_uses = np.unique(directed, axis=0, return_counts=True)
    open_ += int(np.count_nonzero(same_uses > 1))
    v = vertices[triangles]
    area = np.linalg.norm(np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0]),
                          axis=1) / 2
    degenerate = int(np.count_nonzero(area < 1e-12)
                     + np.count_nonzero(
                         (triangles[:, 0] == triangles[:, 1])
                         | (triangles[:, 1] == triangles[:, 2])
                         | (triangles[:, 0] == triangles[:, 2])))
    del pairs
    return Report(len(triangles), open_, crowded, degenerate,
                  volume(vertices, triangles))
