"""
xtal.analysis.topology
======================
A net as the only thing a net is: a periodic graph.

**Only the connectivity matters.**  A net is a finite quotient graph
whose edges each carry a lattice translation, taken up to relabelling
of the vertices and any change of basis in ``GL(d, Z)``.  The cell, the
coordinates and the space group of the crystal underneath are all
irrelevant to its identity, which is what makes the answer stable under
everything else the application does to a structure -- a net survives a
change of setting, a supercell and a relaxation unchanged, because none
of those touch which vertex is joined to which.

This module is the graph, its invariants and its **canonical key**.
Naming one against the RCSR is :mod:`xtal.analysis.rcsr`, and the split
is deliberate: nothing here knows that a catalogue exists.

The invariants -- the coordination sequence and the point symbol --
recognise a net.  The key *writes it down*: :meth:`Net.minimal`
divides out the translations the crystal's cell did not know about, and
:meth:`Net.key` describes what is left in the one way that does not
depend on how it arrived.  Two nets are the same net if and only if
their keys are equal, which is what makes an answer from the key a
decision where an answer from the invariants is a filter.

Three things do the work, and each is here because the one before it
was not enough:

* **a walk.**  Numbering the vertices in the order a breadth-first
  traversal reaches them, in the cell it reaches them in, settles
  everything but where the walk starts and in what frame -- so the walk
  is made to start everywhere in every frame and the smallest
  description wins.
* **the equilibrium placement.**  A walk cannot tell apart two vertices
  it reaches in the same cell of the same colour, and a net is full of
  them; taking both ways round at every such step is not affordable.
  The placement -- every vertex at the mean of its neighbours -- is
  decided by the connectivity alone and separates them.
* **Hermite normal form.**  What the walk cannot fix is the basis, and
  reducing the translations it met, in the order it met them, leaves
  one description out of the whole ``GL(d, Z)`` orbit.

**The images are always three-dimensional** even for a net that is
2-periodic, so that a layer drawn in a crystal and a layer read out of
RCSR's 2D entries are the same kind of object.  How periodic a net is
does not come from the width of its images; it is the rank of the
lattice its own cycles generate (:meth:`Net.periodicity`), and a net
drawn on a 3-periodic crystal is routinely a 2-periodic layer or a
1-periodic rod.

**A component of the quotient graph is not a component of the net.**
One vertex with a single edge to its own image two cells along is
connected here and is two disjoint chains in the crystal.  That is not
a curiosity: it is what interpenetration looks like the moment a net is
described in a cell larger than its own, and
:meth:`Net.multiplicity` is what counts the copies (§
:func:`_saturation_index`).
"""

from __future__ import annotations

import math
import sys
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from fractions import Fraction
from functools import lru_cache
from itertools import combinations, permutations

import numpy as np

from xtal.core.bonding import (
    BondGraph,
    coordination_sequence,
    point_symbol,
)

#: How far the coordination sequence is taken.  Ten is what RCSR
#: publishes and is what the catalogue is indexed on; shortening it
#: costs discrimination and lengthening it would not match.
DEPTH = 10

#: The ring search's bound, as in :func:`xtal.core.bonding.point_symbol`.
MAX_RING = 12

#: How many steps all the walks over one net may take between them.
#: A walk is linear in the size of the net, and there are a walk's
#: worth of them per frame per starting vertex -- so this is the bound
#: on the whole answer and not on any one walk, and reaching it means
#: no key rather than a slow one.  See :class:`TopologyError`.
WALK_BUDGET = 4_000_000

#: How deep a walk is allowed to recurse: a frame per vertex and one
#: per edge end.  Larger nets say so instead of exhausting the
#: interpreter's stack.
WALK_DEPTH = 80_000


class TopologyError(ValueError):
    """A net that cannot be reduced or keyed, and why.

    Raised rather than answered around, because every one of these is
    a net whose *key* would otherwise be computed in the wrong cell --
    and a key computed in the wrong cell is not a slower answer, it is
    a different net's answer.  The caller falls back on the
    invariants, which are true whatever this says.
    """


@dataclass(frozen=True)
class Edge:
    """One edge of the quotient graph: two vertices and a translation.

    Not a :class:`~xtal.core.structure.CellBond`, which is the same
    three fields plus a distance -- and a net edge has no length to
    state.  It carries the three attribute names
    :class:`~xtal.core.bonding.BondGraph` reads, so the walks in
    :mod:`xtal.core.bonding` work on a net unchanged rather than being
    written a second time here to disagree with the first.
    """

    i: int
    j: int
    image: tuple[int, int, int]

    def key(self) -> tuple:
        reverse = (self.j, self.i, tuple(-v for v in self.image))
        return min((self.i, self.j, self.image), reverse)


@dataclass(frozen=True)
class Fingerprint:
    """What is compared against the catalogue.

    The coordination sequences and point symbols of the *distinct*
    vertices, as sets rather than lists.  Both invariants are computed
    on the infinite net, so neither changes when the same net is
    described in a larger cell -- but the cell decides how many times
    each vertex appears, and only a set survives that.  It is the whole
    reason this can name MOF-5's eight-vertex **pcu** against RCSR's
    one-vertex one without any canonical form existing.
    """

    periodicity: int
    sequences: tuple[tuple[int, ...], ...]
    symbols: tuple[str, ...]

    def token(self) -> str:
        """The catalogue's key: one line, stable across versions."""
        walks = ";".join(",".join(str(n) for n in s)
                         for s in self.sequences)
        return f"{self.periodicity}|{walks}|{';'.join(self.symbols)}"

    def coordination(self) -> tuple[int, ...]:
        """The coordination numbers, distinct and sorted."""
        return tuple(sorted({s[0] for s in self.sequences if s}))


