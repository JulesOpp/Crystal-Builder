"""
xtal.modules.carbon
===================
The disordered-carbon builder, as a registry entry: zeolite-templated
carbons and schwarzites as one connected sheet that follows a net.

The geometry is :mod:`xtal.carbon`; this file is the entry in the
Modules menu, the form's parameters and the report.  A builder, so
``needs_structure`` is False and what it returns is filed as an entry
of its own by :meth:`xtal.workspace.Workspace.adopt_build`, in the
window and from ``xtal run carbon.build`` alike.  Nothing optional is
needed: numpy, scipy, and UFF, which ships.
"""

from __future__ import annotations

import numpy as np

from xtal.carbon import build as carbon_build
from xtal.carbon.mesh import MeshError
from xtal.carbon.ribbons import RibbonError
from xtal.carbon.surface import SurfaceError
from xtal.core import limits
from xtal.modules.job import JobResult
from xtal.modules.registry import MODULES, Action, Module, Param
from xtal.modules.report import Histogram, Report, Row, Table

__all__ = ["PARAMS", "CARBON", "build_carbon", "register"]

_DEFAULT = carbon_build.Recipe()

PARAMS = (
    Param("net", "Net", kind="text", default=_DEFAULT.net,
          help="The RCSR's name for the 3-periodic net the carbon "
               "follows.  dia is FAU's supercages, which a zeolite-"
               "templated carbon from faujasite is built on; srs is a "
               "gyroid schwarzite's.  A layer net is refused: a sheet "
               "round it cannot percolate in three directions."),
    Param("repeat", "Repeat the net", kind="text", default="2x2x2",
          help="How many cells of the net -- '2x2x2', or '2' for all "
               "three.  The disorder is drawn over the whole of it, so "
               "a larger repeat is a less periodic carbon, and a "
               "slower build: 2x2x2 of dia is about 2500 carbons."),
    Param("density", "Carbon density", kind="float",
          default=_DEFAULT.density, minimum=0.05, maximum=2.2,
          decimals=3, suffix=" g/cm3",
          help="Grams of framework carbon per cubic centimetre, "
               "terminations left out.  The cell is solved so the "
               "carbon kept is exactly this."),
    Param("radius_ratio", "Strut radius / edge", kind="float",
          default=_DEFAULT.radius_ratio, minimum=0.1, maximum=0.6,
          decimals=2,
          help="How fat the sheet's tube round each edge of the net "
               "is, as a share of the edge's length.  Larger is a "
               "larger cell at the same density.  The innermost sheet "
               "must be at least 2.5 A from its edge."),
    Param("coverage", "Sheet kept", kind="float",
          default=_DEFAULT.coverage, minimum=0.1, maximum=1.0,
          decimals=2,
          help="The share of the closed sheet kept as ribbons.  1 is "
               "a closed schwarzite with no edges; lower is narrower "
               "ribbons with more edge carbons, which is where the "
               "terminations go.  It decides the cell, with the "
               "density; the ribbons are then cut to the carbon count "
               "exactly."),
    Param("layers", "Layers", kind="int", default=_DEFAULT.layers,
          minimum=1, maximum=3,
          help="Sheets stacked round each strut, never bonded to each "
               "other.  Each is cut to the same ribbons."),
    Param("interlayer", "Layer spacing", kind="float",
          default=_DEFAULT.interlayer, minimum=3.0, maximum=4.0,
          decimals=2, suffix=" A",
          help="How far apart stacked sheets are; graphite's is "
               "3.35 A."),
    Param("sigma_vertex", "Node jitter", kind="float",
          default=_DEFAULT.sigma_vertex, minimum=0.0, maximum=3.0,
          decimals=2, suffix=" A",
          help="How far each net vertex is moved at random -- the "
               "disorder of the framework's joints."),
    Param("sigma_edge", "Edge bow", kind="float",
          default=_DEFAULT.sigma_edge, minimum=0.0, maximum=3.0,
          decimals=2, suffix=" A",
          help="How far each net edge bows sideways at its middle."),
    Param("stone_wales", "Stone-Wales pairs per 100 rings",
          kind="float", default=_DEFAULT.stone_wales, minimum=0.0,
          maximum=30.0, decimals=1,
          help="5-7-7-5 defects added to the sheet on top of the "
               "rings its shape needs.  The shape fixes the balance "
               "of pentagons and heptagons by Gauss-Bonnet, which is "
               "why this is set rather than a free ratio of rings."),
    Param("hydrogen", "H/C", kind="float", default=_DEFAULT.hydrogen,
          minimum=0.0, maximum=1.0, decimals=3,
          help="Hydrogen per carbon, counting the hydroxyls'."),
    Param("fluorine", "F/C", kind="float", default=_DEFAULT.fluorine,
          minimum=0.0, maximum=1.0, decimals=3,
          help="Fluorine per carbon, on edge carbons."),
    Param("oxygen", "O/C", kind="float", default=_DEFAULT.oxygen,
          minimum=0.0, maximum=1.0, decimals=3,
          help="Oxygen per carbon, split by the three below."),
    Param("ether", "Oxygen as ring ether", kind="float",
          default=_DEFAULT.ether, minimum=0.0, maximum=1.0, decimals=2,
          help="The share of the oxygen that is an edge carbon made "
               "oxygen, in the ring, as a pyran's is."),
    Param("hydroxyl", "Oxygen as OH", kind="float",
          default=_DEFAULT.hydroxyl, minimum=0.0, maximum=1.0,
          decimals=2, help="The share of the oxygen that is C-OH."),
    Param("carbonyl", "Oxygen as C=O", kind="float",
          default=_DEFAULT.carbonyl, minimum=0.0, maximum=1.0,
          decimals=2, help="The share of the oxygen that is C=O."),
    Param("relax", "Relax", kind="choice", default=_DEFAULT.relax,
          choices=(("uff", "UFF at the solved cell"),
                   ("none", "No, as built")),
          help="UFF on the stated bonds, positions only: the cell "
               "stays the one the density was solved for.  As built, "
               "the bonds run from 1.1 to 1.8 A.  A DFTB+ or ORB-v3 "
               "polish is the Force Field panel's."),
    Param("relax_steps", "Relax steps", kind="int",
          default=_DEFAULT.relax_steps, minimum=0, maximum=5000,
          help="L-BFGS steps for the relaxation; 300 brings the "
               "bonds to 1.43 A on a dia cell."),
    Param("seed", "Seed", kind="int", default=_DEFAULT.seed,
          minimum=0, maximum=2 ** 31 - 1,
          help="The same seed and recipe build the same carbon, atom "
               "for atom; another seed is another draw of the "
               "disorder."),
)


