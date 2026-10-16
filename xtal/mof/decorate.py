"""
xtal.mof.decorate
=================
Supertetrahedral decoration: any 4-connected net as an ST-MOF net.

MIL-100 and the sod-ZMOFs are built of supertetrahedra: four M3O
trimers at the corners of a tetrahedron, a tritopic linker on each of
its four faces, and every trimer a corner of two supertetrahedra.  A
supertetrahedron is a 4-connected vertex of the net it is built on --
``mtn`` for MIL-100, ``sod`` for the ZMOFs -- so any 4-c net gives an
ST net by one transform (:func:`supertetrahedral`):

* a **6-c trimer at each edge midpoint**, shared by the two
  supertetrahedra the edge joins;
* a **3-c face node on each triple of a vertex's four edges**, the
  face of the tetrahedron those three midpoints span.

Each trimer meets three faces at either end, so the result is a
(3,6)-c net with *E* trimers and *4V* faces; ``mtn`` gives ``moo``,
the RCSR's name for MIL-100's net.

**Where a face node goes is the whole difficulty.**  PORMAKE reads a
net by distance (its ``distance_based_build``): a node and an edge
centre are joined when they are closer than a fixed cutoff, so every
edge must be shorter than every non-edge.  At the centroid of its
three midpoints a face is a third of the tetrahedron's edge from its
neighbour faces and only a 1/sqrt(3) from its trimers -- the failure
``nia-d`` had -- and on ``sod`` the two are exactly equal.  So a face
goes on the **normal through the circumcentre** of its three
midpoints, lifted away from the vertex by :data:`LIFTS` of the
triangle's own radius: its three edges are then equal by
construction, and the neighbour faces move apart as it rises.  Every
RCSR zeolite clears :data:`MIN_MARGIN` there (sod 2.0, rho 1.7, fau
1.6, lta 1.57 times the longest edge) where the centroid failed on
nine of twelve.  The embedding is decoration -- the scaler moves the
nodes to the blocks -- so it only has to read back as the right
graph, and :func:`decoration` checks that it does.

Written in the parent's own group and setting, so a decorated
``mtn`` has the four trimer kinds and six face kinds MIL-100 has,
rather than one slot per atom of a P1 cell.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

#: What a decorated net is called: ``sod`` becomes ``sod-st``.
SUFFIX = "-st"

#: How far each face is lifted off its midpoint triangle, in units of
#: the triangle's circumradius; the one with the most room wins.
#: 0.375-0.75 is where the zeolites' best lie (lta 0.375, sod 0.625,
#: rho 0.75); outside it the faces meet the next supertetrahedron's.
LIFTS = (0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0)

#: How much shorter every edge must be than every non-edge, as the
#: ratio of the nearest non-bonded node-to-edge-centre distance to the
#: farthest bonded one.  PORMAKE's cutoff is put at their geometric
#: mean, so this is the room either side of it.
MIN_MARGIN = 1.15

#: PORMAKE's node-to-edge-centre cutoff (``distance_based_build``),
#: less its own epsilon.
PORMAKE_CUTOFF = 0.5

#: The IZA framework codes the bundled RCSR file names as 4-c nets --
#: 63 of the 78 codes it holds; the other fifteen (``bct``, ``sos``,
#: ``ton`` ...) are RCSR names for other nets that happen to share
#: the letters.  A test holds every one to the file.
ZEOLITES = (
    "afi", "afx", "afy", "aht", "ana", "apc", "apd", "ast", "asv",
    "atn", "ato", "att", "atv", "aww", "bik", "bsv", "can", "cas",
    "cgs", "cha", "dft", "doh", "eab", "edi", "eri", "fau", "gis",
    "gme", "itv", "jbw", "jst", "kfi", "lev", "los", "lta", "ltj",
    "ltl", "maz", "mep", "mer", "mon", "mtn", "mvy", "nab", "nat",
    "npo", "off", "oso", "phi", "ptt", "rho", "sas", "sat", "sgt",
    "sod", "ssf", "tsc", "uos", "uov", "uoz", "vfi", "wei", "yug",
)

#: Fractional distance within which two points are one node.
_SAME = 1e-4


class DecorationError(ValueError):
    """A net that cannot be decorated, said in a sentence."""


@dataclass(frozen=True)
class Face:
    """One face of one supertetrahedron: three of a vertex's edges."""

    #: The parent vertex the supertetrahedron stands on.
    vertex: int
    #: ``(edge, shift)`` for each of its three trimers: parent edge
    #: ``edge``'s midpoint, moved ``shift`` cells to sit beside it.
    trimers: tuple[tuple[int, tuple[int, int, int]], ...]
    #: Where it was put, fractional and unwrapped.
    frac: tuple[float, float, float]


