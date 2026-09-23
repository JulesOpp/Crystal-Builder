"""
xtal.mof.catalog
================
What there is to build with, read from the files rather than from
PORMAKE.

Importing PORMAKE used to cost ten seconds warm and half a minute
cold, because it imported ``jax`` and ``pymatgen`` on the way in.
Vendoring it took both away -- see ``xtal/mof/pormake/PROVENANCE.md``
-- and the argument here is unchanged even so: a picker that has to
show 2399 topologies and 867 building blocks should not import a
builder to list files, and it does not have to.  The topologies
are ``.cgd`` files, which :mod:`xtal.io.cgd` has read since the RCSR
work, and a building block is an XYZ whose second line lists which of
its atoms are connection points.  Everything the picker shows -- the
name, the coordination numbers, the formula, whether there is a metal
in it, and the coordinates to draw a picture from -- is in those two
files.

So this module reads them, and nothing in it imports PORMAKE.  The
whole of the database is 3.7 MB and parses in under half a second, so
it is read once, in full, and kept; a lazier arrangement would be more
code for a saving nobody would notice.

**Node types are the ``NODE`` lines, in file order.**  That is not a
convention this module invented: PORMAKE tags each expanded site with
the index of the ``NODE`` line it came from and calls that the node
type, so node type 2 in ``build_by_type`` is the third ``NODE`` line
of the ``.cgd`` and its coordination number is the number on it.
Reading the file is therefore reading PORMAKE's own numbering rather
than guessing at it.

**Edge types are the pairs of node types an edge joins**, which the
file does not state and which has to be worked out by expanding the
net -- :func:`xtal.analysis.rcsr.expand`, already written and already
tested.  It is done for the one topology that was picked and never for
the whole catalogue.  Four of the 2403 files cannot be expanded (they
give edge midpoints instead of endpoints, and a midpoint does not say
what it joins); those report their slots as unknown and the build
falls back on asking PORMAKE, which is imported by then anyway.

**The layer nets are the RCSR's, not files of ours.**  PORMAKE's
database is all 3-periodic; the 2-D nets come from the RCSR file that
already ships for naming nets (:func:`xtal.analysis.rcsr.nets`), each
written flat in its layer group by :func:`xtal.analysis.rcsr.as_layer`
and held as text.  PORMAKE is handed a file only when one is built on.
Four hand-written ones -- ``hcb``, ``hxl``, ``sql``, ``kgm`` -- were
the whole of it until 2026-09-21, and the RCSR's ``hcb`` is the file
that was here, value for value.
"""

from __future__ import annotations

import importlib.util
import re
import tempfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np

from xtal.core import elements as el
from xtal.io.cgd import (
    CgdEntry,
    CgdError,
    read_cgd_string,
    write_cgd_string,
)


class CatalogError(ValueError):
    """A topology or a building block that is not there, or not
    readable."""


#: What a connection point is called in a PORMAKE building block.  The
#: XYZ names its connection points by index on the second line and
#: PORMAKE rewrites those atoms to this symbol; the files are written
#: both ways and the index list is the one that is always there.
CONNECTION = "X"


# ======================================================================
#  WHERE THE DATABASE IS
# ======================================================================

def installed() -> bool:
    """Whether a framework can actually be *built*.

    **PORMAKE is vendored**, at :mod:`xtal.mof.pormake`, so its code is
    always there -- see ``xtal/mof/pormake/PROVENANCE.md``.  Two
    things beside it can still be absent, and they fail differently:

    * the nets and blocks -- 3271 files, 2.8 MB -- which a broken
      installation is missing and nobody can install;
    * ``ase``, which the vendored code is written over and which stays
      an extra, because ``pip install crystal-builder`` has to keep
      working on a headless box with four packages.

    :func:`xtal.modules.mof.available` tells the user which, because
    only one of the two is something they can act on.  This is the
    plain yes-or-no for everything that just wants to know whether to
    offer the feature.

    **Reading the catalogue needs neither**, which is why
    :func:`database_root` is separate: listing 2404 nets and 867
    blocks is file parsing this project does itself.

    No import either way.  This runs on every menu rebuild.
    """
    return database_root() is not None and has_ase()


def has_ase() -> bool:
    """Whether ``ase`` is importable -- without importing it.

    ``find_spec`` reads the location off the path and stops, which is
    the difference between a menu that greys an entry out in
    microseconds and one that pauses every time it is rebuilt.
    """
    try:
        return importlib.util.find_spec("ase") is not None
    except (ImportError, ValueError):           # pragma: no cover
        return False


