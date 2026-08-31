"""
xtal.commands.atoms
===================
Undoable edits to the sites of the asymmetric unit.

Everything here works in *site* space, not in the P1 cell: the sites
are what a file stores and what symmetry multiplies.  Turning a
selection of drawn atoms into the sites an edit touches is
``xtal.core.selection.sites_for``, and warning the user when those are
not the same thing is the UI's job.
"""

from __future__ import annotations

import numpy as np

from xtal.commands.base import Command
from xtal.core import elements as el
from xtal.core import transforms
from xtal.core.site import Site
from xtal.core.structure import Change


class AddSites(Command):
    """Append sites to the asymmetric unit."""

    change = Change.TOPOLOGY

    def __init__(self, sites, label: str | None = None):
        self.sites = [s.copy() for s in sites]
        self.label = label or (
            f"Add {self.sites[0].element}" if len(self.sites) == 1
            else f"Add {len(self.sites)} atoms")
        self.indices: list[int] = []

    def do(self, host) -> None:
        structure = host.structure
        fresh = []
        for site in self.sites:
            copy = site.copy()
            if not copy.label:
                copy.label = structure.suggest_label(
                    copy.element, taken=[s.label for s in fresh])
            fresh.append(copy)
        self.indices = structure.add_sites(fresh)

    def undo(self, host) -> None:
        host.structure.remove_sites(self.indices)


class DeleteSites(Command):
    """Remove sites, remembering enough to put them back exactly.

    The saved bond list matters: removing a site renumbers every bond
    after it, so restoring the sites is not enough on its own.
    """

    change = Change.TOPOLOGY

    def __init__(self, indices, label: str | None = None):
        self.indices = sorted({int(i) for i in indices})
        self.label = label or (
            "Delete atom" if len(self.indices) == 1
            else f"Delete {len(self.indices)} sites")
        self._removed: list = []
        self._bonds: list = []

    def do(self, host) -> None:
        structure = host.structure
        self._bonds = list(structure.bonds)
        self._removed = [(i, structure.sites[i].copy())
                         for i in self.indices]
        structure.remove_sites(self.indices)

    def undo(self, host) -> None:
        structure = host.structure
        for index, site in self._removed:           # ascending
            structure.sites.insert(index, site.copy())
        structure.bonds = list(self._bonds)
        structure.touch(Change.TOPOLOGY)


class SetElement(Command):
    """Retype sites."""

    change = Change.TOPOLOGY

    def __init__(self, indices, symbol: str):
        self.indices = sorted({int(i) for i in indices})
        self.symbol = el.parse_symbol(symbol)
        self.label = f"Change element to {self.symbol}"
        self._old: list[str] = []

    def do(self, host) -> None:
        structure = host.structure
        self._old = [structure.sites[i].element for i in self.indices]
        for index in self.indices:
            structure.sites[index].element = self.symbol
        structure.touch(Change.TOPOLOGY)

    def undo(self, host) -> None:
        structure = host.structure
        for index, symbol in zip(self.indices, self._old, strict=True):
            structure.sites[index].element = symbol
        structure.touch(Change.TOPOLOGY)


class SetSiteProperties(Command):
    """Edit one site's label, occupancy, Uiso, charge or coordinates.

    Successive edits to the same fields of the same site merge, so
    holding a spinbox down is one undo step and not forty.
    """

    def __init__(self, index: int, **values):
        self.index = int(index)
        self.values = dict(values)
        self.change = (Change.POSITIONS if set(values) == {"frac"}
                       else Change.TOPOLOGY)
        names = ", ".join(sorted(values))
        self.label = f"Edit {names}"
        self._old: dict = {}

    def do(self, host) -> None:
        site = host.structure.sites[self.index]
        if not self._old:
            self._old = {key: _copy_value(getattr(site, key))
                         for key in self.values}
        for key, value in self.values.items():
            setattr(site, key, _copy_value(value))
        host.structure.touch(self.change)

    def undo(self, host) -> None:
        site = host.structure.sites[self.index]
        for key, value in self._old.items():
            setattr(site, key, _copy_value(value))
        host.structure.touch(self.change)

    def merge_with(self, other: Command) -> bool:
        if (isinstance(other, SetSiteProperties)
                and other.index == self.index
                and set(other.values) == set(self.values)):
            self.values = dict(other.values)
            return True
        return False


