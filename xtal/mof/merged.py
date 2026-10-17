"""
xtal.mof.merged
===============
Linker sets for a net with more than one kind of edge.

A merged net (``sph`` is spn and hxg) joins one cluster to linkers of
two or more topicities, and its geometric question is not one span but
a *set*: a tritopic and a hexatopic whose reaches put every edge at
the length the net draws it, at one scale.  With the cluster's reach
``R_c`` and a linker's ``R_k`` (centre to connection point, each),
an edge of kind *k* is ``R_c + R_k`` long, so a set fits where

    (R_c + R_k) / l_k  is the same scale for every kind,

``l_k`` being the edge's length in the embedding.  **The embedding is
not one number**: a vertex the group leaves free moves, and the
lengths with it.  sph's 3-c vertex has one free coordinate, and the
RCSR draws it as a pyramid (70 degrees between its edges), where a
flat tritopic does not fit; it is flat at x = 0.205, the cluster's
cuboctahedron fits best near there too, and the 12-6 to 12-3 ratio
there is 1.71 against the RCSR's 1.15.  So the free coordinates are
scanned (:func:`scan`), every sample scored by how well each vertex's
directions take its block (:data:`SHAPE_FIT`, the unit-vector RMSD
PORMAKE's own locator minimises, measured from the vertex and not
from its neighbours' centroid -- centring is what lets PORMAKE take
the pyramid for a triangle), and a set is judged only where the
shapes fit.

**Where a set fits, the net is built there.**  PORMAKE places each
block on the file's own directions, so a set worked out at x = 0.205
built on the RCSR's file meets the pyramid all the same.
:func:`reembedded` writes the net at the sample, named
``sph@0.1560`` (the free coordinates' displacement), and
:class:`xtal.mof.catalog.Catalog` makes it on asking, as it makes a
decorated net.

**Neighbouring clusters must not touch.**  sph puts two 12-c clusters
exactly one 12-6 edge apart, so a short set collides however well its
ratio fits: the scale has a floor (:func:`Sample.floor`), the
clusters' atoms (connection points left out) held clear of each other
by :data:`CLEARANCE`, and a requirement is never asked below it.

Only sets for nets whose every edge meets the cluster are worked out:
that is every merged net on one kind of cluster, and an edge between
two linkers or two clusters would make the scale a second unknown.
Numpy and scipy: no PORMAKE and no RDKit.
"""

from __future__ import annotations

import dataclasses
import itertools
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

#: How far from its block a vertex's directions may be, as the RMSD of
#: unit vectors after the best rotation and pairing -- the number
#: PORMAKE's locator reports as a build's ``max_rmsd``.  0.25 because
#: PORMAKE's own screening took 0.3 as a fit, and the scaler
#: absorbs less than that as strain.
SHAPE_FIT = 0.25

#: How far apart the scales two kinds of edge ask for may be, as a
#: fraction of their mean.  The scaler stretches a joint that much and
#: no more without opening it.
SCALE_SLACK = 0.04

#: How close two clusters' atoms may come, A: the sum of their extents
#: less nothing, plus this.  A carboxylate oxygen of one and of the
#: next at 2 A is a contact; at less it is an overlap.
CLEARANCE = 2.0

#: How far a free coordinate is moved either way, and the step it is
#: moved by, in fractions of the cell along its own direction.  The
#: scan goes four steps at a time and then a step at a time near
#: wherever the shapes come within :data:`NEAR` of fitting: on sph,
#: 40 samples where every step was 101, and the same best one.
REACH = 0.25
STEP = 0.005
COARSE = 4
NEAR = 2 * SHAPE_FIT

_SAME = 1e-4


class SetError(ValueError):
    """A set of linkers the net cannot take, or a net with no set to
    work out, named."""


#: Which nets take a set, and on which node slots a cluster can stand:
#: :func:`plan`'s answer for every net of the catalogue, written by
#: ``scripts/linker_set_nets.py`` because asking it is an expansion a
#: net and the mixed-linker builder's list needs it of 2000 of them.
SET_NETS = Path(__file__).parent / "data" / "linker_set_nets.json"


