"""Modules > MOF builder > Build a rod framework: its own dialog.

The rods listed by their chemistry, the linker picked or drawn rather
than typed, and the rhombus angle's empty box showing in grey the
angle a build would use."""

import shutil
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QWidget

from xtal.modules import MODULES
from xtal.mof import rodbuild
from xtal.mof.catalog import database_root
from xtal.mof.rodbuild import RodRequest
from xtalapp.dialogs.rod_build import FITTING, RodBuildDialog
from xtalapp.mainwindow import MainWindow
from xtalapp.settings import AppSettings


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"RodB{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


@pytest.fixture
def dialog(qtbot, window):
    module, action = MODULES.find("mof.rod")
    made = RodBuildDialog(module, action, window)
    qtbot.addWidget(made)
    return made


def _fitted(qtbot, dialog):
    qtbot.waitUntil(lambda: dialog.angle.placeholderText()
                    not in ("", FITTING), timeout=60000)


def test_rods_are_listed_by_their_chemistry(dialog):
    """MIL-53's hydroxides trans, MOF-303's cis: the name a person
    reads is the rod's, and the value is still the file's key."""
    labels = {dialog.rod.itemData(i): dialog.rod.itemText(i)
              for i in range(dialog.rod.count())}
    assert labels["MIL-53_Al"] == "Al(OH)(O2CR)2-trans"
    assert labels["MOF-303_Al"] == "Al(OH)(O2CR)2-cis"
    assert labels["Ni2Cl2BTDD_Ni"] == "Ni2Cl2(bta)2"
    assert labels["MOF-74_Zn"] == "MOF-74 SBU (Zn)"


def test_the_angle_placeholder_is_the_angle_a_build_would_use(
        qtbot, dialog):
    """Left empty, the build fits the angle; the grey number is that
    fit, worked out before Build is pressed, with the cell under it."""
    _fitted(qtbot, dialog)
    shown = float(dialog.angle.placeholderText().split()[0])
    built = rodbuild.build(RodRequest("MIL-53_Cr", "sql"))
    assert shown == pytest.approx(built.placement.gamma, abs=0.05)
    assert dialog.angle.text() == ""
    assert dialog.values()["angle"] == ""
    assert "Predicted cell" in dialog.summary.text()

    dialog.pattern.setCurrentIndex(dialog.pattern.findData("hcb"))
    assert not dialog.angle.isEnabled()


def test_a_rod_with_no_hand_has_no_hands_to_choose(dialog):
    """MIL-53 is straight; Ni2Cl2BTDD's helices alternate or not, and
    on a pattern with triangles they cannot alternate."""
    assert not dialog.hands.isEnabled()
    dialog.rod.setCurrentIndex(dialog.rod.findData("Ni2Cl2BTDD_Ni"))
    assert dialog.hands.isEnabled()
    dialog.pattern.setCurrentIndex(dialog.pattern.findData("hxl"))
    assert not dialog.hands.model().item(2).isEnabled()


def test_the_linker_is_the_rods_own_unless_another_is_picked(dialog):
    assert dialog.linker.currentText() == "The rod's own (BDC)"
    assert dialog.values()["linker"] == ""
    names = [dialog.linker.itemData(i)
             for i in range(dialog.linker.count())]
    assert {"BDC", "dobdc", "BTDD", "pzdc"} <= set(names)
    dialog.linker_search.setText("pzdc")
    assert [dialog.linker.itemData(i)
            for i in range(dialog.linker.count())] == ["", "pzdc"]


@pytest.mark.skipif(database_root() is None,
                    reason="the vendored PORMAKE database is missing")
def test_the_linker_can_be_drawn_and_is_then_chosen(dialog, monkeypatch):
    """Drawn with the MOF builder's own sketcher, written into the
    workspace's blocks, and in the box with nothing further clicked."""
    from xtalapp.dialogs.draw_block import DrawBlockDialog

    asked = {}

    def draw(cls, slot, folder, parent=None):
        asked["slot"] = slot
        target = dialog.blocks / "mine.xyz"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(database_root() / "bbs" / "E14.xyz", target)
        return target

    monkeypatch.setattr(DrawBlockDialog, "ask", classmethod(draw))
    dialog.draw.click()
    assert asked["slot"].coordination == 2
    assert dialog.linker_name() == "mine"
    assert "this workspace" in dialog.linker.currentText()
    assert dialog.values()["linker"] == "mine"
    assert isinstance(asked["slot"], SimpleNamespace)


def test_a_rod_framework_offers_no_interpenetration(dialog):
    """Rods joined on every side fill the plane across them: nothing
    threads through, so neither the dialog nor the request asks."""
    _module, action = MODULES.find("mof.rod")
    assert "interpenetration" not in {p.name for p in action.params}
    assert "interpenetration" not in dialog.values()
    with pytest.raises(TypeError):
        RodRequest.parse("MIL-53_Cr", "sql", interpenetration=2)


def test_the_rod_and_linker_are_drawn_as_the_mof_builder_draws_a_block(
        dialog):
    """The MOF builder's own picture beside each row: the rod as two
    repeats with every connection point a ring, its formula one
    repeat's, and the linker the one a build would take."""
    from xtal.mof import rod as rods
    from xtalapp.dialogs.mof_preview import BlockPreview

    assert isinstance(dialog.rod_preview, BlockPreview)
    assert isinstance(dialog.linker_preview, BlockPreview)
    shipped = rods.Rod.read(rods.shipped()["MIL-53_Cr"])
    drawn = dialog.rod_preview._block
    assert len(drawn.connections) == 2 * len(shipped.connections)
    assert drawn.formula == "C4Cr2H2O10"
    assert dialog.rod_preview._caption.startswith("Cr(OH)(O2CR)2-trans")
    assert dialog.linker_preview._caption == "BDC  ·  C6H4"

    dialog.linker.setCurrentIndex(dialog.linker.findData("pzdc"))
    assert dialog.linker_preview._caption.startswith("pzdc")
    dialog.rod.setCurrentIndex(dialog.rod.findData("MOF-74_Zn"))
    assert dialog.rod_preview._caption.startswith("MOF-74 SBU (Zn)")


def test_build_is_greyed_for_what_cannot_be_built(qtbot, dialog):
    """MOF-74's rod has three faces a repeat and sql four neighbours:
    said under the form, and Build is not offered."""
    dialog.rod.setCurrentIndex(dialog.rod.findData("MOF-74_Zn"))
    qtbot.waitUntil(lambda: "cannot be built" in dialog.summary.text(),
                    timeout=60000)
    assert not dialog.build_button.isEnabled()
    dialog.pattern.setCurrentIndex(dialog.pattern.findData("hcb"))
    qtbot.waitUntil(lambda: "Predicted cell" in dialog.summary.text(),
                    timeout=60000)
    assert dialog.build_button.isEnabled()
