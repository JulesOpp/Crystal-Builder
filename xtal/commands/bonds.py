"""
xtal.commands.bonds
===================
Undoable bond edits.

A bond the user draws is stored against the asymmetric unit, so it
appears on every symmetry-equivalent pair.  A bond the user deletes
cannot simply be removed -- automatic perception would put it straight
back -- so it is stored as a *suppression*, which is the only way to
express "these two atoms are close enough to bond but do not".

A *topology* bond is the third kind: an edge of the net rather than a
chemical bond.  It is stored the same way and expands the same way, and
it is filtered out of everything chemical -- see
:data:`xtal.core.bonding.TOPOLOGY`.
"""

from __future__ import annotations

from xtal.commands.base import Command
from xtal.core.bonding import TOPOLOGY, bond_between
from xtal.core.structure import Bond, Change

_UNSET = object()


def _contradicting(structure, bond: Bond) -> Bond | None:
    """The record already stored for this pair that says the opposite.

    ``explicit`` and ``suppressed`` are two answers to the same
    question about the same pair, so the structure holds only one of
    them -- see ``Structure._bond_identity``.  That makes
    ``add_bond`` refuse the second answer rather than replace the
    first, and a refusal here is silent: drawing a bond back over one
    that had been deleted did nothing at all, and neither did deleting
    one that had been drawn.  So the record being contradicted is
    taken out by hand, and kept, because undo has to put it back.

    A topology edge is never a contradiction: it joins the same two
    atoms and means something else entirely.
    """
    key = bond.key(structure.space_group)
    for existing in structure.bonds:
        if existing.kind in (TOPOLOGY, bond.kind):
            continue
        if existing.key(structure.space_group) == key:
            return existing
    return None


class AddBond(Command):
    """Add an explicit bond between two sites.

    A bond drawn where one had been *deleted* takes the suppression's
    place rather than being refused -- see :func:`_contradicting`.
    Drawing the bond back is the obvious way to undo a deletion once
    the undo stack has gone, and until the suppression was displaced it
    was the one pair of atoms in the crystal that could not be bonded.
    """

    change = Change.TOPOLOGY
    label = "Add bond"

    def __init__(self, bond: Bond):
        self.bond = bond
        self.added = False
        self.replaced: Bond | None = None

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
        structure = host.structure
        self.replaced = _contradicting(structure, self.bond)
        if self.replaced is not None:
            structure.remove_bond(self.replaced)
        self.added = structure.add_bond(self.bond)

    def undo(self, host) -> None:
        if self.added:
            host.structure.remove_bond(self.bond)
        if self.replaced is not None:
            host.structure.add_bond(self.replaced)


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


class AddTopologyBond(Command):
    """Draw an edge of the underlying net.

    Stored exactly like a bond the user drew, and marked so that
    nothing chemical ever sees it: it is a statement about which parts
    of a framework are nodes, not a claim that two atoms are bonded.
    Like every other bond it expands over the symmetry orbit, which is
    what makes drawing one edge of a **pcu** net draw all six.
    """

    change = Change.TOPOLOGY
    label = "Draw topology bond"

    def __init__(self, bond: Bond):
        self.bond = Bond(bond.i, bond.j, bond.image, bond.order,
                         kind=TOPOLOGY, op=bond.op)
        self._added = False
        self._removed = False

    @classmethod
    def between_atoms(cls, structure, cell, atom_a: int, atom_b: int,
                      image_a=(0, 0, 0),
                      image_b=(0, 0, 0)) -> AddTopologyBond:
        return cls(bond_between(structure, cell, atom_a, atom_b,
                                image_a, image_b))

    def do(self, host) -> None:
        self._added = host.structure.add_bond(self.bond)

    def undo(self, host) -> None:
        if self._added:
            host.structure.remove_bond(self.bond)