@dataclass(frozen=True, eq=False)
class Decoration:
    """A 4-c net decorated with supertetrahedra, before it is a file.

    Kept whole rather than handed back as a ``.cgd`` because what
    comes after the decoration -- the windows to fill -- is asked of
    the *parent*: a window is a ring of the parent net, and its
    trimers are the parent's edges round it.  Trimer *k* is parent
    edge *k*, in ``parent_net.edges`` order.
    """

    parent: str
    #: The space group as PORMAKE has to be told it, setting included.
    group: str
    parent_net: object = field(repr=False)
    parent_frac: np.ndarray = field(repr=False)
    #: The decorated net's cell, scaled so PORMAKE's cutoff falls
    #: between its edges and its non-edges.
    cell: tuple[float, ...]
    #: Fractional midpoint of each parent edge, unwrapped from its
    #: first vertex.
    trimers: np.ndarray = field(repr=False)
    faces: tuple[Face, ...] = field(repr=False)
    #: The lift the faces were put at, in circumradii.
    lift: float
    #: Nearest non-edge over farthest edge, node to edge centre.
    margin: float

    @property
    def name(self) -> str:
        return self.parent + SUFFIX

    def graph(self) -> Graph:
        """The decorated net in P1: trimers first, then faces."""
        return _graph(self.trimers, self.faces)

    def entry(self):
        """The decorated net as one ``.cgd`` block, in the parent's
        group: a node line per orbit of trimers (first) and of faces,
        and an edge line per orbit of edges."""
        if "_entry" not in self.__dict__:
            object.__setattr__(self, "_entry", _write(
                self.name, self.group, self.cell, self.graph()))
        return self.__dict__["_entry"]

    def topology(self):
        """The decorated net as a :class:`~xtal.mof.catalog.Topology`,
        held as text, as an RCSR layer is."""
        return _topology(self.entry())


@dataclass(frozen=True)
class Graph:
    """A net in P1, as this module builds one: each node unwrapped
    with its coordination, each edge its two nodes and where each end
    sits, so an edge through a cell face keeps its direction."""

    nodes: np.ndarray
    coordinations: tuple[int, ...]
    #: ``(a, b, frac at a, frac at b)``.
    edges: tuple


def _graph(trimers, faces, extra=()) -> Graph:
    """Trimers, faces and ``extra`` nodes ``(frac, [(edge, shift)])``
    -- a window filler and the trimers it takes -- as one graph.  A
    trimer's coordination is its six faces and every filler on it."""
    n_trimers = len(trimers)
    nodes = [np.asarray(t, dtype=float) for t in trimers]
    nodes += [np.asarray(face.frac) for face in faces]
    counts = [6] * n_trimers + [3] * len(faces)
    edges = []
    for f, face in enumerate(faces):
        here = np.asarray(face.frac)
        for edge, shift in face.trimers:
            edges.append((n_trimers + f, edge, here,
                          trimers[edge] + np.asarray(shift)))
    for at, taken in extra:
        index = len(nodes)
        nodes.append(np.asarray(at, dtype=float))
        counts.append(len(taken))
        for edge, shift in taken:
            counts[edge] += 1
            edges.append((index, edge, nodes[index],
                          trimers[edge] + np.asarray(shift)))
    return Graph(np.array(nodes), tuple(counts), tuple(edges))


def _write(name, group, cell, graph: Graph):
    """One ``.cgd`` block in ``group``: a node line per orbit of nodes
    in the graph's order, an edge line per orbit of edges."""
    from xtal.analysis.rcsr import space_group_operations
    from xtal.io.cgd import CgdEntry, CgdNode

    ops = space_group_operations(group)
    nodes = [CgdNode(str(n + 1), graph.coordinations[k],
                     _wrap(graph.nodes[k]))
             for n, k in enumerate(_representatives(graph.nodes, ops))]
    centres = np.array([(here + there) / 2
                        for _a, _b, here, there in graph.edges])
    edges = []
    for c in _representatives(centres, ops):
        _a, _b, here, there = graph.edges[c]
        home = np.floor(here + _SAME)
        edges.append((tuple(here - home), tuple(there - home)))
    return CgdEntry(name, group, tuple(nodes), tuple(edges), cell)


def _topology(entry):
    from xtal.io.cgd import write_cgd_string
    from xtal.mof.catalog import Topology

    # PORMAKE drops a file's last line unread, so END must be it.
    text = write_cgd_string([entry]).rstrip() + "\n"
    topology = Topology(
        entry.name, None, entry.group,
        tuple(node.coordination for node in entry.nodes), text,
        len(entry.edges))
    topology._cache["layer"] = False
    return topology


def supertetrahedral(net):
    """``net`` with a supertetrahedron at every vertex, as a topology
    the catalogue builds on.

    ``net`` is a catalogue :class:`~xtal.mof.catalog.Topology`, a
    :class:`~xtal.io.cgd.CgdEntry`, or a name the RCSR knows.
    """
    return decoration(net).topology()


