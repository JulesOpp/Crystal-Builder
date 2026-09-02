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

from PySide6.QtCore import Signal  # noqa: E402

from tests.test_app_shell import StubViewport  # noqa: E402
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
def square_document():
    """Four carbons on a square, close enough to bond each other."""
    document = Document(Structure.empty(Lattice.cubic(10.0)))
    for x in (0.485, 0.515):
        for y in (0.485, 0.515):
            document.add_atom("C", [x, y, 0.5])
    return document


@pytest.fixture
def one_carbon():
    """A single C at the middle of a roomy P1 box."""
    document = Document(Structure.empty(Lattice.cubic(20.0)))
    document.add_atom("C", [0.5, 0.5, 0.5])
    return document


def scene(document):
    return build_scene(document.structure, document.view)


def instance_of(model, atom: int):
    """The drawn row for P1 atom ``atom``, as the mode holds it."""
    return modes.drawn_instance(model, atom)


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


def test_the_anchor_moves_to_the_atom_just_placed(mode, one_carbon):
    """Drawing a chain is the same gesture repeated, so the mode stays
    in it: click, point, point.  Re-anchoring by hand between every
    pair would double the clicks of the one thing this is for."""
    mode.on_click(one_carbon, scene(one_carbon), ray_at(one_carbon, 0))
    mode.on_click(one_carbon, scene(one_carbon),
                  ray_at(one_carbon, 0, offset=(0.0, 8.0, -10.0)))

    placed = one_carbon.cell.cart[1]
    assert mode.anchor is not None
    assert mode.anchor[0] == 1
    assert np.allclose(mode.anchor[2], placed)
    assert sorted(one_carbon.selection.atoms) == [1]


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
    assert "chain ended" in mode.on_cancel(one_carbon)
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


# --------------------------------------------------------- the chain

def test_a_chain_is_one_click_per_atom(mode, one_carbon):
    """Click the carbon once, then point three times: four atoms and
    three bonds, and not one re-anchoring click in between."""
    model = scene(one_carbon)
    mode.on_click(one_carbon, model, ray_at(one_carbon, 0))
    for _ in range(3):
        atom = mode.anchor[0]
        model = scene(one_carbon)
        mode.on_click(one_carbon, model,
                      ray_at(one_carbon, atom, offset=(0.0, 8.0, -10.0)))

    assert one_carbon.structure.n_sites == 4
    assert len(one_carbon.graph.bonds) == 3


def test_every_link_of_the_chain_is_its_own_undo_step(mode, one_carbon):
    """One gesture, one atom, one Ctrl+Z -- a chain that undid all at
    once would be a chain you could not correct the end of."""
    mode.on_click(one_carbon, scene(one_carbon), ray_at(one_carbon, 0))
    mode.on_click(one_carbon, scene(one_carbon),
                  ray_at(one_carbon, 0, offset=(0.0, 8.0, -10.0)))
    mode.on_click(one_carbon, scene(one_carbon),
                  ray_at(one_carbon, 1, offset=(8.0, 0.0, -10.0)))
    assert one_carbon.structure.n_sites == 3

    one_carbon.undo()
    assert one_carbon.structure.n_sites == 2
    one_carbon.undo()
    assert one_carbon.structure.n_sites == 1


def test_carrying_on_says_so(mode, one_carbon):
    mode.on_click(one_carbon, scene(one_carbon), ray_at(one_carbon, 0))
    message = mode.on_click(one_carbon, scene(one_carbon),
                            ray_at(one_carbon, 0,
                                   offset=(0.0, 8.0, -10.0)))
    assert "carry on" in message and "Escape" in message


# ---------------------------------------------------------- the snap

def test_hovering_an_atom_snaps_the_ghost_onto_it(mode, one_carbon):
    """Whatever the distance: the ring being closed is wherever it is,
    and a ghost hanging a bond length short of it is a picture of the
    wrong answer."""
    one_carbon.add_atom("C", [0.8, 0.5, 0.5])       # 6 A away
    model = scene(one_carbon)
    mode.anchor = instance_of(model, 0)

    target = model.positions[1]
    ghost = mode.on_move(one_carbon, model,
                         modes.MoveEvent(tuple(target + [0, 0, -10]),
                                         (0.0, 0.0, 1.0)))
    assert np.allclose(ghost.position, target)
    reach = float(np.linalg.norm(ghost.position - model.positions[0]))
    assert reach > modes.bond_distance("C", "C") * 2


