"""The search widget both net lists share.

Tested over a bare list of real RCSR rows rather than through either
dialog, because what it promises is the same in both: a field it
cannot read is marked and changes nothing, and the boxes and the
fields both apply.  The dialogs' own tests check it is wired in.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QListWidget  # noqa: E402

from xtal.analysis import rcsr  # noqa: E402
from xtal.analysis.netsearch import facts_of_entry  # noqa: E402
from xtalapp.widgets.net_search import (  # noqa: E402
    NAME_ROLE,
    NetSearch,
    add_row,
)

NAMES = ("pcu", "dia", "sod", "pyr", "hcb", "sql", "kgm", "mcm")


@pytest.fixture
def search(qtbot):
    widget = NetSearch()
    qtbot.addWidget(widget)
    nets = QListWidget()
    qtbot.addWidget(nets)
    for name in NAMES:
        entry = rcsr.nets()[name]
        add_row(nets, name, facts_of_entry(entry), entry.dimension == 2)
    widget.count(nets)
    widget.changed.connect(lambda: widget.narrow(nets))
    widget.list = nets
    return widget


def shown(search) -> list[str]:
    nets = search.list
    return [nets.item(i).data(NAME_ROLE) for i in range(nets.count())
            if not nets.item(i).isHidden()]


def test_the_boxes_count_each_kind(search):
    assert search.three_d.text() == "3D (4)"
    assert search.two_d.text() == "2D (4)"


def test_typing_a_coordination_hides_nets_without_it(search):
    search.coordination.setText("3")
    assert shown(search) == ["pyr", "hcb", "mcm"]


def test_exclusive_narrows_what_coordination_alone_listed(search):
    search.coordination.setText("3")
    search.exclusive.setChecked(True)
    assert shown(search) == ["hcb"]


def test_a_bad_transitivity_turns_its_field_red_and_keeps_the_list(
        search):
    """An empty list would say no net is like that; the typing is
    what was wrong, and the list stays as the last query left it."""
    search.coordination.setText("4")
    before = shown(search)
    search.transitivity.setText("1 x")
    assert search.unread() == "transitivity"
    assert search.note.isVisibleTo(search)
    assert "x" in search.transitivity.toolTip()
    assert shown(search) == before

    search.transitivity.setText("1 1")
    assert search.unread() == ""
    assert not search.note.isVisibleTo(search)
    assert shown(search) == ["dia", "sod", "sql", "kgm"]


def test_the_boxes_and_the_fields_both_apply(search):
    search.coordination.setText("4")
    search.two_d.setChecked(False)
    assert shown(search) == ["dia", "sod"]


def test_unticking_the_last_kind_ticks_the_other_instead(search):
    search.two_d.setChecked(False)
    search.three_d.setChecked(False)
    assert search.two_d.isChecked()
    assert shown(search) == ["hcb", "sql", "kgm", "mcm"]
