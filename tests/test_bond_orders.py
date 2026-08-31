"""Bond order: inferred in the core, and drawn in the picture.

The inference used to live inside the UFF typer and to be expressed in
UFF's own type names, which meant the viewport could not ask how many
tubes to draw without importing a force field.  It is chemistry, so it
lives in :mod:`xtal.core.bonding` now, and these tests are chemistry
too: carbon dioxide is O=C=O, butadiene's double bonds are on the
outside, benzene is aromatic all the way round, and ethane has none.

The drawing half is asserted on the scene model rather than on pixels.
Two tubes for a double bond is a claim about how many line segments
come out of :func:`~xtalapp.viewport.scene.split_by_order`, and the one
thing that is genuinely hard -- which way the second tube is offset --
is a claim about a direction, which is a number a test can check.
"""

import math

import numpy as np

from tests.conftest_ff import (
    benzene,
    butadiene,
    carbon_dioxide,
    ethane,
    isolated,
)
from xtal import Lattice, Structure
from xtal.core import bonding, p1
from xtal.core.structure import Bond, Change
from xtalapp.viewport import scene as scene_module
from xtalapp.viewport.builder import _bond_frames, build_scene
from xtalapp.viewport.view_settings import ViewSettings


def orders_by_pair(structure) -> dict:
    graph = bonding.graph(structure)
    return {tuple(sorted((b.i, b.j))): float(o)
            for b, o in zip(graph.bonds, bonding.orders(structure),
                            strict=True)}


# ============================================================ the count

def test_carbon_dioxide_is_doubly_bonded_at_both_ends():
    """An sp carbon has two pi bonds to place, not one.  Pairing atoms
    off one at a time gives O=C-O, which is wrong."""
    assert sorted(bonding.orders(carbon_dioxide())) == [2.0, 2.0]


def test_butadiene_puts_the_double_bonds_on_the_outside():
    """All four carbons are sp2, so the assignment comes from the
    lengths: the short bonds are the double ones.  The two terminal
    carbons have one neighbour and no angles at all, so this is also
    the test that the length rule works on them."""
    orders = orders_by_pair(butadiene())
    assert orders[(0, 1)] == 2.0
    assert orders[(1, 2)] == 1.0
    assert orders[(2, 3)] == 2.0


def test_benzene_is_aromatic_all_the_way_round():
    assert list(bonding.orders(benzene(with_hydrogen=False))) == [1.5] * 6


def test_a_saturated_molecule_is_all_single_bonds():
    assert set(bonding.orders(ethane())) == {1.0}


def test_a_framework_has_no_multiple_bonds(quartz, rutile):
    """The common case, and the reason drawing orders is safe to leave
    on: an oxide gets exactly the picture it had before."""
    assert set(bonding.orders(quartz)) == {1.0}
    assert set(bonding.orders(rutile)) == {1.0}


def test_an_order_the_user_set_beats_the_inference():
    """Perception decides whether two atoms are bonded.  It does not
    get to overrule what the user said the bond is."""
    structure = ethane()
    structure.bonds.append(Bond(0, 1, (0, 0, 0), order=2.0))
    structure.touch()
    orders = orders_by_pair(structure)
    assert orders[(0, 1)] == 2.0


def test_a_stated_order_does_not_get_spent_twice():
    """A bond called double has already used the pi electrons at both
    ends; the inference must not hand them out again elsewhere in the
    same molecule."""
    structure = butadiene()
    structure.bonds.append(Bond(1, 2, (0, 0, 0), order=2.0))
    structure.touch()
    orders = orders_by_pair(structure)
    assert orders[(1, 2)] == 2.0
    assert orders[(0, 1)] == 1.0        # C1 has nothing left to give
    assert orders[(2, 3)] == 1.0


def test_an_empty_structure_has_no_orders():
    empty = Structure.from_arrays(Lattice.cubic(10.0), [],
                                  np.zeros((0, 3)), space_group="P1")
    assert len(bonding.orders(empty)) == 0


def test_the_force_field_reads_the_same_numbers():
    """The typer consumes the core's orders rather than producing its
    own, so the picture and the energy cannot disagree about what a
    bond is."""
    from xtal.ff.uff import typer
    structure = butadiene()
    assert list(typer.assign(structure).bond_orders) == \
        list(bonding.orders(structure))


# ========================================================== the picture

