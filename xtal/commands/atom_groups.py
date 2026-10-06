"""
xtal.commands.atom_groups
=========================
Making, deleting and colouring an atom group, as undo steps.

A group is view state (:mod:`xtal.core.atom_groups`), but making one
is a deliberate act a person wants to take back with Ctrl+Z as much as
any edit -- a colour put on the wrong group, a group deleted by a
misclick.  The structure is never touched; the host's ``atom_groups``
list is.

Each step names its group by row.  The rows move only through these
steps, so a linear history finds the row where the step left it.
Renaming and ticking are not steps and keep the row, which is why the
group is read off the list at the moment it is taken away rather than
remembered from when it was made: a group renamed after it was made
comes back under its new name on a redo.
"""

from __future__ import annotations

from dataclasses import replace

from xtal.commands.base import Command
from xtal.core.structure import Change


class AtomGroupEdit(Command):
    """A step that changes the atom groups and nothing else."""

    change = Change.NONE

    @staticmethod
    def _holds(host, row: int) -> bool:
        return 0 <= row < len(host.atom_groups)


class AddAtomGroup(AtomGroupEdit):
    """Put a new group at the end of the list."""

    def __init__(self, group, label: str = "Make atom group"):
        self.group = group
        self.label = label
        self.row: int | None = None

    def do(self, host) -> None:
        host.atom_groups.append(self.group)
        self.row = len(host.atom_groups) - 1

    def undo(self, host) -> None:
        if self.row is not None and self._holds(host, self.row):
            self.group = host.atom_groups.pop(self.row)


class RemoveAtomGroup(AtomGroupEdit):
    """Take one group out of the list."""

    def __init__(self, row: int, label: str = "Delete atom group"):
        self.row = row
        self.label = label
        self.group = None

    def do(self, host) -> None:
        if self._holds(host, self.row):
            self.group = host.atom_groups.pop(self.row)

    def undo(self, host) -> None:
        if self.group is not None:
            row = min(self.row, len(host.atom_groups))
            host.atom_groups.insert(row, self.group)


class ColourAtomGroup(AtomGroupEdit):
    """Colour one group, or ``None`` for its elements' colours."""

    def __init__(self, row: int, color, label: str = "Colour atom group"):
        self.row = row
        self.color = color
        self.label = label
        self.before = None

    def do(self, host) -> None:
        if self._holds(host, self.row):
            group = host.atom_groups[self.row]
            self.before = group.color
            host.atom_groups[self.row] = replace(group, color=self.color)

    def undo(self, host) -> None:
        if self._holds(host, self.row):
            host.atom_groups[self.row] = replace(
                host.atom_groups[self.row], color=self.before)



class AtomGroupSteps(AtomGroupEdit):
    """Several group steps that undo as one -- a colour or a delete
    applied to every group chosen in the list at once.  Not a
    ``MacroCommand``, whose change would be ``Change.ALL`` for steps
    that change nothing and rebuild every panel for a colour."""

    def __init__(self, steps, label: str):
        self.steps = list(steps)
        self.label = label

    def do(self, host) -> None:
        for step in self.steps:
            step.do(host)

    def undo(self, host) -> None:
        for step in reversed(self.steps):
            step.undo(host)
