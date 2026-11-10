"""
xtal.modules.synthesis
======================
What a synthesis is likely to make, as a registry entry: two actions.

**From a synthesis...** is the vote alone (:mod:`xtal.mof.precedent`):
which nodes and nets the nearest published syntheses formed, each with
its share and the precedents it stood on.  A report and no structure,
no document needed and no run folder, so it answers in a second.

**Build the likely frameworks...** votes and then builds what the vote
names (:mod:`xtal.mof.candidates`): the typed linker made a block,
each voted net the builder has filled with catalogue clusters of the
voted metals, tried best-ranked first for as long as it is given, and
the best that comes out as the net it was asked to be opens in a new
tab.  Every row says how to build it again with ``xtal run
mof.build``, which is why the linker block goes into the workspace's
``blocks/``.  It needs the MOF builder as well as RDKit.

The checks are ``find_spec``, as the molecule builder's is.
"""

from __future__ import annotations

import re

from xtal.build import NOT_INSTALLED, installed
from xtal.modules.job import JobResult
from xtal.modules.registry import (
    MODULES,
    Action,
    Availability,
    Module,
    Param,
)
from xtal.modules.report import Report, Row, Table
from xtal.mof import precedent

__all__ = ["PARAMS", "SYNTHESIS", "forecast", "register"]

PARAMS = (
    Param("metal", "Metal source", kind="text",
          default="zinc nitrate hexahydrate",
          help="The metal salt by name ('zinc nitrate hexahydrate', "
               "'copper(II) acetate'), by formula ('Zn(NO3)2·6H2O', "
               "'ZrOCl2') or the metal alone ('Zr').  The counter-ion "
               "is compared where the precedent recorded one."),
    Param("linkers", "Linkers", kind="text", default="BDC",
          help="One to three, separated by commas or semicolons: a "
               "SMILES, or a common name (BDC, BTC, NH2-BDC, BPDC, "
               "dobdc, 2-methylimidazole, 4,4'-bipyridine, DABCO).  "
               "The acid or its anion, either is read."),
    Param("solvents", "Solvents", kind="text", default="DMF",
          help="Separated by commas: DMF, DEF, DMA, water, EtOH, "
               "MeOH, MeCN, DMSO, NMP, dioxane, pyridine, THF.  One "
               "not recognised is said in the answer and left out of "
               "the comparison."),
    Param("temperature", "Temperature", kind="text", default="",
          help="Reaction temperature in C.  Left empty, it is not "
               "compared."),
    Param("neighbours", "Precedents that vote", kind="int",
          default=precedent.NEIGHBOURS, minimum=1, maximum=100,
          help="How many of the most similar syntheses vote.  Fewer "
               "put the net that formed first slightly more often; "
               "more put it in the first five more often."),
)

BUILD_PARAMS = (
    Param("budget", "Time to spend building", kind="float",
          default=30.0, minimum=1.0, maximum=600.0, decimals=0,
          suffix=" s",
          help="Seconds of test builds, best-ranked first; what is "
               "left is listed untried.  A build is about a second on "
               "pcu, fcu or tbo and longer on an unusual net, and the "
               "last one started may finish past the time."),
)


def _can_build() -> Availability:
    """The vote's needs and the MOF builder's: RDKit and ase."""
    from xtal.modules import mof

    voted = available()
    if not voted:
        return voted
    return mof.available()


#: A comma between two digits is part of a name -- 4,4'-bipyridine,
#: 1,4-dioxane -- and every other one separates two entries.
_SEPARATOR = re.compile(r";|\n|(?<!\d),|,(?!\d)")


def split(text: str) -> list[str]:
    return [part.strip() for part in _SEPARATOR.split(str(text or ""))
            if part.strip()]


def available() -> Availability:
    if not installed():
        return NOT_INSTALLED
    if not precedent.available():
        return Availability(False, "The precedent table is missing "
                                   "from this installation.")
    return Availability(True, "RDKit")


def forecast(job) -> JobResult:
    """Vote the nearest precedents; a report, never a structure."""
    try:
        answer = _vote(job)
    except ValueError as exc:
        # PrecedentError is a ValueError, and so is a temperature that
        # is not a number.
        return JobResult.failure(str(exc))
    job.say(f"voted {len(answer.neighbours)} precedents from "
            f"{answer.source}")
    return JobResult(message=_said(answer), report=report(answer))


