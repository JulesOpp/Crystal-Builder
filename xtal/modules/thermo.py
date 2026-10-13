"""
xtal.modules.thermo
===================
Frequencies and thermochemistry, as a run of the Force Field module.

:mod:`xtal.ff.vibrations` builds the Hessian and :mod:`xtal.ff.thermo`
does the statistical mechanics; this decides what they are asked,
what is left on disk and what comes back on screen.

**It returns no structure**, as a scan does not.  *Relax first*
relaxes a copy -- a Hessian away from a minimum has modes that are the
gradient, not the curvature -- and the relaxed geometry is written
beside the report as ``relaxed.cif`` for whoever wants it, never put
over the tab the numbers are *of*.

**The forces are written as the displacements finish**
(``forces.npz``), every few seconds rather than every pair, because
MFU-4l's array is 60 MB and rewriting it four thousand times would
cost more than the Hessian.  Stop keeps them and gives no
thermochemistry: a Hessian with some of its columns is not one.

**What was left out is said.**  Imaginary modes are counted and kept
out of G, and the summary says in so many words that G is then not a
minimum's.  A crystal's G is its Helmholtz energy and the table says
so; a crystal narrower than :data:`NARROW` is a Gamma-only estimate of
S and the log says that too.
"""

from __future__ import annotations

import time

import numpy as np

from xtal.core import elements, limits, molecule, p1, properties
from xtal.core.lattice import Lattice
from xtal.ff import infrared as ir
from xtal.ff import optimize, phonons, thermo, vibrations
from xtal.ff import scan as driver
from xtal.ff.api import CalculatorStopped
from xtal.ff.registry import (
    ENGINES,
    engine_choices,
)
from xtal.io import atomic
from xtal.modules.job import JobResult
from xtal.modules.report import (
    REPORT_NAME,
    Curve,
    Modes,
    Report,
    Row,
    Table,
)
from xtal.modules.report import save as save_report
from xtal.params import Param, ParamError

#: A cell narrower than this (A, between opposite faces) has its
#: acoustic and low optic branches across the zone missed by Gamma
#: alone, and those are what a solid's entropy is made of.
NARROW = 10.0

#: How often forces.npz is rewritten while the Hessian runs, s.
SAVE_EVERY = 5.0

SUMMARY_COLUMNS = ("Quantity", "Per cell", "Per formula unit", "Unit")

IR_PARAMS = (
    Param("ir_charges", "IR charges", "choice", default="fixed",
          choices=(("fixed", "Fixed (EQeq, or UFF's own)"),
                   ("flux", "Re-solved at each displacement")),
          help="No engine here gives a charge or a dipole, so the "
               "intensities come from a charge model and the report "
               "names it.  Re-solving EQeq at each displaced geometry "
               "follows the charge a polar bond moves as it "
               "stretches."),
    Param("ir_fwhm", "Band width", "float", default=10.0, minimum=0.5,
          maximum=200.0, decimals=1, suffix=" cm-1",
          help="Full width at half height of each Lorentzian; the "
               "Results panel can redraw it."),
)