class MoveSites(Command):
    """Move sites to new fractional coordinates.

    Built either from explicit targets or from a displacement; either
    way the inverse is the coordinates we started from.  Consecutive
    moves of the same sites merge, which is what makes dragging one
    undo step.
    """

    change = Change.POSITIONS

    def __init__(self, targets: dict, label: str = "Move atoms"):
        self.targets = {int(k): np.asarray(v, dtype=float).reshape(3)
                        for k, v in targets.items()}
        self.label = label
        self._old: dict = {}

    @classmethod
    def by_delta(cls, structure, indices, delta,
                 label: str = "Move atoms") -> MoveSites:
        delta = np.asarray(delta, dtype=float).reshape(3)
        targets = {int(i): structure.sites[int(i)].frac + delta
                   for i in indices}
        return cls(targets, label)

    @classmethod
    def by_cartesian_delta(cls, structure, indices, delta,
                           label: str = "Move atoms") -> MoveSites:
        frac_delta = structure.lattice.to_frac(
            np.asarray(delta, dtype=float).reshape(3))
        return cls.by_delta(structure, indices, frac_delta, label)

    def do(self, host) -> None:
        structure = host.structure
        if not self._old:
            self._old = {i: structure.sites[i].frac.copy()
                         for i in self.targets}
        for index, frac in self.targets.items():
            structure.sites[index].frac = np.array(frac, dtype=float)
        structure.touch(Change.POSITIONS)

    def undo(self, host) -> None:
        structure = host.structure
        for index, frac in self._old.items():
            structure.sites[index].frac = np.array(frac, dtype=float)
        structure.touch(Change.POSITIONS)

    def merge_with(self, other: Command) -> bool:
        if (isinstance(other, MoveSites)
                and set(other.targets) == set(self.targets)):
            self.targets = dict(other.targets)
            return True
        return False


