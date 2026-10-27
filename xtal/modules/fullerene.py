"""
xtal.modules.fullerene
======================
The fullerene builder, as a registry entry: a closed cage of C20 to
C100 from the shipped table of isomers, or any cage typed as its face
spiral, of one element, alone in a box.

The geometry is :mod:`xtal.fullerene`; this file is the entry in the
Modules menu, the form's parameters and the report.  A builder, so
``needs_structure`` is False and what it returns is filed as an entry
of its own by :meth:`xtal.workspace.Workspace.adopt_build`, in the
window and from ``xtal run fullerene.build`` alike.  The form is
:mod:`xtalapp.dialogs.fullerene_build`, because which isomers there
are depends on the size; the parameters below are what the CLI and an
agent give.  Nothing optional is needed.
"""

from __future__ import annotations

from collections import Counter

from xtal import references
from xtal.fullerene import build as cage
from xtal.modules.job import JobResult
from xtal.modules.registry import MODULES, Action, Module, Param
from xtal.modules.report import Report, Row, Table

__all__ = ["PARAMS", "FULLERENE", "build_fullerene", "recipe_of",
           "register", "report"]

_DEFAULT = cage.Recipe()

PARAMS = (
    Param("n", "Size", kind="int", default=_DEFAULT.n, minimum=20,
          maximum=cage.MAX_ATOMS, step=2, suffix=" atoms",
          help="How many atoms the cage has: an even number from 20, "
               "and not 22.  The table holds every isomer from C20 to "
               "C40 and every isolated-pentagon one from C60 to C100; "
               "any other size needs its spiral typed."),
    Param("isomer", "Isomer", kind="int", default=_DEFAULT.isomer,
          minimum=0, maximum=10000,
          help="Which of the size's isomers, counted from 1 in the "
               "Atlas of Fullerenes' order (from C60, among the IPR "
               "ones).  0 is the one the formula usually means: "
               "C60-Ih, C70-D5h, C80-Ih, C84-D2."),
    Param("spiral", "Spiral", kind="text", default="",
          help="The twelve faces, counted from 1, where the pentagons "
               "fall in a face spiral -- C60-Ih is 1 7 9 11 13 15 18 20 "
               "22 24 26 32.  Builds any cage that has one, in place "
               "of the isomer; left empty, the isomer is built."),
    Param("element", "Element", kind="text", default=_DEFAULT.element,
          help="One element for every atom.  A cage's twelve "
               "pentagons are odd rings, so two elements cannot "
               "alternate round it as B and N do on a sheet."),
    # Text, not a number, so that empty can mean "the element's own":
    # the nanotube's Bond length is the precedent.
    Param("bond", "Bond length", kind="text", default="",
          help="The cage's bond, in Angstrom, before relaxing.  Left "
               "empty it is the element's from Pyykkö's covalent "
               "radii: aromatic (1.42 A for C) for a bare cage, single "
               "(1.50 A) for a hydrogenated one.  0.8 to 3.0 A."),
    Param("hydrogenate", "Hydrogen on every atom", kind="bool",
          default=_DEFAULT.hydrogenate,
          help="One hydrogen on every atom, pointing out of the cage, "
               "at UFF's sp3 X-H length: C60H60."),
    Param("relax", "Relax", kind="choice", default=_DEFAULT.relax,
          choices=(("uff", "UFF in a fixed box"),
                   ("none", "No, as placed")),
          help="UFF on the stated bonds, positions only.  As placed is "
               "the springs' shape, every bond within about 10 % of "
               "the one asked for.  UFF types a bare carbon cage C_R, "
               "so its bonds come out nearly equal; C60's alternate "
               "1.40 and 1.45 A."),
    Param("relax_steps", "Relax steps", kind="int",
          default=_DEFAULT.relax_steps, minimum=0, maximum=5000,
          help="The most UFF steps; C60 converges in a handful."),
    # Not 0: at 0 a cage touches its own image.
    Param("vacuum", "Vacuum", kind="float", default=_DEFAULT.vacuum,
          minimum=3.0, maximum=50.0, decimals=1, suffix=" A",
          help="The gap between the cage and its periodic image, atom "
               "to atom.  12 A clears the force field's 12 A cutoff, "
               "so a relaxation sees one cage alone."),
)


