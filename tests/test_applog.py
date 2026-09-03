"""The application writes down what happened, including what killed it.

A packaged build has no stderr.  Every one of these covers something
that used to go there and would otherwise go nowhere: a plugin that
would not load, a Qt warning, and the traceback of the exception that
closed the window.

The last two are about *staying* attached.  Two things in this
application move the root logger around -- rdeditor calls
``logging.basicConfig`` in a widget constructor, and PORMAKE is
imported with ``logging.FileHandler`` swapped out from under it -- and
either could quietly take the log file with it.
"""

import logging

import pytest

from xtalapp import applog


@pytest.fixture
def log(tmp_path):
    """A log of this test's own, detached again afterwards."""
    applog.reset()
    path = applog.setup(tmp_path)
    yield path
    applog.reset()


def read(path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def test_a_message_is_written_to_the_file_it_was_told_to_use(log):
    logging.getLogger("xtal.test").warning("the cell is not reduced")

    assert log.parent.name  # it went where the fixture said
    assert "the cell is not reduced" in read(log)


def test_setting_up_twice_does_not_write_every_message_twice(log):
    again = applog.setup(log.parent)
    logging.getLogger("xtal.test").warning("once")

    assert again == log
    assert read(log).count("once") == 1


def test_an_uncaught_exception_is_written_down(log, monkeypatch):
    """Without this a packaged build closes with nothing to send."""
    monkeypatch.setattr("sys.excepthook", lambda *a: None)
    applog.install_excepthook()
    try:
        raise ValueError("no such space group")
    except ValueError as exc:
        import sys
        sys.excepthook(type(exc), exc, exc.__traceback__)

    written = read(log)
    assert "ValueError: no such space group" in written
    assert "Unhandled exception" in written
    assert "test_an_uncaught_exception_is_written_down" in written


def test_an_exception_in_a_worker_thread_is_written_down(log,
                                                         monkeypatch):
    """Where the long work happens, and so where a crash hides.

    An optimisation and a module run both happen off the GUI thread,
    and an exception raised there never reaches ``sys.excepthook``.
    """
    import threading
    monkeypatch.setattr(threading, "excepthook", lambda *a: None)
    applog.install_excepthook()

    def explode():
        raise RuntimeError("the calculator went away")

    thread = threading.Thread(target=explode)
    thread.start()
    thread.join()

    assert "RuntimeError: the calculator went away" in read(log)


def test_a_keyboard_interrupt_is_left_to_the_interpreter(log,
                                                         monkeypatch):
    """Ctrl-C is not a crash and should not be reported as one."""
    seen = []
    monkeypatch.setattr("sys.__excepthook__",
                        lambda *a: seen.append(a))
    applog.install_excepthook()
    import sys
    exc = KeyboardInterrupt()
    sys.excepthook(KeyboardInterrupt, exc, None)

    assert seen and "Unhandled exception" not in read(log)


def test_a_qt_warning_reaches_the_log(log):
    """Qt's warnings explain the layout that came out wrong, and they
    go to a stderr a windowed build does not have."""
    qtcore = pytest.importorskip("PySide6.QtCore")
    applog.install_qt_handler()
    try:
        qtcore.qWarning("a stray Qt complaint")
        assert "a stray Qt complaint" in read(log)
    finally:
        qtcore.qInstallMessageHandler(None)


def test_the_log_directory_is_never_the_users_own_during_a_test():
    """``tests/conftest.py`` points XTAL_LOG_DIR at a scratch folder
    before anything can look, the way it does for QSettings."""
    directory = applog.default_directory()

    assert "xtal-test-logs-" in str(directory)
    assert "Application Support" not in str(directory)


# ======================================================================
#  STAYING ATTACHED
# ======================================================================

def test_the_sketcher_leaves_the_log_handler_attached(log, qtbot):
    """rdeditor's widget calls ``logging.basicConfig`` and sets the
    root logger's level.  ``sketch._canvas`` puts both back, and this
    is the test that says the log survives it."""
    pytest.importorskip("rdeditor")
    from xtalapp.dialogs import sketch

    canvas = sketch._canvas()
    qtbot.addWidget(canvas)
    logging.getLogger("xtal.test").warning("after the sketcher")

    assert "after the sketcher" in read(log)


@pytest.mark.slow
def test_importing_pormake_leaves_the_log_handler_attached(log):
    """``import_pormake`` swaps ``logging.FileHandler`` so PORMAKE's
    ``runtime.log`` lands in a temp folder rather than the working
    directory.  Ours is attached before that and must outlive it.

    The guard is ``installed()`` and not ``importorskip``, which is
    the rule everywhere else in this repository and here it has
    teeth: ``importorskip`` would import PORMAKE *around* the
    containment, drop a ``runtime.log`` in the working directory, and
    leave the thing under test already in ``sys.modules``.
    """
    from xtal.mof import installed
    if not installed():
        pytest.skip("PORMAKE is not installed")
    from xtal.mof.build import import_pormake

    import_pormake()
    logging.getLogger("xtal.test").warning("after pormake")

    assert "after pormake" in read(log)


# ======================================================================
#  REACHING IT FROM THE WINDOW
# ======================================================================

@pytest.fixture
def window(qtbot, tmp_path):
    pytest.importorskip("pytestqt")
    from PySide6.QtWidgets import QWidget

    from xtalapp.mainwindow import MainWindow
    from xtalapp.settings import AppSettings

    class Stub(QWidget):
        def __init__(self, document, parent=None):
            super().__init__(parent)
            self.document = document

    settings = AppSettings("CrystalBuilderTest", f"Log{tmp_path.name}")
    settings.clear_window()
    win = MainWindow(viewport_factory=Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def test_the_help_menu_offers_the_log(window):
    assert "show_log" in window.actions_.names()


def test_showing_the_log_reveals_the_folder_it_is_in(window, log,
                                                     monkeypatch):
    """The folder, not the file: a rotating megabyte of text opened in
    whatever has claimed ``.log`` is a worse answer than Finder."""
    opened = []
    monkeypatch.setattr(applog, "reveal",
                        lambda: opened.append(applog.log_file()))
    window.show_log()

    assert opened == [log]


def test_a_window_with_no_log_says_so_rather_than_doing_nothing(
        window, monkeypatch):
    """Logging is started by ``main()`` and by nothing else, so a
    window built directly has never had one."""
    applog.reset()
    said = []
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **k: said.append(a[2]))
    window.show_log()

    assert said and "not started by the application" in said[0]
