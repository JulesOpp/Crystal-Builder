"""
xtal.commands.symmetry
======================
Undoable symmetry operations.

These are the things a crystallographer does to the symmetry of a
structure, wrapped so that each is one step on the undo stack:

* :class:`FindSymmetry` -- detect the group at a tolerance and reduce
  the cell to its asymmetric unit;
* :class:`SetSpaceGroup` -- adopt a group, either reinterpreting the
  sites as an asymmetric unit or imposing the group on a full cell;
* :class:`Standardize` -- rebuild the cell in the conventional or
  primitive setting of the detected group;
* :class:`ReduceToP1` -- expand every orbit and throw the group away;
* :class:`Invert` -- swap the structure's hand, group included;
* :class:`DescendToSubgroup` -- drop to a maximal subgroup so that an
  orbit splits and its atoms become independent.

Each carries a :class:`~xtal.core.symmetry.SymmetryReport` describing
what it did or would do, so a dialog can show the consequences at the
tolerance the user is currently dragging a spinbox through, and only
commit when they press OK.  Every one of these is a whole-structure
rebuild, so undo keeps the old structure -- there is no smaller honest
description of "this used to be P1 and now it is Fd-3m".
"""

from __future__ import annotations

from xtal.commands.base import StructureOperation
from xtal.core import subgroups, symmetry
from xtal.core.spacegroup import SpaceGroup
from xtal.core.structure import Change


class ReduceToP1(StructureOperation):
    """Expand every orbit into independent sites and drop the group.

    Always available, always safe: it is the way out of every symmetry
    constraint, and the way to edit atoms one at a time.
    """

    change = Change.SYMMETRY | Change.TOPOLOGY
    label = "Reduce to P1"

    def apply_to(self, structure):
        before = structure.space_group.short_name
        out = symmetry.reduce_to_p1(structure)
        return out, symmetry.SymmetryReport(
            n_before=structure.n_sites, n_after=out.n_sites,
            message=(f"expanded {before} to P1: {out.n_sites} "
                     f"independent sites"))


class FindSymmetry(StructureOperation):
    """Detect the space group and keep it: the cell is reduced to its
    asymmetric unit, so an edit to one atom becomes an edit to its
    whole orbit.

    ``standardize_cell`` re-expresses the cell in the standard setting
    of the group first, which is needed whenever the cell as given is
    not already in it.  The operation verifies itself by re-expanding
    the result; a failed check comes back as ``ok=False`` with the
    original structure, never as a plausible wrong answer.
    """

    change = Change.SYMMETRY | Change.CELL | Change.TOPOLOGY
    label = "Find symmetry"

    def __init__(self, symprec: float = symmetry.DEFAULT_SYMPREC,
                 standardize_cell: bool = False):
        super().__init__()
        self.symprec = float(symprec)
        self.standardize_cell = bool(standardize_cell)

    def apply_to(self, structure):
        return symmetry.asymmetrize(structure, self.symprec,
                                    self.standardize_cell)


class SetSpaceGroup(StructureOperation):
    """Adopt a space group.

    ``mode="reinterpret"`` treats the current sites as an asymmetric
    unit and lets the group generate the rest -- what you want when
    building by hand.  ``mode="impose"`` treats them as a full cell and
    looks for an asymmetric unit inside it; atoms the group cannot
    explain are reported rather than dropped in silence.
    """

    change = Change.SYMMETRY | Change.TOPOLOGY

    def __init__(self, group, mode: str = "reinterpret",
                 tol: float = symmetry.MATCH_TOL):
        super().__init__()
        self.group = SpaceGroup.from_any(group)
        self.mode = mode
        self.tol = float(tol)
        self.label = f"Set {self.group.short_name}"

    def apply_to(self, structure):
        return symmetry.set_space_group(structure, self.group,
                                        self.mode, self.tol)