PARAMS = (
    Param("engine", "Engine", "choice", default="uff",
          choices=engine_choices,
          help="Which energy engine the Hessian is taken under.  The "
               "Force Field panel's engine and its options are what "
               "the window hands in."),
    Param("system", "System", "choice", default="auto",
          choices=(("auto", "Decide from the structure"),
                   ("crystal", "Crystal (harmonic solid)"),
                   ("molecule", "Molecule (ideal gas)")),
          help="A molecule alone in a box gets translation, rotation "
               "and spin as an ideal gas, and its rotations are "
               "projected out of the Hessian; a crystal gets the "
               "harmonic solid, and G is its Helmholtz energy."),
    Param("temperature", "Temperature", "float", default=298.15,
          minimum=1.0, maximum=5000.0, decimals=2, suffix=" K",
          help="The temperature the summary table is at."),
    Param("t_min", "Curves from", "float", default=10.0, minimum=1.0,
          maximum=5000.0, decimals=1, suffix=" K",
          help="Where the H, TS, G and Cv curves and thermo.dat "
               "start."),
    Param("t_max", "Curves to", "float", default=800.0, minimum=1.0,
          maximum=5000.0, decimals=1, suffix=" K",
          help="Where the curves and thermo.dat end."),
    Param("t_step", "Curve step", "float", default=10.0, minimum=0.1,
          maximum=1000.0, decimals=1, suffix=" K",
          help="The spacing of the curves' temperatures."),
    Param("pressure", "Pressure", "float", default=1.0, minimum=1e-9,
          maximum=1e6, decimals=4, suffix=" bar",
          help="A gas's translational entropy depends on it; a "
               "solid's G does not, to the precision anything here "
               "is computed."),
    Param("sigma", "Symmetry number", "int", default=0, minimum=0,
          maximum=120,
          help="Rotations that map the molecule onto itself: water "
               "2, methane 12.  0 counts them from the geometry."),
    Param("multiplicity", "Spin multiplicity", "int", default=1,
          minimum=1, maximum=11,
          help="2S + 1 of a molecule's ground state: R ln of it is "
               "added to S.  The engine is not told."),
    Param("quasi_rrho", "Quasi-RRHO entropy", "bool", default=False,
          help="Grimme's correction: below the cutoff a mode's "
               "entropy goes over to a free rotor's, where the "
               "harmonic one runs away.  Soft modes are counted "
               "either way."),
    Param("qrrho_cutoff", "Soft-mode cutoff", "float", default=100.0,
          minimum=1.0, maximum=1000.0, decimals=1, suffix=" cm-1",
          help="Below this a mode is counted as soft, and with "
               "quasi-RRHO its entropy goes over to a rotor's."),
    Param("method", "Hessian", "choice", default="auto",
          choices=(("auto", "Automatic"),
                   ("phonopy", "phonopy, by symmetry"),
                   ("gamma", "Gamma only, every atom"),
                   ("analytic", "Analytic, from the engine")),
          help="Finite differences of the engine's forces, or with "
               "Analytic the engine's own second derivatives (MACE "
               "only), which have no step to be noisy in but hold "
               "about 13 MB an atom and use no symmetry.  "
               "phonopy displaces only the atoms and directions the "
               "space group does not already relate, and samples a "
               "small cell's branches across the zone; Gamma only "
               "displaces every free atom, 6 evaluations each, and is "
               "what a molecule or frozen atoms take.  Automatic is "
               "phonopy where it is installed and can be used."),
    Param("supercell", "Supercell", "text", default="auto",
          help="For phonopy: auto repeats the cell until it is "
               f"{phonons.MIN_WIDTH:g} A across in every direction; "
               "three counts (2 2 1) choose; gamma uses the cell "
               "alone."),
    Param("mesh", "q-mesh density", "float", default=phonons.MESH,
          minimum=1.0, maximum=1000.0, decimals=0, suffix=" A",
          help="For phonopy with a supercell: the points along each "
               "reciprocal axis are about this over the cell length.  "
               "The mode table and the IR spectrum are Gamma's either "
               "way."),
    Param("delta", "Displacement", "float", default=vibrations.DELTA,
          minimum=1e-4, maximum=0.1, decimals=4, suffix=" A",
          help="How far each atom is moved either way.  Small enough "
               "that the force is linear in it, large enough that an "
               "ML engine's noise stays below the difference."),
    Param("relax_first", "Relax first", "bool", default=True,
          help="Relax a copy before the Hessian, the cell too for a "
               "crystal.  Away from a minimum the modes are the "
               "gradient's and some come out imaginary.  The relaxed "
               "copy is written as relaxed.cif; the tab is left "
               "alone."),
    Param("tolerance", "Force tolerance", "float", default=0.01,
          minimum=1e-6, decimals=4, suffix=" kcal/mol/A",
          help="Tighter than an ordinary optimisation: a residual "
               "force is a curvature the Hessian cannot tell from a "
               "soft mode."),
    Param("max_steps", "Relaxation steps", "int", default=2000,
          minimum=1, maximum=100000,
          help="A ceiling on Relax first.  A relaxation that stops "
               "here says so, and the modes then carry what was "
               "left."),
    Param("ir", "Also compute the IR spectrum", "bool", default=False,
          help="Intensities from a charge model over the same "
               "Hessian: no extra evaluations with fixed charges."),
    *IR_PARAMS,
    Param("freeze", "Frozen sites", "text", default="",
          help="Site indices, comma-separated, held still in the "
               "relaxation and left out of the Hessian."),
)


