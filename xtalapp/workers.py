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
                 frozen=(), parent=None, **options):
        super().__init__(parent)
        self.calculator = calculator
        self.structure = structure
        self.method = method
        self.frozen = tuple(frozen)
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
            for step in optimize.steps(
                    self.calculator, self.structure, self.method,
                    self.frozen, **self.options):
                if first is None:
                    first = step
                last = step
                history.append((step.iteration, step.energy,
                                step.max_force))
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
                message=("stopped at step "
                         f"{last.iteration}" if self._cancel.is_set()
                         else last.line()),
            ))
        except Exception as exc:                    # noqa: BLE001
            self.failed.emit(str(exc))
        finally:
            self._running = False


def start_in_thread(worker: QObject) -> QThread:
    """Move ``worker`` onto a fresh thread and start it.

    The thread quits when the worker signals either outcome, and both
    are deleted when it has actually stopped -- deleting a worker while
    its thread is still inside ``run`` is the classic way to crash a Qt
    application on exit.
    """
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread
