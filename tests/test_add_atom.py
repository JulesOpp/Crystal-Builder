"""Add atom: a click on an atom means "another one bonded to this".

Dropping the new atom wherever the click ray met the focal plane is
right over empty space and wrong over an existing atom, where the
depth the plane happened to be at is never what was meant.  So the
gesture has two clicks -- one to anchor, one to point -- the distance
comes from the pair's covalent radii, and the bond is created with the
atom rather than left for perception to find.

The cheaper half is the same state machine entered one click later: an
atom that is already selected is already an anchor.
"""

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.core import elements as el

pytest.importorskip("PySide6")

from xtalapp.document import Document  # noqa: E402
from xtalapp.viewport import modes  # noqa: E402
from xtalapp.viewport.builder import build_scene  # noqa: E402


@pytest.fixture
def mode():
    """The registered mode, reset -- it is a singleton and holds the
    anchor between clicks, which is exactly what a leaked one is."""
    add = modes.get("add_atom")
    add.element = "C"
    add.anchor = None
    yield add
    add.anchor = None
    add.element = "C"


@pytest.fixture
def one_carbon():
    """A single C at the middle of a roomy P1 box."""
    document = Document(Structure.empty(Lattice.cubic(20.0)))
    document.add_atom("C", [0.5, 0.5, 0.5])
    return document


def scene(document):
    return build_scene(document.structure, document.view)


def ray_at(document, atom: int, offset=(0.0, 0.0, -10.0)):
    """A click ray running along +z straight through a drawn atom."""
    target = document.cell.cart[atom]
    origin = target + np.asarray(offset, dtype=float)
    return modes.ClickEvent(origin=tuple(origin),
                            direction=(0.0, 0.0, 1.0),
                            focal=tuple(target))


# ------------------------------------------------------ the geometry

def test_the_ray_meets_the_sphere_on_the_near_face():
    """The face the user is looking at, not the one behind it."""
    point = modes.point_on_sphere([-10, 0, 0], [1, 0, 0],
                                  [0, 0, 0], 1.5)
    assert np.allclose(point, [-1.5, 0.0, 0.0])


def test_a_ray_that_misses_still_places_the_atom():
    """The sphere is about an Angstrom across and the second click is
    a direction, so refusing a miss would fail almost everywhere it is
    aimed."""
    point = modes.point_on_sphere([-10, 5, 0], [1, 0, 0],
                                  [0, 0, 0], 1.5)
    assert np.allclose(point, [0.0, 1.5, 0.0])
    assert np.linalg.norm(point) == pytest.approx(1.5)


def test_the_distance_is_the_pair_s():
    """The sum of the covalent radii -- what perception already uses
    to decide two atoms are bonded."""
    assert modes.bond_distance("C", "C") == pytest.approx(
        2 * el.covalent_radius("C"))
    assert modes.bond_distance("C", "H") == pytest.approx(
        el.covalent_radius("C") + el.covalent_radius("H"))


def test_even_a_dummy_atom_has_a_distance():
    """Nothing here may return zero: a bond of no length is not a
    placement, and Add centroid puts dummy atoms in reach of this."""
    assert modes.bond_distance("X", "C") > 0.5


# ------------------------------------------------------- the gesture

def test_clicking_an_atom_anchors_instead_of_placing(mode, one_carbon):
    message = mode.on_click(one_carbon, scene(one_carbon),
                            ray_at(one_carbon, 0))
    assert one_carbon.structure.n_sites == 1        # nothing placed
    assert mode.anchor is not None and mode.anchor[0] == 0
    assert "bonding to" in message


def test_the_second_click_places_at_a_bond_length(mode, one_carbon):
    mode.element = "O"
    mode.on_click(one_carbon, scene(one_carbon), ray_at(one_carbon, 0))
    # Point off to one side: the ray misses the sphere, so the
    # direction is all it carries.
    mode.on_click(one_carbon, scene(one_carbon),
                  ray_at(one_carbon, 0, offset=(0.0, 8.0, -10.0)))

    assert one_carbon.structure.n_sites == 2
    cart = one_carbon.cell.cart
    distance = float(np.linalg.norm(cart[1] - cart[0]))
    assert distance == pytest.approx(modes.bond_distance("C", "O"))
    assert one_carbon.structure.sites[1].element == "O"