#: What only the thermochemistry reads, left out of the IR action's form.
_THERMO_ONLY = {"temperature", "t_min", "t_max", "t_step", "pressure",
                "sigma", "multiplicity", "quasi_rrho", "qrrho_cutoff",
                "ir", "supercell", "mesh"}

INFRARED_PARAMS = tuple(p for p in PARAMS if p.name not in _THERMO_ONLY)


def frozen_sites(text: str, n_sites: int) -> list[int]:
    """The site indices ``freeze`` names."""
    out = []
    for word in str(text or "").replace(",", " ").split():
        try:
            index = int(word)
        except ValueError:
            raise ParamError(
                f"freeze: {word!r} is not a site index") from None
        if not 0 <= index < n_sites:
            raise ParamError(
                f"freeze: there is no site {index} (the structure has "
                f"{n_sites})")
        out.append(index)
    return sorted(set(out))


def temperatures(job) -> np.ndarray:
    low = float(job.param("t_min", 10.0))
    high = float(job.param("t_max", 800.0))
    step = float(job.param("t_step", 10.0))
    if high < low:
        low, high = high, low
    count = int(np.floor((high - low) / step + 1e-9)) + 1
    return low + step * np.arange(count)


def run_thermo(job, thermochemistry: bool = True) -> JobResult:
    """Relax a copy, take its Hessian, and report H, S and G -- and
    the IR spectrum when asked, or only that."""
    from xtal.modules.scan import _engine_said, engine_settings

    structure = job.structure.copy()
    driver.hold_bonding(structure)
    engine = str(job.param("engine", "uff"))
    settings = engine_settings(job, engine)
    try:
        frozen = frozen_sites(job.param("freeze", ""),
                              structure.n_sites)
    except ParamError as error:
        return JobResult.failure(str(error))
    kind = str(job.param("system", "auto"))
    if kind == "auto":
        kind = "molecule" if molecule.is_isolated(structure) \
            else "crystal"
    said = _engine_said(engine, settings)
    infrared_too = not thermochemistry or bool(job.param("ir", False))
    try:
        method, why = choose_method(str(job.param("method", "auto")),
                                    kind, frozen, engine=engine)
        if method == "phonopy" and thermochemistry:
            _check_supercell(structure, job.param("supercell", "auto"))
        if method == "analytic":
            verdict = check_analytic(structure, frozen)
            if verdict.warned:
                job.say(verdict.sentence)
    except ParamError as error:
        return JobResult.failure(str(error))
    if why:
        job.say(why)

    if bool(job.param("relax_first", True)):
        relax_cell = kind == "crystal"
        job.say(f"relaxing a copy on {said}"
                + (", cell included" if relax_cell else ""))
        result = optimize.run(
            ENGINES.build(engine, structure, **settings), structure,
            method="smart", frozen=frozen, cancel=job.cancel,
            relax_cell=relax_cell,
            max_steps=int(job.param("max_steps", 2000)),
            force_tolerance=float(job.param("tolerance", 0.01)))
        if result.stopped:
            return JobResult.stopped(
                "Stopped while relaxing; no Hessian was taken.")
        # Through set_frac, which touches the structure: assigning a
        # site's frac leaves the P1 cell cached at the old geometry,
        # and with no cell change to touch it the Hessian was taken
        # where the relaxation started.
        for index, row in enumerate(result.frac):
            structure.set_frac(index, row)
        if result.matrix is not None:
            structure.set_lattice(Lattice(result.matrix))
        job.say(f"relaxed: {result.summary()}")
        if not result.converged:
            job.say("the relaxation did not reach the force tolerance; "
                    "expect soft or imaginary modes from what is left")
        if job.folder is not None:
            from xtal.io import FORMATS
            FORMATS.write(structure, job.file("relaxed.cif"),
                          perception=True)

    cell = p1.expand(structure)
    frozen_atoms = [i for i in range(cell.n_atoms)
                    if int(cell.site_idx[i]) in frozen]
    delta = float(job.param("delta", vibrations.DELTA))
    what = "thermochemistry" if thermochemistry else "spectrum"
    if method == "phonopy":
        found = _by_phonopy(job, structure, engine, settings, said,
                            delta, what, thermochemistry)
    elif method == "analytic":
        found = _analytic(job, structure, engine, settings, said, kind,
                          frozen_atoms, what)
    else:
        found = _at_gamma(job, structure, engine, settings, said, kind,
                          delta, frozen_atoms, what)
    if isinstance(found, JobResult):
        return found
    calculator = None
    if infrared_too:
        calculator = ENGINES.build(engine, structure, **settings)

    block = found.to_modes_block(
        note="Choose a mode and press Animate to watch it in the "
             "transport bar.  Negative frequencies are imaginary.")
    files = {"modes.dat": block.as_dat()}
    blocks: list = []
    message = ""
    if thermochemistry:
        chosen, curve, sigma = _thermochemistry(job, structure, found,
                                                kind)
        blocks += [_summary(chosen, found, kind, sigma, frozen_atoms),
                   *_curves(curve)]
        files["thermo.dat"] = thermo.as_dat(curve)
        message = _message(chosen, found)
        job.note(_log_lines(chosen, found, kind, chosen.quasi_rrho,
                            chosen.cutoff))
    blocks.append(block)
    if infrared_too:
        model = str(job.param("ir_charges", "fixed"))
        job.say(f"IR intensities from {model} charges")
        born, source = ir.born_charges(structure, found, model=model,
                                       calculator=calculator)
        spectrum = ir.spectrum_block(
            found, ir.intensities(found, born), source,
            fwhm=float(job.param("ir_fwhm", ir.FWHM)))
        blocks.append(spectrum)
        files["ir.dat"] = spectrum.as_dat()
        files["ir_broadened.xy"] = spectrum.as_xy()
        job.note(f"IR: {source}")
        if not thermochemistry:
            blocks.insert(0, _modes_summary(found, kind, frozen_atoms,
                                            source))
            message = _spectrum_message(found, spectrum, model)

    title = ("Thermochemistry" if thermochemistry else "IR spectrum")
    report = Report(title=f"{title} ({said})", blocks=tuple(blocks))
    artifacts = []
    if job.folder is not None:
        for name, text in files.items():
            atomic.write_text(job.file(name), text, encoding="utf-8")
        save_report(Report(title=report.title, blocks=tuple(
            b for b in report.blocks if not isinstance(b, Modes))),
            job.file(REPORT_NAME))
        artifacts = [job.file(n) for n in (*files, REPORT_NAME)]

    return JobResult(message=message, report=report,
                     artifacts=tuple(artifacts))


