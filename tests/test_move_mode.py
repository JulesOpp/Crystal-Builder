"""Dragging an atom where it should go.

The mode is the small half; the interesting half is what a drag *is*.
A press with no depth has to become a world position, a gesture that
runs for forty frames has to be one undo step, and nothing in it may
touch the bonding -- an atom dragged onto another is two atoms in the
same place and not a bond.
"""

from __future__ import annotations

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.commands import atoms as atom_commands
from xtal.core import p1
from xtal.core.structure import Bond
from xtalapp.document import Document
from xtalapp.viewport import modes
from xtalapp.viewport.builder import build_scene


def a_pair() -> Structure:
    """C and O along x in a roomy P1 box, bonded, well clear of the
    cell edges so that no drag here wraps."""
    structure = Structure.from_arrays(
        Lattice.cubic(10.0), ["C", "O"],
        [[0.30, 0.50, 0.50], [0.45, 0.50, 0.50]])
    structure.bonds.append(Bond(0, 1, (0, 0, 0), kind="single"))
    structure.touch()
    return structure


def ray(x: float, y: float, **kwargs) -> modes.DragRayEvent:
    """The cursor at (x, y) in the plane of the atoms, looking down
    +z from well outside the cell."""
    return modes.DragRayEvent((x, y, -20.0), (0.0, 0.0, 1.0), **kwargs)


def drag(mode, document, model, start, end, steps: int = 1, **kwargs):
    """Press at ``start``, travel to ``end``, release -- in ``steps``
    equal moves, because a drag is not a press and a release."""
    mode.on_drag_start(document, model, ray(*start, **kwargs))
    start, end = np.asarray(start, float), np.asarray(end, float)
    for step in range(1, steps + 1):
        point = start + (end - start) * (step / steps)
        mode.on_drag_move(document, model, ray(*point, **kwargs))
    return mode.on_drag_end(document, model, ray(*end, **kwargs))


@pytest.fixture
def scene():
    document = Document(a_pair())
    return document, build_scene(document.structure, document.view)


def test_dragging_an_atom_takes_it_where_the_cursor_went(scene):
    document, model = scene
    message = drag(modes.MoveMode(), document, model, (3.0, 5.0),
                   (4.0, 5.5), steps=8)

    assert np.allclose(document.structure.sites[0].frac,
                       [0.40, 0.55, 0.50])
    assert np.allclose(document.structure.sites[1].frac,
                       [0.45, 0.50, 0.50])       # the other one stayed
    assert message == "moved 1 site(s) by 1.118 A"


def test_a_press_on_the_background_is_left_to_the_camera(scene):
    """The mode takes the left button only while it has hold of
    something.  Taking it always would mean the crystal could not be
    turned without leaving the mode, which is how a mode becomes a
    tool that has to be put down."""
    document, model = scene
    mode = modes.MoveMode()

    assert mode.on_drag_start(document, model, ray(0.5, 0.5)) is False
    assert mode.plane is None
    assert not document.selection.atoms


def test_dragging_an_atom_of_the_selection_moves_all_of_it(scene):
    """Pick a fragment, then drag any atom of it: the whole fragment
    goes.  Otherwise the selection would have to be made again out of
    whatever the drag left behind."""
    document, model = scene
    document.select([0, 1])

    drag(modes.MoveMode(), document, model, (3.0, 5.0), (3.0, 6.0))

    assert np.allclose(document.structure.sites[0].frac,
                       [0.30, 0.60, 0.50])
    assert np.allclose(document.structure.sites[1].frac,
                       [0.45, 0.60, 0.50])
    assert document.selection.atoms == {0, 1}


def test_dragging_an_atom_outside_the_selection_takes_only_it(scene):
    document, model = scene
    document.select([1])

    drag(modes.MoveMode(), document, model, (3.0, 5.0), (3.0, 6.0))

    assert document.selection.atoms == {0}
    assert np.allclose(document.structure.sites[1].frac,
                       [0.45, 0.50, 0.50])