class Standardize(StructureOperation):
    """Rebuild the cell in the conventional -- or primitive -- setting
    of its detected group.

    The result is in P1: standardising moves the cell, and which sites
    are independent in the new setting is a separate question, answered
    by running :class:`FindSymmetry` afterwards.
    """

    change = Change.CELL | Change.SYMMETRY | Change.TOPOLOGY

    def __init__(self, symprec: float = symmetry.DEFAULT_SYMPREC,
                 to_primitive: bool = False, idealize: bool = True):
        super().__init__()
        self.symprec = float(symprec)
        self.to_primitive = bool(to_primitive)
        self.idealize = bool(idealize)
        self.label = ("Reduce to primitive cell" if to_primitive
                      else "Standardise cell")

    def apply_to(self, structure):
        return symmetry.standardize(structure, self.symprec,
                                    self.to_primitive, self.idealize)


class AssignWyckoff(StructureOperation):
    """Fill in the Wyckoff letter of every site.  Informational: not
    one coordinate moves."""

    change = Change.METADATA
    label = "Assign Wyckoff letters"

    def __init__(self, symprec: float = symmetry.DEFAULT_SYMPREC):
        super().__init__()
        self.symprec = float(symprec)

    def apply_to(self, structure):
        out = symmetry.assign_wyckoff(structure, self.symprec)
        letters = {s.wyckoff for s in out.sites if s.wyckoff}
        return out, symmetry.SymmetryReport(
            n_before=structure.n_sites, n_after=out.n_sites,
            message=(f"{out.n_sites} sites on "
                     f"{', '.join(sorted(letters)) or 'no'} positions"))


class Invert(StructureOperation):
    """The same crystal in the other hand.

    Both halves or neither: the coordinates change *and* the group
    does.  Negating the coordinates while leaving P4_1 in place would
    give a structure whose atoms no longer obey their own symmetry, and
    the next expansion of it would be nonsense.
    """

    change = Change.SYMMETRY | Change.POSITIONS | Change.TOPOLOGY
    label = "Invert the structure"

    def apply_to(self, structure):
        return symmetry.invert(structure)


class DescendToSubgroup(StructureOperation):
    """Drop into one of the maximal subgroups of the current group, so
    that an orbit splits and the atoms in it become independent.

    Going the other way is :class:`FindSymmetry`, and the two are not a
    matched pair: raising the symmetry is a measurement of the
    coordinates, and lowering it is a choice between several subgroups
    that the coordinates cannot make for you.
    """

    change = Change.SYMMETRY | Change.CELL | Change.TOPOLOGY

    def __init__(self, subgroup, tol: float = symmetry.MATCH_TOL):
        super().__init__()
        self.subgroup = subgroup
        self.tol = float(tol)
        self.label = f"Descend to {subgroup.symbol}"

    def apply_to(self, structure):
        out, report = subgroups.descend(structure, self.subgroup,
                                        self.tol)
        if report.ok:
            report.message = (
                f"{structure.space_group.short_name} -> "
                f"{self.subgroup.symbol} at index {self.subgroup.index}"
                f": {structure.n_sites} -> {out.n_sites} independent "
                f"sites")
            if not self.subgroup.keeps_the_cell:
                a, b, c, al, be, ga = out.lattice.parameters
                report.warnings.append(
                    f"the cell is now the standard setting of "
                    f"{self.subgroup.symbol}: a={a:.4f} b={b:.4f} "
                    f"c={c:.4f}, {al:.2f} {be:.2f} {ga:.2f}")
        return out, report


class MergeDuplicates(StructureOperation):
    """Merge sites of the same element that landed on top of each
    other.

    Generating a group over coordinates that were already a full cell
    is the standard way to end up with near-duplicate atoms, so every
    symmetry-changing dialog offers this next to it.
    """

    change = Change.TOPOLOGY
    label = "Merge duplicate sites"

    def __init__(self, tol: float = 0.05):
        super().__init__()
        self.tol = float(tol)

    def apply_to(self, structure):
        return symmetry.merge_duplicates(structure, self.tol)