def run_infrared(job) -> JobResult:
    """The modes and their IR spectrum, without the thermochemistry."""
    return run_thermo(job, thermochemistry=False)


def choose_method(asked: str, kind: str, frozen=(),
                  engine: str | None = None) -> tuple[str, str]:
    """``(method, what to say about it)``: phonopy or gamma, from what
    was asked, what is installed and what the structure is, or
    analytic when that is asked of an ``engine`` that has one --
    Automatic never chooses it.  Raises :class:`ParamError` when
    phonopy or analytic was asked for by name and cannot be had."""
    if asked == "gamma":
        return "gamma", ""
    if asked == "analytic":
        if engine is not None and not has_analytic_hessian(engine):
            label = ENGINES.get(engine).label if engine in ENGINES \
                else engine
            raise ParamError(
                f"{label} has no analytic Hessian; choose phonopy or "
                f"Gamma only, which take it by finite differences")
        return "analytic", ""
    if asked not in ("auto", "phonopy"):
        raise ParamError(f"method is auto, phonopy, gamma or analytic, "
                         f"not {asked!r}")
    named = asked == "phonopy"
    if kind == "molecule":
        return "gamma", ("a molecule takes the Gamma-only Hessian: "
                         "crystal symmetry has nothing to save there"
                         if named else "")
    if frozen:
        if named:
            raise ParamError(
                "phonopy cannot hold atoms still -- its symmetry moves "
                "every one; choose Gamma only to freeze sites")
        return "gamma", ""
    if not phonons.installed():
        if named:
            raise ParamError("phonopy is not installed; "
                             + phonons.install_hint())
        return "gamma", ("phonopy is not installed, so every atom is "
                         "displaced at Gamma; "
                         + phonons.install_hint())
    return "phonopy", ""