def decoration(net) -> Decoration:
    """The supertetrahedral decoration of a 4-c net, worked out.

    Raises :class:`DecorationError` for a net with a vertex of any
    other degree, and for one whose faces cannot be placed with
    :data:`MIN_MARGIN` to spare -- naming the room there was, rather
    than writing a file PORMAKE would read as another graph.
    """
    from xtal.analysis import rcsr
    from xtal.core.lattice import Lattice

    entry = _entry_of(net)
    name = entry.name
    if entry.dimension != 3 or not entry.cell or len(entry.cell) != 6:
        raise DecorationError(
            f"{name} is not a 3-periodic net with a cell, and a "
            f"supertetrahedral net is built on one")
    parent, frac, group = rcsr.resolved(entry)
    degrees = {parent.degree(v) for v in range(parent.n_vertices)}
    if degrees != {4}:
        raise DecorationError(
            f"{name} has {_degrees(degrees)}-connected vertices; a "
            f"supertetrahedron is a 4-connected vertex")

    flat = _square_planar(parent, frac, group)
    if flat is not None:
        raise DecorationError(
            f"{name}: node {parent.label(flat)} sits on "
            f"{_FLAT_REASON[_flat_kind(parent, frac, group, flat)]}, "
            f"which holds its four edges in a plane; a "
            f"supertetrahedron is not flat, so it cannot stand there "
            f"in {group}")
    lattice = np.asarray(Lattice.from_parameters(*entry.cell).matrix)
    trimers, incident = _midpoints(parent, frac)
    best = None
    for lift in LIFTS:
        faces = _faces(frac, trimers, incident, lattice, lift)
        bonded, free = _reach(_graph(trimers, faces), lattice)
        margin = free / bonded
        if best is None or margin > best[0] + 1e-9:
            best = (margin, lift, faces, bonded, free)
    margin, lift, faces, bonded, free = best
    if margin < MIN_MARGIN:
        flat = _drawn_flat(frac, trimers, incident, lattice)
        why = (f"; node {parent.label(flat)} is drawn with its four "
               f"edges in a plane, where its four faces meet"
               if flat is not None else "")
        raise DecorationError(
            f"{name}: the faces of its supertetrahedra cannot be "
            f"placed with every edge shorter than every non-edge (at "
            f"best {margin:.2f} times as far, and PORMAKE needs "
            f"{MIN_MARGIN}){why}")
    scale = PORMAKE_CUTOFF / np.sqrt(bonded * free)
    a, b, c, alpha, beta, gamma = entry.cell
    decorated = Decoration(
        parent=name, group=group, parent_net=parent, parent_frac=frac,
        cell=(a * scale, b * scale, c * scale, alpha, beta, gamma),
        trimers=trimers, faces=faces, lift=lift, margin=margin)
    _check(decorated)
    return decorated


def zeolites() -> tuple:
    """Every RCSR zeolite net, as the file's entries, in code order."""
    from xtal.analysis import rcsr

    nets = rcsr.nets()
    return tuple(nets[code] for code in ZEOLITES)


# ----------------------------------------------------------------------
#  Geometry
# ----------------------------------------------------------------------

def _entry_of(net):
    from xtal.analysis import rcsr
    from xtal.io.cgd import CgdEntry

    if isinstance(net, CgdEntry):
        return net
    if isinstance(net, str):
        try:
            return rcsr.nets()[net]
        except KeyError:
            raise DecorationError(
                f"the RCSR has no net called {net!r}") from None
    return net.entry()


def _degrees(degrees) -> str:
    return ", ".join(str(d) for d in sorted(degrees))


_FLAT_REASON = {"inversion": "a centre of symmetry",
                "fourfold": "a fourfold axis"}


def _site_symmetry(frac, group, vertex):
    from xtal.analysis.rcsr import space_group_operations

    point = frac[vertex]
    for rotation, translation in space_group_operations(group):
        moved = rotation @ point + translation - point
        if np.abs(moved - np.round(moved)).max() < _SAME:
            yield rotation


def _flat_kind(parent, frac, group, vertex) -> str | None:
    """Why symmetry holds this vertex's four edges in a plane, if it
    does: an inversion centre pairs them off end to end, and a proper
    fourfold axis turns each into the next round one circle.  A
    -4 axis does neither -- sod's vertices sit on one -- and is how a
    tetrahedron is fourfold."""
    for rotation in _site_symmetry(frac, group, vertex):
        if np.allclose(rotation, -np.eye(3)):
            return "inversion"
        if (round(np.linalg.det(rotation)) == 1
                and round(np.trace(rotation)) == 1):
            return "fourfold"
    return None


def _square_planar(parent, frac, group) -> int | None:
    """The first vertex the group makes square planar, or ``None``.

    asv, ptt and ssf have one, and there the decoration's four faces
    fall on one point: the four midpoints share a plane and a circle,
    so every triangle of three has the same circumcentre and normal.
    """
    firsts = sorted({parent.orbits.index(o) for o in parent.orbits})
    for vertex in firsts or range(parent.n_vertices):
        if _flat_kind(parent, frac, group, vertex) is not None:
            return vertex
    return None


def _drawn_flat(frac, trimers, incident, lattice) -> int | None:
    """A vertex whose four edges the embedding drew in one plane
    (ssf's, in its mirror), though the group would let them out."""
    for vertex, edges in enumerate(incident):
        arms = np.array([(trimers[k] + np.asarray(s) - frac[vertex])
                         @ lattice for k, s in edges])
        spread = np.linalg.svd(arms, compute_uv=False)
        if spread[-1] < 0.05 * spread[0]:
            return vertex
    return None


def _midpoints(parent, frac):
    """Each edge's midpoint, and each vertex's four edges as
    ``(edge, shift)`` -- the shift that brings the midpoint beside
    that vertex rather than its first one."""
    trimers = np.empty((len(parent.edges), 3))
    incident = [[] for _ in range(parent.n_vertices)]
    for k, edge in enumerate(parent.edges):
        image = np.asarray(edge.image, dtype=float)
        trimers[k] = (frac[edge.i] + frac[edge.j] + image) / 2
        incident[edge.i].append((k, (0, 0, 0)))
        incident[edge.j].append((k, tuple(-int(v) for v in edge.image)))
    return trimers, incident


def _faces(frac, trimers, incident, lattice, lift) -> tuple[Face, ...]:
    inverse = np.linalg.inv(lattice)
    faces = []
    for vertex, edges in enumerate(incident):
        for triple in itertools.combinations(edges, 3):
            corners = [(trimers[k] + np.asarray(s)) @ lattice
                       for k, s in triple]
            middle, normal = _circumcentre(*corners)
            # Away from the fourth corner, never "away from the
            # vertex": where two edges are collinear (asv, ptt, ssf)
            # the vertex lies in the triangle's own plane.
            (last, shift), = (e for e in edges if e not in triple)
            fourth = (trimers[last] + np.asarray(shift)) @ lattice
            if np.dot(middle - fourth, normal) < 0:
                normal = -normal
            radius = np.linalg.norm(corners[0] - middle)
            at = (middle + lift * radius * normal) @ inverse
            faces.append(Face(vertex, tuple(triple),
                              tuple(float(v) for v in at)))
    return tuple(faces)