@lru_cache(maxsize=1)
def set_nets() -> dict[str, tuple[int, ...]]:
    """``{net: cluster slots}`` for every net a set can be worked out
    on, as :data:`SET_NETS` records it (``{}`` if it is missing)."""
    if not SET_NETS.is_file():
        return {}
    data = json.loads(SET_NETS.read_text(encoding="utf-8"))
    return {name: tuple(slots) for name, slots in data.items()}


# ----------------------------------------------------------------------
#  The embedding and its free coordinates
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class Freedom:
    """Where a net's vertices may move without its group changing.

    ``bases[n]`` is a ``(3, k)`` array: the directions node line *n*
    may move in, fractional, each scaled so its largest component is
    one -- so a displacement of 0.1 moves the coordinate written ``x``
    by 0.1.  Every edge end is held as the operation that makes it
    from its node, so moving a node moves every edge it has.
    """

    entry: object
    ops: tuple
    lattice: np.ndarray
    nodes: tuple
    bases: tuple
    ends: tuple

    @property
    def dimension(self) -> int:
        return sum(b.shape[1] for b in self.bases)

    def split(self, u) -> list[np.ndarray]:
        """A flat displacement, one block per node line."""
        u = np.asarray(u, dtype=float).ravel()
        out, at = [], 0
        for basis in self.bases:
            k = basis.shape[1]
            out.append(basis @ u[at:at + k] if k else np.zeros(3))
            at += k
        return out

    def moved(self, u, name: str | None = None):
        """The entry with its nodes displaced by ``u``."""
        shift = self.split(u)
        nodes = tuple(dataclasses.replace(
            node, frac=tuple(float(v) for v in self.nodes[n] + shift[n]))
            for n, node in enumerate(self.entry.nodes))
        edges = tuple(
            tuple(tuple(float(v) for v in
                        rot @ (self.nodes[n] + shift[n]) + trans)
                  for n, rot, trans in pair)
            for pair in self.ends)
        return dataclasses.replace(self.entry, nodes=nodes, edges=edges,
                                   name=name or self.entry.name)

    def lengths(self, u) -> np.ndarray:
        """Each edge line's length at ``u``, in the file's units."""
        shift = self.split(u)
        out = []
        for (n, r, t), (m, r2, t2) in self.ends:
            a = r @ (self.nodes[n] + shift[n]) + t
            b = r2 @ (self.nodes[m] + shift[m]) + t2
            out.append(float(np.linalg.norm((b - a) @ self.lattice)))
        return np.array(out)


def freedom(entry) -> Freedom:
    """The free coordinates of ``entry`` (a :class:`CgdEntry`, 3-D,
    its setting named)."""
    from xtal.analysis.rcsr import space_group_operations
    from xtal.core.lattice import Lattice

    ops = tuple(space_group_operations(entry.group))
    nodes = tuple(np.asarray(n.frac, dtype=float) for n in entry.nodes)
    bases = tuple(_free_directions(p, ops) for p in nodes)
    ends = tuple(tuple(_made_by(np.asarray(point, dtype=float), nodes,
                                ops, entry.name) for point in pair)
                 for pair in entry.edges)
    lattice = np.asarray(Lattice.from_parameters(*entry.cell).matrix)
    return Freedom(entry, ops, lattice, nodes, bases, ends)


def _free_directions(point, ops) -> np.ndarray:
    """The site's free directions: the range of the mean of its
    stabiliser's rotations, which is the projector onto what the
    stabiliser leaves alone."""
    stab = []
    for rot, trans in ops:
        delta = rot @ point + trans - point
        if np.allclose(delta - np.round(delta), 0.0, atol=_SAME):
            stab.append(rot)
    projector = np.mean(stab, axis=0)
    basis = []
    for column in projector.T:
        if np.linalg.norm(column) < 1e-6:
            continue
        trial = np.array(basis + [column])
        if np.linalg.matrix_rank(trial, tol=1e-6) == len(trial):
            basis.append(column)
    out = []
    for v in basis:
        v = v / v[np.argmax(np.abs(v))]
        out.append(v)
    return np.array(out).T if out else np.zeros((3, 0))


