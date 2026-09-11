"""
xtal.mof.build
==============
PORMAKE invoked, the framework read back, and the net drawn on it.

Four steps, and the interesting ones are the last two.

**Resolve.**  A request is three strings -- a topology name, which
block goes in which node slot, which goes on which edge -- because
that is what survives a command line, a saved parameter set and a
dialog equally well.  :class:`BuildRequest` turns them into the
``{type: block}`` dictionaries ``Builder.build_by_type`` wants, and
refuses a block whose connection points do not match the slot's
coordination number *before* PORMAKE is asked to place it: PORMAKE's
own refusal is an assertion deep inside a locator, and "N59 has 6
connection points and node 2 wants 4" is the sentence a user can act
on.

**Build.**  One call.  This is the only place ``pormake`` is imported,
and it happens on the worker thread because the import costs ten
seconds.

**Hand over as CIF.**  ``Framework.write_cif`` into the run folder and
:func:`xtal.io.FORMATS.read` back.  Not the ASE or pymatgen objects
PORMAKE works in: the run folder wants the file on disk anyway, gemmi
already reads it, and a translation layer between three different atom
containers is a bug farm with no upside.

**Draw the net on it, and then check it.**  PORMAKE builds a framework
by putting a block on every slot of a net, so it knows exactly which
atoms are one node -- and a net is exactly what this application draws
on a framework by hand.  So :func:`draw_net` puts the edges in as
:data:`~xtal.core.structure.TOPOLOGY` bonds and the framework arrives
with its net already drawn: the Net panel names it as soon as the tab
opens, and nobody has to click two atoms of a 3856-atom framework to
find out what they built.

That also makes the build checkable, which nothing else in this
application does.  :func:`check_net` reads the net back off the
structure with :func:`xtal.analysis.net_of` -- the same function the
panel uses, over bonds stored in the structure rather than over
anything PORMAKE said -- and names it against the RCSR.  A build that
was asked for **tbo** and produces something that is not tbo says so
in its own report.  Every piece of that was written and tested for the
topology work; what is new here is using the canonical key for
something other than answering a question.
"""

from __future__ import annotations

import logging
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from xtal.core.structure import TOPOLOGY, Bond
from xtal.mof.catalog import Catalog, CatalogError, Slot

#: PORMAKE's own name for the atoms that mark where a block connects.
#: They are removed from the framework, which is what makes the atom
#: ordering below need stating rather than assuming.
CONNECTION = "X"


class MofError(ValueError):
    """A build that cannot be set up, said in a sentence."""


# ======================================================================
#  WHAT WAS ASKED FOR
# ======================================================================

@dataclass
class BuildRequest:
    """A topology, a block per node slot, and a block per edge slot.

    Held as plain data on purpose.  The same object is what a dialog
    fills in, what ``xtal run`` parses out of ``-p`` flags and what a
    test writes by hand, and none of those three should have to know
    about a PORMAKE object.
    """

    topology: str
    #: ``{node type: block name}``.  Node type 0 is the first ``NODE``
    #: line of the ``.cgd``; see :mod:`xtal.mof.catalog`.
    nodes: dict[int, str] = field(default_factory=dict)
    #: ``{(node type, node type): block name}``.  Empty means no
    #: linkers at all, which PORMAKE builds as nodes bonded directly.
    edges: dict[tuple[int, int], str] = field(default_factory=dict)

    @classmethod
    def parse(cls, topology: str, nodes: str, edges: str
              ) -> BuildRequest:
        """The three strings a parameter form and a command line both
        hand over.

        ``nodes`` is ``"N59"`` when there is one node type and
        ``"0=N59,1=N131"`` when there is more than one; ``edges`` is
        ``"E32"``, ``"0-0=E32,0-1=E14"``, or empty for none.  The bare
        form exists because the overwhelming majority of nets people
        build on have one kind of node and one kind of edge, and
        making those spell a slot they cannot get wrong is ceremony.
        """
        topology = str(topology or "").strip()
        if not topology:
            raise MofError("a build needs a topology to build on")
        return cls(topology,
                   _assignments(nodes, _node_key, "node"),
                   _assignments(edges, _edge_key, "edge"))

    def spelled(self) -> tuple[str, str, str]:
        """Back to the three strings, for a log and for a saved set.

        The unkeyed form comes back unkeyed: what a user wrote is what
        their log says they ran, and rewriting ``N59`` as ``0=N59``
        would make the record of a run stop matching the run.
        """
        return (self.topology, _spell(self.nodes, _node_token),
                _spell(self.edges, _edge_token))

    def title(self) -> str:
        """What to call the framework: ``pcu-N59-E32``."""
        parts = [self.topology]
        parts += [self.nodes[k] for k in _ordered(self.nodes)]
        parts += [self.edges[k] for k in _ordered(self.edges)]
        return "-".join(p for p in parts if p)

    def block_for(self, slot: Slot) -> str:
        """The block this request puts in that slot, or ``""``.

        A single unkeyed assignment fills every slot of its kind,
        which is what makes ``nodes="N59"`` mean what it obviously
        means on a net with one node type -- and what makes it mean
        "the same block everywhere" on one with two.
        """
        table = self.edges if slot.is_edge else self.nodes
        if slot.key in table:
            return table[slot.key]
        if len(table) == 1 and _ANY in table:
            return table[_ANY]
        return ""


