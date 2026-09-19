# Reliability of long-running work

*Worker-thread teardown, cancellation, and process lifecycle.*
Reviewed against `main` @ v0.2.1, PySide6 **6.9.3** / Qt 6.9.3,
`.venv/bin/python` 3.12 arm64. No tracked file was modified
(`git status --porcelain` is empty). Probes are in `review/probes/`.

---

## Summary

1. **I reproduced the deadlock and sampled it.** The two stacks are in
   §5 and `review/probes/hung_sample.txt`. `CLAUDE.md`'s diagnosis is
   substantially right — it is a GIL/connection-mutex inversion around a
   wrapper freed inside signal delivery — and **wrong in two details
   that decide what the fix has to be**: the wrapper freed is the
   **worker's**, not the `QThread`'s, and it is freed on
   `thread.started → worker.run`, not on `worker.finished → thread.quit`.
2. Consequently, "hold the pair alive" is the *right* instinct, but the
   thing that must be held is the **worker**, from before `thread.start()`
   until after the thread has stopped, and **not in
   `module_runner.module_worker` / `FFPanel.worker`** — which is why the
   attempt broke `test_modules_ui`: those two attributes are what the
   suite's `waitUntil(... is None)` latches on (§3).
3. **It is worse than a hang.** Against a harness that models the
   suite's shape, the shipped module fails **31 runs in 45** — mostly
   segfaults and `QThread: Destroyed while thread is still running`,
   not hangs. The prototype is **50/50 clean** on the same five
   configurations. Numbers in §5.
4. `xtalapp/docks/ff_panel.py:726` starts its thread with **no parent**
   and never clears `self._thread`, which is the worst of the two call
   sites; and `MainWindow.closeEvent` stops the *module* worker but
   never the Force Field one. `[critical]`
5. Cancellation is cooperative and **two modules never poll it at all**;
   there is no `atexit`/`aboutToQuit` reaper anywhere, so an abrupt exit
   orphans every external child (`start_new_session=True` guarantees it).
   A cancelled scan, in contrast, is handled well and leaves a complete,
   reopenable `report.json`. `[strength]`

---

## 1. `[important]` Two corrections to the documented mechanism

**What.** `xtalapp/workers.py:186-192`, `CLAUDE.md` § Testing the GUI and
`docs/TODO.md:217` all rest on this sentence:

> a bound method owns the Python wrapper of the object it is bound to,
> so when nothing else owns it, PySide6 frees a `QThread` wrapper
> *inside* signal delivery

The shape is right and the live sample in §5 confirms it. Two things in
it are not, and both change what a fix has to do.

**Correction 1 — the connection holds no persistent reference.** A bound
method stored by `connect()` does *not* keep the receiver's wrapper
alive. `review/probes/ownership_probe.py` builds the exact arrangement
`start_in_thread` builds and counts references:

```
$ .venv/bin/python review/probes/ownership_probe.py
A refs held on thread wrapper: 1
A refs held on worker wrapper: 3        # transient, inside the emit
...
C python ticks during a 1s QThread.wait: 83   (0 would mean wait() holds the GIL)
```

One reference to the `QThread` wrapper after all five `connect()` calls —
and that one is the local variable. The connections hold nothing.

PySide6's own source says why. `libpyside/dynamicslot.cpp`:

> "Keeping a reference on the callable itself would prevent object
> deletion. Instead, keep a reference on the function."

`MethodDynamicSlot` holds a strong reference to the *function* and a
**weak** reference to `pythonSelf`. And in this helper no *stored*
Python slot object is created at all: `thread.quit`,
`worker.deleteLater` and `thread.deleteLater` are real Qt slots, so
`libpyside/qobjectconnect.cpp::qobjectConnectCallback()` takes its
`connectByIndex` branch and makes a pure C++ connection.

What *is* created is a **transient** bound method, built per call by
`SignalManagerPrivate::qtMethodMetacall` and released at the end of it.
The sample in §5 catches its `method_dealloc` frame: that release is the
refcount drop that destroys the worker, inside the emit. So the
mechanism is real but per-call, not per-connection — and the remedy is
therefore an *external* owner, not a belief that the connection is one.

**Correction 2 — it is the worker's wrapper, and it is on `started`.**
See §5. The `QThread`'s role is as the *sender* whose
`disconnectNotify` gets called; its own wrapper is not what is being
freed at that moment.

**Why both matter.** `review/probes/who_frees_it.py` shows what happens
if you hold the pair without also removing `deleteLater` — the Python
wrapper survives and its C++ object does not:

```
$ .venv/bin/python review/probes/who_frees_it.py
  Dummy-1       run enters
  Dummy-1       emit returned
  Dummy-1       run returns
  MainThread    _on_finished
  MainThread    WORKER WRAPPER FREED      <- inside the finished slot
  MainThread    worker attr cleared
RuntimeError: Internal C++ object (PySide6.QtCore.QThread) already deleted.
```

`ff_panel._thread` and `module_runner._module_thread` are both such
zombies after every run, for the life of the window.

**What a fix looks like.** Correct the three places that state the
mechanism: the connection owns nothing persistent, the wrapper freed is
the worker's, and the trigger is `thread.started → worker.run`. Then the
rule to write down is *the worker must have an owner outside the
connection for the whole life of the thread, and neither object may be
deleted by Qt.*

---

## 2. `[critical]` The actual root cause, stated precisely

`~QObject` severs its remaining connections while holding the per-object
connection lock, and shiboken dispatches the virtual `disconnectNotify`
from there via `Sbk_GetPyOverride`, which calls `gil.acquire()`. Qt
documents the hazard on `QObject::disconnectNotify` itself:

> "This function may also be called with a QObject internal mutex
> locked. It is therefore not allowed to re-enter any QObject
> functions… If you lock a mutex in your reimplementation… it will
> result in a deadlock."

Acquiring the GIL *is* locking a mutex. So **every destruction of a
connected `QObject` whose wrapper is Python-visible is a potential
lock-order inversion**, and `start_in_thread` schedules two of them per
run, on two threads, at moments chosen by Qt:

