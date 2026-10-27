"""
xtal.modules.graphene
=====================
The graphene builder, as a registry entry: honeycomb sheets of
carbon, boron nitride or any two elements, one layer or stacked AA,
AB, ABC or AA', as graphite (periodic along c) or a slab in vacuum,
in the hexagonal cell or the rectangular one, repeated.

The geometry is :mod:`xtal.graphene`; this file is the entry in the
Modules menu -- Carbon builder, between the nanotube and the
disordered carbon -- the form's parameters and the report.  A
builder, so ``needs_structure`` is False and what it returns is filed
as an entry of its own by :meth:`xtal.workspace.Workspace.adopt_build`,
in the window and from ``xtal run graphene.build`` alike.  Nothing
optional is needed.
"""

from __future__ import annotations

import math
from collections import Counter

from xtal import references
from xtal.core import limits
from xtal.graphene import build as sheet
from xtal.modules.job import JobResult
from xtal.modules.registry import MODULES, Action, Module, Param
from xtal.modules.report import Report, Row, Table

__all__ = ["PARAMS", "GRAPHENE", "build_graphene", "recipe_of",
           "register", "report"]

_DEFAULT = sheet.Recipe()

_STACKINGS = (("AA", "AA (eclipsed)"),
              ("AB", "AB (Bernal, graphite's)"),
              ("ABC", "ABC (rhombohedral)"),
              ("AA'", "AA' (h-BN's, elements alternating)"))

_STACKS = (("slab", "Slab, vacuum above"),
           ("bulk", "Bulk, periodic along c"))

PARAMS = (
    Param("element_a", "Element A", kind="text",
          default=_DEFAULT.element_a,
          help="The element on one of the honeycomb's two sites.  C "
               "and C is graphene; B and N hexagonal boron nitride."),
    Param("element_b", "Element B", kind="text",
          default=_DEFAULT.element_b,
          help="The element on the other site; every bond joins an A "
               "to a B."),
    # Text, not a number, so that empty can mean "the elements' own":
    # the nanotube's Bond length is the precedent.
    Param("bond", "Bond length", kind="text", default="",
          help="The sheet's bond, in Angstrom.  Left empty it is the "
               "two elements' aromatic bond from Pyykkö's covalent "
               "radii: 1.42 A for C-C, 1.47 A for B-N.  0.8 to 3.0 A."),
    Param("layers", "Layers", kind="int", default=_DEFAULT.layers,
          minimum=1, maximum=100,
          help="How many sheets.  Bulk repeats the stacking along c, "
               "so its layers must be a whole number of the "
               "stacking's period: 2 for AB and AA', 3 for ABC."),
    Param("stacking", "Stacking", kind="choice",
          default=_DEFAULT.stacking, choices=_STACKINGS,
          help="How each layer sits over the last.  AA puts every "
               "atom over one; AB (Bernal) shifts every other layer "
               "by one bond, graphite's; ABC shifts each by one more, "
               "rhombohedral graphite's; AA' is AA with the elements "
               "alternating, B over N, h-BN's own."),
    Param("spacing", "Layer spacing", kind="text", default="",
          help="The distance between layers, in Angstrom.  Left "
               "empty it is graphite's 3.35 A, or h-BN's 3.33 A for "
               "B and N.  1 to 20 A."),
    Param("stack", "Stack", kind="choice", default=_DEFAULT.stack,
          choices=_STACKS,
          help="Bulk is periodic along c with no gap but the layer "
               "spacing: graphite.  A slab is the layers with vacuum "
               "above the top one, for a surface or a sheet alone."),
    # Not 0: at 0 a slab's top layer meets its image's bottom one.
    Param("vacuum", "Vacuum", kind="float", default=_DEFAULT.vacuum,
          minimum=3.0, maximum=100.0, decimals=1, suffix=" A",
          help="A slab's gap between its top layer and its image's "
               "bottom one.  15 A clears the force field's 12 A "
               "cutoff.  Bulk has none."),
    Param("cells_a", "Repeat along a", kind="int",
          default=_DEFAULT.cells_a, minimum=1, maximum=500,
          help="How many cells along a."),
    Param("cells_b", "Repeat along b", kind="int",
          default=_DEFAULT.cells_b, minimum=1, maximum=500,
          help="How many cells along b."),
    Param("rectangular", "Rectangular cell", kind="bool",
          default=_DEFAULT.rectangular,
          help="The orthogonal cell, a by sqrt(3) a with four atoms a "
               "layer, in place of the hexagonal two-atom one: a is "
               "then the zigzag direction and b the armchair one."),
)