def test_a_double_bond_is_drawn_as_two_tubes():
    model = build_scene(carbon_dioxide(), ViewSettings())
    solid, dashed = scene_module.split_by_order(model)
    assert len(solid[0]) == 2 * model.n_bond_halves
    assert len(dashed[0]) == 0


def test_a_triple_bond_is_drawn_as_three():
    acetylene = isolated(["C", "C"], [[0, 0, 0], [1.20, 0, 0]])
    assert set(bonding.orders(acetylene)) == {3.0}
    model = build_scene(acetylene, ViewSettings())
    solid, _dashed = scene_module.split_by_order(model)
    assert len(solid[0]) == 3 * model.n_bond_halves


def test_an_aromatic_bond_is_one_tube_and_a_dashed_line():
    model = build_scene(benzene(with_hydrogen=False), ViewSettings())
    solid, dashed = scene_module.split_by_order(model)
    assert len(solid[0]) == model.n_bond_halves
    assert len(dashed[0]) == (scene_module.DASHES_PER_HALF
                              * model.n_bond_halves)


def test_turning_bond_orders_off_draws_one_tube_for_everything():
    settings = ViewSettings()
    settings.show_bond_orders = False
    model = build_scene(carbon_dioxide(), settings)
    assert len(model.bond_orders) == 0
    solid, dashed = scene_module.split_by_order(model)
    assert len(solid[0]) == model.n_bond_halves
    assert len(dashed[0]) == 0


def test_both_halves_of_a_bond_agree_about_its_order():
    """The halves stay adjacent, and the two tubes of a double bond
    have to meet at the midpoint rather than cross it."""
    model = build_scene(carbon_dioxide(), ViewSettings())
    assert np.all(model.bond_orders[0::2] == model.bond_orders[1::2])
    assert np.allclose(model.bond_offsets[0::2],
                       model.bond_offsets[1::2])


def test_the_offset_lies_in_the_molecular_plane():
    """The whole difficulty of drawing a double bond.  A perpendicular
    picked off the bond alone turns with the camera; the pi plane does
    not, and benzene's is the z = 0 plane."""
    structure = benzene(with_hydrogen=False)
    cell = p1.expand(structure)
    frames = _bond_frames(bonding.graph(structure), cell,
                          bonding.orders(structure))
    assert np.allclose(frames[:, 2], 0.0, atol=1e-9)
    assert np.allclose(np.linalg.norm(frames, axis=1), 1.0)


def test_the_aromatic_line_is_drawn_inside_the_ring():
    """Which side the inner line goes is not arbitrary: outside the
    ring it reads as a bond to something that is not there."""
    structure = benzene(with_hydrogen=False)
    cell = p1.expand(structure)
    graph = bonding.graph(structure)
    frames = _bond_frames(graph, cell, bonding.orders(structure))
    matrix = cell.lattice.matrix
    for bond, offset in zip(graph.bonds, frames, strict=True):
        midpoint = (cell.cart[bond.i] + cell.cart[bond.j]
                    + np.asarray(bond.image) @ matrix) / 2.0
        # The ring was built about the cartesian origin, so it wraps to
        # the corners of the box and the midpoint has to come back.
        midpoint -= np.round(cell.lattice.to_frac(midpoint)) @ matrix
        assert float(-midpoint @ offset) > 0


def test_a_bare_diatomic_is_laid_into_the_plane_of_the_screen():
    """An isolated O2 has no substituents and so no pi plane.  Left to
    a fixed perpendicular it comes out edge-on -- one fat tube -- for
    any camera that happens to look along it, so this is the one place
    the view direction is allowed in.
    """
    oxygen = isolated(["O", "O"], [[0, 0, 0], [0, 1.21, 0]])
    assert set(bonding.orders(oxygen)) == {2.0}
    cell = p1.expand(oxygen)
    graph = bonding.graph(oxygen)
    for view in ([0.0, 0.0, -1.0], [1.0, 0.0, 0.0]):
        frames = _bond_frames(graph, cell, bonding.orders(oxygen),
                              view)
        offset = frames[0]
        assert np.allclose(np.linalg.norm(offset), 1.0)
        assert abs(float(offset @ np.array(view))) < 1e-9
        assert abs(float(offset @ np.array([0.0, 1.0, 0.0]))) < 1e-9


