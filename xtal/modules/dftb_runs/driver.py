"""
xtal.modules.dftb_runs.driver
=============================
DFTB+'s own driver: a relaxation, with the cell if asked, and molecular
dynamics.

The DFTB+ panel's *Optimise* is our optimiser taking one DFTB+
evaluation a step -- which is what keeps a space group and every
frozen site exactly, and costs a process launch and an SCC cycle from
scratch per step.  These hand the whole run to DFTB+: one process,
charges carried between steps in memory, the cell relaxed against the
stress DFTB+ computes analytically.  What that gives up is symmetry --
DFTB+ moves a P1 cell -- so the answer is **mapped back onto the
sites** (:func:`xtal.core.p1.parent_frac`, one image per site, the
same map a trajectory is played back through) and the largest distance
between where DFTB+ put an atom and where the space group now puts it
is reported beside the energy.  A few thousandths of an Angstrom is a
converged relaxation; a tenth is a structure that wanted to leave its
group, and the report says which.

Frozen sites are ``MovedAtoms``: every atom of every site not frozen,
numbered the way DFTB+ numbers them.  The frozen set arrives as site
*labels*, because the run is handed a structure with its markers
taken out and a site index from the document would name the wrong
site after one.

Bonds and atoms are untouched, as with every optimiser.  The geometry
comes back as one undoable replacement of the structure it was run on.
"""

from __future__ import annotations

import numpy as np

from xtal.core import p1
from xtal.core.lattice import Lattice
from xtal.ff.dftb import hsd, outputs
from xtal.io.gen import read_gen_string
from xtal.io.trajectory import Frame, Trajectory
from xtal.modules.dftb_runs import common
from xtal.modules.job import JobResult
from xtal.modules.report import Curve, Report, Row, Table

#: 1 GPa in Pascal, for the pressure field.
GPA = 1e9


def moved_atoms(structure, job) -> tuple | None:
    """One-based cell atoms of every site not frozen, or ``None`` when
    everything moves."""
    if not job.param("freeze", True):
        return None
    frozen = {str(label) for label in job.param("frozen", ()) or ()}
    if not frozen:
        return None
    cell = p1.expand(structure)
    moved = tuple(k + 1 for k in range(cell.n_atoms)
                  if structure.sites[int(cell.site_idx[k])].label
                  not in frozen)
    if not moved:
        raise common.RunFailed(JobResult.failure(
            "every site is frozen, so there is nothing to move"))
    return moved


# ======================================================================
#  RELAXATION
# ======================================================================

@common.guarded
def relax(job) -> JobResult:
    structure = job.structure
    options = common.options_of(job)
    common.refuse(structure, options)
    symbols = sorted(set(common.symbols_of(structure)))
    lattice = bool(job.param("lattice", False))
    driver = hsd.Relax(
        lattice=lattice,
        pressure=float(job.param("pressure", 0.0)) * GPA,
        moved=moved_atoms(structure, job),
        max_force=float(job.param("max_force", 1e-4)),
        max_steps=int(job.param("max_steps", 200)),
        optimiser=str(job.param("optimiser", "lbfgs")))
    reader = outputs.StepReader(on_step=_say_step(job))

    with common.folder(job) as directory:
        common.invoke(job, directory, structure, hsd.hsd_string(
            symbols, options, k_points=common.mesh(structure, options),
            driver=driver), on_line=reader)
        reader.finish()
        final = read_gen_string(common.read(directory, "geo_end.gen"))
        converged = "Geometry converged" in \
            (directory / "detailed.out").read_text() \
            if (directory / "detailed.out").is_file() else False

    try:
        adopted, deviation = adopt(structure, final, lattice)
    except LeftTheGroup as left:
        group = structure.space_group.short_name
        return JobResult(
            message=f"DFTB+ moved the atoms out of {group}, so the "
                    f"geometry was not adopted",
            ok=False,
            detail=f"Put back into {group}, its positions would "
                   f"generate {left.generated} atoms where there are "
                   f"{left.given}.  The relaxed cell is geo_end.gen in "
                   f"the run folder; Reduce to P1 and run again to "
                   f"keep it.")
    steps = np.array([s[0] for s in reader.steps], dtype=float)
    energies = np.array([s[1] for s in reader.steps])
    forces = np.array([s[2] for s in reader.steps])
    rows = [
        Row("Converged", "yes" if converged else "no",
            note="" if converged else
            "DFTB+ stopped at its step limit or without meeting the "
            "force criterion; the geometry is where it stopped."),
        Row("Steps", str(len(reader.steps))),
        Row.number("Final energy", energies[-1] if len(energies)
                   else float("nan"), "kcal/mol"),
        Row.number("Largest move off the group", deviation, "A",
                   note="How far the space group puts an atom from "
                        "where DFTB+ left it.  DFTB+ relaxes a P1 "
                        "cell; a large value is a structure that "
                        "wanted a lower symmetry."),
    ]
    if lattice:
        a, b, c, alpha, beta, gamma = adopted.lattice.parameters
        rows.append(Row("Cell", f"{a:.4f} {b:.4f} {c:.4f} "
                                f"{alpha:.2f} {beta:.2f} {gamma:.2f}"))
    blocks = [Table("Relaxation", tuple(rows))]
    if len(steps) > 1:
        blocks.append(Curve(title="Energy", x=steps, y=energies,
                            x_label="step", y_label="kcal/mol",
                            normalised=False))
        blocks.append(Curve(title="Largest force", x=steps, y=forces,
                            x_label="step", y_label="kcal/mol/A",
                            normalised=False))
    message = (f"DFTB+ relaxed the {'cell and ' if lattice else ''}"
               f"atoms in {len(reader.steps)} steps"
               + ("" if converged else " without converging")
               + f"; largest move off the group {deviation:.4f} A")
    return JobResult(message=message, structure=adopted,
                     report=Report(title="DFTB+ relaxation",
                                   blocks=tuple(blocks)))