| destruction | which thread | inside what | seen? |
|---|---|---|---|
| **H0** the **worker**, when the transient bound method for `thread.started → worker.run` is released | the worker thread | delivery of `started` | **yes — §5, the sampled deadlock** |
| **H1** the **worker**, when the panel clears `self.worker` | main thread | delivery of `worker.finished` | yes — `who_frees_it.py` |
| **H2** the **thread** (`thread.finished → thread.deleteLater`) | main thread | `QCoreApplicationPrivate::sendPostedEvents` | matches the `68304b8` sample |

All three are the same bug and all three are removed by the same change:
give both objects an owner outside the connections, and let Qt delete
neither. **H0 is the one that actually fired in my harness**, and it is
the one a fix must be designed against — it happens at the *start* of a
run, not the end, so nothing about the finished-slot can defend against it.

The other half of the inversion is named by `xtalapp/layout.py:75`:

```python
window._dock_tabs = _ScrollingDockTabs(window)
window.installEventFilter(window._dock_tabs)
```

A **Python** `eventFilter` on the `MainWindow` means every event
delivered to the window — `DeferredDelete` included — re-enters Python
and must take the GIL *inside Qt's event delivery*. That is literally the
frame in the `68304b8` sample:

> `PyGILState_Ensure -> take_gil -> _pthread_cond_wait`, inside a
> `QObjectWrapper::eventFilter` during `sendPostedEvents`

So the `68304b8` stack is not incidental: it is the main thread, inside
`sendPostedEvents`, needing the GIL because a Python event filter sits on
the window, while a worker thread holds the GIL inside `~QObject` waiting
for a Qt lock. `xtalapp/viewport/widget.py:200` installs a second Python
event filter on the VTK interactor, widening the same window. My own
sampled hang (§5) reached the same cycle by the mirror route — the main
thread in a Python `disconnect()` holding the GIL and blocked on the
mutex, a worker thread holding the mutex and blocked on the GIL — which
is the same inversion with the roles swapped, and evidence that *either*
side can be the one that blocks first.

**Upstream corroboration.** This family is **PYSIDE-2367**, *"QSignal.disconnect
deadlocks when overwriting disconnectNotify() in multiple thread setups"*
(closed, affects 6.4.1/6.5.3, fixed 6.6.0), whose two stacks are thread A
holding the GIL in `QMetaObject::disconnectOne` → `lockInternal`, and
thread B holding that mutex in `disconnectNotify` → `PyGILState_Ensure`.
Friedemann Kleint's note on it — *"seems to indicate that the
`QThread.started` is involved"* — is this helper.

**The 6.6.0 fix does not cover this project.** It wrapped *explicit*
`connect`/`disconnect` called from Python in `Py_BEGIN_ALLOW_THREADS`
(`// PYSIDE-2367, prevent threading deadlocks with connectNotify()`, still
in `qobjectconnect.cpp`). It did **not** touch destructors:
`SbkDeallocWrapperCommon` has no `Py_BEGIN_ALLOW_THREADS`, so a
Python-owned `QObject`'s C++ destructor still runs with the GIL held and
then takes Qt's connection lock. No upstream issue tracks that half.

**PYSIDE-3246**, *"Qt 6.10 Crash on quitting thread from within"* (fixed
6.11.0), has a reproducer that is structurally this helper and a stack
that is this bug —

```
shiboken6_abi3!Sbk_GetPyOverride
Qt6Core!QObject::~QObject+0x4f9
Qt6Core!QObject::event                     (DeferredDelete)
Qt6Core!QCoreApplicationPrivate::sendPostedEvents
```

— but it **affects 6.10.0/6.10.1 only**, and this project is on 6.9.3, so
it is not the cause here. The actionable version advice is narrow: stay
off 6.10.0/6.10.1; there is no PySide6 release that fixes what you have.

### Is there a second mechanism? Yes, and it is the commoner one

Besides the lock inversion, there is a plain use-after-free with no locks
involved. Both workers are constructed with `parent=None`
(`module_runner.py:210`, `ff_panel.py:715`), so **Python solely owns
them**, and both panels drop that single reference inside the finished
slot (`ff_panel.py:797` and `:861`, `module_runner.py:361`). The
`QThread` at `ff_panel.py:726` is *also* parentless. The result is that
an arbitrary thread's refcount drop — or a cyclic-GC pass, which in
CPython runs on whichever thread trips the allocation threshold — can
destroy a **running** `QThread`. Qt's response is `QThread: Destroyed
while thread is still running` and `std::terminate`. My harness produces
both outcomes from the same configuration (§5), which is the signature of
a race whose two losing branches are "free the C++ object under the lock"
and "free it while the thread still runs".

---

## 3. Object ownership, as numbered sequences

Read `D` as *delivered direct, on the emitting thread* and `Q` as
*queued, on the receiver's own thread*. Connection types are forced by
affinity: the worker lives on the worker thread after `moveToThread`; the
`QThread` **object** lives on the main thread, because that is where it
was constructed.

```
  owns (C++)        MainWindow ──parent──▶ QThread        (module_runner only)
  owns (Python)     ModuleRunner.module_worker ──▶ ModuleWorker
                    ModuleRunner._module_thread ──▶ QThread   (handle, never cleared)
                    FFPanel.worker ──▶ OptimizationWorker
                    FFPanel._thread ──▶ QThread              (NO parent, never cleared)
  owns (nothing)    every connect() in start_in_thread
```

### (a) A run that finishes normally

```
main    1. _start_module builds Job + ModuleWorker(parent=None)
main    2. connects worker.progressed/finished/failed to panel slots
main    3. self.module_worker = worker      <- the ONLY ref to the worker
main    4. start_in_thread(worker, window):
             thread = QThread(window)         C++ owns the thread
             worker.moveToThread(thread)
             thread.started  -> worker.run          D  (on the worker thread)
             worker.finished -> thread.quit         Q  (to the MAIN thread)
             worker.failed   -> thread.quit         Q  (to the MAIN thread)
             thread.finished -> worker.deleteLater  D  (on the worker thread)
             thread.finished -> thread.deleteLater  Q  (to the MAIN thread)
             thread.start()