def _made_by(point, nodes, ops, name):
    """``(node, rotation, translation)`` that puts a node at
    ``point``."""
    for n, here in enumerate(nodes):
        for rot, trans in ops:
            delta = rot @ here + trans - point
            if np.allclose(delta - np.round(delta), 0.0, atol=_SAME):
                return n, rot, trans - np.round(delta)
    raise SetError(f"{name}: an edge of the file ends on no vertex")


# ----------------------------------------------------------------------
#  Shapes
# ----------------------------------------------------------------------

def _unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    return v / np.linalg.norm(v, axis=1)[:, None]


@lru_cache(maxsize=4)
def _rotations(count: int) -> np.ndarray:
    from scipy.spatial.transform import Rotation

    return Rotation.random(count, random_state=7).as_matrix()


def _starts(n: int) -> int:
    """How many orientations to start from: a triangle or a hexagon
    pairs up from a handful, a cuboctahedron needs many."""
    return 16 if n <= 6 else 96


def shape_rmsd(target, directions) -> float:
    """The RMSD of two sets of directions as unit vectors, after the
    best rotation (proper or improper: a block can be turned over) and
    the best pairing.  What PORMAKE's locator minimises, by the same
    route: start from many orientations, pair by assignment, refine
    by Kabsch."""
    from scipy.optimize import linear_sum_assignment

    p, q = _unit(target), _unit(directions)
    if len(p) != len(q):
        return float("inf")
    best = float("inf")
    for start in _rotations(_starts(len(p))):
        turned = q @ start.T
        for _ in range(4):
            cost = ((p[:, None, :] - turned[None, :, :]) ** 2).sum(2)
            _, pairing = linear_sum_assignment(cost)
            u, _s, vt = np.linalg.svd(q[pairing].T @ p)
            turn = (u @ vt).T
            turned = q @ turn.T
        cost = ((p[:, None, :] - turned[None, :, :]) ** 2).sum(2)
        _, pairing = linear_sum_assignment(cost)
        value = float(np.sqrt(cost[np.arange(len(p)), pairing].mean()))
        best = min(best, value)
        if best < 1e-4:
            break
    return best


def ideal_shapes(n: int) -> tuple[np.ndarray, ...]:
    """What an organic vertex of ``n`` is scored against when nothing
    has been chosen for it: the flat regular polygon, and the
    tetrahedron for four."""
    angles = 2 * np.pi * np.arange(n) / n
    flat = np.stack([np.cos(angles), np.sin(angles), 0 * angles], 1)
    if n == 4:
        tetra = np.array([[1, 1, 1], [1, -1, -1], [-1, 1, -1],
                          [-1, -1, 1]], dtype=float)
        return flat, tetra
    return (flat,)


def block_directions(block) -> np.ndarray:
    """A block's connection points from their centroid."""
    points = np.asarray(block.positions, dtype=float)[
        list(block.connections)]
    return points - points.mean(axis=0)


def block_reach(block) -> float:
    """A block's mean centroid-to-point distance, A: its half of an
    edge, PORMAKE's way of joining two nodes."""
    return float(np.mean(np.linalg.norm(block_directions(block),
                                        axis=1)))


def block_extent(block) -> float:
    """How far a block's own atoms reach from its centroid, A, the
    connection points left out."""
    positions = np.asarray(block.positions, dtype=float)
    points = list(block.connections)
    centre = positions[points].mean(axis=0)
    body = np.delete(positions, points, axis=0)
    return float(np.max(np.linalg.norm(body - centre, axis=1)))


