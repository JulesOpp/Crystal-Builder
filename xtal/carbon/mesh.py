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


def _cross3(u, v) -> np.ndarray:
    """``np.cross`` for one pair of 3-vectors, without its overhead."""
    return np.array([u[1] * v[2] - u[2] * v[1],
                     u[2] * v[0] - u[0] * v[2],
                     u[0] * v[1] - u[1] * v[0]])


def _unit(v) -> np.ndarray:
    return v / max(float(np.sqrt(v @ v)), 1e-12)


def _negative(rel) -> np.ndarray:
    """Whether a translation is lexicographically below zero."""
    first = np.argmax(rel != 0, axis=1)
    value = rel[np.arange(len(rel)), first]
    return value < 0


# ======================================================================
#  EDITING
# ======================================================================

class Editor:
    """A mesh that can be split, collapsed and flipped in place.

    Triangles are kept by id, with the set of triangles at each vertex,
    so an operation touches only the two triangles of an edge and the
    fans of its ends.  Every operation keeps the sheet a closed,
    oriented manifold and so keeps its Euler characteristic: the
    Gauss-Bonnet count of rings a remesh or a defect cannot change.
    """

    def __init__(self, mesh: Mesh):
        self.matrix = np.asarray(mesh.matrix, float)
        self.pos = [p.copy() for p in np.asarray(mesh.frac, float)]
        self.tris: dict = {}
        self.shifts: dict = {}
        self.at: list = [set() for _ in self.pos]
        self._next = 0
        for corners, shift in zip(mesh.tri, mesh.shift, strict=True):
            self._add([int(v) for v in corners], np.array(shift, int))

    # -- bookkeeping -----------------------------------------------------

    def _add(self, corners, shift) -> int:
        t = self._next
        self._next += 1
        self.tris[t] = list(corners)
        self.shifts[t] = np.array(shift, int)
        for v in corners:
            self.at[v].add(t)
        return t

    def _remove(self, t) -> None:
        for v in self.tris[t]:
            self.at[v].discard(t)
        del self.tris[t]
        del self.shifts[t]

    def mesh(self) -> Mesh:
        """The current state, as arrays, with unused vertices dropped
        and the rest renumbered in order."""
        ids = sorted(self.tris)
        tri = np.array([self.tris[t] for t in ids], int).reshape(-1, 3)
        shift = np.array([self.shifts[t] for t in ids],
                         int).reshape(-1, 3, 3)
        used, tri = np.unique(tri, return_inverse=True)
        frac = np.array(self.pos, float)[used]
        return Mesh(self.matrix, frac, tri.reshape(-1, 3), shift)

    def valence(self, v) -> int:
        """Edges at ``v``: on a closed sheet, the triangles round it."""
        return len(self.at[v])

    def corner(self, t, v) -> int:
        return self.tris[t].index(v)

    def frac_at(self, t, k) -> np.ndarray:
        """Corner ``k`` of triangle ``t``, unwrapped, in fractions."""
        return self.pos[self.tris[t][k]] + self.shifts[t][k]

    def neighbours(self, v) -> set:
        """``(u, translation)`` for every vertex joined to ``v``,
        relative to ``v`` itself."""
        out = set()
        for t in self.at[v]:
            k = self.corner(t, v)
            base = self.shifts[t][k]
            for j in (1, 2):
                u = self.tris[t][(k + j) % 3]
                out.add((u, tuple(self.shifts[t][(k + j) % 3] - base)))
        return out

    def opposite(self, t, k):
        """The triangle across side ``k`` of ``t`` (from corner ``k`` to
        ``k + 1``), and which of its sides that is, or None."""
        a, b = self.tris[t][k], self.tris[t][(k + 1) % 3]
        rel = self.shifts[t][(k + 1) % 3] - self.shifts[t][k]
        for u in self.at[a] & self.at[b]:
            if u == t:
                continue
            corners, shift = self.tris[u], self.shifts[u]
            for m in range(3):
                if (corners[m] == b and corners[(m + 1) % 3] == a
                        and np.array_equal(
                            shift[(m + 1) % 3] - shift[m], -rel)):
                    return u, m
        return None

    def find(self, a, b, rel):
        """The triangle with side ``a`` to ``b`` at translation
        ``rel``, and which side, or None."""
        rel = np.asarray(rel, int)
        for t in self.at[a]:
            corners, shift = self.tris[t], self.shifts[t]
            for k in range(3):
                if (corners[k] == a and corners[(k + 1) % 3] == b
                        and np.array_equal(
                            shift[(k + 1) % 3] - shift[k], rel)):
                    return t, k
        return None

    def _quad(self, t, k):
        """``(t, k, u, m, c, d, frame)`` for the edge on side ``k`` of
        ``t``: the far corners ``c`` of ``t`` and ``d`` of ``u``, and
        the translation that carries ``u``'s corners into ``t``'s
        frame."""
        found = self.opposite(t, k)
        if found is None:
            return None
        u, m = found
        c = (k + 2) % 3
        d = (m + 2) % 3
        frame = self.shifts[t][k] - self.shifts[u][(m + 1) % 3]
        return t, k, u, m, c, d, frame

    def _normal(self, points) -> np.ndarray:
        p = np.asarray(points) @ self.matrix
        return _unit(_cross3(p[1] - p[0], p[2] - p[0]))

    # -- operations ------------------------------------------------------

    def flip(self, t, k, check: bool = True) -> bool:
        """Turn the edge on side ``k`` of ``t`` to join the two far
        corners: in the dual, a Stone-Wales rotation of one bond.
        Refused where it would duplicate an edge, leave a vertex with
        three neighbours, or fold the two triangles over."""
        quad = self._quad(t, k)
        if quad is None:
            return False
        t, k, u, m, c, d, frame = quad
        a, b = self.tris[t][k], self.tris[t][(k + 1) % 3]
        vc, vd = self.tris[t][c], self.tris[u][d]
        sa, sb, sc = (self.shifts[t][k], self.shifts[t][(k + 1) % 3],
                      self.shifts[t][c])
        sd = self.shifts[u][d] + frame
        if check:
            if self.valence(a) <= 3 or self.valence(b) <= 3:
                return False
            if (vd, tuple(sd - sc)) in self.neighbours(vc) or (
                    vc == vd and np.array_equal(sc, sd)):
                return False
            pa, pb = self.pos[a] + sa, self.pos[b] + sb
            pc, pd = self.pos[vc] + sc, self.pos[vd] + sd
            before = self._normal([pa, pb, pc]) + self._normal(
                [pb, pa, pd])
            if (self._normal([pa, pd, pc]) @ before <= 0.2
                    or self._normal([pd, pb, pc]) @ before <= 0.2):
                return False
        self._remove(t)
        self._remove(u)
        self._add([a, vd, vc], np.array([sa, sd, sc]))
        self._add([vd, b, vc], np.array([sd, sb, sc]))
        return True

    def split(self, t, k) -> int | None:
        """A new vertex at the middle of the edge on side ``k`` of
        ``t``, and four triangles where there were two."""
        quad = self._quad(t, k)
        if quad is None:
            return None
        t, k, u, m, c, d, frame = quad
        a, b = self.tris[t][k], self.tris[t][(k + 1) % 3]
        vc, vd = self.tris[t][c], self.tris[u][d]
        sa, sb, sc = (self.shifts[t][k], self.shifts[t][(k + 1) % 3],
                      self.shifts[t][c])
        sd = self.shifts[u][d] + frame
        middle = (self.pos[a] + sa + self.pos[b] + sb) / 2.0
        home = np.floor(middle)
        n = len(self.pos)
        self.pos.append(middle - home)
        self.at.append(set())
        sm = home.astype(int)
        self._remove(t)
        self._remove(u)
        self._add([a, n, vc], np.array([sa, sm, sc]))
        self._add([n, b, vc], np.array([sm, sb, sc]))
        self._add([b, n, vd], np.array([sb, sm, sd]))
        self._add([n, a, vd], np.array([sm, sa, sd]))
        return n

    def collapse(self, t, k, longest: float) -> bool:
        """Merge the ends of the edge on side ``k`` of ``t`` at its
        middle.  Refused unless the two ends share exactly the two far
        corners as neighbours (the link condition, without which the
        sheet pinches), no edge comes out longer than ``longest``
        Angstrom, no triangle turns over, and neither far corner is
        left with three neighbours."""
        quad = self._quad(t, k)
        if quad is None:
            return False
        t, k, u, m, c, d, frame = quad
        a, b = self.tris[t][k], self.tris[t][(k + 1) % 3]
        if a == b:
            return False
        vc, vd = self.tris[t][c], self.tris[u][d]
        if self.valence(vc) <= 3 or self.valence(vd) <= 3:
            return False
        sa, sb = self.shifts[t][k], self.shifts[t][(k + 1) % 3]
        delta = tuple(sb - sa)
        around_a = self.neighbours(a) - {(b, delta)}
        around_b = {(v, tuple(np.array(r) + delta))
                    for v, r in self.neighbours(b)} - {(a, (0, 0, 0))}
        common = around_a & around_b
        expected = {(vc, tuple(self.shifts[t][c] - sa)),
                    (vd, tuple(self.shifts[u][d] + frame - sa))}
        if common != expected:
            return False
        pa, pb = self.pos[a] + sa, self.pos[b] + sb
        middle = (pa + pb) / 2.0
        home = np.floor(middle)
        merged = middle - home
        # Where the merged vertex sits in every triangle round either
        # end, each in that triangle's own frame.
        moved = {}
        for w, start in ((a, pa), (b, pb)):
            for s in self.at[w]:
                if s in (t, u):
                    continue
                j = self.corner(s, w)
                here = self.pos[w] + self.shifts[s][j] + (middle - start)
                moved[s] = (j, np.round(here - merged).astype(int))
        if moved:
            # One array for every triangle round both ends: checked
            # one at a time, the cross products were most of a remesh.
            ids = list(moved)
            before = np.array([[self.frac_at(s, i) for i in range(3)]
                               for s in ids])
            after = before.copy()
            rows = np.arange(len(ids))
            slot = np.array([moved[s][0] for s in ids])
            after[rows, slot] = merged + np.array([moved[s][1]
                                                   for s in ids])
            before, after = before @ self.matrix, after @ self.matrix
            old = np.cross(before[:, 1] - before[:, 0],
                           before[:, 2] - before[:, 0])
            new = np.cross(after[:, 1] - after[:, 0],
                           after[:, 2] - after[:, 0])
            cosine = (old * new).sum(axis=1) / np.maximum(
                np.linalg.norm(old, axis=1) * np.linalg.norm(new, axis=1),
                1e-24)
            if np.any(cosine <= 0.2):
                return False
            sides = np.linalg.norm(after - after[rows, slot][:, None],
                                   axis=2)
            if np.any(sides > longest):
                return False
        self._remove(t)
        self._remove(u)
        self.pos[a] = merged
        for s, (j, new_shift) in moved.items():
            corners = list(self.tris[s])
            shift = self.shifts[s].copy()
            corners[j] = a
            shift[j] = new_shift
            self._remove(s)
            self._add(corners, shift)
        return True

    # -- passes ----------------------------------------------------------

    def _sides(self):
        """Every edge once, as ``(length, a, b, rel)``."""
        ids = list(self.tris)
        if not ids:
            return []
        tri = np.array([self.tris[t] for t in ids], int)
        shift = np.array([self.shifts[t] for t in ids], int)
        mesh = Mesh(self.matrix, np.array(self.pos, float), tri, shift)
        keys = np.unique(mesh.edge_keys(), axis=0)
        a, b, rel = keys[:, 0], keys[:, 1], keys[:, 2:]
        length = np.linalg.norm(
            (mesh.frac[b] + rel - mesh.frac[a]) @ self.matrix, axis=1)
        return [(float(n), int(i), int(j), tuple(int(x) for x in r))
                for n, i, j, r in zip(length, a, b, rel, strict=True)]

    def split_long(self, longest: float) -> int:
        done = 0
        for length, a, b, rel in sorted(self._sides(), reverse=True):
            if length <= longest:
                break
            found = self.find(a, b, rel)
            if found is not None and self.split(*found) is not None:
                done += 1
        return done

    def collapse_short(self, shortest: float, longest: float) -> int:
        done = 0
        for length, a, b, rel in sorted(self._sides()):
            if length >= shortest:
                break
            if not self.at[a] or not self.at[b]:
                continue
            found = self.find(a, b, rel)
            if found is not None and self.collapse(*found, longest):
                done += 1
        return done

    def flip_to_six(self, longest: float = np.inf) -> int:
        """Flip every edge whose flip brings the four valences nearer
        six: the triangulation that dualises to as many hexagons as
        the curvature allows.  Not where the new edge would be longer
        than ``longest``, which the next split would only undo."""
        done = 0
        for _length, a, b, rel in self._sides():
            found = self.find(a, b, rel)
            if found is None:
                continue
            t, k = found
            quad = self._quad(t, k)
            if quad is None:
                continue
            vc = self.tris[t][quad[4]]
            vd = self.tris[quad[2]][quad[5]]
            ends = [self.valence(v) for v in (a, b, vc, vd)]
            before = sum((n - 6) ** 2 for n in ends)
            after = sum((n - 6) ** 2 for n in (ends[0] - 1, ends[1] - 1,
                                                ends[2] + 1, ends[3] + 1))
            if after >= before:
                continue
            across = ((self.pos[vd] + self.shifts[quad[2]][quad[5]]
                       + quad[6] - self.pos[vc]
                       - self.shifts[t][quad[4]]) @ self.matrix)
            if np.linalg.norm(across) <= longest and self.flip(t, k):
                done += 1
        return done