worker  5. QThread::run emits started -> ModuleWorker.run() begins
worker  6. action.run(job); progressed.emit -> Q to main
worker  7. finished.emit(result) -> posts TWO calls to main:
             _on_module_finished (connected first), then thread.quit
worker  8. finally: _running = False; run() returns; its frame drops
           `self`.  Worker refcount is now 1 (module_worker).
worker  9. QThread::run enters exec() and blocks
main   10. event loop delivers _on_module_finished
             -> _finish_module -> self.module_worker = None
           The slot keeps a local `worker` (it is passed on to
           _show_report and _adopt_module_structure), so the actual
           free is when the slot's frame is torn down -- still inside
           QMetaCallEvent delivery of worker.finished.
             *** LAST Python ref to the worker dropped, inside signal
                 delivery, while the worker still lives on a running
                 thread.  ~QObject runs here, with the GIL held,
                 taking the connection lock.                        (H1)
           (FFPanel is blunter: ff_panel.py:797 is `self.worker = None`
            with no local, so the free is at that line -- which is what
            review/probes/who_frees_it.py prints.)
main   11. event loop delivers thread.quit()
worker 12. exec() returns; QThreadPrivate::finish emits thread.finished
             worker.deleteLater  -- already disconnected at step 10
             thread.deleteLater  -- Q, posted to the main thread
worker 13. the OS thread exits
main   14. sendPostedEvents delivers the QThread's DeferredDelete.
           ~QThread runs on the main thread, and because layout.py:75
           put a Python eventFilter on the window, this delivery needs
           the GIL from inside Qt's event dispatch.                 (H2)
main   15. self._module_thread now holds a wrapper whose C++ object is
           gone.  Never cleared; overwritten by the next run.
```

`H1` and `H2` are the two hazards. Neither is ordered with respect to any
other thread's Qt work.

### (b) A run that is cancelled

```
main    1. stop_module() -> ModuleWorker.cancel() -> job.cancel.cancel()
           (workers.py:248).  This fires every registered callback ON
           THE MAIN THREAD, including ExternalProcess.cancel -> killpg
           + wait(GRACE_SECONDS=5.0).  The GUI is blocked for up to
           five seconds inside the Stop button's own handler.
worker  2. the action returns early, or raises Cancelled
worker  3. ModuleWorker.run catches it and emits *finished*, never
           failed (workers.py:273-274)
        4. ... identical to (a) from step 7.  There is no separate
           teardown path for a cancelled run, so H1 and H2 are the same.
```

### (c) A run whose window closes while it is running

```
main    1. MainWindow.closeEvent (mainwindow.py:1807) calls
           self.stop_module() -- a flag, and the kill callback.  It
           does NOT wait.
main    2. ...may_discard_unsaved, save_session, save_window, sync
main    3. super().closeEvent(event); the window is destroyed
main    4. whenever the window is actually destroyed -- at application
           exit, or in the suite when pytest_runtest_teardown flushes
           DeferredDelete after qtbot's deleteLater -- ~MainWindow
           deletes its children, and the module QThread is one of them
           (MainWindow sets no WA_DeleteOnClose, so this is not at
           closeEvent itself).  If the worker has not reached
           `finished` -- and nothing waited for it -- this is
           "QThread: Destroyed while thread is still running" -> abort.
```

Two gaps here, both `[critical]`:

* **The Force Field optimisation is never stopped.** `closeEvent` calls
  `stop_module()` only. `FFPanel.closeEvent` (`ff_panel.py:863`, marked
  `# pragma: no cover`) would call `stop()`, but a dock's *contents* get
  no `QCloseEvent` when the top-level window closes — Qt delivers one to
  the top level only. So a running optimisation, and any xtb/DFTB+ child
  its engine holds through `stop_with`, survives the window.
* **The FF thread is not even in the window's child tree.**
  `ff_panel.py:726` is `start_in_thread(self.worker)` with no `parent`,
  so step 4 does not reach it at all; it simply keeps running while its
  only Python handle dies with the panel.

There is **no `atexit` and no `aboutToQuit`** anywhere in shipping code
(`grep -rn "atexit\|aboutToQuit" xtal/ xtalapp/` → nothing; the five hits
in the repo are all `shutil.rmtree` in `tests/conftest.py`).

### (d) A second run started while the first finishes

```
main    1. the first run is at step 12-14 above: thread.finished has
           fired, the DeferredDelete for the QThread is posted but not
           yet delivered, and the OS thread may still be unwinding
main    2. FFPanel._start runs again (ff_panel.py:715-726):
             self.worker = OptimizationWorker(...)   drops the old worker
             ...three connect() calls...
             self._thread = start_in_thread(self.worker)
                            ^ this assignment drops the LAST Python ref
                              to the previous QThread, on the main
                              thread, in the middle of a function whose
                              next acts are QThread(), moveToThread()
                              and five connect() calls.
```

That is both halves of the inversion in one statement: a thread holding
the GIL, destroying a connected `QObject` (which wants the connection
lock), and then immediately asking Qt to connect five things. It is also
exactly "every dump lands in `MainWindow.__init__` at a different line" —
the suite's version of the same shape is a teardown freeing the previous
test's objects while the next test's window does thousands of `connect()`
calls. `pytest_runtest_teardown` (`tests/conftest.py:216`) makes that
collision *deterministic per test*:

```python
QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
```

That hook is right and must stay — `CLAUDE.md` is correct that removing it
costs 1.2 GB — but it is also the thing that turns `H2` from "sometime,
maybe" into "once per test, at a known point, with a window under
construction next door". `qtbot`'s own teardown calls `deleteLater` on
every registered widget just before it, so the queue this hook flushes is
at its largest exactly when the next test starts building.

### Why "hold the pair alive" broke `test_modules_ui`

The module tests latch on the worker attribute, not on the thread:

