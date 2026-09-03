"""A molecule from a string, and where its connection points land."""

from __future__ import annotations

import subprocess
import sys

import numpy as np
import pytest

from xtal.build import (
    MISSING,
    BuildError,
    Molecule,
    from_smiles,
    installed,
)
from xtal.core import elements as el
from xtal.mof.block import CONNECTION_DISTANCE

needs_rdkit = pytest.mark.skipif(not installed(), reason=MISSING)


def anchor_of(molecule: Molecule, index: int) -> int:
    """The one atom a connection point hangs off."""
    found = [j if i == index else i for i, j, _ in molecule.bonds
             if index in (i, j)]
    assert len(found) == 1
    return found[0]


def test_the_check_does_not_import_rdkit():
    """``installed`` is asked on every menu rebuild, so it reads the
    path and stops.  Importing RDKit to find out whether RDKit is
    there would stall the window every time.

    In a subprocess because the assertion is about a fresh
    interpreter: any earlier test that built a molecule has RDKit in
    ``sys.modules`` already, and this would then pass or fail on the
    order the files happened to run in.
    """
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys; from xtal.build import installed; "
         "installed(); print('rdkit' in sys.modules)"],
        capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


@needs_rdkit
def test_benzene_comes_out_flat_and_aromatic():
    molecule = from_smiles("c1ccccc1")

    assert molecule.n_atoms == 12               # six C, six H
    assert molecule.formula == "C6H6"
    assert {order for _, _, order in molecule.bonds} == {1.0, 1.5}
    centred = molecule.cart - molecule.cart.mean(axis=0)
    normal = np.linalg.svd(centred)[2][2]
    assert np.abs(centred @ normal).max() < 0.05


@needs_rdkit
def test_the_geometry_starts_near_the_force_fields_minimum():
    """The point of building from a force field's own numbers: what
    comes out does not have to be dragged anywhere first."""
    molecule = from_smiles("c1ccccc1")
    aromatic = [np.linalg.norm(molecule.cart[i] - molecule.cart[j])
                for i, j, order in molecule.bonds if order == 1.5]

    assert aromatic
    assert all(abs(length - 1.39) < 0.05 for length in aromatic)


@needs_rdkit
def test_water_comes_out_bent_and_the_right_size():
    molecule = from_smiles("O")
    oxygen = molecule.elements.index("O")
    hydrogens = [i for i, s in enumerate(molecule.elements)
                 if s == "H"]
    arms = [molecule.cart[h] - molecule.cart[oxygen]
            for h in hydrogens]

    assert all(0.9 < np.linalg.norm(a) < 1.05 for a in arms)
    cosine = (arms[0] @ arms[1]
              / (np.linalg.norm(arms[0]) * np.linalg.norm(arms[1])))
    assert 98.0 < np.degrees(np.arccos(cosine)) < 112.0


@needs_rdkit
def test_a_star_becomes_a_dummy_atom_and_not_a_hydrogen():
    """``*`` is RDKit's attachment point and ``X`` is this
    application's marker; the whole design rests on them being the
    same thing, so it is asserted rather than assumed."""
    molecule = from_smiles("*c1ccccc1")

    assert molecule.connections == (0,)
    assert molecule.elements[0] == "X"
    assert el.is_dummy(molecule.elements[0])
    assert molecule.formula == "C6H5"           # benzene, less one H


@needs_rdkit
def test_a_connection_point_lands_at_the_distance_pormake_uses():
    """0.75 A, not a bond length.  A block written with its connection
    points at 1.4 A builds a framework with every linker bond twice
    too long, and nothing anywhere reports an error."""
    molecule = from_smiles("*c1ccccc1")
    marker = molecule.connections[0]
    offset = molecule.cart[marker] - molecule.cart[
        anchor_of(molecule, marker)]

    assert np.linalg.norm(offset) == pytest.approx(
        CONNECTION_DISTANCE, abs=1e-6)


