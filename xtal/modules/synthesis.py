"""
xtal.modules.synthesis
======================
What a synthesis is likely to make, as a registry entry under Modules
▸ MOF builder.

**From a synthesis...** (``synthesis.build``) is one form.  It votes
(:mod:`xtal.mof.precedent`): which nodes and nets the nearest
published syntheses formed, each with its share and the precedents it
stood on.  With *Build the likely frameworks* ticked, as it is by
default, it then builds what the vote names (:mod:`xtal.mof.candidates`):
the typed linker made a block, each voted net the builder has filled
with catalogue clusters of the voted metals, tried best-ranked first
until *Frameworks to open* have come out as the net they were asked to
be -- one per net and node -- or the time is spent, and those open in
new tabs.  Every row says how to build it again with ``xtal run
mof.build``, which is why the linker block goes into the workspace's
``blocks/``.  Building needs the MOF builder as well as RDKit; the
vote alone needs RDKit only, so the entry is greyed only without that
and a build without ase is a failed run saying so.

``synthesis.forecast`` is the vote alone, unlisted: a report and no
structure, no run folder, for the command line and the agent.

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
               "MeOH, MeCN, DMSO, NMP, dioxane, pyridine, THF, or "
               "their names (N,N-dimethylformamide), in any case.  One "
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
    Param("build", "Build the likely frameworks", kind="bool",
          default=True,
          help="Build what the vote names, best-ranked first, and open "
               "the best in a new tab.  Unticked, the answer is the "
               "vote alone, in about a second."),
    Param("top", "Frameworks to open", kind="int", default=1,
          minimum=1, maximum=10, when="build",
          help="How many of the best builds to open, each in its own "
               "tab: different nets or different nodes, never one "
               "cluster drawn twice.  Building stops once this many "
               "have come out as asked."),
    Param("budget", "Time to spend building", kind="float",
          default=30.0, minimum=1.0, maximum=600.0, decimals=0,
          suffix=" s", when="build",
          help="Seconds of test builds, best-ranked first; what is "
               "left is listed untried.  A build is about a second on "
               "pcu, fcu or tbo and longer on an unusual net, and the "
               "last one started may finish past the time."),
)


#: A comma between two digits is part of a name -- 4,4'-bipyridine,
#: 1,4-dioxane -- and every other one separates two entries ...
_SEPARATOR = re.compile(r";|\n|(?<!\d),|,(?!\d)")
#: ... except in a list of locants before a hyphen: N,N-dimethyl-
#: formamide was read as two solvents, "N" and "N-dimethylformamide",
#: neither known, and DMF dropped out of the comparison.  A locant is
#: a number or one letter standing alone, primed or not.
_LOCANTS = re.compile(r"(?<![\w'])(?:\d+|[A-Za-z])'*"
                      r"(?:\s*,\s*(?:\d+|[A-Za-z])'*)+(?=\s*-)")
_HELD = "\x00"


def split(text: str) -> list[str]:
    held = _LOCANTS.sub(lambda m: m.group(0).replace(",", _HELD),
                        str(text or ""))
    return [part.strip().replace(_HELD, ",")
            for part in _SEPARATOR.split(held) if part.strip()]


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


def from_a_synthesis(job) -> JobResult:
    """The form's one entry: the vote, and the builds when ticked."""
    if not job.param("build", True):
        return forecast(job)
    builder = _builder()
    if not builder:
        return JobResult.failure(
            f"{builder.reason}  Untick Build the likely frameworks to "
            f"see the vote without it.")
    return build_likely(job)


def _builder() -> Availability:
    from xtal.modules import mof

    return mof.available()


def build_likely(job) -> JobResult:
    """Vote, then build what the vote names; the best ``top`` open.

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

    top = max(1, int(job.param("top", 1)))
    tried = candidates.trial(
        answer, catalog_for, folder=folder,
        budget=float(job.param("budget", candidates.BUDGET)),
        log=job.say, cancelled=lambda: job.cancelled, wanted=top)
    if job.cancelled:
        return JobResult.stopped("stopped between builds")
    chosen = tried.chosen(top)
    voted = report(answer)
    result = Report(title="Build the likely frameworks",
                    blocks=_tried(tried, chosen) + voted.blocks,
                    note=voted.note)
    if not chosen:
        return JobResult(
            message=f"Nothing the vote names built as asked. "
                    f"{_said(answer)}",
            report=result)
    for each in chosen:
        each.structure.meta.setdefault("warnings", []).append(
            "A starting geometry on a net the nearest precedents "
            "formed, not a prediction that this is the phase that "
            "forms.")
    best = chosen[0]
    candidate = best.candidate
    built = sum(a.confirmed for a in tried.attempts)
    opened = (f"the best-ranked of {built} that built as asked"
              if len(chosen) == 1 else
              f"and {len(chosen) - 1} more: {_names(chosen[1:])}")
    short = (f" ({top} asked for, {len(chosen)} built)"
             if len(chosen) < top else "")
    return JobResult(
        message=f"Built {candidate.net} with "
                f"{', '.join(n for _, n in candidate.nodes)} "
                f"({best.atoms} atoms), {opened}{short}. "
                f"{_said(answer)}",
        structure=best.structure,
        more=tuple(a.structure for a in chosen[1:]),
        report=result)


def _names(attempts) -> str:
    return ", ".join(f"{a.candidate.net} with {a.candidate.node}"
                     for a in attempts)


def _tried(tried, chosen=()) -> tuple[Table, ...]:
    opened = {id(a) for a in chosen}
    rows = [Row.of(
        a.candidate.net,
        ", ".join(f"{k}={n}" for k, n in a.candidate.nodes),
        a.candidate.edge or "none",
        f"{a.candidate.score:.3f}",
        f"{a.status}, opened" if id(a) in opened else a.status,
        a.atoms or "--", a.candidate.spelled,
        note=a.verdict)
        for a in tried.attempts]
    rows += [Row.of(c.net, ", ".join(f"{k}={n}" for k, n in c.nodes),
                    c.edge or "none", f"{c.score:.3f}",
                    tried.why_untried(c), "--", c.spelled)
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
        _accessibility(query),
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


def _accessibility(query: precedent.Query) -> Row:
    scores = [precedent.synthetic_accessibility(s)
              for s, _ in query.linkers]
    value = "not available" if None in scores \
        else "; ".join(f"{x:.1f}" for x in scores)
    return Row("Synthetic accessibility", value, "",
               "Ertl's SA score of each linker, 1 easy to 10 hard; it "
               "describes the linker and is not the vote")


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
    # Under the MOF builder: it is a way to choose what to build.
    order=28, group="build", menu="MOF builder",
    check=available,
    provides=frozenset({"structure", "table"}),
    actions=(
        # One entry and one form, Build the likely frameworks a box in
        # it: the vote and the build ask the same five questions, and
        # two entries asked them twice.  The vote alone stays an
        # action for the command line and the agent, unlisted, since
        # it is the quick answer and needs neither ase nor a folder.
        Action(name="build", label="From a synthesis...",
               tip="The nodes and nets the nearest published "
                   "syntheses formed, and the likeliest built in a "
                   "new tab",
               kind="build",
               needs_structure=False,
               params=PARAMS + BUILD_PARAMS,
               run=from_a_synthesis),
        Action(name="forecast", label="Vote only",
               tip="The nodes and nets the nearest published "
                   "syntheses formed",
               needs_structure=False,
               writes_run_folder=False,
               listed=False,
               params=PARAMS,
               run=forecast),
    ),
)


def register(registry=MODULES) -> Module:
    return registry.register(SYNTHESIS)
