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

from PySide6.QtCore import Qt  # noqa: E402
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
