"""
xtal.commands.connections
=========================
Turning an atom into a connection point, and why there is no way back.

A building block's connection point is a dummy atom sitting
:data:`~xtal.mof.block.CONNECTION_DISTANCE` from the atom it hangs
off, pointing where the next block goes.  Somebody with a molecule
open has the direction already -- it is a bond they can see -- so
marking one is retyping the atom on the end of that bond and pulling
it in, which is what this does.

**One command for both halves.**  The user made one gesture and Ctrl+Z
has to give back the element *and* the position; two commands would
mean two presses, and a single press would leave a carbon 0.75 A from
its neighbour, which is a worse structure than either end of the edit.

**There is no Unmark.**  An ``X`` does not remember what it was.  The
element is gone, the atom has moved, and the only thing that could put
either back is the undo stack -- which is exactly what it is for.  A
menu entry claiming to reverse this would have to guess an element and
a bond length, and guessing carbon at 1.09 A is how a marked hydrogen
comes back as something the user never had.

**The bond is kept, explicitly, when it was only perceived.**
Perception never bonds a dummy -- see
:data:`xtal.core.elements.DUMMY_ELEMENTS` -- so an atom whose only
bond was distance-perceived would be marked and, on the next read of
the graph, float free of the molecule it belongs to.  That loses the
direction, which is the whole of what a connection point carries, and
it loses it silently.  So the bond that decided where the atom goes is
written down as the user's own before the element changes.  A bond
that was already explicit is left alone; there is nothing to save.
"""

from __future__ import annotations

import numpy as np

from xtal.commands.base import Command
from xtal.core import bonding, p1
from xtal.core.structure import Change
from xtal.mof.block import CONNECTION_DISTANCE

#: What a marked atom becomes.  The dummy
#: :mod:`xtal.build` builds and :mod:`xtal.mof.catalog` reads, and the
#: reason a connection point needed no new symbol of its own.
CONNECTION = "X"


def plan(structure, sites):
    """``(targets, bonds, refused)`` for marking these sites.

    ``targets`` is ``{site: fractional coordinates}``, ``bonds`` the
    perceived bonds that have to be written down before the elements
    change, and ``refused`` a sentence per site that cannot be marked.

    Separate from the command so that a dialog, a status line or a
    test can ask what would happen without doing it -- and so that the
    refusals are worded once.
    """
    cell = p1.expand(structure)
    graph = bonding.graph(structure)
    geo = bonding.geometry(structure)
    targets: dict[int, np.ndarray] = {}
    bonds: list = []
    refused: list[str] = []
    for site in sorted({int(s) for s in sites}):
        atoms = cell.indices_of_site(site)
        if not len(atoms):                          # pragma: no cover
            continue
        # The first image, and any image would do: they are related by
        # an operation of the group, so the displacement is the same
        # one seen from a different frame, and `parent_coordinates`
        # takes it back to the site either way.
        atom = int(atoms[0])
        name = _name(structure, site)
        vectors = geo.vectors(atom)
        if len(vectors) != 1:
            # Named rather than counted.  "3 atoms could not be
            # marked" tells a user with twenty selected nothing at
            # all; the label of the one with three bonds tells them
            # where to look.
            refused.append(
                f"{name} has {len(vectors)} bond(s) -- a connection "
                f"point needs exactly one, to say which way it points")
            continue
        offset = vectors[0]
        length = float(np.linalg.norm(offset))
        if length < 1e-9:                           # pragma: no cover
            refused.append(f"{name} sits on top of the atom it is "
                           f"bonded to, so it has no direction")
            continue
        moved = (cell.cart[atom]
                 + offset * (1.0 - CONNECTION_DISTANCE / length))
        targets[site] = p1.parent_coordinates(
            structure, cell, atom, structure.lattice.to_frac(moved))
        if not graph.bonds_of(atom)[0].explicit:
            partner, image = graph.neighbors_with_images(atom)[0]
            bonds.append(bonding.bond_between(
                structure, cell, atom, partner, (0, 0, 0), image))
    return targets, bonds, refused


def _name(structure, site: int) -> str:
    site_object = structure.sites[site]
    return site_object.label or f"{site_object.element} {site + 1}"


class MarkConnectionPoints(Command):
    """Retype the selected sites as ``X`` and pull them in to
    :data:`~xtal.mof.block.CONNECTION_DISTANCE`.

    Both halves in one undo step, and nothing that marks a site
    without a direction -- see the module docstring.
    """

    change = Change.TOPOLOGY | Change.POSITIONS

    def __init__(self, sites, plan_for=None):
        self.sites = sorted({int(s) for s in sites})
        self.label = (
            "Mark connection point" if len(self.sites) == 1
            else f"Mark {len(self.sites)} connection points")
        #: What could not be marked, in sentences.  Filled by
        #: :meth:`do` when it was not passed in, so a caller that
        #: pushed the command without planning first can still say why
        #: three of the twenty selected atoms are unchanged.
        self.refused: list[str] = []
        self.marked: list[int] = []
        self._plan = plan_for
        self._old: list[tuple] = []
        self._bonds: list = []

    def do(self, host) -> None:
        structure = host.structure
        targets, bonds, refused = (
            self._plan if self._plan is not None
            else plan(structure, self.sites))
        self.refused = list(refused)
        self.marked = sorted(targets)
        # Before the elements change: `bond_between` reads the
        # geometry to work out which operation joins the two ends, and
        # after the move it would be reading the new one.
        self._bonds = [bond for bond in bonds
                       if structure.add_bond(bond)]
        self._old = [(site, structure.sites[site].element,
                      structure.sites[site].frac.copy())
                     for site in self.marked]
        for site, frac in targets.items():
            structure.sites[site].element = CONNECTION
            structure.sites[site].frac = np.array(frac, dtype=float)
        structure.touch(self.change)

    def undo(self, host) -> None:
        structure = host.structure
        for site, element, frac in self._old:
            structure.sites[site].element = element
            structure.sites[site].frac = np.array(frac, dtype=float)
        for bond in self._bonds:
            structure.remove_bond(bond)
        structure.touch(self.change)

    def summary(self) -> str:
        """One line saying what happened, refusals included."""
        if not self.marked:
            return "; ".join(self.refused) or "nothing to mark"
        done = f"marked {len(self.marked)} connection point(s)"
        if not self.refused:
            return done
        return f"{done}; left alone: " + "; ".join(self.refused)
