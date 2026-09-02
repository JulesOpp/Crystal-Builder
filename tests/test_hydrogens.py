"""Putting the hydrogens back.

The tests are geometric, because that is what the answer is: an added
hydrogen is right if it is the right distance away, at the right angle
to what is already there, and in the right *number* -- and the number
is an orbit count, not a site count, which is the part a symmetric
structure gets wrong if nothing is watching.

Two rules run through all of them.  A plan changes nothing (it is
computed while a dialog is open, over and over); and an atom nobody
should guess at is left alone *and said out loud*, because a silent
omission is indistinguishable from a bug.
"""

import math

import numpy as np
import pytest

from tests.conftest_ff import (
    benzene,
    butadiene,
    isolated,
    methane,
    salt,
    water,
)
from xtal import Lattice, Structure
from xtal.commands.base import CommandStack, Host
from xtal.commands.bonds import SetBondType
from xtal.commands.ff import AddHydrogens
from xtal.core import bonding, p1
from xtal.core.site import Site
from xtal.core.structure import Bond
from xtal.ff import hydrogens
from xtal.ff.uff import typer


def cart(structure):
    return structure.lattice.to_cart(
        np.array([s.frac for s in structure.sites]))


def angle(a, b, c) -> float:
    u, v = np.asarray(a) - b, np.asarray(c) - b
    return math.degrees(math.acos(
        float(u @ v) / np.linalg.norm(u) / np.linalg.norm(v)))


def dihedral(p0, p1, p2, p3) -> float:
    b0, b1, b2 = np.asarray(p0) - p1, np.asarray(p2) - p1, \
        np.asarray(p3) - p2
    axis = b1 / np.linalg.norm(b1)
    v = b0 - (b0 @ axis) * axis
    w = b2 - (b2 @ axis) * axis
    return abs(math.degrees(math.atan2(
        float(np.cross(axis, v) @ w), float(v @ w))))


def added(structure, **kwargs):
    """``(plan, cartesian positions of the new hydrogens)``."""
    plan = hydrogens.plan(structure, **kwargs)
    lattice = structure.lattice
    return plan, np.array([lattice.to_cart(s.frac)
                           for s in plan.sites])


def skeleton(*symbols_and_positions) -> Structure:
    symbols = [s for s, _p in symbols_and_positions]
    positions = [p for _s, p in symbols_and_positions]
    return isolated(symbols, positions)


# ------------------------------------------------------ where they go

def test_a_benzene_ring_gets_one_flat_hydrogen_per_carbon():
    """The case the whole feature is for: an aromatic ring refined
    from X-ray data, where every carbon is one neighbour short."""
    ring = benzene(with_hydrogen=False)
    plan, positions = added(ring)

    assert len(plan.sites) == 6
    assert plan.n_atoms == 6
    carbons = cart(ring)
    for k, h in enumerate(positions):
        assert np.linalg.norm(h - carbons[k]) == pytest.approx(
            1.0814, abs=2e-3)                       # UFF's C_R-H_
        assert h[2] == pytest.approx(0.0, abs=1e-9)     # in the plane
        assert angle(carbons[(k + 1) % 6], carbons[k], h) == \
            pytest.approx(120.0, abs=0.5)


def test_a_methyl_group_comes_out_tetrahedral_and_staggered():
    """A terminal group's torsion is undetermined, so the convention
    has to be the one a chemist would draw."""
    ethane = skeleton(("C", [0.0, 0.0, 0.0]), ("C", [0.0, 0.0, 1.526]))
    plan, positions = added(ethane)

    assert len(plan.sites) == 6
    carbons = cart(ethane)
    for h in positions[:3]:
        assert np.linalg.norm(h - carbons[0]) == pytest.approx(
            1.1094, abs=2e-3)                       # UFF's C_3-H_
        assert angle(h, carbons[0], carbons[1]) == pytest.approx(
            109.47, abs=0.1)
    angles = [dihedral(a, carbons[0], carbons[1], b)
              for a in positions[:3] for b in positions[3:]]
    assert sorted(round(a) for a in angles) == [60] * 6 + [180] * 3


def test_a_hydroxyl_is_bent_and_not_linear():
    """The angle comes from the *type*, not from the coordination
    number: sp3 oxygen has four directions and two of them are lone
    pairs the model never draws."""
    methanol = skeleton(("O", [0.0, 0.0, 0.0]), ("C", [1.43, 0.0, 0.0]))
    plan, positions = added(methanol)

    oxygen, carbon = cart(methanol)
    hydroxyl = [h for h in positions
                if np.linalg.norm(h - oxygen) < 1.2]
    assert len(hydroxyl) == 1
    assert np.linalg.norm(hydroxyl[0] - oxygen) == pytest.approx(
        0.9903, abs=2e-3)                           # UFF's O_3-H_
    assert angle(carbon, oxygen, hydroxyl[0]) == pytest.approx(
        104.51, abs=0.1)                            # O_3's own theta0


