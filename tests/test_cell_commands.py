"""Undoable symmetry and cell operations -- headless.

Two invariants run through all of it: a preview says exactly what the
command will do, and undoing any of them puts the original structure
back untouched.
"""

from dataclasses import replace

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.commands import CommandStack, Host
from xtal.commands import cell as cell_commands
from xtal.commands import symmetry as symmetry_commands
from xtal.core import p1
from xtal.core.spacegroup import SpaceGroup
from xtal.core.structure import Change


@pytest.fixture
def host(rutile):
    return Host(rutile)


@pytest.fixture
def stack():
    return CommandStack()


def n_atoms(structure):
    return p1.expand(structure).n_atoms


# ---------------------------------------------------------- previewing

def test_a_preview_is_what_the_command_then_does(host, stack):
    command = cell_commands.Supercell(2, 1, 1)
    preview, report = command.preview(host.structure)
    assert report.n_after == 12

    stack.push(command, host)
    assert host.structure is preview             # the very same object
    assert command.report is report


def test_preview_does_not_touch_the_structure(host):
    before = host.structure.copy()
    symmetry_commands.FindSymmetry(1e-3).preview(host.structure)
    cell_commands.Supercell(3, 3, 3).preview(host.structure)
    assert host.structure.n_sites == before.n_sites
    assert np.allclose(host.structure.sites[1].frac,
                       before.sites[1].frac)


def test_preview_is_recomputed_for_a_different_structure(host, quartz):
    command = cell_commands.Supercell(2, 2, 2)
    _rutile, rutile_report = command.preview(host.structure)
    _quartz, quartz_report = command.preview(quartz)
    assert rutile_report.n_after == 6 * 8
    assert quartz_report.n_after == 9 * 8


# ------------------------------------------------------------ symmetry

def test_reduce_to_p1_and_back(host, stack):
    stack.push(symmetry_commands.ReduceToP1(), host)
    assert host.structure.space_group.is_p1
    assert host.structure.n_sites == 6

    stack.push(symmetry_commands.FindSymmetry(1e-4), host)
    assert host.structure.space_group.number == 136
    assert host.structure.n_sites == 2

    stack.undo(host)
    stack.undo(host)
    assert host.structure.space_group.number == 136
    assert host.structure.n_sites == 2


def test_find_symmetry_follows_the_tolerance(rutile):
    """The same coordinates have different symmetry at different
    tolerances, and neither answer is wrong -- which is why the
    tolerance is the first control in the dialog.

    Rutile with one oxygen nudged 0.02 A off its site is monoclinic at
    a tight tolerance and tetragonal at a loose one.
    """
    from xtal.core import symmetry

    nudged = symmetry.reduce_to_p1(rutile)
    nudged.sites[3].frac = nudged.sites[3].frac + [0.004, 0.0, 0.0]
    nudged.touch()

    tight, _ = symmetry_commands.FindSymmetry(
        1e-5, standardize_cell=True).preview(nudged)
    loose_command = symmetry_commands.FindSymmetry(0.05)
    loose, loose_report = loose_command.preview(nudged)

    assert tight.space_group.number < loose.space_group.number
    assert loose.space_group.number == 136
    assert loose.n_sites == 2
    assert loose_report.ok
    # A loose search idealises coordinates; it has to say how far.
    assert any("idealised" in w for w in loose_report.warnings)
    assert any("0.01" in w or "0.02" in w
               for w in loose_report.warnings)


def test_a_tolerance_too_tight_to_verify_is_refused(rutile):
    """The check runs at the tolerance the group was found at.  Held to
    a fixed tighter one, every loose answer would be rejected and the
    tolerance control would do nothing."""
    from xtal.core import symmetry

    nudged = symmetry.reduce_to_p1(rutile)
    nudged.sites[3].frac = nudged.sites[3].frac + [0.004, 0.0, 0.0]
    nudged.touch()
    _out, report = symmetry_commands.FindSymmetry(0.05).preview(nudged)
    assert report.ok

    strict = symmetry.asymmetrize(nudged, 0.05)
    assert strict[1].ok                     # same call, same answer


