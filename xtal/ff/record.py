"""
xtal.ff.record
==============
What a force-field run writes down while it runs.

Before this, nothing was written down.  The report box in the panel was
cleared by the next run, and the reasons behind every typing decision
-- which the typer computes and the panel shows -- went with it.  A
number nobody can explain three months later is not a result.

So a run writes a log as it goes, and this is what has to be in it for
it to be worth keeping:

* the version, the engine, and **every option it was given**;
* the full typing table, with the confidence and the *reason* for each
  assignment, because a wrong type gives a plausible number rather than
  an obvious error;
* the topology counts, and every warning **in place** rather than only
  in a status bar message that lasted four seconds;
* the per-step line, which :meth:`~xtal.ff.optimize.Step.line` already
  formats;
* the per-term energy breakdown at the start *and* at the end, because
  which term the energy went into is the question a total cannot
  answer.

The recorder is used identically by the window's worker thread and by
the CLI, which is what makes a run started from a script open in the
window: the layout is not the GUI's, it is the module's.
"""

from __future__ import annotations

import numpy as np

from xtal.core import p1
from xtal.core.structure import Change
from xtal.workspace import RunFolder, timestamp, write_header


class RunRecorder:
    """Writes ``run.log``, ``trajectory.extxyz`` and ``final.cif``.

    One recorder per run.  Every method is safe to call on a run that
    fails or is cancelled halfway: the point of writing as we go is
    that what did happen is on disk even when the run did not finish.
    """

    def __init__(self, folder: RunFolder, structure, calculator=None,
                 engine: str = "", options: dict | None = None,
                 record_trajectory: bool = True):
        self.folder = folder
        self.structure = structure
        self.calculator = calculator
        self.engine = engine
        self.options = dict(options or {})
        self.record_trajectory = record_trajectory
        self.n_frames = 0
        self._scratch = None
        self._closed = False

    # -- the log -------------------------------------------------------

    @property
    def log(self):
        return self.folder.log()

    def header(self, title: str = "") -> None:
        """The version, the structure, the engine and the options.

        The block itself is :func:`xtal.workspace.write_header`, which
        the module registry writes too: what somebody asks of a log
        three months later does not depend on which engine wrote it,
        and a second copy of this is the one that would stop recording
        the option they needed.
        """
        fields = [("engine", f"{self.engine}  "
                             f"({_engine_label(self.engine)})")] \
            if self.engine else []
        write_header(self.log, self.folder, self.structure,
                     title=title, fields=fields, options=self.options)
        self.log.blank()

    def typing(self) -> None:
        """The table the whole result rests on."""
        from xtal.ff.uff import typer

        log = self.log
        try:
            typing = typer.assign(
                self.structure, parameter_set=self.options.get(
                    "parameter_set", typer.params.DEFAULT_PARAMETER_SET))
        except Exception as exc:                    # noqa: BLE001
            log.write(f"atom types: could not be assigned ({exc})")
            log.blank()
            return
        cell = p1.expand(self.structure)
        rows = []
        for index in range(self.structure.n_sites):
            images = cell.indices_of_site(index)
            if not len(images):
                continue
            site = self.structure.sites[index]
            atom = typing.types[int(images[0])]
            rows.append([site.label or f"{site.element}{index}",
                         atom.name, _description(atom.name),
                         f"x{len(images)}",
                         "set" if atom.overridden else atom.confidence,
                         atom.reason])
        log.heading("Atom types")
        log.table(rows, headers=("site", "type", "means", "orbit",
                                 "sure?", "why"))
        log.blank()

    def topology(self) -> None:
        if self.calculator is None:
            return
        log = self.log
        log.heading("Topology")
        log.write(self.calculator.summary())
        for warning in getattr(self.calculator, "warnings", []):
            log.write(f"warning: {warning}")
        log.blank()

    def energies(self, result, title: str = "Energy") -> None:
        """A per-term breakdown, which a total cannot replace."""
        log = self.log
        log.heading(title)
        log.write(result.breakdown() if hasattr(result, "breakdown")
                  else _terms_text(result))
        log.blank()

    def warn(self, message: str) -> None:
        self.log.write(f"warning: {message}")

    # -- the steps -----------------------------------------------------

    def begin_steps(self) -> None:
        self.log.heading("Steps")

    def step(self, step) -> None:
        """One iteration: a line in the log, a frame on disk.

        The frame is written **as it arrives** rather than held: 5184
        sites is 124 kB a frame and 200 steps is 25 MB, which is fine
        on disk and not fine in a queue.
        """
        self.log.write(step.line())
        if not self.record_trajectory:
            return
        frame = self._frame(step)
        if frame is not None:
            self.folder.trajectory().append_frame(frame)
            self.n_frames += 1

    def _frame(self, step) -> object | None:
        """The P1 cell at this step, as an extended-XYZ frame.

        The optimiser reports the asymmetric unit, which is what it
        varies; the trajectory holds the cell, which is what OVITO,
        VMD and ASE read.  A scratch copy of the structure carries the
        coordinates between the two, so nothing the caller owns is
        touched.
        """
        from xtal.io.trajectory import frame_of

        if self._scratch is None:
            self._scratch = self.structure.copy()
        if getattr(step, "matrix", None) is not None:
            # A variable-cell run: the frame is the cell as well as the
            # coordinates, and a trajectory whose cell never changed
            # would show the atoms of a relaxation rattling inside a
            # box that was not the one they were relaxed in.
            from xtal.core.lattice import Lattice
            self._scratch.lattice = Lattice(step.matrix)
        try:
            for site, frac in zip(self._scratch.sites, step.frac,
                                  strict=True):
                site.frac = np.asarray(frac, dtype=float)
        except ValueError:                          # pragma: no cover
            return None
        self._scratch.touch(Change.POSITIONS | Change.CELL)
        return frame_of(self._scratch, step=int(step.iteration),
                        energy=float(step.energy),
                        max_force=float(step.max_force))

    # -- the end -------------------------------------------------------

    def result(self, result, final=None) -> None:
        """The verdict, the final breakdown, and ``final.cif``."""
        log = self.log
        log.blank()
        log.heading("Result")
        log.write(result.summary() if hasattr(result, "summary")
                  else str(result))
        if getattr(result, "terms", None):
            log.blank()
            log.write(_terms_text(result.terms))
        if not getattr(result, "converged", True):
            log.write("note: the geometry is where the optimiser "
                      "stopped, not a minimum")
        log.blank()
        if final is not None:
            try:
                path = self.folder.write_final(final)
                log.write(f"wrote {path.name}")
            except Exception as exc:                # noqa: BLE001
                log.write(f"could not write the final structure: "
                          f"{exc}")
        if self.n_frames:
            log.write(f"wrote {self.folder.run.trajectory_path.name} "
                      f"({self.n_frames} frames)")
        log.write(f"finished       {timestamp()}")

    def failed(self, message: str) -> None:
        log = self.log
        log.blank()
        log.write(f"the run failed: {message}")
        log.write(f"finished       {timestamp()}")

    def close(self) -> None:
        if not self._closed:
            self.folder.close()
            self._closed = True

    def __enter__(self) -> RunRecorder:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


def _description(type_name: str) -> str:
    """A UFF type in words, for the column beside the name.

    The log is the thing somebody reads three months later, and a
    column of five-character codes is exactly what they will no longer
    remember how to decode.
    """
    from xtal.ff.uff import params

    try:
        return params.get(type_name).description
    except KeyError:                                # pragma: no cover
        return ""


def _terms_text(terms) -> str:
    """Per-term energies, largest first -- which is the order that
    answers "where did this number come from"."""
    if not terms:
        return "(no terms)"
    return "\n".join(
        f"{name:<16s}{value:14.4f}"
        for name, value in sorted(terms.items(),
                                  key=lambda kv: -abs(kv[1])))


def _engine_label(name: str) -> str:
    """The registry's own name for an engine, so the log says
    "Universal Force Field" rather than repeating "uff"."""
    from xtal.ff import ENGINES
    try:
        return ENGINES.get(name).label
    except (ValueError, KeyError):
        return "unregistered engine"
