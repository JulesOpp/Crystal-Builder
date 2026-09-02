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
:class:`DragEvent` instead.  That one flag is the only thing the
viewport has to know about it: it stops handing the left button to
VTK's trackball while such a mode is active, because a rubber band and
a camera rotation are the same gesture and cannot both have it.

Modes read what was clicked from the scene model's provenance arrays,
never from the geometry: a drawn atom knows which atom of the P1 cell
it is *and* which lattice translation put it there, and a bond half
knows the (i, j, image) of the bond it draws.  Reconstructing any of
that from coordinates is how a click ends up joining the wrong pair.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from xtal.core import elements as el
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


class Mode:
    """Base class: a mode may ignore any event it does not use."""

    name = "mode"
    label = "Mode"
    hint = ""
    #: Does this mode want press-drag-release rather than a click?  The
    #: viewport withholds the left button from VTK's camera while a
    #: mode that does is active.
    wants_drag = False
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


def bond_distance(a: str, b: str) -> float:
    """How far apart to place a new atom and the one it bonds to.

    The sum of the two covalent radii, which is what perception
    already uses to decide that two atoms *are* bonded -- so an atom
    placed here is one the distance criteria would have found anyway,
    and the bond drawn with it does not contradict the rules that
    would have drawn it.  Every element carries one, a dummy atom
    included, so there is no pair this has no answer for.
    """
    return el.covalent_radius(a) + el.covalent_radius(b)


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


class MeasureMode(Mode):
    """Click atoms to measure between them.

    How many atoms you pick is the whole of the choice: two is a
    distance, three an angle, four a torsion.  ``target`` says which
    one is wanted, and the measurement is taken the moment that many
    atoms have been picked -- so measuring a bond is two clicks and
    nothing else.

    The picks stay selected while they accumulate, so the atoms going
    into the measurement are visible before the number appears.
    """

    name = "measure"
    label = "Measure"
    hint = ("click 2 atoms for a distance, 3 for an angle, 4 for a "
            "torsion")

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
register(MeasureMode())