def database_root() -> Path | None:
    """The vendored ``database/`` of nets and blocks, or ``None``.

    Beside the vendored package, which is where upstream keeps it too.
    Found through the module spec rather than by importing, for the
    reason above: ``find_spec`` reads the location off the path and
    stops, where the import costs seconds.
    """
    try:
        spec = importlib.util.find_spec("xtal.mof.pormake")
    except (ImportError, ValueError):           # pragma: no cover
        return None
    if spec is None or not spec.submodule_search_locations:
        return None
    root = Path(list(spec.submodule_search_locations)[0]) / "database"
    return root if root.is_dir() else None


def library_root() -> Path | None:
    """Our own ``blocks/``, the polydentate ones, or ``None``.

    Found the same way and for the same reason as
    :func:`database_root`: ``find_spec`` reads the location off the
    path and stops, where importing :mod:`xtal.mof.library` to ask
    where it is would cost the import.  ``None`` where the folder did
    not travel, which is a smaller catalogue and never a failure --
    the builder has PORMAKE's 867 either way.
    """
    return _library("blocks")


def _library(folder: str) -> Path | None:
    try:
        spec = importlib.util.find_spec("xtal.mof.library")
    except (ImportError, ValueError):           # pragma: no cover
        return None
    if spec is None or not spec.submodule_search_locations:
        return None
    root = Path(list(spec.submodule_search_locations)[0]) / folder
    return root if root.is_dir() else None


# ======================================================================
#  A BUILDING BLOCK
# ======================================================================

@dataclass(frozen=True)
class BuildingBlock:
    """One node or linker: its atoms, and which of them connect.

    ``connections`` are indices into ``symbols``.  A block goes into a
    slot when it has exactly as many of them as the slot's
    coordination number demands, which is the only compatibility rule
    there is and is why the count is the first thing here.

    ``bonds`` is the block's fourth section, ``(i, j, letter)``.  It is
    read because it is the only thing that says which atoms a
    connection point stands for -- see :mod:`xtal.mof.attach`.
    """

    name: str
    path: Path
    symbols: tuple[str, ...]
    positions: np.ndarray
    connections: tuple[int, ...]
    bonds: tuple[tuple[int, int, str], ...] = ()

    @property
    def n_connections(self) -> int:
        return len(self.connections)

    @property
    def members(self) -> dict[int, tuple[int, ...]]:
        """Connection point -> the *distinct* atoms it hangs off.

        The rule is :func:`xtal.mof.attach.members_of` and lives
        there rather than here, because a build reads it off
        PORMAKE's own ``BuildingBlock`` instead of off this one, and
        two copies of it would drift into a block that is bidentate
        at one end of the application and monodentate at the other.
        """
        from xtal.mof.attach import members_of

        return members_of(self.connections, self.bonds)

    def bond_pairs(self) -> list[tuple[int, int]]:
        """The pairs to draw this block with, as ``(i, j)``, ``i < j``.

        Its own bond section, which is what the build reads -- every
        one of the 879 blocks shipped today has one.  Guessing from
        distances instead, as the picker once did, drew 9401 bonds
        those blocks do not have (335 of them metal-metal) and missed
        74 they do, so the block in the picture was not the block that
        would be built.

        A block written with no bond section gets the application's
        own perception over its atoms, which never bonds a connection
        point, and each point is then joined to its nearest atom so it
        still hangs off something.
        """
        if self.bonds:
            return sorted({(min(int(i), int(j)), max(int(i), int(j)))
                           for i, j, *_ in self.bonds})
        from xtal.core.bonding import BondRules

        positions = np.asarray(self.positions, dtype=float)
        points = set(self.connections) | {
            i for i, s in enumerate(self.symbols) if s == CONNECTION}
        body = [i for i in range(len(self.symbols)) if i not in points]
        pairs = {(body[a], body[b]) for a, b in BondRules().pairs_within(
            positions[body], [self.symbols[i] for i in body])}
        for point in points:
            if not body:
                break
            gaps = np.linalg.norm(positions[body] - positions[point],
                                  axis=1)
            near = body[int(np.argmin(gaps))]
            pairs.add((min(point, near), max(point, near)))
        return sorted(pairs)

    @property
    def is_polydentate(self) -> bool:
        """Whether any connection point stands for more than one atom.

        The switch the build reads: a catalogue of blocks that answer
        False reaches none of the polydentate path, which is what
        makes every framework built before this work byte-identical
        after it.
        """
        return any(len(m) > 1 for m in self.members.values())

    @property
    def has_metal(self) -> bool:
        return any(el.element(s).is_metal for s in self.body_symbols)

    @property
    def body_symbols(self) -> tuple[str, ...]:
        """The real atoms: what is left once the connection points are
        gone, and the only ones that reach the framework."""
        return tuple(s for i, s in enumerate(self.symbols)
                     if i not in set(self.connections)
                     and s != CONNECTION)

    @property
    def composition(self) -> dict[str, int]:
        """Element symbol -> count, over the real atoms -- what
        :attr:`formula` renders as text and :func:`matches_composition`
        reads as numbers."""
        counts: dict[str, int] = {}
        for symbol in self.body_symbols:
            counts[symbol] = counts.get(symbol, 0) + 1
        return counts

    @property
    def formula(self) -> str:
        return "".join(f"{s}{n if n > 1 else ''}"
                       for s, n in sorted(self.composition.items()))

    def summary(self) -> str:
        """The line the picker shows beside the name."""
        metal = ", metal" if self.has_metal else ""
        return (f"{self.n_connections}-connected{metal}  ·  "
                f"{self.formula}")