#: The key an unkeyed assignment is stored under -- ``"N59"`` rather
#: than ``"0=N59"``.  Not a valid slot key, so it can never collide
#: with one.
_ANY = "*"


def _assignments(text, key_of, what: str) -> dict:
    out: dict = {}
    for part in str(text or "").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        name, sep, value = part.partition("=")
        if not sep:
            out[_ANY] = name.strip()
            continue
        try:
            out[key_of(name.strip())] = value.strip()
        except ValueError:
            raise MofError(
                f"{part!r} does not name an {what} slot -- write "
                f"{'0-1=E32' if what == 'edge' else '0=N59'}, or just "
                f"the block's name to use it everywhere") from None
    if _ANY in out and len(out) > 1:
        raise MofError(
            f"the {what} blocks are written both with and without a "
            f"slot; pick one spelling")
    return out


def _ordered(table: dict) -> list:
    """The keys of an assignment table, in a stable order.

    ``sorted`` cannot do it: the unkeyed marker is a string and every
    other key is an int or a pair of them.
    """
    return sorted(table, key=lambda k: (k == _ANY, str(k)))


def _spell(table: dict, token) -> str:
    if len(table) == 1 and _ANY in table:
        return table[_ANY]
    return ",".join(f"{token(k)}={table[k]}" for k in _ordered(table))


def _node_token(key) -> str:
    return str(key)


def _edge_token(key) -> str:
    return f"{key[0]}-{key[1]}"


def _node_key(text: str) -> int:
    return int(text)


def _edge_key(text: str) -> tuple[int, int]:
    a, sep, b = text.replace(",", "-").partition("-")
    if not sep:
        raise ValueError(text)
    pair = (int(a), int(b))
    return (min(pair), max(pair))


# ======================================================================
#  BUILDING
# ======================================================================

@dataclass
class BuildOutcome:
    """A framework, and everything worth saying about how it got here.

    ``rmsd`` and ``objective`` are PORMAKE's: the objective is what its
    cell relaxation converged to and the RMSD is how far the placed
    blocks are from the local geometry the net asked for.  They are the
    honest measure of whether the geometry is any good, and they are
    kept apart from ``identified``, which is about the *net* and does
    not move when the geometry does.
    """

    structure: object
    cif: Path
    request: BuildRequest
    n_atoms: int = 0
    max_rmsd: float = 0.0
    mean_rmsd: float = 0.0
    objective: float = 0.0
    #: How many node-to-linker and node-to-node joins arrived bonded.
    #: See :func:`bond_joints`: a joint can be longer than any distance
    #: criterion, so it is stored rather than left to perception.
    joints: int = 0
    #: What the RCSR calls the net that was drawn on the framework.
    identified: object = None
    #: The topology's own name, as PORMAKE's database spells it.
    asked: str = ""

    @property
    def net_name(self) -> str:
        return self.identified.name if self.identified else ""

    @property
    def net_agrees(self) -> bool:
        """Whether what came out is the net that was asked for."""
        return bool(self.net_name) and self.net_name == self.asked

    def verdict(self) -> str:
        """One line: the check, in the words it is worth reading in."""
        if not self.identified:
            return "the net could not be read back off the framework"
        if self.net_agrees:
            return f"the framework is {self.asked}, as asked"
        if not self.net_name:
            return (f"asked for {self.asked}; what was built is "
                    f"{self.identified.headline()}")
        return (f"asked for {self.asked} and built {self.net_name} -- "
                f"these are different nets")