# ----------------------------------------------------------------------
#  The scan
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class Sample:
    """The net at one displacement of its free coordinates.

    ``lengths[n]`` is node line *n*'s edge to the cluster, in the
    file's units; ``fit[n]`` how far its directions are from the shape
    it is scored against; ``apart`` the closest two clusters come
    that are not joined, in the same units.
    """

    u: tuple[float, ...]
    lengths: dict
    fit: dict
    apart: float

    @property
    def worst(self) -> float:
        return max(self.fit.values()) if self.fit else 0.0

    @property
    def fits(self) -> bool:
        return self.worst <= SHAPE_FIT

    def floor(self, cluster) -> float:
        """The least scale, A per unit, at which no two clusters
        touch."""
        return (2 * block_extent(cluster) + CLEARANCE) / self.apart


@dataclass(frozen=True)
class Scan:
    """Every sample of a net's free coordinates, with what was held."""

    topology: object
    cluster_slot: int
    cluster: object
    linker_slots: tuple[int, ...]
    #: Edge line -> the linker slot at its far end.
    edge_of: dict
    samples: tuple[Sample, ...]
    freedom: Freedom

    @property
    def fitting(self) -> tuple[Sample, ...]:
        return tuple(s for s in self.samples if s.fits)

    @property
    def best(self) -> Sample:
        """The sample where the shapes fit best."""
        return min(self.samples, key=lambda s: (s.worst,
                                                np.abs(s.u).sum()))

    def ratio_range(self, first: int, second: int) -> tuple[float, float]:
        """``(low, high)`` of slot ``first``'s edge over ``second``'s
        across the samples where the shapes fit."""
        ratios = [s.lengths[first] / s.lengths[second]
                  for s in self.fitting]
        if not ratios:
            return (float("nan"), float("nan"))
        return min(ratios), max(ratios)


def plan(topology, cluster_slot: int, cluster=None
         ) -> tuple[Freedom, dict]:
    """``(freedom, edge_of)`` -- ``edge_of`` maps each edge line to
    the linker slot at its far end -- or :class:`SetError` saying why
    ``topology`` has no set to work out round ``cluster_slot``.
    Milliseconds: nothing is scanned, which is why a dialog may ask
    it on every change.

    Refused, by name, for a layer, for a net with one kind of edge
    (one length is any scale) and for one with an edge that misses
    the cluster.
    """
    entry = topology.entry()
    if entry.dimension != 3:
        raise SetError(f"{topology.name} is a layer; a set is worked "
                       f"out on 3-periodic nets")
    if not 0 <= cluster_slot < len(entry.nodes):
        raise SetError(f"{topology.name} has no node "
                       f"{cluster_slot + 1}")
    if cluster is not None and (cluster.n_connections
                                != entry.nodes[cluster_slot].coordination):
        raise SetError(
            f"{cluster.name} has {cluster.n_connections} connection "
            f"point(s) and node {cluster_slot + 1} of {topology.name} "
            f"needs {entry.nodes[cluster_slot].coordination}")
    if len(entry.edges) < 2:
        raise SetError(f"{topology.name} has one kind of edge, so any "
                       f"linker fits it at some scale")
    free = freedom(entry)
    edge_of = {}
    for line, ((n, *_), (m, *_)) in enumerate(free.ends):
        if (n == cluster_slot) == (m == cluster_slot):
            between = "two clusters" if n == cluster_slot else "two linkers"
            raise SetError(
                f"{topology.name}: the edge from node {n + 1} to "
                f"{m + 1} joins {between}; a set "
                f"is worked out only where every edge meets the "
                f"cluster")
        edge_of[line] = m if n == cluster_slot else n
    return free, edge_of


def scan(topology, cluster_slot: int, cluster, shapes=None) -> Scan:
    """Every displacement of ``topology``'s free coordinates, each
    scored: how far each vertex is from its block (``cluster`` on
    ``cluster_slot``, ``shapes[slot]`` -- a block or directions --
    for a linker that has one, :func:`ideal_shapes` otherwise), how
    long each kind of edge is and how close two clusters come.
    Refused as :func:`plan` refuses.
    """
    entry = topology.entry()
    free, edge_of = plan(topology, cluster_slot, cluster)
    linkers = tuple(sorted(set(edge_of.values())))
    targets = {cluster_slot: (block_directions(cluster),)}
    for slot in linkers:
        given = (shapes or {}).get(slot)
        if given is None:
            targets[slot] = ideal_shapes(entry.nodes[slot].coordination)
        elif hasattr(given, "connections"):
            targets[slot] = (block_directions(given),)
        else:
            targets[slot] = (np.asarray(given, dtype=float),)
    samples = _samples(free, targets, cluster_slot, edge_of)
    return Scan(topology, cluster_slot, cluster, linkers, edge_of,
                samples, free)


