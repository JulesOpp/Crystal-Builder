"""
xtalapp.viewport.modes
======================
Interaction modes: what a click means right now.

A mode is a small state machine with a name, a cursor hint, and
handlers for the events it cares about.  The viewport owns one active
mode and forwards clicks to it; the camera (rotate, zoom, pan) is
handled by VTK underneath and is never a mode, because you always want
to be able to turn the structure.

Select, add-atom, add-bond, box-select and measure are each their own
mode and slot in here without the viewport changing.

Most modes want a click; box select wants a press, a drag and a
release, so a mode may declare ``wants_drag`` and receive a
:class:`DragEvent` instead.  That flag is what stops the left button
being handed to VTK's trackball while such a mode is active, because a
rubber band and a camera rotation are the same gesture and cannot both
have it.

A drag is two different gestures, and ``drag_style`` says which this
mode means.  ``"band"`` is a rectangle on the screen, reported once
when the button comes up, which is all a rubber band can be.
``"ray"`` is a gesture *in the scene*: the mode is asked at the press
whether it takes the drag at all -- Move takes it over an atom and
leaves it to the camera over the background -- and then gets every
intermediate position as a :class:`DragRayEvent`, because moving an
atom that only arrives where it was let go is not a drag.

Modes read what was clicked from the scene model's provenance arrays,
never from the geometry: a drawn atom knows which atom of the P1 cell
it is *and* which lattice translation put it there, and a bond half
knows the (i, j, image) of the bond it draws.  Reconstructing any of
that from coordinates is how a click ends up joining the wrong pair.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from xtal.core.bonding import bond_distance
from xtal.core.structure import CHEMISTRY
from xtalapp.viewport import picking, styles
from xtalapp.viewport.scene import Ghost


class RayEvent:
    """A pointer position over the viewport, as a ray into the scene.

    Shared by the click and the move, because placing an atom and
    showing the atom that would be placed have to agree about where
    the cursor is pointing -- two spellings of that would drift apart
    and the ghost would stop landing where the click does.
    """

    def plane_point(self):
        """Where this ray meets the plane through the camera's focal
        point, facing the camera.

        A click carries no depth, so placing an atom needs a plane to
        put it on; the plane the camera is focused on is the one the
        user is looking at, and is what every builder uses.
        """
        origin = np.asarray(self.origin, dtype=float)
        direction = np.asarray(self.direction, dtype=float)
        focal = np.asarray(self.focal, dtype=float)
        denominator = float(direction @ direction)
        if denominator < 1e-12:
            return focal
        t = float((focal - origin) @ direction) / denominator
        return origin + direction * t


@dataclass
class ClickEvent(RayEvent):
    """One click, in the terms a mode cares about."""

    origin: tuple            # ray origin, world coordinates
    direction: tuple         # unit ray direction
    additive: bool = False   # shift / cmd held: extend the selection
    double: bool = False
    focal: tuple = (0.0, 0.0, 0.0)   # what the camera is looking at


@dataclass
class MoveEvent(RayEvent):
    """The cursor moved over the viewport with no button down.

    A mode that wants these says so with ``wants_move``, and the
    viewport only casts the ray for the ones that do.  It answers the
    same question a click does -- what is under the cursor, and where
    is it pointing -- without committing to anything, which is what a
    ghost atom and (later) a tooltip both need.
    """

    origin: tuple
    direction: tuple
    focal: tuple = (0.0, 0.0, 0.0)


@dataclass
class DragEvent:
    """A press, a drag and a release over the viewport.

    In *display* coordinates -- pixels from the bottom left, the way
    VTK counts them -- because that is the space a rubber band is drawn
    in and the space the atoms have to be projected into to be tested
    against it.  Turning it into world coordinates would mean choosing
    a depth, and the whole point of a box is that it has none.

    ``project`` maps an (M, 3) array of world positions to (M, 2)
    display coordinates.  It is passed in rather than reached for, so
    this module keeps knowing nothing about VTK.
    """

    start: tuple             # where the button went down
    end: tuple               # where it came up
    additive: bool = False   # shift / cmd held: extend the selection
    project: object = None

    def rectangle(self) -> tuple:
        """``((x0, y0), (x1, y1))`` with the corners in order, so a box
        dragged up and to the left is the same box as one dragged down
        and to the right."""
        x0, x1 = sorted((float(self.start[0]), float(self.end[0])))
        y0, y1 = sorted((float(self.start[1]), float(self.end[1])))
        return (x0, y0), (x1, y1)


@dataclass
class DragRayEvent(RayEvent):
    """One step of a drag that means something in the scene.

    Rays rather than the display coordinates a :class:`DragEvent`
    carries, and for the opposite reason: a rubber band is a rectangle
    on the screen and must have no depth, while moving an atom is
    entirely a question of where a screen movement lands in the world,
    which only a ray can answer.

    ``up`` is the camera's, and is here for the two things a plane
    facing the camera cannot express on its own: with ``depth`` set the
    movement means towards or away from the viewer instead of across
    the picture, and with ``rotate`` set it means a turn, for which the
    screen's own two axes are what the cursor is moving along.
    """

    origin: tuple
    direction: tuple
    focal: tuple = (0.0, 0.0, 0.0)
    up: tuple = (0.0, 1.0, 0.0)
    additive: bool = False   # shift / cmd held: extend the selection
    rotate: bool = False     # alt: turn what is held, do not move it
    depth: bool = False      # shift-alt: along the view axis instead


class Mode:
    """Base class: a mode may ignore any event it does not use."""

    name = "mode"
    label = "Mode"
    hint = ""
    #: Does this mode want press-drag-release rather than a click?  The
    #: viewport withholds the left button from VTK's camera while a
    #: mode that does is active -- for a ``"ray"`` drag, only for as
    #: long as the mode says it has hold of something.
    wants_drag = False
    #: ``"band"`` for a rubber band reported at the release, ``"ray"``
    #: for a gesture in the scene reported as it happens.  Read only
    #: when ``wants_drag`` is set.
    drag_style = "band"
    #: Does this mode want to know where the cursor is between clicks?
    #: Casting a ray per mouse move for the modes that would ignore it
    #: is a cost with nothing on the other side of it, so they ask.
    wants_move = False

    def on_activate(self, document, model) -> str:
        """Entering the mode: what it can say for itself right now.

        The message replaces the hint in the status bar when there is
        one, which is how a mode that starts in the middle of its own
        state machine -- Add atom with an atom already selected -- can
        say so instead of describing a first click that will not
        happen.
        """
        return ""

    def on_click(self, document, model, event: ClickEvent) -> str:
        return ""

    def on_drag(self, document, model, event: DragEvent) -> str:
        return ""

    def on_drag_start(self, document, model,
                      event: DragRayEvent) -> bool:
        """The button went down: does this mode take the drag?

        ``False`` hands the gesture back to the camera, which is what
        makes a scene drag a mode rather than a cage -- Move takes a
        press on an atom and leaves a press on the background to the
        trackball, so the crystal can still be turned while the mode
        is active.
        """
        return False

    def on_drag_move(self, document, model,
                     event: DragRayEvent) -> str:
        return ""

    def on_drag_end(self, document, model,
                    event: DragRayEvent) -> str:
        return ""

    def on_move(self, document, model, event: MoveEvent):
        """Where the cursor is now.  Returns what to draw over the
        scene -- a :class:`~xtalapp.viewport.scene.Ghost` -- or None
        for nothing."""
        return None

    def on_cancel(self, document) -> str:
        """Escape: abandon a half-finished gesture, in place.

        The same forgetting that leaving the mode does, without
        leaving it -- because a mode waiting for a second click is
        holding state with no other way out of it.
        """
        self.on_deactivate(document)
        return ""

    def on_structure_changed(self, document, change: int) -> str:
        """The structure changed between two clicks of a gesture.

        What a mode holds between clicks -- the first end of a bond,
        the first vertex of a net edge, the atoms gathered for a
        measurement, an add-atom anchor -- is P1 atom indices, and an
        edit that adds or removes sites renumbers the cell under them.
        Delete the atom a Draw net gesture had started from and the
        next click asked for atom 102 of 99; delete a different one and
        the index is still in range and names somebody else, which
        bonds the wrong pair without a word.  So the gesture is put
        down, as Escape would put it down.  A move keeps the numbering
        and keeps the gesture.  A mode's own edit lands here too, which
        is harmless: each one sets its state again after the edit.
        """
        if change and not (change & int(CHEMISTRY)):
            return ""
        return self.on_cancel(document)

    def on_deactivate(self, document) -> None:
        pass


class SelectMode(Mode):
    """Click an atom or bond to select it; click nothing to clear.

    Holding shift (or command) extends the selection instead of
    replacing it, and a double-click grows to the whole connected
    fragment -- the fastest way to grab one molecule out of a cell.
    """

    name = "select"
    label = "Select"
    hint = ("click an atom or bond · shift-click to add · "
            "double-click for the whole fragment")

    def on_click(self, document, model, event: ClickEvent) -> str:
        kind, index = picking.pick(model, event.origin, event.direction)

        if kind is None:
            if not event.additive:
                document.select_none()
            return ""

        if kind == "atom":
            atom, _cell = model.instance(index)
            document.select([atom],
                            "toggle" if event.additive else "set")
            if event.double:
                document.expand_selection("fragment")
            return f"{model_element(document, atom)} selected"

        if kind == "topology":
            # Reached only where the ray met nothing else, so this is
            # a click on the span of a net edge.  Named explicitly
            # rather than falling through: the index is into the
            # edges, and handing it to bond_key would select whatever
            # chemical bond happened to share the number.
            document.select_topology(
                model.topology_key(index),
                "toggle" if event.additive else "set")
            return "net edge selected -- Del removes it"

        document.select_bond(model.bond_key(index),
                             "toggle" if event.additive else "set")
        return "bond selected"


def model_element(document, atom: int) -> str:
    cell = document.cell
    label = cell.labels[atom] or cell.elements[atom]
    return f"{label}"


def point_on_sphere(origin, direction, centre, radius):
    """Where a ray meets the sphere of ``radius`` about ``centre``.

    The near intersection when the ray hits it, because that is the
    face of the sphere the user is looking at.  When the ray misses --
    which is most of the screen, the sphere being about one Angstrom
    across -- the closest approach is projected back onto the sphere
    instead, so pointing *that way* still places the atom that way.
    Refusing a miss would make the second click of the gesture fail
    almost everywhere it is aimed.
    """
    origin = np.asarray(origin, dtype=float)
    centre = np.asarray(centre, dtype=float)
    direction = np.asarray(direction, dtype=float)
    length = float(np.linalg.norm(direction))
    if length < 1e-12:                              # pragma: no cover
        return centre + np.array([radius, 0.0, 0.0])
    direction = direction / length

    offset = origin - centre
    along = float(offset @ direction)
    gap = float(offset @ offset) - radius * radius
    discriminant = along * along - gap
    if discriminant >= 0.0:
        root = float(np.sqrt(discriminant))
        near, far = -along - root, -along + root
        t = near if near > 0.0 else far
        if t > 0.0:
            return centre + _to_radius(origin + direction * t - centre,
                                       direction, radius)
    closest = origin - direction * along        # the ray's near point
    return centre + _to_radius(closest - centre, direction, radius)


def _to_radius(offset, direction, radius):
    """``offset`` scaled to ``radius``, or a direction when it has
    none: a ray straight down the middle of the anchor says nothing
    about where to put the atom, so it goes towards the camera."""
    length = float(np.linalg.norm(offset))
    if length < 1e-9:
        return -np.asarray(direction, dtype=float) * radius
    return np.asarray(offset, dtype=float) / length * radius


def instance_at(model, row: int) -> tuple:
    """The drawn atom in ``row``: ``(P1 atom, translation, position)``.

    The copy that was *picked*, translation and all.  Looking the
    atom up again by index would find the copy in the home cell, and
    in a multi-cell view that is a different atom in a different place
    from the one under the cursor.
    """
    return (int(model.atom_index[row]),
            tuple(int(v) for v in model.atom_cell[row]),
            np.asarray(model.positions[row], dtype=float))


def drawn_instance(model, atom: int):
    """One drawn copy of P1 atom ``atom``: ``(atom, cell, position)``.

    The copy in the home cell when it is on screen, because that is
    the one a user with a single atom selected is looking at; any
    other copy otherwise, because a display range that starts at
    (1, 0, 0) still has to be able to anchor.  Where a click said
    which copy, :func:`instance_at` is the one to use instead.
    """
    if model is None or not model.n_atoms:
        return None
    rows = np.flatnonzero(np.asarray(model.atom_index) == int(atom))
    if not len(rows):
        return None
    home = [r for r in rows if not np.any(model.atom_cell[r])]
    return instance_at(model, int(home[0] if home else rows[0]))


#: How much bigger than the atom itself the ghost is drawn when it has
#: snapped onto one.  A translucent sphere exactly over a solid one is
#: invisible; a slightly larger one reads as "this atom", which is
#: what the snap has to say.
SNAP_GROWTH = 1.35


class AddAtomMode(Mode):
    """Click to place an atom of the current element.

    Over empty space the atom lands on the plane the camera is focused
    on, which is the only depth a single click can mean.  Over an atom
    the click means something else entirely -- "another atom bonded to
    this one" -- and landing it at whatever depth the focal plane
    happened to be is never that.  So a click on an atom *anchors*
    rather than places, and the next click carries only a direction:
    the atom goes at the bond distance for the pair, and the bond goes
    with it.

    **The anchor has two spellings.**  With exactly one atom selected,
    entering the mode starts already anchored -- pick the carbon,
    press the button, point -- and with nothing selected the first
    click anchors and the second directs.  They are the same state
    machine entered at different points, and the short one is what an
    experienced user will actually use.

    **Then the anchor moves to what was just placed.**  Drawing a
    chain is the common case and it is the same gesture repeated, so
    the mode stays in it: click, point, point, point.  Re-anchoring by
    hand between every pair would double the clicks of the one thing
    this mode is for.

    **Hovering an existing atom snaps to it**, whatever the distance,
    and the click then bonds to that atom instead of placing a new
    one.  That is what closes a ring: the last atom of a chain has to
    join one that is already there, and placing a second atom on top
    of it at a bond length is not that.

    Between the clicks a ghost atom follows the cursor with its bond
    drawn, so what the click will do is visible before it does it.
    ``Escape`` ends the chain, and a second ``Escape`` -- with nothing
    left to end -- leaves the mode.
    """

    name = "add_atom"
    label = "Add atom"
    hint = ("click to place an atom · click an atom to build from "
            "it, then keep clicking to chain · Escape stops")
    wants_move = True

    def __init__(self, element: str = "C"):
        self.element = element
        # The atom being bonded to, as (P1 index, lattice translation,
        # cartesian position).  The translation is what makes the copy
        # that was clicked the copy that gets the bond.
        self.anchor: tuple | None = None

    def on_activate(self, document, model) -> str:
        """A single selected atom is already an anchor.

        The cheaper half of the same gesture: the common case is
        picking the atom to extend and then reaching for the button,
        and having to click it a second time to say the same thing is
        the click this removes.
        """
        self.anchor = None
        if document is None:
            return ""
        atoms = sorted(document.selection.atoms)
        if len(atoms) != 1:
            return ""
        self.anchor = drawn_instance(model, atoms[0])
        if self.anchor is None:
            return ""
        return (f"bonding to {model_element(document, atoms[0])} "
                f"· click a direction · Escape to place freely")

    def on_deactivate(self, document) -> None:
        self.anchor = None

    def on_cancel(self, document) -> str:
        if self.anchor is None:
            return ""
        self.anchor = None
        return "chain ended · the next click places an atom"

    def on_move(self, document, model, event: MoveEvent):
        """What the next click would do, drawn."""
        if document is None or self.anchor is None:
            return None
        _atom, _cell, centre = self.anchor
        view = document.view
        row = self._snap_row(model, event.origin, event.direction)
        if row is not None:
            # Snapped: the ghost swells the atom under the cursor
            # rather than showing a new one, because the click will
            # bond to it and place nothing.
            return Ghost(position=np.asarray(model.positions[row],
                                             dtype=float),
                         radius=float(model.radii[row]) * SNAP_GROWTH,
                         color=tuple(int(c) for c in model.colors[row]),
                         anchor=centre,
                         bond_radius=view.bond_radius)
        return Ghost(position=self._free_point(document, event),
                     radius=styles.get(view.style).atom_radius(
                         self.element, view),
                     color=view.color_for(self.element),
                     anchor=centre,
                     bond_radius=view.bond_radius)

    def on_click(self, document, model, event: ClickEvent) -> str:
        if document is None:
            return ""
        if self.anchor is not None:
            return self._extend(document, model, event)

        kind, index = picking.pick(model, event.origin, event.direction)
        if kind == "atom":
            # The copy that was clicked, translation and all: in a
            # multi-cell view the copy in the home cell is a different
            # atom somewhere else.
            self.anchor = instance_at(model, index)
            atom = self.anchor[0]
            document.select([atom])
            return (f"bonding to {model_element(document, atom)} "
                    f"· click a direction · Escape to stop")

        point = event.plane_point()
        frac = document.structure.lattice.to_frac(point)
        return document.add_atom(self.element, frac)

    # -- the anchored half ---------------------------------------------

    def _snap_row(self, model, origin, direction):
        """The drawn atom under the cursor to bond to, or ``None``.

        The anchor itself is not one: an atom does not bond to itself,
        and the anchor is the atom the cursor is nearest to for the
        first few pixels of every gesture.
        """
        if model is None or self.anchor is None:
            return None
        kind, index = picking.pick(model, origin, direction)
        if kind != "atom":
            return None
        if instance_at(model, index)[:2] == self.anchor[:2]:
            return None
        return int(index)

    def _free_point(self, document, event):
        """Where the new atom goes: a bond length from the anchor, in
        the direction the cursor is pointing."""
        atom, _cell, centre = self.anchor
        distance = bond_distance(document.cell.elements[atom],
                                 self.element)
        return point_on_sphere(event.origin, event.direction, centre,
                               distance)

    def _extend(self, document, model, event: ClickEvent) -> str:
        """The direction click, and the one after it.

        Either a bond to the atom under the cursor or a new atom at a
        bond length; either way the anchor moves to the far end, so
        the next click carries the chain on.
        """
        row = self._snap_row(model, event.origin, event.direction)
        if row is not None:
            return self._bond_to(document, instance_at(model, row))

        atom, cell, _centre = self.anchor
        point = self._free_point(document, event)
        frac = document.structure.lattice.to_frac(point)
        message, placed = document.add_bonded_atom(
            self.element, frac, atom, cell)
        self._move_anchor(document, (placed[0], placed[1], point))
        return f"{message} · click again to carry on · Escape to stop"

    def _bond_to(self, document, target: tuple) -> str:
        """Join the anchor to an atom that is already there -- which is
        how a chain closes a ring."""
        atom, cell, _centre = self.anchor
        try:
            message = document.add_bond_between(atom, target[0], cell,
                                                target[1])
        except ValueError as exc:
            self.anchor = None
            document.select_none()
            return str(exc)
        self._move_anchor(document, target)
        return f"{message} · click again to carry on · Escape to stop"

    def _move_anchor(self, document, instance: tuple) -> None:
        """Carry the chain on from ``instance``, and show where it is.

        Selected as well as anchored: the anchor is otherwise
        invisible, and a chain being drawn from an atom the user
        cannot pick out is a chain drawn by guesswork.
        """
        self.anchor = instance
        document.select([instance[0]])


class AddBondMode(Mode):
    """Click two atoms to bond them; click a bond to remove it.

    The first atom stays selected while it waits for the second, so the
    pending end of the bond is visible.
    """

    name = "add_bond"
    label = "Add bond"
    hint = "click two atoms to bond them · click a bond to remove it"

    def __init__(self):
        # The atom clicked first, as (P1 index, lattice translation):
        # the translation matters, because in a multi-cell view the
        # copy that was clicked is the one the bond should join.
        self.pending: tuple | None = None

    def on_deactivate(self, document) -> None:
        self.pending = None

    def on_cancel(self, document) -> str:
        """Escape puts down the first end.  Saying so is what makes it
        the *first* stage: silence here means nothing was held, and
        the viewport takes that as leave-the-mode."""
        if self.pending is None:
            return ""
        self.pending = None
        return "first atom dropped"

    def on_click(self, document, model, event: ClickEvent) -> str:
        if document is None:
            return ""
        kind, index = picking.pick(model, event.origin, event.direction)

        if kind == "bond":
            i, j, image = model.bond_key(index)
            self.pending = None
            return document.remove_bond_between(i, j, (0, 0, 0), image)

        if kind is None:
            self.pending = None
            document.select_none()
            return "cancelled"

        atom, cell = model.instance(index)
        if self.pending is None:
            self.pending = (atom, cell)
            document.select([atom])
            return "pick the second atom"
        first, first_cell = self.pending
        if (atom, cell) == self.pending:
            return "pick a different atom"

        self.pending = None
        try:
            message = document.add_bond_between(first, atom,
                                                first_cell, cell)
        except ValueError as exc:
            document.select_none()
            return str(exc)
        document.select([first, atom])
        return message


class BoxSelectMode(Mode):
    """Drag a box over the viewport and take everything inside it.

    The fastest way to grab a slab, a surface layer, or one end of a
    long molecule.

    **Everything inside, front to back.**  The atoms hidden behind the
    ones you can see are taken as well, which is what VESTA does and
    what makes the gesture useful for a slab -- a box that took only
    the visible face would need to be dragged once per layer.  It is
    also the one thing about it that can surprise, so the status bar
    says how many were taken and that they came from all the way
    through.

    **And the bonds between them.**  A box is how a fragment gets
    named, and the bonds inside a named fragment are part of what was
    named -- so Set Bond Type after a box acts on the linker that was
    boxed, rather than on nothing at all.  A bond with one end outside
    the box is not inside it and is not taken.

    Rotating is not available while this mode is active: the left
    button cannot both draw a box and turn the crystal.  Panning and
    zooming still work, and the select mode next door still rotates.
    """

    name = "box_select"
    label = "Box select"
    hint = ("drag a box over the atoms - shift to add - everything "
            "inside is taken, bonds included, front to back")
    wants_drag = True

    def on_click(self, document, model, event: ClickEvent) -> str:
        """A press that did not travel is still a click.

        Missing this makes the mode feel broken: the user drags a box,
        then clicks one atom to add it, and nothing happens.
        """
        return SelectMode().on_click(document, model, event)

    def on_drag(self, document, model, event: DragEvent) -> str:
        if document is None or model is None or model.n_atoms == 0:
            return ""
        if event.project is None:               # pragma: no cover
            return ""
        display = np.asarray(event.project(model.positions), dtype=float)
        (x0, y0), (x1, y1) = event.rectangle()
        inside = ((display[:, 0] >= x0) & (display[:, 0] <= x1)
                  & (display[:, 1] >= y0) & (display[:, 1] <= y1))

        atoms = sorted({int(a) for a in model.atom_index[inside]})
        if not atoms:
            if not event.additive:
                document.select_none()
            return "nothing in the box"
        # The bonds between them come too: a box drawn round a linker
        # is a way of naming that linker, and having to click its
        # eleven bonds one at a time afterwards to set their type is
        # the gesture this mode exists to replace.
        document.select(atoms, "add" if event.additive else "set",
                        with_bonds=True)
        bonds = len(document.selection.bonds)
        return (f"{len(atoms)} atom(s) and {bonds} bond(s) in the box, "
                f"front to back")


class DrawTopologyMode(Mode):
    """Click two atoms to draw an edge of the underlying net.

    A net -- **pcu**, **fcu**, **soc** -- is not a bond graph.  It is
    what is left after deciding which parts of a framework are nodes
    and which are linkers, and that decision belongs to a chemist and
    not to a distance criterion.  This is where the decision gets made.

    The edge expands over the symmetry orbit like every other bond,
    which is what makes drawing one edge of a **pcu** net draw all six.
    Clicking an edge selects it, and ``Del`` removes it.
    """

    name = "topology"
    label = "Draw net"
    hint = ("click two atoms to draw a net edge - click an edge to "
            "select it, Del removes it")

    def __init__(self):
        self.pending: tuple | None = None

    def on_deactivate(self, document) -> None:
        self.pending = None

    def on_cancel(self, document) -> str:
        if self.pending is None:
            return ""
        self.pending = None
        return "first vertex dropped"

    def on_click(self, document, model, event: ClickEvent) -> str:
        if document is None:
            return ""
        kind, index = picking.pick(model, event.origin, event.direction,
                                   prefer_topology=True)

        if kind == "topology":
            self.pending = None
            document.select_topology(model.topology_key(index),
                                     "toggle" if event.additive
                                     else "set")
            return "net edge selected -- Del removes it"

        if kind != "atom":
            self.pending = None
            document.select_none()
            return "cancelled"

        atom, cell = model.instance(index)
        if self.pending is None:
            self.pending = (atom, cell)
            document.select([atom])
            return "pick the second vertex"
        first, first_cell = self.pending
        if (atom, cell) == self.pending:
            return "pick a different atom"

        self.pending = None
        try:
            message = document.add_topology_bond_between(
                first, atom, first_cell, cell)
        except ValueError as exc:
            document.select_none()
            return str(exc)
        document.select([first, atom])
        return message


def point_on_plane(origin, direction, point, normal):
    """Where a ray meets the plane through ``point`` with ``normal``.

    ``point`` itself when the ray runs along the plane, which happens
    only if the camera has been turned exactly edge-on to it during
    the gesture; refusing would mean the drag stopped following the
    cursor instead of standing still.
    """
    origin = np.asarray(origin, dtype=float)
    direction = np.asarray(direction, dtype=float)
    point = np.asarray(point, dtype=float)
    normal = np.asarray(normal, dtype=float)
    denominator = float(direction @ normal)
    if abs(denominator) < 1e-9:                     # pragma: no cover
        return point
    return origin + direction * (float((point - origin) @ normal)
                                 / denominator)


class MoveMode(Mode):
    """Drag an atom, or the selection, to where it should be.

    **In the plane facing the camera.**  A drag has no depth of its
    own -- the cursor is a ray, not a point -- so the atom moves in the
    plane through where it was picked up, facing the viewer, which is
    the only plane a screen movement means without being asked twice.
    ``Shift-Alt`` says otherwise: the movement is then read as towards
    and away from the viewer along the view axis, which is the half of
    the placement a plane cannot reach, and turning the crystal first
    is the other way to get it.

    **Alt turns what is held instead of moving it.**  Placing a
    fragment is two questions -- where, and which way round -- and the
    second one has no answer in a translation: a linker dropped in
    backwards has to be turned, and doing it from the Move dock means
    naming an axis and an angle for something the user can see.  So an
    alt-drag is a trackball over the selection: across the picture
    turns it about the camera's up axis, up and down about the
    camera's right, and one radius of travel is one radian.  Scaling by
    the selection's *own* size is what makes it feel the same on a
    linker and on a framework, without the mode having to know how big
    the window is.

    The pivot is the middle of the selection as it is drawn, taken
    once when the button goes down and held for the gesture: a centroid
    recomputed while the atoms move walks the fragment away from where
    the user grabbed it.  A single atom has no orientation, so an
    alt-drag on one says so rather than doing nothing quietly.

    **A press on an atom moves it; a press on the background turns the
    crystal.**  The mode takes the left button only for as long as it
    has hold of something, so the view is never stuck -- which is what
    makes this liveable as a mode rather than a tool that has to be put
    down again.

    **What is dragged is the selection when the atom is in it.**  Pick
    a fragment, then drag any atom of it and the whole fragment goes;
    drag an atom that is not selected and it becomes the selection,
    alone.  Shift adds the atom to the selection and drags them
    together.

    **The bonding does not change.**  Not the graph, not the bond
    types, not the perception: atoms that end up on top of each other
    are not bonded and a bond stretched to 4 A is still a bond, until
    Recalculate Bonds is asked for.  The whole gesture is one undo
    step, because ``MoveSites`` merges while the button is down.

    The drag moves *sites*, so an atom on a special position takes its
    orbit with it and the copy under the cursor is the one that follows
    the cursor exactly -- see
    :meth:`~xtal.commands.atoms.MoveSites.by_image_delta`.
    """

    name = "move"
    label = "Move"
    hint = ("drag an atom to move it, or any atom of the selection to "
            "move all of it - alt-drag turns the selection - "
            "shift-alt-drag moves it in depth - the background still "
            "turns the crystal")
    wants_drag = True
    drag_style = "ray"

    def __init__(self):
        # Where the gesture is happening: a point on the plane the
        # atom moves in and its normal, and the last place the cursor
        # was on it.  None between drags.
        self.plane: tuple | None = None
        self._last = None
        self._travelled = 0.0
        self._sites = 0
        # The pivot an alt-drag turns about, and the size it scales
        # its angles by.  Taken at the press and held: see the class
        # docstring.
        self._pivot = None
        self._radius = 1.0
        self._turned = 0.0

    def on_deactivate(self, document) -> None:
        self.plane = None
        self._last = None
        self._pivot = None

    def on_click(self, document, model, event: ClickEvent) -> str:
        """A press that took nothing is still a click.

        The background is where a click means "select nothing", and
        the drag never started there -- so without this, clearing the
        selection would need a different mode.
        """
        return SelectMode().on_click(document, model, event)

    def on_drag_start(self, document, model,
                      event: DragRayEvent) -> bool:
        if document is None or model is None:
            return False
        kind, index = picking.pick(model, event.origin, event.direction)
        if kind != "atom":
            return False            # the camera keeps the background
        atom, _cell, position = instance_at(model, index)
        if atom not in document.selection.atoms:
            document.select([atom], "add" if event.additive else "set")
        self.plane = (position, _unit(event.direction))
        self._last = point_on_plane(event.origin, event.direction,
                                    *self.plane)
        self._travelled = 0.0
        self._turned = 0.0
        self._sites = len(document.selected_sites())
        self._pivot, extent = document.selection_pivot()
        # A floor, not a fudge: two atoms half an Angstrom apart would
        # otherwise turn a whole revolution for a nudge of the mouse.
        self._radius = max(float(extent), 1.0)
        return True

    def on_drag_move(self, document, model,
                     event: DragRayEvent) -> str:
        travel = self._travel(event)
        if travel is None:
            return ""
        if event.rotate:
            return self._turn(document, travel, event)
        delta = travel
        if event.depth:
            # Up the screen is away from the viewer.  The plane's
            # normal is the ray that grabbed the atom, which points
            # into the scene, so the sign needs no thought beyond this
            # sentence.
            delta = self.plane[1] * float(travel @ _unit(event.up))
        if float(np.linalg.norm(delta)) < 1e-9:
            return ""
        self._travelled += float(np.linalg.norm(delta))
        document.drag_selection(delta)
        return f"moved by {self._travelled:.3f} A"

    def on_drag_end(self, document, model,
                    event: DragRayEvent) -> str:
        """The button came up: the gesture is over and so is the undo
        step it merged into.

        The whole gesture is reported rather than its last step, which
        is usually a fraction of a pixel and says nothing: what the
        user wants to read afterwards is how far the atom went.
        """
        message = self.on_drag_move(document, model, event)
        travelled, turned, sites = (self._travelled, self._turned,
                                    self._sites)
        self.plane = None
        self._last = None
        self._pivot = None
        if document is not None:
            document.break_merge()
        if turned:
            return f"turned {sites} site(s) by {abs(turned):.1f} deg"
        if travelled <= 0.0:
            # Nothing happened: either a press that did not travel, or
            # a gesture the mode refused -- and the refusal is the half
            # worth repeating once the button is up.
            return message
        return f"moved {sites} site(s) by {travelled:.3f} A"

    def _travel(self, event: DragRayEvent):
        """Where the cursor went since the last step, in the plane the
        gesture is happening in."""
        if self.plane is None:
            return None
        point = point_on_plane(event.origin, event.direction,
                               *self.plane)
        travel, self._last = point - self._last, point
        return travel

    def _turn(self, document, travel, event) -> str:
        """One step of an alt-drag: a trackball over the selection.

        Across the picture turns about the camera's up axis and up the
        picture about its right, which is the gesture every molecular
        viewer uses for an orientation -- here applied to what is held
        rather than to the camera.
        """
        if self._pivot is None or self._sites < 2:
            return ("one site has no orientation -- select more of "
                    "the fragment to turn it")
        up = _unit(event.up)
        right = _unit(np.cross(self.plane[1], up))
        # Right-hand rule, worked out against the near face: dragging
        # right swings the front of the selection right (about +up),
        # dragging up tips the front upwards (about -right).
        omega = ((float(travel @ right) * up
                  - float(travel @ up) * right) / self._radius)
        angle = float(np.degrees(np.linalg.norm(omega)))
        if angle < 1e-9:
            return ""
        self._turned += angle
        document.drag_rotation(omega, angle, self._pivot)
        return f"turned by {self._turned:.1f} deg"


def _unit(vector):
    vector = np.asarray(vector, dtype=float)
    length = float(np.linalg.norm(vector))
    if length < 1e-12:                              # pragma: no cover
        return np.array([0.0, 0.0, 1.0])
    return vector / length


class MeasureMode(Mode):
    """Click atoms to measure between them.

    How many atoms you pick is the whole of the choice: two is a
    distance, three an angle, four a torsion.  ``target`` says which
    one is wanted, and the measurement is taken the moment that many
    atoms have been picked.

    **Clicking the bond itself is one click, whatever the target.**  A
    bond already names its two atoms, so asking the user to find each
    end of the thing they are pointing at is asking them to say it
    twice.

    The picks stay selected while they accumulate, so the atoms going
    into the measurement are visible before the number appears.
    """

    name = "measure"
    label = "Measure"
    hint = ("click a bond for its length, or 2 atoms for a distance, "
            "3 for an angle, 4 for a torsion")

    def __init__(self, target: int = 2):
        self.target = int(target)
        self.picked: list = []

    def on_deactivate(self, document) -> None:
        self.picked = []

    def on_cancel(self, document) -> str:
        if not self.picked:
            return ""
        self.picked = []
        return "measurement abandoned"

    def on_click(self, document, model, event: ClickEvent) -> str:
        if document is None:
            return ""
        kind, index = picking.pick(model, event.origin, event.direction)
        if kind == "bond":
            # Whatever was half-picked goes: the click named a
            # different measurement from the one being assembled, and
            # keeping the atoms would fold them into it.
            self.picked = []
            key = model.bond_key(index)
            document.select_bond(key)
            try:
                return document.add_bond_measurements([key])
            except ValueError as exc:
                return str(exc)
        if kind != "atom":
            self.picked = []
            document.select_none()
            return "cancelled"

        atom, _cell = model.instance(index)
        if atom in self.picked:
            return "that atom is already in the measurement"
        self.picked.append(atom)
        document.select(self.picked, "set")

        if len(self.picked) < self.target:
            left = self.target - len(self.picked)
            return f"{left} more atom{'s' if left > 1 else ''}"

        atoms, self.picked = self.picked, []
        try:
            return document.add_measurement(atoms)
        except ValueError as exc:
            document.select_none()
            return str(exc)


MODES: dict[str, Mode] = {}


def register(mode: Mode) -> Mode:
    MODES[mode.name] = mode
    return mode


def get(name: str) -> Mode:
    try:
        return MODES[name]
    except KeyError:
        raise ValueError(f"unknown interaction mode: {name!r}") from None


def names() -> list[str]:
    return list(MODES)


register(SelectMode())
register(BoxSelectMode())
register(AddAtomMode())
register(AddBondMode())
register(DrawTopologyMode())
register(MoveMode())
register(MeasureMode())
