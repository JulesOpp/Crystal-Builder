"""
xtal.modules.dftb_runs.modes
============================
Vibrational modes: DFTB+'s Hessian, diagonalised by ``modes``.

``Driver = SecondDerivatives`` displaces every free atom both ways
along each axis -- 6N evaluations, which on a framework is an
afternoon, and the dialog says so -- and writes ``hessian.out``;
``modes`` reads it with the geometry and writes the frequencies and
eigenvectors into ``vibrations.tag``.

**Relax first.**  A Hessian taken away from a minimum has imaginary
modes that are the gradient and not the curvature -- carbon dioxide
held at the wrong bond length bends at an imaginary 355 cm^-1 -- so an
imaginary mode is flagged in the table and counted in the message,
not hidden.

**The thermochemistry is the Force Field's.**  ``hessian.out`` goes
through :func:`xtal.ff.vibrations.from_hessian` -- symmetrised, the
rigid motions projected out, which ``modes`` does not do, so a
molecule's rotation at +20 cm^-1 is not summed as a vibration -- and
then through the same table as ``forcefield.thermo``, so G from DFTB+
and G from MACE read alike.  E is a single point at the reference
first: the ``detailed.out`` a SecondDerivatives run leaves is its last
displaced geometry's, off by the gradient times the step.

What a mode is *for* is seeing it: :func:`mode_trajectory` turns one
into a loop of frames for the transport bar, the atoms moving along
it sinusoidally about the geometry the Hessian was taken at.
"""

from __future__ import annotations

import numpy as np

from xtal.core import molecule, p1
from xtal.ff import vibrations
from xtal.ff.dftb import hsd, outputs
from xtal.ff.dftb.calculator import BOHR, HARTREE, parse_energy
from xtal.io.trajectory import Frame, Trajectory
from xtal.modules.dftb_runs import common
from xtal.modules.dftb_runs.driver import moved_atoms
from xtal.modules.job import JobResult
from xtal.modules.process import ExternalProcess, Program
from xtal.modules.report import Modes, Report
from xtal.modules.thermo import tabulate

MODES = Program(
    name="modes", label="modes", env_var="XTAL_MODES",
    url="https://dftbplus.org (it ships with DFTB+)",
    setting="tools/modes")

MODES_INPUT = "modes_in.hsd"

#: Frames in one period of an animated mode.
FRAMES = 24


def modes_input(moved) -> str:
    """``modes_in.hsd``: the geometry, the Hessian, and every mode
    written out -- ``vibrations.tag`` holds eigenvectors only when
    ``DisplayModes`` asks for them.  Checked against DFTB+ 24.1."""
    return "\n".join([
        "Geometry = GenFormat {",
        f'  <<< "{common.GEOMETRY_NAME}"',
        "}",
        "Hessian = {",
        '  <<< "hessian.out"',
        "}",
        f"Atoms = {hsd.moved_atoms(moved)}",
        "DisplayModes = {",
        "  PlotModes = 1:-1",
        "  Animate = No",
        "}",
        ""])