def test_a_bare_diatomic_with_no_camera_still_gets_a_perpendicular():
    """And the same one every time, because a direction that moved
    between rebuilds would flicker."""
    oxygen = isolated(["O", "O"], [[0, 0, 0], [0, 1.21, 0]])
    cell, graph = p1.expand(oxygen), bonding.graph(oxygen)
    first = _bond_frames(graph, cell, bonding.orders(oxygen))
    second = _bond_frames(graph, cell, bonding.orders(oxygen))
    assert np.allclose(first, second)
    assert np.allclose(np.linalg.norm(first[0]), 1.0)
    assert abs(float(first[0] @ np.array([0.0, 1.0, 0.0]))) < 1e-9


def test_moving_the_atoms_does_not_change_the_orders():
    """Orders are perceived, not measured: a bond does not become
    double because two atoms drifted together.  That is also what makes
    the renderer's fast path legal -- it moves points under actors it
    is not allowed to rebuild, and a changed order would change how
    many tubes there are.
    """
    structure = butadiene()
    before = list(bonding.orders(structure))
    for site in structure.sites:
        site.frac = site.frac + 0.001
    structure.touch()
    assert list(bonding.orders(structure)) == before


def test_an_aromatic_ring_that_closes_through_a_cell_face_is_still_one():
    """Ring perception walks the periodic graph, so a linker whose ring
    is cut by the cell boundary is aromatic like any other."""
    a = 4.2
    ring = [[1.39 * math.cos(math.radians(60 * k)),
             1.39 * math.sin(math.radians(60 * k)), 0.0]
            for k in range(6)]
    lattice = Lattice.from_parameters(a, a, 12.0, 90, 90, 90)
    structure = Structure.from_arrays(
        lattice, ["C"] * 6, lattice.to_frac(np.array(ring)),
        space_group="P1")
    assert set(bonding.orders(structure)) == {1.5}


# ------------------------------------------------------ stating an order

def test_a_stated_order_beats_the_inference():
    """The point of Set Bond Type: the geometry says one thing and the
    chemist says another, and the chemist wins."""
    from xtal.commands import Host
    from xtal.commands.bonds import SetBondType

    molecule = butadiene()
    cell = p1.expand(molecule)
    inferred = bonding.orders(molecule)
    middle = [k for k, b in enumerate(bonding.graph(molecule).bonds)
              if inferred[k] == 1.0
              and cell.elements[b.i] == cell.elements[b.j] == "C"][0]
    bond = bonding.graph(molecule).bonds[middle]

    host = Host(molecule)
    SetBondType.between_atoms(molecule, cell, bond.i, bond.j, 2.0,
                              (0, 0, 0), bond.image).do(host)

    orders = bonding.orders(molecule)
    key = bonding.graph(molecule).bonds[middle].key()
    same = [k for k, b in enumerate(bonding.graph(molecule).bonds)
            if b.key() == key][0]
    assert orders[same] == 2.0


def test_a_bond_stated_single_stays_single():
    """The case a number alone cannot express.

    An explicit bond carries order 1.0 whether the user chose single or
    never said anything, so "single" has to be stated as well as
    written -- otherwise the inference goes on calling this bond double
    because both its ends look sp2.
    """
    from xtal.commands import Host
    from xtal.commands.bonds import SetBondType

    molecule = butadiene()
    cell = p1.expand(molecule)
    double = [k for k, b in enumerate(bonding.graph(molecule).bonds)
              if bonding.orders(molecule)[k] == 2.0][0]
    bond = bonding.graph(molecule).bonds[double]

    host = Host(molecule)
    command = SetBondType.between_atoms(molecule, cell, bond.i, bond.j,
                                        1.0, (0, 0, 0), bond.image)
    command.do(host)

    key = bond.key()
    orders = bonding.orders(molecule)
    same = [k for k, b in enumerate(bonding.graph(molecule).bonds)
            if b.key() == key][0]
    assert orders[same] == 1.0

    command.undo(host)
    orders = bonding.orders(molecule)
    same = [k for k, b in enumerate(bonding.graph(molecule).bonds)
            if b.key() == key][0]
    assert orders[same] == 2.0