class RemoveTopologyBond(AddTopologyBond):
    """Delete an edge of the net.

    A plain removal and never a suppression: perception never produces
    a topology bond, so there is nothing that would put it back.
    """

    label = "Delete topology bond"

    def do(self, host) -> None:
        self._removed = host.structure.remove_bond(self.bond)

    def undo(self, host) -> None:
        if self._removed:
            host.structure.add_bond(self.bond)


class SuppressBond(Command):
    """Hide a bond that distance-based perception keeps finding.

    A bond the user *drew* is deleted by the same click, and its record
    is displaced the same way -- see :func:`_contradicting`.  The
    suppression is stored either way: a pair can be both close enough
    to perceive and carrying a drawn record, and removing only the
    record would leave the bond on screen.
    """

    change = Change.TOPOLOGY
    label = "Delete bond"

    def __init__(self, bond: Bond):
        self.bond = Bond(bond.i, bond.j, bond.image, bond.order,
                         kind="suppressed", op=bond.op)
        self._added = False
        self.replaced: Bond | None = None

    @classmethod
    def between_atoms(cls, structure, cell, atom_a: int, atom_b: int,
                      image_a=(0, 0, 0),
                      image_b=(0, 0, 0)) -> SuppressBond:
        return cls(bond_between(structure, cell, atom_a, atom_b,
                                image_a, image_b))

    def do(self, host) -> None:
        structure = host.structure
        self.replaced = _contradicting(structure, self.bond)
        if self.replaced is not None:
            structure.remove_bond(self.replaced)
        self._added = structure.add_bond(self.bond)

    def undo(self, host) -> None:
        if self._added:
            host.structure.remove_bond(self.bond)
        if self.replaced is not None:
            host.structure.add_bond(self.replaced)


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


class RecomputeBonds(Command):
    """Perceive the bonds again, over the geometry as it now is.

    Perception does not follow atoms as they move -- see
    :data:`xtal.core.structure.CHEMISTRY` -- so the graph a structure
    is carrying was worked out at some earlier arrangement, and this is
    the thing that brings it up to date.  It is on the stack because
    the graph is *stored*: recalculating replaces something the user
    may have been relying on, and Ctrl+Z has to be able to give it
    back.

    Nothing is written here beyond dropping the stored graph.  The
    replacement is perceived lazily, by whoever asks for the bonds
    next, which is also what makes the undo data small -- one list of
    bonds rather than two.
    """

    change = Change.TOPOLOGY
    label = "Recalculate bonds"

    def __init__(self):
        self._old = _UNSET

    def do(self, host) -> None:
        structure = host.structure
        if self._old is _UNSET:
            self._old = structure.perceived
        structure.clear_perceived()
        structure.touch(Change.TOPOLOGY)

    def undo(self, host) -> None:
        host.structure.perceived = (None if self._old is _UNSET
                                    else self._old)
        host.structure.touch(Change.TOPOLOGY)


class ResetBonds(Command):
    """Throw away the bond edits and take the automatic answer.

    :class:`RecomputeBonds` re-perceives, and then lays the user's
    edits back over what it found -- which is right, and is also why a
    user who deleted a bond and then asked for the bonds to be
    recalculated saw nothing happen at all.  A suppression is stored
    precisely so that perception cannot undo it, it is saved with the
    project, and until now the only way back from one was an undo step
    that does not survive closing the file.

    So this is the way back.  It drops the *chemical* bond records --
    the ones the user drew and the ones they deleted -- and clears the
    perception, so the next read is the distance criteria and nothing
    else.  It is one command, so Ctrl+Z gives the edits back.

    Topology edges are not chemical bonds and are left alone: they are
    the underlying net, they are not something perception would ever
    produce, and dropping them here would delete a drawing nobody
    asked about.
    """

    change = Change.TOPOLOGY
    label = "Reset bonds to automatic"

    def __init__(self):
        self._old: list | None = None
        self._old_perceived = _UNSET

    def do(self, host) -> None:
        structure = host.structure
        if self._old is None:
            self._old = list(structure.bonds)
        if self._old_perceived is _UNSET:
            self._old_perceived = structure.perceived
        structure.set_bonds([b for b in self._old
                             if b.kind == TOPOLOGY])
        structure.clear_perceived()
        structure.touch(Change.TOPOLOGY)

    def undo(self, host) -> None:
        host.structure.set_bonds(list(self._old or []))
        host.structure.perceived = (None if self._old_perceived is _UNSET
                                    else self._old_perceived)
        host.structure.touch(Change.TOPOLOGY)