def _samples(free: Freedom, targets, cluster_slot, edge_of):
    """The coarse grid, then every fine step beside a coarse sample
    that came near fitting."""
    done: dict[tuple, Sample] = {}

    def take(index):
        if index not in done:
            u = tuple(float(STEP * i) for i in index)
            done[index] = _sample(free, u, targets, cluster_slot,
                                  edge_of)
        return done[index]

    last = int(round(REACH / STEP))
    for index in _grid(free.dimension, last):
        take(index)
    for index, sample in list(done.items()):
        if sample.worst > NEAR or not index:
            continue
        for offset in itertools.product(range(-COARSE + 1, COARSE),
                                        repeat=len(index)):
            near = tuple(i + o for i, o in zip(index, offset,
                                                strict=True))
            if all(abs(i) <= last for i in near):
                take(near)
    return tuple(done[k] for k in sorted(done))


def _grid(dimension: int, last: int):
    """Coarse grid indices, in fine steps: every :data:`COARSE`-th
    step in one or two dimensions, a seeded scatter beyond."""
    steps = range(-last, last + 1, COARSE)
    if dimension == 0:
        return [()]
    if dimension <= 2:
        return list(itertools.product(steps, repeat=dimension))
    rng = np.random.default_rng(0)
    scatter = rng.integers(-last, last + 1, (400, dimension))
    return [(0,) * dimension] + [tuple(int(v) for v in row)
                                 for row in scatter]


def _sample(free: Freedom, u, targets, cluster_slot, edge_of) -> Sample:
    from xtal.analysis import rcsr

    entry = free.moved(u)
    try:
        net, frac = rcsr.placement(entry)
    except rcsr.RcsrError:
        # Moved onto a higher-symmetry place: two vertices of one
        # orbit fell together, and the net is another net there.
        return Sample(tuple(u), {}, {cluster_slot: float("inf")}, 0.0)
    lattice = free.lattice
    neighbours: dict[int, list] = {}
    for edge in net.edges:
        step = (frac[edge.j] + np.asarray(edge.image) - frac[edge.i])
        neighbours.setdefault(edge.i, []).append(step @ lattice)
        neighbours.setdefault(edge.j, []).append(-step @ lattice)
    fit = {}
    first = {}
    for vertex, orbit in enumerate(net.orbits):
        first.setdefault(orbit, vertex)
    for slot, shapes in targets.items():
        here = np.array(neighbours[first[slot]])
        fit[slot] = min(shape_rmsd(here, s) for s in shapes)
    lengths = {}
    for line, value in enumerate(free.lengths(u)):
        slot = edge_of[line]
        lengths[slot] = min(lengths.get(slot, value), value)
    return Sample(tuple(u), lengths, fit,
                  _apart(net, frac, lattice, cluster_slot))


def _apart(net, frac, lattice, cluster_slot) -> float:
    """The closest two cluster vertices come, the file's units."""
    from scipy.spatial import cKDTree

    mine = [v for v, orbit in enumerate(net.orbits)
            if orbit == cluster_slot]
    shifts = np.array(list(np.ndindex(3, 3, 3))) - 1
    points = np.vstack([(frac[mine] + s) @ lattice for s in shifts])
    tree = cKDTree(points)
    home = frac[mine] @ lattice
    distances, _ = tree.query(home, k=2)
    return float(distances[:, 1].min())


# ----------------------------------------------------------------------
#  Requirements and sets
# ----------------------------------------------------------------------