def _circumcentre(a, b, c):
    """The centre of the circle through three points, and the unit
    normal of their plane."""
    ab, ac = b - a, c - a
    normal = np.cross(ab, ac)
    offset = (np.dot(ac, ac) * np.cross(normal, ab)
              + np.dot(ab, ab) * np.cross(ac, normal))
    offset /= 2 * np.dot(normal, normal)
    return a + offset, normal / np.linalg.norm(normal)


def _reach(graph: Graph, lattice) -> tuple[float, float]:
    """``(farthest bonded, nearest non-bonded)`` node-to-edge-centre
    distance -- the two numbers PORMAKE's cutoff has to fall
    between."""
    from xtal.core.lattice import Lattice
    from xtal.core.neighbors import neighbor_pairs

    centres = np.array([(here + there) / 2
                        for _a, _b, here, there in graph.edges])
    owners = [(a, b) for a, b, _h, _t in graph.edges]
    bonded = max(np.linalg.norm((there - here) @ lattice) / 2
                 for _a, _b, here, there in graph.edges)
    points = np.mod(np.vstack([graph.nodes, centres]), 1.0)
    n_nodes = len(graph.nodes)
    pairs = neighbor_pairs(points, Lattice(lattice), 3.0 * bonded,
                           min_distance=0.0)
    free = 3.0 * bonded
    for i, j, d in zip(pairs.i, pairs.j, pairs.distance,
                       strict=True):
        node, centre = (i, j) if i < n_nodes <= j else (j, i)
        if not (node < n_nodes <= centre):
            continue
        if node in owners[centre - n_nodes] and d < bonded * 1.0001:
            continue                # its own edge, at half its length
        free = min(free, d)
    return float(bonded), float(free)


def _representatives(points, ops) -> list[int]:
    """One index per symmetry orbit of ``points``, in first-seen
    order."""
    wrapped = np.mod(np.asarray(points, dtype=float), 1.0)
    seen = np.zeros(len(wrapped), dtype=bool)
    reps = []
    for index, point in enumerate(wrapped):
        if seen[index]:
            continue
        reps.append(index)
        for rotation, translation in ops:
            image = np.mod(rotation @ point + translation, 1.0)
            delta = wrapped - image
            delta -= np.round(delta)
            seen |= (np.abs(delta) < _SAME).all(axis=1)
    return reps


def _wrap(point) -> tuple[float, ...]:
    point = np.asarray(point, dtype=float)
    return tuple(point - np.floor(point + _SAME))


def _check(decorated: Decoration) -> None:
    """The written file must expand to the graph that was meant.

    E trimers of degree 6, 4V faces of degree 3, 12V edges: a face
    lifted onto another's orbit, or a group setting that does not
    resolve, would read back as some other net, and nothing
    downstream would notice.
    """
    from xtal.analysis import rcsr

    net = rcsr.expand(decorated.entry())
    parent = decorated.parent_net
    want = (len(parent.edges) + 4 * parent.n_vertices,
            12 * parent.n_vertices)
    got = (net.n_vertices, len(net.edges))
    if got != want:
        raise DecorationError(
            f"{decorated.name} expands to {got[0]} nodes and {got[1]} "
            f"edges where it should have {want[0]} and {want[1]}")


# ----------------------------------------------------------------------
#  Windows
# ----------------------------------------------------------------------

#: The largest window looked for unless asked otherwise.  Every ring
#: of eight or fewer is milliseconds on a zeolite of 192 vertices
#: (fau); twelve is seconds on sod and past the ring search's budget
#: on fau.  Primitive is not the same as a window: fau's 8-rings are
#: primitive and are no tile's face, and its 12-ring window is above
#: this, so a person asking for fau's supercage windows asks for 12.
WINDOW_MAX = 8

#: How far a trimer's open site may turn out of its own plane to
#: point at a window's centre, degrees.  A site lies in the M3 plane,
#: which stands across the trimer's edge, so it reaches a centre
#: within this of that plane and no other.
SITE_REACH = 30.0

#: How far from a window's donor radius a filler may be and still
#: build, A: a pyridyl's ring flexes, the dative bond does not.
WINDOW_TOLERANCE = 0.3


@dataclass(frozen=True)
class Window:
    """One ring of the parent net, as a decorated net sees it."""

    #: The parent ring, ``(vertex, shift)`` in ring order.
    ring: tuple
    #: The trimers round it, ``(edge, shift)``, in the same order:
    #: trimer *k* is the edge from ring vertex *k* to *k + 1*.
    trimers: tuple
    #: Its centre, fractional: the mean of its trimers.
    centre: tuple[float, float, float]

    @property
    def size(self) -> int:
        return len(self.ring)


@dataclass(frozen=True)
class WindowKind:
    """One symmetry class of window, with the shape its trimers make.

    Lengths are in the decorated net's own units: a framework's are
    these times :func:`scale`, which depends on the blocks.
    """

    window: Window
    #: How many of this kind one cell holds.
    count: int
    #: The trimers' distance from the centre, mean.
    radius: float
    #: Their distance from their best plane, root mean square, over
    #: ``radius``: 0 is flat.
    pucker: float
    #: How many trimers have an open site that can point at the
    #: centre (:data:`SITE_REACH`).
    inward: int
    #: Every window of the kind in one cell, the first ``window``.
    members: tuple = field(default=(), repr=False, compare=False)

    @property
    def size(self) -> int:
        return self.window.size

    def label(self) -> str:
        return f"{self.size}-ring"