def build(request: BuildRequest, directory, catalog: Catalog | None
          = None, log=None, trace=None) -> BuildOutcome:
    """Build one framework, and hand back the structure and the check.

    ``directory`` is where the CIF is written, which is the run folder
    when there is one and a temporary directory when there is not --
    the caller decides, because a build with no workspace should still
    answer rather than refuse.

    ``log`` is what this application says about the build and ``trace``
    is what PORMAKE says about it, defaulting to the same place.  They
    are separate because a shell wants the first on a status bar and
    the second only in the run log: five lines a person is waiting to
    read, against forty a builder emits on the way past.
    """
    catalog = catalog or Catalog.default()
    directory = Path(directory)
    topology, node_bbs, edge_bbs = _resolve(request, catalog)
    _say(log, f"topology {topology.name}: {topology.summary()}")

    cif = directory / f"{_safe(request.title())}.cif"
    with _Logging(trace if trace is not None else log) as listening:
        framework = _build(topology, node_bbs, edge_bbs, log)
        framework.write_cif(str(cif))
        if not cif.is_file():
            raise MofError(
                f"PORMAKE built the framework and then could not "
                f"write it out: {listening.failure or cif.name}")
    _say(log, f"wrote {cif.name}")

    from xtal.io import FORMATS

    structure = FORMATS.read(cif)
    structure.meta["title"] = request.title()
    structure.meta["mof"] = " ".join(request.spelled()).strip()
    outcome = BuildOutcome(
        structure=structure, cif=cif, request=request,
        n_atoms=structure.n_sites, asked=topology.name,
        max_rmsd=float(framework.info.get("max_rmsd", 0.0) or 0.0),
        mean_rmsd=float(framework.info.get("mean_rmsd", 0.0) or 0.0),
        objective=float(framework.info.get("relax_obj", 0.0) or 0.0))
    outcome.joints = bond_joints(structure, framework)
    _say(log, f"bonded {outcome.joints} joint(s) between blocks")
    drawn = draw_net(structure, framework)
    # Said before rather than after, because it is not free: naming a
    # net walks ten shells of an infinite graph and looks for the
    # smallest ring at every angle of every vertex, which is
    # milliseconds on pcu and half a minute on the worst net in the
    # database.  A status bar that has gone quiet for thirty seconds
    # should say what it is doing.
    _say(log, f"drew {drawn} net edge(s); identifying what came out")
    outcome.identified = check_net(structure)
    _say(log, outcome.verdict())
    return outcome


def _build(topology, node_bbs, edge_bbs, log):
    """The one call, with PORMAKE imported at the point of use."""
    _say(log, "loading PORMAKE")
    pormake = import_pormake()
    # By path rather than through ``pormake.Database``, which is a
    # name-to-file lookup over one topology folder and one block
    # folder.  Our catalogue already did that lookup, over as many
    # folders as the user has -- so a block they wrote themselves is
    # built with here for free rather than needing a second database.
    topo = pormake.Topology(str(topology.path))
    nodes = {int(k): pormake.BuildingBlock(str(v.path))
             for k, v in node_bbs.items()}
    edges = {tuple(int(i) for i in k): pormake.BuildingBlock(
        str(v.path)) for k, v in edge_bbs.items()}
    _say(log, f"placing {len(nodes)} node type(s) and "
              f"{len(edges)} linker type(s) on {topo.n_slots} slots")
    return pormake.Builder().build_by_type(
        topology=topo, node_bbs=nodes,
        edge_bbs=edges or None)


# ======================================================================
#  IMPORTING IT
# ======================================================================
#
# **PORMAKE is vendored**, at :mod:`xtal.mof.pormake`, trimmed of
# ``jax``, ``pymatgen`` and ``networkx``.  See
# ``xtal/mof/pormake/PROVENANCE.md`` for what changed and why.
#
# Both of the reasons this function used to be complicated are gone
# with them.  The import cost ten seconds warm and half a minute cold,
# and that was ``jax`` and ``pymatgen`` starting up, not PORMAKE; what
# is left is twelve modules over ``ase``, measured at 0.33 s cold in a
# fresh interpreter.  And it
# opened ``runtime.log`` in the current directory, in mode ``"w"``, at
# import -- somebody's home folder -- which took a swapped-out
# ``logging.FileHandler`` to contain and is now simply not done: see
# the note in ``pormake/log.py``.
#
# What remains is worth keeping.  The lock, because ``_rewire`` must
# happen exactly once and an import races on nothing else; and the
# rewiring itself, because PORMAKE's logger is how the builder reports
# what it did -- and, in one case, the *only* place it reports that a
# CIF was written and then deleted.