def has_analytic_hessian(engine: str) -> bool:
    """Whether ``engine`` offers its own second derivatives."""
    return engine in ENGINES and "hessian" in ENGINES.get(engine).provides


def check_analytic(structure, frozen_sites_=()):
    """The analytic route's size verdict, refused here (before any
    relaxation) over the limit: the retained graph grows with every
    atom, and a laptop swapping is not a run that finishes."""
    cell = p1.expand(structure)
    held = {int(i) for i in frozen_sites_}
    atoms = [i for i in range(cell.n_atoms)
             if int(cell.site_idx[i]) in held]
    verdict = limits.check_hessian(
        vibrations.free_atoms(structure, atoms))
    if verdict.refused:
        raise ParamError(verdict.sentence)
    return verdict


def _check_supercell(structure, asked):
    """The repeats, refused here (before any relaxation) when they
    are over the size limit."""
    try:
        repeats = phonons.supercell_of(structure, asked)
    except ValueError as error:
        raise ParamError(f"supercell: {error}") from None
    real = sum(1 for e in p1.expand(structure).elements
               if not elements.is_dummy(e))
    verdict = limits.check_phonons(real, repeats)
    if verdict.refused:
        raise ParamError(phonons.said(verdict))
    return repeats


def _say_if_narrow(job, structure) -> None:
    widths = molecule._perpendicular_widths(structure.lattice.matrix)
    if widths.min() < NARROW:
        job.say(f"the cell is {widths.min():.1f} A across at its "
                f"narrowest: S and G are a Gamma-only estimate, "
                f"missing the branches across the zone")


def _at_gamma(job, structure, engine, settings, said, kind, delta,
              frozen_atoms, what):
    """Every free atom displaced at Gamma; a :class:`JobResult` if
    stopped."""
    total = vibrations.evaluations(structure, frozen_atoms)
    job.say(f"{kind}: {total} evaluations on {said} (Gamma only, "
            f"every free atom displaced by {delta} A)")
    if kind == "crystal":
        _say_if_narrow(job, structure)

    forces = _Forces(job)
    calculator = ENGINES.build(engine, structure, **settings)
    try:
        found = vibrations.hessian(
            calculator, structure, kind=kind, delta=delta,
            frozen=frozen_atoms, cancel=job.cancel,
            progress=_progress(job, total), record=forces.record)
    except CalculatorStopped:
        forces.flush()
        return JobResult.stopped(
            f"Stopped after {forces.pairs} of {total // 6} atoms' "
            f"displacements; they are in forces.npz.  No {what}: a "
            f"Hessian with some of its columns is not one.")
    forces.flush()
    return found


def _analytic(job, structure, engine, settings, said, kind,
              frozen_atoms, what):
    """The engine's own Hessian, a row at a time; a
    :class:`JobResult` if stopped."""
    total = 3 * vibrations.free_atoms(structure, frozen_atoms) + 1
    job.say(f"{kind}: the analytic Hessian on {said}, {total - 1} rows "
            f"after one evaluation")
    if kind == "crystal":
        _say_if_narrow(job, structure)
    calculator = ENGINES.build(engine, structure, **settings)
    try:
        return vibrations.hessian(
            calculator, structure, kind=kind, frozen=frozen_atoms,
            cancel=job.cancel,
            progress=_progress(job, total, "row"), analytic=True)
    except CalculatorStopped:
        return JobResult.stopped(
            f"Stopped part way through the Hessian's rows.  No {what}: "
            f"a Hessian with some of its rows is not one.")


