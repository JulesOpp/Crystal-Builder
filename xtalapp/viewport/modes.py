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
"""

from __future__ import annotations

from dataclasses import dataclass

from xtalapp.viewport import picking


@dataclass
class ClickEvent:
    """One click, in the terms a mode cares about."""

    origin: tuple            # ray origin, world coordinates
    direction: tuple         # unit ray direction
    additive: bool = False   # shift / cmd held: extend the selection
    double: bool = False


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

        key = bond_key(model, index)
        document.select_bond(key, "toggle" if event.additive else "set")
        return "bond selected"


def model_element(document, atom: int) -> str:
    cell = document.cell
    label = cell.labels[atom] or cell.elements[atom]
    return f"{label}"


def bond_key(model, half_index: int) -> tuple:
    """Identify the bond a half belongs to by its two endpoints.

    Halves are emitted in pairs, so the partner of an even index is the
    next one and vice versa; the key is the pair of atom instances the
    two halves start from.
    """
    partner = half_index + 1 if half_index % 2 == 0 else half_index - 1
    ends = [half_index, partner]
    atoms = []
    for half in ends:
        start = model.bond_starts[half]
        distances = ((model.positions - start) ** 2).sum(axis=1) \
            if model.n_atoms else None
        if distances is None or not len(distances):
            atoms.append(-1)
            continue
        nearest = int(distances.argmin())
        atoms.append(int(model.atom_index[nearest]))
    i, j = sorted(atoms)
    return (i, j, (0, 0, 0))


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
