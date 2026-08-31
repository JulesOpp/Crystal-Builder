"""
xtal.commands.ff
================
Undoable edits that come out of the force field.

Three of them.  An optimisation moves every site at once and lands as a
*single* undo step -- a relaxation is one thing the user asked for, not
two hundred, and Ctrl+Z after it must give back the structure they
started from rather than the second-to-last iteration.  And an atom
type override is an edit like any other, because it changes the answer
the next calculation gives and the user needs to be able to take it
back.  Adding hydrogens is here for the same reason the optimisation
is: what it does to the structure is an ordinary edit, and everything
that decides *what* to do is the force field's typing.

Neither belongs in ``xtal.ff``: that package computes and this one
changes, and the separation is what lets the optimiser run in a worker
thread against a copy while the document stays untouched until the
answer arrives.
"""

from __future__ import annotations

import numpy as np

from xtal.commands.atoms import AddSites
from xtal.commands.base import Command
from xtal.core.lattice import Lattice
from xtal.core.structure import Change


class ApplyOptimizedGeometry(Command):
    """Move every site to where the optimiser left it.

    Deliberately not a :class:`~xtal.commands.atoms.MoveSites`: that
    one merges with the next move of the same sites, which is right for
    dragging and wrong here.  Two optimisations in a row are two
    things that happened, and collapsing them would make the first
    one unreachable.
    """

    change = Change.POSITIONS

    def __init__(self, frac, label: str = "Optimise geometry",
                 report=None, before=None, matrix=None):
        self.frac = np.asarray(frac, dtype=float).reshape(-1, 3)
        self.label = label
        self.report = report
        # A variable-cell relaxation moves the lattice as well, and it
        # has to travel with the coordinates in the *same* command: two
        # commands would mean a Ctrl+Z that put the atoms back into a
        # cell they were never relaxed in.
        self.matrix = (None if matrix is None else
                       np.asarray(matrix, dtype=float).reshape(3, 3))
        self._old_matrix = None
        if self.matrix is not None:
            self.change = Change.POSITIONS | Change.CELL
        # ``before`` matters when the caller has been drawing the
        # optimisation as it ran: the structure then already holds the
        # last previewed geometry, and undo data read from it would
        # take the user back to the second-to-last iteration rather
        # than to where they started.
        self._old = (None if before is None else
                     np.asarray(before, dtype=float).reshape(-1, 3))

    @classmethod
    def from_result(cls, result,
                    label: str = "Optimise geometry"
                    ) -> ApplyOptimizedGeometry:
        """Build from an :class:`xtal.ff.optimize.OptimizationResult`,
        keeping the report so the panel and the status bar can say what
        happened."""
        return cls(result.frac, label, report=result,
                   matrix=getattr(result, "matrix", None))

    def do(self, host) -> None:
        structure = host.structure
        if len(self.frac) != structure.n_sites:
            raise ValueError(
                f"the optimiser returned {len(self.frac)} sites but "
                f"the structure now has {structure.n_sites}; it was "
                f"edited while the calculation was running")
        if self._old is None:
            self._old = structure.frac.copy()
        if self.matrix is not None and self._old_matrix is None:
            self._old_matrix = structure.lattice.matrix.copy()
        for site, frac in zip(structure.sites, self.frac,
                              strict=True):
            site.frac = np.array(frac, dtype=float)
        if self.matrix is not None:
            structure.lattice = Lattice(self.matrix)
        structure.touch(self.change)

    def undo(self, host) -> None:
        structure = host.structure
        for site, frac in zip(structure.sites, self._old, strict=True):
            site.frac = np.array(frac, dtype=float)
        if self._old_matrix is not None:
            structure.lattice = Lattice(self._old_matrix)
        structure.touch(self.change)

    def displacement(self, structure) -> float:
        """The largest distance any atom would move, in Angstrom.

        What the confirmation and the status line should quote: an
        optimisation that moved everything by 0.01 A and one that
        rearranged the crystal are both "converged", and only this
        tells them apart.
        """
        if self._old is not None:
            before = self._old
        else:
            before = structure.frac
        # In the cell it will end up in, which is the cell the atoms
        # are actually in once this has run.
        matrix = (structure.lattice.matrix if self.matrix is None
                  else self.matrix)
        delta = self.frac @ matrix - before @ (
            structure.lattice.matrix if self._old_matrix is None
            else self._old_matrix)
        if not len(delta):
            return 0.0
        return float(np.linalg.norm(delta, axis=1).max())


