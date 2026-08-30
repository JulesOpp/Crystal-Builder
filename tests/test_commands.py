"""The command stack and the commands themselves (headless)."""

import random

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.commands import CommandStack, Host, MacroCommand, SnapshotEdit
from xtal.commands import atoms as atom_commands
from xtal.commands import bonds as bond_commands
from xtal.commands import cell as cell_commands
from xtal.commands.base import ReplaceStructure
from xtal.core import p1
from xtal.core.structure import Bond, Change


@pytest.fixture
def host(rutile):
    return Host(rutile.copy())


@pytest.fixture
def stack():
    return CommandStack()


# ------------------------------------------------------------- stack

def test_push_runs_and_records(host, stack):
    stack.push(atom_commands.SetElement([0], "Zr"), host)
    assert host.structure.sites[0].element == "Zr"
    assert stack.can_undo and not stack.can_redo
    assert stack.undo_label == "Change element to Zr"


def test_undo_and_redo(host, stack):
    original = host.structure.copy()
    stack.push(atom_commands.SetElement([0], "Zr"), host)
    stack.undo(host)
    assert host.structure == original
    assert stack.can_redo and not stack.can_undo
    stack.redo(host)
    assert host.structure.sites[0].element == "Zr"


def test_a_new_command_discards_the_redo_branch(host, stack):
    stack.push(atom_commands.SetElement([0], "Zr"), host)
    stack.undo(host)
    assert stack.can_redo
    stack.push(atom_commands.SetElement([0], "Hf"), host)
    assert not stack.can_redo
    assert host.structure.sites[0].element == "Hf"


def test_undo_on_an_empty_stack_is_harmless(host, stack):
    assert stack.undo(host) is None
    assert stack.redo(host) is None


def test_history_is_bounded(host):
    stack = CommandStack(limit=5)
    for i in range(20):
        stack.push(atom_commands.AddSites([atom_commands.new_site(
            "He", [0.01 * i, 0.0, 0.0])]), host)
    assert stack.depth == 5
    assert host.structure.n_sites == 22      # the edits all happened


def test_transactions_group_into_one_step(host, stack):
    original = host.structure.copy()
    with stack.transaction("Build", host):
        stack.push(atom_commands.SetElement([0], "Zr"), host)
        stack.push(atom_commands.AddSites(
            [atom_commands.new_site("F", [0.1, 0.1, 0.1])]), host)
    assert stack.depth == 1
    assert stack.undo_label == "Build"
    stack.undo(host)
    assert host.structure == original


def test_an_empty_transaction_records_nothing(host, stack):
    with stack.transaction("Nothing", host):
        pass
    assert stack.depth == 0


def test_a_failed_transaction_rolls_back(host, stack):
    original = host.structure.copy()
    with pytest.raises(RuntimeError):
        with stack.transaction("Broken", host):
            stack.push(atom_commands.SetElement([0], "Zr"), host)
            raise RuntimeError("boom")
    assert host.structure == original
    assert stack.depth == 0


def test_clean_tracking_follows_undo(host, stack):
    assert stack.is_clean
    stack.push(atom_commands.SetElement([0], "Zr"), host)
    assert not stack.is_clean
    stack.mark_clean()                      # as if saved
    assert stack.is_clean
    stack.push(atom_commands.SetElement([0], "Hf"), host)
    assert not stack.is_clean
    stack.undo(host)
    assert stack.is_clean                   # back at the saved point


def test_macro_change_hint_is_the_union():
    macro = MacroCommand("Mixed", [
        atom_commands.SetElement([0], "Zr"),
        atom_commands.MoveSites({0: [0.1, 0, 0]}),
    ])
    assert macro.change & Change.TOPOLOGY
    assert macro.change & Change.POSITIONS
    assert len(macro) == 2


# ---------------------------------------------------------- commands

def test_add_sites_labels_only_the_new_atom(host, stack):
    """Adding an atom must not relabel the atoms already there, or
    undoing the addition would leave the structure changed."""
    host.structure.sites[0].label = ""
    before = host.structure.copy()
    stack.push(atom_commands.AddSites(
        [atom_commands.new_site("F", [0.1, 0.2, 0.3])]), host)
    assert host.structure.sites[-1].label == "F1"
    assert host.structure.sites[0].label == ""
    stack.undo(host)
    assert host.structure == before


def test_delete_sites_restores_bonds_too(host, stack):
    host.structure.add_bond(Bond(0, 1))
    before = host.structure.copy()
    stack.push(atom_commands.DeleteSites([0]), host)
    assert host.structure.n_sites == 1
    assert host.structure.bonds == []
    stack.undo(host)
    assert host.structure == before
    assert len(host.structure.bonds) == 1


