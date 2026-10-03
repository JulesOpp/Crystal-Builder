"""The polymer builder's dialog: xtalapp.dialogs.polymer_build."""

from __future__ import annotations

import pytest

from xtal.build import MISSING, installed
from xtal.modules import MODULES

pytestmark = pytest.mark.skipif(not installed(), reason=MISSING)


@pytest.fixture
def dialog(qtbot):
    from xtalapp.dialogs.polymer_build import PolymerBuildDialog

    module = MODULES.get("polymer")
    made = PolymerBuildDialog(module, module.action("build"))
    qtbot.addWidget(made)
    return made


def _type(dialog, name, text) -> None:
    """Text into a monomer box, resolved at once rather than after the
    pause."""
    row = dialog.rows[name]
    row.box.setText(text)
    row.resolve()


def _choose(dialog, **values) -> None:
    for form in dialog.forms.values():
        mine = {k: v for k, v in values.items() if k in form.widgets}
        if mine:
            form.set_values(mine)


def test_the_library_monomer_resolves_and_build_is_enabled(dialog):
    """Polyethylene by default: its formula in the row's footer, and an
    estimate of the model's size under the form."""
    row = dialog.rows["monomer"]

    assert row.monomer is not None
    assert "C2H4" in row.footer.text()
    assert "no tacticity" in row.footer.text()
    assert dialog.build_button.isEnabled()
    assert "atoms" in dialog.readout.text()


def test_a_smiles_without_a_tail_disables_build_with_a_reason(dialog):
    """One connection point is a capped molecule, not a repeat unit:
    the sentence the run would fail with is said before it, and Build
    cannot be pressed."""
    _type(dialog, "monomer", "[*:1]CC")

    assert dialog.rows["monomer"].monomer is None
    assert not dialog.build_button.isEnabled()
    assert "Monomer A" in dialog.readout.text()
    assert "connection point" in dialog.readout.text()

    _type(dialog, "monomer", "[*:1]CC[*:2]")
    assert dialog.build_button.isEnabled()


def test_choosing_a_library_entry_writes_its_name(dialog):
    """The name and not the string, so the tab and the report say
    Polystyrene."""
    row = dialog.rows["monomer"]
    index = row.library.findText("Polystyrene")
    row.library.setCurrentIndex(index)

    assert row.text() == "Polystyrene"
    assert row.monomer is not None and row.monomer.handed


def test_membrane_fields_follow_the_periodicity_choice(dialog):
    """Thickness and vacuum mean nothing to a bulk box, so they are off
    until a membrane is chosen, and off again after."""
    assert not dialog.widget("thickness").isEnabled()
    assert not dialog.widget("vacuum").isEnabled()
    _choose(dialog, periodic="membrane")
    assert dialog.widget("thickness").isEnabled()
    assert dialog.widget("vacuum").isEnabled()
    _choose(dialog, periodic="bulk")
    assert not dialog.widget("thickness").isEnabled()


def test_the_second_monomer_is_used_only_by_a_copolymer(dialog):
    """B is off for a homopolymer; an alternating copolymer with no B
    cannot be built, and one with B can."""
    assert not dialog.rows["monomer_b"].isEnabled()
    _choose(dialog, composition="alternating")

    assert dialog.rows["monomer_b"].isEnabled()
    assert not dialog.build_button.isEnabled()
    _type(dialog, "monomer_b", "PVC")
    assert dialog.build_button.isEnabled()


def test_a_recipe_over_the_atom_limit_is_refused_in_the_dialog(dialog):
    _choose(dialog, chains=200, length=1000)

    assert not dialog.build_button.isEnabled()
    assert "over the" in dialog.readout.text()


def test_the_dialog_values_become_the_module_params(dialog):
    """What the dialog hands back is exactly the action's parameters,
    coerced, with what was typed and chosen in them -- the contract
    every module dialog keeps."""
    _type(dialog, "monomer", "PMMA")
    _choose(dialog, chains=4, length=12, density=1.18,
            tacticity="syndiotactic", periodic="membrane",
            thickness=25.0)
    values = dialog.values()
    action = MODULES.get("polymer").action("build")

    assert set(values) == {p.name for p in action.params}
    assert values["monomer"] == "PMMA"
    assert (values["chains"], values["length"]) == (4, 12)
    assert values["density"] == pytest.approx(1.18)
    assert values["tacticity"] == "syndiotactic"
    assert values["periodic"] == "membrane"
    assert values["thickness"] == pytest.approx(25.0)


def test_the_dialog_is_found_by_the_name_the_action_gives(dialog):
    """The mapping is how a frozen build finds the module: a missing
    entry is a ModuleNotFoundError only the shipped app would see."""
    from xtalapp.dialogs import _BY_NAME

    action = MODULES.get("polymer").action("build")
    assert action.dialog in _BY_NAME
    assert _BY_NAME[action.dialog][1] == type(dialog).__name__


def test_an_answered_dialog_is_deleted_on_the_gui_thread(qtbot,
                                                         monkeypatch):
    """After ``exec`` PySide hands the dialog to Python, and the rows'
    callbacks hold it in a cycle, so only the cyclic collector frees
    it -- which ran on the build's worker thread, destroyed the
    canvases off the GUI thread and segfaulted the default build."""
    import shiboken6
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QDialog, QWidget

    from xtalapp.dialogs.polymer_build import PolymerBuildDialog

    window = QWidget()
    qtbot.addWidget(window)
    made = []

    def answer(self):
        made.append(self)
        return QDialog.Accepted

    monkeypatch.setattr(PolymerBuildDialog, "exec", answer)
    module = MODULES.get("polymer")
    values = PolymerBuildDialog.ask(module, module.action("build"),
                                    window)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    assert values["monomer"]
    assert not shiboken6.isValid(made[0])