def recipe_of(job) -> carbon_build.Recipe:
    """The recipe a job's parameters describe."""
    values = {p.name: job.param(p.name, p.default) for p in PARAMS}
    values["repeat"] = parse_repeat(values["repeat"])
    values["net"] = str(values["net"]).strip()
    return carbon_build.Recipe(**values)


def parse_repeat(text) -> tuple:
    """``'2x2x2'``, ``'2 2 2'`` or ``'2'`` to three counts."""
    parts = [p for p in str(text).replace("x", " ").replace(
        ",", " ").split() if p]
    try:
        counts = [int(p) for p in parts]
    except ValueError:
        raise ValueError(f"{text!r} is not a repeat like 2x2x2") from None
    if len(counts) == 1:
        counts *= 3
    if len(counts) != 3 or min(counts) < 1:
        raise ValueError(f"{text!r} is not a repeat like 2x2x2")
    return tuple(counts)


def build_carbon(job) -> JobResult:
    """Build the carbon, into a document of its own, with a report of
    what came out against what was asked."""
    try:
        recipe = recipe_of(job)
    except ValueError as exc:
        return JobResult.failure(str(exc))
    # Counted from one cell before any of the sheet is made: a repeat
    # has no cap of its own, and 3x3x3 was 53 s and 0.84 GB.
    job.say("counting the atoms one cell holds")
    try:
        verdict = limits.check_carbon(recipe)
    except (SurfaceError, RibbonError, MeshError) as exc:
        return JobResult.failure(str(exc))
    sentence = f"{verdict.sentence[:1].upper()}{verdict.sentence[1:]}"
    if verdict.refused:
        return JobResult.failure(sentence)
    if verdict.warned:
        job.note(sentence)
        job.say(sentence)
    try:
        built = carbon_build.build(recipe, say=job.say, check=job.check)
    except (SurfaceError, RibbonError, MeshError) as exc:
        return JobResult.failure(str(exc))
    for line in built.lines():
        job.say(line)
    return JobResult(
        message=(f"disordered carbon on {recipe.net}: "
                 f"{len(built.structure.sites)} atoms, "
                 f"{built.density:.3f} g/cm3 of carbon"),
        structure=built.structure,
        report=report(built))