def _donor(cluster) -> str:
    """What a linker's connection point hangs off, for this cluster:
    an aryl carbon where the cluster's points hang off a carboxylate
    carbon, as every PORMAKE carboxylate node has it; anything
    otherwise."""
    symbols = cluster.symbols
    for point in cluster.connections:
        for i, j, *_ in cluster.bonds:
            if point in (i, j):
                partner = j if i == point else i
                if symbols[partner] != "C":
                    return "any"
    return "aryl"


def _scales(sample: Sample, reaches: dict, cluster_reach: float) -> dict:
    return {slot: (cluster_reach + reaches[slot]) / sample.lengths[slot]
            for slot in reaches}


def edge_requirements(topology, cluster_slot: int, cluster,
                      given: dict | None = None, shapes=None,
                      scanned: Scan | None = None) -> dict:
    """``{slot: Requirement}``: what each linker slot asks for, once
    ``given`` (``{slot: reach in A}``, the centroid-to-point distance
    :func:`block_reach` measures) sets the scale.

    Each value is a donor radius, the number
    :func:`xtal.mof.linkers.profile` measures a block by: the reach
    less the 0.75 A a connection point sits out from its atom.  Its
    range is every sample where the shapes fit and the clusters have
    room, widened by :data:`SCALE_SLACK`; its value is the best-fitting
    sample's.  With nothing given, the scale is the floor -- the
    smallest framework whose clusters do not touch -- and the range
    runs upward from there.
    """
    from xtal.mof.block import CONNECTION_DISTANCE
    from xtal.mof.linkers import Requirement

    scanned = scanned or scan(topology, cluster_slot, cluster, shapes)
    given = dict(given or {})
    for slot in given:
        if slot not in scanned.linker_slots:
            raise SetError(f"node {slot + 1} of {topology.name} is not a "
                           f"linker slot")
    entry = topology.entry()
    rc = block_reach(cluster)
    donor = _donor(cluster)
    usable = scanned.fitting
    if not usable:
        raise SetError(
            f"{cluster.name} and flat linkers fit {topology.name} "
            f"nowhere its free coordinates reach (best "
            f"{scanned.best.worst:.2f}, needs {SHAPE_FIT})")
    per = {slot: [] for slot in scanned.linker_slots if slot not in given}
    best_value = {}
    for sample in usable:
        floor = sample.floor(cluster)
        if given:
            scales = _scales(sample, given, rc)
            scale = float(np.mean(list(scales.values())))
            if max(abs(s / scale - 1) for s in scales.values()) \
                    > SCALE_SLACK or scale < floor:
                continue
        else:
            scale = floor
        for slot in per:
            reach = scale * sample.lengths[slot] - rc
            per[slot].append(reach - CONNECTION_DISTANCE)
            if sample is scanned.best:
                best_value[slot] = reach - CONNECTION_DISTANCE
    out = {}
    for slot, values in per.items():
        if not values:
            raise SetError(
                f"with {_said(given)}, no embedding of {topology.name} "
                f"where the shapes fit gives the clusters room or "
                f"closes node {slot + 1}'s edge")
        value = best_value.get(slot, float(np.median(values)))
        slack = SCALE_SLACK * (value + CONNECTION_DISTANCE + rc)
        low = min(values) - slack
        high = max(values) + slack if given else float("inf")
        topicity = entry.nodes[slot].coordination
        why = (f"node {slot + 1} of {topology.name} on {cluster.name}"
               + (f", with {_said(given)}" if given else
                  ", smallest with room"))
        out[slot] = Requirement(topicity, value, max(low, 0.0), high,
                                donor=donor, why=why)
    return out


def _said(given: dict) -> str:
    return ", ".join(f"node {k + 1} at {v:.2f} A" for k, v in
                     sorted(given.items()))