class LeftTheGroup(Exception):
    """DFTB+'s geometry is not one the space group can hold."""

    def __init__(self, generated: int, given: int):
        super().__init__(f"{generated} atoms from {given}")
        self.generated = generated
        self.given = given


def adopt(structure, final, lattice: bool):
    """``(structure, deviation)``: ``final``'s P1 cell carried back onto
    ``structure``'s sites, and the largest distance in Angstrom between
    an atom DFTB+ placed and the atom the group now generates there."""
    cell = p1.expand(structure)
    ending = p1.expand(final)
    if tuple(ending.elements) != tuple(cell.elements):
        raise common.RunFailed(JobResult.failure(
            "DFTB+ returned a different set of atoms from the one it "
            "was given"))
    out = structure.copy()
    if lattice:
        out.lattice = Lattice(np.asarray(final.lattice.matrix, float))
    # geo_end.gen is wrapped or not as DFTB+ likes; each atom is put
    # back on the lattice translation it started at, which is the
    # image the reference cell's operations name.
    raw = ending.frac - ending.tau
    frac = raw + np.round(cell.frac - raw)
    parents = p1.parent_frac(structure, cell, frac)
    for site, position in zip(out.sites, parents, strict=True):
        site.frac = position
    out.touch()
    regenerated = p1.expand(out)
    if regenerated.n_atoms != cell.n_atoms:
        # A site moved far enough off a special position for its orbit
        # to split: the group would now make more atoms than DFTB+ had,
        # and adopting that is adding atoms nobody asked for.
        raise LeftTheGroup(regenerated.n_atoms, cell.n_atoms)
    delta = regenerated.frac - frac
    delta -= np.round(delta)
    deviation = float(np.linalg.norm(
        delta @ out.lattice.matrix, axis=1).max()) if len(delta) else 0.0
    return out, deviation


def _say_step(job):
    def say(step, energy, force):
        job.say(f"step {step}: E = {energy:.4f} kcal/mol, largest force "
                f"{force:.3g} kcal/mol/A")
    return say


# ======================================================================
#  MOLECULAR DYNAMICS
# ======================================================================

@common.guarded
def dynamics(job) -> JobResult:
    structure = job.structure
    options = common.options_of(job)
    common.refuse(structure, options)
    symbols = sorted(set(common.symbols_of(structure)))
    time_step = float(job.param("time_step", 1.0))
    driver = hsd.Dynamics(
        steps=int(job.param("steps", 100)), time_step=time_step,
        temperature=float(job.param("temperature", 300.0)),
        thermostat=str(job.param("thermostat", "nose-hoover")),
        coupling=float(job.param("coupling", 3200.0)),
        write_every=int(job.param("write_every", 10)),
        moved=moved_atoms(structure, job))
    counted = {"n": 0}

    def line(text):
        if text.startswith("MD Temperature:"):
            counted["n"] += 1
            if counted["n"] % 10 == 1:
                job.say(f"step {counted['n'] - 1}: "
                        f"{text.split()[-2]} K")

    with common.folder(job) as directory:
        common.invoke(job, directory, structure, hsd.hsd_string(
            symbols, options, k_points=common.mesh(structure, options),
            driver=driver), on_line=line)
        log = outputs.read_md(common.read(directory, "md.out"),
                              time_step)
        frames = outputs.read_xyz_frames(
            common.read(directory, "geo_end.xyz"))

    cell = p1.expand(structure)
    elements = tuple(cell.elements)
    trajectory = Trajectory([
        Frame(elements=elements, cart=positions,
              lattice=structure.lattice,
              info={"step": int(round(t / time_step)),
                    "energy": float(e)})
        for positions, t, e in zip(frames, log.steps, log.potential,
                                   strict=False)
        if len(positions) == len(elements)])
    rows = [Row("Frames", str(trajectory.n_frames)),
            Row.number("Simulated", float(log.steps[-1]), "fs"),
            Row.number("Mean temperature", float(log.temperature.mean()),
                       "K", decimals=1)]
    blocks = (Table("Molecular dynamics", tuple(rows)),
              Curve(title="Temperature", x=log.steps, y=log.temperature,
                    x_label="time (fs)", y_label="K", normalised=False),
              Curve(title="Total energy", x=log.steps, y=log.total,
                    x_label="time (fs)", y_label="kcal/mol",
                    normalised=False,
                    note="Kinetic plus potential.  With no thermostat "
                         "it is conserved, and its drift is the time "
                         "step's error."))
    return JobResult(
        message=f"{trajectory.n_frames} frames over "
                f"{log.steps[-1]:g} fs -- in the transport bar",
        trajectory=trajectory,
        report=Report(title="DFTB+ molecular dynamics", blocks=blocks))