# ======================================================================
#  REMESHING AND DEFECTS
# ======================================================================

#: An even triangulation's edge: the dual's hexagons then have sides
#: of 2.46 / sqrt(3) = 1.42 A, graphene's bond.
TARGET_EDGE = 2.46


#: The furthest one Newton step may move a point, in Angstrom.  Where
#: the field is flat -- the middle of a pore -- its gradient is nearly
#: zero and an uncapped step sent a vertex thousands of Angstrom away,
#: after which every edge it touched was split until memory ran out.
MAX_PROJECTION_STEP = 0.5


def project(cart, field, level: float, steps: int = 4) -> np.ndarray:
    """Points moved onto the ``level`` sheet along the field's
    gradient, by Newton's method, a capped step at a time."""
    cart = np.array(cart, float)
    for _ in range(steps):
        value, grad = field.evaluate(cart, gradient=True)
        norm2 = np.maximum((grad ** 2).sum(axis=1), 1e-12)
        step = ((value - level) / norm2)[:, None] * grad
        length = np.linalg.norm(step, axis=1)
        too_far = length > MAX_PROJECTION_STEP
        step[too_far] *= (MAX_PROJECTION_STEP / length[too_far])[:, None]
        cart -= step
    return cart


def relax(mesh: Mesh, field, level: float,
          damping: float = 0.5) -> Mesh:
    """Each vertex moved part of the way to the middle of its
    neighbours, within the sheet, and put back on it.

    Tangential only: the normal part of the move would shrink the
    sheet, which is what smoothing a closed surface does and is
    exactly what the projection would then have to undo.
    """
    keys, _inverse, _counts = mesh.edges()
    a, b, rel = keys[:, 0], keys[:, 1], keys[:, 2:]
    vector = (mesh.frac[b] + rel - mesh.frac[a]) @ mesh.matrix
    total = np.zeros((mesh.n_vertices, 3))
    count = np.zeros(mesh.n_vertices)
    np.add.at(total, a, vector)
    np.add.at(total, b, -vector)
    np.add.at(count, a, 1)
    np.add.at(count, b, 1)
    move = total / np.maximum(count, 1)[:, None]
    cart = mesh.frac @ mesh.matrix
    _value, grad = field.evaluate(cart, gradient=True)
    normal = grad / np.maximum(np.linalg.norm(grad, axis=1),
                               1e-12)[:, None]
    move -= (move * normal).sum(axis=1)[:, None] * normal
    cart = project(cart + damping * move, field, level)
    return rewrap(mesh, cart @ np.linalg.inv(mesh.matrix))