#: The bond types Set Bond Type offers, in the order a menu should show
#: them.  ``None`` is not a type but the absence of one: the stored
#: order is removed and :func:`xtal.core.bonding.orders` decides again,
#: which is the way back from a wrong answer that is not Ctrl+Z.
BOND_TYPES = (("Single", 1.0),
              ("Double", 2.0),
              ("Triple", 3.0),
              ("Aromatic", 1.5),
              ("Automatic", None))

#: Name -> order, for the dialog and the tests.
BOND_TYPE_ORDERS = {name: order for name, order in BOND_TYPES}


def bond_type_name(order, stated: bool = True) -> str:
    """What to call an order: the inverse of :data:`BOND_TYPE_ORDERS`."""
    if not stated or order is None:
        return "Automatic"
    for name, value in BOND_TYPES:
        if value is not None and abs(value - float(order)) < 1e-9:
            return name
    return f"{float(order):g}"


class SetBondType(Command):
    """State what kind of bond joins two sites: single, double,
    triple, aromatic -- or nothing, and let perception decide.

    Bond order is normally *inferred* from the geometry, which is right
    almost always and wrong in the cases nobody can automate: a
    delocalised carboxylate, a metal-carbene, a structure whose
    hydrogens were never in the file.  This is the override, and like
    every other bond edit it is stored against the asymmetric unit, so
    setting one C-O of an acetate double sets the symmetry-equivalent
    one too.

    An order of ``None`` removes the statement rather than storing one:
    the explicit record goes if it exists only to carry an order, and
    the inference gets the bond back.
    """

    change = Change.TOPOLOGY

    def __init__(self, bond: Bond, order: float | None):
        self.order = None if order is None else float(order)
        self.bond = bond
        self.label = f"Set bond type to {bond_type_name(self.order)}"
        self._old: Bond | None = None
        self._had: bool = False

    @classmethod
    def between_atoms(cls, structure, cell, atom_a: int, atom_b: int,
                      order: float | None, image_a=(0, 0, 0),
                      image_b=(0, 0, 0)) -> SetBondType:
        """From two atoms of the P1 cell, as picked in the viewport."""
        return cls(bond_between(structure, cell, atom_a, atom_b,
                                image_a, image_b), order)

    def _stored(self, structure) -> Bond | None:
        """The record already held for this pair, if there is one.

        Matched the way the structure itself matches bonds, so a bond
        stored from its other end is found rather than duplicated.
        """
        identity = (False, self.bond.key(structure.space_group))
        for existing in structure.bonds:
            if existing.kind == TOPOLOGY:
                continue
            if (existing.kind != "suppressed"
                    and existing.key(structure.space_group)
                    == identity[1]):
                return existing
        return None

    def do(self, host) -> None:
        structure = host.structure
        existing = self._stored(structure)
        self._had = existing is not None
        self._old = existing
        if existing is not None:
            structure.remove_bond(existing)
        if self.order is not None:
            structure.add_bond(Bond(self.bond.i, self.bond.j,
                                    self.bond.image, self.order,
                                    "explicit", self.bond.op,
                                    stated=True))
        elif not self._had:
            # Nothing stated and nothing stored: the bond is already
            # perceived and already inferred, so there is nothing to do
            # -- but the structure still has to be touched, or the
            # viewport is never told the answer it is showing is the
            # same one.
            structure.touch(Change.TOPOLOGY)

    def undo(self, host) -> None:
        structure = host.structure
        if self.order is not None:
            structure.remove_bond(Bond(self.bond.i, self.bond.j,
                                       self.bond.image, self.order,
                                       "explicit", self.bond.op,
                                       stated=True))
        if self._had and self._old is not None:
            structure.add_bond(self._old)
        else:
            structure.touch(Change.TOPOLOGY)