def _said(answer: precedent.Forecast) -> str:
    top = answer.nets[0] if answer.nets else None
    return (f"Likeliest net {top.value} ({top.share:.0%} of the "
            f"vote); {answer.novelty.sentence()}"
            if top else "No precedent close enough named a net.")


def _vote(job):
    """The query and the forecast, or the sentence saying why not."""
    temperature = str(job.param("temperature", "") or "").strip()
    query = precedent.Query.read(
        job.param("metal", ""), split(job.param("linkers", "")),
        split(job.param("solvents", "")),
        float(temperature) if temperature else None)
    return precedent.forecast(
        query, neighbours=int(job.param("neighbours",
                                        precedent.NEIGHBOURS)))


def build_likely(job) -> JobResult:
    """Vote, then build what the vote names; the best build opens.

    The linker block is written into the workspace's ``blocks/`` when
    there is a workspace, which is where the MOF builder reads the
    blocks a person drew -- so each row's parameters rebuild it with
    ``xtal run mof.build``.  Without one it goes with the run.
    """
    from xtal.mof import candidates
    from xtal.mof.catalog import Catalog

    try:
        answer = _vote(job)
        candidates.linker_block(answer.query.linkers[0][0])
    except ValueError as exc:
        # PrecedentError and CandidateError are both ValueErrors: a
        # query that cannot be read and a linker that is not a
        # carboxylate are both the person's to change.
        return JobResult.failure(str(exc))
    job.say(f"voted {len(answer.neighbours)} precedents; building what "
            f"they name")
    folder = None
    if job.folder is not None:
        from xtal.workspace import Workspace

        workspace = Workspace.find(job.folder.path)
        if workspace is not None:
            folder = workspace.blocks
    if folder is None:
        job.note("no workspace open, so the linker block is not kept "
                 "and the rows below cannot be rebuilt by name")

    def catalog_for(blocks):
        return Catalog.default(also_blocks=(str(blocks),))

    tried = candidates.trial(
        answer, catalog_for, folder=folder,
        budget=float(job.param("budget", candidates.BUDGET)),
        log=job.say, cancelled=lambda: job.cancelled)
    if job.cancelled:
        return JobResult.stopped("stopped between builds")
    best = tried.best
    voted = report(answer)
    result = Report(title="Build the likely frameworks",
                    blocks=_tried(tried) + voted.blocks,
                    note=voted.note)
    if best is None:
        return JobResult(
            message=f"Nothing the vote names built as asked. "
                    f"{_said(answer)}",
            report=result)
    structure = best.structure
    candidate = best.candidate
    structure.meta.setdefault("warnings", []).append(
        "A starting geometry on a net the nearest precedents formed, "
        "not a prediction that this is the phase that forms.")
    return JobResult(
        message=f"Built {candidate.net} with "
                f"{', '.join(n for _, n in candidate.nodes)} "
                f"({best.atoms} atoms), the best-ranked of "
                f"{sum(a.confirmed for a in tried.attempts)} that "
                f"built as asked. {_said(answer)}",
        structure=structure, report=result)


def _tried(tried) -> tuple[Table, ...]:
    rows = [Row.of(
        a.candidate.net,
        ", ".join(f"{k}={n}" for k, n in a.candidate.nodes),
        a.candidate.edge or "none",
        f"{a.candidate.score:.3f}", a.status,
        a.atoms or "--", a.candidate.spelled,
        note=a.verdict)
        for a in tried.attempts]
    rows += [Row.of(c.net, ", ".join(f"{k}={n}" for k, n in c.nodes),
                    c.edge or "none", f"{c.score:.3f}",
                    "not tried: out of time", "--", c.spelled)
             for c in tried.untried]
    linker = tried.linker
    built = Table(
        title="Frameworks tried",
        columns=("Net", "Nodes", "Edges", "Score", "Result", "Atoms",
                 "Rebuild with xtal run mof.build"),
        rows=tuple(rows),
        note=(f"The linker as block {linker.name}: {linker.starred}, "
              f"its carboxylates the nodes'.  Score is the net's share "
              f"times the node's.  A build is a starting geometry on a "
              f"net the precedents formed, not the phase that forms."))
    if not tried.skipped:
        return (built,)
    # A table of its own: a reason is a sentence, and in the column
    # beside the builds it widened every row to its length.
    return built, Table(
        title="Voted, but nothing to try it with",
        columns=("Net or node", "Why"),
        rows=tuple(Row.of(s.what, s.why) for s in tried.skipped))