def rewrap(mesh: Mesh, frac) -> Mesh:
    """New vertex positions, wrapped back into the cell, with each
    triangle's translations corrected for the wrap."""
    home = np.floor(frac)
    shift = mesh.shift + home[mesh.tri].astype(int)
    return Mesh(mesh.matrix, frac - home, mesh.tri.copy(), shift)


def remesh(mesh: Mesh, field, level: float,
           target: float = TARGET_EDGE, iterations: int = 8) -> Mesh:
    """Botsch and Kobbelt's isotropic remesh: split what is longer
    than four thirds of the target, collapse what is shorter than four
    fifths, flip towards valence six, relax, and project -- until the
    triangles are all about the target and the sheet is where it was.
    """
    longest, shortest = 4.0 / 3.0 * target, 0.8 * target
    ceiling = RUNAWAY * mesh.area() / (np.sqrt(3.0) / 4.0 * target ** 2)
    for _ in range(iterations):
        editor = Editor(mesh)
        editor.split_long(longest)
        editor.collapse_short(shortest, longest)
        editor.flip_to_six(longest)
        mesh = relax(editor.mesh(), field, level)
        if mesh.n_triangles > ceiling:
            raise MeshError(
                f"the remesh grew to {mesh.n_triangles} triangles where "
                f"the sheet needs about {int(ceiling / RUNAWAY)}; "
                "stopped before it took the memory with it")
    return mesh