#: A composition query's tokens: an optional leading count and one or
#: two letters that might be an element symbol -- ``6C``, ``Zn``,
#: ``n`` (checked against the real table, not assumed).
_COMPOSITION_TOKEN = re.compile(r"^(\d*)([A-Za-z]{1,2})$")


def _parse_composition(text: str) -> tuple[dict[str, int], frozenset]:
    """A composition query, split into the elements that need an
    exact count and the ones that only need to be present.

    ``"6C 4N 3Zn"`` -- every token counted -- gives
    ``({"C": 6, "N": 4, "Zn": 3}, frozenset())``.  ``"C H N O"`` --
    no counts at all -- gives ``({}, {"C", "H", "N", "O"})``.  The two
    forms mix freely token by token, which is what lets the same box
    answer "exactly 6 carbons" and "contains nitrogen" without two
    different searches.

    A token that is not a count-plus-symbol, or whose letters are not
    a real element, is dropped rather than refused: a person still
    typing "3Z" has not finished, and a search box that raises on an
    unfinished query is worse than one that waits for the rest of it.
    """
    exact: dict[str, int] = {}
    present: set[str] = set()
    for token in str(text or "").split():
        match = _COMPOSITION_TOKEN.match(token)
        if not match:
            continue
        count, letters = match.groups()
        try:
            symbol = el.parse_symbol(letters)
        except ValueError:
            continue
        if count:
            exact[symbol] = int(count)
        else:
            present.add(symbol)
    return exact, frozenset(present)


def matches_composition(block: BuildingBlock, query: str) -> bool:
    """Whether *block* answers a composition search.

    Every token in *query* is ANDed together over
    :attr:`BuildingBlock.composition`: ``"6C 4N 3Zn"`` wants exactly
    six carbons, four nitrogens and three zincs, whatever else the
    block is made of; ``"C H N O"`` wants all four elements present in
    any amount; ``"Zn"`` wants zinc, alone, or in company.  An empty or
    unreadable query matches everything, which is what an empty search
    box has to do.
    """
    exact, present = _parse_composition(query)
    if not exact and not present:
        return True
    composition = block.composition
    if not present.issubset(composition.keys()):
        return False
    return all(composition.get(symbol, 0) == count
              for symbol, count in exact.items())


def matches_search(block: BuildingBlock, query: str) -> bool:
    """Whether *block* answers the building-block search box.

    A composition search, plus names: a word that reads as an element
    or a count and an element is composition -- ``6C``, ``Zn``, ``N``
    -- and any other word must appear in the block's name -- ``N59``,
    ``paddle``.  Every word is ANDed.  The split is by what a word can
    be rather than by trying both, because ``N`` tried as a name
    fragment is in every one of PORMAKE's 700-odd node names and would
    make a search for nitrogen a search for nothing.
    """
    fragments = [word.lower() for word in str(query or "").split()
                 if _parse_composition(word) == ({}, frozenset())]
    name = block.name.lower()
    if not all(fragment in name for fragment in fragments):
        return False
    return matches_composition(block, query)


