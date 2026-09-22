"""
xtal.io.cgd
===========
CGD: a periodic net as a space group, some vertices and some edges.

It is Systre's input format and it is how the RCSR publishes its nets,
which is the only reason it is here: naming the net a user has drawn
means comparing it against
``resources/topo/RCSRnets-2019-06-01.cgd``.  Nothing in this module
builds a :class:`~xtal.core.structure.Structure` -- a net has no
elements and its coordinates are decoration -- so the format is
deliberately *not* registered in :data:`xtal.io.FORMATS`.  It reads to
:class:`CgdEntry`, which :mod:`xtal.analysis.rcsr` turns into a graph.

**The file is not as uniform as its first page**, and every quirk below
is one this reader met in the RCSR's own 2929 blocks rather than one it
was designed for in advance:

* **Two dialects.**  The common one names a node and then gives each
  edge as a *pair of points*::

      NODE 1 6  0.0 0.0 0.0
      EDGE  0.0 0.0 0.0   0.0 0.0 1.0

  A handful of blocks use Systre's other form, where an edge line is a
  single *neighbour position* belonging to the node above it::

      ATOM 1 4  0.0683 0.0683 0.0683
      EDGE 1    0.1144 0.0431 0.0000

  The two are told apart by counting numbers, which is why the nodes
  have to be read before the edges: with three-dimensional coordinates
  a pair is six numbers and a neighbour is four, and in two dimensions
  it is four and three.  Guessing from the count alone would read every
  2-periodic pair as a 3-periodic neighbour.

* **A keyword may stand alone** on its line with its rows beneath it
  (``atom`` then ``1 4 0.02 0.09 0.42``), and keywords appear in either
  case.

* **``CELL`` is optional and is never used.**  Four blocks have none,
  and the ones that do are read only to be ignored: the identity of a
  net is its connectivity, endpoints are matched in fractional
  coordinates modulo an integer translation, and a reader that requires
  a cell rejects four nets for a number it would not have looked at.
  The cell *is* kept, because its length says whether the entry is
  2- or 3-periodic when there are no nodes to count.

* **``# EDGE_CENTER`` lines are comments** and are the midpoints of the
  edges above them.  Stripping to the first ``#`` removes them, and
  that is all they are for here.

* **One block is simply incomplete.**  ``moo-a`` declares 22 atoms and
  no edges at all.  So a read collects its refusals rather than
  raising on the first one -- a file of 2929 nets that cannot be
  opened because one of them is broken is worse than 2928 nets and a
  sentence saying which one is missing and why.

**It writes as well, for Systre.**  The Net panel's name comes from a
canonical key that is checked against a supercell of itself and
against the catalogue this module reads, and neither of those is a
check made by anybody else.  :func:`entry_of` puts the drawn net into
one block and :func:`write_cgd` saves it, so that Systre -- the
reference implementation -- can be asked the same question.  Only the
common dialect is written, in ``GROUP P1`` over the expanded cell:
the space group would have to be spelled in a setting Systre agrees
with, and the whole point is to leave nothing of this application's
between the net and the second opinion.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from xtal.io.text import read_text

#: Every keyword a ``.cgd`` file uses.  A line starting with anything
#: else is a continuation row belonging to the keyword above it.
#:
#: ``edge_center`` is here to be *ignored*.  The RCSR file writes the
#: midpoints as ``# EDGE_CENTER`` comments, which are stripped before
#: this is consulted, but PORMAKE's topology database writes four of
#: its 2404 nets with the same word as a live keyword -- and without
#: it in this set those lines are read as rows belonging to the
#: ``NODE`` above them, which fails on a coordinate where a
#: coordination number was expected.  A midpoint says nothing a pair
#: of endpoints has not already said, so naming it is the whole fix.
_KEYWORDS = frozenset({"crystal", "end", "name", "group", "cell",
                       "node", "atom", "edge", "edge_center"})

Point = tuple[float, ...]


class CgdError(ValueError):
    """A block that cannot be read, named and located."""


@dataclass(frozen=True)
class CgdNode:
    """One vertex of the asymmetric unit, with the coordination number
    the file declares for it.

    The declared number is the reason to keep it: expanding the entry
    has to produce exactly that many edges at the vertex, and checking
    it is what makes a hand-written plane-group table safe to trust
    (see :mod:`xtal.analysis.rcsr`).
    """

    label: str
    coordination: int
    frac: Point


@dataclass(frozen=True)
class CgdEntry:
    """One ``CRYSTAL ... END`` block, read but not expanded."""

    name: str
    group: str
    nodes: tuple[CgdNode, ...]
    #: Each edge as the pair of points the file gives, both already
    #: resolved out of whichever dialect wrote them.
    edges: tuple[tuple[Point, Point], ...]
    cell: tuple[float, ...] | None = None
    line: int = 0

    @property
    def dimension(self) -> int:
        """2 or 3, from the coordinates rather than from the cell."""
        if self.nodes:
            return len(self.nodes[0].frac)
        return 2 if self.cell and len(self.cell) == 3 else 3


@dataclass(frozen=True)
class CgdFile:
    """What a ``.cgd`` file held: the nets, and what it got wrong.

    ``problems`` is part of the result and not an exception, for the
    reason the module docstring gives.  It is empty for a well-formed
    file, and a caller that wants to insist on one checks it.
    """

    entries: tuple[CgdEntry, ...]
    problems: tuple[str, ...] = ()

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self):
        return iter(self.entries)

    def __getitem__(self, name: str) -> CgdEntry:
        for entry in self.entries:
            if entry.name == name:
                return entry
        raise KeyError(name)


def read_cgd(path) -> CgdFile:
    """Every net in a ``.cgd`` file, in the order it appears."""
    return read_cgd_string(read_text(path))


def read_cgd_string(text: str) -> CgdFile:
    entries, problems = [], []
    for start, block in _blocks(text):
        try:
            entries.append(_entry(block, start))
        except CgdError as exc:
            problems.append(str(exc))
    return CgdFile(tuple(entries), tuple(problems))


def _blocks(text: str):
    """``(line number, [line, ...])`` for each ``CRYSTAL ... END``.

    Blank lines and everything from a ``#`` onwards are gone by the
    time a block is yielded, so no later step has to think about them.
    """
    start, current = 0, None
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#")[0].strip()
        if not line:
            continue
        head = line.split()[0].lower()
        if head == "crystal":
            start, current = number, []
        elif head == "end":
            if current is not None:
                yield start, current
            current = None
        elif current is not None:
            current.append(line)


def _entry(block: list[str], start: int) -> CgdEntry:
    name = group = ""
    cell: tuple[float, ...] | None = None
    nodes: list[CgdNode] = []
    #: An edge line, kept as its numbers until the dimension is known.
    raw_edges: list[list[float]] = []
    pending = ""

    for line in block:
        token = line.split()
        head = token[0].lower()
        if head in _KEYWORDS:
            pending = head
            rest = token[1:]
        else:
            rest = token                    # a row under a bare keyword
        if not rest:
            continue                        # the keyword stood alone

        if pending == "name":
            name = rest[0]
        elif pending == "group":
            group = rest[0]
        elif pending == "cell":
            cell = tuple(_numbers(rest, line, start))
        elif pending in ("node", "atom"):
            values = _numbers(rest[2:], line, start)
            if not values:
                raise CgdError(
                    f"line {start}: node with no coordinates: {line!r}")
            nodes.append(CgdNode(rest[0], int(rest[1]), tuple(values)))
        elif pending == "edge":
            raw_edges.append(_numbers(rest, line, start))

    if not name:
        raise CgdError(f"line {start}: a block with no NAME")
    dimension = (len(nodes[0].frac) if nodes
                 else 2 if cell and len(cell) == 3 else 3)
    entry = CgdEntry(name, group or "P1", tuple(nodes),
                     tuple(_edges(raw_edges, nodes, dimension,
                                  name, start)),
                     cell, start)
    if not entry.edges:
        raise CgdError(f"line {start}: {name} has no edges")
    return entry


def _numbers(tokens, line: str, start: int) -> list[float]:
    try:
        return [float(t) for t in tokens]
    except ValueError:
        raise CgdError(
            f"line {start}: not a number in {line!r}") from None


def _edges(raw, nodes, dimension: int, name: str, start: int):
    """Resolve both dialects into pairs of points.

    The count decides: ``2 * dimension`` numbers is a pair of points,
    ``dimension + 1`` is a node index followed by one neighbour
    position.  Nothing else is a line this reader understands, and
    saying so is better than silently dropping an edge -- a net with an
    edge missing is a different net, and it would be named as one.
    """
    by_label = {node.label: node for node in nodes}
    for values in raw:
        if len(values) == 2 * dimension:
            yield (tuple(values[:dimension]), tuple(values[dimension:]))
        elif len(values) == dimension + 1:
            label = _label(values[0])
            if label not in by_label:
                raise CgdError(
                    f"line {start}: {name} has an edge at node "
                    f"{label}, which it never declares")
            yield (by_label[label].frac, tuple(values[1:]))
        else:
            raise CgdError(
                f"line {start}: {name} has an edge of {len(values)} "
                f"numbers, which is neither a pair of "
                f"{dimension}D points nor a node and a neighbour")


def _label(value: float) -> str:
    """A node index read as a float, back to the text the node used."""
    return str(int(value))


# ======================================================================
#  WRITING
# ======================================================================

#: Decimal places a coordinate is written to.  Six is a thousand times
#: finer than any tolerance an endpoint is matched to a node at, so an
#: edge written here lands on the node it came from in every reader.
PLACES = 6


def write_cgd(path, entries) -> Path:
    """Write ``entries`` to ``path`` as ``.cgd``; returns the path."""
    path = Path(path)
    path.write_text(write_cgd_string(entries), encoding="utf-8")
    return path


def write_cgd_string(entries) -> str:
    """The text of a ``.cgd`` file holding ``entries``, in order."""
    return "".join(_block(entry) for entry in entries)


def _block(entry: CgdEntry) -> str:
    if not entry.name or any(c.isspace() for c in entry.name):
        # A name is one token to every reader, this one included, and
        # a space would silently cut it short on the way back in.
        raise CgdError(f"cannot write a net named {entry.name!r}")
    lines = ["CRYSTAL", f"  NAME {entry.name}",
             f"  GROUP {entry.group or 'P1'}"]
    if entry.cell:
        lines.append("  CELL " + " ".join(f"{v:.{PLACES}f}"
                                          for v in entry.cell))
    for node in entry.nodes:
        lines.append(f"  NODE {node.label} {node.coordination} "
                     f"{_point(node.frac)}")
    for first, second in entry.edges:
        lines.append(f"  EDGE {_point(first)}   {_point(second)}")
    lines.append("END")
    return "\n".join(lines) + "\n\n"


def _point(values) -> str:
    # ``+ 0.0`` so that a coordinate rounding to zero from below is not
    # written as ``-0.000000``, which is correct and looks like a bug.
    return " ".join(f"{round(float(v), PLACES) + 0.0:.{PLACES}f}"
                    for v in values)


def entry_of(structure, name: str | None = None) -> CgdEntry:
    """The net drawn on ``structure``, as one block Systre can read.

    Every vertex of the expanded cell is a node and every edge a pair
    of points, in P1 -- the net exactly as :func:`~xtal.analysis.
    topology.net_of` sees it, and nothing a reader has to take on
    trust.  A node's coordination is counted from the edges written,
    ends and not neighbours, so an edge from a vertex to its own image
    counts twice at it: that is what a reader expanding the file finds
    there, and a declared number it does not find is a refusal.

    Raises :class:`CgdError` when there is nothing to write, or when
    two vertices sit so close that an endpoint could be matched to
    either -- the format finds an edge's ends *by position*, and a
    file that joins the wrong one describes a different net.
    """
    from xtal.analysis.rcsr import TOLERANCE
    from xtal.core import bonding, p1

    cell = p1.expand(structure)
    bonds = bonding.topology_graph(structure).bonds
    if not bonds:
        raise CgdError("no net has been drawn")
    vertices = sorted({b.i for b in bonds} | {b.j for b in bonds})
    ends = dict.fromkeys(vertices, 0)
    for bond in bonds:
        ends[bond.i] += 1
        ends[bond.j] += 1
    number = {v: str(k) for k, v in enumerate(vertices, start=1)}
    _refuse_coincident(cell, vertices, TOLERANCE)

    nodes = tuple(CgdNode(number[v], ends[v],
                          tuple(float(x) for x in cell.frac[v]))
                  for v in vertices)
    edges = tuple((tuple(float(x) for x in cell.frac[b.i]),
                   tuple(float(x) + t for x, t in
                         zip(cell.frac[b.j], b.image, strict=True)))
                  for b in bonds)
    title = name or str(structure.meta.get("title") or "net")
    return CgdEntry("_".join(title.split()) or "net", "P1", nodes,
                    edges, tuple(structure.lattice.parameters))


def _refuse_coincident(cell, vertices, tolerance: float) -> None:
    import numpy as np

    points = np.asarray(cell.frac[vertices], dtype=float)
    for k in range(1, len(points)):
        delta = points[:k] - points[k]
        delta -= np.round(delta)
        close = np.flatnonzero(np.linalg.norm(delta, axis=1)
                               < tolerance)
        if len(close):
            other = vertices[int(close[0])]
            raise CgdError(
                f"{cell.labels[other] or cell.elements[other]} and "
                f"{cell.labels[vertices[k]] or cell.elements[vertices[k]]}"
                f" are net vertices in the same place, and a .cgd file "
                f"finds an edge's ends by position")