def _in_builder() -> set[str] | None:
    """The nets the MOF builder can build on, or ``None`` if unknown.

    Read from the catalogue, which costs half a second the first time
    and nothing after; a catalogue that will not load is no reason to
    fail a vote, so the column is left out instead.
    """
    try:
        from xtal.mof.catalog import Catalog
        return {t.name for t in Catalog.default().topologies()}
    except Exception:                               # noqa: BLE001
        return None


def report(answer: precedent.Forecast) -> Report:
    query, novelty = answer.query, answer.novelty
    salt = query.salt
    read = Table(title="What was read", rows=(
        Row("Metal", salt.metal, "",
            ", ".join(salt.anions) if salt.anions
            else "no counter-ion read"),
        Row("Linkers", "; ".join(s for s, _ in query.linkers)),
        # The unread ones in the value, not the note: a note is a
        # tooltip, and a solvent silently dropped moves the vote.
        Row("Solvents", (", ".join(precedent.solvent_name(c)
                                   for c in query.solvents) or "none")
            + (" (not recognised, left out: "
               + ", ".join(query.unread_solvents) + ")"
               if query.unread_solvents else "")),
        Row("Temperature", f"{query.temperature:g}"
            if query.temperature is not None else "not given",
            "C" if query.temperature is not None else ""),
    ))
    builder = _in_builder()
    nets = Table(
        title="Nets the nearest precedents formed",
        columns=("Net", "Share", "Precedents", "In the builder"),
        rows=tuple(Row.of(
            s.value, f"{s.share:.0%}", s.support,
            "unknown" if builder is None
            else ("yes" if s.value in builder else "no"))
            for s in answer.nets),
        note=answer.basis)
    nodes = Table(
        title="Nodes, by their metals",
        columns=("Node", "Share", "Precedents"),
        rows=tuple(Row.of(s.value, f"{s.share:.0%}", s.support)
                   for s in answer.nodes))
    blocks = [read, nets, nodes]
    if answer.interpenetrated is not None:
        blocks.append(Table(title="Interpenetration", rows=(
            Row("Interpenetrated",
                f"{answer.interpenetrated.share:.0%}", "",
                "of the weight of those whose MOFid says either way"),
        )))
    blocks.append(Table(
        title="The precedents that voted",
        columns=("Refcode", "Similarity", "Metal", "Net",
                 "Conditions"),
        rows=tuple(Row.of(
            n.precedent.refcode, f"{n.similarity:.3f}",
            "".join(n.precedent.metals), n.precedent.net or "--",
            _conditions(n.precedent))
            for n in answer.neighbours),
        note="CSD refcodes; an entry from a paper's SI keeps its "
             "file's name."))
    warning = "" if novelty.metal_with_linker_seen \
        else novelty.sentence()
    return Report(
        title="From a synthesis",
        blocks=tuple(blocks),
        note=f"{novelty.sentence()}  Closest precedent "
             f"{novelty.closest:.3f} of {novelty.precedents} in "
             f"{answer.source}." + (f"  {warning}" if warning else ""))


def _conditions(p: precedent.Precedent) -> str:
    if not p.has_conditions:
        return "not recorded"
    parts = []
    if p.solvents:
        parts.append("/".join(precedent.solvent_name(c)
                              for c in p.solvents))
    if p.temperature is not None:
        parts.append(f"{p.temperature:g} C")
    if p.anions:
        parts.append(",".join(p.anions))
    return "; ".join(parts)


SYNTHESIS = Module(
    name="synthesis",
    label="From a synthesis",
    description="What a metal salt, linkers, solvents and a "
                "temperature are likely to make, read off the most "
                "similar published syntheses: the nodes and nets they "
                "formed, each with its share of the vote and the "
                "precedents behind it.  Experimental: a vote, not a "
                "prediction.",
    order=28, group="build",
    check=available,
    provides=frozenset({"structure", "table"}),
    actions=(
        Action(name="forecast", label="From a synthesis...",
               tip="The nodes and nets the nearest published "
                   "syntheses formed",
               needs_structure=False,
               writes_run_folder=False,
               params=PARAMS,
               run=forecast),
        Action(name="build", label="Build the likely frameworks...",
               tip="Vote, then build the nets and nodes the nearest "
                   "syntheses formed; the best build opens in a new "
                   "tab",
               kind="build",
               needs_structure=False,
               check=_can_build,
               params=PARAMS + BUILD_PARAMS,
               run=build_likely),
    ),
)


def register(registry=MODULES) -> Module:
    return registry.register(SYNTHESIS)