def read_building_block(path) -> BuildingBlock:
    """One ``.xyz`` from PORMAKE's ``bbs/``, or one of the user's own.

    The format is an ordinary XYZ with the second line -- where a
    comment belongs -- carrying the indices of the connection points.
    Files written the other way mark them as ``X`` atoms instead, and
    both are read, because a user writing their own block will copy
    whichever example they found.

    Everything after the atoms is bonds, which is PORMAKE's own rule
    (``pormake/utils.py``) and the reason a block file can have no
    header of its own: a line that is not a bond would be read as one.
    """
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise CatalogError(f"{path.name} is empty")
    try:
        n_atoms = int(lines[0].split()[0])
    except (IndexError, ValueError):
        raise CatalogError(
            f"{path.name}: the first line of an XYZ file is an atom "
            f"count") from None
    symbols, positions = [], []
    for line in lines[2:2 + n_atoms]:
        parts = line.split()
        if len(parts) < 4:
            raise CatalogError(f"{path.name}: malformed line {line!r}")
        symbols.append(el.parse_symbol(parts[0])
                       if parts[0] != CONNECTION else CONNECTION)
        positions.append([float(v) for v in parts[1:4]])
    if len(symbols) != n_atoms:
        raise CatalogError(
            f"{path.name} claims {n_atoms} atoms and lists "
            f"{len(symbols)}")
    connections = _connections(lines[1] if len(lines) > 1 else "",
                              symbols, path)
    return BuildingBlock(path.stem, path, tuple(symbols),
                         np.asarray(positions, dtype=float).reshape(
                             -1, 3),
                         connections,
                         _bonds(lines[2 + n_atoms:], len(symbols)))


def _bonds(lines, n_atoms: int) -> tuple[tuple[int, int, str], ...]:
    """The bond block: ``i j letter``, one per line.

    Tolerant in exactly the way PORMAKE's own reader is tolerant
    (``pormake/utils.py`` lines 527-531): a line with fewer than three
    tokens is skipped in silence, because there is no header to tell a
    bond block from a blank line and refusing would make a file
    PORMAKE reads one this application does not.  Two things go
    further than PORMAKE does, and both would otherwise become an
    :class:`IndexError` a long way from here: a pair of tokens that
    are not integers is skipped, and so is an index outside the atoms.
    """
    found = []
    for line in lines:
        tokens = line.split()
        if len(tokens) < 3:
            continue
        try:
            i, j = int(tokens[0]), int(tokens[1])
        except ValueError:
            continue
        if 0 <= i < n_atoms and 0 <= j < n_atoms and i != j:
            found.append((i, j, tokens[2]))
    return tuple(found)


def _connections(comment: str, symbols, path: Path) -> tuple[int, ...]:
    """The connection points, from the index line or from the atoms.

    Refused rather than guessed at when there are neither: a block
    whose connection points are unknown cannot be placed on anything,
    and one silently treated as having none would be built into a
    framework as a lump of unbonded atoms.
    """
    try:
        listed = tuple(int(t) for t in comment.split())
    except ValueError:
        listed = ()
    if listed and all(0 <= i < len(symbols) for i in listed):
        return listed
    marked = tuple(i for i, s in enumerate(symbols)
                   if s == CONNECTION)
    if marked:
        return marked
    raise CatalogError(
        f"{path.name} names no connection points -- the second line "
        f"should list their indices, or they should be X atoms")


# ======================================================================
#  A TOPOLOGY, AND THE SLOTS IT WANTS FILLED
# ======================================================================

@dataclass(frozen=True)
class Slot:
    """One thing the user has to pick a building block for.

    A node slot is a node type and the coordination number it demands;
    an edge slot is the pair of node types it joins and always demands
    two.  ``key`` is what ``build_by_type`` is keyed on, so it is what
    a parameter has to be able to spell.
    """

    kind: str                       # "node" or "edge"
    key: tuple                      # 0, or (0, 1)
    coordination: int

    @property
    def is_edge(self) -> bool:
        return self.kind == "edge"

    @property
    def label(self) -> str:
        if self.is_edge:
            a, b = self.key
            return (f"Linker between node {a + 1} and node {b + 1}"
                    if a != b else f"Linker at node {a + 1}")
        return f"Node {self.key + 1}, {self.coordination}-connected"

    @property
    def token(self) -> str:
        """How this slot is spelled in a parameter: ``0`` or ``0-1``."""
        if self.is_edge:
            return f"{self.key[0]}-{self.key[1]}"
        return str(self.key)