_LOCK = threading.Lock()

#: The build currently listening to PORMAKE's logger, or ``None``.
#: One build at a time, which is what the shell already enforces.
_listening = None


class _Forwarder(logging.Handler):
    """PORMAKE's console output, into the run log instead of stdout.

    Its logger prints ``>>> placing edges`` and forty more lines like
    it.  On a command line those are noise interleaved with the
    report; in the window they would go nowhere at all.  In the run
    log they are the trace of what the builder did, next to
    everything else that happened in the same run.

    **The errors are kept as well as forwarded**, and that is not
    tidiness.  ``Framework.write_cif`` catches whatever the write
    raises, deletes the half-written file and reports it *only*
    through this logger -- so a build whose CIF never appeared would
    otherwise fail several lines later on a missing file, with the
    reason nowhere.
    """

    def emit(self, record) -> None:
        listening = _listening
        if listening is None:
            return
        try:
            listening.take(record.levelno, self.format(record))
        except Exception:                       # noqa: BLE001, S110
            pass


def import_pormake():
    """The vendored ``pormake``, with its logger pointed at the run."""
    with _LOCK:
        name = "xtal.mof.pormake"
        if name in sys.modules:
            return sys.modules[name]
        import xtal.mof.pormake as pormake
        _rewire()
        return pormake


def _rewire() -> None:
    """Take PORMAKE's own handlers off its logger and put ours on.

    Closing them is what lets the temporary directory above go away:
    a file handler holds its file open, and on Windows an open file
    cannot be removed at all.
    """
    from xtal.mof.pormake.log import logger

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    forwarder = _Forwarder(logging.INFO)
    forwarder.setFormatter(logging.Formatter("pormake: %(message)s"))
    logger.addHandler(forwarder)


class _Logging:
    """PORMAKE's log lines going to this run's log, and no further."""

    def __init__(self, log):
        self.log = log
        self.errors: list[str] = []

    def take(self, level: int, text: str) -> None:
        if level >= logging.ERROR:
            self.errors.append(text)
        _say(self.log, text)

    @property
    def failure(self) -> str:
        return self.errors[0] if self.errors else ""

    def __enter__(self):
        global _listening
        _listening = self
        return self

    def __exit__(self, *_exc):
        global _listening
        _listening = None
        return False


def _resolve(request: BuildRequest, catalog: Catalog):
    """The topology and the blocks, checked against the slots.

    The check is the point: a block goes in a slot only when it has
    exactly as many connection points as the slot demands, and saying
    so here gives a sentence naming both instead of an assertion
    inside PORMAKE's locator.
    """
    topology = catalog.topology(request.topology)
    try:
        slots = topology.slots()
    except (CatalogError, ValueError) as exc:
        raise MofError(
            f"{topology.name}: the slots of this net cannot be worked "
            f"out from its file ({exc})") from None
    nodes, edges = {}, {}
    for slot in slots:
        name = request.block_for(slot)
        if not name:
            if slot.is_edge:
                continue            # no linker is a legitimate answer
            raise MofError(
                f"{topology.name} has a {slot.coordination}-connected "
                f"node slot ({slot.label}) with nothing in it")
        block = catalog.building_block(name)
        if block.n_connections != slot.coordination:
            raise MofError(
                f"{block.name} has {block.n_connections} connection "
                f"point(s) and {slot.label.lower()} needs "
                f"{slot.coordination}")
        (edges if slot.is_edge else nodes)[slot.key] = block
    return topology, nodes, edges


# ======================================================================
#  THE NET, DRAWN ON WHAT CAME BACK
# ======================================================================