#: How many times the triangles a sheet's area needs a remesh may
#: reach before it is stopped.  A wrong translation makes an edge
#: hundreds of Angstrom long, and splitting it again and again took a
#: machine's memory once.
RUNAWAY = 4.0


class MeshError(RuntimeError):
    """A mesh operation that went wrong rather than finished."""


def stone_wales(mesh: Mesh, pairs: int, rng, field=None,
                level: float = 0.0, temperature: float = 0.5,
                passes: int = 3) -> tuple[Mesh, int]:
    """Up to ``pairs`` Stone-Wales defects, as edge flips that turn
    four valence-six vertices into two fives and two sevens -- in the
    dual, a 5-7-7-5 where there were four hexagons.

    Metropolis on the geometry: the energy is the squared departure of
    the edge from the target, in target edges squared, and a flip that
    raises it by ``x`` is taken with probability ``exp(-x /
    temperature)``, so the defects land where the sheet can take them
    without stretching.  Not the new length against the old: across
    two equilateral triangles the far diagonal is always root three of
    the near one, and judged that way every flip was a one in a
    thousand.  Seeded, so a build is reproducible.
    Returns the mesh and how many were made.
    """
    editor = Editor(mesh)
    made = 0
    for _pass in range(passes):
        # Every side once, in a seeded random order: drawn at random
        # one at a time, most draws missed the four hexagons a defect
        # needs and a small sheet ran out of tries.
        order = [(t, k) for t in sorted(editor.tris) for k in range(3)]
        for index in rng.permutation(len(order)):
            if made >= pairs:
                break
            t, k = order[index]
            if t not in editor.tris:
                continue
            quad = editor._quad(t, k)
            if quad is None:
                continue
            _t, _k, u, _m, c, d, frame = quad
            a, b = editor.tris[t][k], editor.tris[t][(k + 1) % 3]
            vc, vd = editor.tris[t][c], editor.tris[u][d]
            if any(editor.valence(v) != 6 for v in (a, b, vc, vd)):
                continue
            old = ((editor.pos[b] + editor.shifts[t][(k + 1) % 3]
                    - editor.pos[a] - editor.shifts[t][k])
                   @ editor.matrix)
            new = ((editor.pos[vd] + editor.shifts[u][d] + frame
                    - editor.pos[vc] - editor.shifts[t][c])
                   @ editor.matrix)
            stretch = ((np.linalg.norm(new) - TARGET_EDGE) ** 2
                       - (np.linalg.norm(old) - TARGET_EDGE) ** 2
                       ) / TARGET_EDGE ** 2
            if stretch > 0 and rng.random() >= np.exp(
                    -stretch / temperature):
                continue
            if editor.flip(t, k):
                made += 1
        if made >= pairs:
            break
    mesh = editor.mesh()
    if field is not None:
        mesh = relax(mesh, field, level)
    return mesh, made


def gauss_bonnet(mesh: Mesh) -> tuple[int, int]:
    """``(sum of 6 - valence, 6 chi)``: equal on any closed sheet,
    whatever was done to it -- the rings a surface of that topology
    has to have, pentagons counted against heptagons."""
    return int((6 - mesh.valence()).sum()), 6 * mesh.euler()
