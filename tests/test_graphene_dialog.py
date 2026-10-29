"""The graphene builder's form: xtalapp.dialogs.graphene_build."""

import pytest
from PySide6.QtWidgets import QDialogButtonBox

from xtal.modules import MODULES


@pytest.fixture
def dialog(qtbot):
    from xtalapp.dialogs import module_dialog

    module = MODULES.get("graphene")
    made = module_dialog("graphene-build")(module, module.action("build"))
    qtbot.addWidget(made)
    return made


def _twisted(dialog, angle="1.08"):
    widgets = dialog.form.widgets
    widgets["layers"].setValue(2)
    widgets["stacking"].setCurrentIndex(
        widgets["stacking"].findData("twisted"))
    widgets["twist"].setText(angle)


def test_the_twist_is_greyed_until_the_stacking_is_twisted(dialog):
    assert not dialog.form.widgets["twist"].isEnabled()
    assert not dialog.twists.isEnabled() and dialog.twists.count() == 0
    assert dialog.size.text() == "Graphene, one layer: 2 atoms."
    _twisted(dialog)
    assert dialog.form.widgets["twist"].isEnabled()
    assert dialog.twists.isEnabled()


def test_the_list_offers_the_twists_near_the_one_typed_with_their_atoms(
        dialog):
    """The magic angle is chosen in a list of its neighbours, each
    with its count, and the readout names what will be built."""
    _twisted(dialog)
    assert dialog.twists.count() == 8
    assert dialog.twists.currentText() == \
        "1.08°, (m, r) = (30, 1): 11,164 atoms"
    assert dialog.size.text() == \
        "1.08° twisted bilayer graphene: 11,164 atoms."
    assert dialog.buttons.button(QDialogButtonBox.Ok).isEnabled()


def test_an_angle_written_in_deg_still_lists_its_neighbours(dialog):
    """The build reads "1.08 deg"; the list stripped only the degree
    sign and went blank over an angle that builds."""
    _twisted(dialog, "1.08 deg")
    assert dialog.twists.count() == 8
    assert dialog.twists.currentText().startswith("1.08°, (m, r) = "
                                                   "(30, 1)")


def test_choosing_a_twist_writes_its_angle_into_the_box(dialog):
    _twisted(dialog)
    index = dialog.twists.findData("1.05")
    dialog.twists.activated.emit(index)
    assert dialog.values()["twist"] == "1.05"
    assert "1.05° twisted" in dialog.size.text()


def test_only_twists_under_the_size_limit_are_listed(dialog):
    """At 0.2 degrees the cell is over the hard limit: Build greys,
    the readout names the nearest that fits, and nothing over the
    limit is offered."""
    _twisted(dialog, "0.2")
    assert not dialog.buttons.button(QDialogButtonBox.Ok).isEnabled()
    assert "nearest twist that fits" in dialog.size.text()
    counts = [int(dialog.twists.itemText(k).split(": ")[1]
                  .split()[0].replace(",", ""))
              for k in range(dialog.twists.count())]
    assert counts and max(counts) <= 200_000


def test_an_angle_nothing_is_near_greys_build_saying_why(dialog):
    _twisted(dialog, "59.9")
    assert not dialog.buttons.button(QDialogButtonBox.Ok).isEnabled()
    assert "the nearest is 59.80" in dialog.size.text()