@dataclass(frozen=True)
class Topology:
    """One net to build on, read but not expanded."""

    name: str
    #: ``None`` for a net held as :attr:`text` -- an RCSR layer.
    path: Path | None
    group: str
    #: The coordination number of each node type, in the order the
    #: ``NODE`` lines appear -- which is PORMAKE's node numbering.
    coordinations: tuple[int, ...]
    #: The ``.cgd`` itself, for a net that has no file of its own.
    text: str = field(default="", repr=False, compare=False)
    #: How many ``EDGE`` lines the file wrote: q, the edge
    #: transitivity, unless the RCSR says otherwise (:meth:`facts`).
    edge_lines: int = field(default=0, compare=False)
    _cache: dict = field(default_factory=dict, repr=False,
                         compare=False)

    @property
    def n_node_types(self) -> int:
        return len(self.coordinations)

    def summary(self) -> str:
        """The line the picker shows beside the name: coordination,
        group and number, and transitivity as the RCSR prints it."""
        return self.facts().summary()

    def facts(self):
        """What the net search matches this topology on.

        p and q are the RCSR's for a net of PORMAKE's or of the
        RCSR's own, looked up by name: the RCSR writes each net at its
        maximum symmetry, so its ``NODE`` and ``EDGE`` lines count the
        kinds of vertex and edge, and eight of PORMAKE's files write a
        different number of ``EDGE`` lines for the same net -- ``tfm``
        has eleven for two kinds.  A net of the user's is taken at its
        word; one with no ``EDGE`` lines has q unknown.  Read off the
        header, never the expansion, so the whole list costs
        milliseconds.
        """
        if "facts" not in self._cache:
            self._cache["facts"] = self._facts()
        return self._cache["facts"]

    def _facts(self):
        from xtal.analysis.netsearch import NetFacts, space_group_number
        from xtal.analysis.rcsr import plane_group_number

        plane = plane_group_number(self.group)
        number = (plane if plane is not None
                  else space_group_number(self.group))
        p, q = len(self.coordinations), self.edge_lines or None
        if self.path is None or _in_pormake(self.path):
            p, q = _rcsr_transitivity().get(self.name, (p, q))
        return NetFacts(
            name=self.name, dimension=2 if plane is not None else 3,
            coordinations=self.coordinations, group=self.group,
            number=number, p=p, q=q)

    def entry(self) -> CgdEntry:
        """The ``.cgd`` block, parsed."""
        if "entry" not in self._cache:
            self._cache["entry"] = (_entry_of_text(self.text)
                                    if self.text
                                    else _entry_of(self.path))
        return self._cache["entry"]

    def net(self):
        """This topology as a periodic graph.

        :func:`xtal.analysis.rcsr.expand` -- the same expansion the
        RCSR index is built with, so what comes back can be handed
        straight to the catalogue and named.
        """
        return self.placement()[0]

    def placement(self):
        """The net, and where the file drew its vertices.

        The coordinates are decoration and no invariant uses them.
        They are here for the picture the picker shows, which is the
        one thing about a net that a name and four numbers cannot
        convey to somebody choosing between 2399 of them.
        """
        if "placement" not in self._cache:
            from xtal.analysis import rcsr
            self._cache["placement"] = rcsr.placement(self.entry())
        return self._cache["placement"]

    def expanded(self, nx: int = 1, ny: int = 1, nz: int = 1):
        """This net as PORMAKE reads it, repeated along its own axes.

        The one place a vendored :class:`pormake.Topology` is made,
        so that a build and a test ask for a supercell the same way.
        ``(1, 1, 1)`` hands back the net itself and multiplies
        nothing -- a repeat of one has to be the build it always was,
        to the bit, and the way to guarantee that is not to take the
        other path.

        Over ``Topology.__mul__``, which tiles the underlying atoms
        and rebuilds the neighbour lists; no vendored file is edited
        to reach it.  A 2x2x2 of ``pcu`` is 32 slots and 0.03 s, and
        building MFU-4l on it gives 648 atoms -- the crystal's own P1
        count.

        Nothing is cached.  The builder scales the topology it is
        given into a *copy*, so handing the same object to two builds
        would be safe today; it is made fresh anyway, because a net
        held between builds is a thing whose state nobody owns.
        """
        from xtal.mof.build import import_pormake

        pormake = import_pormake()
        topology = self._pormake(pormake)
        repeat = (int(nx), int(ny), int(nz))
        if min(repeat) < 1:
            raise CatalogError(
                f"a net cannot be repeated {repeat[0]}x{repeat[1]}x"
                f"{repeat[2]} times")
        if repeat == (1, 1, 1):
            return topology
        return topology * repeat

    def _pormake(self, pormake):
        """PORMAKE's reading of this net, from a file either way.

        It reads the file once, in its constructor, and keeps nothing
        but what it parsed, so a net held as text is written to a
        folder that is gone before the build begins.
        """
        if not self.text:
            return pormake.Topology(str(self.path))
        with tempfile.TemporaryDirectory(prefix="xtal-net-") as folder:
            path = Path(folder) / f"{self.name}.cgd"
            path.write_text(self.text, encoding="utf-8")
            return pormake.Topology(str(path))

    @property
    def is_layer(self) -> bool:
        """Whether this is a 2-periodic net, stacked along *c*.

        Read off the graph -- :func:`xtal.mof.layers.
        stacking_axis_is_free` -- and not off the folder it came
        from, so a layer somebody wrote into their own topology
        folder is stacked like one of ours.  It costs the expansion,
        milliseconds; the list can ask it of every row only because
        PORMAKE's own nets arrive already answered
        (:func:`_record_pormake_dimensions`).
        """
        if "layer" not in self._cache:
            from xtal.mof.layers import stacking_axis_is_free

            try:
                self._cache["layer"] = stacking_axis_is_free(
                    self.net())
            except (CgdError, ValueError):
                self._cache["layer"] = False
        return self._cache["layer"]

    def lattice(self):
        """A cell to draw the vertices in.

        The ``.cgd`` cell when it states one and a unit cube when it
        does not -- four of the RCSR's own blocks have no ``CELL``
        line, and a net with no cell is still a net.  Nothing but the
        picture depends on this.
        """
        from xtal.core.lattice import Lattice

        cell = self.entry().cell
        if cell and len(cell) == 6:
            return Lattice.from_parameters(*cell)
        if cell and len(cell) == 3:
            a, b, gamma = cell
            return Lattice.from_parameters(a, b, 1.0, 90.0, 90.0,
                                           gamma)
        return Lattice.from_parameters(1, 1, 1, 90, 90, 90)

    def identify(self):
        """What the RCSR calls this net.

        The point of computing it is that PORMAKE's database and the
        RCSR are two catalogues, and a name that appears in both has
        to mean the same net in both.
        """
        if "identified" not in self._cache:
            from xtal.analysis import rcsr
            self._cache["identified"] = rcsr.describe(self.net())
        return self._cache["identified"]

    def slots(self) -> tuple[Slot, ...]:
        """Every node and edge slot, in the order to ask about them.

        Raises :class:`~xtal.io.cgd.CgdError` for the handful of files
        that give edge midpoints rather than endpoints, because the
        edge types cannot be worked out from a midpoint.  The caller
        that cares is the dialog, and its fallback is to ask PORMAKE.
        """
        if "slots" not in self._cache:
            self._cache["slots"] = self._slots()
        return self._cache["slots"]

    def _slots(self) -> tuple[Slot, ...]:
        net = self.net()
        nodes = [Slot("node", i, c)
                 for i, c in enumerate(self.coordinations)]
        pairs = []
        for edge in net.edges:
            a, b = net.orbits[edge.i], net.orbits[edge.j]
            pair = (min(a, b), max(a, b))
            if pair not in pairs:
                pairs.append(pair)
        edges = [Slot("edge", pair, 2) for pair in sorted(pairs)]
        return tuple(nodes + edges)


