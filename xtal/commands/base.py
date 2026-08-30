"""
xtal.commands.base
==================
The command pattern: every change to a structure, as an object that
knows how to undo itself.

Nothing in the application mutates a Structure directly.  A widget
builds a Command and pushes it onto the document's stack; the stack
runs it, remembers it, and can run it backwards.  Undo/redo, macros,
copy/paste and (later) a scripting console are all the same mechanism
seen from different angles.

Two rules make this cheap rather than heavy:

**Commands store their own inverse, not a snapshot.**  Deleting three
atoms remembers three atoms, not the whole crystal.  Operations that
really do replace everything -- a supercell, a change of space group --
use :class:`ReplaceStructure`, or :class:`StructureOperation` when the
new structure is something they work out for themselves; there a
snapshot genuinely is the smaller description.

**Commands are pushed after they are built, not after they are run.**
The stack runs them.  That is what lets it merge a drag into one undo
step, group a dialog's five changes into one, and keep the redo branch
correct.

The host is anything with a mutable ``structure`` attribute -- the
Document in the application, a one-line stand-in in the tests.  Keeping
it to that one attribute is what stops Qt from leaking into the core.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field

from xtal.core.structure import Change, Structure

DEFAULT_HISTORY = 200


@dataclass
class Host:
    """Minimal command target: something that holds a structure."""

    structure: Structure


class Command(ABC):
    """One undoable change."""

    label: str = "Edit"
    change: Change = Change.ALL

    @abstractmethod
    def do(self, host) -> None:
        """Apply the change."""

    @abstractmethod
    def undo(self, host) -> None:
        """Put things back exactly as they were."""

    def merge_with(self, other: Command) -> bool:
        """Absorb a later command of the same kind, returning whether
        it was absorbed.

        This is what turns a drag, or a spinbox held down, into a
        single undo step.  Only ever merge commands that are still part
        of the same gesture -- the stack asks, it does not insist.
        """
        return False

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.label!r})"


class MacroCommand(Command):
    """Several commands that undo as one."""

    def __init__(self, label: str, commands=None):
        self.label = label
        self.commands: list[Command] = list(commands or [])

    def add(self, command: Command) -> None:
        self.commands.append(command)

    @property
    def change(self) -> Change:
        result = Change.NONE
        for command in self.commands:
            result |= command.change
        return result or Change.ALL

    def do(self, host) -> None:
        for command in self.commands:
            command.do(host)

    def undo(self, host) -> None:
        for command in reversed(self.commands):
            command.undo(host)

    def __len__(self) -> int:
        return len(self.commands)


class ReplaceStructure(Command):
    """Swap the whole structure -- the honest form for operations that
    rebuild it (supercell, symmetry changes, cell transformations).

    The old structure *is* the undo data, so nothing smaller would be
    correct here.
    """

    def __init__(self, structure: Structure, label: str = "Replace",
                 change: Change = Change.ALL):
        self.label = label
        self.change = change
        self._new = structure
        self._old: Structure | None = None

    def do(self, host) -> None:
        self._old = host.structure
        host.structure = self._new

    def undo(self, host) -> None:
        host.structure = self._old


class StructureOperation(Command):
    """A command that rebuilds the structure from scratch, and can say
    what it will do before it does it.

    Symmetry and cell operations are the ones users hesitate over --
    "how many atoms will this leave me with?", "did it find the group I
    expected?" -- so every one of them computes a result *and* a report,
    and the dialog can ask for both through :meth:`preview` while the
    user is still deciding.  Running the command then reuses that work
    instead of doing it twice.

    Subclasses implement :meth:`apply_to`, which returns
    ``(new_structure, report)``.  The report is free-form: what it is
    depends on the operation, and nothing here reads it.
    """

    change = Change.ALL
    label = "Rebuild"

    def __init__(self):
        self._old: Structure | None = None
        self._for: Structure | None = None
        self._result: tuple | None = None
        self.report = None

    def apply_to(self, structure: Structure) -> tuple:
        """(new structure, report).  Must not mutate ``structure``."""
        raise NotImplementedError

    def preview(self, structure: Structure) -> tuple:
        """What running this on ``structure`` would produce."""
        if self._for is not structure or self._result is None:
            self._result = self.apply_to(structure)
            self._for = structure
        return self._result

    def do(self, host) -> None:
        self._old = host.structure
        new, self.report = self.preview(host.structure)
        host.structure = new

    def undo(self, host) -> None:
        host.structure = self._old


class SnapshotEdit(Command):
    """An arbitrary mutation, made undoable by keeping a copy.

    The escape hatch for edits that have no dedicated command yet -- a
    line in the Python console, a one-off script, a test.  It costs a
    full copy of the structure, which is why it is the exception and
    not the rule: a real command remembers only what it changed.
    """

    def __init__(self, mutate, label: str = "Edit",
                 change: Change = Change.ALL):
        self.mutate = mutate
        self.label = label
        self.change = change
        self._before: Structure | None = None
        self._after: Structure | None = None

    def do(self, host) -> None:
        if self._after is not None:             # redo
            host.structure = self._after
            return
        self._before = host.structure.copy()
        self.mutate(host.structure)
        self._after = host.structure

    def undo(self, host) -> None:
        self._after = host.structure
        host.structure = self._before.copy()


# ======================================================================
#  THE STACK
# ======================================================================

@dataclass
class CommandStack:
    """Bounded undo/redo history over a host's structure."""

    limit: int = DEFAULT_HISTORY
    _done: list = field(default_factory=list, repr=False)
    _undone: list = field(default_factory=list, repr=False)
    _macro: MacroCommand | None = field(default=None, repr=False)
    _clean_depth: int = 0

    # -- running commands ----------------------------------------------

    def push(self, command: Command, host) -> Command:
        """Run ``command`` and add it to the history."""
        command.do(host)
        if self._macro is not None:
            self._macro.add(command)
            return command

        self._undone.clear()
        if self._done and self._done[-1].merge_with(command):
            return self._done[-1]
        self._done.append(command)
        if len(self._done) > self.limit:
            trimmed = len(self._done) - self.limit
            del self._done[:trimmed]
            self._clean_depth -= trimmed
        return command

    def undo(self, host) -> Command | None:
        if not self._done:
            return None
        command = self._done.pop()
        command.undo(host)
        self._undone.append(command)
        return command

    def redo(self, host) -> Command | None:
        if not self._undone:
            return None
        command = self._undone.pop()
        command.do(host)
        self._done.append(command)
        return command

    # -- macros --------------------------------------------------------

    @contextmanager
    def transaction(self, label: str, host):
        """Group everything pushed inside into one undo step.

        An empty transaction adds nothing to the history, and an
        exception inside it rolls back what had already run -- a
        half-applied dialog is worse than a cancelled one.
        """
        if self._macro is not None:                 # already grouping
            yield self._macro
            return
        macro = MacroCommand(label)
        self._macro = macro
        try:
            yield macro
        except Exception:
            self._macro = None
            macro.undo(host)
            raise
        self._macro = None
        if len(macro):
            self._undone.clear()
            self._done.append(macro)
            if len(self._done) > self.limit:
                del self._done[0]

    # -- state ---------------------------------------------------------

    @property
    def can_undo(self) -> bool:
        return bool(self._done)

    @property
    def can_redo(self) -> bool:
        return bool(self._undone)

    @property
    def undo_label(self) -> str:
        return self._done[-1].label if self._done else ""

    @property
    def redo_label(self) -> str:
        return self._undone[-1].label if self._undone else ""

    @property
    def depth(self) -> int:
        return len(self._done)

    def clear(self) -> None:
        self._done.clear()
        self._undone.clear()
        self._macro = None
        self._clean_depth = 0

    # -- modified tracking ---------------------------------------------
    #
    # "Modified" is not a flag that edits set and saves clear -- undo
    # back to where you saved and the document is clean again, which is
    # what every other editor does.

    def mark_clean(self) -> None:
        self._clean_depth = len(self._done)

    @property
    def is_clean(self) -> bool:
        return len(self._done) == self._clean_depth