def test_a_carbon_skeleton_keeps_its_double_bonds_single_hydrogened():
    """Butadiene: the terminal carbons take two hydrogens and the
    inner ones take one, which is the bond orders being read and not
    the coordination numbers."""
    plan, _positions = added(butadiene())
    assert plan.n_atoms == 6
    assert plan.n_parents == 4


def test_the_hydrogens_arrive_where_the_force_field_wants_them():
    """The point of taking the length from UFF rather than from a
    table of standard distances: the hydrogen is already at the
    minimum of the potential it is about to be relaxed in, so a
    relaxation barely moves it."""
    from xtal.ff import ENGINES, optimize

    host = Host(benzene(with_hydrogen=False))
    CommandStack().push(AddHydrogens(), host)
    filled = host.structure
    before = cart(filled)[6:]

    result = optimize.run(ENGINES.build("uff", filled), filled,
                          max_steps=20)
    after = filled.lattice.to_cart(result.frac)[6:]
    assert np.abs(after - before).max() < 0.05


def test_the_x_ray_option_shortens_every_bond_and_is_not_the_default():
    """Neutron and X-ray hydrogen positions differ by 0.1 A for a real
    reason; offer the short one, do not default to it."""
    ring = benzene(with_hydrogen=False)
    carbons = cart(ring)
    _plan, neutron = added(ring)
    _plan, xray = added(ring, xray=True)

    long_ = np.linalg.norm(neutron[0] - carbons[0])
    short = np.linalg.norm(xray[0] - carbons[0])
    assert long_ - short == pytest.approx(hydrogens.X_RAY_SHORTENING,
                                          abs=1e-6)


# --------------------------------------------------- what is left out

def test_a_structure_that_already_has_its_hydrogens_gets_none():
    for structure in (water(), methane(), benzene()):
        plan = hydrogens.plan(structure)
        assert not plan
        assert plan.message() == "no hydrogens to add"


def test_running_it_twice_adds_nothing_the_second_time():
    host = Host(benzene(with_hydrogen=False))
    stack = CommandStack()
    stack.push(AddHydrogens(), host)
    assert not AddHydrogens().preview(host.structure)


def test_no_hydrogen_is_guessed_onto_a_metal():
    plan = hydrogens.plan(salt())
    assert not plan.sites
    assert any("metal" in s for s in plan.skipped)


def test_an_element_with_no_tabulated_valence_is_reported():
    """Left alone *and reported*: a silent omission cannot be told
    apart from a bug."""
    selenophene = skeleton(("Se", [0.0, 0.0, 0.0]),
                           ("C", [1.86, 0.0, 0.0]))
    plan = hydrogens.plan(selenophene)
    assert any("Se" in s and "valence" in s for s in plan.skipped)


def test_an_atom_with_no_neighbours_is_left_alone_and_said_so():
    """A bare oxygen in a cell is as likely to be an ion as a water
    molecule, and there is no coordination to complete either way."""
    lonely = isolated(["O"], [[0.0, 0.0, 0.0]])
    plan = hydrogens.plan(lonely)
    assert not plan.sites
    assert any("no neighbours" in s for s in plan.skipped)


def test_the_assumption_behind_a_free_rotation_is_written_down():
    ethane = skeleton(("C", [0.0, 0.0, 0.0]), ("C", [0.0, 0.0, 1.526]))
    plan = hydrogens.plan(ethane)
    assert any("undetermined" in note for note in plan.notes)
    assert "undetermined" in plan.report()


def test_a_plan_changes_nothing():
    """It is recomputed every time a checkbox moves in the dialog."""
    ring = benzene(with_hydrogen=False)
    before = np.array([s.frac for s in ring.sites])
    hydrogens.plan(ring)
    hydrogens.plan(ring, xray=True)
    assert ring.n_sites == 6
    assert np.allclose([s.frac for s in ring.sites], before)


# ------------------------------------------------------------ symmetry

def mirrored_methylene() -> Structure:
    """Two carbons on the mirror plane of P m, so each one's three
    hydrogens are two sites: one on the plane, one off it with a
    multiplicity of two."""
    lattice = Lattice.cubic(20.0)
    return Structure(
        lattice=lattice,
        sites=[Site("C", [0.5, 0.0, 0.5]),
               Site("C", [0.5 + 1.53 / 20, 0.0, 0.5])],
        space_group="Pm")