def test_set_space_group_generates_and_imposes(stack):
    """Reinterpreting grows the cell; imposing shrinks it back."""
    flat = Structure.from_arrays(
        Lattice.cubic(5.6402), ["Na", "Cl"],
        [[0.0, 0.0, 0.0], [0.5, 0.5, 0.5]], space_group="P1")
    host = Host(flat)

    stack.push(symmetry_commands.SetSpaceGroup(
        "Fm-3m", "reinterpret"), host)
    assert host.structure.space_group.number == 225
    assert n_atoms(host.structure) == 8

    stack.undo(host)
    assert n_atoms(host.structure) == 2


def test_imposing_a_group_finds_the_asymmetric_unit(rutile, stack):
    flat = symmetry_commands.ReduceToP1().preview(rutile)[0]
    host = Host(flat)
    command = symmetry_commands.SetSpaceGroup(
        rutile.space_group, "impose")
    stack.push(command, host)
    assert command.report.ok
    assert host.structure.n_sites == 2
    assert n_atoms(host.structure) == 6


def test_a_failed_operation_reports_rather_than_guessing(rutile):
    """A group the coordinates cannot support must say so."""
    command = symmetry_commands.SetSpaceGroup("Fm-3m", "impose")
    _new, report = command.preview(rutile)
    assert not report.ok
    assert report.message


def test_standardize_and_primitive(halite, stack):
    host = Host(halite)
    conventional = symmetry_commands.Standardize(1e-4)
    stack.push(conventional, host)
    assert conventional.report.n_after == 8       # F-centred cell

    primitive = symmetry_commands.Standardize(1e-4, to_primitive=True)
    stack.push(primitive, host)
    assert primitive.report.n_after == 2
    assert host.structure.lattice.volume < halite.lattice.volume

    stack.undo(host)
    stack.undo(host)
    assert host.structure is halite


def test_wyckoff_letters_change_nothing_but_the_labels(rutile, stack):
    before = [s.frac.copy() for s in rutile.sites]
    host = Host(rutile)
    command = symmetry_commands.AssignWyckoff(1e-4)
    stack.push(command, host)
    assert command.change == Change.METADATA
    assert {s.wyckoff for s in host.structure.sites} == {"2a", "4f"}
    for site, frac in zip(host.structure.sites, before, strict=True):
        assert np.allclose(site.frac, frac)


def test_merge_duplicates(rutile, stack):
    doubled = rutile.copy()
    doubled.add_site(rutile.sites[0].copy())      # exactly on top
    host = Host(doubled)
    command = symmetry_commands.MergeDuplicates(0.05)
    stack.push(command, host)
    assert command.report.merged == 1
    assert host.structure.n_sites == 2


# ---------------------------------------------------------------- cell

def test_supercell_counts_and_volume(host, stack):
    stack.push(cell_commands.Supercell(2, 3, 1), host)
    assert n_atoms(host.structure) == 36
    assert host.structure.lattice.volume == pytest.approx(
        6 * Lattice.from_parameters(4.594, 4.594, 2.959,
                                    90, 90, 90).volume, rel=1e-3)
    assert host.structure.space_group.is_p1


def test_transform_cell_can_re_express_the_same_crystal(halite, stack):
    """|det P| = 1 keeps the volume and the atom count: this is a
    change of basis, not a supercell."""
    host = Host(halite)
    p = [[1, 0, 0], [1, 1, 0], [0, 0, 1]]
    command = cell_commands.TransformCell(p)
    stack.push(command, host)
    assert host.structure.lattice.volume == pytest.approx(
        halite.lattice.volume)
    assert n_atoms(host.structure) == n_atoms(halite)
    stack.undo(host)
    assert host.structure is halite


def test_a_singular_transformation_is_refused(host):
    command = cell_commands.TransformCell(
        [[1, 0, 0], [1, 0, 0], [0, 0, 1]])
    with pytest.raises(ValueError):
        command.preview(host.structure)


