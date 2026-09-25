"""
The Prepare for simulation dialog and its menu entry.

The dialog is built and driven through its methods; ``exec`` is never
called, because the suite patches it to raise (``tests/conftest.py``).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QDialogButtonBox, QWidget  # noqa: E402

from tests.test_prepare import _read  # noqa: E402
from xtal.core import p1  # noqa: E402
from xtalapp.dialogs.prepare import PrepareDialog  # noqa: E402
from xtalapp.document import Document  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Prep{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def _ok(dialog):
    return dialog.buttons.button(QDialogButtonBox.Ok)


def test_the_dialog_says_what_is_wrong_and_what_each_step_would_do(
        qtbot):
    dialog = PrepareDialog(Document(_read("MIL-88B")))
    qtbot.addWidget(dialog)
    assert "partially occupied" in dialog.found.text()
    assert "-> 110 atoms" in dialog.headline.text()
    assert "24 on arene rings" in dialog.detail.toPlainText()
    assert _ok(dialog).isEnabled()


def test_a_step_unticked_is_left_out_of_the_preview(qtbot):
    dialog = PrepareDialog(Document(_read("MIL-88B")))
    qtbot.addWidget(dialog)
    dialog.boxes["hydrogens"].setChecked(False)
    assert "arene rings" not in dialog.detail.toPlainText()
    assert "-> 86 atoms" in dialog.headline.text()


def test_completing_the_trimers_is_offered_unticked(qtbot):
    """It adds ligands the refinement never located; nobody should get
    them for pressing Prepare."""
    dialog = PrepareDialog(Document(_read("MIL-88B")))
    qtbot.addWidget(dialog)
    assert not dialog.boxes["cap"].isChecked()
    assert all(box.isChecked() for step, box in dialog.boxes.items()
               if step != "cap")


def test_the_dialog_warns_whichever_way_the_trimers_go(qtbot):
    """Left alone the cell is charged; completed, its chemistry is not
    the file's.  Either is a warning before Prepare is pressed."""
    dialog = PrepareDialog(Document(_read("MIL-88B")))
    qtbot.addWidget(dialog)
    assert not dialog.caution.isHidden()
    assert "not neutral" in dialog.caution.text()
    dialog.boxes["cap"].setChecked(True)
    assert "-> 120 atoms" in dialog.headline.text()
    assert "changes the chemistry" in dialog.caution.text()
    assert "2 OH and 4 water" in dialog.caution.text()


def test_a_framework_without_trimers_has_no_caution(qtbot):
    dialog = PrepareDialog(Document(_read("UiO-66")))
    qtbot.addWidget(dialog)
    assert dialog.caution.isHidden()


def test_nothing_to_prepare_cannot_be_pressed(qtbot, quartz):
    dialog = PrepareDialog(Document(quartz))
    qtbot.addWidget(dialog)
    assert dialog.headline.text() == "nothing to prepare"
    assert "no deuterium" in dialog.detail.toPlainText()
    assert not _ok(dialog).isEnabled()


def test_the_whole_preparation_is_one_undo_step():
    """Undoing half of it would leave a cell nobody chose."""
    document = Document(_read("MIL-88B"))
    before = p1.expand(document.structure).n_atoms
    report = document.prepare_for_simulation(("disorder", "solvent",
                                              "cap", "hydrogens"))
    assert report.ok
    assert p1.expand(document.structure).n_atoms == 120
    document.undo()
    assert p1.expand(document.structure).n_atoms == before


def test_the_menu_entry_prepares_the_tab_in_front(window, monkeypatch):
    document = Document(_read("MIL-88B"))
    window.add_document(document)
    assert window.actions_["prepare_simulation"].isEnabled()
    monkeypatch.setattr(
        PrepareDialog, "ask",
        staticmethod(lambda doc, parent=None:
                     doc.prepare_for_simulation(("disorder",))))
    window.actions_["prepare_simulation"].trigger()
    assert all(s.occupancy == 1.0
               for s in window.current_document().structure.sites)
    assert "prepared for simulation" in \
        window.statusBar().currentMessage()