def windows(decorated: Decoration,
            max_size: int = WINDOW_MAX) -> list[WindowKind]:
    """The windows of a decorated net: the parent's primitive rings
    (:mod:`xtal.core.rings`), one :class:`WindowKind` per symmetry
    class, smallest first.  Asked of the parent because a window *is*
    a ring of it -- its trimers are the parent's edges round it."""
    from xtal.analysis.rcsr import space_group_operations
    from xtal.core import rings

    parent = decorated.parent_net
    adjacency = {v: [] for v in range(parent.n_vertices)}
    by_ends = {}
    for k, edge in enumerate(parent.edges):
        image = tuple(int(v) for v in edge.image)
        back = tuple(-v for v in image)
        adjacency[edge.i].append((edge.j, image))
        adjacency[edge.j].append((edge.i, back))
        by_ends[(edge.i, edge.j, image)] = (k, (0, 0, 0))
        by_ends[(edge.j, edge.i, back)] = (k, back)

    found = []
    for ring in rings.of_adjacency(adjacency, max_size):
        trimers = []
        for (a, sa), (b, sb) in zip(ring, ring[1:] + ring[:1],
                                    strict=True):
            step = tuple(y - x for x, y in zip(sa, sb, strict=True))
            k, shift = by_ends[(a, b, step)]
            trimers.append((k, tuple(s + t for s, t in
                                     zip(shift, sa, strict=True))))
        centre = np.mean([decorated.trimers[k] + np.asarray(s)
                          for k, s in trimers], axis=0)
        found.append(Window(tuple(ring), tuple(trimers),
                            tuple(float(v) for v in centre)))

    ops = space_group_operations(decorated.group)
    lattice = _lattice(decorated)
    kinds = []
    for size in sorted({w.size for w in found}):
        same = [w for w in found if w.size == size]
        centres = np.array([w.centre for w in same])
        reps = _representatives(centres, ops)
        orbit = _orbit_of(centres, reps, ops)
        for n, r in enumerate(reps):
            window = same[r]
            radius, pucker, inward = _shape(decorated, window, lattice)
            members = tuple(w for w, o in zip(same, orbit, strict=True)
                            if o == n)
            kinds.append(WindowKind(window, len(members), radius,
                                    pucker, inward, members))
    return kinds


def _lattice(decorated: Decoration) -> np.ndarray:
    from xtal.core.lattice import Lattice

    return np.asarray(Lattice.from_parameters(*decorated.cell).matrix)


def _orbit_of(points, reps, ops) -> list[int]:
    """Which representative each point is an image of."""
    wrapped = np.mod(np.asarray(points, dtype=float), 1.0)
    owner = [-1] * len(wrapped)
    for n, r in enumerate(reps):
        for rotation, translation in ops:
            image = np.mod(rotation @ wrapped[r] + translation, 1.0)
            delta = wrapped - image
            delta -= np.round(delta)
            for i in np.flatnonzero((np.abs(delta) < _SAME).all(axis=1)):
                if owner[i] < 0:
                    owner[i] = n
    return owner


def _sites(decorated, window, lattice):
    """Each trimer's centre and the unit direction its open site
    takes towards the window -- the centre's direction, laid into the
    plane across the trimer's edge -- and how far it had to turn."""
    centre = np.asarray(window.centre) @ lattice
    out = []
    for (edge, shift), (vertex, at) in zip(window.trimers, window.ring,
                                           strict=True):
        here = (decorated.trimers[edge] + np.asarray(shift)) @ lattice
        tail = (decorated.parent_frac[vertex] + np.asarray(at)) @ lattice
        axis = here - tail
        axis /= np.linalg.norm(axis)
        towards = centre - here
        flat = towards - (towards @ axis) * axis
        turn = np.degrees(np.arctan2(abs(towards @ axis),
                                     np.linalg.norm(flat)))
        out.append((here, flat / np.linalg.norm(flat), turn))
    return out


def _shape(decorated, window, lattice) -> tuple[float, float, int]:
    sites = _sites(decorated, window, lattice)
    points = np.array([here for here, _, _ in sites])
    middle = points.mean(axis=0)
    radius = float(np.mean(np.linalg.norm(points - middle, axis=1)))
    spread = np.linalg.svd(points - middle, compute_uv=False)
    pucker = float(spread[-1] / np.sqrt(len(points)) / radius)
    inward = sum(1 for _, _, turn in sites if turn <= SITE_REACH)
    return radius, pucker, inward


# ----------------------------------------------------------------------
#  What a window asks of its filler
# ----------------------------------------------------------------------

def scale(decorated: Decoration, node, face) -> float:
    """A of framework per unit of the decorated net, for this trimer
    and this tritopic face.

    A trimer and a face are joined node to node, so their centres
    are the trimer's reach (oxide to carboxylate point) plus the
    face's (centre to point) apart; the net's trimer-to-face edges,
    averaged, are that length.  The scaler moves the nodes after, so
    this is the instant answer, which a build confirms.
    """
    lattice = _lattice(decorated)
    lengths = []
    for face_ in decorated.faces:
        here = np.asarray(face_.frac)
        for edge, shift in face_.trimers:
            there = decorated.trimers[edge] + np.asarray(shift)
            lengths.append(np.linalg.norm((there - here) @ lattice))
    return (node.reach + face_reach(face)) / float(np.mean(lengths))


