"""
xtal.carbon.ribbons
===================
Cutting a closed sheet into ribbons that still make one piece.

A templated carbon is not a closed tube round every strut: in the
example ZTC four carbons in ten are on an edge, and each dia edge of
10.3 A carries about eighteen carbons -- a ribbon two hexagons wide.

**A ribbon follows a path, so its connectivity is the net's.**  Each
net vertex gets an anchor on the sheet near it, on a side chosen by the
seed, and each net edge a shortest path over the mesh from one end's
anchor to the other's, kept to that strut's own tube.  The ribbons are
the triangles within a half-width of those paths.  Every path joins two
anchors and every anchor is shared by all the struts at its node, so
the ribbons run on through the cell exactly as the net does, at any
width a hexagon fits in.  Cutting by a score instead -- a random field,
or the side of each tube facing a direction -- needed more than half
the sheet kept before the pieces joined up, at any seed, and half a
tube is far more carbon than a ZTC's ribbon.

**Seeded noise makes it disordered**: the paths meander, because each
mesh edge's length is weighted by a smooth random field, and the width
wanders along them by another.

**The count is hit, not the width.**  The cell was solved for a
coverage, but what the density fixes is the number of carbons, so the
half-width is bisected until the largest piece of each layer, every
carbon in a ring, holds that many between them.  Layers are stacked,
never bonded, so each is its own piece and every one must percolate.
"""

from __future__ import annotations

import heapq

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

from xtal.carbon import lattice as lt
from xtal.carbon.mesh import Mesh

#: How many Fourier modes each smooth random field is the sum of.
MODES = 24

#: How much the random field may weight a mesh edge on a ribbon's
#: path, as the exponent's scale: e^0.5 is 1.6, enough for a path to
#: wander round a hexagon and not so much it leaves its strut.
MEANDER = 0.5

#: How much the half-width wanders along a ribbon, as a fraction.
WOBBLE = 0.25

#: A mesh vertex this many strut radii from a net vertex belongs to
#: that vertex's junction, which every strut meeting there may use.
JUNCTION = 1.7

_SHIFTS = np.array([(a, b, c) for a in (-1, 0, 1) for b in (-1, 0, 1)
                    for c in (-1, 0, 1)])


class RibbonError(ValueError):
    """A cut that leaves no piece running through the cell."""


class Noise:
    """Smooth periodic random fields over one cell, from ``rng``,
    varying over about ``length`` Angstrom, each of unit variance."""

    def __init__(self, matrix, length: float, rng, fields: int = 2):
        matrix = np.asarray(matrix, float)
        reciprocal = np.linalg.inv(matrix).T
        reach = np.ceil(np.linalg.norm(matrix, axis=1) / length * 1.5)
        reach = reach.astype(int)
        grid = np.array([(a, b, c)
                         for a in range(-reach[0], reach[0] + 1)
                         for b in range(-reach[1], reach[1] + 1)
                         for c in range(-reach[2], reach[2] + 1)
                         if (a, b, c) != (0, 0, 0)], float)
        wavelength = 1.0 / np.linalg.norm(grid @ reciprocal.T, axis=1)
        pool = grid[(wavelength > 0.6 * length)
                    & (wavelength < 1.6 * length)]
        if not len(pool):
            pool = grid[np.argsort(np.abs(wavelength - length))[:MODES]]
        self.modes = []
        for _field in range(fields):
            pick = pool[rng.integers(len(pool), size=MODES)]
            phase = rng.uniform(0.0, 2.0 * np.pi, MODES)
            self.modes.append((pick, phase))

    def __call__(self, which: int, frac) -> np.ndarray:
        pick, phase = self.modes[which]
        return np.cos(2.0 * np.pi * np.asarray(frac) @ pick.T
                      + phase).sum(axis=1) / np.sqrt(MODES / 2.0)


