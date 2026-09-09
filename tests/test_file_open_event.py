"""A file handed over by Finder reaches the window.

Double-clicking a ``.cif`` delivers it two different ways, and only
one of them was ever handled.  A cold launch puts the path in
``argv``; a launch into an application that is *already running* puts
it in a ``QFileOpenEvent`` on the application object, and nothing
read those -- so opening a second structure from Finder did nothing
at all, which reads as the file association being broken.

The cold case is the one worth the care.  macOS delivers the event
during start-up, **before** ``MainWindow`` exists, so a handler that
opens the file the moment it arrives drops it exactly when somebody
launched the application by opening a file.  Every test below that
says "before the window" is guarding that.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QCoreApplication, QUrl  # noqa: E402
from PySide6.QtGui import QFileOpenEvent  # noqa: E402
from PySide6.QtWidgets import QWidget  # noqa: E402

from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def app(qapp):
    """The session's application, with its queue put back after.

    ``qapp`` is one object shared by the whole run, so anything left
    on it is another test's problem three files away.
    """
    qapp.reset()
    yield qapp
    qapp.reset()


@pytest.fixture
def deliver(app):
    """Connect a window and release the queue, undone afterwards."""
    connected = []

    def connect(window):
        app.file_opened.connect(window.open_from_desktop)
        connected.append(window)
        app.start_delivering()

    yield connect
    for window in connected:
        app.file_opened.disconnect(window.open_from_desktop)


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Open{tmp_path.name}")
    settings.clear_window()
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


# ======================================================================
#  WARM: THE WINDOW IS ALREADY UP
# ======================================================================

def test_a_file_opened_from_finder_while_running_opens_a_tab(
        app, window, deliver, rutile_cif):
    deliver(window)
    QCoreApplication.sendEvent(app, QFileOpenEvent(rutile_cif))

    assert window.tabs.count() == 1
    assert len(window.documents) == 1


def test_the_same_file_twice_is_still_one_document(app, window,
                                                   deliver, rutile_cif):
    """Finder will happily send the event again; the document set
    already refuses a second tab over one file and this must not go
    around it."""
    deliver(window)
    for _ in range(2):
        QCoreApplication.sendEvent(app, QFileOpenEvent(rutile_cif))

    assert len(window.documents) == 1


def test_a_url_event_naming_a_local_file_is_opened(app, window,
                                                    deliver, rutile_cif):
    """``file()`` is empty when the event carries a URL instead."""
    deliver(window)
    QCoreApplication.sendEvent(
        app, QFileOpenEvent(QUrl.fromLocalFile(rutile_cif)))

    assert len(window.documents) == 1


def test_a_url_that_is_not_a_local_file_is_ignored(app, window,
                                                   deliver):
    """Nothing this application can open, and not a reason to fail."""
    deliver(window)
    QCoreApplication.sendEvent(
        app, QFileOpenEvent(QUrl("https://example.org/quartz.cif")))

    assert not window.documents
    assert not app.pending


# ======================================================================
#  COLD: THE EVENT ARRIVES FIRST
# ======================================================================

def test_a_file_arriving_before_the_window_is_queued(app, rutile_cif):
    """The bug this whole module exists to prevent: a double-click
    that launches the application delivers its event during start-up,
    and opening it there would open it into nothing."""
    QCoreApplication.sendEvent(app, QFileOpenEvent(rutile_cif))

    assert app.pending == (rutile_cif,)


def test_the_queue_is_released_when_the_window_arrives(
        app, window, deliver, rutile_cif):
    QCoreApplication.sendEvent(app, QFileOpenEvent(rutile_cif))
    deliver(window)

    assert not app.pending
    assert len(window.documents) == 1


def test_everything_queued_is_opened_in_order(app, window, deliver,
                                              tmp_path, rutile,
                                              quartz):
    from xtal.io import write_cif
    paths = []
    for name, structure in (("a", rutile), ("b", quartz)):
        path = tmp_path / f"{name}.cif"
        write_cif(structure, path)
        paths.append(str(path))
        QCoreApplication.sendEvent(app, QFileOpenEvent(str(path)))
    deliver(window)

    # By the entry, not by the path: a file opened from outside is
    # copied into the workspace and the tab follows the copy.  Where
    # each came from is what the order is being checked against.
    assert [d.entry.name for d in window.documents] == ["a", "b"]
    assert [d.structure.meta["source"]
            for d in window.documents] == paths


def test_a_file_arriving_during_delivery_is_delivered_too(
        app, rutile_cif, quartz_cif):
    """Why the queue is popped rather than iterated over a copy.

    Finder sends one event per file when several are opened at once,
    and Qt may deliver the second while the first is still being
    handled -- into a list a loop had already finished with.
    """
    seen = []

    def handler(path):
        seen.append(path)
        if len(seen) == 1:
            app.open_later(quartz_cif)

    app.file_opened.connect(handler)
    try:
        app.open_later(rutile_cif)
        app.start_delivering()
    finally:
        app.file_opened.disconnect(handler)

    assert seen == [rutile_cif, quartz_cif]


# ======================================================================
#  AND THE WINDOW COMES FORWARD
# ======================================================================

def test_opening_from_the_desktop_brings_the_window_forward(
        window, rutile_cif, monkeypatch):
    """Somebody who double-clicked a file is asking to look at it.
    Leaving the structure open behind whatever they clicked from is
    indistinguishable from nothing having happened."""
    raised = []
    monkeypatch.setattr(window, "raise_", lambda: raised.append("raise"))
    monkeypatch.setattr(window, "activateWindow",
                        lambda: raised.append("activate"))
    window.open_from_desktop(rutile_cif)

    assert raised == ["raise", "activate"]


def test_the_command_line_still_opens_a_file(qtbot, tmp_path,
                                             rutile_cif):
    """The other half, unchanged: argv is how Windows associations
    and a cold macOS launch both deliver a path."""
    settings = AppSettings("CrystalBuilderTest", f"Argv{tmp_path.name}")
    settings.clear_window()
    win = MainWindow(viewport_factory=_Stub, settings=settings,
                     paths=[rutile_cif])
    qtbot.addWidget(win)

    assert len(win.documents) == 1
