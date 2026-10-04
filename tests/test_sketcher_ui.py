"""The 2D sketcher (``xtalapp.widgets.sketcher``), driven as a person
would: keys typed over atoms, Ctrl+A, a tool chosen with a selection.

Every one of these is something rdeditor's canvas could not do, which
is why it was replaced; a regression here is the editor going back to
being mouse-only, atom-only, or seven elements wide.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QMenu  # noqa: E402

from xtal.build import MISSING, installed  # noqa: E402
from xtal.build.sketch import Sketch  # noqa: E402
from xtalapp.dialogs.sketch import SketchEditor  # noqa: E402
from xtalapp.widgets.sketcher import canvas as canvas_module  # noqa: E402

pytestmark = pytest.mark.skipif(not installed(), reason=MISSING)


@pytest.fixture
def editor(qtbot):
    widget = SketchEditor(connection_points=True, head_tail=True)
    qtbot.addWidget(widget)
    widget.resize(700, 500)
    widget.show()
    return widget


def _chain(n=3) -> Sketch:
    sketch = Sketch()
    sketch.add_atom("C")
    for k in range(n - 1):
        sketch.grow(k)
    return sketch


def _hover(view, atom: int) -> None:
    a = view.sketch.atoms[atom]
    QTest.mouseMove(view, view.to_screen(a.x, a.y).toPoint())
    view.hover_at(view.to_screen(a.x, a.y))


def _hover_bond(view, bond: int) -> None:
    b = view.sketch.bonds[bond]
    (ax, ay), (bx, by) = view.sketch.point(b.a), view.sketch.point(b.b)
    view.hover_at(view.to_screen((ax + bx) / 2, (ay + by) / 2))


def _click(view, x, y) -> None:
    QTest.mouseClick(view, Qt.LeftButton, Qt.NoModifier,
                     view.to_screen(x, y).toPoint())


# ----------------------------------------------------------- selection

def test_ctrl_a_selects_every_atom_and_bond(editor):
    view = editor.view
    view.set_sketch(_chain(4))
    QTest.keyClick(view, Qt.Key_A, Qt.ControlModifier)
    assert view.selected_atoms == {0, 1, 2, 3}
    assert view.selected_bonds == {0, 1, 2}


def test_a_bond_type_applies_to_every_selected_bond(editor):
    """Ctrl+A then Double: every bond, not the one under the pointer."""
    view = editor.view
    view.set_sketch(_chain(4))
    QTest.keyClick(view, Qt.Key_A, Qt.ControlModifier)
    editor.tools.button("Double").click()
    assert {b.order for b in view.sketch.bonds} == {"double"}


def test_an_element_chosen_with_atoms_selected_changes_them_all(editor):
    view = editor.view
    view.set_sketch(_chain(3))
    view.select_all()
    editor.tools.button("N").click()
    assert {a.element for a in view.sketch.atoms} == {"N"}


# ----------------------------------------------------------------- keys

def test_hovering_and_typing_n_makes_nitrogen(editor):
    view = editor.view
    view.set_sketch(_chain(3))
    _hover(view, 1)
    QTest.keyClicks(view, "n")
    assert view.sketch.atoms[1].element == "N"
    assert "N" in editor.smiles()


def test_a_quick_second_letter_makes_a_two_letter_element(editor):
    """C then l is chlorine, in one undo step: undo goes back to the
    carbon that was there before, never to a carbon nobody meant."""
    view = editor.view
    sketch = _chain(2)
    sketch.set_element([1], "O")
    view.set_sketch(sketch)
    _hover(view, 1)
    QTest.keyClicks(view, "cl")
    assert view.sketch.atoms[1].element == "Cl"

    view.undo()
    assert view.sketch.atoms[1].element == "O"


def test_a_letter_with_no_element_of_its_own_waits_for_the_second(
        editor):
    """Z is nothing alone; Z then n is zinc."""
    view = editor.view
    view.set_sketch(_chain(2))
    _hover(view, 0)
    QTest.keyClicks(view, "z")
    assert view.sketch.atoms[0].element == "C"
    QTest.keyClicks(view, "n")
    assert view.sketch.atoms[0].element == "Zn"


def test_a_slow_second_letter_is_a_new_change(editor, monkeypatch):
    view = editor.view
    view.set_sketch(_chain(2))
    _hover(view, 0)
    clock = iter([100.0, 100.0 + canvas_module.TYPE_AHEAD + 0.5])
    monkeypatch.setattr(canvas_module.time, "monotonic",
                        lambda: next(clock))
    QTest.keyClicks(view, "c")
    QTest.keyClicks(view, "o")
    assert view.sketch.atoms[0].element == "O"   # O, never Co


def test_typing_on_a_bond_sets_its_order(editor):
    view = editor.view
    view.set_sketch(_chain(3))
    _hover_bond(view, 1)
    QTest.keyClicks(view, "2")
    assert view.sketch.bonds[1].order == "double"
    assert view.sketch.bonds[0].order == "single"


def test_typing_a_ring_size_on_a_bond_fuses_a_saturated_ring(editor):
    """4 to 8 over a bond is cyclobutane to cyclooctane fused there,
    one undo step; 1-3 stay the bond's order."""
    view = editor.view
    view.set_sketch(_chain(2))
    for size in "45678":
        _hover_bond(view, 0)
        QTest.keyClicks(view, size)
        assert len(view.sketch) == int(size)
        assert {b.order for b in view.sketch.bonds} == {"single"}
        view.undo()
        assert len(view.sketch) == 2
    _hover_bond(view, 0)
    QTest.keyClicks(view, "5")
    assert editor.smiles() == "C1CCCC1"


