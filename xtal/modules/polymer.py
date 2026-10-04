"""
xtal.modules.polymer
====================
The amorphous polymer builder, as a registry entry.

The model is :mod:`xtal.polymer`; this file is the entry in the
Modules menu, the form's parameters and the report.  A builder, so
``needs_structure`` is False and what it returns is filed as an entry
of its own by :meth:`xtal.workspace.Workspace.adopt_build`, in the
window and from ``xtal run polymer.build`` alike -- with its bonds
stated, so reopening the file perceives nothing.

**A monomer is named three ways in one box**: a library entry
(``Polyethylene``), a block file with two connection points, or a
starred SMILES string.  The library is asked first because its names
are not SMILES and a path is not either; whatever is left is handed to
RDKit, whose refusal is the run's failure.  RDKit is the ``build``
extra, and the entry greys out naming it, because every library
monomer is a string that needs embedding.

**The report says what the model is not.**  Its last note is the
build's own: packed, not equilibrated.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from xtal.build import MISSING, BuildError, installed
from xtal.modules.job import JobResult
from xtal.modules.registry import (
    MODULES,
    Action,
    Availability,
    Module,
    Param,
)
from xtal.modules.report import Histogram, Report, Row, Table

__all__ = ["PARAMS", "POLYMER", "available", "build_polymer",
           "monomer_of", "recipe_of", "register"]

#: The defaults are the recipe's, read once rather than written twice.
#: Imported lazily below because :mod:`xtal.polymer.pack` pulls in the
#: chain code, and the menu is built without it.
_CHAINS, _LENGTH, _DENSITY = 10, 20, 0.85
_THICKNESS, _VACUUM = 30.0, 20.0
_RELAX_STEPS, _MAX_ATOMS, _TRIALS = 600, 20000, 12


def available() -> Availability:
    """``find_spec`` and nothing more: every monomer is embedded by
    RDKit, the library's included."""
    if not installed():
        return Availability(False, MISSING)
    return Availability(True, "RDKit")


PARAMS = (
    Param("monomer", "Monomer", kind="text", default="Polyethylene",
          help="A library monomer by name (Polyethylene, "
               "Polypropylene, Polystyrene, PMMA, PVC, PEO, PTFE, PET, "
               "Nylon-6, PIM-1, PIM-EA-TB), a block file with two "
               "connection points, or a SMILES string with [*:1] at "
               "the head and [*:2] at the tail."),
    Param("monomer_b", "Second monomer", kind="text", default="",
          help="The B of a copolymer, named the same three ways.  "
               "Left empty, the chain is a homopolymer."),
    Param("composition", "Composition", kind="choice",
          default="homopolymer",
          choices=(("homopolymer", "Homopolymer"),
                   ("alternating", "Alternating A-B"),
                   ("random", "Random"),
                   ("block", "Blocks")),
          help="How A and B follow each other down a chain.  A "
               "copolymer needs a second monomer."),
    Param("fraction_a", "Fraction of A", kind="float", default=0.5,
          minimum=0.0, maximum=1.0, decimals=2,
          help="For a random copolymer: the chance that a unit is A."),
    Param("block_a", "Block of A", kind="int", default=10, minimum=1,
          maximum=10000,
          help="For a block copolymer: units of A in a run, the runs "
               "repeated down the chain."),
    Param("block_b", "Block of B", kind="int", default=10, minimum=1,
          maximum=10000,
          help="For a block copolymer: units of B in a run."),
    Param("tacticity", "Tacticity", kind="choice", default="atactic",
          choices=(("atactic", "Atactic"),
                   ("isotactic", "Isotactic"),
                   ("syndiotactic", "Syndiotactic")),
          help="Whether each unit has the hand of the one before it.  "
               "A monomer with no stereocentre, like polyethylene, "
               "has nothing to choose and the report says nothing."),
    Param("p_meso", "p(meso)", kind="float", default=0.5, minimum=0.0,
          maximum=1.0, decimals=2,
          help="For an atactic chain: the chance a unit has the hand "
               "of the one before it.  0.5 is what a free-radical "
               "polymerisation gives, near enough."),
    Param("chains", "Chains", kind="int", default=_CHAINS, minimum=1,
          maximum=1000,
          help="How many chains are packed into the box."),
    Param("length", "Units per chain", kind="int", default=_LENGTH,
          minimum=1, maximum=10000,
          help="Repeat units in each chain.  Ten chains of a hundred "
               "polyethylene units are 6000 atoms and about twenty "
               "seconds."),
    Param("periodic", "Periodicity", kind="choice", default="bulk",
          choices=(("bulk", "Bulk, periodic in 3D"),
                   ("membrane", "Membrane, with vacuum on c")),
          help="A membrane is grown between two walls, periodic in a "
               "and b, and vacuum is added on c; no bond crosses c, "
               "so its surfaces are the chains' own."),
    Param("density", "Density", kind="float", default=_DENSITY,
          minimum=0.05, maximum=4.0, decimals=3, suffix=" g/cm3",
          help="The target.  Amorphous densities near room "
               "temperature: PE and PP 0.85, PS 1.05, PMMA 1.18, PVC "
               "1.39, PEO 1.13, PTFE 2.0, PET 1.33, nylon-6 1.08, "
               "PIM-1 1.06."),
    Param("start_density", "Grow at (0 chooses)", kind="float", default=0.0,
          minimum=0.0, maximum=4.0, decimals=3, suffix=" g/cm3",
          help="The density the chains are grown at before they are "
               "compressed to the target.  0 chooses: three quarters "
               "of the target for a chain that turns, 0.2 for a "
               "ladder, and lower again if growth jams."),
    Param("thickness", "Membrane thickness", kind="float",
          default=_THICKNESS, minimum=10.0, maximum=500.0, decimals=1,
          suffix=" A", help="The film, wall to wall."),
    Param("vacuum", "Vacuum", kind="float", default=_VACUUM,
          minimum=0.0, maximum=500.0, decimals=1, suffix=" A",
          help="Added on c, split either side of the film."),
    Param("relax_steps", "Push-off steps", kind="int",
          default=_RELAX_STEPS, minimum=0, maximum=20000,
          help="Minimisation after growth or compression, holding "
               "every bond and angle, until no two atoms overlap."),
    Param("trials", "Trials per step", kind="int", default=_TRIALS,
          minimum=2, maximum=100,
          help="Torsions tried for each unit added.  More is slower "
               "and finds room in a fuller box."),
    Param("seed", "Seed", kind="int", default=0, minimum=0,
          maximum=2 ** 31 - 1,
          help="The same seed and recipe build the same model, atom "
               "for atom."),
    Param("max_atoms", "Most atoms", kind="int", default=_MAX_ATOMS,
          minimum=100, maximum=1000000,
          help="A recipe that would make more is refused before "
               "anything is grown."),
)


