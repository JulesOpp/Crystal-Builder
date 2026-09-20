"""
xtal.commands.connections
=========================
Turning an atom into a connection point, and why there is no way back.

A building block's connection point is a dummy atom sitting
:data:`~xtal.mof.block.CONNECTION_DISTANCE` from the atoms it hangs
off, pointing where the next block goes.  Somebody with a molecule
open has the direction already -- it is a bond they can see -- so
marking one is retyping the atom on the end of that bond and pulling
it in, which is what :class:`MarkConnectionPoints` does.

**A point may stand for several atoms**, and that is the second
command here.  A chelate meets its metal through two atoms, not one,
and marking those two separately gives a block with twice the
coordination number it has -- so :class:`MarkOneConnectionPoint`
collapses a selection into a single point instead of retyping each of
them.  Two commands and not one option on one, because the two
gestures differ in what they leave behind: the first moves atoms the
user already had, the second deletes them and adds one that was not
there.

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

from xtal.commands import atoms as atom_commands
from xtal.commands import bonds as bond_commands
from xtal.commands.base import Command
from xtal.core import bonding, neighbors, p1
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


def _gather(cell, lattice, atoms) -> dict:
    """A lattice translation for each atom that puts the group
    together, in the image nearest the first of them.

    The same rule -- and the same function --
    :func:`xtal.core.measure.centroid` uses, a star from the first
    atom rather than a chain, because a selection has no order worth
    following.  It is done here rather than there because the
    translations are needed twice: once for the middle the point goes
    to, and once for the bonds it takes over, which have to name the
    image of each partner that is actually beside it.
    """
    atoms = list(atoms)
    origin = cell.frac[atoms[0]]
    found = {atoms[0]: np.zeros(3, dtype=int)}
    for atom in atoms[1:]:
        vector = neighbors.min_image_vector(origin, cell.frac[atom],
                                            lattice)
        moved = lattice.to_frac(lattice.to_cart(origin) + vector)
        found[atom] = np.round(moved - cell.frac[atom]).astype(int)
    return found


def plan_one(structure, atoms):
    """``(frac, partners, refused)`` for collapsing these atoms into
    one connection point.

    ``partners`` is ``(atom, image)`` for every atom *outside* the
    group that something inside it was bonded to -- the attachment's
    members, and the bonds the new point inherits.  ``frac`` is where
    the point goes, which is
    :data:`~xtal.mof.block.CONNECTION_DISTANCE` from those members'
    centroid along the direction the group sat in.

    Separate from the command for the same reason :func:`plan` is: a
    menu can ask what would happen before it offers to do it.
    """
    cell = p1.expand(structure)
    graph = bonding.graph(structure)
    lattice = structure.lattice
    group = sorted({int(a) for a in atoms})
    if len(group) < 2:
        return None, [], [
            "select two or more atoms -- one atom on the end of one "
            "bond is Mark connection points"]

    inside = set(group)
    shifts = _gather(cell, lattice, group)
    matrix = lattice.matrix
    middle = np.mean([cell.cart[a] + shifts[a] @ matrix
                      for a in group], axis=0)

    partners: dict[tuple, np.ndarray] = {}
    for atom in group:
        for j, image in graph.neighbors_with_images(atom):
            if j in inside:
                continue
            translation = tuple(int(v) for v in
                                (np.asarray(image) + shifts[atom]))
            partners[(j, translation)] = (
                cell.cart[j] + np.asarray(translation) @ matrix)
    if not partners:
        return None, [], [
            "these atoms are bonded to nothing outside themselves, "
            "so there is no direction for a connection point to "
            "point along"]

    anchor = np.mean(list(partners.values()), axis=0)
    offset = middle - anchor
    length = float(np.linalg.norm(offset))
    if length < 1e-9:
        return None, [], [
            "these atoms sit on the middle of the ones they are "
            "bonded to, so there is no direction for a connection "
            "point to point along"]
    point = anchor + offset * (CONNECTION_DISTANCE / length)
    return (lattice.to_frac(point), sorted(partners), [])


class MarkOneConnectionPoint(Command):
    """Collapse the selected atoms into a single connection point.

    The gesture :class:`MarkConnectionPoints` cannot make.  That one
    retypes each selected atom, which is right when each of them is a
    separate joint and wrong when they are one: MFU-4l's kernel meets
    a triazolate through two ring atoms and Ni3(HITP)2's nickel meets
    an imine through two nitrogens, and marked one at a time those
    blocks come out with twice the coordination number they have and
    fit no net in the catalogue.

    So this is a *new* atom rather than a retyped one -- an ``X`` at
    :data:`~xtal.mof.block.CONNECTION_DISTANCE` from the centroid of
    everything the group was bonded to, carrying those bonds, and the
    group itself deleted.  Add first and delete second, exactly as
    Merge atoms does: a site appended last renumbers nothing, so the
    delete that follows still names the sites it was asked to.

    **There is still no Unmark**, and for the same reason: an ``X``
    does not remember what it was.  The grouping is the structure's
    own bonds and not new state on a marker, so there is nothing extra
    to put back -- and nothing but the undo stack that could.
    """

    change = Change.TOPOLOGY | Change.POSITIONS
    label = "Mark as one connection point"

    def __init__(self, atoms, sites, plan_for=None):
        self.atoms = sorted({int(a) for a in atoms})
        self.sites = sorted({int(s) for s in sites})
        #: Why nothing happened, in sentences -- see
        #: :class:`MarkConnectionPoints`.
        self.refused: list[str] = []
        #: The site the point was added as, once it has been.
        self.placed: int | None = None
        self._plan = plan_for
        self._steps: list = []

    def do(self, host) -> None:
        if self._steps:                                 # redo
            for step in self._steps:
                step.do(host)
            return
        structure = host.structure
        frac, partners, refused = (
            self._plan if self._plan is not None
            else plan_one(structure, self.atoms))
        self.refused = list(refused)
        if frac is None:
            return

        self._run(host, atom_commands.AddSites(
            [atom_commands.new_site(CONNECTION, frac)],
            label=self.label, perceive=False))

        # Re-expanded on purpose: the bonds are between drawn atoms,
        # and the point has only just become one of them.  Appending
        # a site appends its images, so every partner index above is
        # still the atom it was.
        cell = p1.expand(structure)
        drawn = self._image_at(cell, structure, frac)
        for atom, image in partners:
            self._run(host, bond_commands.AddBond(
                bonding.bond_between(structure, cell, drawn, atom,
                                     (0, 0, 0), image)))
        self._run(host, atom_commands.DeleteSites(self.sites))
        # Read after the delete and not before it: every site the
        # delete removes is below the one just appended, so the point
        # is the last site either way -- but only this number is an
        # index into the structure the caller is about to look at.
        self.placed = structure.n_sites - 1

    def _run(self, host, command) -> None:
        command.do(host)
        self._steps.append(command)

    @staticmethod
    def _image_at(cell, structure, frac) -> int:
        """Which drawn copy of the new site is the one at ``frac``.

        Any image would do for a bond -- they are related by an
        operation of the group -- but only one of them is where the
        user's atoms were, and that is the one whose neighbours are
        the atoms they were bonded to.
        """
        target = structure.lattice.to_cart(frac)
        atoms = cell.indices_of_site(structure.n_sites - 1)
        distances = [np.linalg.norm(cell.cart[int(a)] - target)
                     for a in atoms]
        return int(atoms[int(np.argmin(distances))])

    def undo(self, host) -> None:
        for step in reversed(self._steps):
            step.undo(host)

    def summary(self) -> str:
        """One line saying what happened, refusals included."""
        if self.placed is None:
            return "; ".join(self.refused) or "nothing to mark"
        return (f"marked {len(self.atoms)} atoms as one connection "
                f"point")
