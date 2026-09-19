"""Who owns what, in the exact arrangement start_in_thread builds."""
import functools, gc, sys, threading, time, weakref
print = functools.partial(print, flush=True)
from PySide6.QtCore import QObject, QThread, Signal, QCoreApplication, QEvent

app = QCoreApplication(sys.argv)

class W(QObject):
    finished = Signal(object)
    failed = Signal(str)
    def run(self):
        print("   run() on", threading.current_thread().name)
        self.finished.emit(1)
        print("   run() returned")

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

w = W(); t = start_in_thread(w)
wr_w, wr_t = weakref.ref(w), weakref.ref(t)
print("A refs held on thread wrapper:", sys.getrefcount(t) - 1)
print("A refs held on worker wrapper:", sys.getrefcount(w) - 1)
t0 = time.time()
ok = t.wait(3000)
print(f"B QThread.wait -> {ok} after {time.time()-t0:.2f}s  "
      f"isFinished={t.isFinished()} isRunning={t.isRunning()}")
# Does QThread.wait() release the GIL?  Ask a plain Python thread.
ticks = []
stop = threading.Event()
def ticker():
    while not stop.is_set():
        ticks.append(1); time.sleep(0.01)
th = threading.Thread(target=ticker, daemon=True); th.start()
w2 = W(); t2 = start_in_thread(w2)
n0 = len(ticks); t2.wait(1000); n1 = len(ticks); stop.set()
print(f"C python ticks during a 1s QThread.wait: {n1-n0} "
      f"(0 would mean wait() holds the GIL)")
print("D t2 finished:", t2.isFinished())