@dataclass(frozen=True)
class Net:
    """A periodic graph, and nothing else."""

    n_vertices: int
    edges: tuple[Edge, ...]
    #: What to call each vertex in a report -- a site label, an
    #: element.  Never part of the identity.
    labels: tuple[str, ...] = ()
    #: Which symmetry orbit each vertex came from, when that is known.
    #:
    #: Not part of the identity either, and purely an economy -- but a
    #: large one.  A net drawn on a structure expands over the space
    #: group, so the group maps the net onto itself and two vertices in
    #: one orbit are related by an automorphism of the net: they have
    #: the same coordination sequence and the same point symbol, and
    #: computing either twice is waste.  RCSR's own ``tep`` is 920
    #: vertices and 28 orbits.
    orbits: tuple[int, ...] = ()
    _cache: dict = field(default_factory=dict, compare=False,
                         repr=False)

    # ---------------------------------------------------------- graph

    def graph(self) -> BondGraph:
        if "graph" not in self._cache:
            self._cache["graph"] = BondGraph(self.n_vertices,
                                             list(self.edges))
        return self._cache["graph"]

    def degree(self, vertex: int) -> int:
        return len(self.graph().neighbors(vertex))

    def is_empty(self) -> bool:
        return not self.edges

    def label(self, vertex: int) -> str:
        if vertex < len(self.labels) and self.labels[vertex]:
            return self.labels[vertex]
        return f"vertex {vertex}"

    # --------------------------------------------------- how periodic

    def voltages(self) -> np.ndarray:
        """The translations the net's own cycles close onto.

        A spanning forest fixes an offset for every vertex; an edge is
        then worth the difference between what its two ends say, which
        is zero for the forest's own edges and the cycle's voltage for
        every other.  Those vectors generate the net's lattice, and
        everything about how periodic it is follows from them.
        """
        if "voltages" in self._cache:
            return self._cache["voltages"]
        graph = self.graph()
        offset: dict[int, np.ndarray] = {}
        for start in range(self.n_vertices):
            if start in offset:
                continue
            offset[start] = np.zeros(3, dtype=int)
            queue = deque([start])
            while queue:
                a = queue.popleft()
                for b, translation in graph.neighbors_with_images(a):
                    if b not in offset:
                        offset[b] = offset[a] + translation
                        queue.append(b)
        found = [offset[e.i] + np.asarray(e.image, dtype=int)
                 - offset[e.j] for e in self.edges]
        found = [v for v in found if v.any()]
        out = (np.array(found, dtype=int) if found
               else np.zeros((0, 3), dtype=int))
        self._cache["voltages"] = out
        return out

    def periodicity(self) -> int:
        """0, 1, 2 or 3 -- the rank of the net's own lattice."""
        voltages = self.voltages()
        if not len(voltages):
            return 0
        return int(np.linalg.matrix_rank(voltages))

    def multiplicity(self) -> int:
        """How many independent copies of this net the crystal holds.

        The quotient graph is connected and the net need not be: a
        vertex joined to its own image two cells along is one component
        here and two chains in the crystal.  The count is the index of
        the lattice the cycles generate in the lattice of everything
        parallel to it -- which is 2 in that example, and is the
        interpenetration number of a net described in a doubled cell.
        """
        return _saturation_index(self.voltages())

    def components(self) -> list[Net]:
        """The connected pieces of the quotient graph, renumbered.

        One `Net` each, so every component is identified in its own
        right: an interpenetrated framework is two copies of one net
        and saying so needs each of them named.
        """
        graph = self.graph()
        seen = [False] * self.n_vertices
        out: list[Net] = []
        for start in range(self.n_vertices):
            if seen[start]:
                continue
            members: list[int] = []
            queue = deque([start])
            seen[start] = True
            while queue:
                a = queue.popleft()
                members.append(a)
                for b in graph.neighbors(a):
                    if not seen[b]:
                        seen[b] = True
                        queue.append(b)
            members.sort()
            renumber = {old: new for new, old in enumerate(members)}
            kept = tuple(Edge(renumber[e.i], renumber[e.j], e.image)
                         for e in self.edges if e.i in renumber)
            if not kept:
                continue                    # an isolated vertex
            out.append(Net(len(members), kept,
                           tuple(self.label(m) for m in members),
                           tuple(self.orbits[m] for m in members)
                           if len(self.orbits) == self.n_vertices
                           else ()))
        return out

    # ---------------------------------------------------- invariants

    def coordination_sequence(self, vertex: int,
                              depth: int = DEPTH) -> tuple[int, ...]:
        return tuple(coordination_sequence(self.graph(), vertex, depth))

    def point_symbol(self, vertex: int,
                     max_ring: int = MAX_RING) -> str:
        return point_symbol(self.graph(), vertex, max_ring)

    def representatives(self) -> list[int]:
        """One vertex per orbit, or every vertex when none is known.

        Every invariant is computed on these and on nothing else.
        Without orbits that is every vertex, which is correct and slow;
        with them it is as many vertices as the net has *kinds* of
        vertex, which is what the answer depends on anyway.
        """
        vertices = [v for v in range(self.n_vertices) if self.degree(v)]
        if len(self.orbits) != self.n_vertices:
            return vertices
        seen: dict[int, int] = {}
        for vertex in vertices:
            seen.setdefault(self.orbits[vertex], vertex)
        return sorted(seen.values())

    # ------------------------------------------------- the canonical form

    def minimal(self) -> Net:
        """The same net, in the smallest cell it has.

        The net's own translations -- the ones the crystal's cell does
        not know about -- divided out.  MOF-5's eight-vertex **pcu**
        comes back with one vertex and three edges, which is how RCSR
        writes it, and so does every other description of it: a
        supercell, a centred setting, another choice of asymmetric
        unit.  That is the whole point of doing it.

        The quotient graph must be connected; a drawn net is split by
        :meth:`components` first, because two interpenetrating nets
        have no common cell to be smallest in.
        """
        if "minimal" not in self._cache:
            n, edges, d = _minimal(self, WALK_BUDGET)
            self._cache["minimal"] = Net(n, tuple(
                Edge(i, j, tuple(image) + (0,) * (3 - d))
                for i, j, image in edges))
        return self._cache["minimal"]

    def key(self, budget: int = WALK_BUDGET) -> str:
        """The canonical form of this net: equal keys iff same net.

        A fingerprint can be shared by two nets and is a filter.  This
        is a decision: the net is reduced to its smallest cell and then
        written down in the one way that does not depend on how it
        arrived -- so two nets are the same net **if and only if** the
        strings match, and "no catalogued net has this key" is a fact
        rather than a strong hint.

        ``budget`` bounds the search, in walk steps.  It is not a
        tuning knob but a promise about the worst case: a panel that
        refreshes while a chemist draws cannot spend half a minute on
        a net that will not settle, and a net that runs out is named by
        its invariants instead.  The index build, which has nowhere to
        be, uses the whole of it.
        """
        if ("key", budget) not in self._cache:
            n, edges, d = _minimal(self, budget)
            self._cache[("key", budget)] = _canonical(n, edges, d,
                                                      budget)
        return self._cache[("key", budget)]

    def fingerprint(self, depth: int = DEPTH) -> Fingerprint:
        """The invariants of every kind of vertex, as sets.

        Sets over *all* the representatives rather than one symbol per
        coordination sequence.  Two vertices can walk identically and
        ring differently, and picking one of them to speak for both
        would make the answer depend on which came first -- which
        depends on the cell, which is the one thing a net's identity
        must not.
        """
        key = ("fingerprint", depth)
        if key in self._cache:
            return self._cache[key]
        sequences, symbols = set(), set()
        for vertex in self.representatives():
            sequences.add(self.coordination_sequence(vertex, depth))
            symbols.add(self.point_symbol(vertex))
        out = Fingerprint(self.periodicity(), tuple(sorted(sequences)),
                          tuple(sorted(symbols)))
        self._cache[key] = out
        return out