def trial_scale(decorated: Decoration, node_block, face_block,
                log=None) -> float:
    """A of framework per unit of the decorated net, as PORMAKE
    builds it: one pass of its builder with the trimer and the face
    and nothing in the windows, the cell's growth read off.

    What :func:`scale` estimates and cannot know: the scaler trades
    the blocks' angles against the net's, and on lta (trimer-to-face
    edges 20 % apart) that comes out 9 % smaller than the estimate,
    on sod 5 % larger.  A window filler is judged against this.
    Seconds, not the build's minute: nothing is identified.
    """
    from xtal.mof.build import _Logging, import_pormake

    key = (decorated.name, str(node_block.path), str(face_block.path))
    if key in _TRIALS:
        return _TRIALS[key]
    pormake = import_pormake()
    topology = decorated.topology()
    nodes = {}
    for slot in topology.slots():
        if not slot.is_edge:
            block = node_block if slot.coordination == 6 else face_block
            nodes[slot.key] = pormake.BuildingBlock(str(block.path))
    with _Logging(log):
        framework = pormake.Builder().build_by_type(
            topology=topology.expanded(), node_bbs=nodes)
    built = abs(np.linalg.det(np.asarray(framework.atoms.cell)))
    net = abs(np.linalg.det(_lattice(decorated)))
    _TRIALS[key] = float((built / net) ** (1.0 / 3.0))
    return _TRIALS[key]


#: Trial scales already run, by net and blocks.
_TRIALS: dict = {}


def face_reach(block) -> float:
    """A tritopic block's centre-to-point distance, mean."""
    positions = np.asarray(block.positions, dtype=float)
    points = positions[list(block.connections)]
    middle = points.mean(axis=0)
    return float(np.mean(np.linalg.norm(points - middle, axis=1)))


def donors(decorated, kind: WindowKind, node, face,
           every: int = 1, at_scale: float | None = None) -> np.ndarray:
    """Where a filler's donor nitrogens go round one window, A: each
    taken trimer's open-site line, the trimer's radius and the dative
    bond out from its centre.  ``every`` takes every so-many-th site,
    as a ditopic dps takes two of a pacs channel's three."""
    from xtal.mof.attach import DATIVE_MN

    factor = at_scale or scale(decorated, node, face)
    lattice = _lattice(decorated) * factor
    out = node.radius + DATIVE_MN[node.metal]
    return np.array([here + out * site
                     for here, site, _ in _sites(decorated, kind.window,
                                                 lattice)][::every])


def requirement(decorated, kind: WindowKind, node, face,
                every: int = 1, at_scale: float | None = None):
    """What fills one kind of window: a pyridyl with one donor on
    each taken site, as a :class:`xtal.mof.linkers.Requirement`.

    Its donor radius is the nitrogens' distance from their centroid,
    the number :func:`xtal.mof.linkers.profile` measures a block by;
    a ditopic filler is a span instead, point to point, the points
    0.75 A in from each nitrogen towards its metal.
    """
    from xtal.mof.block import CONNECTION_DISTANCE
    from xtal.mof.linkers import Requirement, within

    if kind.size % every:
        raise DecorationError(
            f"a {kind.label()} has {kind.size} sites, which taking "
            f"every {every} does not divide")
    at = donors(decorated, kind, node, face, every, at_scale)
    topicity = len(at)
    why = (f"{kind.label()} of {decorated.name} on {node.name}"
           + (f", every {every}" if every > 1 else ""))
    if topicity == 2:
        inward = at.mean(axis=0) - at
        inward /= np.linalg.norm(inward, axis=1)[:, None]
        points = at - CONNECTION_DISTANCE * inward
        value = float(np.linalg.norm(points[0] - points[1]))
    else:
        middle = at.mean(axis=0)
        value = float(np.mean(np.linalg.norm(at - middle, axis=1)))
    if topicity < 2:
        raise DecorationError(
            f"taking every {every} of a {kind.label()}'s sites leaves "
            f"{topicity}, and a filler bridges at least two")
    return Requirement(topicity, value,
                       *within(value, WINDOW_TOLERANCE),
                       donor="pyridyl", why=why)


def sentence(decorated, kind: WindowKind, node, face,
             every: int = 1, at_scale: float | None = None) -> str:
    """The line a person reads: the window, then what fills it.

    "4-ring, 4 sites, radius 7.9 A: a 4-connected pyridyl linker with
    a donor radius of 5.80 A (5.50-6.10)"."""
    wanted = requirement(decorated, kind, node, face, every, at_scale)
    across = kind.radius * (at_scale or scale(decorated, node, face))
    shape = (f"{kind.label()}, {kind.size} sites ({kind.inward} "
             f"facing in), radius {across:.1f} A")
    if kind.pucker > 0.05:
        shape += f", puckered {kind.pucker:.2f}"
    return f"{shape}: {wanted.sentence()}"


# ----------------------------------------------------------------------
#  Filling them
# ----------------------------------------------------------------------

#: Open sites a trimer has to give: one per metal.
OPEN_SITES = 3


@dataclass(frozen=True)
class Fill:
    """One kind of window to fill, and how many of its sites."""

    kind: WindowKind
    every: int = 1

    @property
    def topicity(self) -> int:
        return self.kind.size // self.every

    def token(self) -> str:
        """How the filled net's name spells it: ``f4``, ``f6e3``."""
        return f"f{self.kind.size}" + (f"e{self.every}"
                                       if self.every > 1 else "")


