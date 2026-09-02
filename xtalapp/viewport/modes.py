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

from xtalapp.viewport import picking


@dataclass
class ClickEvent:
    """One click, in the terms a mode cares about."""

    origin: tuple            # ray origin, world coordinates
    direction: tuple         # unit ray direction
    additive: bool = False   # shift / cmd held: extend the selection
    double: bool = False
    focal: tuple = (0.0, 0.0, 0.0)   # what the camera is looking at

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

    def on_click(self, document, model, event: ClickEvent) -> str:
        return ""

    def on_drag(self, document, model, event: DragEvent) -> str:
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


class AddAtomMode(Mode):
    """Click to place an atom of the current element.

    The atom lands on the plane the camera is focused on, which is the
    only depth a single click can mean.  Exact coordinates are what the
    Add Atom dialog is for.
    """

    name = "add_atom"
    label = "Add atom"
    hint = "click to place an atom · set the element in the toolbar"

    def __init__(self, element: str = "C"):
        self.element = element

    def on_click(self, document, model, event: ClickEvent) -> str:
        if document is None:
            return ""
        point = event.plane_point()
        frac = document.structure.lattice.to_frac(point)
        return document.add_atom(self.element, frac)


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