def test_a_snapped_ghost_swells_the_atom_it_is_on(mode, one_carbon):
    """A translucent sphere exactly over a solid one is invisible."""
    one_carbon.add_atom("O", [0.8, 0.5, 0.5])
    model = scene(one_carbon)
    mode.anchor = instance_of(model, 0)

    ghost = mode.on_move(
        one_carbon, model,
        modes.MoveEvent(tuple(model.positions[1] + [0, 0, -10]),
                        (0.0, 0.0, 1.0)))
    assert ghost.radius > float(model.radii[1])
    assert ghost.color == tuple(int(c) for c in model.colors[1])


def test_clicking_a_snapped_atom_bonds_instead_of_placing(
        mode, one_carbon):
    """What closes a ring.  Placing a second atom on top of the one
    that is already there is not that."""
    one_carbon.add_atom("C", [0.8, 0.5, 0.5])
    model = scene(one_carbon)
    mode.anchor = instance_of(model, 0)

    message = mode.on_click(
        one_carbon, model,
        modes.ClickEvent(tuple(model.positions[1] + [0, 0, -10]),
                         (0.0, 0.0, 1.0)))
    assert "bond added" in message
    assert one_carbon.structure.n_sites == 2        # nothing placed
    assert len(one_carbon.graph.bonds) == 1
    assert mode.anchor[0] == 1                      # chain carries on


def test_the_anchor_does_not_snap_to_itself(mode, one_carbon):
    """It is the atom the cursor is nearest for the first few pixels
    of every gesture, and an atom does not bond to itself."""
    model = scene(one_carbon)
    mode.anchor = instance_of(model, 0)

    ghost = mode.on_move(
        one_carbon, model,
        modes.MoveEvent(tuple(model.positions[0] + [0, 0, -10]),
                        (0.0, 0.0, 1.0)))
    assert not np.allclose(ghost.position, model.positions[0])
    assert float(np.linalg.norm(
        ghost.position - model.positions[0])) == pytest.approx(
            modes.bond_distance("C", "C"))


def test_a_click_anchors_the_copy_that_was_clicked(mode, quartz):
    """In a multi-cell view the copy in the home cell is a different
    atom in a different place from the one under the cursor."""
    document = Document(quartz)
    document.view.set_cells(2, 1, 1)
    model = build_scene(document.structure, document.view)
    row = next(i for i in range(model.n_atoms)
               if tuple(model.atom_cell[i]) == (1, 0, 0))

    point = model.positions[row] + np.array([0.0, 0.0, -10.0])
    mode.on_click(document, model,
                  modes.ClickEvent(tuple(point), (0.0, 0.0, 1.0)))
    assert mode.anchor[1] == (1, 0, 0)
    assert np.allclose(mode.anchor[2], model.positions[row])


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
        self.modes_set: list = []
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

    def set_mode(self, name):
        self.mode.on_deactivate(self.document)
        self.mode = modes.get(name)
        self.modes_set.append(name)


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


class ModeViewport(StubViewport):
    """A stub that holds a mode the way the real viewport does.

    Its ``set_mode`` and ``cancel_gesture`` are the real ones, because
    those are what the window talks to -- a stub with its own simpler
    versions would pass while the shipped pair was broken.
    """

    modeChanged = Signal(str)
    statusMessage = Signal(str)

    def __init__(self, document, parent=None):
        super().__init__(document, parent)
        self.mode = modes.get("select")
        self.scene = FakeScene()
        self._ghost = None

    def set_mode(self, name):
        self.mode.on_deactivate(self.document)
        self.mode = modes.get(name)
        self.modeChanged.emit(name)

    def set_ghost(self, ghost):
        from xtalapp.viewport.widget import ViewportWidget
        ViewportWidget.set_ghost(self, ghost)

    def cancel_gesture(self):
        from xtalapp.viewport.widget import ViewportWidget
        return ViewportWidget.cancel_gesture(self)

    def _safe_render(self):
        pass


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


def test_the_first_escape_ends_the_chain_and_the_second_leaves(
        mode, one_carbon):
    """Two different things to want.  The first Escape puts down state
    that is otherwise unreachable except by switching modes and back;
    the second means the user is finished, and Select is the mode a
    click can do no harm in."""
    widget = viewport_module()
    mode.anchor = (0, (0, 0, 0), one_carbon.cell.cart[0])
    view = FakeViewport(mode, one_carbon, scene(one_carbon))

    widget.ViewportWidget.cancel_gesture(view)
    assert mode.anchor is None
    assert view.modes_set == []                 # still in Add atom
    assert view.statusMessage.sent

    widget.ViewportWidget.cancel_gesture(view)
    assert view.modes_set == ["select"]


