"""The disordered-carbon builder's dialog: xtalapp.dialogs.carbon_build."""

import pytest
from PySide6.QtWidgets import QDialogButtonBox

from xtal.modules import MODULES
from xtalapp.dialogs import module_dialog
from xtalapp.dialogs.carbon_build import GROUPS, CarbonBuildDialog


@pytest.fixture
def dialog(qtbot):
    module = MODULES.get("carbon")
    made = CarbonBuildDialog(module, module.action("build"),
                             initial={"repeat": "1x1x1"})
    qtbot.addWidget(made)
    return made


def _widget(dialog, name):
    for form in dialog.forms.values():
        if name in form.widgets:
            return form.widgets[name]
    raise KeyError(name)


def test_the_readout_says_what_the_nets_shape_fixes(dialog):
    """dia's cell: chi -16, so 96 more heptagon-equivalents than
    pentagons, said before anything is built.  A repeat multiplies
    it."""
    assert "chi -16" in dialog.readout.text()
    assert "96 more heptagon" in dialog.readout.text()
    _widget(dialog, "repeat").setText("2x2x2")
    assert "768 more heptagon" in dialog.readout.text()


def test_a_net_that_cannot_be_built_on_greys_out_build(dialog):
    """A layer net, or a name the RCSR does not have, is said in the
    readout and Build cannot be pressed."""
    build = dialog.buttons.button(QDialogButtonBox.Ok)
    _widget(dialog, "net").setText("hcb")
    assert not build.isEnabled()
    assert "3-periodic" in dialog.readout.text()
    _widget(dialog, "net").setText("srs")
    assert build.isEnabled()
    assert "chi -8" in dialog.readout.text()


def test_every_parameter_is_in_one_group_and_comes_back(dialog):
    """Nothing the module declares is lost between the groups, and the
    values come back in the module's own types."""
    grouped = [n for _title, names in GROUPS for n in names]
    declared = [p.name for p in MODULES.get("carbon").action(
        "build").params]
    assert sorted(grouped) == sorted(declared)
    values = dialog.values()
    assert values["repeat"] == "1x1x1"
    assert values["net"] == "dia"
    assert isinstance(values["layers"], int)


def test_the_frozen_build_can_find_the_dialog():
    """The mapping is how a PyInstaller build imports it."""
    assert module_dialog("carbon-build") is CarbonBuildDialog