def draw_net(structure, framework) -> int:
    """Put the net's edges on the framework as topology bonds.

    A vertex has to be an *atom*, because that is what a bond joins,
    so each node slot is represented by the atom of its own block
    nearest that block's centroid -- which PORMAKE defines as the mean
    of the connection points and is the point it aligned with the
    slot.  For a metal node that is the metal.

    The image comes from the net and not from the geometry, and it has
    to: two nodes joined through a linker are twenty Angstrom apart,
    and there is no distance at which "the same cell or the next one"
    could be guessed from their coordinates.

    Returns how many edges were drawn.
    """
    topology = framework.info["topology"]
    blocks = framework.info["located_bbs"]
    representative = _representatives(topology, blocks)
    drawn = 0
    for i, j, image in _edges_of(topology):
        if i not in representative or j not in representative:
            continue                            # pragma: no cover
        if structure.add_bond(Bond(i=representative[i],
                                   j=representative[j],
                                   image=image, kind=TOPOLOGY)):
            drawn += 1
    return drawn


def bond_joints(structure, framework) -> int:
    """Bond the joints PORMAKE made between one block and the next.

    A framework is blocks placed on a net and then *joined*: the
    connection points are fused and the bond that replaces them is the
    node-to-linker or node-to-node join.  Every bond inside a block
    arrives at a chemical length and perception finds it; a joint does
    not have to.  A carboxylate onto a metal, a nitrogen onto a zinc,
    a block whose connection points were written a little long -- the
    join can be well past any distance criterion, and the framework
    then opens with the linker floating unbonded beside the node it was
    built onto, which is the one bond in the structure that nobody
    would think to draw by hand.

    So the joints are stored as the user's own bonds, from what the
    builder did rather than from a distance: PORMAKE knows exactly
    which pairs it fused, and a bond that is *explicit* survives
    Recalculate Bonds and never has to answer for its length.

    **A joint is a bond the joining step made, not a bond between two
    blocks**, and the difference is a whole class of framework.  A net
    with one node slot and no linker -- pcu on N59 -- joins every node
    to *its own periodic image*, so both ends of the join are the same
    block and an inter-block test finds nothing to bond.  What
    separates a join from chemistry is that the blocks' own bond lists
    do not contain it, which is true in both cases and is what this
    subtracts.

    Returns how many were added.
    """
    blocks = framework.info["located_bbs"]
    inside = _intra_block_bonds(blocks)
    known = _block_of_atoms(blocks)
    labels = {site.label: index
              for index, site in enumerate(structure.sites)}
    frac = np.asarray(structure.frac, dtype=float)
    symbols = framework.atoms.symbols
    fresh, seen = [], {b.key(structure.space_group)
                       for b in structure.bonds}
    for i, j in framework.bonds:
        i, j = int(i), int(j)
        if i not in known or j not in known:        # pragma: no cover
            continue
        if (min(i, j), max(i, j)) in inside:
            continue
        # By label rather than by position.  The CIF is written in the
        # framework's own atom order and read back in it, and the
        # labels say so -- but the mapping is what this depends on, and
        # a reader that ever reorders should fail to find an atom
        # rather than bond the wrong one.
        ends = (labels.get(f"{symbols[i]}{i}"),
                labels.get(f"{symbols[j]}{j}"))
        if None in ends:                            # pragma: no cover
            continue
        a, b = ends
        image = tuple(int(v) for v in np.round(frac[a] - frac[b]))
        bond = Bond(a, b, image)
        if bond.key(structure.space_group) in seen:
            continue
        seen.add(bond.key(structure.space_group))
        fresh.append(bond)
    if fresh:
        # One change and not one per bond: every add drops the P1
        # expansion, and a framework re-expanded once per joint is the
        # stall that `set_bonds` exists to avoid.
        structure.set_bonds(list(structure.bonds) + fresh)
    return len(fresh)


def _intra_block_bonds(blocks) -> set[tuple[int, int]]:
    """Every bond a placed block brought with it, in framework indices.

    A block's own bond list is in its own atom numbering and includes
    its connection points; the framework's is the blocks concatenated
    with those points taken out.  So each block's bonds are carried
    over by the same walk :func:`_block_of_atoms` makes -- position
    among the kept atoms, plus where the block starts -- and the bonds
    that touched an ``X`` are dropped, because the atom on that end is
    not in the framework to name.

    What is left over when these are subtracted from the framework's
    bonds is exactly what the joining step added.  See
    :func:`bond_joints`.
    """
    out: set[tuple[int, int]] = set()
    offset = 0
    for block in blocks:
        if block is None:
            continue
        moved: dict[int, int] = {}
        for local, symbol in enumerate(
                block.atoms.get_chemical_symbols()):
            if symbol != CONNECTION:
                moved[local] = offset + len(moved)
        for u, v in np.asarray(block.bonds, dtype=int).reshape(-1, 2):
            a, b = moved.get(int(u)), moved.get(int(v))
            if a is not None and b is not None:
                out.add((min(a, b), max(a, b)))
        offset += len(moved)
    return out


