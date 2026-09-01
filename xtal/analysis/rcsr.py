"""
xtal.analysis.rcsr
==================
The RCSR, expanded, and the net you drew looked up in it.

:mod:`xtal.analysis.topology` knows what a net is; this knows what the
nets are *called*.  Given the periodic graph of a drawn net it answers
with **pcu**, or with the two names it cannot yet tell apart, or with
the honest statement that nothing in the catalogue has these
invariants -- which for a genuinely new net is a result and not a
failure.

**The lookup has two layers, and they are computed independently.**

The first is the invariants: the coordination sequence to ten terms and
the Schlafli point symbol, taken over the distinct vertices, which name
2665 of the 2679 3-periodic RCSR nets uniquely.  Both are computed on
the *infinite* net, so neither changes when the same net is described
in a larger cell, and that is what lets MOF-5's eight-vertex **pcu** be
recognised against RCSR's one-vertex one.  It is a filter with a
measured 99.5% hit rate: **sxd** and **vng** share both invariants and
are not the same net.

The second is the canonical key of
:meth:`xtal.analysis.topology.Net.key` -- the net reduced to the
smallest cell it has and written down the one way that does not depend
on how it arrived.  Equal keys mean the same net and unequal keys mean
different nets, so this layer *decides*: it separates the fourteen
names the invariants cannot, and it turns "no catalogued net has these
invariants" into "no catalogued net is this net".

Neither layer is allowed to hide the other.  A net whose key matches
nothing while its invariants match **pcu** is reported as what it is --
not in the RCSR, and looking very like **pcu** -- because a
disagreement between two independent calculations is the most
interesting thing on the page and not something to resolve quietly.
And a net too large to key is named by its invariants exactly as it was
before there was a key, which is why every entry here keeps both.

**The coordination sequence alone is not enough**, and the commonest
net in the field is the proof: **pcu** shares 6, 18, 38, 66, 102, 146
with **tfs**, **smd**, **sxd** and **vng**, and it is the point symbol
that separates them.

**Expanding the file is a build step, not a startup cost.**  It takes
the better part of an hour with the keys, so it is done once by
``python -m xtal.analysis.rcsr build`` and the result is the small
JSON in ``data/`` that ships with the package.  That build is also
where the canonicalisation is checked: a key that is self-consistent
but not canonical gives two descriptions of one net two different
strings, and across 2929 nets it collides names in bulk.  The build
counts the collisions and the suite fails on any.

Two things make that build trustworthy.  Every ``NODE`` in the file
declares its own coordination number, so the expansion is checked
against the file's own arithmetic -- **all 2679 3-periodic entries
agree, none disagree** -- and that is what makes the hand-written
plane-group table below safe: get ``p3m1`` and ``p31m`` the wrong way
round and fourteen entries stop matching.  And every edge endpoint has
to land on a node orbit, which is what caught the one entry (``thz``)
whose space-group symbol omits the origin choice it was written in.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from functools import cached_property, lru_cache
from pathlib import Path

import gemmi
import numpy as np

from xtal.analysis.topology import (
    DEPTH,
    MAX_RING,
    Edge,
    Fingerprint,
    Net,
    TopologyError,
)
from xtal.io.cgd import CgdEntry, CgdError, read_cgd

#: The catalogue that ships with the package.
DATA = Path(__file__).resolve().parent / "data"
INDEX = DATA / "rcsr-2019-06-01.json.gz"

#: The file it is built from, on a source checkout.
SOURCE = ("resources", "topo", "RCSRnets-2019-06-01.cgd")

#: Fractional distance within which two points are the same vertex.
#: The file's coordinates run to five decimals and its symmetry images
#: to rather fewer -- ``thz`` writes one endpoint 1e-4 away from where
#: its own operation puts it -- so the tolerance is loose enough to
#: absorb that and far tighter than any two distinct vertices.
TOLERANCE = 2e-3
_GRID = 1000            # the hash TOLERANCE is probed against


class RcsrError(ValueError):
    """An entry that cannot be turned into a net, named."""


# ======================================================================
#  PLANE GROUPS
# ======================================================================

#: The 17 plane groups, as generators in the notation of the
#: International Tables.  gemmi has no two-dimensional groups and the
#: 200 layer nets in the RCSR file are written in them, so they are
#: here.
#:
#: Embedding them in three-dimensional space groups instead is a trap
#: worth naming: it works for most of them and then ``pg`` needs a
#: non-standard setting, which is exactly where the mapping stops being
#: checkable by eye.  A table of generators is longer and is right.
PLANE_GROUPS: dict[str, tuple[str, ...]] = {
    "p1": (),
    "p2": ("-x,-y",),
    "pm": ("-x,y",),
    "pg": ("-x,y+1/2",),
    "cm": ("-x,y", "x+1/2,y+1/2"),
    "p2mm": ("-x,-y", "-x,y"),
    "p2mg": ("-x,-y", "-x+1/2,y"),
    "p2gg": ("-x,-y", "-x+1/2,y+1/2"),
    "c2mm": ("-x,-y", "-x,y", "x+1/2,y+1/2"),
    "p4": ("-y,x",),
    "p4mm": ("-y,x", "-x,y"),
    "p4gm": ("-y,x", "-x+1/2,y+1/2"),
    "p3": ("-y,x-y",),
    "p3m1": ("-y,x-y", "-y,-x"),
    "p31m": ("-y,x-y", "y,x"),
    "p6": ("-y,x-y", "-x,-y"),
    "p6mm": ("-y,x-y", "-x,-y", "-y,-x"),
}

#: Spellings the RCSR file uses for the groups above.
_PLANE_ALIASES = {"pmm": "p2mm", "pmg": "p2mg", "pgg": "p2gg",
                  "cmm": "c2mm", "p4m": "p4mm", "p4g": "p4gm",
                  "p6m": "p6mm", "p2mm": "p2mm"}


def _triplet(text: str) -> tuple[np.ndarray, np.ndarray]:
    """``"-y,x-y+1/2"`` to a rotation and a translation."""
    parts = text.split(",")
    rot = np.zeros((len(parts), len(parts)))
    trans = np.zeros(len(parts))
    for row, part in enumerate(parts):
        for token in part.replace("-", "+-").split("+"):
            token = token.strip()
            if not token:
                continue
            sign = -1.0 if token.startswith("-") else 1.0
            body = token.lstrip("-")
            if body in ("x", "y", "z"):
                rot[row, "xyz".index(body)] += sign
            elif "/" in body:
                numerator, denominator = body.split("/")
                trans[row] += sign * float(numerator) / float(denominator)
            else:
                trans[row] += sign * float(body)
    return rot, trans


def plane_group_operations(symbol: str) -> list[tuple]:
    """Every operation of a plane group, from its generators.

    Closed by repeated composition rather than listed, so the table
    above stays short enough to check against the International Tables
    line by line -- which is the only way it gets to be right.
    """
    key = symbol.strip().lower()
    key = _PLANE_ALIASES.get(key, key)
    if key not in PLANE_GROUPS:
        raise RcsrError(f"unknown plane group {symbol!r}")
    identity = (np.eye(2), np.zeros(2))
    found = {_signature(identity): identity}
    generators = [_triplet(t) for t in PLANE_GROUPS[key]]
    frontier = list(found.values())
    while frontier:
        nxt = []
        for rot, trans in frontier:
            for grot, gtrans in generators:
                new = (grot @ rot, np.mod(grot @ trans + gtrans, 1.0))
                if _signature(new) not in found:
                    found[_signature(new)] = new
                    nxt.append(new)
        frontier = nxt
    return list(found.values())


def _signature(operation) -> tuple:
    rot, trans = operation
    return (tuple(np.round(rot).astype(int).ravel()),
            tuple(np.round(np.mod(trans, 1.0) * 24).astype(int) % 24))


@lru_cache(maxsize=512)
def _space_group_operations(symbol: str) -> tuple:
    group = gemmi.SpaceGroup(symbol)
    den = float(gemmi.Op.DEN)
    return tuple((np.array(op.rot) / den,
                  np.mod(np.array(op.tran) / den, 1.0))
                 for op in group.operations())


def operations(entry: CgdEntry) -> list[tuple]:
    """The symmetry operations an entry is written in."""
    if entry.dimension == 2:
        return plane_group_operations(entry.group)
    try:
        return list(_space_group_operations(entry.group))
    except (RuntimeError, ValueError):
        raise RcsrError(
            f"{entry.name}: no space group {entry.group!r}") from None


# ======================================================================
#  EXPANDING AN ENTRY
# ======================================================================

def expand(entry: CgdEntry) -> Net:
    """One RCSR entry as the periodic graph it describes.

    The space group is applied to the nodes to get the vertices of the
    cell and to the edges to get the edges, and each edge endpoint is
    then located among the vertices modulo a lattice translation --
    which is where the ``image`` on the edge comes from and is why no
    cell parameters are needed to do any of this.

    **A symbol with an unstated origin choice is retried, not
    guessed.**  ``thz`` is written ``I41/amd`` and is in the second
    setting, and in the first one its edges point at nothing.  Because
    an endpoint that lands on no vertex is a hard failure rather than a
    silent one, trying the other setting and keeping whichever resolves
    every endpoint is safe: a wrong setting cannot pass this test.
    """
    problems = []
    for symbol in _settings(entry):
        try:
            return _expand_with(entry, symbol)
        except RcsrError as exc:
            problems.append(str(exc))
    raise RcsrError(problems[0])


def _settings(entry: CgdEntry) -> list[str]:
    if entry.dimension == 2 or ":" in entry.group:
        return [entry.group]
    return [entry.group, f"{entry.group}:2", f"{entry.group}:1"]


def _expand_with(entry: CgdEntry, symbol: str) -> Net:
    ops = (plane_group_operations(symbol) if entry.dimension == 2
           else list(_space_group_operations(symbol)))
    sites = _Sites(entry.dimension)
    origin: list[int] = []
    for index, node in enumerate(entry.nodes):
        point = np.asarray(node.frac, dtype=float)
        for rot, trans in ops:
            if sites.add(rot @ point + trans):
                origin.append(index)

    edges: dict[tuple, Edge] = {}
    for first, second in entry.edges:
        a = np.asarray(first, dtype=float)
        b = np.asarray(second, dtype=float)
        for rot, trans in ops:
            i, shift_a = sites.locate(rot @ a + trans, entry)
            j, shift_b = sites.locate(rot @ b + trans, entry)
            image = tuple(int(v) for v in _pad(shift_b - shift_a))
            edge = Edge(i, j, image)
            edges[edge.key()] = edge

    net = Net(sites.count,
              tuple(sorted(edges.values(), key=lambda e: e.key())),
              tuple(entry.nodes[node].label for node in origin),
              tuple(origin))
    _check_coordination(net, entry, origin, symbol)
    return net


def _pad(vector: np.ndarray) -> np.ndarray:
    """A two-dimensional image, as the three-dimensional one it is.

    Every net in this application carries three-dimensional images so
    that a layer read out of RCSR and a layer drawn in a crystal are
    the same kind of object -- see :mod:`xtal.analysis.topology`.
    """
    if len(vector) == 3:
        return vector
    return np.array([vector[0], vector[1], 0])


def _check_coordination(net: Net, entry: CgdEntry, origin, symbol):
    """Every vertex must have the degree its node declared.

    This is the file checking the expansion rather than the expansion
    trusting the file, and it is the whole reason the plane-group table
    above can be hand-written: an operation that is wrong produces a
    vertex with the wrong number of edges, here, at build time.
    """
    for vertex, node in enumerate(origin):
        want = entry.nodes[node].coordination
        got = net.degree(vertex)
        if got != want:
            raise RcsrError(
                f"{entry.name} in {symbol}: vertex {vertex} of node "
                f"{entry.nodes[node].label} has {got} edges and the "
                f"file declares {want}")


class _Sites:
    """The vertices of one cell, found by position.

    A dictionary on coordinates rounded to a thousandth, probed over
    the neighbouring cells of that grid so that two points either side
    of a rounding boundary still meet.  Every candidate is then checked
    against :data:`TOLERANCE` properly, so the grid is an index and
    never the answer.
    """

    def __init__(self, dimension: int):
        self.dimension = dimension
        self.frac: list[np.ndarray] = []
        self._index: dict[tuple, list[int]] = {}
        self._offsets = _neighbourhood(dimension)

    @property
    def count(self) -> int:
        return len(self.frac)

    def add(self, point) -> bool:
        """Record a vertex; ``False`` if it was already there."""
        wrapped = np.mod(np.asarray(point, dtype=float), 1.0)
        if self._search(wrapped) is not None:
            return False
        self.frac.append(wrapped)
        self._index.setdefault(_cell(wrapped), []).append(
            len(self.frac) - 1)
        return True

    def locate(self, point, entry) -> tuple[int, np.ndarray]:
        """Which vertex this is, and how many cells away."""
        raw = np.asarray(point, dtype=float)
        wrapped = np.mod(raw, 1.0)
        found = self._search(wrapped)
        if found is None:
            raise RcsrError(
                f"{entry.name}: the edge endpoint "
                f"{np.round(raw, 5).tolist()} is not on any vertex")
        return found, np.round(raw - self.frac[found])

    def _search(self, wrapped) -> int | None:
        base = _cell(wrapped)
        best, distance = None, TOLERANCE
        for offset in self._offsets:
            key = tuple((b + o) % _GRID
                        for b, o in zip(base, offset, strict=True))
            for candidate in self._index.get(key, ()):
                delta = wrapped - self.frac[candidate]
                delta -= np.round(delta)
                length = float(np.linalg.norm(delta))
                if length < distance:
                    best, distance = candidate, length
        return best


def _cell(wrapped) -> tuple:
    return tuple(int(v) % _GRID
                 for v in np.round(np.asarray(wrapped) * _GRID))


def _neighbourhood(dimension: int) -> list[tuple]:
    out = [()]
    for _ in range(dimension):
        out = [row + (step,) for row in out for step in (-1, 0, 1)]
    return out


# ======================================================================
#  THE CATALOGUE
# ======================================================================

@dataclass(frozen=True)
class CatalogueEntry:
    """One named net, as the index holds it."""

    name: str
    periodicity: int
    sequences: tuple[tuple[int, ...], ...]
    symbols: tuple[str, ...]
    group: str
    vertices: int
    edges: int
    #: The canonical form of the net, from
    #: :meth:`xtal.analysis.topology.Net.key`.  Empty for the handful
    #: of entries too large to key, and the catalogue says so rather
    #: than treating their absence as a net nobody matches.
    key: str = ""

    def fingerprint(self) -> Fingerprint:
        return Fingerprint(self.periodicity, self.sequences,
                           self.symbols)

    def coordination(self) -> tuple[int, ...]:
        return self.fingerprint().coordination()

    def to_row(self) -> list:
        return [self.name, self.periodicity,
                [list(s) for s in self.sequences], list(self.symbols),
                self.group, self.vertices, self.edges, self.key]

    @classmethod
    def from_row(cls, row) -> CatalogueEntry:
        name, periodicity, sequences, symbols, group, nv, ne = row[:7]
        return cls(name, int(periodicity),
                   tuple(tuple(s) for s in sequences), tuple(symbols),
                   group, int(nv), int(ne),
                   str(row[7]) if len(row) > 7 else "")


@dataclass(frozen=True)
class Catalogue:
    """Every net RCSR names, indexed by what identifies it."""

    entries: tuple[CatalogueEntry, ...]
    source: str = ""
    refused: tuple[tuple[str, str], ...] = ()

    def __len__(self) -> int:
        return len(self.entries)

    @cached_property
    def by_token(self) -> dict[str, tuple[str, ...]]:
        out: dict[str, list[str]] = {}
        for entry in self.entries:
            out.setdefault(entry.fingerprint().token(), []).append(
                entry.name)
        return {k: tuple(v) for k, v in out.items()}

    @cached_property
    def by_key(self) -> dict[str, tuple[str, ...]]:
        """The canonical forms, and what each one is called.

        One name each, or the index build is broken: two different
        nets with one key is what a canonicalisation that is
        self-consistent but not canonical produces, and it produces it
        in bulk.  The build says how many it found and the suite fails
        on any.
        """
        out: dict[str, list[str]] = {}
        for entry in self.entries:
            if entry.key:
                out.setdefault(entry.key, []).append(entry.name)
        return {k: tuple(v) for k, v in out.items()}

    @cached_property
    def keyed(self) -> bool:
        """Whether there are canonical forms here to compare against."""
        return any(entry.key for entry in self.entries)

    @cached_property
    def unkeyed(self) -> tuple[str, ...]:
        """The nets here that have no canonical form of their own.

        A handful of the RCSR's augmented nets are too large to key,
        and they are what a key that matches nothing has to be honest
        about: everything else has been ruled out, and these have only
        been compared by their invariants.  Naming the number is the
        difference between "no catalogued net is this net" and "no
        catalogued net that could be keyed is this net".
        """
        return tuple(entry.name for entry in self.entries
                     if entry.periodicity >= 2 and not entry.key)

    def lookup(self, fingerprint: Fingerprint) -> tuple[str, ...]:
        return self.by_token.get(fingerprint.token(), ())

    def lookup_key(self, key: str) -> tuple[str, ...]:
        return self.by_key.get(key, ()) if key else ()

    def nearest(self, fingerprint: Fingerprint,
                limit: int = 5) -> tuple[str, tuple[str, ...]]:
        """Names worth looking at when nothing matched, and on what
        grounds.

        Anything with the same coordination sequences first -- a net
        that walks like this one and rings differently is the near miss
        worth naming -- then anything merely as coordinated.  Which
        rule fired is returned with the names, because "these walk the
        same way" and "these have the same coordination number" are
        very different claims and reporting the second as the first
        would overstate the match.
        """
        close = [e.name for e in self.entries
                 if e.sequences == fingerprint.sequences]
        if close:
            return "coordination sequence", tuple(close[:limit])
        want = fingerprint.coordination()
        close = [e.name for e in self.entries
                 if e.periodicity == fingerprint.periodicity
                 and e.coordination() == want]
        return ("coordination number" if close else "",
                tuple(close[:limit]))

    def __getitem__(self, name: str) -> CatalogueEntry:
        for entry in self.entries:
            if entry.name == name:
                return entry
        raise KeyError(name)


# ======================================================================
#  NAMING ONE
# ======================================================================

@dataclass(frozen=True)
class Identification:
    """What one connected net is, and how sure that is."""

    fingerprint: Fingerprint
    #: Every catalogue net with these invariants.  One name is an
    #: answer, two are the truth, none is a result of its own.
    names: tuple[str, ...] = ()
    #: Where to look when nothing matched, and what they have in
    #: common with it.
    nearest: tuple[str, ...] = ()
    nearest_by: str = ""
    #: Names whose invariants match although the canonical form says
    #: they are other nets.  Only the key can produce this, and
    #: printing it is how a disagreement between the two layers
    #: reaches the reader instead of being decided behind their back.
    looks_like: tuple[str, ...] = ()
    #: How many independent copies of this net the crystal holds --
    #: see :meth:`xtal.analysis.topology.Net.multiplicity`.
    multiplicity: int = 1
    #: This net's canonical form, or empty where it could not be
    #: computed.  See :meth:`xtal.analysis.topology.Net.key`.
    key: str = ""
    #: Whether the key is what settled it.  A key that matches names
    #: the net; a key that matches nothing rules the catalogue out --
    #: all of it that could be keyed, which :attr:`unkeyed` is what
    #: says.  Both are decisions, and everything else on this class is
    #: a filter.
    decided: bool = False
    #: What the key could *not* rule out: how many catalogued nets had
    #: no canonical form of their own to be compared with.  Empty when
    #: every one of them did, which is what makes "not in the RCSR" a
    #: statement about the RCSR rather than about this index.
    unkeyed: str = ""
    #: Whether there was a catalogue to look in at all.  A package
    #: installed without its data file, or a checkout before the index
    #: has been built, must not be reported as a net nobody has seen
    #: before -- the invariants are still right and are still worth
    #: showing, and only the name is missing.
    catalogued: bool = True

    @property
    def verdict(self) -> str:
        if len(self.names) == 1:
            return "named"
        if self.names:
            return "ambiguous"
        if not self.catalogued:
            return "not looked up"
        if self.fingerprint.periodicity < 2:
            return "uncatalogued"
        return "unknown"

    @property
    def name(self) -> str:
        return self.names[0] if len(self.names) == 1 else ""

    def headline(self) -> str:
        """What to call it, in as few words as are true."""
        if self.verdict == "named":
            return self.names[0]
        if self.verdict == "ambiguous":
            return " or ".join(self.names)
        if self.verdict == "uncatalogued":
            return "not catalogued"
        if self.verdict == "not looked up":
            return "not looked up"
        return "not in the RCSR"

    def shape(self) -> str:
        return _shape(self.fingerprint, self.multiplicity)

    def caveat(self) -> str:
        """Why the headline is not a single name, or is not certain."""
        if self.verdict == "named" and not self.decided:
            # The invariants name 99.5% of the RCSR correctly and are
            # still a filter: they recognise a net rather than proving
            # it, and where the key did not run, saying so is the
            # difference between a match and a proof.
            if not self.key:
                return ("named by its invariants; this net is too "
                        "large to key, so nothing has proved it")
            return ("named by its invariants; this index holds no "
                    "canonical forms to prove it against, so rebuild "
                    "it with: python -m xtal.analysis.rcsr build")
        if self.verdict == "ambiguous":
            if not self.key:
                return ("these nets share both invariants, and this "
                        "net is too large to tell them apart by its "
                        "canonical form")
            return ("these nets share both invariants; the index was "
                    "built without canonical forms, so rebuild it "
                    "with: python -m xtal.analysis.rcsr build")
        if self.verdict == "uncatalogued":
            return ("the RCSR net file holds only 2- and 3-periodic "
                    "nets, so there is no name to look up")
        if self.verdict == "not looked up":
            return ("there is no RCSR index to look in; rebuild it "
                    "with: python -m xtal.analysis.rcsr build")
        if self.verdict == "unknown":
            near = (f"nearest by {self.nearest_by}: "
                    + ", ".join(self.nearest) if self.nearest else
                    "no catalogued net is even as coordinated as this")
            if not self.decided:
                return near
            # The key is a proof, so this is the one place the report
            # gets to say *not* rather than *not found* -- and the one
            # place the two layers can contradict each other, which is
            # worth printing rather than quietly resolving.
            if self.looks_like:
                return (f"no catalogued net has this net's canonical "
                        f"form; {', '.join(self.looks_like)} share its "
                        f"invariants and are other nets"
                        + self.unkeyed)
            return (f"no catalogued net has this net's canonical form"
                    f"; {near}" + self.unkeyed)
        return ""

    def invariant_lines(self) -> list[str]:
        """The numbers themselves, a block per kind of vertex."""
        out = []
        symbols = _padded(self.fingerprint)
        many = len(self.fingerprint.sequences) > 1
        for index, sequence in enumerate(self.fingerprint.sequences):
            if many:
                out.append(f"{sequence[0]}-coordinated vertex")
            walk = ", ".join(str(n) for n in sequence)
            out.append(f"coordination sequence  {walk}")
            if symbols[index]:
                out.append(f"point symbol           {symbols[index]}")
        if not many and self.fingerprint.symbols and not symbols[0]:
            out.append("point symbol           "
                       + ", ".join(self.fingerprint.symbols))
        return out

    def sentence(self) -> str:
        """One line: what this net is, invariants included."""
        head = f"{self.headline()} -- {self.shape()}"
        rest = "; ".join(" ".join(line.split())
                         for line in self.invariant_lines())
        caveat = self.caveat()
        return "; ".join(x for x in (head, rest, caveat) if x)


def _padded(fingerprint: Fingerprint) -> tuple[str, ...]:
    """Point symbols lined up with sequences, when there are as many.

    A net can have two vertices with different walks and the same
    symbol, and then there is nothing to line up -- so the symbols are
    reported on their own rather than being paired up wrongly.
    """
    if len(fingerprint.symbols) == len(fingerprint.sequences):
        return fingerprint.symbols
    return ("",) * len(fingerprint.sequences)


def _shape(fingerprint: Fingerprint, multiplicity: int) -> str:
    numbers = "-, ".join(str(n) for n in fingerprint.coordination())
    periodic = f"{fingerprint.periodicity}-periodic"
    shape = f"{numbers}-coordinated, {periodic}"
    if multiplicity > 1:
        return f"{_fold(multiplicity)} interpenetrated, {shape}"
    return shape


def _fold(count: int) -> str:
    return {2: "2-fold", 3: "3-fold", 4: "4-fold"}.get(
        count, f"{count}-fold")


@dataclass(frozen=True)
class NetReport:
    """Every connected piece of the net a user drew, identified."""

    parts: tuple[Identification, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.parts)

    @property
    def name(self) -> str:
        """The one name, when every component agrees on it."""
        names = {p.name for p in self.parts}
        return names.pop() if len(names) == 1 and all(
            p.verdict == "named" for p in self.parts) else ""

    @property
    def copies(self) -> int:
        return sum(p.multiplicity for p in self.parts)

    def sentence(self) -> str:
        """One line, for a status bar."""
        if not self.parts:
            return "no net has been drawn"
        if self.name and self.copies > 1:
            first = self.parts[0]
            rest = "; ".join(" ".join(line.split())
                             for line in first.invariant_lines())
            return (f"{_fold(self.copies)} interpenetrated "
                    f"{self.name} -- {_shape(first.fingerprint, 1)}"
                    f"; {rest}")
        if len(self.parts) == 1:
            return self.parts[0].sentence()
        joined = "; ".join(p.sentence() for p in self.parts)
        return f"{len(self.parts)} separate nets: {joined}"

    def headline(self) -> str:
        """The panel's first line: the name, and nothing else."""
        if not self.parts:
            return "no net drawn"
        if self.name and self.copies > 1:
            return f"{_fold(self.copies)} interpenetrated {self.name}"
        if len(self.parts) == 1:
            return self.parts[0].headline()
        return f"{len(self.parts)} separate nets"

    def lines(self) -> list[str]:
        """The panel's version: the name, then what it rests on."""
        if not self.parts:
            return ["no net has been drawn"]
        out = [self.headline()]
        one = len(self.parts) == 1
        for index, part in enumerate(self.parts):
            out.append("")
            if not one:
                out.append(f"component {index + 1}  --  "
                           f"{part.headline()}")
            out.append(part.shape())
            out.extend(part.invariant_lines())
            if part.caveat():
                out.extend(["", part.caveat()])
        return out


