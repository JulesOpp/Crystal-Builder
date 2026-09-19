"""Which thread drops the last reference, and to what.

Models the real arrangement: a panel on the main thread holds
``self.worker``, connects ``worker.finished`` to a slot of its own
(queued, main thread) and clears ``self.worker`` inside that slot --
which is what xtalapp/docks/ff_panel.py:797 and 861 do.
"""
import functools, sys, threading, weakref
print = functools.partial(print, flush=True)
from PySide6.QtCore import (QObject, QThread, Signal, QTimer,
                            QCoreApplication)

app = QCoreApplication(sys.argv)
events = []

class Worker(QObject):
    finished = Signal(object)
    failed = Signal(str)
    def run(self):
        events.append(("run enters", threading.current_thread().name))
        self.finished.emit("result")
        events.append(("emit returned", threading.current_thread().name))
        # OptimizationWorker's ``finally: self._running = False``
        self._running = False
        events.append(("run returns", threading.current_thread().name))

def start_in_thread(worker, parent=None):
    thread = QThread(parent)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread

class Panel(QObject):
    def __init__(self):
        super().__init__()
        self.worker = None
        self._thread = None
    def start(self):
        self.worker = Worker()
        self.worker.finished.connect(self._on_finished)
        self._thread = start_in_thread(self.worker)   # no parent
    def _on_finished(self, result):
        events.append(("_on_finished", threading.current_thread().name))
        self.worker = None           # ff_panel.py:797
        events.append(("worker attr cleared",
                       threading.current_thread().name))

panel = Panel()
panel.start()
weakref.finalize(panel.worker, lambda: events.append(
    ("WORKER WRAPPER FREED", threading.current_thread().name)))
weakref.finalize(panel._thread, lambda: events.append(
    ("THREAD WRAPPER FREED", threading.current_thread().name)))
QTimer.singleShot(2500, app.quit)
app.exec()
for what, where in events:
    print(f"  {where:<12s}  {what}")
print("thread still running:", panel._thread.isRunning(),
      " finished:", panel._thread.isFinished())
panel._thread.wait(2000)
