"""Filling the empty space of a host with copies of a molecule."""

from pathlib import Path

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.build import fill
from xtal.commands import CommandStack, Host
from xtal.commands.clipboard import InsertMolecules
from xtal.core import bonding, p1
from xtal.core import elements as el
from xtal.io import FORMATS

SAMPLES = Path(__file__).resolve().parents[1] / "resources" / "samples"


@pytest.fixture
def mof5():
    return FORMATS.read(SAMPLES / "MOF-5.cif")


@pytest.fixture
def co2(dry_ice):
    return fill.guest_molecules(dry_ice)[0]


def _closest_contact(first, second, lattice, radii_a, radii_b,
                     exclude_self=False):
    """The smallest distance over contact, every periodic image of
    ``second`` against ``first``, brute force -- nothing of the code
    under test."""
    shifts = np.array([[a, b, c] for a in (-1, 0, 1)
                       for b in (-1, 0, 1) for c in (-1, 0, 1)])
    frac_b = lattice.to_frac(second)
    worst = np.inf
    for shift in shifts:
        if exclude_self and not shift.any():
            continue
        images = lattice.to_cart(frac_b + shift)
        gap = np.linalg.norm(first[:, None, :] - images[None, :, :],
                             axis=2)
        worst = min(worst, float((gap / (radii_a[:, None]
                                         + radii_b[None, :])).min()))
    return worst


def _radii(symbols):
    return np.array([el.vdw_radius(s) for s in symbols])


# ------------------------------------------------------------ guests

def test_the_guest_is_one_whole_molecule_per_formula(dry_ice, co2):
    """Dry ice is four CO2 across the corners of its cell, and what is
    offered is one CO2 -- in one piece, not with an oxygen a cell
    away."""
    assert len(fill.guest_molecules(dry_ice)) == 1
    assert co2.formula == "CO2"
    assert len(co2.bonds) == 2
    carbon = co2.elements.index("C")
    lengths = np.linalg.norm(co2.cart - co2.cart[carbon], axis=1)
    assert sorted(lengths)[1:] == pytest.approx([1.149, 1.149],
                                                abs=1e-2)


def test_a_framework_is_not_a_guest(mof5):
    assert fill.guest_molecules(mof5) == []


def test_a_marker_on_the_solvent_is_left_behind(dry_ice):
    """A centroid somebody placed on the molecule they drew is not
    part of the solvent."""
    flat = dry_ice.copy()
    from xtal.core.site import Site
    flat.add_sites([Site("X", [0.0, 0.0, 0.0])])
    guests = fill.guest_molecules(flat)
    assert [g.formula for g in guests] == ["CO2"]


# --------------------------------------------------------- placement

def test_no_guest_overlaps_the_framework_or_another_guest(mof5, co2):
    placement = fill.place(mof5, co2, 30, seed=3)
    assert placement.placed == 30
    scale = fill.DEFAULT_OVERLAP_SCALE
    cell = p1.expand(mof5)
    host = mof5.lattice.to_cart(cell.frac)
    host_r = _radii(cell.elements)
    guest_r = _radii(co2.elements)
    lattice = mof5.lattice
    for k, one in enumerate(placement.positions):
        assert _closest_contact(one, host, lattice, guest_r,
                                host_r) >= scale - 1e-9
        for other in placement.positions[k + 1:]:
            assert _closest_contact(one, other, lattice, guest_r,
                                    guest_r) >= scale - 1e-9


def test_a_guest_keeps_its_shape(mof5, co2):
    """Rotated and moved, never bent: the same distances between its
    atoms as the molecule it is a copy of."""
    def distances(cart):
        return np.linalg.norm(cart[:, None] - cart[None, :], axis=2)
    for one in fill.place(mof5, co2, 5, seed=1).positions:
        assert np.allclose(distances(one), distances(co2.cart))


def test_the_same_seed_places_the_same_molecules(mof5, co2):
    first = fill.place(mof5, co2, 6, seed=11).positions
    again = fill.place(mof5, co2, 6, seed=11).positions
    other = fill.place(mof5, co2, 6, seed=12).positions
    assert all(np.array_equal(a, b)
               for a, b in zip(first, again, strict=True))
    assert not np.allclose(first[0], other[0])


def test_a_full_host_places_what_fits_and_says_so(dry_ice, co2):
    """Dry ice has no room for another CO2 at all."""
    placement = fill.place(dry_ice, co2, 4, seed=0, max_attempts=50)
    assert placement.placed == 0
    assert "0 of 4" in placement.message()