@dataclass(frozen=True)
class LinkerSet:
    """One block per linker slot, and how well they fit together."""

    blocks: dict
    #: How far the kinds' scales disagree at the best sample, a
    #: fraction of their mean.
    strain: float
    sample: Sample
    #: A per unit of the file's cell.
    scale: float
    worst_fit: float

    def sentence(self) -> str:
        names = ", ".join(f"{k}={b.name}" for k, b in
                          sorted(self.blocks.items()))
        return (f"{names}: edges agree to {100 * self.strain:.1f} %, "
                f"shapes to {self.worst_fit:.2f}, at "
                f"{self.scale:.2f} A a unit")


def check_set(topology, cluster_slot: int, cluster, blocks: dict
              ) -> LinkerSet:
    """Whether ``blocks`` (``{slot: block}``, every linker slot) close
    every edge of ``topology`` at one scale, and where.

    Refused by name when they do not: the ratio of their edges against
    the range the net allows where these blocks fit its vertices, or
    the clusters touching.  The answer's sample is what
    :func:`reembedded` builds.
    """
    scanned = scan(topology, cluster_slot, cluster, shapes=blocks)
    missing = [s for s in scanned.linker_slots if s not in blocks]
    if missing:
        raise SetError(f"no block for node(s) "
                       f"{', '.join(str(k + 1) for k in missing)}")
    rc = block_reach(cluster)
    reaches = {slot: block_reach(b) for slot, b in blocks.items()}
    found = []
    for sample in scanned.fitting:
        scales = _scales(sample, reaches, rc)
        scale = float(np.mean(list(scales.values())))
        strain = max(abs(s / scale - 1) for s in scales.values())
        found.append((strain, sample.worst, sample, scale))
    if not found:
        best = scanned.best
        names = ", ".join(b.name for b in blocks.values())
        raise SetError(
            f"{cluster.name} with {names} fit {topology.name} nowhere "
            f"its free coordinates reach: the closest is "
            f"{best.worst:.2f} from the blocks' shapes (needs "
            f"{SHAPE_FIT})")
    strain, worst, sample, scale = min(found, key=lambda f: f[:2])
    if strain > SCALE_SLACK:
        first, second = scanned.linker_slots[:2]
        have = ((rc + reaches[first]) / (rc + reaches[second]))
        low, high = scanned.ratio_range(first, second)
        raise SetError(
            f"{blocks[first].name} and {blocks[second].name} make the "
            f"{_edge(topology, cluster_slot, first)} edge "
            f"{have:.2f} times the "
            f"{_edge(topology, cluster_slot, second)}; "
            f"{topology.name} allows {low:.2f}-{high:.2f} where these "
            f"blocks fit it")
    floor = sample.floor(cluster)
    if scale < floor:
        raise SetError(
            f"the clusters of {topology.name} touch with these "
            f"linkers: they make {scale:.2f} A a unit and "
            f"{cluster.name} needs {floor:.2f}, so every linker "
            f"{100 * (floor / scale - 1):.0f} % longer")
    return LinkerSet(dict(blocks), strain, sample, scale, worst)


def _edge(topology, cluster_slot, slot) -> str:
    cn = topology.entry().nodes
    return f"{cn[cluster_slot].coordination}-{cn[slot].coordination}"