def recipe_of(job) -> sheet.Recipe:
    """The recipe a job's parameters describe, checked."""
    values = {p.name: job.param(p.name, p.default) for p in PARAMS}
    return sheet.checked(sheet.Recipe(**values))


def build_graphene(job) -> JobResult:
    """Build the sheets, into a document of their own, with a report."""
    try:
        recipe = recipe_of(job)
    except sheet.GrapheneError as exc:
        return JobResult.failure(str(exc))
    verdict = limits.check_graphene(recipe)
    sentence = f"{verdict.sentence[:1].upper()}{verdict.sentence[1:]}"
    if verdict.refused:
        return JobResult.failure(sentence)
    if verdict.warned:
        job.note(sentence)
        job.say(sentence)
    built = sheet.build(recipe, say=job.say)
    for line in built.lines():
        job.say(line)
    return JobResult(
        message=(f"{recipe.title}: {len(built.structure.sites)} atoms"),
        structure=built.structure,
        report=report(built))


def report(built) -> Report:
    """What was built: its layers, its cell, its bonds."""
    recipe = built.recipe
    counts = Counter(s.element for s in built.structure.sites)
    formula = " ".join(f"{e}{counts[e]}" for e in sorted(counts))
    rows = [
        Row("Layers", str(recipe.layers)),
        Row("Stacking", dict(_STACKINGS)[recipe.stacking]
            if recipe.layers > 1 else "--"),
        Row("Stack", dict(_STACKS)[recipe.stack]),
        Row("Composition", formula),
        Row("Atoms per layer", str(built.atoms_per_layer)),
        Row.number("a", built.a, "A", decimals=3),
        Row.number("b", built.b, "A", decimals=3),
        Row.number("c", built.c, "A", decimals=3),
        Row.number("gamma", built.gamma, "deg",
                   "rectangular cell" if recipe.rectangular
                   else "hexagonal cell", decimals=1),
        Row.number("Bond length", recipe.bond_length, "A",
                   "from Pyykkö's covalent radii"
                   if recipe.from_radii else "as given"),
    ]
    if recipe.layers > 1 or recipe.stack == "bulk":
        rows.append(Row.number("Layer spacing", recipe.interlayer, "A",
                               recipe.spacing_source, decimals=3))
    if math.isfinite(built.closest_contact):
        rows.append(Row.number("Closest contact", built.closest_contact,
                               "A", "between atoms neither bonded nor "
                               "sharing a neighbour", decimals=2))
    else:
        # Two atoms a cell: every atom is a neighbour of its own
        # images, so nothing is left to measure.
        rows.append(Row("Closest contact", "--", "",
                        "the cell is too small to tell"))
    return Report(title=recipe.title,
                  blocks=(Table(title="What was built",
                                rows=tuple(rows)),),
                  note="; ".join(built.notes))


GRAPHENE = Module(
    name="graphene",
    label="Graphene builder",
    description="Build honeycomb sheets -- graphene, h-BN or any two "
                "elements -- one layer or stacked AA, AB, ABC or AA', "
                "as bulk graphite or a slab in vacuum, in the "
                "hexagonal or the rectangular cell, repeated.  It "
                "opens in a new tab with its bonds stated.",
    # The carbon builders by dimension: 0D, 1D, 2D, 3D.
    order=25, group="build", menu="Carbon builder",
    provides=frozenset({"structure", "table"}),
    actions=(
        Action(name="build", label="Graphene...",
               tip="Honeycomb sheets, alone or stacked; the result "
                   "opens in a new tab",
               kind="build",
               needs_structure=False,
               params=PARAMS,
               run=build_graphene,
               references=references.GRAPHENE),
    ),
)


def register(registry=MODULES) -> Module:
    return registry.register(GRAPHENE)