@common.guarded
def vibrational_modes(job) -> JobResult:
    structure = job.structure
    options = common.options_of(job)
    common.refuse(structure, options)
    available = MODES.availability()
    if not available:
        return JobResult.failure(available.reason)
    symbols = sorted(set(common.symbols_of(structure)))
    moved = moved_atoms(structure, job)
    cell = p1.expand(structure)
    free = list(range(cell.n_atoms)) if moved is None \
        else [atom - 1 for atom in moved]

    k_points = common.mesh(structure, options)
    with common.folder(job) as directory:
        job.say("the energy at the reference geometry")
        common.invoke(job, directory, structure, hsd.hsd_string(
            symbols, options, k_points=k_points,
            analysis=hsd.Analysis(forces=False)))
        energy = parse_energy(common.read(directory, "detailed.out"))
        if energy is None:
            return JobResult.failure(
                "DFTB+ wrote no total energy into detailed.out")
        job.say(f"second derivatives: {6 * len(free)} evaluations")
        common.invoke(job, directory, structure, hsd.hsd_string(
            symbols, options, k_points=k_points,
            driver=hsd.SecondDerivatives(
                delta=float(job.param("delta", 1e-4)), moved=moved),
            analysis=hsd.Analysis(forces=False)))
        hessian = read_hessian(common.read(directory, "hessian.out"),
                               len(free))
        (directory / MODES_INPUT).write_text(modes_input(moved),
                                             encoding="utf-8")
        process = ExternalProcess([MODES.name], cwd=directory,
                                  log=job.log)
        result = process.run(cancel=job.cancel, program=MODES)
        if result.cancelled:
            return JobResult.stopped("modes was stopped")
        if not result.ok:
            return JobResult.failure(
                f"modes exited with status {result.returncode}",
                detail=result.detail())
        found = outputs.read_modes(common.read(directory,
                                               "vibrations.tag"))
        # The Hessian is over the free atoms only; a frozen atom does
        # not move in any mode.
        displacements = np.zeros((len(found.frequencies),
                                  cell.n_atoms, 3))
        displacements[:, free, :] = found.displacements
        block = Modes(title="Vibrational modes",
                      frequencies=found.frequencies,
                      displacements=displacements,
                      elements=tuple(cell.elements),
                      cart=np.asarray(cell.cart, float),
                      lattice=np.asarray(structure.lattice.matrix,
                                         float),
                      note="Choose a mode and press Animate to watch "
                           "it in the transport bar.  Negative "
                           "frequencies are imaginary.")
        (directory / "modes.dat").write_text(block.as_dat(),
                                             encoding="utf-8")
        kind = "molecule" if molecule.is_isolated(structure) \
            else "crystal"
        found = vibrations.from_hessian(
            structure, hessian, kind=kind, free=free,
            energy=energy * HARTREE, evaluations=6 * len(free) + 1,
            method="dftb")
        chosen, tables, dat = tabulate(
            job, structure, found, kind,
            [i for i in range(cell.n_atoms) if i not in set(free)])
        (directory / "thermo.dat").write_text(dat, encoding="utf-8")

    highest = float(block.frequencies.max()) if block.n_modes else 0.0
    t = chosen.temperature
    imaginary = chosen.vibrations.n_imaginary
    message = (f"{block.n_modes} modes up to {highest:.0f} cm-1, "
               f"G({t:g} K) = {chosen.per_unit(chosen.g):.3f} kcal/mol "
               + ("per formula unit" if kind == "crystal"
                  else "per molecule")
               + (f", {imaginary} imaginary -- relax first"
                  if imaginary else ""))
    warnings = ()
    if imaginary:
        warnings = (("IMAGINARY_MODES",
                     f"{imaginary} imaginary modes:"
                     f" the structure is not at a minimum, and they are"
                     f" left out of every sum"),)
    return JobResult(message=message, report=Report(
        title="DFTB+ vibrational modes",
        blocks=(*tables, block)),
        answer=chosen, warnings=warnings)


def read_hessian(text: str, n_free: int) -> np.ndarray:
    """``hessian.out`` in kcal/mol/A^2: the 3N square over the moved
    atoms, Hartree/Bohr^2, written row after row whatever the line
    breaks."""
    values = np.array(text.split(), dtype=float)
    size = 3 * n_free
    if values.size != size * size:
        raise common.RunFailed(JobResult.failure(
            f"hessian.out holds {values.size} numbers; {n_free} moved "
            f"atoms need {size * size}"))
    return values.reshape(size, size) * (HARTREE / BOHR**2)


def mode_trajectory(block: Modes, mode: int, amplitude: float = 0.3,
                    frames: int = FRAMES) -> Trajectory:
    """One period of ``mode`` as frames: every atom at ``cart +
    amplitude * sin(phase) * displacement``, the largest moving
    ``amplitude`` Angstrom."""
    from xtal.core.lattice import Lattice
    lattice = Lattice(block.lattice) if block.lattice is not None \
        else None
    vector = np.asarray(block.displacements[mode], float)
    out = []
    for step in range(frames):
        phase = 2 * np.pi * step / frames
        out.append(Frame(
            elements=tuple(block.elements),
            cart=block.cart + amplitude * np.sin(phase) * vector,
            lattice=lattice,
            info={"step": step,
                  "frequency": float(block.frequencies[mode])}))
    return Trajectory(out)
