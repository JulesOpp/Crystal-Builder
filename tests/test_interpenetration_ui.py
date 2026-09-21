"""
The Interpenetrate dialog and its menu entry.

The dialog is built and driven through its methods; ``exec`` is never
called, because the suite patches it to raise (``tests/conftest.py``).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QDialogButtonBox, QWidget  # noqa: E402

from tests.test_interpenetration import pcu  # noqa: E402
from xtalapp.dialogs.interpenetrate import (  # noqa: E402
    InterpenetrateDialog,
)
from xtalapp.document import Document  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Ip{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def _ok(dialog):
    return dialog.buttons.button(QDialogButtonBox.Ok)


def test_the_placement_with_the_most_room_is_offered_first(qtbot):
    """Returning on the dialog as it opens takes the body centre --
    the answer for somebody who wants the one with the most room."""
    dialog = InterpenetrateDialog(Document(pcu()))
    qtbot.addWidget(dialog)
    assert dialog.placement().name == "translation by 1/2, 1/2, 1/2"
    assert _ok(dialog).isEnabled()
    assert "3.46 A apart" in dialog.detail.text()


def test_a_placement_that_collides_cannot_be_chosen(qtbot):
    """Kept in the list with its reason, and the button is off on it,
    rather than being dropped so that the list has nothing to say."""
    dialog = InterpenetrateDialog(Document(pcu()))
    qtbot.addWidget(dialog)
    last = len(dialog.placements) - 1
    assert dialog.placements[last].collides
    dialog.table.setCurrentCell(last, 0)
    assert not _ok(dialog).isEnabled()
    assert "cannot be made" in dialog.detail.text()


def test_a_new_fold_measures_again(qtbot):
    dialog = InterpenetrateDialog(Document(pcu()))
    qtbot.addWidget(dialog)
    dialog.fold.setValue(3)
    assert dialog.placement().fold == 3
    assert dialog.placement().name.startswith("translations by")


def test_a_molecular_crystal_says_why_and_offers_nothing(qtbot,
                                                         dry_ice):
    dialog = InterpenetrateDialog(Document(dry_ice))
    qtbot.addWidget(dialog)
    assert dialog.table.rowCount() == 0
    assert not _ok(dialog).isEnabled()
    assert "only molecules" in dialog.detail.text()


def test_the_menu_entry_interpenetrates_the_tab_in_front(window,
                                                         monkeypatch):
    """Structure > Interpenetrate... reaches the Document through the
    dialog's ``ask``, and the tab in front gets the copies."""
    document = Document(pcu())
    window.add_document(document)
    assert window.actions_["interpenetrate"].isEnabled()

    def answer(doc, parent=None):
        return doc.interpenetrate(doc.interpenetration_candidates(2)[0])

    monkeypatch.setattr(InterpenetrateDialog, "ask",
                        staticmethod(answer))
    window.actions_["interpenetrate"].trigger()
    assert window.current_document().structure.n_sites == 2
