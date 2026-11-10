"""
xtal.modules.synthesis
======================
What a synthesis is likely to make, as a registry entry.

The vote is :mod:`xtal.mof.precedent`; this file is the form, the
check and the tables.  **It builds nothing**: the answer is which
nodes and nets the nearest published syntheses formed, each with its
share and the precedents it stood on, and building one is the MOF
builder's -- the nets table says which of them the builder has.  So
the action returns a report and no structure, needs no document and
leaves no run folder, like :mod:`xtal.modules.net`'s.

It needs RDKit to read a linker, and the check is ``find_spec``, as
the molecule builder's is.
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
    temperature = str(job.param("temperature", "") or "").strip()
    try:
        query = precedent.Query.read(
            job.param("metal", ""), split(job.param("linkers", "")),
            split(job.param("solvents", "")),
            float(temperature) if temperature else None)
        answer = precedent.forecast(
            query, neighbours=int(job.param("neighbours",
                                            precedent.NEIGHBOURS)))
    except ValueError as exc:
        # PrecedentError is a ValueError, and so is a temperature that
        # is not a number.
        return JobResult.failure(str(exc))
    job.say(f"voted {len(answer.neighbours)} precedents from "
            f"{answer.source}")
    top = answer.nets[0] if answer.nets else None
    message = (f"Likeliest net {top.value} ({top.share:.0%} of the "
               f"vote); {answer.novelty.sentence()}"
               if top else "No precedent close enough named a net.")
    return JobResult(message=message, report=report(answer))


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
    provides=frozenset({"table"}),
    actions=(
        Action(name="forecast", label="From a synthesis...",
               tip="The nodes and nets the nearest published "
                   "syntheses formed",
               needs_structure=False,
               writes_run_folder=False,
               params=PARAMS,
               run=forecast),
    ),
)


def register(registry=MODULES) -> Module:
    return registry.register(SYNTHESIS)