def test_shift_drag_adds_the_atom_to_what_is_already_held(scene):
    document, model = scene
    document.select([1])

    drag(modes.MoveMode(), document, model, (3.0, 5.0), (3.0, 6.0),
         additive=True)

    assert document.selection.atoms == {0, 1}
    assert np.allclose(document.structure.sites[1].frac,
                       [0.45, 0.60, 0.50])


def test_a_drag_changes_no_bonding_at_all(scene):
    """The invariant the whole feature is written under: bonds are
    what the user said they are until Recalculate Bonds is pressed.
    Dragging one atom on top of another does not bond them, and
    stretching a bond to four Angstrom does not break it."""
    document, model = scene
    before = [(b.i, b.j, b.image, b.kind)
              for b in document.structure.bonds]

    drag(modes.MoveMode(), document, model, (3.0, 5.0), (7.0, 5.0),
         steps=6)

    after = [(b.i, b.j, b.image, b.kind)
             for b in document.structure.bonds]
    assert after == before


def test_the_whole_gesture_is_one_undo_step(scene):
    """Forty frames of drag that came back one frame at a time would
    make the undo stack useless for anything else."""
    document, model = scene
    mode = modes.MoveMode()
    drag(mode, document, model, (3.0, 5.0), (4.0, 5.0), steps=40)

    document.undo()

    assert np.allclose(document.structure.sites[0].frac,
                       [0.30, 0.50, 0.50])
    assert not document.can_undo


def test_the_next_drag_is_a_different_undo_step(scene):
    """The release closes the merge window.  Without that the drag an
    hour later merges into the same step, and Ctrl+Z goes back
    further than anything the user remembers doing."""
    document, model = scene
    mode = modes.MoveMode()
    drag(mode, document, model, (3.0, 5.0), (4.0, 5.0))
    # The scene follows the structure, and the second press has to
    # find the atom where it now is.
    model = build_scene(document.structure, document.view)
    drag(mode, document, model, (4.0, 5.0), (4.0, 6.0))

    document.undo()

    assert np.allclose(document.structure.sites[0].frac,
                       [0.40, 0.50, 0.50])       # only the second went


def test_shift_alt_drag_moves_along_the_view_axis(scene):
    """The half of a placement the plane facing the camera cannot
    reach.  Up the screen is away from the viewer."""
    document, model = scene

    drag(modes.MoveMode(), document, model, (3.0, 5.0), (3.0, 6.0),
         steps=4, depth=True)

    assert np.allclose(document.structure.sites[0].frac,
                       [0.30, 0.50, 0.60])


# ================================================ alt: turning it


@pytest.fixture
def wide():
    """Two atoms 2 A apart across the middle of a roomy box, so that
    the pivot is at (6, 10, 10) and the radius is exactly 1 A -- one
    radian per Angstrom of drag, with no arithmetic to hide in."""
    document = Document(Structure.from_arrays(
        Lattice.cubic(20.0), ["C", "O"],
        [[0.25, 0.50, 0.50], [0.35, 0.50, 0.50]]))
    document.select([0, 1])
    return document, build_scene(document.structure, document.view)


def test_alt_drag_turns_the_selection_like_a_trackball(wide):
    """Dragging across the picture swings the near face of the
    selection that way: here the camera looks down +z with up +y, so
    screen-right is world -x, and the atom on the screen-left comes
    towards the viewer.

    One radius of travel is one radian, which is what makes the
    gesture feel the same on a linker and on a framework.
    """
    document, model = wide
    message = drag(modes.MoveMode(), document, model, (7.0, 10.0),
                   (6.0, 10.0), steps=5, rotate=True)

    turn = np.array([np.cos(1.0), 0.0, -np.sin(1.0)])
    assert np.allclose(document.cell.cart[1], [6, 10, 10] + turn)
    assert np.allclose(document.cell.cart[0], [6, 10, 10] - turn)
    assert message == "turned 2 site(s) by 57.3 deg"


def test_a_turn_is_rigid_and_leaves_the_middle_alone(wide):
    """A rotation that stretched the fragment or walked it off its
    pivot would be a worse way to place it than typing the angle."""
    document, model = wide
    before = document.cell.cart.copy()

    drag(modes.MoveMode(), document, model, (7.0, 10.0), (6.6, 10.4),
         steps=12, rotate=True)

    after = document.cell.cart
    assert np.isclose(np.linalg.norm(after[0] - after[1]),
                      np.linalg.norm(before[0] - before[1]))
    assert np.allclose(after.mean(axis=0), before.mean(axis=0))


