"""
xtal.modules.orca
=================
Modules > ORCA > Input file...: an ORCA input and the coordinates it
reads, written into a run folder beside everything else run on the
structure.

Nothing runs.  Writing an input needs no ORCA, so the entry is never
greyed, and the folder is the thing to copy to the cluster.  When
ORCA's own ``_trj.xyz`` comes back into that folder it opens as a run
like any other (:mod:`xtal.io.trajectory`).

**A refused input writes nothing**: a folder holding a ``.inp`` with
a multiplicity its electrons cannot have is one somebody will submit.
The checks are :func:`xtal.orca.input.problems`, which the dialog
shows as they are typed, so reaching a refusal here is the CLI's
path, or a script's.

The markers are kept and left out by :func:`xtal.orca.input.cluster`
itself (``keeps_markers``): taking their sites out first would
renumber the cell under the selected atoms the dialog passes.
"""

from __future__ import annotations

from dataclasses import fields

from xtal.io import atomic
from xtal.modules.job import JobResult
from xtal.modules.registry import MODULES, Action, Module, Param
from xtal.orca import catalogue
from xtal.orca import input as orca


def _pairs(choices):
    return tuple((value, label) for value, label in choices)


PARAMS = (
    Param("functional", "Functional", kind="text",
          default=catalogue.DEFAULT_FUNCTIONAL,
          help="An ORCA native functional keyword (Tables 3.1-3.9)"),
    Param("basis", "Basis set", kind="text",
          default=catalogue.DEFAULT_BASIS,
          help="An ORCA built-in orbital basis (Tables 2.12-2.33); "
               "a 3c method writes none"),
    Param("dispersion", "Dispersion", kind="choice", default="",
          choices=_pairs(catalogue.DISPERSIONS),
          help="Added to the ! line; not with a functional that "
               "already has one"),
    Param("ri", "RI", kind="choice", default="",
          choices=_pairs(catalogue.RI_CHOICES),
          help="ORCA's default is RI-J for a pure functional and "
               "RIJCOSX for a hybrid; a choice writes its auxiliary "
               "basis too"),
    Param("run", "Job", kind="choice", default="sp",
          choices=_pairs(catalogue.RUNS),
          help="A single point, an optimisation, or a transition "
               "state search"),
    Param("opt_level", "Optimisation", kind="choice", default="Opt",
          choices=_pairs(catalogue.OPT_LEVELS),
          help="How tightly an optimisation converges"),
    Param("cartesian", "Cartesian (COpt)", kind="bool", default=False,
          help="Optimise in Cartesian rather than internal "
               "coordinates"),
    Param("freq", "Frequencies (Freq)", kind="bool", default=False,
          help="Vibrational frequencies, after the optimisation if "
               "there is one"),
    Param("max_iter", "Geometry MaxIter", kind="int", default=0,
          minimum=0, maximum=100000,
          help="%geom MaxIter; 0 is ORCA's own, max(3N, 50)"),
    Param("calc_hess", "Calc_Hess", kind="bool", default=False,
          help="An exact Hessian before the first step"),
    Param("scf_threshold", "SCF convergence", kind="choice",
          default="", choices=_pairs(catalogue.SCF_THRESHOLDS),
          help="TightSCF and the like, Table 2.9"),
    Param("scf_solver", "SCF solver", kind="choice", default="",
          choices=_pairs(catalogue.SCF_SOLVERS),
          help="SlowConv for most transition-metal complexes"),
    Param("scf_max_iter", "SCF MaxIter", kind="int", default=0,
          minimum=0, maximum=100000,
          help="%scf MaxIter; 0 is ORCA's own"),
    Param("scf_guess", "SCF guess", kind="choice", default="",
          choices=_pairs(catalogue.SCF_GUESSES),
          help="%scf Guess; the default is ORCA's own"),
    Param("tddft_nroots", "TD-DFT roots", kind="int", default=0,
          minimum=0, maximum=10000,
          help="Excited states for a UV-Vis spectrum; 0 writes no "
               "%tddft block"),
    Param("tddft_triplets", "Triplets", kind="bool", default=False,
          help="Singlet-triplet excitations as well"),
    Param("tddft_state", "TD-DFT with Opt or Freq", kind="choice",
          default="ground", choices=_pairs(catalogue.TDDFT_STATES),
          help="Optimise the ground state and then take its spectrum, "
               "in two steps, or optimise excited state IRoot itself"),
    Param("tddft_iroot", "IRoot", kind="int", default=1, minimum=1,
          maximum=10000,
          help="The excited state followed, counting from 1"),
    Param("tddft_iroot_triplet", "Triplet IRoot", kind="bool",
          default=False, help="Follow a triplet root (needs Triplets)"),
    Param("solvation", "Solvation", kind="choice", default="",
          choices=_pairs(catalogue.SOLVATIONS),
          help="An implicit solvent, C-PCM or SMD"),
    Param("solvent", "Solvent", kind="text", default="water",
          help="Any name of Table 2.56, e.g. water, dmf, thf"),
    Param("nprocs", "Processes (%pal)", kind="int", default=1,
          minimum=1, maximum=4096,
          help="Above one, a %pal block"),
    Param("maxcore_mb", "Memory per process", kind="int", default=0,
          minimum=0, maximum=10_000_000, suffix=" MB",
          help="%maxcore; 0 writes none"),
    Param("charge", "Charge", kind="int", default=0, minimum=-1000,
          maximum=1000, help="Of the atoms written"),
    Param("multiplicity", "Multiplicity", kind="int", default=1,
          minimum=1, maximum=1000,
          help="2S+1; refused when the electron count cannot have it"),
    Param("extra_keywords", "More keywords", kind="text", default="",
          help="Added to the end of the ! line as written"),
    Param("extra_blocks", "More blocks", kind="text", default="",
          help="% blocks of your own, written before the coordinates"),
    Param("atoms", "Atoms", kind="text", default="",
          help="Cell atom indices to write; blank is the whole cell"),
    Param("name", "File name", kind="text", default="",
          help="The .inp and .xyz are named after this"),
)