class Spines:
    """One path over a mesh for every edge of the net, joining anchors
    shared at each net vertex, and every mesh vertex's distance along
    the sheet from the nearest path."""

    def __init__(self, mesh: Mesh, skeleton, radius: float, rng,
                 noise: Noise):
        self.mesh = mesh
        matrix = np.asarray(mesh.matrix, float)
        keys, _inverse, _counts = mesh.edges()
        a, b, rel = keys[:, 0], keys[:, 1], keys[:, 2:]
        vector = (mesh.frac[b] + rel - mesh.frac[a]) @ matrix
        length = np.linalg.norm(vector, axis=1)
        middle = (mesh.frac[a] + (mesh.frac[b] + rel - mesh.frac[a]) / 2)
        weight = length * np.exp(MEANDER * noise(0, middle % 1.0))
        self.adjacency: list = [[] for _ in range(mesh.n_vertices)]
        for u, v, r, w in zip(a, b, rel, weight, strict=True):
            self.adjacency[u].append((v, tuple(r), w))
            self.adjacency[v].append((u, tuple(-r), w))
        n = mesh.n_vertices
        self.graph = coo_matrix((np.concatenate([length, length]),
                                 (np.concatenate([a, b]),
                                  np.concatenate([b, a]))),
                                shape=(n, n)).tocsr()

        cart = mesh.frac @ matrix
        owner = _nearest_owner(cart, skeleton, matrix)
        vertices = np.asarray(skeleton.vertices, float)
        near = _near_vertices(cart, vertices, matrix, JUNCTION * radius)
        directions = rng.standard_normal((len(vertices), 3))
        directions /= np.linalg.norm(directions, axis=1)[:, None]
        self.anchors = []
        for k, node in enumerate(vertices):
            target = node @ matrix + radius * directions[k]
            self.anchors.append(_closest(cart, target, matrix,
                                         candidates=near[k]))
        self.paths = []
        self.missing = 0
        for e, (i, j, image) in enumerate(skeleton.edges):
            allowed = (owner == e) | np.isin(np.arange(n),
                                             near[i] + near[j])
            path = self._path(i, j, np.asarray(image), allowed,
                              vertices, matrix)
            if path is None:
                self.missing += 1
                continue
            self.paths.append(path)
        on_path = sorted({v for path in self.paths for v in path})
        if not on_path:
            raise RibbonError("no strut of the net could be followed "
                              "over the sheet")
        self.distance = dijkstra(self.graph, indices=on_path,
                                 min_only=True)

    def _path(self, i, j, image, allowed, vertices, matrix):
        """The cheapest walk from net vertex ``i``'s anchor to the
        anchor of ``j`` displaced by ``image``, over ``allowed``
        vertices, tracking which image of each vertex it is at."""
        start, start_shift = self.anchors[i]
        goal, goal_shift = self.anchors[j]
        # Both anchors are stored wrapped; the goal is the one image of
        # j's anchor that sits by the image of j this edge reaches.
        goal_offset = tuple((goal_shift + image - start_shift).astype(int))
        best = {(start, (0, 0, 0)): 0.0}
        heap = [(0.0, start, (0, 0, 0), None)]
        came = {}
        while heap:
            cost, v, offset, previous = heapq.heappop(heap)
            if cost > best.get((v, offset), np.inf):
                continue
            came[(v, offset)] = previous
            if v == goal and offset == goal_offset:
                path = []
                state = (v, offset)
                while state is not None:
                    path.append(state[0])
                    state = came[state]
                return path[::-1]
            for u, r, w in self.adjacency[v]:
                if not allowed[u]:
                    continue
                state = (u, tuple(o + s for o, s in zip(offset, r,
                                                        strict=True)))
                if max(abs(x) for x in state[1]) > 3:
                    continue
                total = cost + w
                if total < best.get(state, np.inf):
                    best[state] = total
                    heapq.heappush(heap, (total, u, state[1], (v, offset)))
        return None


def _nearest_owner(cart, skeleton, matrix) -> np.ndarray:
    """Which net edge each point is nearest, by its nearest bead."""
    images = (skeleton.beads[None] + (_SHIFTS @ matrix)[:, None])
    tree = cKDTree(images.reshape(-1, 3))
    _d, index = tree.query(cart)
    return np.asarray(skeleton.bead_edge)[index % len(skeleton.beads)]


def _near_vertices(cart, vertices, matrix, reach) -> list:
    """For each net vertex, the mesh vertices within ``reach`` of any
    image of it."""
    tree = cKDTree(cart)
    out = []
    for node in vertices:
        found = set()
        for shift in _SHIFTS:
            found.update(tree.query_ball_point((node + shift) @ matrix,
                                               reach))
        out.append(sorted(found))
    return out