def test_escape_in_select_mode_goes_nowhere(one_carbon):
    """There is nothing past Select to escape to."""
    widget = viewport_module()
    view = FakeViewport(modes.get("select"), one_carbon,
                        scene(one_carbon))
    widget.ViewportWidget.cancel_gesture(view)
    assert view.modes_set == []


def test_leaving_a_mode_by_escape_releases_the_toolbar_button(
        qtbot, tmp_path, rutile_cif):
    """The viewport changes mode by itself, so the button cannot be
    what decides which mode is current -- a pressed Add atom over a
    viewport in Select is a picture of a mode nobody is in."""
    pytest.importorskip("pytestqt")
    from xtalapp.mainwindow import MainWindow
    from xtalapp.settings import AppSettings

    settings = AppSettings("CrystalBuilderTest", f"Mode{tmp_path.name}")
    settings.clear_recent_files()
    settings.last_directory = str(tmp_path)
    window = MainWindow(viewport_factory=ModeViewport,
                        settings=settings)
    qtbot.addWidget(window)
    window.open_path(rutile_cif)

    window.actions_["mode_add_atom"].trigger()
    assert window.actions_["mode_add_atom"].isChecked()

    window.current_viewport().set_mode("select")    # what Escape does
    assert window.actions_["mode_select"].isChecked()
    assert not window.actions_["mode_add_atom"].isChecked()


def test_every_two_click_mode_reports_what_escape_put_down(one_carbon):
    """Silence from ``on_cancel`` is what the viewport reads as
    "nothing was held, so leave the mode".  A mode that forgets its
    pending state silently would be left in a single Escape, taking
    the user out of a mode they were halfway through using."""
    one_carbon.add_atom("C", [0.6, 0.5, 0.5])
    pending = {"add_bond": ("pending", (0, (0, 0, 0))),
               "topology": ("pending", (0, (0, 0, 0))),
               "measure": ("picked", [0])}
    for name, (attribute, value) in pending.items():
        mode = modes.get(name)
        setattr(mode, attribute, value)
        assert mode.on_cancel(one_carbon), f"{name} said nothing"
        assert not getattr(mode, attribute)
        assert mode.on_cancel(one_carbon) == ""      # and then leaves


# --------------------------------------------- bonds are not perceived

def test_a_placed_atom_arrives_bonded_to_nothing(mode, one_carbon):
    """Bonds change when the user asks them to.  An atom appearing
    already bonded to whatever it happened to land near is that rule
    being broken by the one operation nobody expects to break it."""
    one_carbon.add_atom("H", [0.5 + 0.0545, 0.5, 0.5])   # 1.09 A
    assert len(one_carbon.graph.bonds) == 0
    assert "recalculated" in one_carbon.recompute_bonds()
    assert len(one_carbon.graph.bonds) == 1


def test_the_chain_bonds_only_what_it_was_told_to(mode, one_carbon):
    """Two clicks make one bond, not one bond plus whatever perception
    found on the way past."""
    one_carbon.add_atom("O", [0.5, 0.55, 0.5])      # 1 A from the C
    mode.on_click(one_carbon, scene(one_carbon), ray_at(one_carbon, 0))
    mode.on_click(one_carbon, scene(one_carbon),
                  ray_at(one_carbon, 0, offset=(0.0, 0.0, 8.0)))

    assert one_carbon.structure.n_sites == 3
    assert len(one_carbon.graph.bonds) == 1
    assert [b.kind for b in one_carbon.structure.bonds] == ["explicit"]


def test_reset_bonds_is_the_way_to_the_automatic_answer(one_carbon):
    one_carbon.add_atom("H", [0.5 + 0.0545, 0.5, 0.5])
    assert len(one_carbon.graph.bonds) == 0
    one_carbon.reset_bonds()
    assert len(one_carbon.graph.bonds) == 1


def test_a_centroid_does_not_perceive_either(square_document):
    document = square_document
    document.select([0, 1, 2, 3])
    document.add_centroid("C")          # a real element, close in
    assert len(document.graph.bonds) == 0


