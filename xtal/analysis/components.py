"""
xtal.analysis.components
========================
A net broken into the nets its kinds of edge span.

A merged net (Eddaoudi and O'Keeffe) is two or three edge-transitive
nets laid over one another so that they share vertices: ``sph``'s
12-c vertices take six edges to 6-c vertices and six to 3-c ones,
and the two kinds of edge span two nets of their own.  So the parents
of a net are found the same way for any net, catalogued, built or
drawn: take each set of *kinds* of edge, keep the subgraph they span,
and name it (:func:`components`).  Nothing is guessed from a name.

**A kind is a symmetry class of edge.**  A catalogued net says what
its kinds are -- each ``EDGE`` line of its file is one orbit
(:func:`entry_kinds`) -- and a net drawn on a structure says it too,
since each drawn bond is stored against the asymmetric unit and
expanded over the group (:func:`drawn_kinds`).  Where neither is
known (a built framework is P1) the kinds are worked out from the
graph alone (:func:`edge_kinds`): the pair of colours a stable
colouring gives its ends, which can only lump two orbits together,
never split one.  A net with *k* kinds has at most 2^k - 1 subgraphs
to try, and :data:`MAX_KINDS` caps it.

A vertex left with two edges is a point on an edge of the component,
not a vertex of it, so it is folded away before naming: a net's edge
drawn through a 2-c vertex is still one edge of the net.
A piece with a vertex of one edge, or one that is not periodic in
every direction its parent is, is reported and never named.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from xtal.analysis.topology import Edge, Net, _colours, _incidence

#: The most kinds of edge whose every combination is tried: 255
#: subgraphs.  A net with more is asked about its kinds singly and in
#: pairs, which is where every merged net in the literature lies.
MAX_KINDS = 8


@dataclass(frozen=True)
class Component:
    """The net one set of edge kinds spans."""

    #: Which kinds of edge, as the numbers :func:`components` was given.
    kinds: tuple[int, ...]
    #: The subgraph, with its two-connected vertices folded into edges.
    net: Net = field(repr=False)
    #: How many two-connected vertices were folded away.
    folded: int = 0
    #: What the RCSR calls each piece, or ``None`` when it was not
    #: asked: a piece that is not a net (:attr:`periodic`).
    report: object = field(default=None, repr=False)

    @property
    def pieces(self) -> int:
        return len(self.net.components())

    @property
    def periodicity(self) -> int:
        """The least periodicity of its pieces: 3 for a 3-periodic net,
        less where a kind spans only layers, rods or islands."""
        return min((piece.periodicity() for piece in self.net.components()),
                   default=0)

    @property
    def periodic(self) -> bool:
        return self.report is not None

    @property
    def name(self) -> str:
        """The RCSR name when every piece is that one net, else ``""``."""
        return self.report.name if self.report is not None else ""

    @property
    def copies(self) -> int:
        return self.report.copies if self.report is not None else 0

    def sentence(self, names=None) -> str:
        """``"edges 0+1: spn"`` -- the kinds by ``names`` if given."""
        which = "+".join(str(names[k]) if names else str(k)
                         for k in self.kinds)
        if self.report is None:
            return (f"edges {which}: {self.periodicity}-periodic, "
                    f"not a net to name")
        if self.name:
            fold = f", {self.copies} copies" if self.copies > 1 else ""
            return f"edges {which}: {self.name}{fold}"
        return f"edges {which}: {self.report.headline()}"


def components(net: Net, kinds=None, *, keyed: bool = False,
               periodicity: int | None = None) -> list[Component]:
    """Every subgraph a set of ``kinds`` (one number per edge of
    ``net``) spans, fewest kinds first.

    ``kinds`` defaults to :func:`edge_kinds`.  A piece is named when
    it is periodic in as many directions as ``net`` (or
    ``periodicity``) and every vertex has three edges or more once
    two-connected ones are folded; ``keyed`` asks for the canonical
    form as well as the invariants, which on a large net is seconds a
    subgraph.  The last component is ``net`` itself.
    """
    from xtal.analysis import rcsr

    if kinds is None:
        kinds = edge_kinds(net)
    kinds = tuple(int(k) for k in kinds)
    if len(kinds) != len(net.edges):
        raise ValueError(f"{len(kinds)} kinds for {len(net.edges)} edges")
    distinct = sorted(set(kinds))
    if periodicity is None:
        periodicity = net.periodicity()
    sizes = range(1, len(distinct) + 1)
    if len(distinct) > MAX_KINDS:
        sizes = (1, 2, len(distinct))
    out = []
    for size in sizes:
        for chosen in itertools.combinations(distinct, size):
            keep = set(chosen)
            edges = [e for e, k in zip(net.edges, kinds, strict=True)
                     if k in keep]
            sub, folded = _fold(_spanned(net, edges))
            report = None
            pieces = sub.components()
            if pieces and all(
                    piece.periodicity() == periodicity
                    and min(piece.degree(v)
                            for v in range(piece.n_vertices)) >= 3
                    for piece in pieces):
                report = rcsr.describe(sub, keyed=keyed)
            out.append(Component(tuple(chosen), sub, folded, report))
    return out


def edge_kinds(net: Net) -> tuple[int, ...]:
    """Edge kinds from the graph alone: the pair of stable colours of
    an edge's two ends.  Two orbits joining the same kinds of vertex
    share a kind here; one orbit is never split."""
    colours = _colours(net.n_vertices, _incidence(
        net.n_vertices, [(e.i, e.j, e.image) for e in net.edges]))
    pairs = [tuple(sorted((colours[e.i], colours[e.j])))
             for e in net.edges]
    order = {pair: n for n, pair in enumerate(sorted(set(pairs)))}
    return tuple(order[pair] for pair in pairs)


def entry_kinds(entry) -> tuple[Net, tuple[int, ...]]:
    """A catalogued net and its edge kinds: each ``EDGE`` line of the
    file is one orbit.  A line that repeats an earlier one's orbit (the
    RCSR overstates q for 18 nets) makes no kind of its own."""
    from xtal.analysis import rcsr

    net, _frac, symbol = rcsr.resolved(entry)
    ops = rcsr.operations(entry) if ":" not in symbol else list(
        rcsr.space_group_operations(symbol))
    sites = rcsr._Sites(entry.dimension)
    for node in entry.nodes:
        for rot, trans in ops:
            sites.add(rot @ _array(node.frac) + trans)
    kind_of: dict[tuple, int] = {}
    for line, (first, second) in enumerate(entry.edges):
        a, b = _array(first), _array(second)
        for rot, trans in ops:
            i, shift_a = sites.locate(rot @ a + trans, entry)
            j, shift_b = sites.locate(rot @ b + trans, entry)
            image = tuple(int(v) for v in rcsr._pad(shift_b - shift_a))
            kind_of.setdefault(Edge(i, j, image).key(), line)
    kinds = tuple(kind_of[e.key()] for e in net.edges)
    return net, _renumbered(kinds)


def drawn_kinds(structure) -> tuple[Net, tuple[int, ...]]:
    """The net drawn on ``structure`` and its edge kinds: each drawn
    bond is stored once for its whole orbit.  A P1 structure has as
    many kinds as edges, so past :data:`MAX_KINDS` the graph's own
    (:func:`edge_kinds`) are used instead."""
    from xtal.analysis.topology import net_of
    from xtal.core import bonding, p1
    from xtal.core.structure import TOPOLOGY

    net = net_of(structure)
    graph = bonding.topology_graph(structure)
    vertices = sorted({b.i for b in graph.bonds} | {b.j for b in graph.bonds})
    renumber = {old: new for new, old in enumerate(vertices)}
    cell = p1.expand(structure)
    kind_of: dict[tuple, int] = {}
    stored = [b for b in structure.bonds if b.kind == TOPOLOGY]
    for line, bond in enumerate(stored):
        for mapped in bonding.map_explicit_bond(structure, cell, bond):
            if mapped.i in renumber and mapped.j in renumber:
                edge = Edge(renumber[mapped.i], renumber[mapped.j],
                            tuple(int(v) for v in mapped.image))
                kind_of.setdefault(edge.key(), line)
    kinds = tuple(kind_of.get(e.key(), -1) for e in net.edges)
    if -1 in kinds or len(set(kinds)) > MAX_KINDS:
        return net, edge_kinds(net)
    return net, _renumbered(kinds)


# ----------------------------------------------------------------------

def _array(point):
    import numpy as np

    return np.asarray(point, dtype=float)


def _renumbered(kinds) -> tuple[int, ...]:
    order = {k: n for n, k in enumerate(dict.fromkeys(kinds))}
    return tuple(order[k] for k in kinds)


def _spanned(net: Net, edges) -> Net:
    """The vertices ``edges`` touch, renumbered, and those edges."""
    vertices = sorted({e.i for e in edges} | {e.j for e in edges})
    renumber = {old: new for new, old in enumerate(vertices)}
    return Net(len(vertices),
               tuple(Edge(renumber[e.i], renumber[e.j], e.image)
                     for e in edges),
               tuple(net.label(v) for v in vertices))


def _fold(net: Net) -> tuple[Net, int]:
    """``net`` with every two-connected vertex replaced by one edge
    joining its neighbours, translations added; and how many went."""
    edges = [(e.i, e.j, tuple(e.image)) for e in net.edges]
    alive = set(range(net.n_vertices))
    folded = 0
    changed = True
    while changed:
        changed = False
        incident: dict[int, list] = {v: [] for v in alive}
        for index, (i, j, _image) in enumerate(edges):
            incident[i].append(index)
            if j != i:
                incident[j].append(index)
        for v in sorted(alive):
            touching = incident[v]
            if len(touching) != 2 or any(edges[t][0] == edges[t][1]
                                         for t in touching):
                continue
            ends = []
            for t in touching:
                i, j, image = edges[t]
                if i == v:
                    ends.append((j, image))
                else:
                    ends.append((i, tuple(-x for x in image)))
            (a, to_a), (b, to_b) = ends
            # v -> a by to_a and v -> b by to_b, so a -> b by
            # to_b - to_a.
            image = tuple(y - x for x, y in zip(to_a, to_b, strict=True))
            edges = [e for t, e in enumerate(edges) if t not in touching]
            edges.append((a, b, image))
            alive.discard(v)
            folded += 1
            changed = True
            break
    keep = sorted(alive)
    renumber = {old: new for new, old in enumerate(keep)}
    out = Net(len(keep), tuple(Edge(renumber[i], renumber[j], image)
                               for i, j, image in edges),
              tuple(net.label(v) for v in keep))
    return out, folded
