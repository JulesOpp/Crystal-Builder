"""An automated launch closes without asking about unsaved work.

The prompt exists for a person who would otherwise lose edits.  A
screenshot run, a smoke test, or an agent driving the GUI is not that
person: nothing will answer the modal, so the window never closes and
the run hangs until something kills it.  XTAL_NO_CONFIRM_CLOSE says
there is nobody to ask.

The default stays the safe one -- unset means the question is still
asked -- so these tests pin both directions, not just the new one.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QMessageBox, QWidget  # noqa: E402

from xtal.core.structure import Change  # noqa: E402
from xtalapp.document import Document  # noqa: E402
from xtalapp.mainwindow import (  # noqa: E402
    NO_CONFIRM_CLOSE_ENV,
    MainWindow,
    no_confirm_close,
)
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"NoAsk{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


@pytest.fixture
def never_answered(monkeypatch):
    """A QMessageBox.question that fails rather than blocking.

    A modal in a headless run does not raise -- it waits.  Failing
    loudly turns "the suite hung" into "this line asked a question".
    """
    def refuse(*args, **kwargs):
        raise AssertionError("the close prompt was shown")

    monkeypatch.setattr(
        "xtalapp.mainwindow.QMessageBox.question", refuse)


def _a_dirty_document(rutile_cif):
    """A loaded document with one real edit on its undo stack."""
    document = Document.load(rutile_cif)
    document.apply(lambda s: s.set_frac(1, [0.31, 0.31, 0.0]),
                   Change.POSITIONS)
    assert document.modified
    return document


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "ON"])
def test_the_variable_is_read_in_every_spelling_of_true(monkeypatch, value):
    monkeypatch.setenv(NO_CONFIRM_CLOSE_ENV, value)
    assert no_confirm_close() is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", " OFF "])
def test_an_empty_or_falsish_value_leaves_the_prompt_alone(
        monkeypatch, value):
    monkeypatch.setenv(NO_CONFIRM_CLOSE_ENV, value)
    assert no_confirm_close() is False


def test_unset_means_the_user_is_still_asked(monkeypatch):
    monkeypatch.delenv(NO_CONFIRM_CLOSE_ENV, raising=False)
    assert no_confirm_close() is False


def test_a_modified_tab_closes_without_a_question(
        window, rutile_cif, monkeypatch, never_answered):
    monkeypatch.setenv(NO_CONFIRM_CLOSE_ENV, "1")
    window.add_document(_a_dirty_document(rutile_cif))
    before = len(window.documents)

    window.close_document(len(window.documents) - 1)

    assert len(window.documents) == before - 1


def test_the_window_quits_with_unsaved_work_and_no_question(
        window, rutile_cif, monkeypatch, never_answered):
    monkeypatch.setenv(NO_CONFIRM_CLOSE_ENV, "1")
    window.add_document(_a_dirty_document(rutile_cif))

    assert window.close() is True


def test_without_the_variable_a_refused_prompt_keeps_the_tab(
        window, rutile_cif, monkeypatch):
    """The guard must not have quietly deleted the prompt.

    Every test above passes just as happily against a build with no
    confirmation at all, which is the one regression that would lose a
    user's work.  Here the question is asked and answered No, and the
    document has to survive it.
    """
    monkeypatch.delenv(NO_CONFIRM_CLOSE_ENV, raising=False)
    asked = []
    monkeypatch.setattr(
        "xtalapp.mainwindow.QMessageBox.question",
        lambda *a, **k: asked.append(a) or QMessageBox.No)
    window.add_document(_a_dirty_document(rutile_cif))
    before = len(window.documents)

    window.close_document(len(window.documents) - 1)

    assert asked, "the user was never asked about unsaved work"
    assert len(window.documents) == before