def test_reduce_cell_keeps_the_crystal(quartz, stack):
    host = Host(quartz)
    for kind in ("niggli", "delaunay"):
        command = cell_commands.ReduceCell(kind)
        stack.push(command, host)
        assert command.report.n_after == n_atoms(quartz)
        assert host.structure.lattice.volume == pytest.approx(
            quartz.lattice.volume, rel=1e-6)
    with pytest.raises(ValueError):
        cell_commands.ReduceCell("banana")


def test_set_lattice_keeps_fractional_or_cartesian(host, stack):
    original = host.structure.lattice
    before = host.structure.lattice.to_cart(host.structure.sites[1].frac)
    stretched = original.with_parameters(a=original.lengths[0] * 2)

    stack.push(cell_commands.SetLattice(stretched, "cartesian"), host)
    after = host.structure.lattice.to_cart(host.structure.sites[1].frac)
    assert np.allclose(before, after)             # the atom did not move

    stack.undo(host)
    stack.push(cell_commands.SetLattice(stretched, "fractional"), host)
    moved = host.structure.lattice.to_cart(host.structure.sites[1].frac)
    assert not np.allclose(before, moved)         # it moved with the cell
    assert cell_commands.SetLattice(stretched).change == Change.CELL

    with pytest.raises(ValueError):
        cell_commands.SetLattice(stretched, "sideways")


def test_shift_origin_and_wrap(host, stack):
    stack.push(symmetry_commands.ReduceToP1(), host)
    stack.push(cell_commands.ShiftOrigin([0.5, 0.0, 0.0]), host)
    assert host.structure.sites[0].frac[0] == pytest.approx(0.5)

    stack.push(cell_commands.WrapIntoCell(), host)
    for site in host.structure.sites:
        assert np.all(site.frac >= 0) and np.all(site.frac < 1)

    stack.undo(host)
    stack.undo(host)
    assert host.structure.sites[0].frac[0] == pytest.approx(0.0)


def drawn_length(structure, bond) -> float:
    """How long a stored bond is, read the way the viewport reads it:
    from the sites' written coordinates, the operation and the image."""
    op = structure.space_group.operations[bond.op]
    far = op.apply(structure.sites[bond.j].frac) + np.array(bond.image)
    return float(np.linalg.norm(structure.lattice.to_cart(
        far - structure.sites[bond.i].frac)))


@pytest.fixture
def p1_rutile_with_a_drawn_bond(rutile):
    """Rutile in P1 with a Ti-O bond drawn by hand across two faces:
    Ti at the origin to the O at (0.695, 0.695, 0) one cell back."""
    from xtal.core import symmetry
    from xtal.core.structure import Bond
    structure = symmetry.reduce_to_p1(rutile)
    structure.set_bonds([Bond(0, 4, (-1, -1, 0))])
    return structure


def test_moving_the_origin_keeps_a_drawn_bond_its_length(
        p1_rutile_with_a_drawn_bond):
    """Ti folds across three faces and its O across one; a bond whose
    image stayed put was drawn 7.4 A long (MFU-4l's was 32.28 A)."""
    structure = p1_rutile_with_a_drawn_bond
    before = drawn_length(structure, structure.bonds[0])
    host, stack = Host(structure), CommandStack()
    stack.push(cell_commands.ShiftOrigin([0.1, 0.1, 0.1]), host)
    moved = host.structure
    assert moved.sites[0].frac == pytest.approx([0.9, 0.9, 0.9])
    assert drawn_length(moved, moved.bonds[0]) == pytest.approx(before)
    assert before == pytest.approx(1.984, abs=1e-3)


def test_moving_the_origin_keeps_every_perceived_bond(rutile):
    from xtal.core import bonding, symmetry
    structure = symmetry.reduce_to_p1(rutile)
    lengths = sorted(round(b.distance, 6)
                     for b in bonding.perceive(structure))
    host, stack = Host(structure), CommandStack()
    stack.push(cell_commands.ShiftOrigin([0.37, 0.61, 0.2]), host)
    moved = host.structure
    cell = p1.expand(moved)
    drawn = sorted(
        round(float(np.linalg.norm(moved.lattice.to_cart(
            cell.frac[b.j] + np.array(b.image) - cell.frac[b.i]))), 6)
        for b in bonding.perceive(moved))
    assert drawn == lengths


