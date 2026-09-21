"""The net picker: finding one of 2926 nets by something you know.

The dialog exists because the generated form for
:data:`xtal.modules.net.PARAMS` is a text box you have to already know
the answer to type into.  What these assert is the searching, not the
drawing -- ``tests/test_net_drawing.py`` is the geometry.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt  # noqa: E402

from xtal.build import topology  # noqa: E402
from xtal.modules import MODULES  # noqa: E402
from xtalapp.dialogs.net_draw import NetDrawDialog  # noqa: E402


@pytest.fixture
def dialog(qtbot):
    module = MODULES.get("net")
    made = NetDrawDialog(module, module.action("draw"))
    qtbot.addWidget(made)
    return made


def showing(dialog) -> list[str]:
    return [dialog.nets.item(i).data(Qt.UserRole)
            for i in range(dialog.nets.count())
            if not dialog.nets.item(i).isHidden()]


def test_the_net_picker_offers_every_drawable_net(dialog):
    """A text box you have to already know the answer to type into is
    only usable by somebody who did not need it: 2926 names of three
    letters each, and no mnemonic among them."""
    assert dialog.nets.count() == len(topology.names())


def test_the_search_matches_a_group_number_and_a_coordination(dialog):
    """What somebody knows is rarely the name.  More often it is "the
    4-coordinate ones" or a space group, so every row carries both."""
    dialog.search.number.setText("225")
    cubic = showing(dialog)
    assert "fcu" in cubic and len(cubic) < dialog.nets.count()

    dialog.search.number.setText("")
    dialog.search.coordination.setText("4")
    dialog.search.exclusive.setChecked(True)
    four = showing(dialog)
    assert "sod" in four and "pcu" not in four   # pcu is 6-coordinate

    dialog.search.coordination.setText("")
    assert len(showing(dialog)) == dialog.nets.count()


def test_the_net_builder_lists_layers_and_can_leave_them_out(dialog):
    """The 200 layers were refused until 2026-09-21; now they are
    drawn, and the 2D box is how to not see them."""
    assert "hcb" in showing(dialog)
    assert dialog.two_d.text() == "2D (200)"
    dialog.two_d.setChecked(False)
    assert "hcb" not in showing(dialog) and "pcu" in showing(dialog)


def test_a_layer_gets_a_picture_and_says_its_plane_group(dialog):
    assert dialog._select("kgm")
    assert dialog.preview._drawing is not None
    assert "Plane group p6mm" in dialog.details.text()
    assert dialog.values()["net"] == "kgm"


def test_a_transitivity_search_finds_the_two_kinds_of_edge(dialog):
    dialog.search.transitivity.setText("2 2")
    dialog.two_d.setChecked(True)
    found = showing(dialog)
    assert "mcm" in found and "hcb" not in found


def test_the_picker_returns_the_net_it_is_showing(dialog):
    """The list answers the ``net`` parameter, so the generated form
    must not also ask about it -- two controls for one value is two
    places for them to disagree."""
    assert dialog._select("sod")
    assert dialog.values()["net"] == "sod"
    assert "net" not in dialog.form.widgets


def test_the_picker_opens_on_the_net_it_was_given(qtbot):
    """Running the action a second time comes back to what was run
    last, which is what ``initial`` is for."""
    module = MODULES.get("net")
    made = NetDrawDialog(module, module.action("draw"),
                         initial={"net": "dia", "beads": 6})
    qtbot.addWidget(made)
    assert made.values() == {"net": "dia", "scale": topology.SCALE,
                             "beads": 6}


def test_a_chosen_net_gets_a_picture_and_its_numbers(dialog):
    """The preview is the MOF builder's own widget, reached through a
    nine-line adapter rather than a second net renderer."""
    assert dialog._select("sod")
    assert dialog.preview._drawing is not None
    assert "Im-3m" in dialog.details.text()


def test_the_dialog_is_reachable_by_the_name_the_action_gives():
    """A module names a dialog and cannot import one, so the name has
    to resolve -- and in a frozen bundle it only resolves if
    ``dialog_modules`` names the module for PyInstaller too."""
    from xtalapp.dialogs import (
        dialog_actions,
        dialog_modules,
        module_dialog,
    )
    assert module_dialog("net-draw") is NetDrawDialog
    assert "net-draw" in dialog_actions()
    assert "xtalapp.dialogs.net_draw" in dialog_modules()