class SetAtomTypes(Command):
    """Override the force field's own choice of atom type.

    Stored on the site, so it applies to the whole symmetry orbit and
    survives a save: two atoms related by symmetry are one atom seen
    twice, and letting them carry different types would make the energy
    depend on which copy happened to be clicked.

    Passing ``None`` clears the override and hands the site back to the
    typer.
    """

    change = Change.METADATA
    key = "uff_type"

    def __init__(self, indices, type_name: str | None,
                 label: str | None = None):
        self.indices = sorted({int(i) for i in indices})
        self.type_name = type_name
        self.label = label or (
            f"Set atom type to {type_name}" if type_name
            else "Clear atom type override")
        self._old: list = []

    def do(self, host) -> None:
        structure = host.structure
        if not self._old:
            self._old = [structure.sites[i].props.get(self.key)
                         for i in self.indices]
        for index in self.indices:
            props = structure.sites[index].props
            if self.type_name is None:
                props.pop(self.key, None)
            else:
                props[self.key] = self.type_name
        structure.touch(self.change)

    def undo(self, host) -> None:
        structure = host.structure
        for index, previous in zip(self.indices, self._old,
                                   strict=True):
            props = structure.sites[index].props
            if previous is None:
                props.pop(self.key, None)
            else:
                props[self.key] = previous
        structure.touch(self.change)


class SetCharges(Command):
    """Write computed charges onto the sites.

    Equilibrated charges are worth keeping -- they are what the next
    calculation should start from, and they belong in the file -- but
    writing them is a change to the structure and goes on the stack
    like one.
    """

    change = Change.METADATA

    def __init__(self, charges, label: str = "Set charges"):
        self.charges = [None if c is None else float(c)
                        for c in charges]
        self.label = label
        self._old: list = []

    def do(self, host) -> None:
        structure = host.structure
        if len(self.charges) != structure.n_sites:
            raise ValueError(
                f"got {len(self.charges)} charges for "
                f"{structure.n_sites} sites")
        if not self._old:
            self._old = [s.charge for s in structure.sites]
        for site, charge in zip(structure.sites, self.charges,
                                strict=True):
            site.charge = charge
        structure.touch(self.change)

    def undo(self, host) -> None:
        structure = host.structure
        for site, charge in zip(structure.sites, self._old,
                                strict=True):
            site.charge = charge
        structure.touch(self.change)


class AddHydrogens(Command):
    """Put the missing hydrogens back, as one undoable edit.

    The work is :func:`xtal.ff.hydrogens.plan`; what this adds is the
    two things a command has to have.  It **says what it will do before
    it does it** -- :meth:`preview` returns the same plan the run will
    use, so the dialog's count is the count and not an estimate -- and
    it lands as *one* entry on the undo stack however many hydrogens
    it added, because putting the hydrogens back is one thing the user
    asked for.

    One :class:`~xtal.commands.atoms.AddSites` is enough for that: it
    already appends a list.  A ``MacroCommand`` over one command per
    hydrogen would undo identically and describe the operation less
    honestly.
    """

    change = Change.TOPOLOGY
    label = "Add hydrogens"

    def __init__(self, rules=None, xray: bool = False):
        self.rules = rules
        self.xray = bool(xray)
        self.plan = None
        self._for = None
        self._add: AddSites | None = None

    def preview(self, structure):
        """The :class:`~xtal.ff.hydrogens.HydrogenPlan` for this
        structure, computed once and reused when it is run."""
        from xtal.ff import hydrogens

        if self._for is not structure or self.plan is None:
            self.plan = hydrogens.plan(structure, self.rules,
                                       self.xray)
            self._for = structure
        return self.plan

    def do(self, host) -> None:
        plan = self.preview(host.structure)
        self._add = AddSites(plan.sites, label=self.label)
        self._add.do(host)

    def undo(self, host) -> None:
        if self._add is not None:
            self._add.undo(host)