def test_a_whole_turn_is_one_undo_step(wide):
    document, model = wide
    before = document.cell.cart.copy()

    drag(modes.MoveMode(), document, model, (7.0, 10.0), (6.0, 10.0),
         steps=30, rotate=True)
    document.undo()

    assert np.allclose(document.cell.cart, before)
    assert not document.can_undo


def test_turning_one_atom_says_so_rather_than_doing_nothing(scene):
    """A single site has no orientation, and a gesture that quietly
    does nothing is the one people report as broken."""
    document, model = scene
    mode = modes.MoveMode()
    before = document.cell.cart.copy()

    message = drag(mode, document, model, (3.0, 5.0), (4.0, 5.0),
                   rotate=True)

    assert "no orientation" in message
    assert np.allclose(document.cell.cart, before)


def test_the_copies_under_the_cursor_turn_with_it_too(rutile):
    """The rotating half of the image rule: what turns is the drawn
    atoms, and each site moves to whatever puts its image there.

    One image per site, which is all a rotation of the asymmetric unit
    can promise -- two images of the same site cannot both be granted
    the same turn, and the first of them is the one that gets it.
    """
    cell = p1.expand(rutile)
    first: dict = {}
    for atom, site in enumerate(cell.site_idx):
        first.setdefault(int(site), atom)
    atoms = sorted(first.values())
    centre = cell.cart[atoms].mean(axis=0)
    matrix = atom_commands.rotation_matrix((0, 0, 1), 30.0)

    command = atom_commands.MoveSites.by_image_rotation(
        rutile, cell, atoms, (0, 0, 1), 30.0, centre)

    for atom in atoms:
        rotation, translation = p1.image_transform(rutile, cell, atom)
        parent = command.targets[int(cell.site_idx[atom])]
        image = rutile.lattice.to_cart(rotation @ parent + translation)
        assert np.allclose(image,
                           centre + matrix @ (cell.cart[atom] - centre))


def test_the_copy_under_the_cursor_is_the_one_that_follows_it(rutile):
    """In P4_2/mnm the image the user has hold of is generated by an
    operation, so displacing its *parent* by the cursor's travel slides
    it off sideways.  The site moves by the inverse, and the atom being
    dragged goes where the cursor goes."""
    document = Document(rutile)
    model = build_scene(document.structure, document.view)
    rotated = [row for row in range(model.n_atoms)
               if document.cell.op_idx[int(model.atom_index[row])]]
    position = np.asarray(model.positions[rotated[0]], dtype=float)

    mode = modes.MoveMode()
    mode.on_drag_start(document, model,
                       modes.DragRayEvent(tuple(position - [0, 0, 20.0]),
                                          (0.0, 0.0, 1.0)))
    atom = sorted(document.selection.atoms)[0]
    before = document.cell.cart[atom].copy()
    mode.on_drag_end(document, model,
                     modes.DragRayEvent(tuple(position - [-0.2, 0, 20.0]),
                                        (0.0, 0.0, 1.0)))

    assert np.allclose(document.cell.cart[atom] - before, [0.2, 0.0, 0.0])
    assert document.cell.op_idx[atom]            # not the identity


def test_a_click_in_move_mode_still_selects(scene):
    """A press that took nothing is still a click, and the background
    is where a click means 'select nothing'."""
    document, model = scene
    document.select([0, 1])
    mode = modes.MoveMode()

    assert mode.on_click(document, model, modes.ClickEvent(
        (0.5, 0.5, -20.0), (0.0, 0.0, 1.0))) == ""
    assert not document.selection.atoms

    mode.on_click(document, model, modes.ClickEvent(
        (3.0, 5.0, -20.0), (0.0, 0.0, 1.0)))
    assert document.selection.atoms == {0}


def test_move_is_one_of_the_mouse_modes():
    """Registration is the whole of putting it in the menu and on the
    toolbar -- both are generated from ``modes.names()``."""
    assert "move" in modes.names()
    assert modes.get("move").wants_drag is True
    assert modes.get("move").drag_style == "ray"


