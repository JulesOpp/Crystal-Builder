"""The undo history keeps what an undo needs and lets go of the rest.

Whole-structure steps (a supercell, Reduce to P1) keep the crystal
they replaced, and that crystal kept every memo it had ever been asked
for: an MFU-4l 3x3x3 held 43 MB a step, under a cap of two hundred
steps.  Only the top step keeps its cache now, and the history is
trimmed by the sites it holds as well as by its count.
"""

import pytest

from xtal.commands import CommandStack, Host
from xtal.commands import cell as cell_commands
from xtal.commands.base import ReplaceStructure
from xtal.commands.symmetry import ReduceToP1
from xtal.core import bonding, limits, p1


def warm(structure):
    """What the window asks of a structure it draws."""
    p1.expand(structure)
    bonding.graph(structure)


@pytest.fixture
def history(rutile):
    host = Host(rutile.copy())
    warm(host.structure)
    stack = CommandStack()
    for command in (cell_commands.Supercell(2, 2, 2), ReduceToP1(),
                    cell_commands.WrapIntoCell()):
        stack.push(command, host)
        warm(host.structure)
    return host, stack


def test_an_old_whole_structure_step_holds_no_cache(history):
    """Only the top step keeps its memo, so undoing it stays instant;
    the steps under it hold the crystal and nothing derived from it."""
    _host, stack = history
    supercell, reduce, top = stack._done

    assert not supercell._old._cache
    assert not reduce._old._cache
    assert top._old._cache


def test_undoing_an_old_supercell_gives_back_its_bonds_without_perceiving(
        history, monkeypatch):
    """The stored graph is not cache: dropping the memo must not make
    an undo perceive the bonds again, which would break *bonds are
    recalculated only when the user asks*."""
    host, stack = history
    searched = []
    search = bonding._search
    monkeypatch.setattr(bonding, "_search",
                        lambda *a, **k: searched.append(1)
                        or search(*a, **k))

    for _ in range(3):
        stack.undo(host)
        warm(host.structure)

    assert searched == []
    assert bonding.graph(host.structure).bonds


def test_history_is_trimmed_by_atoms_not_only_by_steps(rutile):
    """Steps that each hold a big crystal are let go, oldest first,
    long before the count runs out; ``trimmed`` says how many."""
    host = Host(rutile.copy())
    stack = CommandStack(atom_budget=100)
    for _ in range(limits.UNDO_KEEP + 3):
        stack.push(ReplaceStructure(_supercell(rutile)), host)

    # Each step holds a 48-site P1 cell: over 100, so the history is
    # its five most recent steps, two hundred short of its count.
    assert stack.depth == limits.UNDO_KEEP < stack.limit
    assert stack.trimmed == 1


def _supercell(structure):
    from xtal.core import supercell, symmetry
    return symmetry.reduce_to_p1(supercell.supercell(structure, 2, 2, 2))


def test_the_last_five_steps_are_never_trimmed(rutile):
    """However much they hold: a budget that took the step just made
    would make Ctrl+Z do nothing."""
    host = Host(rutile.copy())
    stack = CommandStack(atom_budget=1)
    for _ in range(limits.UNDO_KEEP):
        stack.push(ReduceToP1(), host)

    assert stack.depth == limits.UNDO_KEEP
    assert stack.trimmed == 0
    for _ in range(limits.UNDO_KEEP):
        assert stack.undo(host) is not None


def test_trimming_below_the_save_point_leaves_the_document_modified(
        rutile):
    """The step that would undo back to the saved file is gone, so no
    amount of undoing may call the document clean again."""
    host = Host(rutile.copy())
    stack = CommandStack(atom_budget=1)
    stack.mark_clean()
    for _ in range(limits.UNDO_KEEP + 1):
        stack.push(ReduceToP1(), host)
    while stack.undo(host) is not None:
        pass

    assert not stack.is_clean