# ======================================================================
#  FROM A STRUCTURE
# ======================================================================

def net_of(structure) -> Net:
    """The net the user drew, with the framework underneath it gone.

    Only the bonds marked :data:`~xtal.core.structure.TOPOLOGY`, and
    only the atoms they join: a net drawn over a linker has three atoms
    per edge that are not vertices of anything, and counting them would
    make every invariant wrong.
    """
    from xtal.core import bonding, p1

    graph = bonding.topology_graph(structure)
    vertices = sorted({b.i for b in graph.bonds}
                      | {b.j for b in graph.bonds})
    renumber = {old: new for new, old in enumerate(vertices)}
    edges = tuple(Edge(renumber[b.i], renumber[b.j],
                       tuple(int(v) for v in b.image))
                  for b in graph.bonds)
    cell = p1.expand(structure)
    labels = tuple(cell.labels[v] or cell.elements[v] for v in vertices)
    # The site an atom came from *is* its orbit: a topology bond is
    # stored against the asymmetric unit and expanded over the group,
    # so the group maps the net onto itself and one site's atoms are
    # one kind of vertex.
    orbits = tuple(int(cell.site_idx[v]) for v in vertices)
    return Net(len(vertices), edges, labels, orbits)


def net_of_chemistry(structure) -> Net:
    """The net of the *bonds*, rather than the net drawn over them.

    :func:`net_of` answers about a net somebody drew by hand.  This
    answers about the crystal as it is bonded, which is what makes
    interpenetration a question the application can ask without being
    told where the nodes are.
    """
    from xtal.core import bonding, p1

    graph = bonding.graph(structure)
    cell = p1.expand(structure)
    edges = tuple(Edge(b.i, b.j, tuple(int(v) for v in b.image))
                  for b in graph.bonds)
    labels = tuple(cell.labels[v] or cell.elements[v]
                   for v in range(cell.n_atoms))
    orbits = tuple(int(cell.site_idx[v]) for v in range(cell.n_atoms))
    return Net(cell.n_atoms, edges, labels, orbits)


@dataclass(frozen=True)
class Interpenetration:
    """How many independent frameworks a crystal holds."""

    fold: int                   # 1 is not interpenetrated
    frameworks: int             # 3-periodic components
    other: int                  # everything else: solvent, ions, dust

    def text(self) -> str:
        if self.fold <= 1:
            return "not interpenetrated"
        return f"{self.fold}-fold interpenetrated"


def interpenetration(structure) -> Interpenetration:
    """Count the independent frameworks threaded through each other.

    Two things have to be counted and only one of them is obvious.  A
    second framework that is simply *disconnected* from the first is
    another component, which :meth:`Net.components` finds.  A second
    one described in the *same* component -- because the cell given is
    a multiple of the net's own -- is not, and is what
    :meth:`Net.multiplicity` is for.  A count of components alone gets
    that case wrong, and it is the common one in deposited files.

    Only 3-periodic components are frameworks.  The rest are solvent,
    counter-ions and whatever else was left in the pores, which is why
    they are counted separately rather than ignored: Ni2Cl2BTDD has
    eighteen of them and they are not a second framework.
    """
    components = net_of_chemistry(structure).components()
    frameworks = [c for c in components if c.periodicity() == 3]
    return Interpenetration(
        fold=sum(c.multiplicity() for c in frameworks),
        frameworks=len(frameworks),
        other=len(components) - len(frameworks))


# ======================================================================
#  INTEGER LATTICES
# ======================================================================

def _saturation_index(vectors: np.ndarray) -> int:
    """``[L' : L]`` for the lattice ``L`` these vectors generate.

    ``L'`` is everything in the rational span of ``L`` that is still
    integral, so the index is 1 exactly when ``L`` is already
    everything it could be, and is the number of independent copies of
    the net otherwise.

    It is the greatest common divisor of the ``r`` by ``r`` minors of a
    *basis* of ``L`` -- the classical ``D_r``, the product of the
    invariant factors.  Taken on a basis rather than on the generators
    because there are as many generators as the net has independent
    cycles and only three of them can ever be independent.  In exact
    integers throughout: this is a question about a lattice, and a
    tolerance has no business in the answer.
    """
    basis = _row_basis(vectors)
    rank = len(basis)
    if rank == 0:
        return 1
    minors = [
        abs(_determinant([[row[c] for c in columns] for row in basis]))
        for columns in combinations(range(basis.shape[1]), rank)
    ]
    return math.gcd(*minors) or 1


