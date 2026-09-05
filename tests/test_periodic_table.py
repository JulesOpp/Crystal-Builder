"""Choosing an element by pointing at it.

Every element chooser in the application was an editable combo, which
answers "carbon" quickly and "the one two along from molybdenum" not at
all.  These tests cover the picture -- that it holds every element in
the right cell -- and the one button that opens it, because a picker
that is right and unreachable is not a picker.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QDialog  # noqa: E402

from xtal.core import elements as el  # noqa: E402
from xtalapp.dialogs.add_atom import AddAtomDialog  # noqa: E402
from xtalapp.widgets import periodic_table as pt  # noqa: E402

# ------------------------------------------------------- the picture

def test_the_table_holds_every_element_once_and_only_once():
    """118 elements, 118 cells.  A symbol left out cannot be picked
    and a symbol written twice is two buttons that disagree."""
    cells = pt.layout_cells()
    symbols = [symbol for symbol, _row, _column in cells]
    assert len(symbols) == len(set(symbols)) == 118
    assert sorted(el.atomic_number(s) for s in symbols) == list(
        range(1, 119))


def test_no_two_elements_share_a_cell():
    """The grid would stack them, and the one underneath would be
    unclickable rather than absent -- which is the failure that does
    not show up in a screenshot."""
    places = [(row, column) for _s, row, column in pt.layout_cells()]
    assert len(places) == len(set(places))


def test_the_table_is_the_shape_the_table_is():
    """Eighteen groups, hydrogen and helium at the two ends of the
    first row, and the f block hanging below rather than stretched
    into the middle of period 6."""
    where = {symbol: (row, column)
             for symbol, row, column in pt.layout_cells()}
    assert where["H"] == (0, 0)
    assert where["He"] == (0, 17)
    assert where["Fe"][1] == 7                  # group 8
    assert where["Ba"][0] == where["Hf"][0] == 5
    assert where["La"][0] == where["Lu"][0] > where["Og"][0]
    assert where["Ac"][0] == where["La"][0] + 1
    assert max(c for _r, c in where.values()) == 17


def test_the_dummy_is_not_in_the_table():
    """``X`` marks a position and is not the 119th element.  Add
    centroid is where a marker comes from."""
    symbols = {s for s, _r, _c in pt.layout_cells()}
    assert not symbols & el.DUMMY_ELEMENTS


# ------------------------------------------------------- the dialog

def test_clicking_an_element_is_the_whole_answer(qtbot):
    """One click picks and closes: the dialog asks one question, and
    an OK button after the click would be a second answer to it."""
    dialog = pt.PeriodicTableDialog(current="C")
    qtbot.addWidget(dialog)
    dialog.buttons["Mo"].click()
    assert dialog.selected() == "Mo"
    assert dialog.result() == QDialog.Accepted


def test_the_table_opens_on_the_element_already_chosen(qtbot):
    """The current element is marked, so the table opens saying where
    you are rather than as 118 equal choices."""
    dialog = pt.PeriodicTableDialog(current="Fe")
    qtbot.addWidget(dialog)
    assert dialog.selected() == "Fe"
    assert "#1a6fd4" in dialog.buttons["Fe"].styleSheet()
    assert "#1a6fd4" not in dialog.buttons["Co"].styleSheet()


def test_every_button_is_drawn_in_the_colour_the_viewport_uses(qtbot):
    """The table is worth having because it looks like the crystal.
    Hydrogen is white and iodine near-black, so the ink has to follow
    the ground or one end of the table is unreadable."""
    dialog = pt.PeriodicTableDialog()
    qtbot.addWidget(dialog)
    assert f"rgb{el.color('Fe')}" in dialog.buttons["Fe"].styleSheet()
    assert "#000000" in dialog.buttons["H"].styleSheet()
    assert "#ffffff" in dialog.buttons["I"].styleSheet()


def test_the_caption_names_the_element_under_the_cursor(qtbot):
    """Two letters is not a name.  Reading the table by symbol alone
    is the thing the picker exists to avoid."""
    dialog = pt.PeriodicTableDialog(current="W")
    qtbot.addWidget(dialog)
    assert "Tungsten" in dialog.caption.text()
    assert "74" in dialog.caption.text()


# -------------------------------------------------------- the button

def test_the_button_writes_the_choice_into_the_field_beside_it(
        qtbot, rutile, monkeypatch):
    """The table fills the combo rather than replacing it, so the
    dialog still has exactly one field holding the answer."""
    dialog = AddAtomDialog(rutile.lattice, element="C")
    qtbot.addWidget(dialog)
    monkeypatch.setattr(pt.PeriodicTableDialog, "ask",
                        classmethod(lambda cls, *a, **k: "Zn"))

    dialog.table.click()
    assert dialog.element.currentText() == "Zn"
    assert dialog.result_values()["element"] == "Zn"


def test_a_cancelled_table_leaves_the_element_alone(
        qtbot, rutile, monkeypatch):
    """Escape has to leave with what the caller already had."""
    dialog = AddAtomDialog(rutile.lattice, element="Ti")
    qtbot.addWidget(dialog)
    monkeypatch.setattr(pt.PeriodicTableDialog, "ask",
                        classmethod(lambda cls, *a, **k: None))

    dialog.table.click()
    assert dialog.element.currentText() == "Ti"


def test_the_button_opens_the_table_where_the_field_already_is(
        qtbot, rutile, monkeypatch):
    """Otherwise the table opens on nothing and the user has to find
    their own element before they can change it."""
    dialog = AddAtomDialog(rutile.lattice, element="Ti")
    qtbot.addWidget(dialog)
    seen = []
    monkeypatch.setattr(
        pt.PeriodicTableDialog, "ask",
        classmethod(lambda cls, parent=None, current="":
                    seen.append(current)))

    dialog.table.click()
    assert seen == ["Ti"]
