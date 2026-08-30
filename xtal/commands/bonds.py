"""
xtal.commands.bonds
===================
Undoable bond edits.

A bond the user draws is stored against the asymmetric unit, so it
appears on every symmetry-equivalent pair.  A bond the user deletes
cannot simply be removed -- automatic perception would put it straight
back -- so it is stored as a *suppression*, which is the only way to
express "these two atoms are close enough to bond but do not".
"""

from __future__ import annotations

from xtal.commands.base import Command
from xtal.core.bonding import bond_between
from xtal.core.structure import Bond, Change


class AddBond(Command):
    """Add an explicit bond between two sites."""

    change = Change.TOPOLOGY
    label = "Add bond"

    def __init__(self, bond: Bond):
        self.bond = bond
        self._added = False

    @classmethod
    def between_atoms(cls, structure, cell, atom_a: int, atom_b: int,
                      image_a=(0, 0, 0),
                      image_b=(0, 0, 0)) -> AddBond:
        """From two atoms of the P1 cell, as picked in the viewport.

        The images are the lattice translations the two atoms were
        drawn at, which a multi-cell view makes essential.
        """
        return cls(bond_between(structure, cell, atom_a, atom_b,
                                image_a, image_b))

    def do(self, host) -> None:
        self._added = host.structure.add_bond(self.bond)

    def undo(self, host) -> None:
        if self._added:
            host.structure.remove_bond(self.bond)


class RemoveBond(Command):
    """Delete a bond the user had drawn."""

    change = Change.TOPOLOGY
    label = "Delete bond"

    def __init__(self, bond: Bond):
        self.bond = bond
        self._removed = False

    def do(self, host) -> None:
        self._removed = host.structure.remove_bond(self.bond)

    def undo(self, host) -> None:
        if self._removed:
            host.structure.add_bond(self.bond)


class SuppressBond(Command):
    """Hide a bond that distance-based perception keeps finding."""

    change = Change.TOPOLOGY
    label = "Delete bond"

    def __init__(self, bond: Bond):
        self.bond = Bond(bond.i, bond.j, bond.image, bond.order,
                         kind="suppressed", op=bond.op)
        self._added = False

    @classmethod
    def between_atoms(cls, structure, cell, atom_a: int, atom_b: int,
                      image_a=(0, 0, 0),
                      image_b=(0, 0, 0)) -> SuppressBond:
        return cls(bond_between(structure, cell, atom_a, atom_b,
                                image_a, image_b))

    def do(self, host) -> None:
        self._added = host.structure.add_bond(self.bond)

    def undo(self, host) -> None:
        if self._added:
            host.structure.remove_bond(self.bond)


class SetBondRules(Command):
    """Change the distance criteria used for automatic perception."""

    change = Change.TOPOLOGY
    label = "Bond rules"

    def __init__(self, rules: dict):
        self.rules = dict(rules)
        self._old: dict = {}

    def do(self, host) -> None:
        self._old = dict(host.structure.bond_rules)
        host.structure.bond_rules = dict(self.rules)
        host.structure.touch(Change.TOPOLOGY)

    def undo(self, host) -> None:
        host.structure.bond_rules = dict(self._old)
        host.structure.touch(Change.TOPOLOGY)