```python
# tests/test_modules_ui.py:91
qtbot.waitUntil(lambda: window.module_worker is None, ...)
# tests/test_ff_ui.py:78
qtbot.waitUntil(lambda: dock.worker is None, timeout=TIMEOUT)
```

`window.module_worker` is `module_runner.module_worker`
(`mainwindow.py:1184-1191`), which `_finish_module` clears. Any fix that
keeps the pair alive *in that attribute* makes `run_and_wait` time out on
every call — which is the reported breakage, and it is a property of the
test's latch, not of the fix. **A fix must hold the pair somewhere else**
and leave `module_worker` / `dock.worker` meaning "no run in progress".
The prototype below does exactly that, and both latches keep working.

---

## 4. Pattern survey

| pattern | avoids the mechanism by construction? | cancel | pause/resume | progress | hour-long jobs |
|---|---|---|---|---|---|
| **1. worker + QThread as long-lived attributes, explicit `quit(); wait()`, no self-deleting connections** | **Yes** | cooperative flag | easy (worker has an event loop) | natural | **ideal** |
| **2. `QThreadPool` + `QRunnable` + separate signals QObject** | **Yes** — no Python `QThread` wrapper exists at all | cooperative only | hand-rolled (no event loop) | via the signals object | **poor** — occupies a global pool slot; `waitForDone()` at exit blocks for hours; no per-job `wait()` |
| **3. one persistent worker thread + a job queue** | **Yes** — one wrapper for the process lifetime | cooperative; queued jobs trivially droppable | natural | natural | fine, but strictly sequential |
| **4. `concurrent.futures` + a QObject relay** | **Yes** — no `QThread` object exists | `Future.cancel()` pre-start, then a flag | hand-rolled | good | good; `ProcessPoolExecutor` adds a hard kill |
| **5. `QtConcurrent`** | n/a | — | — | — | **not usable from PySide6** |

Notes that matter for a decision here.

**Pattern 1 is Qt's own documented pattern minus the `deleteLater`
lines.** It removes the mechanism because the wrapper's only owner is a
long-lived attribute (never freed during emission) and the C++ object is
never deleted inside event delivery. `QThread.wait()` is declared
`allow-thread="yes"` in PySide6's `typesystem_core_common.xml`, so it
releases the GIL and cannot participate in the inversion — measured above
as 83 Python ticks during a 1 s wait. Worth knowing: **`quit()` is *not*
in that allow-thread list**, so calling it directly from Python holds the
GIL while taking `QThreadPrivate`'s mutex. In the current helper `quit`
arrives from C++ through a queued connection, so it does not bite there —
but it does bite anywhere you call it yourself, including any `closeEvent`
teardown you add.

**Pattern 2 is what superqt/napari actually ship.**
`superqt/utils/_qthreading.py`'s `WorkerBase` is a `QRunnable` — *not* a
`QObject` — that composes a `WorkerBaseSignals(QObject)`, and starts via
`QThreadPool.globalInstance().start(self)`. It keeps
`WorkerBase._worker_set: ClassVar[set]` for exactly the lifetime reason,
although the docstring only claims it is for `await_workers()`. It is
battle-tested and structurally immune — but it is the wrong shape for
this application: a scan is an overnight job, and `await_workers()`'s own
docstring admits a worker with no yield points *"will just hang"*.

**Pattern 4 is Orange3's, and it solves the general problem explicitly.**
`Orange/widgets/utils/concurrent.py` uses a plain
`ThreadPoolExecutor(max_workers=1)` and bridges back **by posting a
QEvent**, not by emitting a signal from the callback thread:
`QCoreApplication.postEvent(selfref, QEvent(...))` in the done-callback,
`customEvent` emitting every signal on the GUI thread, and a
`weakref.ref(self)` so the callback cannot resurrect a dead widget. Its
`PyOwned` mixin is the clearest statement of this whole hazard class I
found anywhere:

> "A mixin for python owned QObject's used as queued cross thread
> communication channels. When this object is released from a thread
> that is not `self.thread()` it is **resurrected** and scheduled for
> deferred deletion from its own thread with `self.deleteLater()`."

**Spyder is the cautionary tale** — `QThread` + `moveToThread` with
`QThread(None)`, and a
`self._bag_collector = deque()  # Keeps references to old workers / Needed
to avoid C++/python object errors`, drained five seconds later by a
GUI-thread `QTimer`. That is this project's `_thread` attribute, with the
missing half bolted on.

**`QtConcurrent` is not an option.** `PySide6.QtConcurrent` is a stub —
its typesystem says *"this is currently the minimum possible
QtConcurrent support, by just extracting the name space from QtCore"* —
with no `run`, `map` or `task`, and no generic `QFuture` in QtCore.
PYSIDE-1896 and PYSIDE-1202 are both still open. The Python-looking
snippets on `doc.qt.io/qtforpython-6/overviews/qtconcurrentrun.html` are
machine-translated C++ for an API that is not bound.

**Ranking for what this application needs** (cancel, pause/resume,
per-step progress, jobs that run for hours): **1, then 4, then 3, then
2**. Pattern 1 wins because an hour-long job wants a dedicated thread
rather than a pool slot, and because the worker having a real event loop
is what makes pause/resume and mid-run control cheap — which
`OptimizationWorker` already relies on.

### What each candidate one-liner does and does not fix

| change | fixes | does **not** fix |
|---|---|---|
| drop `thread.finished.connect(thread.deleteLater)` | `H2`: no `QThread` destroyed inside `sendPostedEvents` | nothing — you must now own the thread yourself, or you get "Destroyed while thread is still running" instead |
| drop `thread.finished.connect(worker.deleteLater)` | the same class for the worker | ditto |
| strong refs in a set, and nothing else | GC/refcount destruction of a *running* QThread from an arbitrary thread | the inversion itself — with `deleteLater` still connected the mechanism is intact and you get a zombie wrapper (§1) |
| explicit `quit(); wait()` at teardown | ordering: the thread is provably stopped before anything is freed; `wait()` is allow-thread | anything mid-run; and `quit()` is **not** allow-thread |
| disconnect before delete | shortens `~QObject`'s work | on PySide6 < 6.6 the explicit `.disconnect()` *is* the deadlocking call (PYSIDE-2367); on 6.9.3 it is allow-threaded and buys little |
| a lambda instead of a bound method | nothing | **actively harmful** — it forces the `PySideQSlotObject` branch instead of `connectByIndex`, creating a Python slot object whose closure *does* strongly reference the thread, i.e. it manufactures the ownership the docstring wrongly assumed already existed |
| spelling `Qt.QueuedConnection` | nothing | `worker.finished → thread.quit` and `thread.finished → thread.deleteLater` are *already* queued by affinity |
| upgrading PySide6 | PYSIDE-3246 (≥6.11), if you ever go to 6.10 | the destructor half of the inversion, which no release fixes |

