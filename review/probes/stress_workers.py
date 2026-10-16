"""Start and finish N short jobs, with the original ``start_in_thread``
and then with the one in ``workers_fixed.py``, and say which hangs.

Two modes, because the plain one does not reproduce what the suite
sees.

``--mode plain``
    200 jobs, one after another, nothing else going on.  This is the
    honest control: it exercises the teardown but never puts a second
    thread on the other side of the lock inversion.

``--mode hostile``
    The shape a full pytest run has.  While each job is being torn
    down, the GUI thread is doing what ``MainWindow.__init__`` does --
    building QObjects and connecting signals, thousands of them -- and
    a Python ``eventFilter`` is installed on the window, as
    ``xtalapp/layout.py:75`` installs one, so that every event
    delivered on the GUI thread (a ``DeferredDelete`` included) has to
    take the GIL inside Qt's event delivery.  That is both halves of
    the inversion: a GUI thread holding the GIL and calling
    ``QObject::connect``, and a worker thread destroying Python
    wrappers from inside ``~QObject``.

A watchdog thread dumps every stack with ``faulthandler`` and leaves
with status 3 if a run stops making progress.

    .venv/bin/python review/probes/stress_workers.py --jobs 200
"""
from __future__ import annotations

import argparse
import faulthandler
import importlib.util
import os
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

from PySide6.QtCore import QEvent, QObject, QTimer, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

OPTS = {"overlap": 1, "tail": 0.0, "parented": True}


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class StressWorker(QObject):
    """The smallest thing with the shape ``start_in_thread`` expects."""

    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, spin: float = 0.0, tail: float = 0.0):
        super().__init__()
        self.spin = spin
        self.tail = tail
        self._running = False

    def cancel(self) -> None:
        pass

    def run(self) -> None:
        self._running = True
        try:
            if self.spin:
                time.sleep(self.spin)
            self.finished.emit("done")
            # The GUI thread's slot runs during this, and drops its
            # reference to this object.  The only reference left is
            # ``self`` in this frame -- so the wrapper is destroyed on
            # *this* thread, the moment ``run`` returns, which is the
            # half of the race the plain pass never creates.
            if self.tail:
                time.sleep(self.tail)
        finally:
            self._running = False


class NoisyFilter(QObject):
    """A Python event filter on the window, as ``layout.py`` installs.

    It is the reason the GUI thread needs the GIL *inside* Qt's event
    delivery, which is where the shipped application's hang was
    sampled (``QObjectWrapper::eventFilter`` during
    ``sendPostedEvents``).
    """

    def __init__(self):
        super().__init__()
        self.seen = 0

    def eventFilter(self, watched, event):
        self.seen += 1
        return False


class Churn(QObject):
    """What ``MainWindow.__init__`` does, on the GUI thread, repeatedly.

    Every dump of the real hang landed in ``MainWindow.__init__`` at a
    different line, which is a thread holding the GIL and asking Qt to
    connect something.
    """

    ping = Signal()

    def __init__(self, width: int = 400):
        super().__init__()
        self.width = width

    def build(self) -> None:
        kept = []
        for _ in range(self.width):
            child = Churn(0)
            child.ping.connect(self.noop)
            self.ping.connect(child.noop)
            child.ping.disconnect(self.noop)
            kept.append(child)

    def noop(self) -> None:
        pass


class Driver(QObject):
    """Drives the passes from the GUI thread.

    A slot has to be a bound method of a QObject that lives here: a
    plain function or a lambda has no thread affinity, so Qt calls it
    directly on the *emitting* thread, and the whole point is to model
    a panel whose finished-slot runs on the GUI thread.
    """

    def __init__(self, module, jobs, hostile, spin, progress, window,
                 overlap=1, tail=0.0, parented=True):
        super().__init__()
        self.module = module
        self.jobs = jobs
        self.hostile = hostile
        self.spin = spin
        self.tail = tail
        self.overlap = overlap
        self.parented = parented
        self.progress = progress
        self.window = window
        self.churn = Churn()
        self.n = 0
        self.live = 0
        self.worker = None
        self.thread = None

    def next_job(self) -> None:
        while self.live < self.overlap:
            if self.n >= self.jobs:
                if self.live == 0:
                    QApplication.instance().quit()
                return
            self.n += 1
            self.live += 1
            self.progress(self.n)
            worker = StressWorker(self.spin, self.tail)
            worker.finished.connect(self.on_done)
            self.worker = worker
            self.thread = self.module.start_in_thread(
                worker, self.window if self.parented else None)

    def on_done(self, _result) -> None:
        self.live -= 1
        # What both panels do in their finished slot: let go of the
        # worker (ff_panel.py:797, module_runner.py:361) and keep
        # nothing but the stale thread handle.
        self.worker = None
        self.thread = None
        if self.hostile:
            # A pytest teardown (conftest.py:216) happening while the
            # next test builds its window: DeferredDelete delivered
            # into a Python event filter, and thousands of connects on
            # the side that holds the GIL.
            QApplication.sendPostedEvents(
                None, QEvent.Type.DeferredDelete)
            self.churn.build()
        QTimer.singleShot(0, self.next_job)


