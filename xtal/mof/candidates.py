"""
xtal.mof.candidates
===================
The frameworks a synthesis forecast names, put together from the
catalogue and tried with the builder.

:mod:`xtal.mof.precedent` says which nodes and nets the nearest
published syntheses formed; this turns that into builds.  Three steps,
each a function a test can call alone:

* **the linker as a block** (:func:`linker_block`): the typed
  linker's carboxylic acids become connection points on the carbon
  they hung off, because in this catalogue the carboxylate is the
  node's -- PORMAKE's N16 is Zn4O(CO2)6 and its E14 is the phenylene
  between.  Two carboxylates make an edge; three or more make an
  organic node, as BTC is in HKUST-1, joined to the metal directly.
  Only carboxylates: a pyridyl or an azolate donor is a different
  node chemistry the catalogue writes differently, and is refused by
  name rather than built wrong;
* **the candidates** (:func:`plan`): each voted net the catalogue has,
  with each voted node, filled with catalogue blocks whose metals are
  exactly the node's (``Zr6``) and whose connections are the slot's,
  plain carboxylate clusters first.  Ranked by the product of the two
  shares, which is the vote's own estimate of the pair;
* **the trial** (:func:`attempt`): each built in rank order until the
  time runs out, and kept only if the builder reads back the net it
  was asked for.

A build that comes out is a starting geometry on a net the precedents
made with these metals and this linker -- not a prediction that it is
the phase that forms, and the report says so.
"""

from __future__ import annotations

import hashlib
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from xtal.mof import precedent

#: Voted nets and nodes considered, best first.  Past five of either
#: the shares are a few percent each, and the product of two is noise.
NETS = 5
NODES = 5

#: Catalogue blocks tried for one node in one slot.  The plain
#: carboxylate clusters come first, and two of them are usually two
#: drawings of the same cluster (N14 and N15 are both Zr6(CO2)6).
BLOCKS = 2

#: Seconds of test-building before the rest are listed untried.  A
#: build is about a second on pcu, fcu or tbo; naming what came out is
#: the slow half on an unusual net.
BUDGET = 30.0


class CandidateError(ValueError):
    """The linker cannot be made into a block for this catalogue."""


# ======================================================================
#  THE LINKER
# ======================================================================

@dataclass(frozen=True)
class LinkerBlock:
    """A typed linker, ready to go in a slot."""

    smiles: str             # the linker as typed, uncharged
    starred: str            # carboxylates replaced by connection points
    topicity: int
    name: str               # the block's file name, without .xyz

    @property
    def is_edge(self) -> bool:
        return self.topicity == 2


#: A carboxylic acid or carboxylate and the carbon it hangs off.
_CARBOXYL = "[#6:1]-[CX3](=[OX1])-[OX2H1,OX1-]"


def starred(smiles: str) -> tuple[str, int]:
    """The linker with each carboxyl swapped for ``*``, and how many.

    ``OC(=O)c1ccc(cc1)C(=O)O`` is ``*c1ccc(*)cc1``, 2.  Needs RDKit.
    """
    from rdkit import Chem

    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise CandidateError(f"{smiles!r} is not a molecule")
    pattern = Chem.MolFromSmarts(_CARBOXYL)
    matches = molecule.GetSubstructMatches(pattern)
    if not matches:
        raise CandidateError(
            f"{smiles} has no carboxylate, and only carboxylate "
            f"linkers are test-built for now: a pyridyl or an azolate "
            f"meets its metal in a node this catalogue draws "
            f"differently")
    # The carboxyl carbon *becomes* the point rather than a new atom
    # standing in for a deleted one: a double bond's E or Z is stored
    # against its neighbours, and deleting them took fumarate's trans
    # with it -- *C=C*, which embeds as maleate as readily.
    editable = Chem.RWMol(molecule)
    gone = set()
    for _carbon, carboxyl, oxo, hydroxyl in matches:
        atom = editable.GetAtomWithIdx(carboxyl)
        atom.SetAtomicNum(0)
        atom.SetFormalCharge(0)
        atom.SetNoImplicit(True)
        atom.SetIsAromatic(False)
        gone.update((oxo, hydroxyl))
    for index in sorted(gone, reverse=True):
        editable.RemoveAtom(index)
    result = editable.GetMol()
    Chem.SanitizeMol(result)
    return Chem.MolToSmiles(result), len(matches)


def linker_block(text: str) -> LinkerBlock:
    """The first linker of a query, as a block to be written."""
    smiles, _ = precedent.linker_key(text)
    star, topicity = starred(smiles)
    digest = hashlib.sha1(smiles.encode("utf-8")).hexdigest()[:8]
    return LinkerBlock(smiles, star, topicity, f"SYN-{digest}")