class TransformSites(Command):
    """Rotate or mirror sites about a point, in cartesian space.

    Rotation is the one editing operation where doing the arithmetic in
    fractional coordinates would be wrong: a rotation is only rigid in
    cartesian space, and in a non-orthogonal cell the two are not the
    same transformation.
    """

    change = Change.POSITIONS

    def __init__(self, indices, matrix, centre=None,
                 label: str = "Transform atoms"):
        self.indices = sorted({int(i) for i in indices})
        self.matrix = np.asarray(matrix, dtype=float).reshape(3, 3)
        self.centre = None if centre is None else np.asarray(
            centre, dtype=float).reshape(3)
        self.label = label
        self._old: dict = {}
        # Where the atoms ended up.  Kept so that a redo replays the
        # result rather than re-deriving it -- which matters once these
        # merge, because a merged burst of nudges is one command whose
        # matrix describes only the last of them.
        self._new: dict = {}

    @classmethod
    def rotation(cls, indices, axis, angle_degrees, centre=None,
                 label=None) -> TransformSites:
        axis = np.asarray(axis, dtype=float).reshape(3)
        norm = np.linalg.norm(axis)
        if norm < 1e-12:
            raise ValueError("rotation axis must be non-zero")
        axis = axis / norm
        theta = np.radians(float(angle_degrees))
        cross = np.array([[0.0, -axis[2], axis[1]],
                          [axis[2], 0.0, -axis[0]],
                          [-axis[1], axis[0], 0.0]])
        matrix = (np.eye(3) + np.sin(theta) * cross
                  + (1 - np.cos(theta)) * (cross @ cross))
        return cls(indices, matrix, centre,
                   label or f"Rotate {angle_degrees:g} degrees")

    @classmethod
    def mirror(cls, indices, normal, centre=None,
               label="Mirror atoms") -> TransformSites:
        normal = np.asarray(normal, dtype=float).reshape(3)
        norm = np.linalg.norm(normal)
        if norm < 1e-12:
            raise ValueError("mirror plane needs a non-zero normal")
        normal = normal / norm
        return cls(indices, np.eye(3) - 2 * np.outer(normal, normal),
                   centre, label)

    def do(self, host) -> None:
        structure = host.structure
        lattice = structure.lattice
        if self._new:                       # a redo: replay the result
            self._write(structure, self._new)
            return
        self._old = {i: structure.sites[i].frac.copy()
                     for i in self.indices}
        cart = np.array([lattice.to_cart(structure.sites[i].frac)
                         for i in self.indices])
        centre = (cart.mean(axis=0) if self.centre is None
                  else self.centre)
        moved = (cart - centre) @ self.matrix.T + centre
        self._new = {index: lattice.to_frac(position)
                     for index, position in zip(self.indices, moved,
                                                strict=True)}
        self._write(structure, self._new)

    def undo(self, host) -> None:
        self._write(host.structure, self._old)

    @staticmethod
    def _write(structure, frac_by_index) -> None:
        for index, frac in frac_by_index.items():
            structure.sites[index].frac = np.array(frac, dtype=float)
        structure.touch(Change.POSITIONS)

    def merge_with(self, other: Command) -> bool:
        """Absorb a later rotation of the same atoms.

        What is absorbed is the *result*, not the matrix: two rotations
        about a moving centre do not compose into one, and the thing
        this command has to be able to reproduce is where the atoms
        finished up.  The coordinates it undoes to are still the ones
        from before the first of them, which is what makes a held arrow
        one Ctrl+Z.
        """
        if (isinstance(other, TransformSites)
                and other.indices == self.indices):
            self._new = dict(other._new)
            return True
        return False


class PlanarizeSites(Command):
    """Flatten sites onto their own best-fit plane.

    The fastest way to fix an aromatic ring that came out of a builder
    or an optimiser slightly puckered.  Every atom slides along the
    plane normal and no further, which is the smallest move that makes
    them coplanar.

    How far the furthest one had to move is the number that matters and
    is kept on the command: "moved by up to 0.08 A" is a fix and
    "moved by up to 0.8 A" is a silent corruption, and the two are
    indistinguishable from the picture afterwards.
    """

    change = Change.POSITIONS

    def __init__(self, indices, label: str = "Make planar"):
        self.indices = sorted({int(i) for i in indices})
        if len(self.indices) < 3:
            raise ValueError("a plane needs at least three atoms")
        self.label = label
        self.displacement = 0.0
        self._old: dict = {}

    def do(self, host) -> None:
        structure = host.structure
        lattice = structure.lattice
        if not self._old:
            self._old = {i: structure.sites[i].frac.copy()
                         for i in self.indices}
        cart = np.array([lattice.to_cart(structure.sites[i].frac)
                         for i in self.indices])
        moved, self.displacement = transforms.planarize(cart)
        for index, position in zip(self.indices, moved, strict=True):
            structure.sites[index].frac = lattice.to_frac(position)
        structure.touch(Change.POSITIONS)

    def undo(self, host) -> None:
        structure = host.structure
        for index, frac in self._old.items():
            structure.sites[index].frac = np.array(frac, dtype=float)
        structure.touch(Change.POSITIONS)


def new_site(element: str, frac, occupancy: float = 1.0,
             label: str = "") -> Site:
    """Convenience for the Add Atom dialog and the tests."""
    return Site(element, np.asarray(frac, dtype=float),
                occupancy=occupancy, label=label)


def _copy_value(value):
    return value.copy() if isinstance(value, np.ndarray) else value