def one_pass(module, jobs: int, hostile: bool, spin: float,
             progress) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = QWidget()
    filt = NoisyFilter()
    if hostile:
        window.installEventFilter(filt)
        app.installEventFilter(filt)
    driver = Driver(module, jobs, hostile, spin, progress, window,
                    overlap=OPTS["overlap"], tail=OPTS["tail"],
                    parented=OPTS["parented"])
    QTimer.singleShot(0, driver.next_job)
    app.exec()
    window.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    return driver.n


class Watchdog:
    """Dump every stack and leave if a pass stops making progress.

    **This cannot see a pure GIL deadlock**, because it is a Python
    thread and therefore needs the GIL to run at all.  One run wedged
    with this watchdog itself blocked in ``take_gil``; it was found
    minutes later with ``sample``, and that sample is
    ``review/probes/hung_sample.txt``.  So every "no hang" here is a
    lower bound.  pytest's own ``-o faulthandler_timeout=`` does not
    have this problem: faulthandler's watchdog is a C thread that
    dumps without taking the GIL.
    """

    def __init__(self, seconds: float, label: str):
        self.seconds = seconds
        self.label = label
        self.beat = time.time()
        self.last = 0
        self.done = threading.Event()
        self.thread = threading.Thread(target=self._watch, daemon=True)

    def touch(self, n=None) -> None:
        self.beat = time.time()
        if n is not None:
            self.last = n

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.done.set()

    def _watch(self) -> None:
        while not self.done.wait(0.25):
            if time.time() - self.beat > self.seconds:
                sys.stderr.write(
                    f"\n=== HUNG in {self.label}: no progress for "
                    f"{self.seconds:g}s, stuck at job "
                    f"{self.last} ===\n")
                sys.stderr.flush()
                faulthandler.dump_traceback(all_threads=True)
                sys.stderr.flush()
                os._exit(3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=200)
    ap.add_argument("--mode", choices=("plain", "hostile", "both"),
                    default="both")
    ap.add_argument("--which", choices=("original", "fixed", "both"),
                    default="both")
    ap.add_argument("--spin", type=float, default=0.0,
                    help="seconds of work per job")
    ap.add_argument("--overlap", type=int, default=1,
                    help="jobs in flight at once")
    ap.add_argument("--tail", type=float, default=0.0,
                    help="seconds of work after finished is emitted")
    ap.add_argument("--no-parent", action="store_true",
                    help="parent=None, as the Force Field panel does")
    ap.add_argument("--timeout", type=float, default=20.0,
                    help="seconds without progress before it is a hang")
    args = ap.parse_args()

    which = ({"original": ROOT / "xtalapp" / "workers.py"}
             if args.which == "original" else
             {"fixed": HERE / "workers_fixed.py"}
             if args.which == "fixed" else
             {"original": ROOT / "xtalapp" / "workers.py",
              "fixed": HERE / "workers_fixed.py"})
    modes = (("plain", "hostile") if args.mode == "both"
             else (args.mode,))

    OPTS["overlap"] = args.overlap
    OPTS["tail"] = args.tail
    OPTS["parented"] = not args.no_parent
    faulthandler.enable()
    for mode in modes:
        for name, path in which.items():
            label = f"{name}/{mode}"
            module = load(path, f"stress_{name}_{mode}")
            dog = Watchdog(args.timeout, label).start()
            started = time.time()
            done = one_pass(module, args.jobs, mode == "hostile",
                            args.spin, dog.touch)
            dog.touch()
            print(f"{label:<18s} {done}/{args.jobs} jobs in "
                  f"{time.time() - started:6.2f}s", flush=True)
            dog.stop()
    # Leaving the hard way on purpose: PySide's interpreter shutdown
    # is itself a place this arrangement can wedge, and a harness that
    # hangs there says nothing about the 200 jobs that just passed.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