def _known(given: Catalogue | None) -> Catalogue:
    """The catalogue to look in, or an empty one.

    A missing index is a missing *file*, not a net nobody has seen
    before, and the two must not read the same.  Everything the net
    itself says is still true without it.
    """
    if given is not None:
        return given
    try:
        return catalogue()
    except RcsrError:
        return Catalogue(())


def identify(net: Net, catalogue_: Catalogue | None = None,
             depth: int = DEPTH) -> Identification:
    """Name one connected net.

    **Both layers run.**  The invariants are a filter with a measured
    99.5% hit rate and the canonical key is a decision, and they are
    computed independently of each other on purpose: where the key
    settles the answer it says so, and where the two disagree the
    report prints both rather than choosing quietly.

    The net is assumed connected; :func:`describe` is what splits a
    drawn net into its components first, and identifying a
    disconnected one would compute the invariants of two nets at once
    and match neither.
    """
    known = _known(catalogue_)
    fingerprint = net.fingerprint(depth)
    names = known.lookup(fingerprint)
    key = _key(net) if fingerprint.periodicity >= 2 else ""
    matched = known.lookup_key(key)
    decided = bool(key) and (bool(matched) or known.keyed)
    looks_like = ()
    if matched:
        names = matched
    elif decided:
        names, looks_like = (), names
    reason, nearest = ("", ()) if names else known.nearest(fingerprint)
    return Identification(fingerprint, names, nearest, reason,
                          looks_like, net.multiplicity(), key, decided,
                          _unkeyed(known, decided and not matched),
                          bool(known.entries))