def _entry_of(path: Path) -> CgdEntry:
    return _entry_of_text(Path(path).read_text(encoding="utf-8"),
                          Path(path).name)


def _entry_of_text(text: str, where: str = "the net") -> CgdEntry:
    read = read_cgd_string(text)
    if not read.entries:
        raise CgdError(read.problems[0] if read.problems
                       else f"{where} holds no net")
    return read.entries[0]


#: The RCSR layer nets PORMAKE cannot build on: each fails its own
#: ``check_validity``, the test that took its 3-D catalogue from 2726
#: nets to 2405.  Listing a net whose every build fails is worse than
#: a list four shorter, so they are left out, and
#: ``test_the_four_pormake_rejects_are_left_out_and_still_fail`` is
#: what keeps this from going stale.  The Net builder still draws them.
PORMAKE_REJECTS = frozenset({"fzh", "mtb-a", "mtc-a", "sde"})


def rcsr_layers() -> tuple[Topology, ...]:
    """Every 2-periodic RCSR net PORMAKE can build on, as topologies.

    Written by :func:`xtal.analysis.rcsr.as_layer` into the layer
    group of their plane group, with the plane group kept as
    :attr:`Topology.group` because that is the group the net is *in*;
    the space group is how it is spelled for PORMAKE.  Each is told
    it is a layer rather than asked, as PORMAKE's are told they are
    not (:func:`_record_pormake_dimensions`), and
    ``test_every_rcsr_layer_is_recorded_as_a_layer_and_is_one``
    re-derives it.  ``END`` is the file's last line because PORMAKE
    drops the last line unread.
    """
    from xtal.analysis import rcsr

    found = []
    for entry in rcsr.nets():
        if (entry.dimension != 2 or not entry.cell
                or entry.name in PORMAKE_REJECTS):
            continue
        text = write_cgd_string([rcsr.as_layer(entry)]).rstrip() + "\n"
        topology = Topology(
            entry.name, None, entry.group,
            tuple(node.coordination for node in entry.nodes), text,
            len(entry.edges))
        topology._cache["layer"] = True
        found.append(topology)
    return tuple(found)