---

## 5. The prototype, and what it measures

`review/probes/workers_fixed.py` is a copy of `xtalapp/workers.py` with
`start_in_thread` replaced (everything else byte-identical;
`.venv/bin/ruff check` passes). The change is 60 lines:

* a module-level `_LIVE` set and an unparented `_Run(QObject)` that owns
  the worker and the thread **from the GUI thread**, from before
  `thread.start()` until after the thread has stopped — which is what
  closes **H0**, the hazard the sample in §5 actually caught: with an
  owner in `_LIVE`, releasing the transient bound method at the end of
  the `started` metacall can no longer be the last reference;
* **no `deleteLater` on either object** — lifetime is Python's alone;
* `worker.finished`/`failed` → `_Run._finished`, which runs on the GUI
  thread (queued by affinity), does `thread.quit(); thread.wait()`, and
  then defers the actual drop by one event-loop turn with
  `QTimer.singleShot(0, ...)` so that nothing is freed while Qt is still
  delivering a signal;
* `stop_all(timeout)` / `_Run.stop_and_wait()` for `closeEvent`.

Crucially it holds the pair in `_LIVE`, **not** in
`module_runner.module_worker` or `FFPanel.worker`, so the
`waitUntil(... is None)` latches in `test_modules_ui.py:91` and
`test_ff_ui.py:78` keep working — which is the specific thing the
author's earlier attempt broke.

`review/probes/stress_workers.py` runs 200 short jobs through each
module, by file path via `importlib`, with a watchdog thread that dumps
`faulthandler` and `os._exit(3)`s after 20 s without progress. It has two
modes, and **the honest result is that the plain one is nearly useless**:

* `--mode plain` — 200 jobs back to back, nothing else happening.
* `--mode hostile` — the shape a pytest run has: a Python `eventFilter`
  installed on the window (as `layout.py:75` does), a
  `sendPostedEvents(DeferredDelete)` at each job's teardown (as
  `conftest.py:216` does), and, on the GIL-holding side, several hundred
  `QObject` constructions and `connect()`/`disconnect()` calls per job (as
  `MainWindow.__init__` does).

Two further knobs matter and are worth explaining, because they are what
turns an un-reproducible bug into a 10/10 one:

* `--tail 0.005` — five milliseconds of work *after* `finished.emit`, so
  the GUI thread's slot runs while `run()` is still on the worker
  thread's stack. Without it the worker's wrapper is always freed on the
  main thread after `run()` has returned, and the interesting branch of
  the race never happens.
* `--no-parent` — `QThread(None)`, which is what `ff_panel.py:726` does.

**Results.** `REPEATS` repeats of 200 jobs each; `crash` is a non-zero
exit (segfault / `Fatal Python error: Aborted` / `QThread: Destroyed
while thread is still running`), `hang` is the watchdog firing.

```
REPEATS=10  JOBS=200          ("crash" = non-zero exit; "hang" = watchdog fired)

ORIGINAL (xtalapp/workers.py)
  plain   ov=1 tail=0   parented     ok= 9  crash= 1  hang=0   Destroyed_while_thread
  hostile ov=1 tail=0   parented     ok= 5  crash= 0  hang=0   (5 repeats)
  hostile ov=4 tail=5ms parented     ok= 0  crash= 8  hang=2   7x segfault, 1x abort
  hostile ov=4 tail=5ms NO parent    ok= 0  crash=10  hang=0   7x segfault, 3x Destroyed
  plain   ov=4 tail=5ms NO parent    ok= 0  crash=10  hang=0   9x segfault, 1x Destroyed

FIXED (review/probes/workers_fixed.py)
  plain   ov=1 tail=0   parented     ok=10  crash= 0  hang=0
  hostile ov=1 tail=0   parented     ok=10  crash= 0  hang=0
  hostile ov=4 tail=5ms parented     ok=10  crash= 0  hang=0
  hostile ov=4 tail=5ms NO parent    ok=10  crash= 0  hang=0
  plain   ov=4 tail=5ms NO parent    ok=10  crash= 0  hang=0
```

**Fifty repeats of 200 jobs each against the fixed module: 50 clean, 0
failures. The same five configurations against the shipped module: 31
failures in 45 runs.** Reproduce with `review/probes/matrix.sh`.

### The deadlock itself, captured live

One `--mode hostile --overlap 1 --tail 0.005` run against the **original**
module wedged and sat there. `sample` on it (saved as
`review/probes/hung_sample.txt`) is the whole bug in two stacks. This is
PySide6 **6.9.3**, i.e. well after the PYSIDE-2367 fix.

**Main thread — holding the GIL, blocked on Qt's connection mutex:**

```
Sbk_QApplicationFunc_exec
  QCoreApplicationPrivate::sendPostedEvents
    QCoreApplication::sendEvent
      QApplicationWrapper::notify -> QApplication::notify -> notify_helper
        QObjectWrapper::event -> QObject::event
          SignalManagerPrivate::qtMethodMetacall          (a Python slot)
            signalInstanceDisconnect
              PySide::qobjectDisconnectCallback
                PySide::disconnectSlot
                  QObject::disconnect(const QMetaObject::Connection &)
                    QBasicMutex::lockInternal()      <-- BLOCKED
```

**A worker thread — holding that mutex, blocked on the GIL:**