def write_linker(linker: LinkerBlock, folder) -> Path:
    """Embed the linker arms-out and write it as ``<name>.xyz``.

    The same embedding the isoreticular series uses
    (:func:`xtal.mof.linkers.embed_extended`), so a typed BDC is the
    shape a drawn one is.  Needs RDKit.
    """
    from xtal.io.atomic import write_text
    from xtal.mof.block import block_string
    from xtal.mof.linkers import embed_extended

    path = Path(folder) / f"{linker.name}.xyz"
    if not path.is_file():
        molecule = embed_extended(linker.starred, name=linker.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_text(path, block_string(molecule.to_structure()))
    return path


# ======================================================================
#  THE CANDIDATES
# ======================================================================

@dataclass(frozen=True)
class Candidate:
    """One framework to try: a net, a block per slot, and why."""

    net: str
    nodes: tuple[tuple[int, str], ...]      # (node type, block)
    edge: str                               # "" for nodes joined
    node: str                               # the voted node, "Zr6"
    score: float                            # net share x node share

    def request(self):
        from xtal.mof.build import BuildRequest

        nodes = ",".join(f"{k}={name}" for k, name in self.nodes)
        return BuildRequest.parse(self.net, nodes, self.edge)

    @property
    def spelled(self) -> str:
        """The ``xtal run mof.build`` parameters that build it again."""
        nodes = ",".join(f"{k}={name}" for k, name in self.nodes)
        parts = [f"topology={self.net}", f"nodes={nodes}"]
        if self.edge:
            parts.append(f"edges={self.edge}")
        return " ".join(f"-p {p}" for p in parts)


@dataclass(frozen=True)
class Skipped:
    """A voted net or node nothing could be built for, and why."""

    what: str
    why: str


def metals_of(composition: dict) -> dict:
    return {s: n for s, n in composition.items()
            if s not in precedent.NONMETALS}


def node_metals(formula: str) -> dict:
    """``Zr6`` as ``{'Zr': 6}``; ``CuZn`` as one of each."""
    import re

    return {s: int(n or 1)
            for s, n in re.findall(r"([A-Z][a-z]?)(\d*)", formula)}


def _plain_carboxylate(block) -> bool:
    """Whether a cluster is metals, oxygens and one carboxylate carbon
    per connection -- the node a carboxylate linker meets.  Others
    with the right metals carry pyridines or porphyrins of their own,
    which the typed linker is not."""
    composition = block.composition
    return composition.get("C", 0) == block.n_connections \
        and "N" not in composition


def node_blocks(catalog, metals: dict, coordination: int) -> list:
    """Catalogue carboxylate clusters with exactly these metals and
    connections, by name.

    Only plain ones.  Preferring them and falling back on the rest
    put a zinc porphyrin (N2) and a tris-pyridyl zinc (N151) on the
    first rows of Zn + BDC: the right metal, the right count, and a
    node the typed linker cannot make.  A slot nothing plain fits is
    skipped, with the reason, instead.
    """
    found = [b for b in catalog.fitting(coordination)
             if b.has_metal and metals_of(b.composition) == metals
             and _plain_carboxylate(b)]
    found.sort(key=lambda b: b.name)
    return found


def plan(forecast: precedent.Forecast, linker: LinkerBlock, catalog,
         nets: int = NETS, nodes: int = NODES,
         blocks: int = BLOCKS) -> tuple[list[Candidate], list[Skipped]]:
    """Every candidate the vote names, best first, and what was not.

    A net gets the linker in its two-connected edges when the linker
    has two carboxylates, and in its node slots of the linker's
    topicity otherwise; every other node slot gets a metal block.  A
    net with no slot for the linker, or a node with no block, is
    *skipped* with the reason -- said, because a voted net that cannot
    be tried is something the person should know was not.
    """
    have = {t.name for t in catalog.topologies()}
    out, skipped = [], []
    # One row per node, not per net and node: "Zr" missing from five
    # nets is one fact, and five rows of it buried the builds.
    unfit: dict[str, list[str]] = {}
    for net_share in forecast.nets[:nets]:
        net = net_share.value
        if net not in have:
            skipped.append(Skipped(net, "not in the builder's nets"))
            continue
        slots = catalog.topology(net).slots()
        node_slots = [s for s in slots if not s.is_edge]
        edge_slots = [s for s in slots if s.is_edge]
        if linker.is_edge:
            if not edge_slots:
                skipped.append(Skipped(net, "has no edge for a "
                                            "ditopic linker"))
                continue
            organic, metal_slots = [], node_slots
        else:
            organic = [s for s in node_slots
                       if s.coordination == linker.topicity]
            metal_slots = [s for s in node_slots if s not in organic]
            if not organic or not metal_slots:
                skipped.append(Skipped(
                    net, f"has no {linker.topicity}-connected node "
                         f"beside a metal one for this linker"))
                continue
        for node_share in forecast.nodes[:nodes]:
            metals = node_metals(node_share.value)
            options = {}
            for slot in metal_slots:
                found = node_blocks(catalog, metals, slot.coordination)
                if not found:
                    break
                options[slot.key] = [b.name for b in found[:blocks]]
            if len(options) < len(metal_slots):
                needs = sorted({s.coordination for s in metal_slots})
                unfit.setdefault(node_share.value, []).append(
                    f"{net} ({'/'.join(map(str, needs))}-c)")
                continue
            for choice in _choices(options):
                assigned = dict(choice)
                for slot in organic:
                    assigned[slot.key] = linker.name
                out.append(Candidate(
                    net=net,
                    nodes=tuple(sorted(assigned.items())),
                    edge=linker.name if linker.is_edge else "",
                    node=node_share.value,
                    score=round(net_share.share * node_share.share, 4)))
    for node, where in unfit.items():
        skipped.append(Skipped(
            node, f"no carboxylate cluster of exactly {node} in the "
                  f"catalogue for {', '.join(where)}"))
    out.sort(key=lambda c: (-c.score, c.net, c.nodes))
    return out, skipped


def _choices(options: dict):
    """One block per slot, every combination, first blocks first."""
    import itertools

    keys = sorted(options)
    for picked in itertools.product(*(options[k] for k in keys)):
        yield tuple(zip(keys, picked, strict=True))


# ======================================================================
#  THE TRIAL
# ======================================================================

@dataclass
class Attempt:
    """One candidate, tried."""

    candidate: Candidate
    built: bool = False
    confirmed: bool = False     # the net read back is the one asked
    verdict: str = ""
    atoms: int = 0
    overlaps: int = 0
    seconds: float = 0.0
    structure: object = field(default=None, repr=False)

    @property
    def status(self) -> str:
        if not self.built:
            return "did not build"
        if not self.confirmed:
            return "built, a different net"
        return "built, overlapping atoms" if self.overlaps else "built"


@dataclass
class Trial:
    attempts: list[Attempt]
    untried: list[Candidate]
    skipped: list[Skipped]
    linker: LinkerBlock | None = None

    @property
    def best(self) -> Attempt | None:
        """The highest-ranked build that is the net it was asked to
        be with nothing overlapping; failing that, the highest-ranked
        that is the net."""
        confirmed = [a for a in self.attempts if a.confirmed]
        clean = [a for a in confirmed if not a.overlaps]
        return (clean or confirmed or [None])[0]


def attempt(candidates, catalog, directory=None, budget: float = BUDGET,
            log=None, cancelled=lambda: False) -> tuple[list, list]:
    """Build candidates in order until ``budget`` seconds are spent.

    Returns ``(attempts, untried)``.  The budget is checked between
    builds, never during one -- PORMAKE builds in a single call with
    nothing to poll -- so the last build may finish past it.  Only a
    confirmed build keeps its structure; the rest are a line each.
    """
    from xtal.mof.build import build

    holder = None
    if directory is None:
        holder = tempfile.TemporaryDirectory(prefix="synthesis-")
        directory = holder.name
    start = time.perf_counter()
    attempts, untried = [], []
    try:
        for candidate in candidates:
            if attempts and (time.perf_counter() - start > budget
                             or cancelled()):
                untried.append(candidate)
                continue
            begun = time.perf_counter()
            tried = Attempt(candidate)
            folder = Path(directory) / f"{len(attempts) + 1:02d}"
            folder.mkdir(parents=True, exist_ok=True)
            try:
                outcome = build(candidate.request(), folder, catalog)
            except Exception as exc:                # noqa: BLE001
                # PORMAKE's locator raises what it raises -- an
                # assertion, an index error -- on a block that cannot
                # be placed; any of it is this candidate failing, and
                # the next one is still worth trying.
                tried.verdict = str(exc) or type(exc).__name__
            else:
                tried.built = True
                tried.confirmed = outcome.net_agrees
                tried.verdict = outcome.verdict()
                tried.atoms = outcome.n_atoms
                tried.overlaps = len(outcome.overlaps)
                if tried.confirmed:
                    tried.structure = outcome.structure
            tried.seconds = round(time.perf_counter() - begun, 2)
            if log is not None:
                log(f"{candidate.net} with "
                    f"{', '.join(n for _, n in candidate.nodes)}: "
                    f"{tried.status} ({tried.seconds:.1f} s)")
            attempts.append(tried)
    finally:
        if holder is not None:
            holder.cleanup()
    return attempts, untried


def trial(forecast: precedent.Forecast, catalog_for, folder=None,
          budget: float = BUDGET, log=None,
          cancelled=lambda: False) -> Trial:
    """The whole of it: the linker written, the plan, the builds.

    ``catalog_for(blocks_folder)`` is handed the folder the linker
    block was written to and returns the catalogue to build from, so
    the module can add the workspace's own blocks and a test can hand
    a catalogue of its own.  ``folder`` keeps the linker block (the
    workspace's ``blocks/``, so ``xtal run mof.build`` finds it again);
    ``None`` writes it to a temporary folder that goes with the run.
    """
    linker = linker_block(forecast.query.linkers[0][0])
    holder = None
    if folder is None:
        holder = tempfile.TemporaryDirectory(prefix="synthesis-blocks-")
        folder = holder.name
    try:
        write_linker(linker, folder)
        catalog = catalog_for(Path(folder))
        candidates, skipped = plan(forecast, linker, catalog)
        attempts, untried = attempt(candidates, catalog, budget=budget,
                                    log=log, cancelled=cancelled)
    finally:
        if holder is not None:
            holder.cleanup()
    return Trial(attempts, untried, skipped, linker)