def _unkeyed(known: Catalogue, needed: bool) -> str:
    """What the negative verdict has to admit to, if anything."""
    if not needed or not known.unkeyed:
        return ""
    return (f" ({len(known.unkeyed)} catalogued nets have no "
            "canonical form and were compared by their invariants "
            "only)")


#: What a lookup will spend on a canonical form before falling back on
#: the invariants.  Smaller than what the index build allows itself,
#: and for a reason: this one runs while somebody is drawing.
LOOKUP_BUDGET = 2_000_000


def _key(net: Net) -> str:
    """The net's canonical form, or nothing if it has none to give.

    A net too large or too symmetric to key is not an error the user
    can act on: the invariants are still true, still name 99.5% of the
    RCSR, and the report says which of the two answered.
    """
    try:
        return net.key(LOOKUP_BUDGET)
    except TopologyError:
        return ""


def describe(net: Net, catalogue_: Catalogue | None = None,
             depth: int = DEPTH) -> NetReport:
    """Name the whole of what a user drew.

    Split into components first, because a framework that carries two
    interpenetrating nets is two answers and not one -- and because
    the invariants of two nets computed together are the invariants of
    neither.
    """
    if net.is_empty():
        return NetReport()
    known = _known(catalogue_)
    return NetReport(tuple(identify(part, known, depth)
                           for part in net.components()))