def test_the_bond_comes_with_the_atom(mode, one_carbon):
    """The user has just said what it is bonded to; leaving it for
    perception is a different answer to a question nobody asked."""
    mode.element = "H"
    mode.on_click(one_carbon, scene(one_carbon), ray_at(one_carbon, 0))
    mode.on_click(one_carbon, scene(one_carbon),
                  ray_at(one_carbon, 0, offset=(0.0, 8.0, -10.0)))

    assert len(one_carbon.graph.bonds) == 1
    assert [b.kind for b in one_carbon.structure.bonds] == ["explicit"]


def test_the_atom_and_its_bond_are_one_undo_step(mode, one_carbon):
    mode.on_click(one_carbon, scene(one_carbon), ray_at(one_carbon, 0))
    mode.on_click(one_carbon, scene(one_carbon),
                  ray_at(one_carbon, 0, offset=(0.0, 8.0, -10.0)))
    assert one_carbon.structure.n_sites == 2

    one_carbon.undo()
    assert one_carbon.structure.n_sites == 1
    assert one_carbon.structure.bonds == []


def test_the_anchor_is_forgotten_after_the_placement(mode, one_carbon):
    mode.on_click(one_carbon, scene(one_carbon), ray_at(one_carbon, 0))
    mode.on_click(one_carbon, scene(one_carbon),
                  ray_at(one_carbon, 0, offset=(0.0, 8.0, -10.0)))
    assert mode.anchor is None


def test_a_click_on_empty_space_still_places_an_atom(mode, one_carbon):
    """Today's behaviour, unchanged, for the click that means what it
    always meant."""
    event = modes.ClickEvent(origin=(0.0, 0.0, -10.0),
                             direction=(0.0, 0.0, 1.0),
                             focal=(3.0, 4.0, 5.0))
    assert "added" in mode.on_click(one_carbon, scene(one_carbon),
                                    event)
    assert one_carbon.structure.n_sites == 2
    placed = one_carbon.structure.lattice.to_cart(
        one_carbon.structure.sites[1].frac)
    assert np.allclose(placed, [0.0, 0.0, 5.0], atol=1e-6)


# -------------------------------------------- the selected anchor

def test_one_selected_atom_is_already_an_anchor(mode, one_carbon):
    """The common case -- pick the carbon, press the button, point --
    is one click shorter."""
    one_carbon.select([0])
    message = mode.on_activate(one_carbon, scene(one_carbon))
    assert mode.anchor is not None and mode.anchor[0] == 0
    assert "bonding to" in message

    mode.on_click(one_carbon, scene(one_carbon),
                  ray_at(one_carbon, 0, offset=(0.0, 8.0, -10.0)))
    assert one_carbon.structure.n_sites == 2
    assert len(one_carbon.graph.bonds) == 1


def test_more_than_one_selected_atom_is_not_an_anchor(mode, one_carbon):
    one_carbon.add_atom("C", [0.6, 0.5, 0.5])
    one_carbon.select([0, 1])
    assert mode.on_activate(one_carbon, scene(one_carbon)) == ""
    assert mode.anchor is None


def test_nothing_selected_starts_at_the_first_click(mode, one_carbon):
    one_carbon.select_none()
    assert mode.on_activate(one_carbon, scene(one_carbon)) == ""
    assert mode.anchor is None


def test_escape_abandons_the_anchor(mode, one_carbon):
    mode.on_click(one_carbon, scene(one_carbon), ray_at(one_carbon, 0))
    assert mode.anchor is not None
    assert "dropped" in mode.on_cancel(one_carbon)
    assert mode.anchor is None
    assert one_carbon.structure.n_sites == 1


def test_escape_with_no_anchor_says_nothing(mode, one_carbon):
    assert mode.on_cancel(one_carbon) == ""


def test_leaving_the_mode_drops_the_anchor(mode, one_carbon):
    mode.on_click(one_carbon, scene(one_carbon), ray_at(one_carbon, 0))
    mode.on_deactivate(one_carbon)
    assert mode.anchor is None


# ----------------------------------------------------------- the ghost

def test_the_ghost_follows_the_cursor_at_the_bond_distance(
        mode, one_carbon):
    mode.element = "O"
    mode.on_click(one_carbon, scene(one_carbon), ray_at(one_carbon, 0))

    centre = one_carbon.cell.cart[0]
    event = modes.MoveEvent(origin=tuple(centre + [0.0, 8.0, -10.0]),
                            direction=(0.0, 0.0, 1.0),
                            focal=tuple(centre))
    ghost = mode.on_move(one_carbon, scene(one_carbon), event)
    assert ghost is not None
    assert float(np.linalg.norm(ghost.position - centre)) == \
        pytest.approx(modes.bond_distance("C", "O"))
    assert np.allclose(ghost.anchor, centre)
    assert ghost.color == one_carbon.view.color_for("O")