def test_typing_an_atoms_own_element_takes_a_hydrogen_off(editor):
    """CH3, CH2, CH, C and round to CH3 again -- left automatic, so
    the label and the string follow what is drawn after."""
    view = editor.view
    view.set_sketch(_chain(2))
    seen = []
    for _ in range(4):
        _hover(view, 1)
        QTest.keyClicks(view, "c")
        view._typed = None                  # each a separate keystroke
        seen.append(view.hydrogens[1])
    assert seen == [2, 1, 0, 3]
    assert view.sketch.atoms[1].hydrogens is None


def test_a_lone_carbon_cycles_down_from_methane(editor):
    view = editor.view
    view.set_sketch(_chain(1))
    _hover(view, 0)
    QTest.keyClicks(view, "c")
    assert view.hydrogens[0] == 3
    view._typed = None
    for _ in range(3):
        QTest.keyClicks(view, "c")
        view._typed = None
    assert view.sketch.atoms[0].hydrogens == 0      # bare C, as asked
    QTest.keyClicks(view, "c")
    assert view.hydrogens[0] == 4


def test_c_then_l_on_a_carbon_is_still_chlorine_in_one_step(editor):
    view = editor.view
    view.set_sketch(_chain(2))
    _hover(view, 1)
    QTest.keyClicks(view, "cl")
    assert view.sketch.atoms[1].element == "Cl"
    assert view.sketch.atoms[1].hydrogens is None
    view.undo()
    assert view.sketch.atoms[1].element == "C"
    assert view.hydrogens[1] == 3


def test_delete_removes_the_selection(editor):
    view = editor.view
    view.set_sketch(_chain(3))
    view.selected_atoms = {2}
    QTest.keyClick(view, Qt.Key_Delete)
    assert len(view.sketch) == 2


# --------------------------------------------------------------- mouse

def test_clicking_the_page_places_the_element_chosen(editor, qtbot):
    view = editor.view
    editor.tools.check("O")
    _click(view, 0.0, 0.0)
    assert [a.element for a in view.sketch.atoms] == ["O"]
    assert editor.smiles() == "O"


def test_clicking_an_atom_with_its_own_element_grows_a_bond(editor):
    view = editor.view
    _click(view, 0.0, 0.0)
    _click(view, 0.0, 0.0)
    assert len(view.sketch) == 2
    assert editor.smiles() == "CC"


