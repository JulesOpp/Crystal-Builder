"""Substitution through the window: the context menu on hydrogens, and
Structure > Substitute hydrogens.

Menus are built and read, never popped up, and the dialog is driven
through its methods -- see ``tests/conftest.py``.  What breaks if these
regress is an entry that offers to replace a carbon, or an edit that
takes two Ctrl+Zs to undo.
"""

from collections import Counter
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QDialogButtonBox, QWidget  # noqa: E402

from xtal.build import MISSING  # noqa: E402
from xtal.build import installed as rdkit_installed  # noqa: E402
from xtal.core import p1  # noqa: E402
from xtal.io import FORMATS  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402

pytestmark = pytest.mark.skipif(not rdkit_installed(), reason=MISSING)

SAMPLES = Path(__file__).resolve().parents[1] / "resources" / "samples"


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Sub{tmp_path.name}")
    settings.clear_window()
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


@pytest.fixture
def mof5(window):
    document = window.new_document()
    document.set_structure(FORMATS.read(SAMPLES / "MOF-5.cif"),
                           modified=False)
    return document


def _group_menu(window):
    menu = window.build_context_menu("atom")
    entry = next(a for a in menu.actions()
                 if a.menu() is not None
                 and a.text() == "Replace with &group")
    return entry.menu()


def test_replace_with_group_is_offered_only_on_hydrogens(window, mof5):
    """A submenu that opened on a carbon would offer an edit that could
    only refuse, so it is greyed unless every selected atom is H."""
    elements = mof5.cell.elements
    mof5.select([elements.index("H")])
    assert _group_menu(window).isEnabled()

    mof5.select([elements.index("H"), elements.index("C")])
    assert not _group_menu(window).isEnabled()


def test_replacing_from_the_context_menu_is_one_undo_step(window, mof5):
    hydrogen = mof5.cell.elements.index("H")
    mof5.select([hydrogen])
    amino = next(a for a in _group_menu(window).actions()
                 if a.text() == "Amino")

    amino.trigger()

    assert Counter(mof5.cell.elements)["N"] == 1
    mof5.undo()
    assert "N" not in mof5.cell.elements
    assert not mof5.can_undo


def test_every_ring_needs_no_selection_and_is_one_step(window, mof5,
                                                       qtbot):
    """With nothing selected the dialog offers every ring, says what it
    will do, and MOF-5 becomes IRMOF-3 in one undoable edit."""
    from xtalapp.dialogs.substitute import PER_RING, SubstituteDialog

    dialog = SubstituteDialog(mof5, window)
    qtbot.addWidget(dialog)
    dialog.group.setCurrentText("Amino")

    assert dialog.where.currentText() == PER_RING
    assert "every aromatic ring" in dialog.headline.text()
    assert dialog.buttons.button(QDialogButtonBox.Ok).isEnabled()
    report = dialog.substitute()

    assert report.ok and report.warnings == []
    assert Counter(p1.expand(mof5.structure).elements)["N"] == 24
    mof5.undo()
    assert not mof5.can_undo


def test_the_selected_hydrogens_mode_needs_a_hydrogen(window, mof5,
                                                      qtbot):
    from xtalapp.dialogs.substitute import SELECTED, SubstituteDialog

    mof5.select([mof5.cell.elements.index("C")])
    dialog = SubstituteDialog(mof5, window)
    qtbot.addWidget(dialog)
    dialog.where.setCurrentText(SELECTED)

    assert "select the hydrogens" in dialog.headline.text()
    assert not dialog.buttons.button(QDialogButtonBox.Ok).isEnabled()
