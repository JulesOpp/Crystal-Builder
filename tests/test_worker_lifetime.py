"""Who owns a worker and its thread, and when they are let go.

The arrangement this replaces wired ``finished`` to ``deleteLater`` on
both the worker and its thread, which put the destruction of two Python
wrappers at two moments nobody chose: the worker's on the dying thread,
the thread's inside ``sendPostedEvents``.  A Python wrapper cannot be
destroyed without the GIL, and ``~QObject`` severing its connections
holds Qt's connection lock while calling back into Python for
``disconnectNotify`` -- so a GUI thread holding the GIL and connecting
anything waits on that lock for as long as the other thread waits for
the GIL.  Qt documents the hazard on ``disconnectNotify`` itself.

Against a harness shaped like the suite, the shipped module aborted
with "QThread: Destroyed while thread is still running" in five runs
out of five.  ``review/probes/stress_workers.py`` is that harness and
``review/probes/matrix.sh`` runs it across the configurations.
"""

from xtalapp import workers


class _Tiny(workers.QObject):
    finished = workers.Signal(object)
    failed = workers.Signal(str)

    def run(self):
        self.finished.emit(object())


def test_a_finished_run_lets_go_of_its_worker_and_its_thread(qtbot):
    """Nothing is deleted by Qt, so something has to let go, and it is
    a plain event-loop turn with no thread dying underneath it."""
    worker = _Tiny()
    thread = workers.start_in_thread(worker)
    qtbot.waitUntil(lambda: not workers._LIVE, timeout=5000)
    assert thread.isFinished()


def test_a_run_still_going_is_not_forgotten(qtbot):
    """_LIVE is what closeEvent asks; a run missing from it is a
    thread nobody will wait for, which is the abort."""
    worker = _Tiny()
    before = len(workers._LIVE)
    workers.start_in_thread(worker)
    assert len(workers._LIVE) >= before


def test_stop_all_waits_for_every_run_not_just_the_first(qtbot):
    """`all` over a generator short-circuits, and a thread left
    running when the window is destroyed aborts the process."""
    import inspect
    source = inspect.getsource(workers.stop_all)
    assert "list(" in source or "[" in source


def test_the_panel_does_not_own_its_thread_by_an_attribute_alone():
    """ff_panel.py started its thread with no parent and kept the only
    handle in an attribute the next run overwrote -- the worst call
    site in the application, and a one-word fix."""
    import pathlib
    text = (pathlib.Path(__file__).resolve().parent.parent
            / "xtalapp" / "docks" / "ff_panel.py").read_text()
    assert "start_in_thread(self.worker, self)" in text


def test_closing_the_window_stops_the_force_field_run_too():
    """closeEvent stopped the module worker and never this one.
    FFPanel.closeEvent would have, but a docked widget gets no close
    event when its window closes -- Qt delivers one to the top level
    only, which is why that method was never covered."""
    import pathlib
    text = (pathlib.Path(__file__).resolve().parent.parent
            / "xtalapp" / "mainwindow.py").read_text()
    close = text[text.index("def closeEvent"):]
    close = close[:close.index("super().closeEvent")]
    assert "ff_dock.stop()" in close
    assert "workers.stop_all()" in close
