"""Marking an atom as a connection point, in an open structure.

The other half of Phase U's building-block path: a molecule is built
or opened, an atom on the end of a bond is marked, and what comes out
is what :mod:`xtal.mof.block` writes.
"""

from __future__ import annotations

import numpy as np
import pytest

from xtal.commands import CommandStack, Host
from xtal.commands.connections import (
    CONNECTION,
    MarkConnectionPoints,
    plan,
)
from xtal.core import bonding, p1
from xtal.core.lattice import Lattice
from xtal.core.structure import Bond, Site, Structure
from xtal.mof.block import CONNECTION_DISTANCE


@pytest.fixture
def methane() -> Structure:
    """CH4 in a box, with its bonds stated rather than perceived --
    the shape a molecule built from a SMILES string arrives in."""
    d = 1.087 / np.sqrt(3.0)
    lattice = Lattice.cubic(14.0)
    cart = np.array([[0.0, 0.0, 0.0],
                     [d, d, d], [d, -d, -d],
                     [-d, d, -d], [-d, -d, d]]) + 7.0
    structure = Structure.from_arrays(
        lattice, ["C", "H", "H", "H", "H"], lattice.to_frac(cart),
        space_group="P1")
    for j in (1, 2, 3, 4):
        structure.add_bond(Bond(0, j, (0, 0, 0), 1.0))
    return structure


def marked(structure, sites):
    host = Host(structure)
    stack = CommandStack()
    command = MarkConnectionPoints(sites)
    stack.push(command, host)
    return host, stack, command


def distance(structure, a: int, b: int) -> float:
    cell = p1.expand(structure)
    return float(np.linalg.norm(cell.cart[a] - cell.cart[b]))


def test_a_hydrogen_becomes_a_dummy_at_the_connection_distance(
        methane):
    """Not at a bond length.  A block written with its connection
    points at 1.4 A builds a framework with every linker bond twice
    too long and nothing reports it."""
    host, _stack, command = marked(methane.copy(), [1])

    assert command.marked == [1]
    assert host.structure.sites[1].element == CONNECTION
    assert distance(host.structure, 0, 1) == pytest.approx(
        CONNECTION_DISTANCE, abs=1e-6)


def test_marking_keeps_the_direction_and_only_changes_the_length(
        methane):
    """The direction is where the next building block goes, and it
    came from a relaxed geometry."""
    before = p1.expand(methane)
    was = before.cart[1] - before.cart[0]
    host, _stack, _command = marked(methane.copy(), [1])
    now = p1.expand(host.structure)
    is_now = now.cart[1] - now.cart[0]

    assert np.dot(was, is_now) > 0
    assert np.linalg.norm(np.cross(was, is_now)) == pytest.approx(
        0.0, abs=1e-6)


def test_one_undo_gives_back_both_the_element_and_the_position(
        methane):
    """The user made one gesture.  Two commands would be two presses,
    and one press would leave a carbon 0.75 A from its neighbour."""
    before = methane.copy()
    host, stack, _command = marked(methane.copy(), [1, 2])
    stack.undo(host)

    assert host.structure == before
    assert stack.can_redo


def test_several_atoms_are_marked_in_one_step(methane):
    """Three atoms, one gesture, one press of Ctrl+Z."""
    before = methane.copy()
    host, stack, command = marked(methane.copy(), [1, 2, 3])
    assert command.marked == [1, 2, 3]

    stack.undo(host)
    assert host.structure == before
    assert not stack.can_undo


def test_an_atom_with_several_bonds_is_refused_by_name(methane):
    """"3 atoms could not be marked" tells somebody with twenty
    selected nothing; the label of the one with four bonds tells them
    where to look."""
    host, _stack, command = marked(methane.copy(), [0, 1])

    assert command.marked == [1]
    assert host.structure.sites[0].element == "C"
    assert len(command.refused) == 1
    assert "C 1" in command.refused[0]
    assert "4 bond" in command.refused[0]
    assert "left alone" in command.summary()


def test_an_atom_with_no_bonds_at_all_is_refused_by_name(methane):
    structure = methane.copy()
    structure.add_sites([Site("Ar", [0.1, 0.1, 0.1], label="Ar6")])
    _host, _stack, command = marked(structure, [5])

    assert command.marked == []
    assert "Ar6" in command.refused[0]
    assert "0 bond" in command.refused[0]
    assert command.summary() == command.refused[0]


def test_a_perceived_bond_is_written_down_before_the_element_changes(
        methane):
    """Perception never bonds a dummy, so an atom whose only bond was
    perceived would be marked and then float free of the molecule it
    belongs to -- losing the direction, silently."""
    loose = methane.copy()
    loose.set_bonds([])                 # nothing stated: all perceived
    assert len(bonding.graph(loose).bonds_of(1)) == 1

    host, stack, _command = marked(loose, [1])
    graph = bonding.graph(host.structure)

    assert len(host.structure.bonds) == 1
    assert graph.bonds_of(1) and graph.bonds_of(1)[0].explicit
    stack.undo(host)
    assert host.structure.bonds == []


def test_an_explicit_bond_is_left_exactly_as_it_was(methane):
    """There is nothing to save: the bond is already the user's."""
    host, _stack, _command = marked(methane.copy(), [1])
    assert len(host.structure.bonds) == 4


def test_planning_says_what_would_happen_without_doing_it(methane):
    targets, bonds, refused = plan(methane, [0, 1])

    assert list(targets) == [1]
    assert bonds == []
    assert refused and "C 1" in refused[0]
    assert methane.sites[1].element == "H"


def test_marking_in_a_symmetric_structure_marks_the_whole_orbit(
        dry_ice):
    """Symmetry ties images together and a site edit is a site edit:
    marking one oxygen of the eight marks all eight.  Worth knowing
    before it happens, which is why a building block is drawn in P1."""
    host, _stack, command = marked(dry_ice.copy(), [1])
    cell = p1.expand(host.structure)
    images = cell.indices_of_site(1)

    assert command.marked == [1]
    assert len(images) == 8
    assert all(cell.elements[a] == CONNECTION for a in images)
    assert distance(host.structure, 0, int(images[0])) == \
        pytest.approx(CONNECTION_DISTANCE, abs=1e-6)
