"""Copy and paste as fragments."""

import numpy as np
import pytest

from xtal.commands import CommandStack, Host
from xtal.commands.clipboard import Fragment, PasteFragment
from xtal.core import bonding, p1


def fragment_of(structure, atoms):
    return Fragment.from_selection(structure, p1.expand(structure),
                                   atoms, bonding.graph(structure))


def test_copying_a_molecule(dry_ice):
    """One CO2 out of the four in the cell, with its two bonds."""
    graph = bonding.graph(dry_ice)
    molecule = graph.fragments()[0].atoms
    fragment = fragment_of(dry_ice, molecule)

    assert fragment.n_atoms == 3
    assert fragment.formula == "CO2"
    assert len(fragment.bonds) == 2
    assert np.allclose(fragment.centroid, 0.0, atol=1e-9)


def test_an_empty_selection_copies_nothing(rutile):
    fragment = fragment_of(rutile, [])
    assert fragment.is_empty and fragment.n_atoms == 0
    assert fragment.formula == ""
    assert np.allclose(fragment.centroid, 0.0)


def test_xyz_round_trip(dry_ice):
    fragment = fragment_of(dry_ice, bonding.graph(
        dry_ice).fragments()[0].atoms)
    text = fragment.to_xyz()
    assert text.splitlines()[0] == "3"
    assert "Crystal Builder" in text.splitlines()[1]

    back = Fragment.from_xyz(text)
    assert back.formula == fragment.formula
    assert np.allclose(back.cart, fragment.cart, atol=1e-6)


def test_xyz_from_another_program():
    """A plain XYZ with no comment conventions still pastes."""
    text = "2\nwater bits\nO 0.0 0.0 0.0\nH 0.96 0.0 0.0\n"
    fragment = Fragment.from_xyz(text)
    assert fragment.n_atoms == 2
    assert fragment.formula == "HO"
    assert np.linalg.norm(fragment.cart[0] - fragment.cart[1]) == \
        pytest.approx(0.96)


@pytest.mark.parametrize("bad", ["", "nonsense", "2\ncomment\nO 0 0\n",
                                 "5\nc\nO 0 0 0\n"])
def test_malformed_xyz_is_rejected(bad):
    with pytest.raises(ValueError):
        Fragment.from_xyz(bad)


def test_pasting_into_p1(dry_ice):
    from xtal.core.symmetry import reduce_to_p1
    flat = reduce_to_p1(dry_ice)
    # a real molecule, not just the first three indices: the expansion
    # lists every C before every O, so 0-1-2 is three carbons
    molecule = bonding.graph(flat).fragments()[0].atoms
    fragment = fragment_of(flat, molecule)
    host = Host(flat.copy())
    stack = CommandStack()
    before = host.structure.copy()

    command = PasteFragment(fragment, offset=[1.0, 1.0, 1.0])
    assert "paste 3 atom(s)" in command.describe(host.structure)
    stack.push(command, host)

    assert host.structure.n_sites == before.n_sites + 3
    assert len(host.structure.bonds) == 2       # the internal bonds
    stack.undo(host)
    assert host.structure == before


def test_pasting_into_a_symmetric_structure_says_what_will_happen(
        rutile):
    """Pasting into Fm-3m or P4_2/mnm multiplies the atoms; a person
    has to be told before it happens, not after."""
    fragment = fragment_of(rutile, [0])
    command = PasteFragment(fragment)
    message = command.describe(rutile)
    assert "P42/mnm" in message
    assert "multiply" in message

    host = Host(rutile.copy())
    CommandStack().push(command, host)
    assert host.structure.n_sites == 3
    assert p1.expand(host.structure).n_atoms > 6


def test_pasted_atoms_land_where_they_are_put(dry_ice):
    from xtal.core.symmetry import reduce_to_p1
    flat = reduce_to_p1(dry_ice)
    molecule = bonding.graph(flat).fragments()[0].atoms
    fragment = fragment_of(flat, molecule)
    host = Host(flat.copy())
    offset = np.array([2.0, 3.0, 4.0])
    CommandStack().push(PasteFragment(fragment, offset), host)

    pasted = host.structure.sites[-3:]
    cart = np.array([host.structure.lattice.to_cart(s.frac)
                     for s in pasted])
    assert np.allclose(cart.mean(axis=0), offset, atol=1e-6)


def test_paste_defaults_to_the_cell_centre(dry_ice):
    from xtal.core.symmetry import reduce_to_p1
    flat = reduce_to_p1(dry_ice)
    molecule = bonding.graph(flat).fragments()[0].atoms
    fragment = fragment_of(flat, molecule)
    sites = fragment.to_sites(flat.lattice)
    centre = np.array([flat.lattice.to_cart(s.frac)
                       for s in sites]).mean(axis=0)
    assert np.allclose(centre, flat.lattice.to_cart([0.5, 0.5, 0.5]),
                       atol=1e-6)


def test_occupancies_survive_a_copy():
    from xtal import Lattice, Structure
    structure = Structure.from_arrays(
        Lattice.cubic(10.0), ["Na", "K"], [[0.4, 0.5, 0.5],
                                           [0.6, 0.5, 0.5]],
        occupancies=[0.3, 0.7])
    fragment = fragment_of(structure, [0, 1])
    assert fragment.occupancies == (0.3, 0.7)
    sites = fragment.to_sites(structure.lattice)
    assert [s.occupancy for s in sites] == [0.3, 0.7]