def _row_basis(matrix: np.ndarray) -> np.ndarray:
    """A basis of the lattice the rows generate, in exact integers.

    Row echelon form reached by repeated Euclidean reduction.  Every
    step adds an integer multiple of one row to another, so the lattice
    at the end is the lattice at the start -- which is the property a
    floating-point rank reduction would not have.
    """
    if not len(matrix):
        return np.zeros((0, 3), dtype=object)
    a = np.array(matrix, dtype=object)
    rows, columns = a.shape
    top = 0
    for column in range(columns):
        while True:
            nonzero = sorted(
                (r for r in range(top, rows) if a[r, column]),
                key=lambda r: abs(a[r, column]))
            if len(nonzero) < 2:
                break
            pivot = nonzero[0]
            for other in nonzero[1:]:
                a[other] = (a[other]
                            - (a[other, column] // a[pivot, column])
                            * a[pivot])
        nonzero = [r for r in range(top, rows) if a[r, column]]
        if not nonzero:
            continue
        if nonzero[0] != top:
            a[[top, nonzero[0]]] = a[[nonzero[0], top]]
        top += 1
    return a[:top]


def _determinant(square) -> int:
    """An exact determinant of a 1, 2 or 3 square matrix of integers."""
    n = len(square)
    if n == 1:
        return int(square[0][0])
    if n == 2:
        return int(square[0][0] * square[1][1]
                   - square[0][1] * square[1][0])
    return int(
        square[0][0] * (square[1][1] * square[2][2]
                        - square[1][2] * square[2][1])
        - square[0][1] * (square[1][0] * square[2][2]
                          - square[1][2] * square[2][0])
        + square[0][2] * (square[1][0] * square[2][1]
                          - square[1][1] * square[2][0]))


# ======================================================================
#  THE MINIMAL QUOTIENT, AND THE CANONICAL KEY
# ======================================================================

def _incidence(n: int, edges) -> list[list[tuple]]:
    """Every vertex's edges, as ``(neighbour, image, edge)``.

    A self-loop appears twice, once each way round, because that is
    what it is in the net: a vertex joined to two of its own images,
    and a walk leaving along one of them is not the walk that leaves
    along the other.
    """
    out: list[list[tuple]] = [[] for _ in range(n)]
    for index, (i, j, image) in enumerate(edges):
        out[i].append((j, image, index))
        out[j].append((i, tuple(-v for v in image), index))
    return out


def _rank(values) -> tuple[int, ...]:
    order = {value: r for r, value in enumerate(sorted(set(values)))}
    return tuple(order[value] for value in values)


def _colours(n: int, incidence) -> tuple[int, ...]:
    """A stable colouring of the vertices, refined to a fixed point.

    Degree, then repeatedly degree-and-neighbours' colours, ranked so
    that the colour of a vertex is a number two *isomorphic* nets
    agree on -- which is what makes it usable both to prune the
    search below and to order it.  The images are deliberately not
    looked at: they depend on which cell the net was written in, and a
    colour that depends on the cell would make the key depend on it
    too.
    """
    colour = _rank([len(incidence[v]) for v in range(n)])
    while True:
        signature = [
            (colour[v], tuple(sorted(colour[j] for j, _m, _e
                                     in incidence[v])))
            for v in range(n)]
        refined = _rank(signature)
        if refined == colour:
            return colour
        colour = refined


def _in_basis(vector, basis) -> tuple[int, ...]:
    """``vector`` in terms of a row-echelon lattice basis, exactly.

    Integers throughout and integral or nothing: a vector that is not
    in the lattice is a bug in whatever built the basis, not a vector
    to round.
    """
    rest = [int(v) for v in vector]
    out = []
    for row in basis:
        pivot = next(c for c in range(len(row)) if row[c])
        multiple, remainder = divmod(int(rest[pivot]), int(row[pivot]))
        if remainder:
            raise TopologyError(
                f"{tuple(vector)} is not on the net's own lattice")
        out.append(multiple)
        rest = [rest[c] - multiple * int(row[c])
                for c in range(len(rest))]
    if any(rest):
        raise TopologyError(
            f"{tuple(vector)} is not on the net's own lattice")
    return tuple(out)


def _normalise(net: Net) -> tuple[int, tuple, int]:
    """A connected net as ``(vertices, edges, dimension)``.

    Two changes, both of which leave the periodic graph the same graph
    and both of which the key needs made before it starts:

    * **the gauge.**  A spanning tree fixes an offset per vertex and
      every image is taken relative to it, which is the same net
      described with each vertex's representative moved into the cell
      the tree reaches it in.  Every image is then a cycle voltage.
    * **the basis.**  Those voltages are re-expressed in a basis of the
      lattice *they* generate, so the images become ``d``-dimensional
      and generate the whole of ``Z^d``.  A net whose cycles close on
      every second cell -- two interpenetrating chains described in one
      cell -- is one chain here, which is what
      :meth:`Net.multiplicity` counts separately and what the name of
      the net has never included.
    """
    graph = net.graph()
    offset = {0: np.zeros(3, dtype=int)}
    queue = deque([0])
    while queue:
        a = queue.popleft()
        for b, translation in graph.neighbors_with_images(a):
            if b not in offset:
                offset[b] = offset[a] + translation
                queue.append(b)
    if len(offset) != net.n_vertices:
        raise TopologyError(
            "the quotient graph is not connected; identify each "
            "component in its own right")
    reduced = [(e.i, e.j,
                offset[e.i] + np.asarray(e.image, dtype=int)
                - offset[e.j]) for e in net.edges]
    basis = _row_basis(np.array([r[2] for r in reduced], dtype=object))
    edges = tuple((i, j, _in_basis(image, basis))
                  for i, j, image in reduced)
    return net.n_vertices, edges, len(basis)


# ======================================================================
#  WALKING THE NET
# ======================================================================
#
#  One traversal serves both halves of the answer.  Reducing the net to
#  its smallest cell means finding the walks that see exactly what the
#  walk from vertex 0 sees, because a walk that sees the same thing
#  *is* a translation of the net; writing the net down canonically
#  means walking it from every vertex in every frame and keeping the
#  smallest description any walk produces.  Both are the same code, and
#  the difference is only what the caller does with what comes back.

@dataclass(frozen=True)
class _Walk:
    """One traversal of the net, and everything it decided.

    ``structure`` is the shape of the numbering -- which vertex each
    edge reached, in the order the walk met them -- and is what the
    running minimum is compared on.  ``encounter`` is the edges in the
    same order with the cell each one closes into, which is what the
    key is made of and what says whether two walks saw the same net.
    """

    structure: tuple
    encounter: tuple
    number: tuple
    place: tuple

    def order(self) -> tuple:
        """The vertices, in the order the walk numbered them."""
        out = [0] * len(self.number)
        for vertex, index in enumerate(self.number):
            out[index] = vertex
        return tuple(out)


#: Past this many vertices, a placement that has to be solved in exact
#: fractions costs more than the answer is worth.
EXACT_PLACEMENT = 250


@lru_cache(maxsize=16)
def _placement(n: int, edges, d: int) -> tuple[tuple, int]:
    """Where the net sits when every vertex is at the mean of its
    neighbours, in whole numbers over one denominator.

    This is the one thing a walk cannot work out for itself.  Two
    vertices reached from the same place in the same cell are
    indistinguishable to a walk, and a net is full of them -- so
    without this the walk has to try both ways round at every such
    step, and the number of ways to walk a symmetric net that way is
    not a number worth counting.  The equilibrium placement separates
    them: it is decided by the connectivity alone, it is unique up to
    where the origin is put, and an isomorphism carries it to the
    other net's placement, so ordering two vertices by it is a
    statement about the net and not about the cell.

    Exactly, or not at all.  The rational solution is found in floating
    point and then *checked* in whole numbers, and anything that does
    not check out is solved again exactly -- a placement that is nearly
    right would order two vertices by rounding error and make the key
    depend on the arithmetic.
    """
    incidence = _incidence(n, edges)
    laplacian = np.zeros((n, n))
    right = np.zeros((n, d))
    for v in range(n):
        laplacian[v, v] = len(incidence[v])
        for u, image, _edge in incidence[v]:
            laplacian[v, u] -= 1
            right[v] += image
    laplacian[0] = 0.0
    laplacian[0, 0] = 1.0
    right[0] = 0.0
    try:
        floating = np.linalg.solve(laplacian, right)
    except np.linalg.LinAlgError:           # pragma: no cover
        raise TopologyError(
            "this net has no equilibrium placement") from None
    found = None
    for limit in (10_000, 10_000_000):
        found = [[Fraction(value).limit_denominator(limit)
                  for value in row] for row in floating]
        if _balanced(found, incidence, d):
            break
    else:
        # Nets this size have placements over denominators of a
        # thousand million, which no floating-point solution can be
        # read back to.  Slow and right beats fast and nearly -- but
        # exact elimination is cubic in fractions, so past a few
        # hundred vertices it is neither, and the net is left to its
        # invariants instead.
        if n > EXACT_PLACEMENT:
            raise TopologyError(
                f"a net of {n} vertices whose placement floating "
                "point cannot read back is too large to key")
        found = _exact_placement(n, incidence, d)
    scale = 1
    for row in found:
        for value in row:
            scale = scale * value.denominator // math.gcd(
                scale, value.denominator)
    return tuple(tuple(int(value * scale) for value in row)
                 for row in found), scale


