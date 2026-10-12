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

from xtal.core import molecule, p1, properties
from xtal.core.lattice import Lattice
from xtal.ff import optimize, thermo, vibrations
from xtal.ff import scan as driver
from xtal.ff.api import CalculatorStopped
from xtal.ff.registry import ENGINES
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

PARAMS = (
    Param("engine", "Engine", "choice", default="uff",
          choices=tuple((e.name, e.label) for e in ENGINES),
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
          minimum=1.0, maximum=5000.0, decimals=2, suffix=" K"),
    Param("t_min", "Curves from", "float", default=10.0, minimum=1.0,
          maximum=5000.0, decimals=1, suffix=" K"),
    Param("t_max", "Curves to", "float", default=800.0, minimum=1.0,
          maximum=5000.0, decimals=1, suffix=" K"),
    Param("t_step", "Curve step", "float", default=10.0, minimum=0.1,
          maximum=1000.0, decimals=1, suffix=" K"),
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
          minimum=1, maximum=11),
    Param("quasi_rrho", "Quasi-RRHO entropy", "bool", default=False,
          help="Grimme's correction: below the cutoff a mode's "
               "entropy goes over to a free rotor's, where the "
               "harmonic one runs away.  Soft modes are counted "
               "either way."),
    Param("qrrho_cutoff", "Soft-mode cutoff", "float", default=100.0,
          minimum=1.0, maximum=1000.0, decimals=1, suffix=" cm-1"),
    Param("method", "Hessian", "choice", default="auto",
          choices=(("auto", "Automatic"),
                   ("gamma", "Gamma only, every atom displaced")),
          help="Finite differences of the engine's forces at Gamma: "
               "6 evaluations per free atom and one more."),
    Param("delta", "Displacement", "float", default=vibrations.DELTA,
          minimum=1e-4, maximum=0.1, decimals=4, suffix=" A"),
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
          minimum=1, maximum=100000),
    Param("freeze", "Frozen sites", "text", default="",
          help="Site indices, comma-separated, held still in the "
               "relaxation and left out of the Hessian."),
)


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


def run_thermo(job) -> JobResult:
    """Relax a copy, take its Hessian, and report H, S and G."""
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
    total = vibrations.evaluations(structure, frozen_atoms)
    job.say(f"{kind}: {total} evaluations on {said} (Gamma only, "
            f"every free atom displaced by "
            f"{float(job.param('delta', vibrations.DELTA))} A)")
    if kind == "crystal":
        widths = molecule._perpendicular_widths(structure.lattice.matrix)
        if widths.min() < NARROW:
            job.say(f"the cell is {widths.min():.1f} A across at its "
                    f"narrowest: S and G are a Gamma-only estimate, "
                    f"missing the branches across the zone")

    forces = _Forces(job)
    try:
        found = vibrations.hessian(
            ENGINES.build(engine, structure, **settings), structure,
            kind=kind, delta=float(job.param("delta", vibrations.DELTA)),
            frozen=frozen_atoms, cancel=job.cancel,
            progress=_progress(job, total), record=forces.record)
    except CalculatorStopped:
        forces.flush()
        return JobResult.stopped(
            f"Stopped after {forces.pairs} of {total // 6} atoms' "
            f"displacements; they are in forces.npz.  No "
            f"thermochemistry: a Hessian with some of its columns is "
            f"not one.")
    forces.flush()

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

    def at(t):
        return thermo.thermochemistry(
            found.frequencies, found.weights, temperature=float(t),
            e_elec=found.energy, gas=gas, quasi_rrho=quasi,
            cutoff=cutoff, z=z)

    chosen = at(float(job.param("temperature", 298.15)))
    curve = [at(t) for t in temperatures(job)]
    block = found.to_modes_block(
        note="Choose a mode and press Animate to watch it in the "
             "transport bar.  Negative frequencies are imaginary.")

    report = Report(
        title=f"Thermochemistry ({said})",
        blocks=(_summary(chosen, found, kind, sigma, frozen_atoms),
                *_curves(curve), block))
    artifacts = []
    if job.folder is not None:
        atomic.write_text(job.file("thermo.dat"), thermo.as_dat(curve),
                          encoding="utf-8")
        atomic.write_text(job.file("modes.dat"), block.as_dat(),
                          encoding="utf-8")
        save_report(Report(title=report.title, blocks=tuple(
            b for b in report.blocks if not isinstance(b, Modes))),
            job.file(REPORT_NAME))
        artifacts = [job.file(n) for n in
                     ("thermo.dat", "modes.dat", REPORT_NAME)]
        job.note(_log_lines(chosen, found, kind, quasi, cutoff))

    return JobResult(message=_message(chosen), report=report,
                     artifacts=tuple(artifacts))


def _progress(job, total):
    tenth = max(total // 10, 1)

    def progress(done, _total):
        if done == 1 or done % tenth == 0 or done == total:
            job.say(f"displacement {done} of {total}")
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
        Row.of("Modes summed", str(vib.n_used), "", ""),
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
        Row.of("Hessian", "Gamma only, finite differences", "",
               f"{found.evaluations} evaluations"),
    ]
    if kind == "molecule":
        rows.insert(1, Row.of("Symmetry number", str(sigma), "", ""))
    return Table("Summary", tuple(rows), columns=SUMMARY_COLUMNS,
                 note=f"Per cell, Z = {result.z}." if kind == "crystal"
                 else "Per molecule.")


def _curves(results) -> list[Curve]:
    if not results:
        return []
    x = np.array([r.temperature for r in results])
    base = results[0].e_elec + results[0].zpe

    def series(attr):
        return np.array([getattr(r, attr) for r in results])

    return [
        Curve(title="Free energy", x=x, y=series("h") - base,
              x_label="T (K)",
              y_label="kcal/mol, from E + ZPE (per cell)",
              series=(("T S", series("ts")),
                      ("G", series("g") - base)),
              normalised=False,
              note="H and G are drawn from the electronic energy "
                   "plus the zero-point energy."),
        Curve(title="Heat capacity", x=x, y=series("cv"),
              x_label="T (K)", y_label="Cv (cal/(mol K), per cell)",
              series=(("S", series("s")),), normalised=False),
    ]


def _message(result) -> str:
    t = result.temperature
    g = result.per_unit(result.g)
    unit = "per formula unit" if result.kind == "crystal" \
        else "per molecule"
    vib = result.vibrations
    tail = []
    if vib.n_soft:
        tail.append(f"{vib.n_soft} modes below "
                    f"{result.cutoff:g} cm-1")
    if vib.n_imaginary:
        tail.append(f"{vib.n_imaginary} imaginary -- relax first")
    return (f"G({t:g} K) = {g:.3f} kcal/mol {unit}"
            + (", " + ", ".join(tail) if tail else ""))


def _log_lines(result, found, kind, quasi, cutoff) -> str:
    vib = result.vibrations
    return "\n".join([
        f"system: {kind}; method: Gamma only, finite differences, "
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