def test_move_sites_by_delta_and_cartesian(host, stack):
    start = host.structure.sites[1].frac.copy()
    stack.push(atom_commands.MoveSites.by_delta(
        host.structure, [1], [0.1, 0, 0]), host)
    assert host.structure.sites[1].frac[0] == pytest.approx(
        start[0] + 0.1)

    stack.push(atom_commands.MoveSites.by_cartesian_delta(
        host.structure, [1], [4.594, 0, 0]), host)   # exactly one a
    assert host.structure.sites[1].frac[0] == pytest.approx(
        start[0] + 1.1)


def test_consecutive_moves_merge_into_one_undo_step(host, stack):
    start = host.structure.sites[0].frac.copy()
    for _ in range(5):
        stack.push(atom_commands.MoveSites.by_delta(
            host.structure, [0], [0.01, 0, 0]), host)
    assert stack.depth == 1                 # one drag, one undo
    assert host.structure.sites[0].frac[0] == pytest.approx(
        start[0] + 0.05)
    stack.undo(host)
    assert host.structure.sites[0].frac[0] == pytest.approx(start[0])


def test_moves_of_different_atoms_do_not_merge(host, stack):
    stack.push(atom_commands.MoveSites.by_delta(
        host.structure, [0], [0.01, 0, 0]), host)
    stack.push(atom_commands.MoveSites.by_delta(
        host.structure, [1], [0.01, 0, 0]), host)
    assert stack.depth == 2


def test_property_edits_merge_per_field(host, stack):
    stack.push(atom_commands.SetSiteProperties(0, occupancy=0.9), host)
    stack.push(atom_commands.SetSiteProperties(0, occupancy=0.8), host)
    assert stack.depth == 1
    stack.push(atom_commands.SetSiteProperties(0, label="Ti9"), host)
    assert stack.depth == 2
    stack.undo(host)
    assert host.structure.sites[0].label == ""
    stack.undo(host)
    assert host.structure.sites[0].occupancy == 1.0


def test_rotation_is_rigid_in_cartesian_space(quartz):
    """A 90 degree rotation about c in a hexagonal cell: distances
    inside the fragment must not change, which they would if the
    arithmetic were done on fractional coordinates."""
    host = Host(quartz.copy())
    stack = CommandStack()
    lattice = host.structure.lattice
    before = np.array([lattice.to_cart(s.frac)
                       for s in host.structure.sites])
    span_before = np.linalg.norm(before[0] - before[1])

    stack.push(atom_commands.TransformSites.rotation(
        [0, 1], lattice.matrix[2], 90.0), host)
    after = np.array([lattice.to_cart(s.frac)
                      for s in host.structure.sites])
    assert np.linalg.norm(after[0] - after[1]) == pytest.approx(
        span_before)
    assert not np.allclose(after, before)

    stack.undo(host)
    restored = np.array([lattice.to_cart(s.frac)
                         for s in host.structure.sites])
    assert np.allclose(restored, before)


def test_rotation_by_360_returns_home(host, stack):
    before = [s.frac.copy() for s in host.structure.sites]
    stack.push(atom_commands.TransformSites.rotation(
        [0, 1], [0, 0, 1], 360.0), host)
    for site, start in zip(host.structure.sites, before, strict=True):
        assert np.allclose(site.frac, start, atol=1e-9)


def test_mirror_twice_is_the_identity(host, stack):
    before = [s.frac.copy() for s in host.structure.sites]
    for _ in range(2):
        stack.push(atom_commands.TransformSites.mirror(
            [0, 1], [1, 0, 0]), host)
    for site, start in zip(host.structure.sites, before, strict=True):
        assert np.allclose(site.frac, start, atol=1e-9)


def test_bad_transform_arguments(host):
    with pytest.raises(ValueError):
        atom_commands.TransformSites.rotation([0], [0, 0, 0], 90)
    with pytest.raises(ValueError):
        atom_commands.TransformSites.mirror([0], [0, 0, 0])


def test_add_and_remove_bond(host, stack):
    stack.push(bond_commands.AddBond(Bond(0, 1)), host)
    assert len(host.structure.bonds) == 1
    stack.undo(host)
    assert host.structure.bonds == []
    stack.redo(host)
    stack.push(bond_commands.RemoveBond(Bond(0, 1)), host)
    assert host.structure.bonds == []
    stack.undo(host)
    assert len(host.structure.bonds) == 1


