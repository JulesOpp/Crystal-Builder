"""
xtalapp.workers
===============
Long calculations, off the GUI thread.

A geometry optimisation is the first thing this application does that
takes longer than a frame.  Run it in the window's thread and the
window stops answering: no redraw, no cancel, and a spinning cursor
that cannot be told apart from a crash.  So it runs in a
:class:`QThread`, reports each step back through a signal, and can be
paused or cancelled between them.

**The worker owns a copy of the structure, not the document's.**  The
optimiser reads the structure on every step and memoises derived data
on it; the window is meanwhile free to redraw, and the user is free to
select and to look around.  Sharing one structure between the two
threads would be a data race in the most literal sense, and the copy
costs a few hundred kilobytes once.  What comes back over the signal is
a plain numpy array of coordinates, which is safe to hand across.

Cancelling therefore never leaves a half-finished structure behind:
the document is not touched at all until the run ends and the panel
pushes a single command.

:class:`ModuleWorker` is the same arrangement for anything the module
registry offers.  It is separate from :class:`OptimizationWorker`
rather than a generalisation of it because the two cancel differently
and report differently, and folding them together would mean a worker
carrying a pause button that most jobs cannot honour and a step signal
that most jobs never emit.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QThread, Signal

from xtal.ff import optimize


class OptimizationWorker(QObject):
    """Runs :func:`xtal.ff.optimize.steps` and reports as it goes."""

    stepped = Signal(object)        # xtal.ff.optimize.Step
    finished = Signal(object)       # OptimizationResult
    failed = Signal(str)

    def __init__(self, calculator, structure, method: str = "lbfgs",
                 frozen=(), parent=None, recorder=None, **options):
        # ``options`` carries whatever ``optimize.steps`` takes, which
        # now includes ``relax_cell`` and ``pressure``: the worker has
        # no opinion about any of them and passing them through by name
        # would be one more place to forget one.
        super().__init__(parent)
        self.calculator = calculator
        self.structure = structure
        self.method = method
        self.frozen = tuple(frozen)
        # Where the run writes itself down, or None when there is no
        # workspace to write into.  The frames go out on this thread,
        # as they arrive, which is the whole reason they can be kept:
        # 5184 sites is 124 kB a frame and 200 steps is 25 MB, which
        # is fine on disk and not fine in a signal queue.
        self.recorder = recorder
        self.recording_failed = ""
        self.options = options
        self._cancel = threading.Event()
        self._resume = threading.Event()
        self._resume.set()
        self._running = False

    # -- control, called from the GUI thread ---------------------------

    def cancel(self) -> None:
        self._cancel.set()
        self._resume.set()           # a paused run must be able to stop

    def pause(self) -> None:
        self._resume.clear()

    def resume(self) -> None:
        self._resume.set()

    @property
    def is_paused(self) -> bool:
        return not self._resume.is_set()

    @property
    def is_running(self) -> bool:
        return self._running

    # -- the work ------------------------------------------------------

    def run(self) -> None:
        """The thread's entry point.

        Every exception is turned into a ``failed`` signal.  A worker
        that raises into a QThread takes the exception with it and the
        panel waits for a result that will never come, which looks
        exactly like a hang.
        """
        self._running = True
        history = []
        first = last = None
        try:
            self._record(lambda r: r.begin_steps())
            for step in optimize.steps(
                    self.calculator, self.structure, self.method,
                    self.frozen, **self.options):
                if first is None:
                    first = step
                last = step
                history.append((step.iteration, step.energy,
                                step.max_force))
                self._record(lambda r, s=step: r.step(s))
                self.stepped.emit(step)
                self._resume.wait()
                if self._cancel.is_set():
                    break
            if last is None:                        # pragma: no cover
                raise RuntimeError(
                    "the optimiser produced no steps")
            self.finished.emit(optimize.OptimizationResult(
                converged=last.converged and not self._cancel.is_set(),
                steps=last.iteration,
                initial_energy=first.energy,
                energy=last.energy,
                max_force=last.max_force,
                frac=last.frac,
                terms=dict(last.terms),
                history=history,
                matrix=last.matrix,
                initial_matrix=(None if last.matrix is None else
                                self.structure.lattice.matrix),
                message=("stopped at step "
                         f"{last.iteration}" if self._cancel.is_set()
                         else last.line()),
            ))
        except Exception as exc:                    # noqa: BLE001
            self.failed.emit(str(exc))
        finally:
            self._running = False

    def _record(self, action) -> None:
        """Write something down, and never lose a run over it.

        A full disk, a workspace on a volume that went away, a folder
        somebody deleted mid-run: none of those are a reason to throw
        away the optimisation that is still perfectly happy in memory.
        The failure is remembered and reported once, and the run
        carries on without a recorder.
        """
        if self.recorder is None:
            return
        try:
            action(self.recorder)
        except Exception as exc:                    # noqa: BLE001
            self.recording_failed = str(exc)
            self.recorder = None


def start_in_thread(worker: QObject, parent: QObject = None) -> QThread:
    """Move ``worker`` onto a fresh thread and start it.

    The thread quits when the worker signals either outcome, and both
    are deleted when it has actually stopped -- deleting a worker while
    its thread is still inside ``run`` is the classic way to crash a Qt
    application on exit.

    Give it a ``parent`` and C++ owns the thread, which is the other
    half of the same rule.  ``finished`` is emitted from *inside* the
    thread, so a caller that drops its last Python reference in that
    slot destroys a ``QThread`` that has not stopped yet -- and Qt
    aborts the process rather than raising something catchable.  With
    a parent, the reference count is nobody's problem.
    """
    thread = QThread(parent)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread


class ModuleWorker(QObject):
    """Runs one module action's ``run`` callable and reports as it goes.

    The same shape as :class:`OptimizationWorker` and for the same
    reasons -- a run that takes longer than a frame cannot happen on
    the window's thread -- with one difference that matters.

    **Cancelling is a message, not a flag the thread checks on its
    way out.**  An in-process job polls the cancellation between units
    of work; an external process is killed by it, through a callback
    registered by :class:`~xtal.modules.process.ExternalProcess`.  Both
    go through the same :class:`~xtal.modules.job.Cancellation`, so
    :meth:`cancel` does not have to know which kind of job it is
    stopping -- and a job that has already finished is unaffected by
    being cancelled, which is what makes the race between Stop and the
    last line of output harmless.

    Progress lines arrive on this thread and leave as a signal, which
    is the only safe way for them to reach a label.
    """

    progressed = Signal(str)
    finished = Signal(object)       # xtal.modules.job.JobResult
    failed = Signal(str)

    def __init__(self, module, action, job, parent=None):
        super().__init__(parent)
        self.module = module
        self.action = action
        self.job = job
        self.job.on_progress = self.progressed.emit
        self._running = False

    @property
    def label(self) -> str:
        return f"{self.module.label}: {self.action.label.rstrip('.')}"

    @property
    def is_running(self) -> bool:
        return self._running

    def cancel(self) -> None:
        """Called from the GUI thread, at any point in the run."""
        self.job.cancel.cancel()

    def run(self) -> None:
        """The thread's entry point.

        Every exception becomes a ``failed`` signal, for the same
        reason as in :class:`OptimizationWorker`: an exception that
        escapes into a QThread goes with it, and the panel waits for a
        result that never comes, which looks exactly like a hang.

        ``Cancelled`` is not one of them.  Stopping a run is something
        the user did on purpose and must never be reported as a
        failure.
        """
        from xtal.modules.job import Cancelled, JobResult

        self._running = True
        try:
            result = self.action.run(self.job)
            if result is None:
                result = JobResult(message=f"{self.label} finished")
            if self.job.cancelled and not result.cancelled:
                # It stopped early and said nothing about why.
                result.cancelled = True
            self.finished.emit(result)
        except Cancelled:
            self.finished.emit(JobResult.stopped())
        except Exception as exc:                    # noqa: BLE001
            self.failed.emit(str(exc))
        finally:
            self._running = False