def _balanced(placement, incidence, d: int) -> bool:
    """Is every vertex really at the mean of its neighbours?"""
    for v, edges_here in enumerate(incidence):
        for c in range(d):
            total = sum(placement[u][c] + image[c] - placement[v][c]
                        for u, image, _edge in edges_here)
            if total:
                return False
    return True


def _exact_placement(n: int, incidence, d: int) -> list[list[Fraction]]:
    """The equilibrium placement again, in exact fractions.

    Slower by a long way, and reached only when the floating-point
    solution did not check out -- a net with a nearly singular
    Laplacian, which is a real net and not a broken one.
    """
    rows = []
    for v in range(n):
        row = [Fraction(0)] * (n + d)
        if v:
            row[v] = Fraction(len(incidence[v]))
            for u, image, _edge in incidence[v]:
                row[u] -= 1
                for c in range(d):
                    row[n + c] += image[c]
        else:
            row[0] = Fraction(1)
        rows.append(row)
    for column in range(n):
        pivot = next((r for r in range(column, n) if rows[r][column]),
                     None)
        if pivot is None:
            raise TopologyError(
                "this net has no equilibrium placement")
        rows[column], rows[pivot] = rows[pivot], rows[column]
        lead = rows[column][column]
        rows[column] = [value / lead for value in rows[column]]
        for r in range(n):
            if r != column and rows[r][column]:
                factor = rows[r][column]
                rows[r] = [a - factor * b
                           for a, b in zip(rows[r], rows[column],
                                           strict=True)]
    return [row[n:] for row in rows]


def _rank_of(vectors, d: int) -> int:
    """How many of these integer vectors are independent."""
    rows = [list(v) for v in vectors]
    rank = 0
    for column in range(d):
        pivot = next((r for r in range(rank, len(rows))
                      if rows[r][column]), None)
        if pivot is None:
            continue
        rows[rank], rows[pivot] = rows[pivot], rows[rank]
        for r in range(rank + 1, len(rows)):
            if rows[r][column]:
                a, b = rows[rank][column], rows[r][column]
                rows[r] = [a * y - b * x
                           for x, y in zip(rows[rank], rows[r],
                                           strict=True)]
        rank += 1
    return rank


def _frame(vectors, d: int):
    """The matrix that reads a translation in these vectors' terms.

    The adjugate rather than the inverse, with the sign of the
    determinant: coordinates scaled by a positive number order the same
    way as coordinates themselves, and staying in whole numbers keeps
    the comparison exact.  ``None`` when the vectors are not a frame at
    all.
    """
    matrix = [list(v) for v in vectors]
    if not d:
        return []
    determinant = _determinant(matrix)
    if not determinant:
        return None
    sign = 1 if determinant > 0 else -1
    return [[sign * (-1) ** (i + j)
             * (_determinant([[matrix[r][c] for c in range(d) if c != i]
                              for r in range(d) if r != j])
                if d > 1 else 1)
             for j in range(d)] for i in range(d)]


def _frames(incidence, d: int, start: int, placement,
            scale: int) -> list[list]:
    """Every frame a walk from ``start`` may set out in.

    The frame is what orders the walk, so it has to be chosen by the
    net: ``d`` independent edges of the equilibrium placement, taken
    from the edges at ``start`` and, only if those do not span, from
    the shells around it until they do.  Which edges those are is a
    question about the net, so an isomorphism carries a frame to a
    frame -- and that is what makes the smallest description over all
    of them a property of the net rather than of the walk that found
    it.

    The vectors are the placement's and not the images', because an
    image is nothing on its own: half the edges of a net written in a
    conventional cell join two vertices of the same cell and have an
    image of zero, and a frame cannot be built out of zeroes.

    **Only the frames of smallest volume are kept.**  A change of basis
    leaves ``|det|`` alone, so choosing the smallest is a choice the
    net makes; and it is the difference between a hundred frames and
    several thousand.
    """
    if not d:
        return [[]]
    vectors: list[tuple] = []
    met: set[int] = set()
    seen = {start}
    frontier = [start]
    while _rank_of(vectors, d) < d:
        following = []
        for here in frontier:
            for there, image, edge in incidence[here]:
                if edge not in met:
                    met.add(edge)
                    step = tuple(placement[there][c] + scale * image[c]
                                 - placement[here][c] for c in range(d))
                    if any(step):
                        vectors.append(step)
                        vectors.append(tuple(-v for v in step))
                if there not in seen:
                    seen.add(there)
                    following.append(there)
        if not following and _rank_of(vectors, d) < d:
            raise TopologyError(
                "this net has no frame to be written down in")
        frontier = following
    found: dict[tuple, tuple] = {}
    for chosen in permutations(vectors, d):
        if chosen in found:
            continue
        matrix = _frame(chosen, d)
        if matrix is not None:
            found[chosen] = (abs(_determinant([list(v)
                                               for v in chosen])),
                             matrix)
    if not found:                           # pragma: no cover
        raise TopologyError(
            "this net has no frame to be written down in")
    smallest = min(volume for volume, _matrix in found.values())
    return [matrix for volume, matrix in found.values()
            if volume == smallest]


