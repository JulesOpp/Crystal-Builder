"""Rectangular select: drag a box, take what is inside it.

Two halves, tested apart.  The projection is arithmetic against a real
camera and is checked by putting an atom somewhere known and asking
where it landed.  The mode itself is checked with a projection handed
in, because what it has to get right is the rectangle test and the
selection -- neither of which needs a GPU to be wrong.
"""

import numpy as np
import pytest

from tests.conftest import needs_offscreen_gl
from xtal import Lattice, Structure
from xtal.core.selection import Selection
from xtalapp.viewport import modes
from xtalapp.viewport.builder import build_scene
from xtalapp.viewport.view_settings import ViewSettings


class FakeDocument:
    """Just enough document for a selection to land in."""

    def __init__(self):
        self.selected: list = []
        self.calls: list = []
        self.selection = Selection()
        self.with_bonds: list = []

    def select(self, atoms, mode="set", with_bonds=False):
        atoms = [int(a) for a in atoms]
        self.calls.append((sorted(atoms), mode))
        self.with_bonds.append(with_bonds)
        if mode == "add":
            self.selected = sorted(set(self.selected) | set(atoms))
        else:
            self.selected = sorted(atoms)
        self.selection.set_atoms(self.selected)

    def select_none(self):
        self.calls.append(([], "none"))
        self.selected = []
        self.selection.clear()


def a_row_of_atoms(n=5, spacing=2.0, box=30.0) -> Structure:
    """A row along x starting at the cartesian origin, so the fake
    projection below can be read as "drop the z axis" and the numbers
    in a test are the coordinates themselves."""
    lattice = Lattice.cubic(box)
    cart = np.array([[k * spacing, 0.0, 0.0] for k in range(n)])
    return Structure.from_arrays(lattice, ["C"] * n, cart / box,
                                 space_group="P1")


def drag(model, start, end, additive=False, project=None):
    """Run a box drag over ``model`` and return (document, message)."""
    document = FakeDocument()
    mode = modes.get("box_select")
    event = modes.DragEvent(start, end, additive,
                            project or (lambda p: p[:, :2]))
    return document, mode.on_drag(document, model, event)


# ================================================== the rectangle test

def test_the_box_takes_what_is_inside_it():
    """The atoms are in a row along x; a box over the first two takes
    two of them and no more."""
    model = build_scene(a_row_of_atoms(), ViewSettings(show_cell=False))
    document, message = drag(model, (-0.5, -1.0), (2.5, 1.0))
    assert document.selected == [0, 1]
    assert "2 atom(s)" in message


def test_a_box_dragged_backwards_is_the_same_box():
    """Up and to the left has to mean the same rectangle as down and
    to the right, or half of every drag selects nothing."""
    model = build_scene(a_row_of_atoms(), ViewSettings(show_cell=False))
    forwards, _ = drag(model, (-0.5, -1.0), (2.5, 1.0))
    backwards, _ = drag(model, (2.5, 1.0), (-0.5, -1.0))
    assert forwards.selected == backwards.selected == [0, 1]


def test_an_empty_box_clears_the_selection():
    model = build_scene(a_row_of_atoms(), ViewSettings(show_cell=False))
    document, message = drag(model, (100.0, 100.0), (200.0, 200.0))
    assert document.selected == []
    assert document.calls == [([], "none")]
    assert "nothing" in message


def test_shift_extends_instead_of_replacing():
    model = build_scene(a_row_of_atoms(), ViewSettings(show_cell=False))
    document, _ = drag(model, (-0.5, -1.0), (0.5, 1.0))
    assert document.selected == [0]

    mode = modes.get("box_select")
    mode.on_drag(document, model,
                 modes.DragEvent((1.5, -1.0), (2.5, 1.0), True,
                                 lambda p: p[:, :2]))
    assert document.selected == [0, 1]


def test_shift_over_nothing_leaves_the_selection_alone():
    model = build_scene(a_row_of_atoms(), ViewSettings(show_cell=False))
    document, _ = drag(model, (-0.5, -1.0), (0.5, 1.0))
    modes.get("box_select").on_drag(
        document, model,
        modes.DragEvent((100.0, 100.0), (200.0, 200.0), True,
                        lambda p: p[:, :2]))
    assert document.selected == [0]


