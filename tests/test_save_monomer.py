"""Structure > Building blocks > Save as a monomer, and the polymer
builder's library reading what it wrote."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QWidget  # noqa: E402

from xtal.build import MISSING, from_smiles, installed  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402

pytestmark = pytest.mark.skipif(not installed(), reason=MISSING)


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Mono{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def _drawn(window, smiles):
    document = window.new_document()
    document.paste(from_smiles(smiles).to_fragment())
    return document


def test_save_as_monomer_is_disabled_without_two_connection_points(
        window):
    """Greyed with the count as the reason: a monomer is a head and a
    tail, and a dialog that opened only to say so is a dismissal."""
    action = window.actions_["save_monomer"]

    _drawn(window, "O")
    assert not action.isEnabled()
    assert "this has 0" in action.toolTip()

    _drawn(window, "[*:1]c1ccc([*:2])cc1[*:3]")
    assert not action.isEnabled()
    assert "this has 3" in action.toolTip()

    _drawn(window, "[*:1]CC([*:2])c1ccccc1")
    assert action.isEnabled()
    assert "polymer builder" in action.toolTip()


def test_a_saved_monomer_appears_in_the_polymer_dialog(
        window, qtbot, monkeypatch):
    """The whole of the path: drawn, saved to the workspace, and then
    offered by the polymer builder with nothing further clicked."""
    from xtal.modules import MODULES
    from xtalapp.dialogs.polymer_build import PolymerBuildDialog
    from xtalapp.dialogs.save_monomer import SaveMonomerDialog

    document = _drawn(window, "[*:1]CC([*:2])c1ccccc1")
    target = window.workspace.monomers / "PS-mine.xyz"
    monkeypatch.setattr(
        SaveMonomerDialog, "ask",
        classmethod(lambda cls, structure, folder, parent=None:
                    (folder / "PS-mine.xyz", None)))
    window.actions_["save_monomer"].trigger()
    assert target.exists()
    assert "polymer builder" in window.status_label.text()
    assert document.structure.n_sites                # untouched

    module = MODULES.get("polymer")
    dialog = PolymerBuildDialog(module, module.action("build"), window)
    qtbot.addWidget(dialog)
    row = dialog.rows["monomer"]
    index = row.library.findText("PS-mine (this workspace)")
    assert index > 0
    row.library.setCurrentIndex(index)

    assert row.monomer is not None
    assert row.monomer.formula == "C8H8"
    assert dialog.build_button.isEnabled()


def test_the_save_dialog_refuses_with_the_builders_sentence(qtbot,
                                                           tmp_path):
    """The footer is the reader's verdict, so what the dialog refuses
    is what the polymer builder would have failed with."""
    from xtalapp.dialogs.save_monomer import SaveMonomerDialog

    structure = from_smiles("[*:1]CC([*:2])c1ccccc1").to_structure()
    dialog = SaveMonomerDialog(structure, tmp_path)
    qtbot.addWidget(dialog)
    dialog.name.setText("PS")
    assert dialog.ok_button.isEnabled()
    assert dialog.head.count() == 2

    dialog.name.setText("")
    assert not dialog.ok_button.isEnabled()
    assert "needs a name" in dialog.summary.text()