```
QThread::started(QThread::QPrivateSignal)              <-- emitting `started`
  SignalManagerPrivate::qtMethodMetacall               <-- delivering to worker.run
    method_dealloc                                     <-- the bound method is freed
      subtype_dealloc
        SbkDeallocWrapperCommon
          QObjectWrapper::~QObjectWrapper              <-- the WORKER's wrapper
            QObject::~QObject
              QThreadWrapper::disconnectNotify(QMetaMethod)
                Sbk_GetPyOverride
                  PyGILState_Ensure
                    take_gil -> _pthread_cond_wait     <-- BLOCKED
```

Every other thread in the sample is also in `take_gil`, so the main
thread is the GIL holder by elimination. That is a closed cycle: neither
side can proceed, ever.

**This refines the diagnosis in `CLAUDE.md` in one specific way, and it
matters for the fix.** The wrapper freed inside signal delivery is the
**worker's**, not the `QThread`'s — freed by `method_dealloc` when the
transient bound method Qt built for the `started` metacall is released at
the end of the call. The `QThread` is the object whose
**`disconnectNotify`** is then invoked, because `~QObject` notifies the
*sender* of each connection it tears down, and `thread.started ->
worker.run` makes the thread that sender. (Friedemann Kleint's note on
PYSIDE-2367 — *"seems to indicate that the `QThread.started` is
involved"* — is this exact frame.)

So the requirement on a fix is sharper than "hold the pair alive": **the
worker must not be the last reference at the moment `started` finishes
being delivered.** A `_LIVE` set that holds the worker from before
`thread.start()` until after the thread has stopped satisfies that by
construction, and is why the fixed column is clean.

It also explains a limitation of **my** harness, worth stating because it
understates the original's failure rate: `stress_workers.py`'s watchdog
is a *Python* thread, so a GIL deadlock freezes the watchdog too. The
run sampled above hung with its watchdog blocked in `take_gil` and would
have sat there forever; I found it as a stray process minutes later.
Every `hang=0` in the ORIGINAL column should be read as "no hang *that
this watchdog could report*", and the true original failure count is a
lower bound.

This is **not** a criticism of `CLAUDE.md`'s `-o faulthandler_timeout=90`
advice, which is correct and which I would keep: `faulthandler`'s
watchdog is a **C** thread that walks the interpreter state and dumps
without acquiring the GIL. That is precisely why it could name this hang
and mine could not.

**Reading these honestly.** The plain, one-at-a-time pass — the obvious
harness, and the one I would have written if I had stopped at the task
description — fails **1 run in 10**, and only with the "Destroyed while
thread is still running" branch, which is the refcount race and not the
lock inversion. If I had reported on that alone the answer would have
been "mostly fine, occasionally crashes", which is wrong.

What makes the difference is the two knobs above. `--tail` creates the
overlap between the GUI thread's slot and the worker thread's
still-executing `run()`; `--mode hostile` puts Qt work on the
GIL-holding side. With both, the failure rate goes from 1-in-10 to
**10-in-10**. That is also why the author's rate is "one in four" for a
full suite rather than "every run": it needs a worker finishing in the
same few milliseconds as a window being built, and the suite only
arranges that when the timing happens to line up.

One caveat on the machine: `sysctl vm.swapusage` read
`used = 9648.38M` of 10240 M during these runs, i.e. 94 % — as `CLAUDE.md`
warns. I treated only non-zero exits with a Qt/shiboken signature as
crashes, and no run produced the `dlopen` stack that would mean memory
rather than code.

---

## 6. Recommended fix

**Shape: pattern 1, applied to the existing helper.** Size, measured:
the 27-line `start_in_thread` block in `xtalapp/workers.py` becomes 110
lines (about 45 of which are docstring, in the house style); plus ~4
lines in `xtalapp/mainwindow.py` and one word in
`xtalapp/docks/ff_panel.py`. Nothing else in `workers.py` changes —
`OptimizationWorker` and `ModuleWorker` are byte-identical in the
prototype. Risk: **low-medium** — no public signature changes, no caller
changes, and the two test latches that broke last time keep working by
construction.

1. **`xtalapp/workers.py`** — replace `start_in_thread` with the
   `_Run`/`_LIVE` version in `review/probes/workers_fixed.py`. Four
   rules, in the order they matter: *the worker has an owner outside the
   connections before the thread starts* (closes H0); *nothing is
   deleted by Qt* — delete both `thread.finished.connect(...deleteLater)`
   lines; *both objects are owned from Python on the GUI thread*; *the
   drop happens one clean event-loop turn after the thread has stopped*,
   via `QTimer.singleShot(0, ...)`, so nothing is freed with Qt still
   delivering a signal underneath.
   The `_Run` is deliberately **unparented**: parenting it to the window
   would hand its lifetime back to C++, and closing the window would then
   destroy it while `_LIVE` still held the wrapper — the same zombie the
   change exists to stop making.
2. **`xtalapp/docks/ff_panel.py:726`** — pass a parent:
   `start_in_thread(self.worker, self)`. A parentless `QThread` whose only
   handle is an attribute that is silently overwritten by the next run is
   the worst call site in the codebase, and it is a one-word fix.
3. **`xtalapp/mainwindow.py:1807`** — in `closeEvent`, after
   `self.stop_module()`, also stop the optimisation and then **wait**:
   `self.ff_panel.stop()` and `workers.stop_all()`. Today the window can
   be destroyed with a live thread among its children (sequence (c)),
   which is an abort, not a hang; and the FF worker is not stopped at all.
   `FFPanel.closeEvent` cannot do this job — a docked widget does not get
   a close event when its window closes, which is why that method is
   `# pragma: no cover`.
4. **Then reconsider `-n auto`.** `CLAUDE.md` says fixing this is what
   gives back 25 s instead of ~173 s serial. That claim should be
   re-measured after the fix rather than assumed: `conftest.py:62`'s own
   docstring records a *second* wedge cause — eight workers contending on
   `cfprefsd` — which the INI-backend guard already addressed but which
   deserves a run before the default is changed back.

5. **Fix the `Stop` granularity on a scan** (§7) — `xtal/ff/scan.py:541`
   should pass a `callback=` into `optimize.run` so the step loop breaks
   the way `OptimizationWorker.run` breaks it. Independent of the
   threading fix, and the one Stop bug a user will actually meet.
6. **Add a reaper** (§8) — `app.aboutToQuit → workers.stop_all()` plus an
   `atexit` that kills any live `ExternalProcess`. There is none today,
   and `start_new_session=True` guarantees an abrupt exit orphans the child.

What I would **not** do: move to `QThreadPool`. It is immune by
construction, but a scan is an overnight job and the pool is the wrong
place for one, for the reasons superqt's own `await_workers()` docstring
gives.

**How to verify it rather than believe it.** `review/probes/matrix.sh`
is the cheap check (seconds, and it discriminates 31-failures-in-45 from 0-in-50). The
real check is ten full suite runs with `-o faulthandler_timeout=90`
before and after. `CLAUDE.md`'s advice to use it is sound and I would
not change it: `faulthandler`'s watchdog is a **C** thread that dumps
without taking the GIL, which is exactly why it could name this hang
when my own Python-thread watchdog could not (§5).

---

## 7. Cancellation

**`[important]` Two modules never poll cancellation at all.**
`xtal/modules/build.py` (`build.build_molecule`) and `xtal/modules/net.py`
(`net.draw_net`) contain no reference to `cancel` whatsoever. Stop is a
no-op on them until the job ends naturally. `xtal/modules/mof.py:191-196`
is a near-third and is at least honest about it — *"Cancellation is
checked either side of the build and not during it"* — so Stop on a MOF
build only changes the message afterwards (`mof.py:211-213`).

The machinery itself is good. `xtal/modules/job.py:52-105`'s
`Cancellation` is a `threading.Event` plus a callback list, with
`when_cancelled` registering a terminator that fires immediately if
already cancelled, and `forget` for a process that has ended. The design
note at `job.py:19-26` — *"an external process cannot be asked anything…
so cancelling has to reach the process itself"* — is exactly right, and
`ModuleWorker`'s docstring is one of the better pieces of writing in the
repo. `[strength]`

**`[important]` `optimize.steps` advertises `cancel=` and never checks
it.** `xtal/ff/optimize.py:1361` takes it; the only uses in 1439 lines are
the docstring and the forward at `:1381-1384`:

```python
if cancel is not None and hasattr(calculator, "stop_with"):
    calculator.stop_with(cancel)
```

Neither `_descend` (`:1156`), `fire` (`:812`) nor `_line_search` (`:1121`)
polls anything. So there are two stop mechanisms with very different
granularity:

* the **consumer breaks the generator** — `workers.py:127-128`,
  `if self._cancel.is_set(): break`. This is what makes Stop work in the
  Force Field panel. Granularity: **one optimiser step**, which for a
  line-search method is several energy evaluations.
* the **engine kills its binary** — honoured by exactly two engines,
  `xtal/ff/xtb/calculator.py:332-341` and
  `xtal/ff/dftb/calculator.py:347-356`, and correctly forwarded through
  the marker-holding wrapper at `xtal/ff/markers.py:138-139`. Granularity:
  genuinely **mid-evaluation**; the SCC cycle is killed and
  `CalculatorStopped` propagates, with `workers.py:129-135` keeping the
  last completed step. That is a nice piece of design. `[strength]`
  UFF and MACE contain no `cancel` reference at all, which `api.py:85-89`
  documents as intentional.

**`[important]` Stop on a relaxed scan under UFF or MACE is dead for
minutes.** `xtal/ff/scan.py:460-461` polls `cancel.requested` only at the
top of each grid index, and `_one_point` calls
`optimize.run(..., cancel=cancel, ...)` at `:541-545` **with no
`callback=`** — so nothing breaks the step loop and the in-process engine
ignores `cancel`. The unit is one whole scan point: up to `max_steps`
(default 500, `xtal/modules/scan.py:250`) at, by `CLAUDE.md`'s own
measurement, 0.44 s/step on 1152 atoms. With a pre-relax engine
configured (`xtal/ff/scan.py:570-589`) it is two such relaxations back to
back. This is the longest dead Stop in the codebase and the one users will
actually meet, since a scan is the thing people leave running.
**Fix:** pass `callback=` (or a `cancel` poll) down into `_one_point`'s
`optimize.run` so the step loop breaks the way `OptimizationWorker.run`
breaks it.

**`[minor]`** Zeo++'s post-process phase is unstoppable seconds:
`_accessible_surface` (`xtal/modules/zeopp.py:295-334`, called at `:539`)
runs `grids.distance_grid` then `iso.isosurface`, and neither
`xtal/analysis/grid.py` nor `xtal/analysis/isosurface.py` mentions
cancellation. ~3 s on MFU-4l per `CLAUDE.md`.

**`[minor]`** `ModuleWorker.cancel` runs the whole kill on the GUI thread
(§3b step 1), including `ExternalProcess.cancel`'s
`wait(timeout=GRACE_SECONDS=5.0)`. Stop can freeze the window for five
seconds. Moving the terminate/wait onto a short-lived thread, or making
the grace period asynchronous with a `QTimer`, would fix it.

---

## 8. The external-process runner

`xtal/modules/process.py:318-481`. This is the best-engineered part of
the area I reviewed. `[strength]`

* `subprocess.Popen` with an argv list (no shell), `stdin=DEVNULL` so it
  can never block on input, stderr merged into stdout
  (`process.py:387-393`).
* Isolation at `:488-498`: `start_new_session=True` on POSIX,
  `CREATE_NEW_PROCESS_GROUP` on Windows.
* Kill at `:453-468`: terminate → `wait(grace=5.0)` → kill, and on POSIX
  **both stages signal the group** (`os.killpg(os.getpgid(pid), ...)` at
  `:505-506` and `:513-514`), so a shell wrapper cannot orphan its child.
* Both races are closed: cancel-before-launch returns without launching
  (`:370-385`), cancel-between-check-and-Popen is re-checked at
  `:407-408`. The stream loop deliberately does not poll — *"cancelling
  closes it, because cancelling kills the writer"* (`:424-431`).

**Windows.** `docs/RELEASE_NOTES.md:33-34` claims Stop *"now ends a
program started through a wrapper script"*. The code backs it:
`_end_tree` (`:517-537`) runs `taskkill /F /T /PID` **before**
`process.kill()`, which is the required order — the docstring explains
why (*"`taskkill /T` walks the tree from the parent, so it has to run
while the parent is still there"*). So no, the wrapper fix is not an
illusion. Three caveats for the author:

* `[minor]` On Windows `_terminate` and `_kill` are the **same function**
  (`:502-504` and `:510-512` both call `_end_tree`, which is
  `taskkill /F`). The documented "terminate gently, wait, then kill"
  contract at `:26-30` degenerates to "force-kill the tree twice", so
  nothing on Windows gets a chance to close its output files. The
  docstring explains the *why* but the asymmetry is not flagged at the
  call site.
* `[important]` If `taskkill` is missing or fails, `except (OSError,
  subprocess.SubprocessError): pass` at `:535-536` falls through to
  `process.kill()` alone — silently restoring the exact orphaning bug the
  release note claims fixed.
* `[minor]` Every Windows branch is `# pragma: no cover` (`:496, 502,
  510, 517, 554`). None of it is exercised.

**`[critical]` Nothing reaps a child on an abrupt exit.** There is no
`atexit` and no `aboutToQuit` hook, and `start_new_session=True`
deliberately detaches the child from our process group, so no POSIX
signal follows the parent's death and there is no Windows Job Object
(`grep JobObject` → nothing). A crashed or `kill -9`'d application leaves
xtb/DFTB+/Zeo++ running and writing into a run folder nobody is watching.
Given §3c already shows `closeEvent` is the *only* reaper and that it
misses the FF panel's child entirely, an `app.aboutToQuit` connected to
`workers.stop_all()` plus an `atexit` that kills any live
`ExternalProcess` is cheap insurance.

---

## 9. The scan's partially written landscape

**`[strength]` A cancelled scan is handled properly and I could not
break it.** The cancel path at `xtal/ff/scan.py:460-461` is a bare
`return` from the generator, so the `for` loop in `run_scan`
(`xtal/modules/scan.py:252-256`) ends *normally* — no exception — and
every closing line at `:256-273` runs.

| artefact | written | where |
|---|---|---|
| `scan.csv` header | before the first point | `modules/scan.py:369-377` |
| `scan.csv` row | **per point, then `flush()`** | `:381-392` |
| `<branch>-NN-NN.cif` | **per point, but only `if point.finished`** | `:393-395`, `_write_cif` `:397-413` |
| `report.json` | once, at the end — **and on a cancel too** | `writer.keep(report)` `:261` → `:419-431` |
| `energy_landscape.png` | once, at the end, by the GUI not the module | `xtalapp/module_runner.py:322-355` |

The PNG survives a cancel because `ModuleWorker.run` emits **`finished`,
not `failed`, for a cancelled result** (`workers.py:269-274`), so
`_on_module_finished` runs and `_save_report_images` is its first act
(`module_runner.py:264`). The partial landscape reopens by
double-clicking `report.json` exactly as the `CLAUDE.md` invariant
promises: `workspace_shell.py:363-382` → `xtal/modules/report.py:787-804`,
with per-cell CIF paths stored relative and re-absolutised at `:806-825`.

The partial-grid maths is careful throughout: `ScanResult.base()` returns
`0.0` when nothing finished (`xtal/ff/scan.py:705-707`), `grid()` is
pre-filled with NaN (`:694-699`), `best()` guards the empty case
(`:726-727`), and `hysteresis()` returns `None` when only one branch has
points (`:736-739`) — which is exactly the state a scan stopped during the
forward branch is in. A cancel before the first point completes still
produces a valid all-NaN report. Pinned by
`tests/test_scan_module.py:181-196` (`assert 0 < len(written) < 9`).

**`[minor]` One trap for the `--resume` in `docs/TODO.md:156-165`.**
That entry says `scan.csv` *"already holds everything needed… the file
each point left behind"*. It does not, quite: `_Files.wrote` writes the
`name` column unconditionally (`modules/scan.py:391`) but writes the CIF
only `if point.finished` (`:393`). A hole in the landscape therefore names
a `.cif` that does not exist, and a resume that trusts the `file` column
rather than the empty energy/`converged` columns would re-seed from a
missing file. Worth writing down before somebody implements it.

**`[minor]`** The same entry's framing of Stop as instantaneous is only
true for xtb and DFTB+. Under UFF or MACE, "stopped at point 60 of 144"
means point 61 runs to completion first (§7). Nothing is lost — the yield
at `xtal/ff/scan.py:476` happens before the next cancel check, so point 61
is written — but the user waits, possibly for minutes.

---

## What I did not get to

* **I did not run the full test suite**, on the brief's own advice
  (serial, 4-6 min, and the machine at 94 % swap). So I have not measured
  the 1-in-4 hang rate directly, nor confirmed that the prototype changes
  it. I did reproduce and sample the deadlock itself (§5), which I think
  settles the mechanism; what remains unmeasured is the suite's rate.
  That is the obvious next step: apply `workers_fixed.py` on a branch and
  run `python -m pytest -q -o faulthandler_timeout=90` ten times each way.
* **I did not wire the prototype into the application** — the brief
  forbids touching tracked files — so the `closeEvent` and `ff_panel`
  changes in §6 are reasoned from the code, not run.
* **I did not exercise the Windows path.** Everything in §8 about Windows
  is read, not run, and every branch there is `# pragma: no cover`.
* **I did not test cancel against a real xtb or DFTB+ binary**, only
  against the code path; `resources/test/` is largely absent on this
  machine, as the brief warns.
* **`--mode hostile` is a model, not the suite.** It reproduces the
  mechanism and it discriminates sharply between the two modules, but a
  pass on it is not a proof that the suite's hang is gone.
