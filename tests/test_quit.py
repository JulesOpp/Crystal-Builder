"""Quit asks about unsaved work, including from over a dialog.

Cmd-Q is not a close.  It is delivered to the application object, so
``MainWindow.closeEvent`` -- which is where the question about unsaved
work has always lived -- is not on the path at all when the desktop
sends one, and the dialog a user happened to have open is a modal
holding the keyboard in front of anything asked from underneath it.
Both together are a quit that appears not to ask and loses the edits.

So the question moved out of ``closeEvent`` into ``may_discard_unsaved``
and both routes call it, the dialogs in front are dismissed first, and
the answer is remembered for the close the quit causes so that nobody
is asked the same question twice.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QDialog, QMessageBox, QWidget  # noqa: E402

from xtal.core.structure import Change  # noqa: E402
from xtalapp.document import Document  # noqa: E402
from xtalapp.mainwindow import (  # noqa: E402
    NO_CONFIRM_CLOSE_ENV,
    MainWindow,
)
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    """A window that asks -- the suite's own guard is dropped here.

    Every test in this file is *about* the prompt, so
    XTAL_NO_CONFIRM_CLOSE has to go, and ``QMessageBox.question`` is
    patched by each test rather than reaching a modal nobody answers.
    """
    monkeypatch.delenv(NO_CONFIRM_CLOSE_ENV, raising=False)
    settings = AppSettings("CrystalBuilderTest", f"Quit{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    # Shown, because "the window is still there" is what a refused
    # quit has to be checked by, and a window that was never shown is
    # invisible whatever the quit did.
    win.show()
    return win


@pytest.fixture
def answers(monkeypatch):
    """Record what was asked, and answer it.

    The answer is what the list is set to; the questions are what the
    test reads back.  ``QMessageBox.question`` is patched on the class,
    which is the one the window holds too.
    """
    class Asked(list):
        answer = QMessageBox.Yes

    asked = Asked()
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *a, **k: asked.append(a) or asked.answer)
    return asked


def _dirty(window, rutile_cif):
    """A loaded document in the window with one real edit on it."""
    document = Document.load(rutile_cif)
    document.apply(lambda s: s.set_frac(1, [0.31, 0.31, 0.0]),
                   Change.POSITIONS)
    window.add_document(document)
    assert document.modified
    return document


def _modal(qtbot, window):
    """A dialog in front of the window, as a user would have one.

    Shown rather than ``exec``-ed: the suite patches ``QDialog.exec``
    to raise, and the modality is what these tests are about, not the
    nested event loop underneath it.
    """
    dialog = QDialog(window)
    dialog.setModal(True)
    qtbot.addWidget(dialog)
    dialog.show()
    return dialog


# ======================================================================
#  THE QUESTION IS ASKED
# ======================================================================

def test_quitting_over_a_dialog_still_asks_about_unsaved_work(
        window, qtbot, rutile_cif, answers):
    """The bug: the dialog was in front, the question was behind it,
    and the edits went with the quit."""
    document = _dirty(window, rutile_cif)
    _modal(qtbot, window)
    answers.answer = QMessageBox.No

    window.request_quit()

    assert answers, "the user was never asked about unsaved work"
    assert document in window.documents
    assert window.isVisible()


def test_the_dialog_in_front_is_closed_before_the_question(
        window, qtbot, rutile_cif, monkeypatch):
    """A question raised behind a modal is one nobody can answer, so
    what matters is not that it was asked but that it was reachable
    when it was."""
    _dirty(window, rutile_cif)
    dialog = _modal(qtbot, window)
    from PySide6.QtWidgets import QApplication
    on_top = []
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *a, **k: on_top.append(QApplication.activeModalWidget())
        or QMessageBox.No)

    window.request_quit()

    assert on_top == [None]
    assert not dialog.isVisible()


def test_a_refused_quit_keeps_the_window_and_the_edits(
        window, rutile_cif, answers):
    document = _dirty(window, rutile_cif)
    answers.answer = QMessageBox.No

    window.request_quit()

    assert document.modified
    assert len(window.documents) == 1
    assert window.isVisible()


def test_the_same_question_is_not_asked_twice(window, rutile_cif,
                                              answers):
    """The quit asks, and the close it causes must not ask again --
    the documents are still modified when ``closeEvent`` runs."""
    _dirty(window, rutile_cif)
    answers.answer = QMessageBox.Yes

    window.request_quit()

    assert len(answers) == 1
    assert not window.isVisible()


def test_a_quit_with_nothing_unsaved_asks_nothing(window, rutile_cif,
                                                  answers):
    window.open_path(rutile_cif)

    window.request_quit()

    assert not answers
    assert not window.isVisible()


# ======================================================================
#  THE DESKTOP'S OWN QUIT
# ======================================================================

def test_the_application_asks_its_guard_before_quitting(qapp):
    """Cmd-Q arrives here and nowhere else."""
    qapp.reset()
    try:
        qapp.guard_quit(lambda: False)
        assert qapp.may_quit() is False
        qapp.guard_quit(lambda: True)
        assert qapp.may_quit() is True
    finally:
        qapp.reset()


def test_an_unguarded_application_quits_as_it_always_did(qapp):
    """A window is what sets the guard; a run that has none -- the
    selftest, a test holding a bare application -- must not be stopped
    from quitting by a guard that was never there."""
    qapp.reset()
    assert qapp.may_quit() is True


@pytest.mark.parametrize("kind", [QEvent.Type.Quit, QEvent.Type.Close])
def test_a_refused_quit_event_is_swallowed_and_ignored(qapp, kind):
    """Both spellings of "the desktop wants us gone", and both halves
    of refusing one: macOS's terminate reads the answer back off the
    event, so swallowing it without ignoring it quits anyway."""
    qapp.reset()
    try:
        qapp.guard_quit(lambda: False)
        event = QEvent(kind)

        assert QCoreApplication.sendEvent(qapp, event) is True
        assert not event.isAccepted()
    finally:
        qapp.reset()