@dataclass(frozen=True, eq=False)
class Filled:
    """A decorated net with fillers in some of its windows."""

    decoration: Decoration
    fills: tuple[Fill, ...]
    cell: tuple[float, ...]
    graph_: Graph = field(repr=False)
    margin: float

    @property
    def name(self) -> str:
        tokens = []
        for one in self.fills:
            if one.token() not in tokens:
                tokens.append(one.token())
        return "-".join([self.decoration.name] + tokens)

    def graph(self) -> Graph:
        return self.graph_

    @property
    def n_trimer_kinds(self) -> int:
        """How many node lines are trimers: they come first."""
        return len(_representatives(self.decoration.trimers,
                                    _ops(self.decoration.group)))

    def entry(self):
        if "_entry" not in self.__dict__:
            object.__setattr__(self, "_entry", _write(
                self.name, self.decoration.group, self.cell,
                self.graph_))
        return self.__dict__["_entry"]

    def topology(self):
        topology = _topology(self.entry())
        topology._cache["filled"] = self
        return topology

    def filler_slots(self) -> dict[int, Fill]:
        """Node slot -> the fill whose filler goes there.  Fillers
        are the last node lines, one per kind in the order filled."""
        first = len(self.entry().nodes) - len(self.fills)
        return {first + n: one for n, one in enumerate(self.fills)}


def _ops(group):
    from xtal.analysis.rcsr import space_group_operations

    return space_group_operations(group)


def fill(decorated: Decoration, fills) -> Filled:
    """``decorated`` with a filler node at the centre of every window
    of each :class:`Fill`, bonded to the open site of each trimer it
    takes -- every one of them, or every ``every``-th round the ring,
    as a ditopic dps takes two of a pacs channel's three.

    Refused by name: a window whose trimers cannot all turn a site to
    its centre (:data:`SITE_REACH`), a trimer asked for more than its
    three open sites, and a choice of sites the window's own symmetry
    does not keep -- taking every other site of a square whose
    fourfold axis turns them onto the others would bond the filler to
    all four.
    """
    fills = tuple(fills)
    extra = []
    for one in fills:
        kind = one.kind
        if kind.size % one.every or kind.size // one.every < 2:
            raise DecorationError(
                f"taking every {one.every} of a {kind.label()}'s "
                f"{kind.size} sites leaves no filler to bridge them")
        if kind.inward < kind.size:
            raise DecorationError(
                f"{decorated.name}: only {kind.inward} of a "
                f"{kind.label()}'s {kind.size} trimers can turn an open "
                f"site to its centre; the rest stand edge-on to it")
        for window in kind.members:
            extra.append((np.asarray(window.centre),
                          list(window.trimers)[::one.every]))
    graph = _graph(decorated.trimers, decorated.faces, extra)
    over = [k for k, n in enumerate(graph.coordinations[
        :len(decorated.trimers)]) if n > 6 + OPEN_SITES]
    if over:
        raise DecorationError(
            f"{decorated.name}: these windows ask "
            f"{graph.coordinations[over[0]] - 6} open sites of a "
            f"trimer that has {OPEN_SITES}")
    lattice = _lattice(decorated)
    bonded, free = _reach(graph, lattice)
    margin = free / bonded
    if margin < MIN_MARGIN:
        raise DecorationError(
            f"{decorated.name} with its "
            f"{' and '.join(f.kind.label() + 's' for f in fills)} "
            f"filled cannot be written with every edge shorter than "
            f"every non-edge (at best {margin:.2f} times as far, and "
            f"PORMAKE needs {MIN_MARGIN})")
    factor = PORMAKE_CUTOFF / np.sqrt(bonded * free)
    a, b, c, alpha, beta, gamma = decorated.cell
    filled = Filled(decorated, fills,
                    (a * factor, b * factor, c * factor,
                     alpha, beta, gamma), graph, margin)
    _check_filled(filled)
    return filled


def _check_filled(filled: Filled) -> None:
    """Expanded, the file must be the graph: a filler whose choice
    of sites its window's symmetry does not keep comes back bonded to
    them all."""
    from xtal.analysis import rcsr

    graph = filled.graph_
    try:
        net = rcsr.expand(filled.entry())
        agrees = (net.n_vertices, len(net.edges)) == (
            len(graph.nodes), len(graph.edges))
    except (rcsr.RcsrError, ValueError):
        # A node with more edges than it declared is the reader's
        # refusal of the same thing; retrying other settings of the
        # group then finds none it knows.
        agrees = False
    if not agrees:
        raise DecorationError(
            f"{filled.name}: the windows' symmetry relates the sites "
            f"a filler takes to the ones it leaves, so in "
            f"{filled.decoration.group} it would take them all; "
            f"fill every site, or the window in a lower symmetry")


#: ``sod-st-f4-f6``: a decorated net and the windows filled in it,
#: each by size and, after ``e``, how many sites a filler skips.
_NAME = re.compile(r"^(?P<parent>.+?)" + re.escape(SUFFIX)
                   + r"(?P<fills>(?:-f\d+(?:e\d+)?)*)$")


def parse(name: str):
    """``(parent, [(size, every), ...])`` for a decorated net's name,
    or ``None`` for any other."""
    found = _NAME.match(name)
    if not found:
        return None
    fills = [(int(size), int(every or 1)) for size, every in
             re.findall(r"-f(\d+)(?:e(\d+))?", found["fills"])]
    return found["parent"], fills


