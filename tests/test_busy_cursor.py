"""The wait cursor over an edit, and never left behind.

Every command a click runs goes through ``Document.run``, and some of
them take seconds on a framework -- Supercell, Reduce to P1, Set Bond
Type over everything.  The cursor says the window is working.  What
must never happen is the cursor staying *wait* after the work, which
reads as a hung application for the rest of the session.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from xtal.commands.base import Command  # noqa: E402
from xtal.core.structure import Change  # noqa: E402
from xtalapp.document import Document  # noqa: E402


def cursor():
    override = QGuiApplication.overrideCursor()
    return None if override is None else override.shape()


class Watching(Command):
    """A command that records the cursor it ran under."""

    label = "Watch"
    change = Change.NONE

    def __init__(self, fail=False):
        self.fail = fail
        self.seen = []

    def do(self, host):
        self.seen.append(cursor())
        if self.fail:
            raise RuntimeError("the command failed")

    def undo(self, host):
        self.seen.append(cursor())


class Merging(Watching):
    """One step of a gesture: it merges with the next."""

    def merge_with(self, other):
        return False


@pytest.fixture
def document(qapp, rutile):
    return Document(rutile)


def test_a_command_runs_under_the_wait_cursor(document):
    command = Watching()
    document.run(command)
    assert command.seen == [Qt.WaitCursor]
    assert cursor() is None


def test_undo_and_redo_run_under_the_wait_cursor(document):
    command = Watching()
    document.run(command)
    document.undo()
    document.redo()
    assert command.seen == [Qt.WaitCursor] * 3
    assert cursor() is None


def test_a_structure_edit_restores_the_cursor_even_when_it_raises(
        document):
    """A command that fails part way must still hand the cursor back;
    otherwise every click after it looks like the window is busy."""
    with pytest.raises(RuntimeError):
        document.run(Watching(fail=True))
    assert cursor() is None


def test_a_step_of_a_drag_does_not_flash_the_wait_cursor(document):
    """A drag runs a merging command per mouse event; a cursor that
    flickers to *wait* at every one is worse than none."""
    command = Merging()
    document.run(command)
    assert command.seen == [None]