def _by_phonopy(job, structure, engine, settings, said, delta, what,
                thermochemistry=True):
    """phonopy's displacements, its force constants and, with a
    supercell, its q-mesh; a :class:`JobResult` if stopped or
    refused.  A spectrum alone is Gamma's, which the cell's own force
    constants already sum exactly: a supercell would only cost."""
    asked = (job.param("supercell", "auto") if thermochemistry
             else "gamma")
    try:
        ahead = phonons.plan(structure, asked, delta=delta)
    except ValueError as error:
        return JobResult.failure(str(error))
    if ahead.verdict.refused:
        return JobResult.failure(phonons.said(ahead.verdict))
    n = "x".join(str(v) for v in ahead.supercell)
    job.say(f"crystal: phonopy, supercell {n} ({ahead.atoms} atoms), "
            f"{ahead.displacements} displacements by {delta} A on "
            f"{said}")
    if ahead.verdict.warned:
        job.say(phonons.said(ahead.verdict))
    if ahead.supercell == (1, 1, 1):
        widths = molecule._perpendicular_widths(structure.lattice.matrix)
        if widths.min() < NARROW:
            job.say(f"the cell is {widths.min():.1f} A across at its "
                    f"narrowest and no supercell was asked for: S and "
                    f"G are a Gamma-only estimate")

    forces = _Displaced(job)
    try:
        found = phonons.phonopy_vibrations(
            lambda big: ENGINES.build(engine, big, **settings),
            structure, supercell=asked,
            mesh=float(job.param("mesh", phonons.MESH)), delta=delta,
            cancel=job.cancel,
            progress=_progress(job, ahead.evaluations),
            record=forces.record,
            save=(job.file("phonopy_params.yaml")
                  if job.folder is not None else None))
    except CalculatorStopped:
        forces.flush()
        return JobResult.stopped(
            f"Stopped after {len(forces.forces)} of "
            f"{ahead.displacements} displacements; they are in "
            f"forces.npz.  No {what}: force constants from some of "
            f"the displacements are not force constants.")
    except ValueError as error:
        return JobResult.failure(str(error))
    forces.flush()
    if found.q_mesh is not None:
        job.say("q-mesh " + "x".join(str(v) for v in found.q_mesh))
    return found


def _thermochemistry(job, structure, found, kind):
    """``(at the chosen temperature, along the curve, sigma)``."""
    z = properties.formula(structure)[1]
    gas = None
    sigma = int(job.param("sigma", 0))
    if kind == "molecule":
        elements, whole = molecule.whole(structure)
        if not sigma:
            sigma = molecule.rotational_symmetry_number(elements, whole)
        gas = thermo.IdealGas(
            masses=tuple(vibrations.masses_of(elements)), cart=whole,
            sigma=sigma, multiplicity=int(job.param("multiplicity", 1)),
            pressure=float(job.param("pressure", 1.0)))
        z = 1
    quasi = bool(job.param("quasi_rrho", False))
    cutoff = float(job.param("qrrho_cutoff", thermo.QRRHO_CUTOFF))

    frequencies, weights = found.sampled()

    def at(t):
        return thermo.thermochemistry(
            frequencies, weights, temperature=float(t),
            e_elec=found.energy, gas=gas, quasi_rrho=quasi,
            cutoff=cutoff, z=z)

    return (at(float(job.param("temperature", 298.15))),
            [at(t) for t in temperatures(job)], sigma)


def hessian_said(found) -> str:
    """How the Hessian was taken, as the summary and the log say it."""
    if found.method == "analytic":
        return "Gamma only, analytic (the engine's own)"
    if found.method != "phonopy":
        return "Gamma only, finite differences"
    n = "x".join(str(v) for v in found.supercell or (1, 1, 1))
    if found.q_mesh is None:
        return f"phonopy, Gamma only (supercell {n})"
    mesh = "x".join(str(v) for v in found.q_mesh)
    return f"phonopy, supercell {n}, q-mesh {mesh}"


def _modes_summary(found, kind, frozen_atoms, source) -> Table:
    imaginary = int(np.count_nonzero(
        found.frequencies < thermo.IMAGINARY_BELOW))
    return Table("Summary", (
        Row("System", "molecule" if kind == "molecule" else "crystal"),
        Row("Modes", str(len(found.frequencies))),
        Row("Imaginary modes", str(imaginary),
            note="" if not imaginary else
            "An imaginary mode is a direction the energy falls along: "
            "the structure was not at a minimum.  Relax it first."),
        Row("Displaced atoms", str(len(found.free)),
            note="" if not frozen_atoms else
            f"{len(frozen_atoms)} frozen atoms were not displaced."),
        Row("Hessian", hessian_said(found),
            f"{found.evaluations} evaluations"),
        Row("Intensities", "charge model", note=source),
    ))


def _spectrum_message(found, spectrum, model) -> str:
    imaginary = int(np.count_nonzero(
        found.frequencies < thermo.IMAGINARY_BELOW))
    strongest = (float(spectrum.frequencies[np.argmax(
        spectrum.intensities)]) if len(spectrum.frequencies) else 0.0)
    return (f"{len(spectrum.frequencies)} IR bands, the strongest at "
            f"{strongest:.0f} cm-1 ({model} charges)"
            + (f", {imaginary} imaginary -- relax first"
               if imaginary else ""))