def test_bond_between_picked_atoms(host, stack):
    """Drawing a bond on one pair draws it on every equivalent pair."""
    from xtal.core import bonding
    cell = p1.expand(host.structure)
    rules = bonding.BondRules(forbidden={("Ti", "O")})
    assert bonding.perceive(host.structure, rules) == []

    stack.push(bond_commands.AddBond.between_atoms(
        host.structure, cell, 0, 2), host)
    made = bonding.perceive(host.structure, rules)
    assert len(made) == 4                   # the whole orbit of the pair
    assert all(b.explicit for b in made)


def test_suppressing_a_perceived_bond(host, stack):
    from xtal.core import bonding
    cell = p1.expand(host.structure)
    before = len(bonding.perceive(host.structure))
    stack.push(bond_commands.SuppressBond.between_atoms(
        host.structure, cell, 0, 2), host)
    assert len(bonding.perceive(host.structure)) == before - 4
    stack.undo(host)
    assert len(bonding.perceive(host.structure)) == before


def test_set_lattice_keeping_fractional_or_cartesian(host, stack):
    lattice = Lattice.cubic(6.0)
    frac_before = host.structure.sites[1].frac.copy()
    cart_before = host.structure.lattice.to_cart(frac_before)

    stack.push(cell_commands.SetLattice(lattice, "fractional"), host)
    assert np.allclose(host.structure.sites[1].frac, frac_before)
    stack.undo(host)

    stack.push(cell_commands.SetLattice(lattice, "cartesian"), host)
    assert np.allclose(
        host.structure.lattice.to_cart(host.structure.sites[1].frac),
        cart_before)
    stack.undo(host)
    assert np.allclose(host.structure.sites[1].frac, frac_before)


def test_set_lattice_rejects_a_nonsense_mode():
    with pytest.raises(ValueError):
        cell_commands.SetLattice(Lattice.cubic(5.0), keep="vibes")


def test_replace_structure(host, stack):
    before = host.structure.copy()
    replacement = Structure.from_arrays(Lattice.cubic(3.0), ["Cu"],
                                        [[0, 0, 0]])
    stack.push(ReplaceStructure(replacement, "Swap"), host)
    assert host.structure.n_sites == 1
    stack.undo(host)
    assert host.structure == before


def test_snapshot_edit_is_the_escape_hatch(host, stack):
    before = host.structure.copy()
    stack.push(SnapshotEdit(lambda s: s.wrap_sites(), "Wrap",
                            Change.POSITIONS), host)
    stack.undo(host)
    assert host.structure == before
    stack.redo(host)
    assert host.structure.n_sites == before.n_sites


# ------------------------------------------- the round-trip invariant

def random_command(structure, rng):
    """One valid command for whatever the structure currently is."""
    n = structure.n_sites
    choices = ["add", "element", "move", "property", "rotate"]
    if n > 1:
        choices += ["delete", "bond"]
    kind = rng.choice(choices)
    index = rng.randrange(n) if n else 0

    if kind == "add":
        return atom_commands.AddSites([atom_commands.new_site(
            rng.choice(["C", "N", "Fe"]),
            [rng.random(), rng.random(), rng.random()])])
    if kind == "delete":
        return atom_commands.DeleteSites([index])
    if kind == "element":
        return atom_commands.SetElement([index],
                                        rng.choice(["S", "Se", "Zr"]))
    if kind == "move":
        return atom_commands.MoveSites.by_delta(
            structure, [index], [rng.random() * 0.1, 0.0, 0.0])
    if kind == "property":
        return atom_commands.SetSiteProperties(
            index, occupancy=round(rng.uniform(0.2, 1.0), 3))
    if kind == "rotate":
        return atom_commands.TransformSites.rotation(
            [index], [0, 0, 1], rng.uniform(-180, 180))
    other = (index + 1) % n
    return bond_commands.AddBond(Bond(min(index, other),
                                      max(index, other)))


@pytest.mark.parametrize("seed", range(8))
def test_undoing_everything_restores_the_original(seed, quartz):
    """The invariant the whole editor rests on: whatever sequence of
    edits you make, undoing them all gets the crystal you started
    with -- and redoing them all gets back to where you were."""
    rng = random.Random(seed)
    host = Host(quartz.copy())
    stack = CommandStack()
    original = host.structure.copy()

    for _ in range(25):
        stack.push(random_command(host.structure, rng), host)
    edited = host.structure.copy()

    while stack.can_undo:
        stack.undo(host)
    assert host.structure.almost_equal(original, tol=1e-9)

    while stack.can_redo:
        stack.redo(host)
    assert host.structure.almost_equal(edited, tol=1e-9)