_FIELDS = {f.name for f in fields(orca.OrcaInput)}


def orca_input(params: dict) -> orca.OrcaInput:
    """The values of a form or a command line, as an input."""
    given = {k: v for k, v in params.items() if k in _FIELDS}
    for name in ("max_iter", "scf_max_iter", "maxcore_mb"):
        if name in given:
            given[name] = int(given[name] or 0) or None
    return orca.OrcaInput(**given)


def coordinates_name(stem: str) -> str:
    """Never ``<stem>.xyz``: an optimisation writes its last geometry
    there, over the structure it was handed."""
    return f"{stem}_from_crystal_builder.xyz"


def atoms_of(text: str) -> list[int] | None:
    """``"0 4 5"`` or ``"0,4,5"`` as cell indices; blank is ``None``,
    the whole cell."""
    words = str(text or "").replace(",", " ").split()
    return [int(w) for w in words] if words else None


def write_input(job) -> JobResult:
    inp = orca_input(job.params)
    found = orca.cluster(job.structure, atoms_of(job.param("atoms")))
    refused, cautions = orca.problems(inp, found)
    if refused:
        return JobResult.failure(refused[0], detail="\n".join(refused))
    if job.folder is None:
        return JobResult.failure(
            "There is no workspace to write the input into; give "
            "xtal run a --workspace")
    title = str(job.param("name", "") or
                job.structure.meta.get("title") or "structure")
    stem = orca.safe_name(title)
    xyz = coordinates_name(stem)
    text = orca.render(inp, xyz, title=f"{title}, from Crystal Builder")
    written = (job.file(f"{stem}.inp"), job.file(xyz))
    atomic.write_text(written[1], orca.xyz_text(found, title),
                      encoding="utf-8")
    atomic.write_text(written[0], text, encoding="utf-8")
    job.note(text)
    for caution in cautions:
        job.note(f"caution: {caution}")
    n = orca.electrons(found.elements, inp.charge)
    said = (f"Wrote {stem}.inp and {xyz}: {found.n_atoms} atoms, "
            f"{orca.describe(n, inp.multiplicity)}")
    return JobResult(
        message=said + (f"; {len(cautions)} caution"
                        f"{'s' if len(cautions) != 1 else ''}"
                        if cautions else ""),
        artifacts=written,
        detail="\n".join(cautions))


INPUT = Action(
    name="input", label="Input file...",
    tip="An ORCA input and the coordinates it reads, in a run folder: "
        "the functional, basis, job and blocks chosen here, the charge "
        "and multiplicity checked against the electrons",
    params=PARAMS, run=write_input, dialog="orca-input", kind="input",
    keeps_markers=True)

ORCA = Module(
    name="orca", label="ORCA",
    description="ORCA quantum chemistry: an input file for the "
                "structure, written here and run wherever ORCA is.",
    order=13, group="energy", actions=(INPUT,))


def register(registry=MODULES) -> Module:
    return registry.register(ORCA)