def monomer_of(text: str, optimise: bool = True):
    """A monomer from what was typed: a library name, a block file, or
    a starred SMILES string.  ``optimise=False`` is the dialog's live
    check, which needs the head and tail and not the geometry."""
    from xtal.build import library
    from xtal.polymer import monomer

    text = str(text).strip()
    if not text:
        raise BuildError("no monomer given")
    entry = library.find(text)
    if entry is not None and entry.category == library.MONOMER:
        return monomer.from_smiles(entry.smiles, name=entry.name,
                                   optimise=optimise)
    path = Path(text).expanduser()
    if path.suffix.lower() == ".xyz" and path.is_file():
        return monomer.from_block_file(path)
    return monomer.from_smiles(text, optimise=optimise)


def recipe_of(job, monomers=None):
    """The recipe a job's parameters describe.  ``monomers`` are the
    units already resolved, by a dialog that has them; otherwise the
    names in the parameters are."""
    from xtal.polymer.pack import Recipe
    from xtal.polymer.sequence import Sequence

    def value(name):
        param = next(p for p in PARAMS if p.name == name)
        return job.param(name, param.default)

    if monomers is None:
        monomers = [monomer_of(value("monomer"))]
        if (str(value("composition")) != "homopolymer"
                and str(value("monomer_b") or "").strip()):
            monomers.append(monomer_of(value("monomer_b")))
    fraction = float(value("fraction_a"))
    sequence = Sequence(
        composition=str(value("composition")),
        tacticity=str(value("tacticity")),
        p_meso=float(value("p_meso")),
        fractions=(fraction, 1.0 - fraction),
        blocks=(int(value("block_a")), int(value("block_b"))))
    start = float(value("start_density"))
    return Recipe(
        monomers=tuple(monomers), chains=int(value("chains")),
        length=int(value("length")), sequence=sequence,
        periodic=str(value("periodic")),
        density=float(value("density")),
        start_density=start if start > 0 else None,
        thickness=float(value("thickness")),
        vacuum=float(value("vacuum")), trials=int(value("trials")),
        seed=int(value("seed")),
        relax_steps=int(value("relax_steps")),
        max_atoms=int(value("max_atoms")))


