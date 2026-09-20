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
    MarkOneConnectionPoint,
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


# ------------------------------- a point that stands for several atoms

@pytest.fixture
def chelate() -> Structure:
    """Two carbons bonded to each other and to a pair that continues
    the molecule: the shape of a bidentate attachment before it is
    marked.

    C0 and C1 are the members the point will hang off; C2 and C3 are
    the atoms the user selects and collapses, standing in for the rest
    of the linker.
    """
    lattice = Lattice.cubic(20.0)
    cart = np.array([[-0.70, -1.21, 0.0], [0.70, -1.21, 0.0],
                     [-0.70, 0.21, 0.0], [0.70, 0.21, 0.0],
                     [-1.40, -2.42, 0.0], [1.40, -2.42, 0.0]]) + 10.0
    structure = Structure.from_arrays(
        lattice, ["C", "C", "C", "C", "H", "H"],
        lattice.to_frac(cart), space_group="P1")
    for i, j in ((0, 1), (0, 2), (1, 3), (2, 3), (0, 4), (1, 5)):
        structure.add_bond(Bond(i, j, (0, 0, 0), 1.0))
    return structure


def marked_one(structure, atoms, sites):
    host = Host(structure)
    stack = CommandStack()
    command = MarkOneConnectionPoint(atoms, sites)
    stack.push(command, host)
    return host, stack, command


def test_two_atoms_become_one_connection_point(chelate):
    """Not two.  Marking them one at a time gives a block with twice
    the coordination number it has, which fits no net in the
    catalogue."""
    host, _stack, command = marked_one(chelate, [2, 3], [2, 3])
    cell = p1.expand(host.structure)

    assert list(cell.elements).count(CONNECTION) == 1
    assert host.structure.n_sites == 5
    assert command.summary() == ("marked 2 atoms as one connection "
                                 "point")


def test_the_point_sits_above_the_middle_of_what_it_hangs_off(
        chelate):
    """0.75 A from the centroid of its members, and further than that
    from either of them -- it is where the next block's own point has
    to land for the two ends to meet."""
    host, _stack, _command = marked_one(chelate, [2, 3], [2, 3])
    cell = p1.expand(host.structure)
    point = int(np.flatnonzero(
        np.array(cell.elements) == CONNECTION)[0])
    middle = (cell.cart[0] + cell.cart[1]) / 2.0

    assert np.linalg.norm(
        cell.cart[point] - middle) == pytest.approx(
            CONNECTION_DISTANCE, abs=1e-9)
    assert distance(host.structure, point, 0) > 1.0
    assert distance(host.structure, point, 1) > 1.0


def test_the_point_takes_over_every_bond_out_of_the_group(chelate):
    """Both of them, explicitly.  Perception never bonds a dummy, so
    a point that did not carry the bonds over would float free of the
    molecule on the next read of the graph -- and the direction it
    carries is the whole of what it is for."""
    host, _stack, _command = marked_one(chelate, [2, 3], [2, 3])
    cell = p1.expand(host.structure)
    graph = bonding.graph(host.structure)
    point = int(np.flatnonzero(
        np.array(cell.elements) == CONNECTION)[0])

    assert sorted(graph.neighbors(point)) == [0, 1]
    assert all(bond.explicit for bond in graph.bonds_of(point))


def test_marking_a_group_as_one_point_is_one_undo_step(chelate):
    """Three commands inside it -- the add, the bonds, the delete --
    and one press of Ctrl+Z."""
    host, stack, _command = marked_one(chelate, [2, 3], [2, 3])

    assert stack.depth == 1
    stack.undo(host)

    assert host.structure.n_sites == 6
    assert list(p1.expand(host.structure).elements) == [
        "C", "C", "C", "C", "H", "H"]
    assert not stack.can_undo


def test_undo_then_redo_puts_the_point_back(chelate):
    host, stack, _command = marked_one(chelate, [2, 3], [2, 3])
    stack.undo(host)
    stack.redo(host)
    cell = p1.expand(host.structure)

    assert list(cell.elements).count(CONNECTION) == 1
    assert host.structure.n_sites == 5


def test_one_atom_is_the_other_command_s_gesture(chelate):
    """Named rather than silently done: one atom on the end of one
    bond is Mark connection points, and doing that here would delete
    the atom and add a different one."""
    host, stack, command = marked_one(chelate, [2], [2])

    assert command.placed is None
    assert any("two or more" in line for line in command.refused)
    assert host.structure.n_sites == 6
    assert stack.depth == 1


def test_a_group_bonded_to_nothing_outside_itself_is_refused():
    """There is no direction to point along, and inventing one is how
    a block gets built along a direction nobody wrote down."""
    lattice = Lattice.cubic(20.0)
    pair = Structure.from_arrays(
        lattice, ["C", "C"],
        lattice.to_frac(np.array([[-0.7, 0.0, 0.0], [0.7, 0.0, 0.0]])
                        + 10.0),
        space_group="P1")
    pair.add_bond(Bond(0, 1, (0, 0, 0), 1.0))
    host, _stack, command = marked_one(pair, [0, 1], [0, 1])

    assert command.placed is None
    assert any("bonded to nothing outside" in line
               for line in command.refused)
    assert host.structure.n_sites == 2


def test_a_group_across_the_cell_boundary_is_gathered_first(chelate):
    """A molecule lying across a face is two pieces a cell apart in
    the wrapped coordinates, and a point placed at the average of
    those is in the vacuum in the middle of the box."""
    wrapped = chelate.copy()
    for site in wrapped.sites:
        site.frac = (site.frac + np.array([0.49, 0.0, 0.0])) % 1.0
    host, _stack, _command = marked_one(wrapped, [2, 3], [2, 3])
    cell = p1.expand(host.structure)
    graph = bonding.graph(host.structure)
    point = int(np.flatnonzero(
        np.array(cell.elements) == CONNECTION)[0])

    assert sorted(graph.neighbors(point)) == [0, 1]
    matrix = host.structure.lattice.matrix
    for j, image in graph.neighbors_with_images(point):
        reach = cell.cart[j] + image @ matrix - cell.cart[point]
        assert np.linalg.norm(reach) == pytest.approx(
            np.sqrt(CONNECTION_DISTANCE ** 2 + 0.70 ** 2), abs=1e-6)