def report(built) -> Report:
    """What was built: the cell, the chemistry, the rings."""
    recipe = built.recipe
    a, b, c = built.structure.lattice.parameters[:3]
    what = Table(title="What was built", rows=(
        Row("Net", f"{recipe.net} x "
            + "x".join(str(n) for n in recipe.repeat)),
        Row("Cell", f"{a:.2f} x {b:.2f} x {c:.2f}", "A",
            "solved from the density, not chosen"),
        Row.number("Net edge", built.edge_length, "A", decimals=2),
        Row.number("Carbon density", built.density, "g/cm3",
                   "framework carbon, terminations left out"),
        Row("Atoms", str(len(built.structure.sites))),
        Row.number("H/C", built.ratios["H/C"], ""),
        Row.number("F/C", built.ratios["F/C"], ""),
        Row.number("O/C", built.ratios["O/C"], ""),
        Row.number("Edge carbons", 100 * built.edge_fraction, "%",
                   "two-coordinate carbons, before termination",
                   decimals=0),
        Row("Bare edge carbons", str(built.bare_edges), "",
            "edge carbons with no room for a termination, or more "
            "than the ratios asked for"),
        Row("Pieces", str(built.pieces), "",
            "one per layer: the carbon of each layer is connected"),
        Row("Percolates in", f"{built.periodicity} directions"),
        Row.number("Closest contact", built.closest_contact, "A",
                   "between atoms neither bonded nor sharing a "
                   "neighbour", decimals=2),
    ))
    topology = Table(title="Topology", rows=(
        Row("Sheet chi", str(built.euler), "",
            "per layer, the net's 2(V - E) over the repeat"),
        Row("Sum of (6 - ring size)", str(built.gauss_bonnet), "",
            "on the closed sheet, Gauss-Bonnet's six chi: negative "
            "is heptagons the shape needs"),
        Row("Stone-Wales pairs", str(built.defects)),
    ))
    sizes = sorted(built.census)
    rings = Histogram(
        title="Rings", x=np.array(sizes, float),
        y=np.array([built.census[n] for n in sizes], float),
        x_label="ring size", y_label="rings",
        note="primitive rings of the stored graph, up to ten")
    note = "; ".join([built.relaxed] + list(built.notes)) \
        if built.relaxed or built.notes else ""
    return Report(title=f"Disordered carbon on {recipe.net}",
                  blocks=(what, topology, rings), note=note)


CARBON = Module(
    name="carbon",
    label="Disordered carbon builder",
    description="Build a zeolite-templated carbon or a schwarzite: "
                "one connected sheet that follows a net, cut into "
                "ribbons, with Stone-Wales defects and terminated "
                "edges, at the density asked for.  It opens in a new "
                "tab with its bonds stated.",
    order=23, group="build",
    provides=frozenset({"structure", "table"}),
    actions=(
        Action(name="build", label="Build a disordered carbon...",
               tip="Ribbons of carbon along a net, at a density; the "
                   "result opens in a new tab",
               kind="build",
               needs_structure=False,
               dialog="carbon-build",
               params=PARAMS,
               run=build_carbon),
    ),
)


def register(registry=MODULES) -> Module:
    return registry.register(CARBON)