# ======================================================================
#  BUILDING THE INDEX
# ======================================================================

def _built(entry: CgdEntry, depth: int) -> tuple:
    """One entry, expanded and keyed, as it will be stored.

    A free function and not a closure because the build runs it in a
    process pool: 2929 nets are independent of one another and the
    keys are what makes the build cost an hour instead of a minute.
    """
    try:
        net = expand(entry)
        fingerprint = net.fingerprint(depth)
    except (RcsrError, CgdError) as exc:
        return None, (entry.name, str(exc))
    key, refusal = "", None
    try:
        key = net.key()
    except TopologyError as exc:
        refusal = (entry.name, f"no key: {exc}")
    return CatalogueEntry(
        entry.name, fingerprint.periodicity, fingerprint.sequences,
        fingerprint.symbols, entry.group, net.n_vertices,
        len(net.edges), key), refusal


def build(path=None, depth: int = DEPTH, report=None,
          workers: int = 1) -> Catalogue:
    """Read a ``.cgd`` file and compute every net's invariants and key.

    An hour, not a minute: the invariants are ten shells and a ring
    search per kind of vertex, and the key is a walk of the net from
    every vertex in every frame.  Which is why it is a build step and
    why it will use every core it is given -- 2929 nets have nothing to
    say to one another.  The running application calls
    :func:`catalogue` and reads the result.

    **A net that will not key is kept, not refused.**  Its invariants
    are as true as anything else here and they name it as well as they
    ever did; all that is missing is the certainty, and
    :attr:`Catalogue.unkeyed` is what makes the lookup say so.
    """
    path = Path(path) if path else source_file()
    if path is None or not path.is_file():
        raise RcsrError(
            "no RCSR .cgd file: expected "
            f"{Path(*SOURCE)} on a source checkout")
    read = read_cgd(path)
    entries, refused = [], [(_named(p), p) for p in read.problems]
    for built, refusal in _all(read, depth, workers):
        if refusal is not None:
            refused.append(refusal)
        if built is not None:
            entries.append(built)
            if report is not None:
                report(built)
    # In name order rather than the file's, so that two builds of the
    # same file differ only where the nets do.
    entries.sort(key=lambda e: e.name)
    return Catalogue(tuple(entries), path.name, tuple(refused))


