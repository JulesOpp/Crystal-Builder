"""Greying one entry of a combo box without touching its item.

``combo.model().item(at)`` hands Python a wrapper for an item Qt made,
and PySide has the model keep that wrapper.  Clearing the combo frees
the item in C++, but shiboken still maps the freed address to the
wrapper; the next object Qt makes at that address -- a QAction from
``menu.addAction(text, callable)`` in the case CI hit -- comes back
to Python as the old QStandardItem."""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QComboBox, QMenu  # noqa: E402

from tests.conftest_qt import item_wrappers  # noqa: E402
from xtalapp.widgets.choices import (  # noqa: E402
    choice_enabled,
    set_choice_enabled,
)


@pytest.fixture
def combo(qtbot):
    made = QComboBox()
    qtbot.addWidget(made)
    made.addItems(["none", "best", "tpt", "sql"])
    return made


def test_a_greyed_choice_reads_greyed_and_the_others_do_not(combo):
    """The entry asked for, and only it, both ways."""
    set_choice_enabled(combo, 2, False)
    assert [choice_enabled(combo, i) for i in range(4)] == [
        True, True, False, True]
    set_choice_enabled(combo, 2, True)
    assert all(choice_enabled(combo, i) for i in range(4))


def test_greying_a_choice_leaves_no_item_wrapper_behind(combo):
    """Each wrapper left behind is an address that, once the combo is
    refilled, can turn the next QAction into a QStandardItem."""
    before = item_wrappers()
    for at in range(combo.count()):
        set_choice_enabled(combo, at, at % 2 == 0)
        choice_enabled(combo, at)
    assert item_wrappers() == before


def test_a_menu_built_after_greyed_choices_are_cleared_has_actions(
        qtbot, combo):
    """The CI failure itself, without the dialog around it: grey,
    clear, refill and rebuild a menu, until the allocator would have
    put an action on a freed entry's address."""
    menu = QMenu()
    qtbot.addWidget(menu)
    for _ in range(50):
        combo.clear()
        combo.addItems([str(i) for i in range(10)])
        for at in range(1, 10, 2):
            set_choice_enabled(combo, at, False)
        combo.clear()
        menu.clear()
        for k in range(5):
            menu.addAction(str(k), lambda: None).setToolTip(str(k))
