"""The way back from a bond edit.

``Recalculate bonds`` perceives again and then lays the user's own
edits back over what it found.  That is correct -- a bond somebody
drew is information the distance criteria cannot produce -- and it is
also why the button looked broken: delete a bond, ask for the bonds to
be recalculated, and the graph comes back byte for byte the same with
nothing said about why.

Worse, a deletion is stored as a *suppression* precisely so that
perception cannot undo it, and it is saved with the project.  So once
the undo stack has gone there was no way back from one at all.

These tests are about the two halves of that fix: recalculating says
what it kept, and ``Reset bonds to automatic`` is the thing that drops
it.
"""

import pytest

from xtal.commands import CommandStack, Host
from xtal.commands.bonds import (
    AddBond,
    RecomputeBonds,
    ResetBonds,
    SuppressBond,
)
from xtal.core import bonding
from xtal.core.bonding import TOPOLOGY
from xtal.core.structure import Bond


@pytest.fixture
def suppressed(rutile):
    """Rutile with one Ti-O bond -- and its whole orbit -- deleted."""
    perceived = len(bonding.perceive(rutile))
    rutile.add_bond(Bond(0, 1, (0, 0, 0), kind="suppressed"))
    assert len(bonding.perceive(rutile)) < perceived
    return rutile


def test_recalculating_keeps_a_suppression(suppressed):
    """The behaviour that made the button look broken, pinned: it is
    deliberate, and it is why resetting has to exist."""
    before = {b.key() for b in bonding.perceive(suppressed)}

    host = Host(suppressed)
    CommandStack().push(RecomputeBonds(), host)

    assert {b.key() for b in bonding.perceive(host.structure)} == before


def test_resetting_drops_it(suppressed):
    before = {b.key() for b in bonding.perceive(suppressed)}
    host, stack = Host(suppressed), CommandStack()

    stack.push(ResetBonds(), host)

    after = {b.key() for b in bonding.perceive(host.structure)}
    assert after > before
    assert not [b for b in host.structure.bonds
                if b.kind == "suppressed"]


def test_resetting_can_be_undone(suppressed):
    """It throws away work, so Ctrl+Z has to give it back -- which is
    the whole reason it is a command and not a method."""
    before = {b.key() for b in bonding.perceive(suppressed)}
    host, stack = Host(suppressed), CommandStack()

    stack.push(ResetBonds(), host)
    assert stack.undo(host) is not None

    assert {b.key() for b in bonding.perceive(host.structure)} == before
    assert [b.kind for b in host.structure.bonds] == ["suppressed"]


def test_resetting_drops_a_bond_the_user_drew(rutile):
    """Both kinds of edit, not only the invisible one: a hand-drawn
    bond is an answer to the same question and goes with them."""
    rutile.add_bond(Bond(0, 0, (1, 0, 0), kind="explicit"))
    host, stack = Host(rutile), CommandStack()
    drawn = len(bonding.perceive(rutile))

    stack.push(ResetBonds(), host)

    assert len(bonding.perceive(host.structure)) < drawn
    assert not host.structure.bonds


def test_resetting_leaves_the_net_alone(rutile):
    """A topology edge is not a chemical bond and is not something
    perception would ever produce, so dropping it here would be
    deleting a drawing nobody asked about."""
    rutile.add_bond(Bond(0, 1, (0, 0, 0), kind=TOPOLOGY))
    host, stack = Host(rutile), CommandStack()

    stack.push(ResetBonds(), host)

    assert [b.kind for b in host.structure.bonds] == [TOPOLOGY]


def test_resetting_twice_is_not_a_second_undo_step(suppressed):
    """``do`` is called again by redo, and must not record the state
    it produced itself as the state to go back to."""
    host, stack = Host(suppressed), CommandStack()
    stack.push(ResetBonds(), host)
    stack.undo(host)
    stack.redo(host)
    assert not [b for b in host.structure.bonds
                if b.kind == "suppressed"]
    stack.undo(host)
    assert [b.kind for b in host.structure.bonds] == ["suppressed"]


# ------------------------------------------- drawing over the other answer
#
# A deletion and a drawn bond are two answers to the same question, and
# the structure stores only one record per pair.  Whichever was stored
# first used to win in silence: the second command was refused by
# ``add_bond`` and reported success anyway.


def test_drawing_a_deleted_bond_back_redraws_it(suppressed):
    """The other way back from a deletion, and the one a user reaches
    for first: draw the bond again.  It was refused, because the
    suppression already held the record for that pair."""
    before = {b.key() for b in bonding.perceive(suppressed)}
    host, stack = Host(suppressed), CommandStack()

    command = AddBond(Bond(0, 1, (0, 0, 0), kind="explicit"))
    stack.push(command, host)

    assert command.added
    assert {b.key() for b in bonding.perceive(host.structure)} > before
    assert not [b for b in host.structure.bonds
                if b.kind == "suppressed"]