def test_the_count_reported_is_the_orbit_count():
    """One hydrogen added to a site of multiplicity two is two
    hydrogens, and saying "2 sites" would be a lie about what the
    button does."""
    plan = hydrogens.plan(mirrored_methylene())
    assert len(plan.sites) == 4          # in the asymmetric unit
    assert plan.n_atoms == 6             # in the cell
    assert "6 hydrogens" in plan.message()
    assert sorted(plan.multiplicity) == [1, 1, 2, 2]


def test_a_hydrogen_on_a_special_position_is_not_generated_twice():
    """Two hydrogens either side of a mirror plane are one site.
    Adding both would put two atoms on top of each other -- the
    failure that makes a structure look right and count wrong."""
    from xtal.core import p1

    host = Host(mirrored_methylene())
    CommandStack().push(AddHydrogens(), host)
    cell = p1.expand(host.structure)
    assert cell.n_atoms == 8             # 2 carbons + 6 hydrogens
    positions = cell.lattice.to_cart(cell.frac)
    gaps = np.linalg.norm(positions[:, None] - positions[None, :],
                          axis=-1)
    np.fill_diagonal(gaps, np.inf)
    assert gaps.min() > 0.5              # nothing landed on anything


# ------------------------------------------------------- the command

def test_adding_hydrogens_is_one_undoable_step():
    host = Host(benzene(with_hydrogen=False))
    stack = CommandStack()
    command = AddHydrogens()
    assert command.preview(host.structure).n_atoms == 6

    stack.push(command, host)
    assert host.structure.n_sites == 12
    assert stack.depth == 1

    stack.undo(host)
    assert host.structure.n_sites == 6
    stack.redo(host)
    assert host.structure.n_sites == 12


def test_every_added_hydrogen_gets_its_own_label():
    """Twelve atoms added at once must not all be called H1."""
    host = Host(benzene(with_hydrogen=False))
    CommandStack().push(AddHydrogens(), host)
    labels = [s.label for s in host.structure.sites if s.element == "H"]
    assert len(set(labels)) == len(labels) == 6


# ------------------------------------- the user overruling the geometry

def state_every_bond(structure, order) -> None:
    """What Set Bond Type does to every bond of a structure."""
    cell = p1.expand(structure)
    host = Host(structure)
    for bond in list(bonding.graph(structure).bonds):
        SetBondType.between_atoms(structure, cell, bond.i, bond.j,
                                  order, (0, 0, 0), bond.image).do(host)


def state_one_bond(structure, order, which: int = 0):
    """The same, on a single bond.  Returns the bond it acted on."""
    bond = bonding.graph(structure).bonds[which]
    SetBondType.between_atoms(structure, p1.expand(structure), bond.i,
                              bond.j, order, (0, 0, 0),
                              bond.image).do(Host(structure))
    return bond


def bent_carbon(angle_degrees: float) -> Structure:
    """One carbon at the origin with two carbon neighbours, at a
    chosen angle.  The angle is the point: the typer reads it, and a
    stated order has to beat it."""
    half = math.radians(angle_degrees / 2)
    return skeleton(
        ("C", [0.0, 0.0, 0.0]),
        ("C", [1.5 * math.sin(half), 1.5 * math.cos(half), 0.0]),
        ("C", [-1.5 * math.sin(half), 1.5 * math.cos(half), 0.0]))


def on_the_middle(structure) -> int:
    """How many of the planned hydrogens land on the atom at the
    origin."""
    _plan, positions = added(structure)
    centre = cart(structure)[0]
    return sum(1 for h in positions
               if np.linalg.norm(h - centre) < 1.2)


@pytest.mark.parametrize("drawn_angle", [109.5, 120.0, 180.0])
def test_two_stated_single_bonds_want_two_hydrogens(drawn_angle):
    """A carbon with two bonds the user has called single is sp3, and
    an sp3 carbon with two neighbours is two hydrogens short --
    whatever angle the model happens to have them drawn at.

    Before this, the geometry decided the hybridisation on its own: the
    same carbon drawn at 120 degrees was typed sp2 and got one
    hydrogen, and drawn linear was typed sp and got none.  The valence
    was never the part that was wrong.
    """
    structure = bent_carbon(drawn_angle)
    state_every_bond(structure, 1.0)
    assert on_the_middle(structure) == 2


def test_a_stated_double_bond_leaves_room_for_one():
    """The other half of the same rule: one double and one single is
    sp2 -- three directions, two of them taken, one hydrogen."""
    structure = bent_carbon(120.0)
    state_every_bond(structure, 1.0)
    state_one_bond(structure, 2.0)
    assert on_the_middle(structure) == 1