def test_the_box_takes_what_is_hidden_behind_what_it_can_see():
    """VESTA's behaviour, and the reason the gesture is useful for a
    slab: a box that took only the front face would have to be dragged
    once per layer.  Here two atoms project to the same spot and both
    are taken."""
    lattice = Lattice.cubic(30.0)
    cart = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 5.0]])
    stacked = Structure.from_arrays(lattice, ["C", "C"], cart / 30.0,
                                    space_group="P1")
    model = build_scene(stacked, ViewSettings(show_cell=False))
    # projecting away the z axis is exactly "looking down z"
    document, message = drag(model, (-1.0, -1.0), (1.0, 1.0))
    assert document.selected == [0, 1]
    assert "front to back" in message


def test_a_drawn_copy_selects_the_atom_it_is_a_copy_of(rutile):
    """The box works in drawn instances and the selection is over P1
    atoms, so the same atom drawn at three corners of the cell must not
    arrive as three selections."""
    settings = ViewSettings(show_cell=False)
    model = build_scene(rutile, settings)
    assert model.n_atoms > len(set(model.atom_index.tolist()))

    document = FakeDocument()
    modes.get("box_select").on_drag(
        document, model,
        modes.DragEvent((-1e6, -1e6), (1e6, 1e6), False,
                        lambda p: p[:, :2]))
    assert document.selected == sorted(set(model.atom_index.tolist()))


def test_the_box_takes_the_bonds_between_what_it_took():
    """A box is how a fragment gets named, and the bonds inside a named
    fragment are part of what was named -- otherwise Set Bond Type
    after a box acts on nothing at all."""
    model = build_scene(a_row_of_atoms(spacing=1.5),
                        ViewSettings(show_cell=False))
    document, message = drag(model, (-0.5, -1.0), (4.0, 1.0))
    assert document.selected == [0, 1, 2]
    assert document.with_bonds == [True]
    assert "bond(s) in the box" in message


def test_a_bond_with_one_end_outside_the_box_is_not_inside_it():
    """Which is what the document decides, from the atoms the box
    handed it -- so what the mode has to get right is asking for
    them."""
    from xtalapp.document import Document

    structure = a_row_of_atoms(spacing=1.5)
    document = Document(structure)
    document.select([0, 1], with_bonds=True)
    assert len(document.selection.bonds) == 1

    document.select([0], with_bonds=True)
    assert not document.selection.bonds


def test_an_empty_scene_is_not_an_error():
    empty = Structure.from_arrays(Lattice.cubic(10.0), [],
                                  np.zeros((0, 3)), space_group="P1")
    model = build_scene(empty, ViewSettings())
    assert drag(model, (0.0, 0.0), (10.0, 10.0))[1] == ""


def test_a_click_in_box_mode_is_still_a_click():
    """Otherwise the mode feels broken: you box a slab, then click one
    atom to add it, and nothing happens."""
    assert modes.get("box_select").wants_drag is True
    assert hasattr(modes.get("box_select"), "on_click")


# ======================================================= the projection

vtk_scene = pytest.importorskip("xtalapp.viewport.vtk_scene")


# Renders for real, so it needs a GL driver; the rest of this
# file does not and must keep running without one.  See
# conftest.offscreen_gl_works.
@needs_offscreen_gl
def test_projection_puts_the_centre_of_the_scene_in_the_middle():
    """The camera looks at the middle of what it is shown, so the atom
    there lands in the middle of the window -- which is the calibration
    every rectangle test rests on."""
    from xtalapp.viewport.picking import project_to_display

    one = Structure.from_arrays(Lattice.cubic(10.0), ["C"],
                                [[0.5, 0.5, 0.5]], space_group="P1")
    model = build_scene(one, ViewSettings(show_cell=False))
    scene = vtk_scene.VtkScene()
    scene.set_model(model)
    from vtkmodules.vtkRenderingCore import vtkRenderWindow
    window = vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetSize(400, 300)
    window.AddRenderer(scene.renderer)
    scene.reset_camera()
    window.Render()

    display = project_to_display(scene.renderer, model.positions)
    assert display.shape == (model.n_atoms, 2)
    assert display[0][0] == pytest.approx(200.0, abs=2.0)
    assert display[0][1] == pytest.approx(150.0, abs=2.0)
    window.Finalize()