def _walks(n: int, edges, d: int, incidence, colours, start: int,
           matrix, placement, scale: int, bound=None,
           budget=None) -> list[_Walk]:
    """Traverse the net from ``start``, in the frame ``matrix``.

    Breadth-first, and at each vertex the edges are taken in the order
    that reaches the lowest-numbered vertex first and, among vertices
    not yet reached, the one the equilibrium placement puts first in
    this frame.  That settles every choice the walk has but one: two
    edges reaching vertices of the same colour standing in exactly the
    same place, which happens only where the placement folds two
    vertices onto one point.  That is a genuine tie and is taken both
    ways round, hence a list.

    ``bound`` is the structure of the best walk so far.  A walk that
    is already worse than it cannot become better, and is dropped where
    it goes wrong rather than at the end -- which is what keeps the
    minimum over every frame of every start vertex affordable.  The
    structure records where each step landed as well as which vertex it
    reached, so that walks which differ only in where they went differ
    in the first step where they do, rather than at the end of the net.
    """
    number = [-1] * n
    place: list[tuple | None] = [None] * n
    zero = (0,) * d
    number[start], place[start] = 0, zero
    order = [start]
    structure = [colours[start]]
    met: list[tuple | None] = [None] * len(edges)
    encounter: list[tuple] = []
    out: list[_Walk] = []
    settle: dict[int, list] = {}
    below = bound is None
    budget = [WALK_BUDGET] if budget is None else budget
    read: dict[tuple, tuple] = {}

    def coordinates(cell: tuple) -> tuple:
        """A cell of the net, in the frame's own terms."""
        if cell not in read:
            read[cell] = tuple(
                sum(cell[k] * matrix[k][c] for k in range(d))
                for c in range(d))
        return read[cell]

    #: Every vertex's own place, in the frame's terms and relative to
    #: where the walk began, to be added to the cell it is reached in.
    #: Relative because the structure is compared between walks that
    #: began in different places, and where a walk starts is not
    #: something the net has an opinion about.
    home = coordinates(placement[start])
    stands = [tuple(a - b for a, b in zip(coordinates(position), home,
                                          strict=True))
              for position in placement]

    def push(value: int) -> bool:
        """Extend the structure; ``False`` if the walk has lost."""
        nonlocal below
        structure.append(value)
        if below:
            return True
        depth = len(structure) - 1
        if depth >= len(bound):             # pragma: no cover
            return True
        if value > bound[depth]:
            return False
        if value < bound[depth]:
            below = True
        return True

    def vertex(p: int) -> None:
        if p == len(order):
            if len(encounter) != len(edges):
                raise TopologyError(          # pragma: no cover
                    f"a walk of this net saw {len(encounter)} of its "
                    f"{len(edges)} edges")
            out.append(_Walk(tuple(structure), tuple(encounter),
                             tuple(number), tuple(place)))
        else:
            leave(p, list(range(len(incidence[order[p]]))))
            settle.pop(p, None)             # a different vertex next time

    def leave(p: int, remaining: list[int]) -> None:
        nonlocal below
        budget[0] -= 1
        if budget[0] < 0:
            raise TopologyError(
                f"walking this net of {n} vertices did not finish; it "
                "is too large or too tangled to key")
        if not remaining:
            vertex(p + 1)
            return
        here = order[p]
        count = len(order)

        def settled(index: int) -> tuple:
            """Where this edge lands and what is standing there.

            Everything but the number, which is the only part of the
            comparison that changes as the walk numbers the vertices
            this vertex leads to -- so this half is worked out once
            for the whole of one vertex's edges rather than once per
            step, which is most of what a walk costs.
            """
            neighbour, image, _edge = incidence[here][index]
            cell = coordinates(tuple(place[here][c] + image[c]
                                     for c in range(d)))
            return (tuple(stands[neighbour][c] + scale * cell[c]
                          for c in range(d)), colours[neighbour])

        if p not in settle:
            settle[p] = [settled(index)
                         for index in range(len(incidence[here]))]
        fixed = settle[p]

        def token(index: int) -> tuple:
            neighbour = incidence[here][index][0]
            return ((number[neighbour] if number[neighbour] >= 0
                     else count),) + fixed[index]

        tokens = {index: token(index) for index in remaining}
        first = min(tokens.values())
        taken = set()
        for index in remaining:
            if tokens[index] != first:
                continue
            v, image, edge = incidence[here][index]
            if (v, image) in taken:         # the same step twice over
                continue
            taken.add((v, image))
            was, held, seen = below, len(structure), len(encounter)
            fresh = number[v] < 0
            if push(first[0]) and all(push(where)
                                      for where in first[1]):
                if fresh:
                    number[v] = count
                    place[v] = tuple(place[here][c] + image[c]
                                     for c in range(d))
                    order.append(v)
                if not fresh or push(colours[v]):
                    new = met[edge] is None
                    if new:
                        met[edge] = (number[here], number[v], tuple(
                            place[here][c] + image[c] - place[v][c]
                            for c in range(d)))
                        encounter.append(met[edge])
                    leave(p, [i for i in remaining if i != index])
                    if new:
                        met[edge] = None
                if fresh:
                    order.pop()
                    number[v], place[v] = -1, None
            del structure[held:]
            del encounter[seen:]
            below = was

    with _deep():
        vertex(0)
    return out


@contextmanager
def _deep():
    """Room to recurse: a walk is as deep as the net is long."""
    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(max(limit, WALK_DEPTH))
    try:
        yield
    finally:
        sys.setrecursionlimit(limit)


def _best_walk(n: int, edges, d: int, incidence, colours, start: int,
               matrix, placement, scale: int, bound=None,
               budget=None) -> _Walk | None:
    """The smallest description a walk from ``start`` produces."""
    found = _walks(n, edges, d, incidence, colours, start, matrix,
                   placement, scale, bound, budget)
    if not found:
        return None
    return min(found, key=lambda w: (w.structure, w.encounter))


# ======================================================================
#  THE MINIMAL QUOTIENT
# ======================================================================