def test_automatic_takes_the_statement_back():
    """The way out of a wrong answer that is not Ctrl+Z."""
    from xtal.commands import Host
    from xtal.commands.bonds import SetBondType

    molecule = butadiene()
    cell = p1.expand(molecule)
    bond = bonding.graph(molecule).bonds[0]
    host = Host(molecule)

    SetBondType.between_atoms(molecule, cell, bond.i, bond.j, 3.0,
                              (0, 0, 0), bond.image).do(host)
    assert any(b.stated for b in molecule.bonds)

    SetBondType.between_atoms(molecule, cell, bond.i, bond.j, None,
                              (0, 0, 0), bond.image).do(host)
    assert not molecule.bonds


def test_a_stated_order_survives_a_round_trip():
    """It is a statement about the crystal, so it belongs in the file
    and not only in the session."""
    from xtal.core.structure import Bond

    stated = Bond(0, 1, (0, 0, 0), 1.0, "explicit", 0, stated=True)
    assert Bond.from_dict(stated.to_dict()).stated
    assert not Bond.from_dict(Bond(0, 1).to_dict()).stated
    assert stated.reverse(Structure.empty().space_group).stated


# --------------------------------------------- many bonds in one edit

def a_framework():
    """MFU-4l: 648 atoms, 848 drawn bonds, 192 symmetry operations --
    the structure Select All was unusable on."""
    from xtal.io import read_cif
    return read_cif("resources/samples/MFU4l.cif")


def test_setting_every_bond_is_one_command_and_one_change():
    """The fix for the stall.  A command per bond is a touch per bond,
    and a touch drops the P1 expansion -- so eight hundred bonds
    re-expanded a 648-atom cell eight hundred times and redrew it
    eight hundred times on the way to a picture that only changes
    once."""
    from xtalapp.document import Document

    document = Document(a_framework())
    document.select_all()
    assert len(document.selection.bonds) == 848

    revision = document.structure.revision
    changes = []
    document.structureChanged.connect(changes.append)
    document.set_selected_bond_type(2.0)

    assert changes == [int(Change.TOPOLOGY)]        # one redraw
    assert document.structure.revision == revision + 1
    assert document.stack.depth == 1                # one Ctrl+Z


def test_deleting_every_bond_is_one_command_too():
    from xtalapp.document import Document

    document = Document(a_framework())
    document.select_all()
    changes = []
    document.structureChanged.connect(changes.append)
    document.delete_selected_bonds()

    assert len(changes) == 1
    assert document.stack.depth == 1
    assert not bonding.graph(document.structure).bonds


def test_a_bulk_edit_is_one_record_per_pair_not_per_drawn_bond():
    """848 drawn bonds are a handful of pairs of the asymmetric unit,
    and storing one record each is what keeps the file small and the
    undo cheap."""
    from xtalapp.document import Document

    document = Document(a_framework())
    document.select_all()
    document.set_selected_bond_type(1.0)

    assert len(document.structure.bonds) < 40
    assert all(b.stated for b in document.structure.bonds)
    assert set(bonding.orders(document.structure)) == {1.0}


def test_a_bulk_edit_undoes_in_one_step():
    from xtalapp.document import Document

    document = Document(a_framework())
    before = list(document.structure.bonds)
    document.select_all()
    document.set_selected_bond_type(3.0)
    assert set(bonding.orders(document.structure)) == {3.0}

    document.undo()

    assert document.structure.bonds == before
    assert set(bonding.orders(document.structure)) != {3.0}


def test_a_bulk_type_edit_leaves_a_suppression_alone():
    """A suppression says these two atoms are *not* bonded, which is a
    different statement from an order and must not be overwritten by
    one -- otherwise Select All then Set Bond Type puts back every bond
    the user had deleted."""
    from xtalapp.document import Document

    document = Document(a_framework())
    document.select_bond(bonding.graph(document.structure).bonds[0].key())
    document.delete_selected_bonds()
    gone = len(bonding.graph(document.structure).bonds)

    document.select_all()
    document.set_selected_bond_type(1.0)

    assert len(bonding.graph(document.structure).bonds) == gone
    assert any(b.kind == "suppressed" for b in document.structure.bonds)


def test_automatic_over_a_whole_selection_takes_every_statement_back():
    from xtalapp.document import Document

    document = Document(a_framework())
    document.select_all()
    document.set_selected_bond_type(2.0)
    assert document.structure.bonds

    document.set_selected_bond_type(None)

    assert not any(b.stated for b in document.structure.bonds)
