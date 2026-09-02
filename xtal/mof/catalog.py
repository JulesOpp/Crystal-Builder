"""
xtal.mof.catalog
================
What there is to build with, read from the files rather than from
PORMAKE.

``import pormake`` costs ten seconds on a warm cache and half a minute
on a cold one, because it imports ``jax`` and ``pymatgen`` on the way
in.  A picker that has to show 2399 topologies and 867 building blocks
cannot pay that when it opens, and it does not have to: the topologies
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
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from xtal.core import elements as el
from xtal.io.cgd import CgdEntry, CgdError, read_cgd_string


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
    """Whether ``pormake`` is importable -- without importing it.

    ``find_spec`` reads the package's location off the path and stops.
    That is the whole difference between a menu that greys an entry out
    in microseconds and one that freezes for ten seconds every time it
    is rebuilt.
    """
    try:
        return importlib.util.find_spec("pormake") is not None
    except (ImportError, ValueError):           # pragma: no cover
        return False


def database_root() -> Path | None:
    """PORMAKE's bundled ``database/``, or ``None``.

    It ships inside the wheel, so an installed PORMAKE has it and a
    source checkout has it in the same place.  Found through the
    module spec rather than by importing, for the reason above.
    """
    try:
        spec = importlib.util.find_spec("pormake")
    except (ImportError, ValueError):           # pragma: no cover
        return None
    if spec is None or not spec.submodule_search_locations:
        return None
    root = Path(list(spec.submodule_search_locations)[0]) / "database"
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
    """

    name: str
    path: Path
    symbols: tuple[str, ...]
    positions: np.ndarray
    connections: tuple[int, ...]

    @property
    def n_connections(self) -> int:
        return len(self.connections)

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
    def formula(self) -> str:
        counts: dict[str, int] = {}
        for symbol in self.body_symbols:
            counts[symbol] = counts.get(symbol, 0) + 1
        return "".join(f"{s}{n if n > 1 else ''}"
                       for s, n in sorted(counts.items()))

    def summary(self) -> str:
        """The line the picker shows beside the name."""
        metal = ", metal" if self.has_metal else ""
        return (f"{self.n_connections}-connected{metal}  ·  "
                f"{self.formula}")


def read_building_block(path) -> BuildingBlock:
    """One ``.xyz`` from PORMAKE's ``bbs/``, or one of the user's own.

    The format is an ordinary XYZ with the second line -- where a
    comment belongs -- carrying the indices of the connection points.
    Files written the other way mark them as ``X`` atoms instead, and
    both are read, because a user writing their own block will copy
    whichever example they found.
    """
    path = Path(path)
    lines = path.read_text().splitlines()
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
                         connections)


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
    path: Path
    group: str
    #: The coordination number of each node type, in the order the
    #: ``NODE`` lines appear -- which is PORMAKE's node numbering.
    coordinations: tuple[int, ...]
    _cache: dict = field(default_factory=dict, repr=False,
                         compare=False)

    @property
    def n_node_types(self) -> int:
        return len(self.coordinations)

    def summary(self) -> str:
        counts = ", ".join(f"{c}-c" for c in self.coordinations)
        return f"{counts}  ·  {self.group}"

    def entry(self) -> CgdEntry:
        """The ``.cgd`` block, parsed."""
        if "entry" not in self._cache:
            self._cache["entry"] = _entry_of(self.path)
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
    read = read_cgd_string(Path(path).read_text())
    if not read.entries:
        raise CgdError(read.problems[0] if read.problems
                       else f"{Path(path).name} holds no net")
    return read.entries[0]


def read_topology(path) -> Topology:
    """The header of one ``.cgd``: the name, the group and the nodes.

    Only the header, because the catalogue holds 2403 of these and the
    expansion of one is worth ten milliseconds that the list does not
    need.  What it does need -- the coordination numbers -- is what the
    ``NODE`` lines state, and the expansion checks them against the
    graph when a topology is actually picked.
    """
    path = Path(path)
    entry = _header(path)
    return Topology(entry[0] or path.stem, path, entry[1], entry[2])


def _header(path: Path) -> tuple[str, str, tuple[int, ...]]:
    name = group = ""
    coordinations: list[int] = []
    for raw in path.read_text().splitlines():
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
        elif head == "end":
            break
    if not coordinations:
        raise CatalogError(f"{path.name} declares no nodes")
    return name, group or "P1", tuple(coordinations)


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
            Path(p) for p in self.topology_dirs if p)
        self.bb_dirs = tuple(Path(p) for p in self.bb_dirs if p)
        self._topologies: dict[str, Topology] | None = None
        self._blocks: dict[str, BuildingBlock] | None = None
        self._failures: list[str] = []

    @classmethod
    def default(cls, topology_dir="", bb_dir="") -> Catalog:
        """PORMAKE's bundled database, plus the user's own folders."""
        root = database_root()
        topologies = [root / "topologies"] if root else []
        blocks = [root / "bbs"] if root else []
        if topology_dir:
            topologies.append(Path(topology_dir).expanduser())
        if bb_dir:
            blocks.append(Path(bb_dir).expanduser())
        return cls(tuple(topologies), tuple(blocks))

    @property
    def usable(self) -> bool:
        return bool(self.topology_dirs and self.bb_dirs)

    # -- topologies ----------------------------------------------------

    def topologies(self) -> tuple[Topology, ...]:
        if self._topologies is None:
            self._topologies = self._read(
                self.topology_dirs, "*.cgd", read_topology)
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