def _progress(job, total, what="displacement"):
    tenth = max(total // 10, 1)

    def progress(done, _total):
        if done == 1 or done % tenth == 0 or done == total:
            job.say(f"{what} {done} of {total}")
    return progress


class _Forces:
    """``forces.npz``: each displaced pair's forces, kept as it comes
    and written out every :data:`SAVE_EVERY` seconds and at the end,
    so Stop leaves what was reached on disk."""

    def __init__(self, job):
        self.job = job
        self.atoms: list[int] = []
        self.axes: list[int] = []
        self.plus: list[np.ndarray] = []
        self.minus: list[np.ndarray] = []
        self.pairs_seen: set[int] = set()
        self._last = time.monotonic()

    @property
    def pairs(self) -> int:
        return len(self.pairs_seen)

    def record(self, atom, axis, plus, minus) -> None:
        self.atoms.append(atom)
        self.axes.append(axis)
        self.plus.append(plus)
        self.minus.append(minus)
        if axis == 2:
            self.pairs_seen.add(atom)
        if time.monotonic() - self._last > SAVE_EVERY:
            self.flush()

    def flush(self) -> None:
        self._last = time.monotonic()
        if self.job.folder is None:
            return
        path = self.job.file("forces.npz")
        with atomic.replacing(path) as partial:
            with open(partial, "wb") as handle:
                np.savez(handle, atom=np.array(self.atoms, dtype=int),
                         axis=np.array(self.axes, dtype=int),
                         plus=np.array(self.plus),
                         minus=np.array(self.minus))


class _Displaced(_Forces):
    """phonopy's displaced supercells' forces, in its own atom order
    (eV/A, as phonopy reads them), kept the same way."""

    def __init__(self, job):
        super().__init__(job)
        self.steps: list[np.ndarray] = []
        self.forces: list[np.ndarray] = []

    def record(self, index, step, forces) -> None:
        self.steps.append(step)
        self.forces.append(forces)
        if time.monotonic() - self._last > SAVE_EVERY:
            self.flush()

    def flush(self) -> None:
        self._last = time.monotonic()
        if self.job.folder is None:
            return
        path = self.job.file("forces.npz")
        with atomic.replacing(path) as partial:
            with open(partial, "wb") as handle:
                np.savez(handle, displacement=np.array(self.steps),
                         forces=np.array(self.forces))


def _summary(result, found, kind, sigma, frozen_atoms) -> Table:
    t = result.temperature
    vib = result.vibrations

    def quantity(label, value, unit, note=""):
        per = result.per_unit(value)
        return Row.of(label, f"{value:.4f}", f"{per:.4f}", unit,
                      note=note)

    g_note = ("" if kind == "molecule" else
              "A solid's G is its Helmholtz energy F: PV at one bar "
              "is thousandths of a kcal/mol per cell.")
    imaginary_note = ""
    if vib.n_imaginary:
        imaginary_note = (
            "An imaginary mode is a direction the energy falls along, "
            "so this is not a minimum and G is not a minimum's G; the "
            "modes are left out of it.  Relax first, with a tighter "
            "tolerance.")
    rows = [
        Row.of("System", "molecule (ideal gas)" if kind == "molecule"
               else "crystal (harmonic solid)", "", ""),
        quantity("E (electronic)", result.e_elec, "kcal/mol"),
        quantity("Zero-point energy", result.zpe, "kcal/mol"),
        quantity(f"H({t:g} K)", result.h, "kcal/mol"),
        quantity(f"T S({t:g} K)", result.ts, "kcal/mol"),
        quantity(f"G({t:g} K)", result.g, "kcal/mol", g_note),
        quantity("S", result.s, "cal/(mol K)"),
        quantity("Cv", result.cv, "cal/(mol K)"),
        Row.of("Modes summed", str(vib.n_used), "", "",
               note=_mesh_note(found)),
        Row.of("Imaginary modes", str(vib.n_imaginary), "", "",
               note=imaginary_note),
        Row.of("Zero modes", str(vib.n_zero), "", "",
               note="Translations, rotations and acoustic modes at "
                    "Gamma: zero in principle, and left out of the "
                    "sum."),
        Row.of("Soft modes", str(vib.n_soft), "", "cm-1 below "
               f"{result.cutoff:g}",
               note=("Interpolated towards a free rotor's entropy "
                     "(quasi-RRHO)." if result.quasi_rrho else
                     "Summed harmonically; their entropy is the "
                     "least certain part of S.")),
        Row.of("Displaced atoms", str(len(found.free)), "", "",
               note="" if not frozen_atoms else
               f"{len(frozen_atoms)} frozen atoms were not displaced."),
        Row.of("Hessian", hessian_said(found), "",
               f"{found.evaluations} evaluations"),
    ]
    if kind == "molecule":
        rows.insert(1, Row.of("Symmetry number", str(sigma), "", ""))
    return Table("Summary", tuple(rows), columns=SUMMARY_COLUMNS,
                 note=f"Per cell, Z = {result.z}." if kind == "crystal"
                 else "Per molecule.")


def _mesh_note(found) -> str:
    """Counts over a q-mesh are its entries, a cell's worth of modes
    at each of its irreducible points; say so where they are."""
    if found.mesh_frequencies is None:
        return ""
    branches = max(len(found.frequencies), 1)
    points = len(found.mesh_frequencies) // branches
    return (f"Counted over the q-mesh: {branches} branches at each of "
            f"{points} irreducible points, each weighed by its share "
            f"of the zone.  The mode table is Gamma's.")


def _curves(results) -> list[Curve]:
    if not results:
        return []
    x = np.array([r.temperature for r in results])
    base = results[0].e_elec + results[0].zpe

    def series(attr):
        return np.array([getattr(r, attr) for r in results])

    return [
        Curve(title="H, TS and G (kcal/mol per cell, from E + ZPE)",
              x=x, y=series("h") - base, x_label="T (K)", y_label="H",
              series=(("T S", series("ts")),
                      ("G", series("g") - base)),
              normalised=False,
              note="H and G are drawn from the electronic energy "
                   "plus the zero-point energy."),
        Curve(title="Cv and S (cal/(mol K) per cell)", x=x,
              y=series("cv"), x_label="T (K)", y_label="Cv",
              series=(("S", series("s")),), normalised=False),
    ]


def _message(result, found=None) -> str:
    t = result.temperature
    g = result.per_unit(result.g)
    unit = "per formula unit" if result.kind == "crystal" \
        else "per molecule"
    vib = result.vibrations
    tail = []
    meshed = found is not None and found.mesh_frequencies is not None
    if vib.n_soft:
        if meshed:
            # Entries of a mesh are not modes of the cell: its share
            # of the zone is what reads.
            frequencies, weights = found.sampled()
            soft = (frequencies > thermo.ZERO_BELOW) \
                & (frequencies < result.cutoff)
            share = weights[soft].sum() / weights.sum()
            tail.append(f"{share:.0%} of the modes below "
                        f"{result.cutoff:g} cm-1")
        else:
            tail.append(f"{vib.n_soft} modes below "
                        f"{result.cutoff:g} cm-1")
    if vib.n_imaginary:
        tail.append(("imaginary modes on the q-mesh" if meshed else
                     f"{vib.n_imaginary} imaginary")
                    + " -- relax first")
    return (f"G({t:g} K) = {g:.3f} kcal/mol {unit}"
            + (", " + ", ".join(tail) if tail else ""))


def _log_lines(result, found, kind, quasi, cutoff) -> str:
    vib = result.vibrations
    return "\n".join([
        f"system: {kind}; method: {hessian_said(found)}, "
        f"{found.evaluations} evaluations",
        f"modes: {vib.n_used} summed, {vib.n_imaginary} imaginary "
        f"(below {thermo.IMAGINARY_BELOW:g} cm-1), {vib.n_zero} zero "
        f"(below {thermo.ZERO_BELOW:g}), {vib.n_soft} soft (below "
        f"{cutoff:g})",
        "entropy: " + ("quasi-RRHO (Grimme 2012)" if quasi
                       else "harmonic"),
        *(f"{label}: {cell:.6f} per cell, {unit_value:.6f} per formula "
          f"unit, {unit}" for label, cell, unit_value, unit
          in result.as_rows()),
    ])