def test_two_stated_double_bonds_leave_no_room_at_all():
    """Two doubles is sp, which has two directions and both are
    spoken for -- and the valence agrees: 2 + 2 is 4."""
    structure = bent_carbon(120.0)
    state_every_bond(structure, 2.0)
    assert on_the_middle(structure) == 0


def test_calling_a_ring_single_makes_it_cyclohexane():
    """Benzene's carbons take one hydrogen each.  The same ring with
    every bond called single is sp3 and takes two -- the difference
    between the molecule the geometry suggests and the one the user
    says they have."""
    assert added(benzene(with_hydrogen=False))[0].n_atoms == 6

    saturated = benzene(with_hydrogen=False)
    state_every_bond(saturated, 1.0)
    assert added(saturated)[0].n_atoms == 12


def test_calling_a_ring_aromatic_keeps_it_aromatic():
    """Two stated aromatic bonds sum to exactly one pi bond, which is
    also what one plain double bond sums to -- so resonance has to be
    read from the orders themselves and not from the total."""
    ring = benzene(with_hydrogen=False)
    state_every_bond(ring, 1.5)
    assert typer.assign(ring).types[0].name == "C_R"
    assert added(ring)[0].n_atoms == 6


def test_an_unstated_bond_leaves_the_geometry_in_charge():
    """One statement among several says nothing about the total, so it
    must not retype the atom: a single click would otherwise turn a
    benzene into a cyclohexane."""
    ring = benzene(with_hydrogen=False)
    bond = state_one_bond(ring, 1.0)

    assert typer.assign(ring).types[bond.i].name == "C_R"
    assert added(ring)[0].n_atoms == 6


def test_a_stated_order_that_contradicts_the_coordination_is_ignored():
    """Four neighbours and a stated double bond describes no carbon.
    The angles are better evidence than an order that cannot be
    right."""
    neopentane_core = skeleton(
        ("C", [0.0, 0.0, 0.0]), ("C", [0.89, 0.89, 0.89]),
        ("C", [0.89, -0.89, -0.89]), ("C", [-0.89, 0.89, -0.89]),
        ("C", [-0.89, -0.89, 0.89]))
    state_every_bond(neopentane_core, 2.0)
    assert typer.assign(neopentane_core).types[0].name == "C_3"


# ------------------------------------------------------- dummy atoms

def with_a_marker(structure, frac=(0.9, 0.9, 0.9)) -> Structure:
    """The structure with a dummy atom dropped into a corner of the
    cell, well away from everything."""
    structure.sites.append(Site("X", list(frac)))
    structure.touch()
    return structure


def test_a_dummy_atom_does_not_stop_the_hydrogens_going_back():
    """Add centroid puts an X in by an ordinary gesture, and the force
    field this reads refuses one by name -- so before the marker was
    held back at the door, one centroid anywhere in the cell made Add
    hydrogens fail outright on the whole structure."""
    plain = hydrogens.plan(benzene(with_hydrogen=False))
    marked = hydrogens.plan(with_a_marker(benzene(with_hydrogen=False)))
    assert marked.n_atoms == plain.n_atoms == 6
    assert marked.message() == plain.message()


def test_no_hydrogen_is_offered_to_a_dummy_atom():
    """A marker is a position and not an atom: it has no valence to
    complete, and nothing may be hung off it."""
    marked = with_a_marker(benzene(with_hydrogen=False))
    host = Host(marked)
    CommandStack().push(AddHydrogens(), host)
    for site in host.structure.sites:
        if site.element != "H":
            continue
        marker = host.structure.lattice.to_cart([0.9, 0.9, 0.9])
        near = host.structure.lattice.to_cart(site.frac)
        assert np.linalg.norm(near - marker) > 2.0


def test_the_marker_is_still_there_afterwards():
    """Held back from the reasoning, not deleted from the crystal."""
    host = Host(with_a_marker(benzene(with_hydrogen=False)))
    CommandStack().push(AddHydrogens(), host)
    assert [s.element for s in host.structure.sites].count("X") == 1


def test_a_bond_drawn_to_a_marker_spends_no_valence():
    """A user-drawn bond from a carbon to a centroid would otherwise
    look like a fourth neighbour, and that carbon would go without the
    hydrogen it is actually missing."""
    marked = with_a_marker(benzene(with_hydrogen=False),
                           frac=(0.5, 0.5, 0.5))
    marked.bonds.append(Bond(0, 6, (0, 0, 0)))
    marked.touch()
    assert hydrogens.plan(marked).n_atoms == 6