# ======================================================================
#  MANY BONDS AT ONCE
# ======================================================================
#
# Everything above edits one bond and touches the structure when it is
# done, which is right for one bond and quadratic for eight hundred:
# each touch drops the P1 expansion, and the next command rebuilds it.
# Select All on a framework selects every bond there is, so the bulk
# form is not an optimisation for a rare case -- it is what one click
# now does.


class _BulkBondEdit(Command):
    """Several bond-record edits, applied and undone as one change.

    One touch, so the cell is expanded once and the viewport redraws
    once: there is no state between the first bond and the last that
    anybody should see, and drawing eight hundred intermediate pictures
    is the whole of what made this slow.

    The undo data is the bond list as it was.  That is a genuinely
    small thing to keep even here -- bonds are stored against the
    asymmetric unit, so a framework whose cell has eight hundred bonds
    has a couple of dozen records behind them.
    """

    change = Change.TOPOLOGY

    def __init__(self, bonds, label: str):
        self.bonds = list(bonds)
        self.label = label
        self._old: list | None = None

    def plan(self, structure, existing: list) -> list:
        """The bond list this edit wants, given the one it has."""
        raise NotImplementedError

    def do(self, host) -> None:
        structure = host.structure
        if self._old is None:
            self._old = list(structure.bonds)
        structure.set_bonds(self.plan(structure, list(structure.bonds)))

    def undo(self, host) -> None:
        host.structure.set_bonds(list(self._old))

    @staticmethod
    def _keyed(structure, bonds) -> dict:
        """The bonds, one per pair, keyed the way the structure matches
        them.

        Deduplicating here is what makes the batch safe to apply in one
        pass: a selection of eight hundred drawn bonds is a couple of
        dozen distinct pairs of the asymmetric unit, and the same pair
        arriving twenty times must end up as one record, not twenty.
        """
        group = structure.space_group
        return {bond.key(group): bond for bond in bonds}


class SetBondTypes(_BulkBondEdit):
    """State the order of many bonds at once -- see :class:`SetBondType`
    for what one of them means."""

    def __init__(self, bonds, order: float | None):
        self.order = None if order is None else float(order)
        super().__init__(
            bonds,
            f"Set {len(list(bonds))} bond(s) to "
            f"{bond_type_name(self.order)}")

    def plan(self, structure, existing: list) -> list:
        group = structure.space_group
        wanted = self._keyed(structure, self.bonds)
        # Everything the batch does not speak for, kept as it is.  A
        # suppression is somebody saying these two atoms are *not*
        # bonded, which is a different statement from an order and is
        # not overwritten by one.
        out = [b for b in existing
               if b.kind == TOPOLOGY or b.kind == "suppressed"
               or b.key(group) not in wanted]
        if self.order is None:
            return out                  # the statements simply go
        out.extend(Bond(b.i, b.j, b.image, self.order, "explicit",
                        b.op, stated=True)
                   for b in wanted.values())
        return out


class SuppressBonds(_BulkBondEdit):
    """Delete many perceived bonds at once -- see :class:`SuppressBond`
    for why deleting one is storing a suppression."""

    def __init__(self, bonds):
        super().__init__(bonds, f"Delete {len(list(bonds))} bond(s)")

    def plan(self, structure, existing: list) -> list:
        group = structure.space_group
        wanted = self._keyed(structure, self.bonds)
        out = [b for b in existing
               if b.kind == TOPOLOGY or b.key(group) not in wanted]
        out.extend(Bond(b.i, b.j, b.image, b.order, "suppressed", b.op)
                   for b in wanted.values())
        return out