# Renders for real, so it needs a GL driver; the rest of this
# file does not and must keep running without one.  See
# conftest.offscreen_gl_works.
@needs_offscreen_gl
def test_something_behind_the_camera_is_not_in_front_of_it():
    """A perspective divide by a negative w folds a point behind the
    viewer round to the front of the picture.  Left alone, a box drawn
    over empty space would take atoms from behind your head."""
    from xtalapp.viewport.picking import project_to_display

    one = Structure.from_arrays(Lattice.cubic(10.0), ["C"],
                                [[0.5, 0.5, 0.5]], space_group="P1")
    model = build_scene(one, ViewSettings(show_cell=False))
    scene = vtk_scene.VtkScene()
    scene.set_model(model)
    from vtkmodules.vtkRenderingCore import vtkRenderWindow
    window = vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetSize(400, 300)
    window.AddRenderer(scene.renderer)
    scene.reset_camera()
    window.Render()

    camera = scene.renderer.GetActiveCamera()
    eye = np.array(camera.GetPosition())
    behind = eye - np.array(camera.GetDirectionOfProjection()) * 10.0
    display = project_to_display(scene.renderer, [behind])
    assert np.all(np.isnan(display))
    window.Finalize()


# =================================================== the drag plumbing

class FakeBand:
    def __init__(self):
        self.visible = False
        self.rects: list = []

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def setGeometry(self, rect):
        self.rects.append(rect)


class FakeSignal:
    def __init__(self):
        self.sent: list = []

    def emit(self, text):
        self.sent.append(text)


class FakeViewport:
    """Enough of ViewportWidget to run the band handlers unbound.

    The handlers are the part that is easy to get wrong -- a drag that
    is really a click, a band left on screen, the left button handed to
    VTK after all -- and none of it needs a render window.
    """

    def __init__(self, mode, document, model):
        self.mode = mode
        self.document = document
        self.model = model
        self._band = FakeBand()
        self._band_origin = None
        self._press_position = None
        self._press_button = None
        self.statusMessage = FakeSignal()
        self.picked: list = []

    def _display_at(self, point):
        return (float(point.x()), float(point.y()))

    def _project(self, points):
        return np.asarray(points)[:, :2]

    def pick_at(self, point, additive=False, double=False):
        self.picked.append((point.x(), point.y(), additive, double))


def _widget_module():
    pytest.importorskip("PySide6")
    from xtalapp.viewport import widget
    return widget


def test_a_drag_mode_takes_the_left_button_from_the_camera():
    """A rubber band and a camera rotation are the same gesture; only
    one of them can have the button."""
    widget = _widget_module()
    from PySide6.QtCore import Qt

    class FakeEvent:
        def __init__(self, button):
            self._button = button

        def button(self):
            return self._button

    box = FakeViewport(modes.get("box_select"), None, None)
    plain = FakeViewport(modes.get("select"), None, None)
    takes = widget.ViewportWidget._takes_drag
    assert takes(box, FakeEvent(Qt.LeftButton)) is True
    assert takes(box, FakeEvent(Qt.RightButton)) is False
    assert takes(plain, FakeEvent(Qt.LeftButton)) is False


def test_a_finished_band_selects_and_puts_itself_away():
    widget = _widget_module()
    from PySide6.QtCore import QPoint, Qt

    class FakeEvent:
        def position(self):
            class P:
                def toPoint(self):
                    return QPoint(300, 300)
            return P()

        def modifiers(self):
            return Qt.NoModifier

    document = FakeDocument()
    model = build_scene(a_row_of_atoms(), ViewSettings(show_cell=False))
    view = FakeViewport(modes.get("box_select"), document, model)
    view._band_origin = QPoint(-10, -10)
    view._band.show()

    widget.ViewportWidget._finish_band(view, FakeEvent())
    assert not view._band.visible
    assert view._band_origin is None
    assert document.selected                    # the row was taken
    assert view.statusMessage.sent


def test_a_band_that_never_moved_is_sent_on_as_a_click():
    """Otherwise clicking one atom in box mode does nothing at all."""
    widget = _widget_module()
    from PySide6.QtCore import QPoint, Qt

    class FakeEvent:
        def position(self):
            class P:
                def toPoint(self):
                    return QPoint(40, 40)
            return P()

        def modifiers(self):
            return Qt.NoModifier

    document = FakeDocument()
    model = build_scene(a_row_of_atoms(), ViewSettings(show_cell=False))
    view = FakeViewport(modes.get("box_select"), document, model)
    view._band_origin = QPoint(40, 41)          # inside CLICK_SLOP
    view._band.show()

    widget.ViewportWidget._finish_band(view, FakeEvent())
    assert view.picked == [(40, 40, False, False)]
    assert document.calls == []                 # no box was applied