class _Layers:
    """Where :class:`Catalog` reads the RCSR layers, in the order of
    its folders.  Not a folder; it stands in the list so that a
    folder after it still wins, as every later folder does."""

    def __str__(self) -> str:
        return "the RCSR's layer nets"


#: The one :class:`_Layers` a catalogue's ``topology_dirs`` holds.
RCSR_LAYERS = _Layers()


@lru_cache(maxsize=1)
def _rcsr_transitivity() -> dict[str, tuple[int | None, int | None]]:
    """Name -> (p, q) for every RCSR net; empty if the file is not
    there, which leaves every net with what its own file says."""
    from xtal.analysis import rcsr

    try:
        nets = rcsr.nets()
    except rcsr.RcsrError:                      # pragma: no cover
        return {}
    return {e.name: (len(e.nodes) or None, len(e.edges) or None)
            for e in nets}


@lru_cache(maxsize=1)
def _pormake_folder() -> Path | None:
    root = database_root()
    return (root / "topologies").resolve() if root else None


def _in_pormake(path: Path) -> bool:
    folder = _pormake_folder()
    return folder is not None and path.parent.resolve() == folder


def _record_pormake_dimensions(topologies) -> None:
    """Tell every net of PORMAKE's own that it is not a layer.

    Every one of them is 3-periodic: the 2395 that expand, which is
    the recorded fact ``test_every_pormake_net_is_three_periodic``
    re-derives.  Asking the graph instead costs the expansion, ten
    seconds over the list, and the topology picker needs the answer
    for every row to offer 3-D and 2-D nets apart.  Only the files in
    PORMAKE's folder are told: a net of ours or of the user's --
    including one that replaces a PORMAKE name -- is still asked, and
    there are a handful of those.
    """
    for topology in topologies:
        if topology.path is not None and _in_pormake(topology.path):
            topology._cache.setdefault("layer", False)


def read_topology(path) -> Topology:
    """The header of one ``.cgd``: the name, the group and the nodes.

    Only the header, because the catalogue holds 2403 of these and the
    expansion of one is worth ten milliseconds that the list does not
    need.  What it does need -- the coordination numbers -- is what the
    ``NODE`` lines state, and the expansion checks them against the
    graph when a topology is actually picked.
    """
    path = Path(path)
    name, group, coordinations, edges = _header(path)
    return Topology(name or path.stem, path, group, coordinations,
                    edge_lines=edges)


def _header(path: Path) -> tuple[str, str, tuple[int, ...], int]:
    name = group = ""
    coordinations: list[int] = []
    edges = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#")[0].strip()
        if not line:
            continue
        token = line.split()
        head = token[0].lower()
        if head == "name" and len(token) > 1:
            name = token[1]
        elif head == "group" and len(token) > 1:
            group = token[1]
        elif head in ("node", "atom") and len(token) > 2:
            try:
                coordinations.append(int(token[2]))
            except ValueError:                  # pragma: no cover
                pass
        elif head == "edge":
            edges += 1
        elif head == "end":
            break
    if not coordinations:
        raise CatalogError(f"{path.name} declares no nodes")
    return name, group or "P1", tuple(coordinations), edges


# ======================================================================
#  THE CATALOGUE
# ======================================================================