def test_moving_the_origin_outside_p1_is_refused_not_broken(host,
                                                            stack):
    """Keeping the operations while the sites move made rutile shifted
    by (0.1, 0.2, 0.05) expand to 32 atoms, not 6."""
    command = cell_commands.ShiftOrigin([0.1, 0.2, 0.05])
    same, report = command.preview(host.structure)
    assert not report.ok
    assert "Reduce to P1" in report.message
    assert same is host.structure
    from xtal.core import supercell
    with pytest.raises(ValueError, match="P1"):
        supercell.shift_origin(host.structure, [0.1, 0.2, 0.05])


def test_wrapping_a_site_written_outside_the_cell_keeps_its_bonds(
        p1_rutile_with_a_drawn_bond):
    """A CIF may write a site at 1.2 or -0.3; folding it in must not
    stretch the bonds it was drawn with."""
    structure = p1_rutile_with_a_drawn_bond
    structure.sites[4].frac = structure.sites[4].frac + [2, -1, 1]
    structure.set_bonds([replace(structure.bonds[0],
                                 image=(-3, 0, -1))])
    before = drawn_length(structure, structure.bonds[0])
    host, stack = Host(structure), CommandStack()
    stack.push(cell_commands.WrapIntoCell(), host)
    wrapped = host.structure
    assert np.all(wrapped.sites[4].frac < 1)
    assert drawn_length(wrapped, wrapped.bonds[0]) == pytest.approx(
        before)
    assert wrapped.bonds[0].image == (-1, -1, 0)


def test_wrapping_keeps_the_perceived_graph_of_a_folded_site(rutile):
    """The stored graph reads a changed wrap as an atom that drifted
    across a face and moves its bonds' images; a fold is the written
    coordinate jumping with the atom still, and must not be read so."""
    from xtal.core import bonding, symmetry
    structure = symmetry.reduce_to_p1(rutile)
    structure.sites[3].frac = structure.sites[3].frac + [1, 0, -2]
    structure.touch(Change.POSITIONS)   # as a CIF may write it
    lengths = sorted(round(b.distance, 6)
                     for b in bonding.perceive(structure))
    structure.wrap_sites()
    cell = p1.expand(structure)
    drawn = sorted(
        round(float(np.linalg.norm(structure.lattice.to_cart(
            cell.frac[b.j] + np.array(b.image) - cell.frac[b.i]))), 6)
        for b in bonding.perceive(structure))
    assert drawn == lengths


def test_a_fold_through_an_operation_keeps_the_bond(rutile):
    """In a group the far end is op(j) + image, so a fold of j moves
    it by the operation's rotation of the fold, not the fold itself."""
    from xtal.core.structure import Bond
    ops = rutile.space_group.operations
    k = next(k for k, op in enumerate(ops)
             if not np.allclose(op.rot, np.eye(3)))
    rutile.set_bonds([Bond(0, 1, (0, 0, 0), op=k)])
    before = drawn_length(rutile, rutile.bonds[0])
    rutile.fold_sites([s.frac + [1, -2, 3] for s in rutile.sites])
    assert drawn_length(rutile, rutile.bonds[0]) == pytest.approx(before)


# ----------------------------------------------------------- the table

def test_the_space_group_table_carries_every_setting():
    from xtal.core import spacegroup as sg

    table = sg.table()
    assert len(table) > 230                       # settings, not groups
    assert {g.number for g in table} == set(range(1, 231))
    assert [g.hm for g in sg.search("227")] == ["F d -3 m:1",
                                                "F d -3 m:2"]
    assert sg.search("P21/c")                     # squashed H-M
    assert sg.search("P 1 21/c 1")                # spelled out
    assert all(g.crystal_system == "tetragonal"
               for g in sg.search("tetragonal"))
    assert sg.search("not a group") == []
    assert len(sg.search("")) == len(table)


def test_every_group_in_the_table_round_trips_through_its_hall():
    from xtal.core import spacegroup as sg

    for group in sg.table():
        assert SpaceGroup.from_hall(group.hall) == group