def derived(name: str, source=None):
    """The topology a decorated net's name spells, or ``None`` if the
    name is not one.  ``source`` is the parent net when the caller
    has it (the catalogue's own); the RCSR's otherwise."""
    spelled = parse(name)
    if spelled is None:
        return None
    parent, spec = spelled
    decorated = decoration(source if source is not None else parent)
    if not spec:
        return decorated.topology()
    return filled(decorated, spec).topology()


def filled(decorated: Decoration, spec) -> Filled:
    """``decorated`` with every window of each ``(size, every)``
    filled: all kinds of that size, as lta's two kinds of 4-ring."""
    largest = max([WINDOW_MAX] + [size for size, _ in spec])
    kinds = windows(decorated, largest)
    fills = []
    for size, every in spec:
        chosen = [k for k in kinds if k.size == size]
        if not chosen:
            have = ", ".join(sorted({str(k.size) for k in kinds}))
            raise DecorationError(
                f"{decorated.parent} has no {size}-ring windows (its "
                f"windows are {have}-rings)")
        fills += [Fill(k, every) for k in chosen]
    return fill(decorated, fills)


# ----------------------------------------------------------------------
#  Building one
# ----------------------------------------------------------------------

def prepared(request, catalog, folder):
    """``(request, catalog)`` for a build on a filled net, with the
    blocks it needs that are not blocks yet written into ``folder``.

    A trimer slot of 7 to 9 named with a 6-connected trimer takes its
    twin (:func:`xtal.mof.trimer.write_twin`) with as many open sites
    made points; a filler named from the isoreticular series
    (:func:`xtal.mof.linkers.stored`) is embedded from its SMILES.
    Anything already a block of the right count is used as it is.
    """
    from dataclasses import replace

    from xtal.mof.build import MofError
    from xtal.mof.catalog import Catalog, CatalogError
    from xtal.mof.trimer import TrimerError, twin_name, write_twin

    topology = catalog.topology(request.topology)
    blocks = Path(folder) / "blocks"
    nodes = dict(request.nodes)
    made = topology._cache.get("filled")
    if made is not None:
        _refuse_misfits(made, nodes, catalog)
    wrote = False
    for slot in topology.slots():
        name = nodes.get(slot.key) if not slot.is_edge else None
        if not name:
            continue
        try:
            block = catalog.building_block(name)
        except CatalogError:
            block = None
        if block is not None and block.n_connections == slot.coordination:
            continue
        if (block is not None and block.n_connections == 6
                and 6 < slot.coordination <= 6 + OPEN_SITES):
            count = slot.coordination - 6
            try:
                write_twin(block.path, blocks, count=count)
            except TrimerError as exc:
                raise MofError(f"{name}: {exc}") from None
            nodes[slot.key] = twin_name(name, count)
            wrote = True
        elif block is None:
            _write_series(name, blocks)
            wrote = True
    if not wrote:
        return request, catalog
    widened = Catalog(catalog.topology_dirs, catalog.bb_dirs + (blocks,))
    # The made net, so the wider catalogue does not make it again.
    widened._made[request.topology] = topology
    return replace(request, nodes=nodes), widened


def _write_series(name: str, folder: Path) -> None:
    from xtal.build import chem
    from xtal.mof import linkers
    from xtal.mof.build import MofError

    found = [c for c in linkers.stored() if c.name == name]
    if not found:
        raise MofError(f"no building block called {name!r}, and no "
                       f"generated linker either")
    if not chem.installed():
        raise MofError(f"building {name} from its SMILES needs the "
                       f"'build' extra (RDKit)")
    linkers.write_block(found[0], folder)


def _refuse_misfits(made: Filled, nodes, catalog) -> None:
    """Every filler must be inside what its window asks, before
    anything is built: a donor radius three times too large builds,
    with a metal-nitrogen bond of 0.6 A where the scaler gave up."""
    from xtal.mof import linkers
    from xtal.mof.build import MofError
    from xtal.mof.catalog import CatalogError
    from xtal.mof.partition import node_geometry
    from xtal.mof.trimer import TrimerError

    trimer = nodes.get(0)
    face = nodes.get(made.n_trimer_kinds)
    if not trimer or not face:
        return                      # _resolve says what is missing
    try:
        node = node_geometry(catalog.building_block(trimer))
        face_block = catalog.building_block(face)
    except (CatalogError, TrimerError) as exc:
        raise MofError(f"{made.name}: {exc}") from None
    trial = None
    for slot, one in made.filler_slots().items():
        name = nodes.get(slot)
        if not name:
            continue
        if trial is None:
            trial = trial_scale(made.decoration,
                                catalog.building_block(trimer),
                                face_block)
        wanted = requirement(made.decoration, one.kind, node,
                             face_block, one.every, trial)
        offered = _candidate(name, catalog, linkers)
        if offered is None:
            continue
        if not wanted.admits(offered):
            raise MofError(
                f"{name} has a {wanted.measure} of "
                f"{offered.value:.2f} A, and the "
                f"{one.kind.label()}s of {made.decoration.name} on "
                f"{node.name} with {face} ask for {wanted.value:.2f} "
                f"({wanted.low:.2f}-{wanted.high:.2f}); it would be "
                f"built strained or not at all")


def _candidate(name, catalog, linkers):
    from xtal.mof.catalog import CatalogError

    try:
        return linkers.profile(catalog.building_block(name))
    except CatalogError:
        pass
    found = [c for c in linkers.stored() if c.name == name]
    return found[0] if found else None