def test_a_guest_does_not_meet_its_own_image_in_a_small_cell(co2):
    """A five-Angstrom box is shorter than CO2 and a contact, so an
    orientation along an axis runs into the copy next door -- which a
    27-cell test of the host alone would never see, there being no
    host."""
    box = Structure.empty(Lattice.cubic(4.2))
    placement = fill.place(box, co2, 1, seed=5)
    assert placement.placed == 1
    one = placement.positions[0]
    radii = _radii(co2.elements)
    assert _closest_contact(one, one, box.lattice, radii, radii,
                            exclude_self=True) >= \
        fill.DEFAULT_OVERLAP_SCALE - 1e-9


def test_capacity_is_an_upper_bound_on_what_is_placed(mof5, co2):
    room = fill.capacity(mof5, co2)
    assert room > 100                   # MOF-5 is mostly empty
    placed = fill.place(mof5, co2, room, seed=0, max_attempts=100)
    assert placed.placed < room


# ----------------------------------------------------------- command

def test_filling_adds_the_guests_bonds_and_no_others(mof5, co2):
    """Each CO2 comes with its two bonds, and nothing -- however close
    it sits -- is perceived between a guest and the framework."""
    host = Host(mof5)
    before = p1.expand(mof5).n_atoms
    bonds_before = len(bonding.graph(mof5).bonds)
    placement = fill.place(mof5, co2, 10, seed=2)
    CommandStack().push(InsertMolecules(co2, placement.positions), host)

    structure = host.structure
    graph = bonding.graph(structure)
    guest_atoms = set(range(before, p1.expand(structure).n_atoms))
    assert len(guest_atoms) == 30
    touching = [b for b in graph.bonds
                if (b.i in guest_atoms) != (b.j in guest_atoms)]
    assert touching == []
    inside = [b for b in graph.bonds
              if b.i in guest_atoms and b.j in guest_atoms]
    assert len(inside) == 20
    assert len(graph.bonds) == bonds_before + 20
    lengths = [b.distance for b in inside]
    assert max(lengths) < 1.3           # whole molecules, not torn


def test_one_undo_takes_every_guest_back(mof5, co2):
    host = Host(mof5)
    stack = CommandStack()
    before = mof5.copy()
    perceived = bonding.graph(mof5).bonds
    placement = fill.place(mof5, co2, 8, seed=4)
    stack.push(InsertMolecules(co2, placement.positions), host)
    assert host.structure.n_sites == before.n_sites + 24

    stack.undo(host)
    assert host.structure.n_sites == before.n_sites
    assert host.structure.bonds == before.bonds
    assert bonding.graph(host.structure).bonds == perceived


def test_a_host_with_symmetry_is_reduced_in_the_same_step(co2):
    """Each guest placed once, not multiplied by the group -- and one
    Ctrl+Z gives the symmetric host back."""
    sparse = Structure.from_arrays(Lattice.cubic(14.0), ["Na"],
                                   [[0.0, 0.0, 0.0]],
                                   space_group="Fm-3m")
    host = Host(sparse)
    stack = CommandStack()
    placement = fill.place(sparse, co2, 5, seed=1)
    assert placement.placed == 5
    command = InsertMolecules(co2, placement.positions)
    stack.push(command, host)

    assert host.structure.space_group.is_p1
    assert host.structure.n_sites == 4 + 15
    assert p1.expand(host.structure).n_atoms == 4 + 15

    stack.undo(host)
    assert host.structure.space_group.short_name == "Fm-3m"
    assert host.structure.n_sites == 1

    stack.redo(host)
    assert host.structure.n_sites == 4 + 15


def test_a_stated_bond_type_on_the_guest_stays_stated(dry_ice):
    """A bond the user called single in the molecule they drew is
    still their answer in the pore."""
    from xtal.commands.bonds import SetBondType
    from xtal.core.symmetry import reduce_to_p1
    flat = reduce_to_p1(dry_ice)
    cell = p1.expand(flat)
    bond = bonding.graph(flat).bonds[0]
    CommandStack().push(SetBondType.between_atoms(
        flat, cell, bond.i, bond.j, 1.0, image_b=bond.image),
        Host(flat))
    guest = fill.guest_molecules(flat)[0]
    assert len(guest.stated) == 1

    box = Structure.empty(Lattice.cubic(12.0))
    host = Host(box)
    placement = fill.place(box, guest, 1, seed=0)
    CommandStack().push(InsertMolecules(guest, placement.positions),
                        host)
    assert sorted(b.stated for b in host.structure.bonds) == \
        [False, True]