@dataclass
class Catalog:
    """Everything there is to build with, from one or more folders.

    The extra directories are the whole of "a user's own building
    block is a folder, not a code change": PORMAKE's ``Database``
    takes a ``topo_dir`` and a ``bb_dir``, so a block somebody drew is
    an XYZ they drop in one, and it appears in the picker beside the
    867 that shipped.  A name in a later directory wins, which is what
    lets a user replace one of PORMAKE's own.
    """

    topology_dirs: tuple[Path, ...] = ()
    bb_dirs: tuple[Path, ...] = ()

    def __post_init__(self):
        self.topology_dirs = tuple(
            p if p is RCSR_LAYERS else Path(p)
            for p in self.topology_dirs if p)
        self.bb_dirs = tuple(Path(p) for p in self.bb_dirs if p)
        self._topologies: dict[str, Topology] | None = None
        self._blocks: dict[str, BuildingBlock] | None = None
        self._failures: list[str] = []

    @classmethod
    def default(cls, topology_dir="", bb_dir="",
                also_blocks=()) -> Catalog:
        """PORMAKE's bundled database, plus the user's own folders.

        ``also_blocks`` is every other folder of blocks to read -- the
        open workspace's, in the application -- and comes last for the
        same reason ``bb_dir`` comes after PORMAKE's: a file in a
        later directory replaces one of the same name in an earlier
        one, so a block you drew wins over a block you were shipped.

        :func:`library_root` goes in second, between the two, and
        that is where it belongs rather than an accident of writing:
        our four are shipped, so a folder of the user's own must
        still win over them, and they are ours, so they may replace
        one of PORMAKE's.  :data:`RCSR_LAYERS` goes between PORMAKE's
        nets and the user's for the same reason.
        """
        root = database_root()
        ours = library_root()
        topologies = [root / "topologies"] if root else []
        blocks = [root / "bbs"] if root else []
        topologies.append(RCSR_LAYERS)
        if ours:
            blocks.append(ours)
        if topology_dir:
            topologies.append(Path(topology_dir).expanduser())
        if bb_dir:
            blocks.append(Path(bb_dir).expanduser())
        blocks += [Path(p).expanduser() for p in also_blocks if p]
        return cls(tuple(topologies), tuple(blocks))

    @property
    def usable(self) -> bool:
        return bool(self.topology_dirs and self.bb_dirs)

    # -- topologies ----------------------------------------------------

    def topologies(self) -> tuple[Topology, ...]:
        if self._topologies is None:
            self._topologies = self._read(
                self.topology_dirs, "*.cgd", read_topology)
            _record_pormake_dimensions(self._topologies.values())
        return tuple(self._topologies.values())

    def topology(self, name: str) -> Topology:
        self.topologies()
        try:
            return self._topologies[str(name)]
        except KeyError:
            raise CatalogError(
                f"no topology called {name!r}; "
                f"{len(self._topologies)} were read from "
                f"{', '.join(str(d) for d in self.topology_dirs)}"
            ) from None

    # -- building blocks -----------------------------------------------

    def building_blocks(self) -> tuple[BuildingBlock, ...]:
        if self._blocks is None:
            self._blocks = self._read(self.bb_dirs, "*.xyz",
                                      read_building_block)
        return tuple(self._blocks.values())

    def building_block(self, name: str) -> BuildingBlock:
        self.building_blocks()
        try:
            return self._blocks[str(name)]
        except KeyError:
            raise CatalogError(
                f"no building block called {name!r}; "
                f"{len(self._blocks)} were read from "
                f"{', '.join(str(d) for d in self.bb_dirs)}"
            ) from None

    def fitting(self, coordination: int) -> tuple[BuildingBlock, ...]:
        """The blocks that can go in a slot of this coordination.

        The only rule there is: a six-connected slot takes a block
        with six connection points, and nothing else fits it at all.
        """
        return tuple(b for b in self.building_blocks()
                     if b.n_connections == int(coordination))

    # -- reading -------------------------------------------------------

    @property
    def failures(self) -> tuple[str, ...]:
        """The files that could not be read, if any were.

        Collected rather than raised, for the reason
        :mod:`xtal.io.cgd` collects them: a catalogue of 2403 nets
        that will not open because one of them is malformed is worse
        than 2399 nets and a sentence naming the four.
        """
        self.topologies()
        self.building_blocks()
        return tuple(self._failures)

    def _read(self, directories, pattern: str, reader) -> dict:
        out: dict = {}
        for directory in directories:
            if directory is RCSR_LAYERS:
                from xtal.analysis.rcsr import RcsrError
                try:
                    out.update((t.name, t) for t in rcsr_layers())
                except RcsrError as exc:
                    self._failures.append(f"{directory}: {exc}")
                continue
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob(pattern)):
                try:
                    item = reader(path)
                except (CatalogError, CgdError, OSError,
                        ValueError) as exc:
                    self._failures.append(f"{path.name}: {exc}")
                    continue
                out[item.name] = item
        return dict(sorted(out.items()))