# ============================================ the drag, from the widget

class FakeSignal:
    def __init__(self):
        self.sent: list = []

    def emit(self, text):
        self.sent.append(text)


class FakeCamera:
    def GetFocalPoint(self):
        return (0.0, 0.0, 0.0)

    def GetViewUp(self):
        return (0.0, 1.0, 0.0)


class FakeScene:
    class renderer:                             # noqa: N801
        @staticmethod
        def GetActiveCamera():
            return FakeCamera()


class FakeViewport:
    """Enough of ViewportWidget to run the ray-drag handlers unbound.

    The ray comes from the widget position with no VTK in it, which is
    what makes the press-and-release plumbing testable without a render
    window.
    """

    def __init__(self, mode, document, model):
        self.mode = mode
        self.document = document
        self.model = model
        self.scene = FakeScene()
        self._ray_drag = False
        self._press_position = None
        self.statusMessage = FakeSignal()

    def _ray_at(self, point):
        return (np.array([point.x(), point.y(), -20.0]),
                np.array([0.0, 0.0, 1.0]))

    def _ray_event(self, event):
        from xtalapp.viewport import widget
        return widget.ViewportWidget._ray_event(self, event)


def _mouse_event(x, y, modifiers=None):
    from PySide6.QtCore import QPoint, Qt

    held = Qt.NoModifier if modifiers is None else modifiers

    class FakeEvent:
        def position(self):
            class P:
                def toPoint(self):
                    return QPoint(x, y)
            return P()

        def modifiers(self):
            return held

    return FakeEvent()


def test_what_the_modifiers_mean_to_a_drag(scene):
    """Alt claims the gesture and shift is read inside it: alt turns,
    shift-alt moves in depth, and neither is a drag in which adding an
    atom to the selection means anything.  Shift on its own is what it
    is everywhere else in the application."""
    pytest.importorskip("PySide6")
    from PySide6.QtCore import Qt

    from xtalapp.viewport import widget

    document, model = scene
    view = FakeViewport(modes.MoveMode(), document, model)

    def read(modifiers):
        event = widget.ViewportWidget._ray_event(
            view, _mouse_event(3, 5, modifiers))
        return event.additive, event.rotate, event.depth

    assert read(Qt.NoModifier) == (False, False, False)
    assert read(Qt.ShiftModifier) == (True, False, False)
    assert read(Qt.ControlModifier) == (True, False, False)
    assert read(Qt.AltModifier) == (False, True, False)
    assert read(Qt.AltModifier | Qt.ShiftModifier) == (False, False,
                                                       True)


def test_the_button_is_taken_only_when_the_mode_has_hold_of_something(
        scene):
    """The press is offered to the mode, and whether it took it is
    whether VTK sees the event.  A drag on the background has to reach
    the trackball or the view is stuck."""
    pytest.importorskip("PySide6")
    from xtalapp.viewport import widget

    document, model = scene
    view = FakeViewport(modes.MoveMode(), document, model)

    assert widget.ViewportWidget._begin_ray_drag(
        view, _mouse_event(0, 0)) is False       # empty space
    assert view._ray_drag is False
    assert widget.ViewportWidget._begin_ray_drag(
        view, _mouse_event(3, 5)) is True        # the carbon
    assert view._ray_drag is True


def test_the_release_ends_the_drag_and_says_how_far_it_went(scene):
    pytest.importorskip("PySide6")
    from xtalapp.viewport import widget

    document, model = scene
    view = FakeViewport(modes.MoveMode(), document, model)
    widget.ViewportWidget._begin_ray_drag(view, _mouse_event(3, 5))
    widget.ViewportWidget._drag_ray(view, _mouse_event(4, 5))
    widget.ViewportWidget._finish_ray_drag(view, _mouse_event(4, 5))

    assert view._ray_drag is False
    assert view._press_position is None
    assert view.statusMessage.sent == ["moved by 1.000 A",
                                       "moved 1 site(s) by 1.000 A"]
    assert np.allclose(document.structure.sites[0].frac,
                       [0.40, 0.50, 0.50])