def test_a_ring_fused_on_a_clicked_bond(editor):
    view = editor.view
    view.set_sketch(_chain(2))
    editor.tools.check("Benzene")
    (ax, ay), (bx, by) = view.sketch.point(0), view.sketch.point(1)
    _click(view, (ax + bx) / 2, (ay + by) / 2)
    assert len(view.sketch) == 6
    assert editor.smiles() == "c1ccccc1"


def test_a_five_ring_template_is_one_click(editor):
    view = editor.view
    editor.tools.check("Thiophene")
    _click(view, 0.0, 0.0)
    assert editor.smiles() == "c1ccsc1"


def test_the_gestures_are_down_the_left_of_the_page(editor):
    """Bonds, rings and charges in a palette beside the page, each a
    picture; the elements and commands stay above it."""
    side = editor.tools.side
    assert side.geometry().right() < editor.view.geometry().left()
    for name in ("Select", "Double", "6", "Pyrrole", "+"):
        assert side.isAncestorOf(editor.tools.button(name)), name
    for name in ("C", "Undo"):
        assert not side.isAncestorOf(editor.tools.button(name)), name
    assert not editor.tools.button("Benzene").icon().isNull()


# ------------------------------------------------- metals and points

def test_a_metal_from_the_periodic_table_takes_bonds(editor):
    """Any element is a tool: platinum from the table, four chlorines
    dragged out of it, and the string is the skeleton of PtCl4."""
    view = editor.view
    editor.tools._from_table("Pt")
    _click(view, 0.0, 0.0)
    editor.tools.check("Cl")
    centre = view.to_screen(0.0, 0.0).toPoint()
    for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
        QTest.mousePress(view, Qt.LeftButton, Qt.NoModifier, centre)
        QTest.mouseMove(view, view.to_screen(0.5 * dx, 0.5 * dy).toPoint())
        QTest.mouseRelease(view, Qt.LeftButton, Qt.NoModifier,
                           view.to_screen(dx, dy).toPoint())
    assert view.sketch.atoms[0].element == "Pt"
    assert len(view.sketch.neighbours(0)) == 4
    assert "[Pt]" in editor.smiles()


def test_the_geometry_menu_sets_an_override(editor):
    view = editor.view
    sketch = Sketch()
    pt = sketch.add_atom("Pt")
    for _ in range(4):
        sketch.grow(pt, "Cl")
    view.set_sketch(sketch)
    menu = view.menu_for(pt)
    geometry = menu.findChild(QMenu, "geometry")
    choice = next(a for a in geometry.actions()
                  if a.text() == "Tetrahedral")
    choice.trigger()
    assert view.sketch.atoms[pt].shape == "tetrahedral"
    assert "xtal_shape" in editor.smiles()


def test_a_connection_point_can_be_made_the_head(editor):
    view = editor.view
    sketch = _chain(2)
    point = sketch.grow(1, "X")
    view.set_sketch(sketch)
    menu = view.menu_for(point)
    next(a for a in menu.actions() if a.text().startswith("Head")
         ).trigger()
    assert "[*:1]" in editor.smiles()


def test_without_connection_points_there_is_no_star_tool(qtbot):
    widget = SketchEditor(connection_points=False)
    qtbot.addWidget(widget)
    assert widget.tools.button("X") is None
    widget.view.set_sketch(_chain(2))
    widget.view.hover = ("atom", 0)
    widget.view.type_key("*")
    assert widget.view.sketch.atoms[0].element == "C"


# ------------------------------------------------------------- history

def test_one_gesture_is_one_undo_step(editor):
    """A ring is six atoms and six bonds, and one Ctrl+Z."""
    view = editor.view
    editor.tools.check("6")
    _click(view, 0.0, 0.0)
    assert len(view.sketch) == 6
    QTest.keyClick(view, Qt.Key_Z, Qt.ControlModifier)
    assert len(view.sketch) == 0


