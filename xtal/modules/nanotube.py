"""
xtal.modules.nanotube
=====================
The nanotube builder, as a registry entry: a single-walled tube from
its roll-up vector (n,m), periodic along c or a finite piece, of
carbon, boron nitride or any two elements on the honeycomb's two
sites.

The geometry is :mod:`xtal.nanotube`; this file is the entry in the
Modules menu, the form's parameters and the report.  A builder, so
``needs_structure`` is False and what it returns is filed as an entry
of its own by :meth:`xtal.workspace.Workspace.adopt_build`, in the
window and from ``xtal run nanotube.build`` alike.  Nothing optional
is needed.
"""

from __future__ import annotations

from collections import Counter

from xtal import references
from xtal.core import limits
from xtal.modules.job import JobResult
from xtal.modules.registry import MODULES, Action, Module, Param
from xtal.modules.report import Report, Row, Table
from xtal.nanotube import build as tube

__all__ = ["PARAMS", "NANOTUBE", "build_nanotube", "recipe_of",
           "register"]

_DEFAULT = tube.Recipe()

_ENDS = (("periodic", "Periodic (infinite along c)"),
         ("capped", "Finite, ends capped with H"),
         ("bare", "Finite, bare ends"))

PARAMS = (
    Param("n", "n", kind="int", default=_DEFAULT.n, minimum=1,
          maximum=200,
          help="The roll-up vector's first index: the sheet is rolled "
               "so that n a1 + m a2 goes once round the tube.  (n,n) "
               "is armchair, (n,0) zigzag, anything else chiral."),
    Param("m", "m", kind="int", default=_DEFAULT.m, minimum=0,
          maximum=200,
          help="The roll-up vector's second index.  (m,n) is the "
               "mirror image of (n,m): the same tube in the other "
               "hand."),
    Param("ends", "Ends", kind="choice", default=_DEFAULT.ends,
          choices=_ENDS,
          help="Periodic is an infinite tube along c, with no ends.  "
               "Finite is a piece of the length asked for in a "
               "vacuum box; capped puts a hydrogen on each edge atom "
               "at the force field's own X-H length, bare leaves the "
               "edge atoms two-coordinate."),
    Param("length", "Length", kind="float", default=_DEFAULT.length,
          minimum=1.0, maximum=2000.0, decimals=2, suffix=" A",
          help="Finite: the tube's length.  Periodic: rounded to a "
               "whole number of the tube's translational periods, at "
               "least one -- the report says what it came to.  A "
               "chiral tube's period can be tens of angstroms."),
    Param("element_a", "Element A", kind="text",
          default=_DEFAULT.element_a,
          help="The element on one of the honeycomb's two sites.  C "
               "and C is a carbon nanotube; B and N a boron nitride "
               "one."),
    Param("element_b", "Element B", kind="text",
          default=_DEFAULT.element_b,
          help="The element on the other site; every bond joins an A "
               "to a B."),
    Param("bond", "Bond length", kind="float", default=_DEFAULT.bond,
          minimum=0.8, maximum=3.0, decimals=3, suffix=" A",
          help="The flat sheet's bond: graphite's is 1.421 A, "
               "h-BN's 1.446 A.  Rolling shortens each bond to a "
               "chord, a little; the report gives the shortest."),
    # Not 0: at 0 a tube overlaps its own image.
    Param("vacuum", "Vacuum", kind="float", default=_DEFAULT.vacuum,
          minimum=3.0, maximum=50.0, decimals=1, suffix=" A",
          help="The gap between the tube and its periodic image, "
               "atom to atom: across, and for a finite tube along it, "
               "caps included.  12 A clears the force field's 12 A "
               "cutoff, so a relaxation sees one tube alone; a "
               "bundle's gap is about 3.2-3.4 A."),
)


def recipe_of(job) -> tube.Recipe:
    """The recipe a job's parameters describe, checked."""
    values = {p.name: job.param(p.name, p.default) for p in PARAMS}
    return tube.checked(tube.Recipe(**values))


def build_nanotube(job) -> JobResult:
    """Build the tube, into a document of its own, with a report."""
    try:
        recipe = recipe_of(job)
    except tube.NanotubeError as exc:
        return JobResult.failure(str(exc))
    # Counted before anything is rolled: the length has no cap of its
    # own, and (200,200) at 2000 A is 650,000 atoms.
    verdict = limits.check_nanotube(recipe)
    sentence = f"{verdict.sentence[:1].upper()}{verdict.sentence[1:]}"
    if verdict.refused:
        return JobResult.failure(sentence)
    if verdict.warned:
        job.note(sentence)
        job.say(sentence)
    try:
        built = tube.build(recipe, say=job.say)
    except tube.NanotubeError as exc:
        return JobResult.failure(str(exc))
    for line in built.lines():
        job.say(line)
    return JobResult(
        message=(f"{recipe.title}: {len(built.structure.sites)} atoms, "
                 f"{built.chirality.diameter:.2f} A across"),
        structure=built.structure,
        report=report(built))


def report(built) -> Report:
    """What was built: its size, its period, its ends, its bonds."""
    recipe, c = built.recipe, built.chirality
    counts = Counter(s.element for s in built.structure.sites)
    formula = " ".join(f"{e}{counts[e]}" for e in sorted(counts))
    mirror = f"the mirror image of ({c.m},{c.n})" if c.m > c.n else ""
    rows = [
        Row("Chirality", f"({c.n},{c.m})", "", mirror),
        Row.number("Diameter", c.diameter, "A", decimals=2),
        Row.number("Chiral angle", c.theta, "deg",
                   "from the zigzag direction", decimals=2),
        Row.number("Period |T|", c.t_length, "A", decimals=3),
        Row("Atoms per period", str(c.atoms_per_period)),
    ]
    if recipe.periodic:
        rows.append(Row("Periods", str(built.periods), "",
                        "the length asked for, in whole periods"))
    rows += [
        Row.number("Length", built.length, "A",
                   "along c" if recipe.periodic
                   else "end to end, between atom centres", decimals=2),
        Row("Ends", dict(_ENDS)[recipe.ends]),
        Row("Composition", formula),
    ]
    if recipe.ends == "capped":
        rows.append(Row("Hydrogens", str(built.hydrogens), "",
                        "one on each two-coordinate edge atom"))
    rows += [
        Row.number("Shortest bond", built.shortest_bond, "A",
                   f"rolled from {recipe.bond:.3f}"),
        Row.number("Closest contact", built.closest_contact, "A",
                   "between atoms not bonded", decimals=2),
        Row("Electronic character", built.electronic),
    ]
    return Report(title=recipe.title,
                  blocks=(Table(title="What was built",
                                rows=tuple(rows)),),
                  note="; ".join(built.notes))


NANOTUBE = Module(
    name="nanotube",
    label="Nanotube builder",
    description="Build a single-walled nanotube from its roll-up "
                "vector (n,m): periodic along c, or a finite piece "
                "with bare or hydrogen-capped ends, of carbon, boron "
                "nitride or any two elements on the honeycomb's two "
                "sites.  It opens in a new tab with its bonds "
                "stated.",
    order=25, group="build",
    provides=frozenset({"structure", "table"}),
    actions=(
        Action(name="build", label="Build a nanotube...",
               tip="A single-walled tube from (n,m); the result "
                   "opens in a new tab",
               kind="build",
               needs_structure=False,
               params=PARAMS,
               run=build_nanotube,
               references=references.NANOTUBE),
    ),
)


def register(registry=MODULES) -> Module:
    return registry.register(NANOTUBE)
