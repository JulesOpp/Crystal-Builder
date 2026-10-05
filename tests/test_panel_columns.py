"""The Move, Force Field and DFTB+ panels side by side when wide.

The Style panel's groups have sat in two columns since 2026-09; these
three were one column at any width, so a panel dragged wide was half
empty and one dragged tall still scrolled.  Each now reflows the same
way: two columns once no form row would wrap, one below that, read in
the same order.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QGroupBox, QWidget  # noqa: E402

from xtalapp.docks.columns import ReflowColumns  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Cols{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def _laid_out_at(qtbot, dock, width, height=900):
    dock.setFloating(True)
    dock.resize(width, height)
    dock.show()
    qtbot.wait(20)
    return dock.columns


def _wide(qtbot, dock):
    """Wide enough for two columns, in whatever font this machine
    draws in."""
    columns = _laid_out_at(qtbot, dock, 400)
    need = columns.layout().two_column_width() + 80
    return _laid_out_at(qtbot, dock, max(need, 800))


def _titles(dock) -> list[str]:
    return [g.title() for g in dock.columns.widgets
            if isinstance(g, QGroupBox)]


def test_move_has_reflect_and_flatten_as_groups_of_their_own(window):
    """Make planar takes no normal, and in Reflect's box it read as
    though the plane were the one chosen there."""
    assert _titles(window.move_dock) == [
        "Translate", "Reflect", "Rotate", "Flatten"]
    flatten = window.move_dock.columns.widgets[3]
    assert flatten.isAncestorOf(window.move_dock.planar_button)
    assert not flatten.isAncestorOf(window.move_dock.mirror_axis)


@pytest.mark.parametrize("name", ["move_dock", "ff_dock", "dftb_dock"])
def test_a_wide_panel_puts_its_groups_side_by_side(qtbot, window, name):
    dock = getattr(window, name)
    columns = _wide(qtbot, dock)
    assert columns.two_columns()
    first = columns.widgets[0]
    right = [w for w in columns.widgets
             if w.isVisible() and w.x() > first.x() + first.width()]
    assert right
    assert right[0].y() == first.y()


@pytest.mark.parametrize("name", ["move_dock", "ff_dock", "dftb_dock"])
def test_a_narrow_panel_stacks_its_groups_in_order(qtbot, window, name):
    dock = getattr(window, name)
    columns = _laid_out_at(qtbot, dock, 330)
    assert not columns.two_columns()
    shown = [w for w in columns.widgets if w.isVisible()]
    assert len({w.x() for w in shown}) == 1
    assert [w.y() for w in shown] == sorted(w.y() for w in shown)


def test_the_force_field_panel_does_not_squeeze_its_stacked_groups(
        qtbot, window):
    """A splitter does not ask a pane for its height at a width, so one
    column of groups was given the height of the tallest alone."""
    dock = window.ff_dock
    columns = _laid_out_at(qtbot, dock, 330, 600)
    assert columns.height() >= columns.heightForWidth(columns.width())


def test_the_atom_types_table_opens_tall_enough_to_read(qtbot, window,
                                                        rutile_cif):
    from xtalapp.docks.ff_panel import TYPE_ROWS

    window.open_path(rutile_cif)
    table = window.ff_dock.table
    rows = TYPE_ROWS * table.verticalHeader().defaultSectionSize()
    assert table.minimumHeight() >= rows


def test_a_balanced_cut_evens_out_the_columns(qtbot):
    """``split=None`` cuts where the taller column is shortest."""
    heights = [100, 100, 300, 50, 50]
    boxes = []
    for h in heights:
        box = QWidget()
        box.setFixedHeight(h)
        boxes.append(box)
    columns = ReflowColumns(boxes, split=None)
    qtbot.addWidget(columns)
    columns.resize(600, 1000)
    columns.show()
    qtbot.wait(10)
    assert columns.two_columns()
    left = [b for b in boxes if b.x() == boxes[0].x()]
    # 100 + 100 + 300 | 50 + 50 leaves the right empty; 100 + 100 |
    # 300 + 50 + 50 is the even one.
    assert left == boxes[:2]