def _translations(n: int, edges, d: int, incidence, colours,
                  allowance: int):
    """Every translation of the net the crystal's cell does not have.

    A translation is a permutation ``f`` of the vertices with a shift
    ``s`` on each, under which the edge ``(i, j, m)`` becomes
    ``(f(i), f(j), m + s(j) - s(i))``.  The shifts telescope around
    every cycle, so such a map leaves each cycle's translation exactly
    as it was: it is an automorphism of the net that leaves the lattice
    alone, which is what a translation is and is the only kind of
    automorphism that may be divided out.

    They are found by walking rather than by searching.  The walk is
    decided by what it sees -- colours, and where the frame puts each
    vertex -- and a translation preserves all of it, so a walk from
    ``w`` sees exactly what the walk from vertex 0 saw **if and only
    if** a translation carries one onto the other.  Two walks and a
    comparison, in place of a backtracking search that a symmetric net
    makes very expensive.  Each survivor is then confirmed against the
    edge list itself.
    """
    frame = [[1 if i == j else 0 for j in range(d)] for i in range(d)]
    placement, scale = _placement(n, edges, d)
    budget = [allowance]
    reference = _best_walk(n, edges, d, incidence, colours, 0, frame,
                           placement, scale, budget=budget)
    out = []
    for target in range(1, n):
        if colours[target] != colours[0]:
            continue
        walk = _best_walk(n, edges, d, incidence, colours, target,
                          frame, placement, scale,
                          reference.structure, budget)
        if walk is None or walk.structure != reference.structure \
                or walk.encounter != reference.encounter:
            continue
        image = [0] * n
        for mine, theirs in zip(reference.order(), walk.order(),
                                strict=True):
            image[mine] = theirs
        shift = tuple(
            tuple(walk.place[image[v]][c] - reference.place[v][c]
                  for c in range(d)) for v in range(n))
        candidate = (tuple(image), shift)
        if _free(candidate, d) and _preserves(edges, d, candidate):
            out.append(candidate)
    return _closed(out, n, d)


def _free(translation, d: int) -> bool:
    """Does this map move every vertex of the infinite net?

    A translation does.  What a walk finds is the wider thing -- an
    automorphism that leaves every cycle's translation alone -- and on
    a net where two vertices sit in exactly the same place those are
    not the same: RCSR's ``cys`` has one that swaps two vertices and
    fixes the other ten, which is a symmetry of the net and not a
    translation of it.  Dividing by it would be dividing by something
    that is not a lattice.
    """
    image, shift = translation
    zero = (0,) * d
    fixed = [v for v, onto in enumerate(image)
             if onto == v and shift[v] == zero]
    return not fixed or len(fixed) == len(image)


def _anchored(translation, n: int, d: int):
    """The same translation, written with vertex 0 left where it is.

    Two translations that differ by one of the cell's own are the same
    map of the quotient graph, and only one of them is worth holding:
    without this the composition below would go on generating the
    lattice for ever.
    """
    image, shift = translation
    return image, tuple(tuple(shift[v][c] - shift[0][c]
                              for c in range(d)) for v in range(n))


def _closed(found: list, n: int, d: int) -> list:
    """The group these translations generate, and not merely them.

    The search asks one question per vertex -- *is there a translation
    carrying vertex 0 onto this one* -- and takes the first answer.
    Where two translations carry 0 to the same place it sees one of
    them, and a set of translations that is not closed under
    composition would divide the net into orbits it cannot then
    describe.  Closing it costs a few products of permutations and
    removes the question.
    """
    identity = (tuple(range(n)), ((0,) * d,) * n)
    group = {identity: identity}
    frontier = list(found)
    while frontier:
        following = []
        for one in frontier:
            for other in [*found, identity]:
                product = _anchored(_compose(one, other, n, d), n, d)
                if product not in group:
                    if len(group) > n:
                        raise TopologyError(
                            "the translations of this net do not "
                            "close into a group")
                    group[product] = product
                    following.append(product)
        frontier = following
    return [t for t in group if t != identity]


def _preserves(edges, d: int, translation) -> bool:
    """Does this candidate really map the net onto itself?

    The walks that produced it agree on everything a walk looks at;
    this is the sweep that says the edge list itself is unchanged.
    Cheap, and the difference between a proof and a likeness.
    """
    image, shift = translation

    def moved(edge):
        i, j, m = edge
        return Edge(image[i], image[j],
                    tuple(m[c] + shift[j][c] - shift[i][c]
                          for c in range(d))).key()

    return (sorted(moved(e) for e in edges)
            == sorted(Edge(i, j, m).key() for i, j, m in edges))


def _compose(first, second, n: int, d: int):
    """``second`` after ``first``, as one translation."""
    fimage, fshift = first
    simage, sshift = second
    image = tuple(simage[fimage[v]] for v in range(n))
    shift = tuple(tuple(fshift[v][c] + sshift[fimage[v]][c]
                        for c in range(d)) for v in range(n))
    return image, shift