def _closest(cart, target, matrix, candidates):
    """``(vertex, shift)``: the candidate whose image ``vertex +
    shift`` is nearest ``target``."""
    candidates = np.asarray(candidates, int)
    if not len(candidates):
        candidates = np.arange(len(cart))
    frac_target = target @ np.linalg.inv(matrix)
    frac = cart[candidates] @ np.linalg.inv(matrix)
    shift = np.round(frac_target - frac)
    distance = np.linalg.norm((frac + shift - frac_target) @ matrix,
                              axis=1)
    k = int(np.argmin(distance))
    return int(candidates[k]), shift[k].astype(int)


def keep(mesh: Mesh, spines: Spines, half_width: float,
         noise: Noise) -> lt.Sheet:
    """The carbon of the triangles within ``half_width`` of a spine,
    wobbling along it, every carbon in a ring: its largest piece,
    pruned."""
    middle = ((mesh.frac[mesh.tri] + mesh.shift).mean(axis=1)) % 1.0
    reach = half_width * (1.0 + WOBBLE * noise(1, middle))
    distance = spines.distance[mesh.tri].mean(axis=1)
    return lt.prune(lt.largest_piece(lt.dual(
        mesh.subset(in_rings(mesh, distance <= reach)))))


def in_rings(mesh: Mesh, kept) -> np.ndarray:
    """``kept`` without the triangles whose carbon would be in no ring.

    A vertex is a ring of the dual only where its whole fan of
    triangles is kept, so a triangle with no such corner is a carbon
    on a chain -- a strip of triangles one wide -- and chains are not
    what a ribbon's edge is: before this, 59 % of a dia build's carbons
    were edge carbons against the example's 40 %.  Taking one away can
    open a fan, so it is repeated until nothing changes.
    """
    kept = np.asarray(kept, bool).copy()
    fan = np.bincount(mesh.tri.reshape(-1), minlength=mesh.n_vertices)
    while True:
        held = np.bincount(mesh.tri[kept].reshape(-1),
                           minlength=mesh.n_vertices)
        whole = held == fan
        still = kept & whole[mesh.tri].any(axis=1)
        if np.array_equal(still, kept):
            return kept
        kept = still


def cut(meshes, spines, noise: Noise, carbons: int, rounds: int = 30):
    """Each layer's mesh cut to one half-width, so that their largest
    pieces hold ``carbons`` between them: ``(sheets, half_width)``.
    Refused if what is kept does not run through all three pairs of
    faces."""
    total = sum(m.n_triangles for m in meshes)
    if carbons >= total:
        sheets = [lt.prune(lt.largest_piece(lt.dual(m))) for m in meshes]
        return sheets, np.inf
    low = 0.0
    high = max(float(np.nanmax(s.distance[np.isfinite(s.distance)]))
               for s in spines) * 2.0
    best = None
    for _ in range(rounds):
        middle = (low + high) / 2.0
        sheets = [keep(m, s, middle, noise)
                  for m, s in zip(meshes, spines, strict=True)]
        held = sum(s.n_atoms for s in sheets)
        if best is None or abs(held - carbons) < abs(best[2] - carbons):
            best = (sheets, middle, held)
        if abs(held - carbons) <= max(1, carbons // 500):
            break
        if held > carbons:
            high = middle
        else:
            low = middle
    sheets, half_width, _held = best
    for k, sheet in enumerate(sheets):
        if lt.periodicity(sheet.n_atoms, sheet.bonds, sheet.images) < 3:
            raise RibbonError(
                f"the ribbons of layer {k + 1} do not run through the "
                "cell in all three directions: they are too narrow to "
                "hold a ring.  Raise the density or lower the coverage")
    return sheets, half_width


def merge(sheets) -> lt.Sheet:
    """Several layers as one sheet, unbonded to each other."""
    if len(sheets) == 1:
        return sheets[0]
    offset = np.cumsum([0] + [s.n_atoms for s in sheets[:-1]])
    return lt.Sheet(
        sheets[0].matrix,
        np.vstack([s.frac for s in sheets]),
        np.vstack([s.bonds + o for s, o in zip(sheets, offset,
                                               strict=True)]),
        np.vstack([s.images for s in sheets]),
        np.vstack([s.normal for s in sheets]))
