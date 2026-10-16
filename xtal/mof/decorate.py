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
from dataclasses import dataclass, field

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

    def entry(self):
        """The decorated net as one ``.cgd`` block, in the parent's
        group: a node line per orbit of trimers (first) and of faces,
        and an edge line per orbit of edges."""
        if "_entry" not in self.__dict__:
            object.__setattr__(self, "_entry", self._entry())
        return self.__dict__["_entry"]

    def _entry(self):
        from xtal.analysis.rcsr import space_group_operations
        from xtal.io.cgd import CgdEntry, CgdNode

        ops = space_group_operations(self.group)
        trimer_reps = _representatives(self.trimers, ops)
        face_frac = np.array([face.frac for face in self.faces])
        face_reps = _representatives(face_frac, ops)
        nodes = [CgdNode(str(n + 1), 6, _wrap(self.trimers[k]))
                 for n, k in enumerate(trimer_reps)]
        nodes += [CgdNode(str(len(nodes) + n + 1), 3,
                          _wrap(face_frac[f]))
                  for n, f in enumerate(face_reps)]

        ends, centres = [], []
        for face in self.faces:
            here = np.asarray(face.frac)
            for edge, shift in face.trimers:
                there = self.trimers[edge] + np.asarray(shift)
                ends.append((here, there))
                centres.append((here + there) / 2)
        edges = []
        for c in _representatives(np.array(centres), ops):
            here, there = ends[c]
            home = np.floor(here + _SAME)
            edges.append((tuple(here - home), tuple(there - home)))
        return CgdEntry(self.name, self.group, tuple(nodes),
                        tuple(edges), self.cell)

    def topology(self):
        """The decorated net as a :class:`~xtal.mof.catalog.Topology`,
        held as text, as an RCSR layer is."""
        from xtal.io.cgd import write_cgd_string
        from xtal.mof.catalog import Topology

        entry = self.entry()
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
        bonded, free = _reach(trimers, faces, lattice)
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


def _reach(trimers, faces, lattice) -> tuple[float, float]:
    """``(farthest bonded, nearest non-bonded)`` node-to-edge-centre
    distance -- the two numbers PORMAKE's cutoff has to fall
    between."""
    from xtal.core.lattice import Lattice
    from xtal.core.neighbors import neighbor_pairs

    nodes = [np.asarray(t) for t in trimers]
    nodes += [np.asarray(face.frac) for face in faces]
    n_trimers = len(trimers)
    centres, owners, bonded = [], [], 0.0
    for f, face in enumerate(faces):
        here = np.asarray(face.frac)
        for edge, shift in face.trimers:
            there = trimers[edge] + np.asarray(shift)
            centres.append((here + there) / 2)
            owners.append((n_trimers + f, edge))
            bonded = max(bonded, np.linalg.norm(
                (there - here) @ lattice) / 2)
    points = np.mod(np.array(nodes + centres), 1.0)
    n_nodes = len(nodes)
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
    return bonded, free


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