def _vector(translation, n: int, d: int, order: int) -> tuple[int, ...]:
    """The translation's own vector, multiplied by ``order``.

    A translation that is not one of the cell's own moves the vertices
    around, so its vector is written nowhere in the quotient graph.
    Repeat it, though, and after as many times as its order in the
    group it is a translation of the cell by a vector the graph does
    state -- and a third of that vector is what a translation of order
    three moves by.  Kept multiplied by the group's order, so that
    everything downstream stays in whole numbers.
    """
    identity = tuple(range(n))
    power, times = translation, 1
    while power[0] != identity:
        power = _compose(power, translation, n, d)
        times += 1
        if times > order:
            break
    shifts = set(power[1])
    if power[0] != identity or len(shifts) != 1 or order % times:
        raise TopologyError(
            "a translation of this net does not repeat into one of "
            "the cell's own")
    return tuple(v * (order // times) for v in shifts.pop())


def _minimise_once(n: int, edges, d: int, allowance: int):
    """Divide the net by every translation of it that was found."""
    incidence = _incidence(n, edges)
    colours = _colours(n, incidence)
    found = [(tuple(range(n)), ((0,) * d,) * n)]
    found.extend(_translations(n, edges, d, incidence, colours,
                               allowance))
    count = len(found)
    if count == 1:
        return n, edges

    home = list(range(n))                   # union-find over the orbits

    def root(v: int) -> int:
        while home[v] != v:
            home[v] = home[home[v]]
            v = home[v]
        return v

    for image, _shift in found:
        for v in range(n):
            a, b = root(v), root(image[v])
            if a != b:
                home[max(a, b)] = min(a, b)
    orbit: dict[int, list[int]] = {}
    for v in range(n):
        orbit.setdefault(root(v), []).append(v)
    if any(len(members) != count for members in orbit.values()):
        raise TopologyError(
            "the net's translations do not divide its vertices evenly")

    lattice = _row_basis(np.array(
        [_vector(t, n, d, count) for t in found]
        + [[count if c == k else 0 for c in range(d)]
           for k in range(d)], dtype=object))
    if len(lattice) != d:
        raise TopologyError("the reduced net lost a dimension")

    # Where each vertex sits relative to its orbit's representative,
    # in the same multiplied-up whole numbers as the lattice above.
    where: dict[int, tuple] = {}
    for representative, members in orbit.items():
        for v in members:
            for image, shift in found:
                if image[representative] == v:
                    where[v] = tuple(
                        a - count * b for a, b in zip(
                            _vector((image, shift), n, d, count),
                            shift[representative], strict=True))
                    break
            else:                           # pragma: no cover
                raise TopologyError(
                    "the net's translations do not reach every vertex "
                    "of their own orbits")

    number = {r: k for k, r in enumerate(sorted(orbit))}
    kept: dict[tuple, tuple] = {}
    for i, j, image in edges:
        moved = _in_basis(
            [where[j][c] + count * image[c] - where[i][c]
             for c in range(d)], lattice)
        edge = Edge(number[root(i)], number[root(j)], moved)
        kept[edge.key()] = (edge.i, edge.j, edge.image)
    if len(kept) * count != len(edges):
        raise TopologyError(
            f"reducing the net turned {len(edges)} edges into "
            f"{len(kept)} where {len(edges) // count} were due")
    return len(number), tuple(sorted(kept.values()))


def _minimal(net: Net, allowance: int) -> tuple[int, tuple, int]:
    """The smallest cell this net has, and the net in it.

    Repeated until a pass finds nothing, which costs one sweep that
    finds nothing and answers the question the reduction cannot answer
    about itself: a translation missed on the first pass would leave
    the net keyed in too large a cell, and that is a different net's
    answer rather than a slower one.
    """
    n, edges, d = _normalise(net)
    while True:
        smaller, fewer = _minimise_once(n, edges, d, allowance)
        if smaller == n:
            return n, edges, d
        n, edges, d = _normalise(Net(smaller, tuple(
            Edge(i, j, tuple(image) + (0,) * (3 - d))
            for i, j, image in fewer)))


# ======================================================================
#  THE KEY
# ======================================================================

def _hermite(rows, d: int) -> list[list[int]]:
    """A basis change putting these translations in Hermite form.

    The walk fixes which vertex is which and which cell each one sits
    in; what it cannot fix is the basis, because any change of basis in
    ``GL(d, Z)`` describes the same net.  Column reduction over the
    translations *in the order the walk met them* leaves one matrix out
    of that whole orbit and the same one every time, so the basis ends
    up chosen by the net rather than by the cell it arrived in.

    Returns the transform, to be applied to every image.
    """
    work = [list(row) for row in rows]
    transform = [[1 if i == j else 0 for j in range(d)]
                 for i in range(d)]

    def combine(target: int, source: int, times: int) -> None:
        for row in work:
            row[target] -= times * row[source]
        for row in transform:
            row[target] -= times * row[source]

    def swap(a: int, b: int) -> None:
        for row in work:
            row[a], row[b] = row[b], row[a]
        for row in transform:
            row[a], row[b] = row[b], row[a]

    pivot = 0
    for row in work:
        if pivot >= d:
            break
        while True:
            nonzero = sorted((c for c in range(pivot, d) if row[c]),
                             key=lambda c: abs(row[c]))
            if len(nonzero) < 2:
                break
            for other in nonzero[1:]:
                combine(other, nonzero[0],
                        row[other] // row[nonzero[0]])
        nonzero = [c for c in range(pivot, d) if row[c]]
        if not nonzero:
            continue
        if nonzero[0] != pivot:
            swap(pivot, nonzero[0])
        if row[pivot] < 0:
            combine(pivot, pivot, 2)        # negate the column
        for column in range(pivot):
            combine(column, pivot, row[column] // row[pivot])
        pivot += 1
    if pivot != d:
        raise TopologyError(
            "the net's own translations do not span its lattice")
    return transform


def _described(walk: _Walk, d: int) -> tuple:
    """One walk's description of the net, basis and all."""
    transform = _hermite([voltage for _a, _b, voltage
                          in walk.encounter], d)
    out = []
    for a, b, voltage in walk.encounter:
        moved = tuple(sum(voltage[k] * transform[k][c]
                          for k in range(d)) for c in range(d))
        if a > b:
            a, b, moved = b, a, tuple(-v for v in moved)
        elif a == b:
            moved = min(moved, tuple(-v for v in moved))
        out.append((a, b) + moved)
    out.sort()
    return walk.structure, tuple(out)


def _canonical(n: int, edges, d: int, allowance: int) -> str:
    """The net written down in the one way that does not depend on how
    it arrived.

    Every walk of :func:`_walks` describes the whole net; which
    description you get depends on where the walk started and in what
    frame, and on nothing else.  So the walk is made to start
    everywhere and in every frame, and the smallest description any of
    them gives is the key.  A minimum over an exhaustive search is a
    property of the net alone, which is what makes two equal keys a
    proof rather than a likeness -- and what makes "no catalogued net
    has this key" a fact.
    """
    if n + 2 * len(edges) + 8 > WALK_DEPTH:
        raise TopologyError(
            f"a net of {n} vertices and {len(edges)} edges is too "
            "large to key")
    incidence = _incidence(n, edges)
    colours = _colours(n, incidence)
    placement, scale = _placement(n, edges, d)
    lowest = min(colours)
    budget = [allowance]
    best = None
    for start in range(n):
        if colours[start] != lowest:
            continue
        for matrix in _frames(incidence, d, start,
                              placement, scale):
            for walk in _walks(n, edges, d, incidence, colours, start,
                               matrix, placement, scale,
                               best[0] if best else None, budget):
                candidate = _described(walk, d)
                if best is None or candidate < best:
                    best = candidate
    if best is None:
        raise TopologyError(
            "this net has no frame to be written down in")
    return f"{d}:{n}:" + ";".join(
        ",".join(str(v) for v in edge) for edge in best[1])