def test_there_is_no_ghost_without_an_anchor(mode, one_carbon):
    """A first click that has not happened has nothing to show."""
    event = modes.MoveEvent(origin=(0.0, 0.0, -10.0),
                            direction=(0.0, 0.0, 1.0))
    assert mode.on_move(one_carbon, scene(one_carbon), event) is None


def test_the_ghost_lands_where_the_click_would(mode, one_carbon):
    """Two spellings of the same aim would drift apart, and the ghost
    would stop meaning the placement."""
    mode.on_click(one_carbon, scene(one_carbon), ray_at(one_carbon, 0))
    centre = one_carbon.cell.cart[0]
    origin = tuple(centre + [3.0, 4.0, -10.0])

    ghost = mode.on_move(one_carbon, scene(one_carbon),
                         modes.MoveEvent(origin, (0.0, 0.0, 1.0),
                                         tuple(centre)))
    mode.on_click(one_carbon, scene(one_carbon),
                  modes.ClickEvent(origin, (0.0, 0.0, 1.0),
                                   focal=tuple(centre)))
    placed = one_carbon.cell.cart[1]
    assert np.allclose(placed, ghost.position, atol=1e-9)


# ------------------------------------------------------- with symmetry

def test_the_bond_is_to_the_copy_that_was_clicked(mode, quartz):
    """A multi-cell view draws the same P1 atom many times, and
    bonding the copy at (1, 0, 0) is not the same bond as bonding the
    one at the origin."""
    document = Document(quartz)
    document.view.set_cells(2, 1, 1)
    model = build_scene(document.structure, document.view)

    outside = [i for i in range(model.n_atoms)
               if tuple(model.atom_cell[i]) == (1, 0, 0)]
    assert outside, "the display range should draw a second cell"
    row = outside[0]
    atom = int(model.atom_index[row])

    mode.anchor = (atom, (1, 0, 0),
                   np.asarray(model.positions[row], dtype=float))
    point = model.positions[row] + np.array([0.0, 0.0, -10.0])
    mode.on_click(document, model,
                  modes.ClickEvent(tuple(point), (0.0, 0.0, 1.0)))

    lattice = document.structure.lattice
    placed = lattice.to_cart(document.structure.sites[-1].frac)
    distance = float(np.linalg.norm(placed - model.positions[row]))
    assert distance == pytest.approx(
        modes.bond_distance(document.cell.elements[atom], "C"), abs=1e-6)
    assert len(document.structure.bonds) == 1

    # And the picture agrees: a bond half runs from the copy that was
    # clicked to where the atom landed.  The stored record is a
    # symmetry record, so this is the half of it that can be wrong
    # while the distance above stays right.
    redrawn = build_scene(document.structure, document.view)
    drawn = [i for i in range(redrawn.n_bond_halves)
             if np.allclose(redrawn.bond_starts[i],
                            model.positions[row], atol=1e-4)
             and np.allclose(redrawn.bond_ends[i],
                             (model.positions[row] + placed) / 2,
                             atol=1e-4)]
    assert drawn, "the bond was not drawn to the copy that was clicked"


# ------------------------------------------------- through the viewport
#
# The widget's own methods, run against a stand-in: what is being
# tested is the plumbing -- who gets asked, and when -- and putting a
# real VTK render window behind it would test OpenGL instead.

class FakeSignal:
    def __init__(self):
        self.sent = []

    def emit(self, text):
        self.sent.append(text)


class FakeCamera:
    def GetFocalPoint(self):
        return (0.0, 0.0, 0.0)


class FakeRenderer:
    def GetActiveCamera(self):
        return FakeCamera()


class FakeScene:
    def __init__(self):
        self.renderer = FakeRenderer()
        self.ghosts = []

    def set_ghost(self, ghost):
        self.ghosts.append(ghost)


