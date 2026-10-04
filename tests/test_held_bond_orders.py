"""A bond order, once inferred, is held until the bonds are recalculated.

The order of a bond nobody set is read off the geometry, and it used to
be read again on every chemistry change: a hydrogen added to a MOF-5
ring carbon turned two of the ring's bonds single, a relaxed cell
turned eight more, and an atom dragged and then any edit at all
re-read the moved geometry.  Bond types change when the user asks --
Recalculate Bonds, or Set Bond Type -- and these tests hold that.
"""

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.commands import CommandStack, Host
from xtal.commands import atoms as atom_commands
from xtal.commands.bonds import RecomputeBonds
from xtal.commands.ff import ApplyOptimizedGeometry
from xtal.core import bonding, p1
from xtal.core.site import Site


@pytest.fixture
def ethylene() -> Structure:
    """Two bare carbons 1.33 A apart: a double bond by its length."""
    return Structure.from_arrays(
        Lattice.cubic(8.0), ["C", "C"],
        [[0.40, 0.5, 0.5], [0.40 + 1.33 / 8.0, 0.5, 0.5]])


def order_of_cc(structure) -> float:
    graph = bonding.graph(structure)
    orders = bonding.orders(structure)
    (k,) = [k for k, b in enumerate(graph.bonds) if {b.i, b.j} == {0, 1}]
    return float(orders[k])


def stretched(structure, stack, host) -> None:
    """The second carbon pulled out to a single bond's length."""
    stack.push(atom_commands.MoveSites(
        {1: [0.40 + 1.54 / 8.0, 0.5, 0.5]}), host)


def test_a_moved_atom_keeps_its_bond_type_through_the_next_edit(
        ethylene):
    """Moving is positions only and the memo survived it; the next
    edit of any kind re-read the stretched bond as single."""
    host = Host(ethylene)
    stack = CommandStack()
    assert order_of_cc(ethylene) == 2.0
    stretched(ethylene, stack, host)
    assert order_of_cc(ethylene) == 2.0
    stack.push(atom_commands.AddSites(
        [Site("O", [0.9, 0.1, 0.1])], perceive=False), host)
    assert order_of_cc(ethylene) == 2.0


def test_a_relaxed_cell_keeps_every_bond_type(ethylene):
    host = Host(ethylene)
    stack = CommandStack()
    assert order_of_cc(ethylene) == 2.0
    stack.push(ApplyOptimizedGeometry(
        ethylene.frac, matrix=ethylene.lattice.matrix * 1.16), host)
    assert order_of_cc(ethylene) == 2.0


def test_recalculating_the_bonds_reads_the_types_afresh(ethylene):
    host = Host(ethylene)
    stack = CommandStack()
    assert order_of_cc(ethylene) == 2.0
    stretched(ethylene, stack, host)
    stack.push(RecomputeBonds(), host)
    assert order_of_cc(ethylene) == 1.0
    stack.undo(host)
    assert order_of_cc(ethylene) == 2.0


def test_a_project_round_trip_keeps_the_held_bond_types(ethylene,
                                                        tmp_path):
    from xtal.io.project import read_project, write_project

    host = Host(ethylene)
    stack = CommandStack()
    assert order_of_cc(ethylene) == 2.0
    stretched(ethylene, stack, host)
    path = write_project(ethylene, tmp_path / "p.xtalproj")
    back, _view, _session = read_project(path)
    assert order_of_cc(back) == 2.0


def test_a_removed_atom_leaves_the_others_their_bond_types():
    """Deleting renumbers the cell, and a held order has to move with
    its bond rather than stay on the numbers."""
    structure = Structure.from_arrays(
        Lattice.cubic(8.0), ["O", "C", "C"],
        [[0.1, 0.1, 0.1], [0.40, 0.5, 0.5],
         [0.40 + 1.33 / 8.0, 0.5, 0.5]])
    host = Host(structure)
    stack = CommandStack()
    assert list(bonding.orders(structure)) == [2.0]
    stack.push(atom_commands.MoveSites(
        {2: [0.40 + 1.54 / 8.0, 0.5, 0.5]}), host)
    stack.push(atom_commands.DeleteSites([0]), host)
    assert order_of_cc(structure) == 2.0


@pytest.mark.slow
def test_a_hydrogen_added_to_a_ring_leaves_the_ring_aromatic(tmp_path):
    """MOF-5: an H bonded to a ring carbon turned two ring bonds single
    by the new coordination's reading."""
    from xtal.agent.session import Session

    session = Session.open("resources/samples/MOF-5.cif",
                           workspace=tmp_path)
    session.reduce_to_p1()
    structure = session.structure
    graph = bonding.graph(structure)
    before = {b.key(): float(o) for b, o in
              zip(graph.bonds, bonding.orders(structure), strict=True)}
    cell = session.cell
    carbon = next(i for i, e in enumerate(cell.elements) if e == "C")
    result = session.add_atom(
        "H", cart=list(cell.cart[carbon] + [0.0, 0.0, 1.1]),
        bonded_to=carbon)
    assert result.ok
    graph = bonding.graph(structure)
    after = {b.key(): float(o) for b, o in
             zip(graph.bonds, bonding.orders(structure), strict=True)}
    changed = [k for k in before if after.get(k) != before[k]]
    assert changed == []


def test_the_held_orders_are_not_shared_with_an_undo_record(ethylene):
    """An undo puts back the graph object it saved; orders written
    for atoms added later must not land in it."""
    host = Host(ethylene)
    stack = CommandStack()
    bonding.orders(ethylene)
    saved = ethylene.perceived
    held = dict(saved.orders)
    stack.push(atom_commands.AddBondedSite(
        Site("H", [0.40 - 1.09 / 8.0, 0.5, 0.5]), anchor=0), host)
    bonding.orders(ethylene)
    assert saved.orders == held
    assert len(p1.expand(ethylene).elements) == 3
    assert np.isfinite(bonding.orders(ethylene)).all()