def recipe_of(job) -> cage.Recipe:
    """The recipe a job's parameters describe, checked."""
    values = {p.name: job.param(p.name, p.default) for p in PARAMS}
    return cage.checked(cage.Recipe(**values))


def build_fullerene(job) -> JobResult:
    """Build the cage, into a document of its own, with a report."""
    try:
        recipe = recipe_of(job)
        built = cage.build(recipe, say=job.say)
    except cage.FullereneError as exc:
        return JobResult.failure(str(exc))
    for line in built.lines():
        job.say(line)
    return JobResult(
        message=(f"{built.title}: {len(built.structure.sites)} atoms, "
                 f"{built.diameter:.2f} A across"),
        structure=built.structure,
        report=report(built))


def report(built) -> Report:
    """What was built: which cage, its symmetry, its size, its bonds."""
    recipe = built.recipe
    counts = Counter(s.element for s in built.structure.sites)
    formula = " ".join(f"{e}{counts[e]}" for e in sorted(counts))
    row = built.isomer
    if row is None:
        which = "typed spiral, not in the table"
    else:
        which = row.label
    rows = [
        Row("Cage", built.title),
        Row("Isomer", which),
        Row("Spiral", " ".join(str(p) for p in built.spiral), "",
            "the canonical one: pentagons as early as any start puts "
            "them"),
        Row("Point group",
            row.group if row is not None and row.group else "--",
            "", f"order {built.order}, reflections included"),
        Row("Isolated pentagons", "yes" if built.ipr else "no", "",
            "" if built.ipr else
            f"{built.pentagon_pairs} pentagon-pentagon bonds"),
        Row("Composition", formula),
        Row.number("Diameter", built.diameter, "A",
                   "the widest two atom centres of the cage",
                   decimals=2),
        Row.number("Bond length", recipe.bond_length, "A",
                   "from Pyykkö's covalent radii"
                   if recipe.from_radii else "as given"),
        Row.number("Shortest bond", built.shortest_bond, "A"),
        Row.number("Longest bond", built.longest_bond, "A"),
        Row.number("Closest contact", built.closest_contact, "A",
                   "between atoms neither bonded nor sharing a "
                   "neighbour", decimals=2),
    ]
    if recipe.hydrogenate:
        rows.append(Row("Hydrogens", str(built.hydrogens), "",
                        "one on every atom, pointing out"))
    if built.relaxed:
        rows.append(Row("Relaxed", built.relaxed))
    return Report(title=built.title,
                  blocks=(Table(title="What was built",
                                rows=tuple(rows)),),
                  note="; ".join(built.notes))


FULLERENE = Module(
    name="fullerene",
    label="Fullerene builder",
    description="Build a fullerene cage: any of the isomers from C20 "
                "to C40, the isolated-pentagon ones from C60 to C100, "
                "or any cage typed as its face spiral, of one element, "
                "optionally with a hydrogen on every atom.  It opens "
                "in a new tab with its bonds stated.",
    # After the nanotube until the Carbon builder submenu orders the
    # four by dimension.
    order=26, group="build",
    provides=frozenset({"structure", "table"}),
    actions=(
        Action(name="build", label="Build a fullerene...",
               tip="A closed cage from the table of isomers or a "
                   "typed spiral; the result opens in a new tab",
               kind="build",
               needs_structure=False,
               params=PARAMS,
               run=build_fullerene,
               dialog="fullerene-build",
               references=references.FULLERENE),
    ),
)


def register(registry=MODULES) -> Module:
    return registry.register(FULLERENE)