def suggest_sets(topology, cluster_slot: int, cluster, catalog,
                 n: int = 5) -> list[LinkerSet]:
    """Sets of catalogue blocks that close every edge, least strained
    first.  Each linker slot's blocks are those whose shape fits it
    somewhere the cluster does; every pair is then judged by
    :func:`check_set`'s arithmetic, without scanning again."""
    from xtal.mof.linkers import profile

    scanned = scan(topology, cluster_slot, cluster)
    usable = scanned.fitting
    if not usable:
        raise SetError(f"{cluster.name} fits {topology.name} nowhere "
                       f"its free coordinates reach")
    rc = block_reach(cluster)
    donor = _donor(cluster)
    entry = topology.entry()
    pools = {}
    for slot in scanned.linker_slots:
        want = entry.nodes[slot].coordination
        pools[slot] = [b for b in catalog.fitting(want)
                       if (c := profile(b)) is not None
                       and donor in ("any", c.donor)]
    directions = _directions_at(scanned)
    found = []
    slots = scanned.linker_slots
    fits = {slot: {b.name: [shape_rmsd(directions[s.u][slot],
                                       block_directions(b))
                            for s in usable] for b in pools[slot]}
            for slot in slots}
    for combo in itertools.product(*(pools[s] for s in slots)):
        blocks = dict(zip(slots, combo, strict=True))
        reaches = {s: block_reach(b) for s, b in blocks.items()}
        best = None
        for k, sample in enumerate(usable):
            worst = max(fits[s][blocks[s].name][k] for s in slots)
            worst = max(worst, sample.fit[cluster_slot])
            if worst > SHAPE_FIT:
                continue
            scales = _scales(sample, reaches, rc)
            scale = float(np.mean(list(scales.values())))
            strain = max(abs(v / scale - 1) for v in scales.values())
            if strain > SCALE_SLACK or scale < sample.floor(cluster):
                continue
            key = (strain, worst)
            if best is None or key < best[0]:
                best = (key, sample, scale)
        if best is not None:
            (strain, worst), sample, scale = best
            found.append(LinkerSet(blocks, strain, sample, scale, worst))
    found.sort(key=lambda s: (max(s.strain / SCALE_SLACK,
                                  s.worst_fit / SHAPE_FIT), s.scale))
    return found[:n]


def _directions_at(scanned: Scan) -> dict:
    """Each fitting sample's directions at one vertex of every slot."""
    from xtal.analysis import rcsr

    out = {}
    lattice = scanned.freedom.lattice
    for sample in scanned.fitting:
        net, frac = rcsr.placement(scanned.freedom.moved(sample.u))
        neighbours: dict[int, list] = {}
        for edge in net.edges:
            step = frac[edge.j] + np.asarray(edge.image) - frac[edge.i]
            neighbours.setdefault(edge.i, []).append(step @ lattice)
            neighbours.setdefault(edge.j, []).append(-step @ lattice)
        first = {}
        for vertex, orbit in enumerate(net.orbits):
            first.setdefault(orbit, vertex)
        out[sample.u] = {slot: np.array(neighbours[first[slot]])
                         for slot in first}
    return out


# ----------------------------------------------------------------------
#  The net where the set fits
# ----------------------------------------------------------------------

#: ``sph@0.1560``, ``net@0.1_-0.05``: a net and its free coordinates'
#: displacement.
_NAME = re.compile(r"^(?P<parent>[^@]+)@(?P<u>-?\d+(?:\.\d+)?"
                   r"(?:_-?\d+(?:\.\d+)?)*)$")


def spelled(name: str, u) -> str:
    """The name a re-embedded net goes by."""
    return f"{name}@" + "_".join(f"{v:.4f}" for v in u)


def parse(name: str):
    """``(parent, u)`` for a re-embedded net's name, else ``None``."""
    found = _NAME.match(str(name))
    if not found:
        return None
    return found["parent"], tuple(float(v)
                                  for v in found["u"].split("_"))


def reembedded(topology, u):
    """``topology`` with its free coordinates moved by ``u``, as a
    topology PORMAKE builds on: the same graph (it is checked), the
    file's cell, and every edge moved with its ends."""
    from xtal.analysis import rcsr
    from xtal.mof import decorate

    free = freedom(topology.entry())
    if len(u) != free.dimension:
        raise SetError(
            f"{topology.name} has {free.dimension} free "
            f"coordinate(s), and {len(u)} were given")
    name = spelled(topology.name, u)
    entry = free.moved(u, name)
    try:
        net = rcsr.placement(entry)[0]
    except rcsr.RcsrError as exc:
        raise SetError(f"{name}: {exc}") from None
    if net.fingerprint() != topology.net().fingerprint():
        raise SetError(f"{name} is not {topology.name} any more: the "
                       f"move put vertices together")
    return decorate._topology(entry)


def derived(name: str, source):
    """The topology a re-embedded net's name spells, or ``None``."""
    spelled_ = parse(name)
    if spelled_ is None:
        return None
    return reembedded(source, spelled_[1])