def test_add_hydrogens_still_bonds_what_it_adds(rutile_cif):
    """The other kind of edit, and the reason this is a flag and not a
    rule: Add hydrogens puts a hydrogen at a bond length from its
    parent and means the graph to find it."""
    from xtal.commands.atoms import AddSites, new_site

    document = Document.load(rutile_cif)
    before = len(document.graph.bonds)
    site = new_site("H", document.structure.sites[1].frac + [0.05, 0, 0])
    document.run(AddSites([site]))                  # perceive defaults on
    assert len(document.graph.bonds) > before


# ------------------------------------------------ Escape, from anywhere

def test_escape_is_a_window_action_and_not_a_viewport_key(
        qtbot, tmp_path, rutile_cif):
    """The bug this is here for: a key event goes to the widget that
    has focus, and entering a mode means pressing a toolbar button --
    so the viewport never saw the key and Escape did nothing at all.

    Two things have to hold, and each is a way it silently broke.  The
    action must be *on the window*, which is what makes a shortcut
    live for an action that is in no menu; and triggering it must
    reach the viewport.
    """
    pytest.importorskip("pytestqt")
    from xtalapp.mainwindow import MainWindow
    from xtalapp.settings import AppSettings

    settings = AppSettings("CrystalBuilderTest", f"Esc{tmp_path.name}")
    settings.clear_recent_files()
    settings.last_directory = str(tmp_path)
    window = MainWindow(viewport_factory=ModeViewport,
                        settings=settings)
    qtbot.addWidget(window)
    window.open_path(rutile_cif)
    window.actions_["mode_add_atom"].trigger()

    action = window.actions_["cancel_gesture"]
    assert action in window.actions(), \
        "an action in no menu needs adding to the window to have a key"

    add = modes.get("add_atom")
    add.anchor = (0, (0, 0, 0), np.zeros(3))
    window.element_combo.setFocus()             # where the focus is

    action.trigger()
    assert add.anchor is None
    action.trigger()
    assert window.current_viewport().mode.name == "select"


def test_escape_is_one_action_and_not_two(qtbot, tmp_path):
    """Two actions on the same key is an "ambiguous shortcut
    overload", which is Qt for neither of them firing -- and is what
    made the new binding do nothing next to Select None's."""
    pytest.importorskip("pytestqt")
    from PySide6.QtGui import QKeySequence

    from tests.test_app_shell import StubViewport
    from xtalapp.mainwindow import MainWindow
    from xtalapp.settings import AppSettings

    settings = AppSettings("CrystalBuilderTest", f"Esc2{tmp_path.name}")
    settings.clear_recent_files()
    settings.last_directory = str(tmp_path)
    window = MainWindow(viewport_factory=StubViewport,
                        settings=settings)
    qtbot.addWidget(window)

    escape = QKeySequence("Esc")
    on_escape = [name for name in window.actions_.names()
                 if escape in window.actions_[name].shortcuts()]
    assert on_escape == ["cancel_gesture"]


def test_escape_still_clears_the_selection_in_select_mode(
        qtbot, tmp_path, rutile_cif):
    """The last rung of the escalation, and where Escape has always
    ended up."""
    pytest.importorskip("pytestqt")
    from xtalapp.mainwindow import MainWindow
    from xtalapp.settings import AppSettings

    settings = AppSettings("CrystalBuilderTest", f"Esc3{tmp_path.name}")
    settings.clear_recent_files()
    settings.last_directory = str(tmp_path)
    window = MainWindow(viewport_factory=ModeViewport,
                        settings=settings)
    qtbot.addWidget(window)
    window.open_path(rutile_cif)
    document = window.current_document()
    document.select([0, 1])

    window.cancel_gesture()
    assert not document.selection.atoms


def test_undoing_an_add_does_not_perceive_again(one_carbon):
    """The atoms come out again, and the bonds are the ones that were
    there before -- not a fresh perception at whatever geometry the
    atoms are at now.  Bonds following a geometry they were never
    meant to follow, by way of an undo, is still bonds following a
    geometry."""
    one_carbon.add_atom("O", [0.5 + 0.062, 0.5, 0.5])
    one_carbon.recompute_bonds()
    assert len(one_carbon.graph.bonds) == 1

    one_carbon.select([1])
    one_carbon.move_selection([3.0, 0.0, 0.0], cartesian=True)
    assert len(one_carbon.graph.bonds) == 1     # bonds do not follow

    one_carbon.add_atom("N", [0.1, 0.1, 0.1])
    one_carbon.undo()
    assert len(one_carbon.graph.bonds) == 1
