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

What a mode is *for* is seeing it: :func:`mode_trajectory` turns one
into a loop of frames for the transport bar, the atoms moving along
it sinusoidally about the geometry the Hessian was taken at.
"""

from __future__ import annotations

import numpy as np

from xtal.core import p1
from xtal.ff.dftb import hsd, outputs
from xtal.io.trajectory import Frame, Trajectory
from xtal.modules.dftb_runs import common
from xtal.modules.dftb_runs.driver import moved_atoms
from xtal.modules.job import JobResult
from xtal.modules.process import ExternalProcess, Program
from xtal.modules.report import Modes, Report, Row, Table

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

    with common.folder(job) as directory:
        job.say(f"second derivatives: {6 * len(free)} evaluations")
        common.invoke(job, directory, structure, hsd.hsd_string(
            symbols, options, k_points=common.mesh(structure, options),
            driver=hsd.SecondDerivatives(
                delta=float(job.param("delta", 1e-4)), moved=moved),
            analysis=hsd.Analysis(forces=False)))
        common.read(directory, "hessian.out")
        (directory / MODES_INPUT).write_text(modes_input(moved))
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
        (directory / "modes.dat").write_text(block.as_dat())

    rows = [Row("Modes", str(block.n_modes)),
            Row("Imaginary", str(block.n_imaginary),
                note="" if not block.n_imaginary else
                "An imaginary mode is a direction the energy falls "
                "along: the structure was not at a minimum.  Relax it "
                "first."),
            Row("Free atoms", str(len(free)))]
    highest = float(block.frequencies.max()) if block.n_modes else 0.0
    message = (f"{block.n_modes} modes up to {highest:.0f} cm-1"
               + (f", {block.n_imaginary} imaginary -- relax first"
                  if block.n_imaginary else ""))
    return JobResult(message=message, report=Report(
        title="DFTB+ vibrational modes",
        blocks=(Table("Summary", tuple(rows)), block)))


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