def test_undoing_that_puts_the_deletion_back(suppressed):
    """The suppression it displaced is work, and Ctrl+Z owes it back."""
    before = {b.key() for b in bonding.perceive(suppressed)}
    host, stack = Host(suppressed), CommandStack()

    stack.push(AddBond(Bond(0, 1, (0, 0, 0), kind="explicit")), host)
    assert stack.undo(host) is not None

    assert {b.key() for b in bonding.perceive(host.structure)} == before
    assert [b.kind for b in host.structure.bonds] == ["suppressed"]


def test_redrawing_survives_a_redo(suppressed):
    """``do`` runs again on redo, and the record it has to displace is
    the one its own undo put back."""
    host, stack = Host(suppressed), CommandStack()

    stack.push(AddBond(Bond(0, 1, (0, 0, 0), kind="explicit")), host)
    stack.undo(host)
    stack.redo(host)

    assert [b.kind for b in host.structure.bonds] == ["explicit"]


def test_deleting_a_bond_the_user_drew_deletes_it(rutile):
    """The mirror of the same refusal: the drawn record held the pair,
    so the suppression was dropped and the bond stayed on screen."""
    rutile.add_bond(Bond(0, 0, (1, 0, 0), kind="explicit"))
    host, stack = Host(rutile), CommandStack()
    drawn = len(bonding.perceive(rutile))

    stack.push(SuppressBond(Bond(0, 0, (1, 0, 0))), host)

    assert len(bonding.perceive(host.structure)) < drawn
    assert [b.kind for b in host.structure.bonds] == ["suppressed"]


def test_undoing_that_puts_the_drawn_bond_back(rutile):
    rutile.add_bond(Bond(0, 0, (1, 0, 0), kind="explicit"))
    host, stack = Host(rutile), CommandStack()
    drawn = len(bonding.perceive(rutile))

    stack.push(SuppressBond(Bond(0, 0, (1, 0, 0))), host)
    assert stack.undo(host) is not None

    assert len(bonding.perceive(host.structure)) == drawn
    assert [b.kind for b in host.structure.bonds] == ["explicit"]


def test_a_net_edge_is_not_the_other_answer(rutile):
    """A topology edge joins the same two atoms and says something
    else, so drawing a bond must not take it away."""
    rutile.add_bond(Bond(0, 1, (0, 0, 0), kind=TOPOLOGY))
    host, stack = Host(rutile), CommandStack()

    stack.push(AddBond(Bond(0, 1, (0, 0, 0), kind="explicit")), host)

    assert sorted(b.kind for b in host.structure.bonds) == sorted(
        [TOPOLOGY, "explicit"])


# ------------------------------------------------------- through the app

def test_the_document_says_what_it_kept(rutile_cif):
    """An unexplained no-op is indistinguishable from a broken
    button, which is what this was reported as."""
    pytest.importorskip("PySide6")
    from xtalapp.document import Document

    document = Document.load(rutile_cif)
    bond = document.graph.bonds[0]
    document.selection.bonds.add(bond.key())
    document.delete_selected_bonds()

    message = document.recompute_bonds()
    assert "you deleted" in message
    assert "Reset bonds" in message


def test_the_document_resets_and_undoes(rutile_cif):
    pytest.importorskip("PySide6")
    from xtalapp.document import Document

    document = Document.load(rutile_cif)
    before = len(document.graph.bonds)
    bond = document.graph.bonds[0]
    document.selection.bonds.add(bond.key())
    document.delete_selected_bonds()
    assert len(document.graph.bonds) < before

    message = document.reset_bonds()
    assert "reset to automatic" in message
    assert len(document.graph.bonds) == before

    assert document.undo()
    assert len(document.graph.bonds) < before


def test_resetting_with_nothing_to_reset_is_a_recalculation(rutile_cif):
    """It must not claim to have thrown edits away when there were
    none -- that is a different sentence and a different event."""
    pytest.importorskip("PySide6")
    from xtalapp.document import Document

    message = Document.load(rutile_cif).reset_bonds()
    assert "recalculated" in message
    assert "gone" not in message


def test_the_document_draws_a_deleted_bond_back(rutile_cif):
    """What Add bond does when the two atoms clicked are the pair whose
    bond was deleted -- reported as the click doing nothing at all."""
    pytest.importorskip("PySide6")
    from xtalapp.document import Document

    document = Document.load(rutile_cif)
    before = len(document.graph.bonds)
    bond = document.graph.bonds[0]
    document.selection.bonds.add(bond.key())
    document.delete_selected_bonds()
    assert len(document.graph.bonds) < before

    message = document.add_bond_between(bond.i, bond.j,
                                        (0, 0, 0), bond.image)

    assert len(document.graph.bonds) == before
    assert "deleted" in message
    assert document.undo()
    assert len(document.graph.bonds) < before
