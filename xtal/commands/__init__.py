"""
xtal.commands
=============
Undoable structure edits.

    from xtal.commands import CommandStack, Host, atoms

    stack = CommandStack()
    stack.push(atoms.SetElement([0], "Fe"), document)
    stack.undo(document)

Every command works on a host object with a mutable ``structure``
attribute -- the GUI's Document, or :class:`Host` in a script.
"""

from xtal.commands.base import (
    Command,
    CommandStack,
    Host,
    MacroCommand,
    ReplaceStructure,
    SnapshotEdit,
    StructureOperation,
)

__all__ = ["Command", "CommandStack", "Host", "MacroCommand",
           "ReplaceStructure", "SnapshotEdit", "StructureOperation"]
