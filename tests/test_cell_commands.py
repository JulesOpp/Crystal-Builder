"""Undoable symmetry and cell operations -- headless.

Two invariants run through all of it: a preview says exactly what the
command will do, and undoing any of them puts the original structure
back untouched.
"""

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
    stack.push(cell_commands.ShiftOrigin([0.5, 0.0, 0.0]), host)
    assert host.structure.sites[0].frac[0] == pytest.approx(0.5)

    stack.push(cell_commands.WrapIntoCell(), host)
    for site in host.structure.sites:
        assert np.all(site.frac >= 0) and np.all(site.frac < 1)

    stack.undo(host)
    stack.undo(host)
    assert host.structure.sites[0].frac[0] == pytest.approx(0.0)


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