def build_polymer(job) -> JobResult:
    """Pack the chains into a document of their own, with a report of
    what came out against what was asked."""
    from xtal.polymer import build
    from xtal.polymer.monomer import MonomerError
    from xtal.polymer.pack import PackError
    from xtal.polymer.sequence import SequenceError

    try:
        recipe = recipe_of(job)
        recipe.check()
    except (BuildError, MonomerError, SequenceError, PackError,
            ValueError) as exc:
        return JobResult.failure(str(exc))
    try:
        built = build.build(recipe, say=job.say, check=job.check)
    except PackError as exc:
        return JobResult.failure(str(exc))
    for line in built.lines():
        job.say(line)
    return JobResult(
        message=(f"{_names(recipe)}: {recipe.chains} chains of "
                 f"{recipe.length}, {len(built.structure.sites)} atoms "
                 f"at {built.density:.3f} g/cm3"),
        structure=built.structure,
        report=report(built))


def _names(recipe) -> str:
    return " / ".join(dict.fromkeys(m.name or m.formula
                                    for m in recipe.monomers))


def report(built) -> Report:
    """What was built: the box, the contacts, the chains' shape."""
    recipe = built.recipe
    a, b, c = built.structure.lattice.parameters[:3]
    shape = built.shape
    rows = [
        Row("Monomer", _names(recipe)),
        Row("Chains", f"{recipe.chains} x {recipe.length} units"),
        Row("Atoms", str(len(built.structure.sites))),
        Row("Cell", f"{a:.2f} x {b:.2f} x {c:.2f}", "A", "P1"),
        Row.number("Density", built.density, "g/cm3",
                   f"asked {recipe.density:g}"
                   + (", in the film" if recipe.periodic == "membrane"
                      else "")),
        Row.number("Grown at", built.grown_at, "g/cm3",
                   "compressed to the target after"
                   if built.grown_at < recipe.density else ""),
        Row.number("Closest contact", built.closest_distance, "A",
                   f"{built.closest:.2f} of the van der Waals sum, "
                   f"between atoms three bonds apart or more",
                   decimals=2),
    ]
    if built.meso is not None:
        rows.append(Row.number("Meso dyads", 100 * built.meso, "%",
                               decimals=0))
    if built.speared:
        rows.append(Row("Bonds through rings", str(built.speared), "",
                        "a knot no relaxation undoes: build again"))
    what = Table(title="What was built", rows=tuple(rows))
    chain_rows = [
        Row.number("<R^2>^1/2", float(np.sqrt(shape.r2)), "A",
                   "end to end", decimals=1),
        Row.number("Rg", shape.rg, "A", "root mean square",
                   decimals=1),
    ]
    if shape.c_n is not None:
        chain_rows.append(Row.number(
            f"C_{shape.bonds}", shape.c_n, "",
            f"freely rotating {shape.c_free:.2f}", decimals=2))
    chains = Table(title="Chains", rows=tuple(chain_rows))
    ends = np.asarray(shape.ends, dtype=float)
    counts, edges = np.histogram(ends, bins=min(20, max(3, len(ends))))
    histogram = Histogram(
        title="End-to-end distance",
        x=0.5 * (edges[1:] + edges[:-1]), y=counts.astype(float),
        x_label="R / A", y_label="chains",
        note="one chain each; few chains are a noisy picture")
    return Report(title=f"Amorphous {_names(recipe)}",
                  blocks=(what, chains, histogram),
                  note=built.lines()[-1] if not any(
                      m.is_ladder for m in recipe.monomers)
                  else "; ".join(built.lines()[-2:]))


POLYMER = Module(
    name="polymer",
    label="Polymer builder",
    description="Pack amorphous polymer chains into a box or a "
                "membrane at a density: homopolymers or copolymers, "
                "any tacticity, from a library monomer or a SMILES "
                "string.  It opens in a new tab with its bonds "
                "stated.  The model is packed, not equilibrated.",
    order=24, group="build",
    check=available,
    provides=frozenset({"structure", "table"}),
    actions=(
        Action(name="build", label="Build an amorphous polymer...",
               tip="Chains grown into a box at a density; the result "
                   "opens in a new tab",
               kind="build",
               needs_structure=False,
               dialog="polymer-build",
               params=PARAMS,
               run=build_polymer),
    ),
)


def register(registry=MODULES) -> Module:
    return registry.register(POLYMER)