@needs_rdkit
def test_pulling_a_connection_point_in_keeps_its_direction():
    """Only the length is changed.  The direction came out of a
    relaxed geometry and is where the next building block goes."""
    loose = from_smiles("*c1ccccc1", optimise=False)
    marker = loose.connections[0]
    anchor = anchor_of(loose, marker)
    offset = loose.cart[marker] - loose.cart[anchor]
    ring = loose.cart[anchor] - loose.cart.mean(axis=0)

    assert (offset @ ring) / (np.linalg.norm(offset)
                              * np.linalg.norm(ring)) > 0.9


@needs_rdkit
def test_two_connection_points_come_out_where_the_string_put_them():
    molecule = from_smiles("[*:1]c1ccc(cc1)[*:2]")
    first, second = molecule.connections
    ends = (molecule.cart[first] - molecule.cart.mean(axis=0),
            molecule.cart[second] - molecule.cart.mean(axis=0))
    cosine = (ends[0] @ ends[1]
              / (np.linalg.norm(ends[0]) * np.linalg.norm(ends[1])))

    assert molecule.n_connections == 2
    assert np.degrees(np.arccos(cosine)) > 175.0        # para


@needs_rdkit
def test_half_numbered_connection_points_are_refused():
    """Map numbers say which slot each point fills, so numbering some
    of them says nothing at all."""
    with pytest.raises(BuildError, match="map number"):
        from_smiles("[*:1]c1ccc(cc1)*")


@needs_rdkit
def test_connection_points_are_refused_where_they_are_not_wanted():
    """The box that drops a molecule into a cell does not do them, and
    says so rather than quietly building a benzene."""
    with pytest.raises(BuildError, match="building block"):
        from_smiles("*c1ccccc1", connection_points=False)


@needs_rdkit
def test_a_string_that_is_not_a_molecule_is_refused_by_name():
    with pytest.raises(BuildError, match="c1cc"):
        from_smiles("c1cc")


@needs_rdkit
def test_an_empty_string_is_refused():
    with pytest.raises(BuildError, match="no SMILES"):
        from_smiles("   ")


@needs_rdkit
def test_the_same_string_gives_the_same_molecule_twice():
    """A fixed seed, so that a user who builds the same linker twice
    gets the same one -- and so every assertion above is stable."""
    assert np.allclose(from_smiles("CC(=O)Oc1ccccc1C(=O)O").cart,
                       from_smiles("CC(=O)Oc1ccccc1C(=O)O").cart)


@needs_rdkit
def test_a_molecule_becomes_a_fragment_the_clipboard_can_paste():
    fragment = from_smiles("c1ccccc1").to_fragment()

    assert fragment.n_atoms == 12
    assert fragment.formula == "C6H6"
    assert len(fragment.bonds) == 12
    assert np.allclose(fragment.cart.mean(axis=0), 0.0, atol=1e-6)


@needs_rdkit
def test_a_molecule_becomes_a_p1_cell_with_room_around_it():
    """A molecule in vacuum is a molecule in a box big enough that the
    periodic images do not see each other."""
    structure = from_smiles("c1ccccc1", name="benzene").to_structure()
    cart = structure.lattice.to_cart(
        [site.frac for site in structure.sites])
    edge = structure.lattice.matrix[0][0]

    assert structure.space_group.is_p1
    assert structure.n_sites == 12
    assert cart.min() > 4.0 and cart.max() < edge - 4.0
    assert structure.meta["title"] == "benzene"


@needs_rdkit
def test_a_built_molecule_keeps_the_bonds_it_was_given():
    """Bonds arrive with the atoms and nothing perceives them -- the
    same rule Add atom obeys."""
    structure = from_smiles("c1ccccc1").to_structure()

    assert len(structure.bonds) == 12
    assert {round(b.order, 2) for b in structure.bonds} == {1.0, 1.5}
