"""
xtalapp.viewport.modes
======================
Interaction modes: what a click means right now.

A mode is a small state machine with a name, a cursor hint, and
handlers for the events it cares about.  The viewport owns one active
mode and forwards clicks to it; the camera (rotate, zoom, pan) is
handled by VTK underneath and is never a mode, because you always want
to be able to turn the structure.

Phase 3 ships **select**.  Add-atom, add-bond, measure and move are
their own modes and slot in here without the viewport changing.

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


class Mode:
    """Base class: a mode may ignore any event it does not use."""

    name = "mode"
    label = "Mode"
    hint = ""

    def on_click(self, document, model, event: ClickEvent) -> str:
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
register(AddAtomMode())
register(AddBondMode())