def _block_of_atoms(blocks) -> dict[int, int]:
    """Framework atom index -> the slot whose block it came from.

    The framework's atoms are the located blocks concatenated in slot
    order with the connection points removed, so this is arithmetic
    rather than a search -- the same ordering :func:`_representatives`
    relies on, shared so that the two cannot drift apart.
    """
    out: dict[int, int] = {}
    offset = 0
    for slot, block in enumerate(blocks):
        if block is None:
            continue
        kept = sum(1 for symbol in block.atoms.get_chemical_symbols()
                   if symbol != CONNECTION)
        for k in range(kept):
            out[offset + k] = slot
        offset += kept
    return out


def _representatives(topology, blocks) -> dict[int, int]:
    """Node slot -> the index, in the framework, of its vertex atom.

    The framework's atoms are the located blocks concatenated in slot
    order with the connection points removed, which is what makes the
    index arithmetic rather than a search.  Stated here because it is
    PORMAKE's internal ordering and nothing enforces it from outside;
    the net check downstream is what would notice if it changed.

    **Which atom stands for the slot is decided by the slot, not by
    the block.**  The topology's own atoms are in the framework's
    frame -- the builder relaxes the cell and puts both in it -- so
    the vertex is the block's atom nearest the point the block was
    placed on.  For a metal node that is the metal.  The block's own
    ``centroid`` would say the same thing and is not usable: it is the
    mean of the connection points, and a framework built with no
    linker has had them consumed by the bonds between the nodes.
    """
    out: dict[int, int] = {}
    slots = np.asarray(topology.atoms.get_positions(), dtype=float)
    nodes = {int(s) for s in topology.node_indices}
    owner = _block_of_atoms(blocks)
    starts: dict[int, int] = {}
    for atom in sorted(owner):
        starts.setdefault(owner[atom], atom)
    for slot, block in enumerate(blocks):
        if block is None or slot not in nodes:
            continue
        kept = [i for i, symbol in
                enumerate(block.atoms.get_chemical_symbols())
                if symbol != CONNECTION]
        if not kept:                                # pragma: no cover
            continue
        positions = block.atoms.get_positions()[kept]
        nearest = int(np.argmin(
            ((positions - slots[slot]) ** 2).sum(axis=1)))
        out[slot] = starts[slot] + nearest
    return out


def _edges_of(topology) -> list[tuple[int, int, tuple[int, int, int]]]:
    """Every edge of the net, as ``(node slot, node slot, image)``.

    An edge slot sits between exactly two node slots and PORMAKE
    records each neighbour as a minimum-image displacement rather than
    as a cell offset, so the offset is recovered by taking the
    displaced point back to the vertex it is a copy of.  The edge's
    image is the difference of the two, which is what makes it
    independent of where the edge centre itself was put.
    """
    frac = topology.atoms.get_scaled_positions()
    inverse = np.linalg.inv(np.asarray(topology.atoms.cell))
    out = []
    for slot in topology.edge_indices:
        ends = []
        for neighbour in topology.neighbor_list[int(slot)]:
            index = int(neighbour.index)
            displaced = frac[int(slot)] + (
                np.asarray(neighbour.distance_vector) @ inverse)
            ends.append((index,
                         np.round(displaced - frac[index])))
        if len(ends) != 2:                      # pragma: no cover
            continue
        (i, shift_i), (j, shift_j) = ends
        out.append((i, j, tuple(int(v) for v in shift_j - shift_i)))
    return out


def check_net(structure):
    """What the net drawn on this framework actually is.

    Read back off the structure with the same two functions the Net
    panel uses, so this is a statement about the bonds that are stored
    in the file and not about anything PORMAKE said while writing it.
    """
    from xtal.analysis import net_of, rcsr

    return rcsr.describe(net_of(structure))


# ======================================================================
#  SMALL THINGS
# ======================================================================

def _say(log, text: str) -> None:
    if log is not None:
        log(text)


def _safe(text: str) -> str:
    from xtal.workspace import safe_name

    return safe_name(text, "framework")
