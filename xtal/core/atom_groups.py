"""
xtal.core.atom_groups
=====================
Named sets of atoms drawn in a colour of their own, or not drawn.

An atom group is how the picture is told about some atoms: these in
red, those hidden until I tick them again.  It is view state and never
chemistry -- nothing here is written into a structure, a CIF or an
export, only into a project's session -- and a hidden group is still
in the cell that every calculation sees.

"Group" already means a functional group (``xtal.core.groups``), so
these are *atom* groups everywhere, in the code as in the window.

A group names P1 atoms, and an edit may renumber the cell or rebuild
it in another setting; :func:`follow` keeps each group on its atoms
through either, with :mod:`xtal.core.tracking`, exactly as the hidden
set of View > Show Only Selected is kept.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from xtal.core import tracking


@dataclass(frozen=True)
class AtomGroup:
    """A named set of P1 atoms, its colour and whether it is drawn.

    ``color`` is 0-255 RGB, or ``None`` for the element colours.
    ``where`` is the record :func:`follow` finds the atoms by; a group
    made by :func:`make` carries one.
    """

    name: str
    atoms: frozenset = frozenset()
    color: tuple[int, int, int] | None = None
    shown: bool = True
    where: tracking.Record = field(default_factory=tracking.Record,
                                   compare=False, repr=False)

    @property
    def empty(self) -> bool:
        """Every atom of it has gone -- deleted, or a symmetry change
        left none of them.  It stays in the list rather than vanishing
        under the person who made it."""
        return not self.atoms

    def to_dict(self, cell) -> dict:
        """The group for a project's session: its atoms by index with
        their elements, so a restore onto a cell they no longer fit is
        noticed (:func:`from_dict`) rather than applied to the wrong
        atoms."""
        order = sorted(self.atoms)
        record = {"name": self.name, "atoms": order,
                  "elements": [cell.elements[a] for a in order],
                  "shown": self.shown}
        if self.color is not None:
            record["color"] = list(self.color)
        return record


def make(cell, lattice, atoms, name: str, color=None,
         shown: bool = True) -> AtomGroup:
    """A group of ``atoms`` of ``cell`` (on ``lattice``), recorded so
    it can be found again after an edit."""
    chosen = frozenset(int(a) for a in atoms)
    return AtomGroup(name, chosen,
                     None if color is None else _rgb(color), bool(shown),
                     tracking.record(cell, chosen, lattice))


def from_dict(record: dict, cell, lattice) -> AtomGroup | None:
    """A saved group back on ``cell``, or ``None`` when it no longer
    fits: an index past the end or an atom of another element means
    the structure is not the one it was saved over, and colouring
    whichever atoms now have those numbers would be a picture of a
    group nobody made."""
    try:
        atoms = [int(a) for a in record.get("atoms", [])]
        elements = list(record.get("elements", []))
        if len(elements) != len(atoms):
            return None
        for atom, element in zip(atoms, elements, strict=True):
            if not 0 <= atom < cell.n_atoms \
                    or cell.elements[atom] != element:
                return None
        color = record.get("color")
        return make(cell, lattice, atoms, str(record.get("name", "")),
                    color=color, shown=bool(record.get("shown", True)))
    except (TypeError, ValueError):
        return None


def colors(groups, n_atoms: int):
    """Each atom's group colour: ``(rgb, mask)``, an ``(N, 3)`` uint8
    array and the ``(N,)`` atoms it applies to.  Where groups overlap
    the later one in the list wins, as a later stroke of paint does.
    A hidden group still colours its atoms, which are not drawn."""
    rgb = np.zeros((n_atoms, 3), np.uint8)
    mask = np.zeros(n_atoms, bool)
    for group in groups:
        if group.color is None:
            continue
        atoms = _within(group.atoms, n_atoms)
        rgb[atoms] = group.color
        mask[atoms] = True
    return rgb, mask


def hidden(groups, n_atoms: int) -> np.ndarray:
    """The ``(N,)`` mask of atoms some hidden group holds."""
    mask = np.zeros(n_atoms, bool)
    for group in groups:
        if not group.shown:
            mask[_within(group.atoms, n_atoms)] = True
    return mask


def follow(groups, cell, lattice, via: tracking.AtomMap | None = None,
           renumbered: bool = True, moved: bool = False) -> list:
    """Every group on its own atoms after an edit, in the same order.

    ``via`` is a symmetry or cell change's map (inverted already for
    an undo): followed both ways, so a supercell's group holds every
    copy and a primitive cell's atom is grouped if any atom it stands
    for was.  Otherwise an edit that kept the numbering
    (``renumbered`` false) keeps the indices, recording the atoms
    where they now are if it ``moved`` them; and one that renumbered
    the cell finds them by element and position, so what it added
    joins no group.
    """
    out = []
    for group in groups:
        if via is not None:
            atoms = tracking.follow(cell, lattice, group.where, via)
        elif not renumbered and _indices_hold(group, cell.n_atoms):
            if not moved:
                out.append(group)
                continue
            atoms = group.atoms
        else:
            atoms = tracking.find(cell, group.where)
        out.append(replace(group, atoms=frozenset(atoms),
                           where=tracking.record(cell, atoms, lattice)))
    return out


def next_name(groups, stem: str = "Group") -> str:
    """``Group 1``, ``Group 2``, ... -- the first number no group in
    the list is called by."""
    taken = {g.name for g in groups}
    n = 1
    while f"{stem} {n}" in taken:
        n += 1
    return f"{stem} {n}"


def _indices_hold(group: AtomGroup, n_atoms: int) -> bool:
    return (not group.atoms or max(group.atoms) < n_atoms) \
        and len(group.where) == len(group.atoms)


def _within(atoms, n_atoms: int) -> list:
    return [a for a in atoms if a < n_atoms]


def _rgb(color) -> tuple[int, int, int]:
    r, g, b = (int(v) for v in color)
    if not all(0 <= v <= 255 for v in (r, g, b)):
        raise ValueError(f"not an 0-255 RGB colour: {color!r}")
    return r, g, b