def _all(read, depth: int, workers: int):
    """Every entry built, in the order they were written."""
    if workers < 2:
        yield from (_built(entry, depth) for entry in read)
        return
    from concurrent.futures import ProcessPoolExecutor
    entries = list(read)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        yield from pool.map(_built, entries, [depth] * len(entries),
                            chunksize=4)


def _named(problem: str) -> str:
    """The net a reader's complaint was about, for the refused list."""
    words = problem.split()
    return words[2] if len(words) > 2 else "?"


def write_index(catalogue: Catalogue, path=None) -> Path:
    path = Path(path) if path else INDEX
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        # 2 adds the canonical key to each row.  A row without one is
        # read as a net that has no key rather than as a broken file,
        # so an index built before the key still opens.
        "format": 2,
        "source": catalogue.source,
        "depth": DEPTH,
        "max_ring": MAX_RING,
        "nets": [e.to_row() for e in catalogue.entries],
        "refused": [list(r) for r in catalogue.refused],
    }
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"))
    return path


@lru_cache(maxsize=1)
def catalogue() -> Catalogue:
    """The catalogue that ships with the package.

    Read once and kept: it is a few hundred kilobytes and every net
    identified afterwards is a dictionary lookup.
    """
    if not INDEX.is_file():
        raise RcsrError(
            f"the RCSR index is missing from {INDEX}. "
            "Rebuild it with: python -m xtal.analysis.rcsr build")
    with gzip.open(INDEX, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    return Catalogue(
        tuple(CatalogueEntry.from_row(r) for r in payload["nets"]),
        payload.get("source", ""),
        tuple(tuple(r) for r in payload.get("refused", ())))


def source_file() -> Path | None:
    """The ``.cgd`` in ``resources/topo``, on a source checkout."""
    import xtal
    candidate = Path(xtal.__file__).resolve().parent.parent.joinpath(
        *SOURCE)
    return candidate if candidate.is_file() else None


if __name__ == "__main__":                  # pragma: no cover
    import os
    import sys
    import time

    if len(sys.argv) < 2 or sys.argv[1] != "build":
        print("usage: python -m xtal.analysis.rcsr build [FILE.cgd]")
        raise SystemExit(2)
    began = time.time()
    seen = [0]

    def tick(entry):
        seen[0] += 1
        print(f"  {seen[0]:5d} {entry.name:10s} "
              f"{'keyed' if entry.key else 'NO KEY':>6s}", flush=True)

    files = [a for a in sys.argv[2:] if not a.startswith("-")]
    built = build(files[0] if files else None,
                  report=tick if "-v" in sys.argv else None,
                  workers=os.cpu_count() or 1)
    written = write_index(built)
    print(f"{len(built)} nets from {built.source} "
          f"in {time.time() - began:.0f}s -> {written} "
          f"({written.stat().st_size / 1024:.0f} kB)")
    for name, why in built.refused:
        print(f"  refused {name}: {why}")
    clashes = {t: n for t, n in built.by_token.items() if len(n) > 1}
    print(f"  {len(clashes)} fingerprints name more than one net "
          f"({sum(len(n) for n in clashes.values())} names)")
    # Two names on one key is what a canonicalisation that is
    # self-consistent but not canonical produces, and it produces it
    # in bulk.  It is the one number in this report that must be zero.
    collisions = {k: n for k, n in built.by_key.items() if len(n) > 1}
    print(f"  {sum(1 for e in built.entries if not e.key)} nets "
          f"without a key, {len(collisions)} keys naming more than "
          f"one net")
    for names in list(collisions.values())[:20]:
        print(f"    one key: {', '.join(names)}")