def test_a_drawing_that_is_not_a_molecule_leaves_the_box_alone(editor):
    """Five bonds on a carbon on the way to four: the page says so,
    and the string the box holds is the last good one."""
    view = editor.view
    view.set_sketch(_chain(2))
    for _ in range(3):
        view.edit(lambda s: s.grow(0, "F"))
    before = editor.smiles()
    view.edit(lambda s: s.grow(0, "F"))
    assert "too many bonds" in view.problem
    assert editor.smiles() == before


# ------------------------------------------------------- zoom and pan

def test_zooming_keeps_the_point_under_the_pointer(editor):
    view = editor.view
    view.set_sketch(_chain(3))
    pointer = view.to_screen(*view.sketch.point(2))
    before = view.scale
    view.zoom_by(2.0, pointer)
    assert view.scale == pytest.approx(min(2 * before,
                                           canvas_module.MAX_SCALE))
    after = view.to_screen(*view.sketch.point(2))
    assert after.x() == pytest.approx(pointer.x())
    assert after.y() == pytest.approx(pointer.y())


def test_zoom_stops_at_its_limits(editor):
    view = editor.view
    view.zoom_by(1e6)
    assert view.scale == canvas_module.MAX_SCALE
    view.zoom_by(1e-6)
    assert view.scale == canvas_module.MIN_SCALE


def test_ctrl_plus_and_minus_zoom_and_never_charge_an_atom(editor):
    view = editor.view
    view.set_sketch(_chain(2))
    _hover(view, 0)
    before = view.scale
    QTest.keyClick(view, Qt.Key_Equal, Qt.ControlModifier)
    assert view.scale > before
    QTest.keyClick(view, Qt.Key_Minus, Qt.ControlModifier)
    assert view.scale == pytest.approx(before)
    assert view.sketch.atoms[0].charge == 0


def test_a_middle_drag_pans_and_draws_nothing(editor):
    view = editor.view
    view.set_sketch(_chain(2))
    start = view.to_screen(-3.0, -3.0).toPoint()
    end = start + QPoint(40, 25)
    before = QPointF(view.offset)
    QTest.mousePress(view, Qt.MiddleButton, Qt.NoModifier, start)
    QTest.mouseMove(view, end)
    QTest.mouseRelease(view, Qt.MiddleButton, Qt.NoModifier, end)
    assert view.offset.x() - before.x() == pytest.approx(40)
    assert view.offset.y() - before.y() == pytest.approx(25)
    assert len(view.sketch) == 2


def test_space_and_a_drag_pans_instead_of_drawing_a_bond(editor):
    view = editor.view
    view.set_sketch(_chain(2))
    start = view.to_screen(-3.0, -3.0).toPoint()
    end = start + QPoint(60, 0)
    QTest.keyPress(view, Qt.Key_Space)
    QTest.mousePress(view, Qt.LeftButton, Qt.NoModifier, start)
    QTest.mouseMove(view, end)
    QTest.mouseRelease(view, Qt.LeftButton, Qt.NoModifier, end)
    QTest.keyRelease(view, Qt.Key_Space)
    assert len(view.sketch) == 2
    assert not view._space


def _wheel(view, angle, pixels, phase):
    from PySide6.QtGui import QWheelEvent
    at = QPointF(view.width() / 2, view.height() / 2)
    event = QWheelEvent(at, view.mapToGlobal(at), pixels, angle,
                        Qt.NoButton, Qt.NoModifier, phase, False)
    view.wheelEvent(event)


def test_a_wheel_zooms_and_a_trackpad_pans(editor):
    """A mouse wheel's notch zooms in; two fingers on a trackpad (a
    scroll with phases) move the page and leave the scale alone."""
    view = editor.view
    view.set_sketch(_chain(3))
    before = view.scale
    _wheel(view, QPoint(0, 120), QPoint(0, 0), Qt.NoScrollPhase)
    assert view.scale == pytest.approx(before * canvas_module.WHEEL_ZOOM)
    scale, offset = view.scale, QPointF(view.offset)
    _wheel(view, QPoint(0, 0), QPoint(12, -30), Qt.ScrollUpdate)
    assert view.scale == scale
    assert view.offset.x() - offset.x() == pytest.approx(12)
    assert view.offset.y() - offset.y() == pytest.approx(-30)
