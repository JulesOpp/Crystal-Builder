"""
xtal.carbon.mesh
================
A triangle mesh on a periodic surface, and what is done to it before
it becomes carbon.

**A corner is a vertex and a lattice translation.**  The vertices are
kept wrapped into the cell, and each triangle says, per corner, which
image of its vertex it means (``shift``): a triangle across a cell face
has a corner at ``frac[v] + shift``.  An edge is then a pair of
vertices *and* the translation between them, which is what lets one
vertex be bonded to its own image in a cell smaller than a ring, and
what the dual carries into each bond's ``image``.  Only the
translations between the corners of one triangle mean anything; adding
the same vector to all three changes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components


@dataclass
class Mesh:
    """``frac`` (V, 3) wrapped vertices, ``tri`` (T, 3) and ``shift``
    (T, 3, 3) corners, in the lattice whose rows are ``matrix``."""

    matrix: np.ndarray
    frac: np.ndarray
    tri: np.ndarray
    shift: np.ndarray

    @property
    def n_vertices(self) -> int:
        return len(self.frac)

    @property
    def n_triangles(self) -> int:
        return len(self.tri)

    def corners(self) -> np.ndarray:
        """``(T, 3, 3)`` cartesian corners, each triangle in its own
        frame."""
        return (self.frac[self.tri] + self.shift) @ self.matrix

    def triangle_areas(self) -> np.ndarray:
        c = self.corners()
        return 0.5 * np.linalg.norm(
            np.cross(c[:, 1] - c[:, 0], c[:, 2] - c[:, 0]), axis=1)

    def area(self) -> float:
        return float(self.triangle_areas().sum())

    def normals(self) -> np.ndarray:
        """Unit normal per triangle, by its winding."""
        c = self.corners()
        n = np.cross(c[:, 1] - c[:, 0], c[:, 2] - c[:, 0])
        return n / np.maximum(np.linalg.norm(n, axis=1), 1e-12)[:, None]

    # -- edges -----------------------------------------------------------

    def half_edges(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """``(a, b, rel)``: every triangle's three sides in winding
        order, ``rel`` the translation from ``a``'s corner to ``b``'s.
        Side ``k`` of triangle ``t`` is row ``3 t + k``."""
        a = self.tri.reshape(-1)
        b = self.tri[:, [1, 2, 0]].reshape(-1)
        rel = (self.shift[:, [1, 2, 0]] - self.shift).reshape(-1, 3)
        return a, b, rel

    def edge_keys(self) -> np.ndarray:
        """``(3T, 5)``: each side as an undirected edge -- the smaller
        vertex first, and the translation from it to the other."""
        a, b, rel = self.half_edges()
        swap = (a > b) | ((a == b) & _negative(rel))
        lo = np.where(swap, b, a)
        hi = np.where(swap, a, b)
        rel = np.where(swap[:, None], -rel, rel)
        return np.column_stack([lo, hi, rel])

    def edges(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """``(keys, side_of_edge, counts)``: the distinct edges, which
        edge each side is, and how many sides each edge has."""
        keys, inverse, counts = np.unique(
            self.edge_keys(), axis=0, return_inverse=True,
            return_counts=True)
        return keys, inverse.reshape(-1), counts

    def is_closed(self) -> bool:
        """Every edge in exactly two triangles, wound opposite ways --
        a closed, oriented 2-manifold, as a sheet with no edge is."""
        _keys, _inverse, counts = self.edges()
        if not len(counts) or np.any(counts != 2):
            return False
        a, b, rel = self.half_edges()
        directed = np.column_stack([a, b, rel])
        return len(np.unique(directed, axis=0)) == len(directed)

    def euler(self) -> int:
        """V - E + F."""
        keys, _inverse, _counts = self.edges()
        used = np.unique(self.tri)
        return len(used) - len(keys) + self.n_triangles

    def valence(self) -> np.ndarray:
        """Distinct edges at each vertex: the size of the ring it
        becomes in the dual, where the surface is closed round it."""
        keys, _inverse, _counts = self.edges()
        out = np.zeros(self.n_vertices, int)
        np.add.at(out, keys[:, 0], 1)
        np.add.at(out, keys[:, 1], 1)
        return out

    def boundary_vertices(self) -> np.ndarray:
        """Vertices on an edge only one triangle has."""
        keys, _inverse, counts = self.edges()
        open_ = keys[counts == 1]
        mark = np.zeros(self.n_vertices, bool)
        mark[open_[:, 0]] = mark[open_[:, 1]] = True
        return mark

    def neighbours(self) -> tuple[np.ndarray, np.ndarray]:
        """``(pairs, shared)``: triangles that share an edge, and which
        edge -- the bonds of the dual."""
        _keys, inverse, counts = self.edges()
        order = np.argsort(inverse, kind="stable")
        sides = inverse[order]
        two = np.flatnonzero(counts[sides[:-1]] == 2)
        two = two[sides[two] == sides[two + 1]]
        first, second = order[two] // 3, order[two + 1] // 3
        return np.column_stack([first, second]), sides[two]

    # -- pieces ----------------------------------------------------------

    def components(self) -> np.ndarray:
        """Which piece each triangle is in, joined across shared
        edges."""
        pairs, _shared = self.neighbours()
        n = self.n_triangles
        graph = coo_matrix((np.ones(len(pairs)), (pairs[:, 0],
                                                  pairs[:, 1])),
                           shape=(n, n))
        return connected_components(graph, directed=False)[1]

    def periodicity(self) -> int:
        """In how many independent directions the mesh runs on through
        the cell faces: 3 for a sheet that percolates in every one, 0
        for a closed bubble.

        Each vertex is placed in an image as it is reached across an
        edge; reaching one already placed, in another image, is a loop
        that crosses the cell, and the rank of those loops is the
        answer.
        """
        a, b, rel = self.half_edges()
        n = self.n_vertices
        adjacency: list = [[] for _ in range(n)]
        for u, v, r in zip(a, b, rel, strict=True):
            adjacency[u].append((v, r))
            adjacency[v].append((u, -r))
        where: dict = {}
        loops = []
        for start in np.unique(self.tri):
            if start in where:
                continue
            where[start] = np.zeros(3, int)
            stack = [start]
            while stack:
                u = stack.pop()
                for v, r in adjacency[u]:
                    image = where[u] + r
                    if v not in where:
                        where[v] = image
                        stack.append(v)
                    elif np.any(image != where[v]):
                        loops.append(image - where[v])
                        if len(loops) > 64 and np.linalg.matrix_rank(
                                np.array(loops)) == 3:
                            return 3
        if not loops:
            return 0
        return int(np.linalg.matrix_rank(np.array(loops)))

    def subset(self, keep) -> Mesh:
        """The triangles ``keep`` picks, with the vertices they use."""
        tri = self.tri[keep]
        used, tri = np.unique(tri, return_inverse=True)
        return Mesh(self.matrix, self.frac[used],
                    tri.reshape(-1, 3), self.shift[keep])


def _negative(rel) -> np.ndarray:
    """Whether a translation is lexicographically below zero."""
    first = np.argmax(rel != 0, axis=1)
    value = rel[np.arange(len(rel)), first]
    return value < 0