class FakeViewport:
    """Enough of ViewportWidget to run its own methods against."""

    def __init__(self, mode, document, model, ray=None):
        self.mode = mode
        self.document = document
        self.model = model
        self.scene = FakeScene()
        self.statusMessage = FakeSignal()
        self._ghost = None
        self.renders = 0
        self._ray = ray or ((0.0, 0.0, -10.0), (0.0, 0.0, 1.0))

    def _ray_at(self, point):
        return self._ray

    def _safe_render(self):
        self.renders += 1

    def set_ghost(self, ghost):
        from xtalapp.viewport.widget import ViewportWidget
        ViewportWidget.set_ghost(self, ghost)

    def cancel_gesture(self):
        from xtalapp.viewport.widget import ViewportWidget
        ViewportWidget.cancel_gesture(self)


class FakeMove:
    def __init__(self, buttons=0):
        self._buttons = buttons

    def buttons(self):
        return self._buttons

    def position(self):
        from PySide6.QtCore import QPointF
        return QPointF(10.0, 10.0)


def viewport_module():
    from xtalapp.viewport import widget
    return widget


def test_a_hover_puts_a_ghost_up(mode, one_carbon):
    widget = viewport_module()
    centre = one_carbon.cell.cart[0]
    mode.anchor = (0, (0, 0, 0), centre)
    view = FakeViewport(mode, one_carbon, scene(one_carbon),
                        ray=(tuple(centre + [0.0, 8.0, -10.0]),
                             (0.0, 0.0, 1.0)))

    widget.ViewportWidget._maybe_hover(view, FakeMove())
    assert view.scene.ghosts and view.scene.ghosts[-1] is not None
    assert view.renders == 1


def test_a_mode_that_wants_no_moves_is_never_asked(one_carbon):
    """A ray per mouse move for a mode that would ignore it is a cost
    with nothing on the other side of it."""
    widget = viewport_module()
    view = FakeViewport(modes.get("select"), one_carbon,
                        scene(one_carbon))
    widget.ViewportWidget._maybe_hover(view, FakeMove())
    assert view.scene.ghosts == []


def test_a_move_with_a_button_down_is_the_camera(mode, one_carbon):
    widget = viewport_module()
    from PySide6.QtCore import Qt

    mode.anchor = (0, (0, 0, 0), one_carbon.cell.cart[0])
    view = FakeViewport(mode, one_carbon, scene(one_carbon))
    widget.ViewportWidget._maybe_hover(view, FakeMove(Qt.LeftButton))
    assert view.scene.ghosts == []


def test_nothing_to_nothing_is_not_a_redraw(mode, one_carbon):
    """Every mouse move over a structure arrives here, and rendering
    the same empty overlay each time puts a frame on the wire for a
    cursor that is only passing through."""
    widget = viewport_module()
    view = FakeViewport(mode, one_carbon, scene(one_carbon))
    widget.ViewportWidget.set_ghost(view, None)
    assert view.renders == 0 and view.scene.ghosts == []


def test_escape_takes_the_ghost_down_with_the_anchor(mode, one_carbon):
    widget = viewport_module()
    mode.anchor = (0, (0, 0, 0), one_carbon.cell.cart[0])
    view = FakeViewport(mode, one_carbon, scene(one_carbon))
    view._ghost = object()                      # one is on screen

    widget.ViewportWidget.cancel_gesture(view)
    assert mode.anchor is None
    assert view.scene.ghosts == [None]
    assert view.statusMessage.sent


def test_a_click_takes_the_ghost_down(mode, one_carbon):
    """It was showing what the click would do, and the click has now
    done it."""
    widget = viewport_module()
    from PySide6.QtCore import QPoint

    centre = one_carbon.cell.cart[0]
    mode.anchor = (0, (0, 0, 0), centre)
    view = FakeViewport(mode, one_carbon, scene(one_carbon),
                        ray=(tuple(centre + [0.0, 8.0, -10.0]),
                             (0.0, 0.0, 1.0)))
    view._ghost = object()

    widget.ViewportWidget.pick_at(view, QPoint(10, 10))
    assert one_carbon.structure.n_sites == 2
    assert view.scene.ghosts == [None]


def test_escape_reaches_the_mode_through_the_event_filter(
        mode, one_carbon):
    """The unit above tests what Escape does; this tests that pressing
    it is what calls it -- the connection is where a key that appears
    to do nothing actually goes missing."""
    widget = viewport_module()
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    mode.anchor = (0, (0, 0, 0), one_carbon.cell.cart[0])
    view = FakeViewport(mode, one_carbon, scene(one_carbon))
    view._interactor = object()
    view._band_origin = None

    consumed = widget.ViewportWidget.eventFilter(
        view, view._interactor,
        QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
    assert consumed is True                 # VTK never sees it
    assert mode.anchor is None
