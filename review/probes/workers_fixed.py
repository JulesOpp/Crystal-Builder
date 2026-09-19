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

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from xtal.ff import optimize
from xtal.ff.api import CalculatorStopped


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
        # The same Stop, for the engine: DFTB+ and xTB kill their
        # program with it rather than finishing an SCC cycle nobody is
        # waiting for.
        from xtal.modules.job import Cancellation
        self._stop = Cancellation()
        self._resume = threading.Event()
        self._resume.set()
        self._running = False

    # -- control, called from the GUI thread ---------------------------

    def cancel(self) -> None:
        self._cancel.set()
        self._resume.set()           # a paused run must be able to stop
        self._stop.cancel()

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
            try:
                for step in optimize.steps(
                        self.calculator, self.structure, self.method,
                        self.frozen, cancel=self._stop, **self.options):
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
            except CalculatorStopped:
                # Killed in the middle of an evaluation.  The last step
                # that finished is the result, exactly as if Stop had
                # landed between two -- and a run stopped before its
                # first step has nothing to keep, which is a failure.
                if last is None:
                    raise
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
                stress=last.stress,
                message=("stopped at step "
                         f"{last.iteration}" if self._cancel.is_set()
                         else last.reason or last.line()),
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


#: Every run that has been started and not yet released.  The GUI
#: thread is the only thread that touches this, and it is a
#: module-level set rather than an attribute of the caller so that a
#: panel is free to drop its own ``self.worker`` the moment the result
#: arrives -- which is what ``test_modules_ui`` waits on.
_LIVE: set = set()


class _Run(QObject):
    """Owns one worker and its thread, from the GUI thread.

    The arrangement this replaces let Qt delete both: ``finished`` was
    wired to ``deleteLater`` on each.  That put the destruction of two
    Python wrappers at two places nobody chose -- the worker's on the
    dying thread inside ``QThreadPrivate::finish``, the thread's inside
    ``sendPostedEvents`` -- and a Python wrapper cannot be destroyed
    without the GIL, while ``~QObject`` severing its connections holds
    Qt's connection lock and calls back into Python for
    ``disconnectNotify``.  A GUI thread holding the GIL and connecting
    anything then waits on that lock for as long as the other thread
    waits for the GIL.

    So nothing here is deleted by Qt.  Both objects are owned by
    Python, from this object, on the GUI thread, and both are dropped
    from a plain event-loop turn with no thread dying and no signal
    being delivered.
    """

    def __init__(self, worker, thread):
        # Deliberately unparented.  Parenting it to the window would
        # hand its lifetime back to C++ -- and then closing the window
        # would destroy it while ``_LIVE`` still held the wrapper,
        # which is the zombie this whole change exists to stop making.
        super().__init__()
        self.worker = worker
        self.thread = thread

    def stop_and_wait(self, timeout: int = 30000) -> bool:
        """Quit the thread and block until it has actually stopped.

        For a window on its way out: a thread whose ``QThread`` is
        destroyed while it is still running aborts the process, and
        closing the window destroys the whole object tree.
        """
        thread = self.thread
        if thread is None:
            return True
        cancel = getattr(self.worker, "cancel", None)
        if cancel is not None:
            cancel()
        thread.quit()
        stopped = thread.wait(timeout)
        if stopped:
            self._release()
        return stopped

    def _finished(self, *_ignored) -> None:
        """The worker is done.  Runs on the GUI thread.

        ``worker.finished`` is emitted from inside ``run``, and the
        worker lives on the other thread, so this is a queued call and
        the worker is by now back in ``QThread::exec``.  ``quit`` makes
        that return; ``wait`` is then the length of one event-loop
        return, not of the run.
        """
        thread = self.thread
        if thread is None:
            return
        thread.quit()
        thread.wait()
        # Not here: the stack above this is still Qt delivering a
        # signal.  One clean turn later there is nothing underneath.
        QTimer.singleShot(0, self._release)

    def _release(self) -> None:
        self.worker = None
        self.thread = None
        _LIVE.discard(self)


def start_in_thread(worker: QObject, parent: QObject = None) -> QThread:
    """Move ``worker`` onto a fresh thread and start it.

    Both objects stay alive, owned from Python on the GUI thread,
    until the thread has stopped -- see :class:`_Run`.  ``parent`` is
    still honoured for the thread, so a window that outlives the run
    still owns it in C++ as well.
    """
    thread = QThread(parent)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    run = _Run(worker, thread)
    _LIVE.add(run)
    worker.finished.connect(run._finished)
    worker.failed.connect(run._finished)
    thread.start()
    return thread


def stop_all(timeout: int = 30000) -> bool:
    """Stop every run there is and wait for it.  For ``closeEvent``.

    Every one of them, not up to the first that will not stop: a list
    rather than a generator, because ``all`` short-circuits and a
    thread left running is the abort this is here to prevent.
    """
    return all([run.stop_and_wait(timeout) for run in list(_LIVE)])


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
