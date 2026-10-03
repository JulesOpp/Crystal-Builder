"""A repeat unit: a head, a tail, and which hand it is."""

from __future__ import annotations

import numpy as np
import pytest

from xtal.build import MISSING, installed
from xtal.polymer import monomer
from xtal.polymer.monomer import MonomerError

needs_rdkit = pytest.mark.skipif(not installed(), reason=MISSING)


@needs_rdkit
def test_every_library_monomer_embeds_with_a_head_and_a_tail():
    """The picker offers these by name; one that refused when chosen
    would be the library advertising a chain it cannot build."""
    found = monomer.monomers()

    assert len(found) == 11
    for entry in found:
        unit = monomer.from_library(entry.name)
        assert unit.elements[unit.head] == "X", entry.name
        assert unit.elements[unit.tail] == "X", entry.name
        assert unit.head_members and unit.tail_members, entry.name
        assert "X" not in unit.body_elements, entry.name


@needs_rdkit
def test_the_head_is_star_one_whatever_order_it_is_written_in():
    """A map number says which end is which; the order the string
    happens to list them in must not."""
    unit = monomer.from_smiles("[*:2]CC([*:1])C")
    carbon = unit.head_members[0]
    neighbours = [j if i == carbon else i for i, j, _ in unit.bonds
                  if carbon in (i, j)]

    # [*:1] is written second, on the carbon carrying the methyl
    assert unit.head > unit.tail
    assert sorted(unit.elements[n] for n in neighbours).count("C") == 2


@needs_rdkit
def test_a_third_connection_point_is_refused_by_name():
    """Branching is a different generator; ``[*:3]`` is kept for it,
    so ignoring the third star now would change the format later."""
    with pytest.raises(MonomerError, match="branching is not built"):
        monomer.from_smiles("[*:1]CC([*:2])C[*:3]")


@needs_rdkit
def test_one_connection_point_is_refused_by_name():
    with pytest.raises(MonomerError, match="needs a head and a tail"):
        monomer.from_smiles("[*:1]CC")


@needs_rdkit
def test_a_ladder_monomer_stands_for_two_atoms_at_each_end():
    """PIM-1 meets the next unit through two oxygens and two ring
    carbons, which is what makes it a ladder and not a chain."""
    unit = monomer.from_library("PIM-1")

    assert unit.is_ladder
    assert sorted(unit.elements[m] for m in unit.head_members) == \
        ["O", "O"]
    assert sorted(unit.elements[m] for m in unit.tail_members) == \
        ["C", "C"]
    assert unit.formula == "C29H20N2O4"


def _signed_volume(unit, centre) -> float:
    """The handedness at a stereocentre: the triple product of three
    of its neighbours, in index order."""
    around = sorted({j if i == centre else i
                     for i, j, _ in unit.bonds if centre in (i, j)})
    a, b, c = (unit.cart[n] - unit.cart[centre] for n in around[:3])
    return float(np.dot(a, np.cross(b, c)))


@needs_rdkit
def test_a_mirrored_monomer_has_the_other_hand():
    """Tacticity is nothing but this: isotactic is one hand
    throughout, syndiotactic alternates.  A mirror that only moved
    the atoms would make every chain isotactic."""
    unit = monomer.from_library("Polypropylene")
    centre = unit.tail_members[0]
    other = unit.mirrored()

    assert other.mirror and not unit.mirror
    assert np.sign(_signed_volume(other, centre)) == \
        -np.sign(_signed_volume(unit, centre))
    assert other.mirrored().mirror is False
    np.testing.assert_allclose(other.mirrored().cart, unit.cart)


def test_a_block_file_is_read_head_first(tmp_path):
    """What *Save as Monomer* writes: the head is the first connection
    point in the file.  No RDKit -- a saved monomer is atoms."""
    path = tmp_path / "ethylene.xyz"
    path.write_text(
        "8\n    6    7\n"
        "C    -0.7700 0.0000 0.0000\n"
        "C     0.7700 0.0000 0.0000\n"
        "H    -1.1300 1.0300 0.0000\n"
        "H    -1.1300 -0.5100 0.8900\n"
        "H     1.1300 1.0300 0.0000\n"
        "H     1.1300 -0.5100 0.8900\n"
        "X    -1.3000 -0.4400 -0.5000\n"
        "X     1.3000 -0.4400 -0.5000\n"
        "0 1 S\n0 2 S\n0 3 S\n1 4 S\n1 5 S\n0 6 S\n1 7 S\n",
        encoding="utf-8")

    unit = monomer.from_block_file(path)

    assert unit.name == "ethylene"
    assert (unit.head, unit.tail) == (6, 7)
    assert unit.head_members == (0,) and unit.tail_members == (1,)
    assert unit.formula == "C2H4"


def test_ends_of_different_widths_are_refused():
    """A ladder head on a single-strand tail cannot join itself."""
    cart = np.zeros((5, 3)) + np.arange(5)[:, None]
    with pytest.raises(MonomerError, match="ladder is two at each end"):
        monomer.from_parts(
            ("X", "O", "O", "C", "X"), cart,
            ((0, 1, 1.0), (0, 2, 1.0), (1, 3, 1.0), (2, 3, 1.0),
             (3, 4, 1.0)), (0, 4))


def _styrene():
    from xtal.build import from_smiles

    return from_smiles("[*:1]CC([*:2])c1ccccc1").to_structure()


@needs_rdkit
def test_save_as_monomer_writes_the_head_first(tmp_path):
    """The file has no other way to say which end is the head, so the
    one chosen must be the first point written -- otherwise a chain of
    them is tail to tail wherever the user picked the other end."""
    structure = _styrene()
    first, second = monomer.connection_points(structure)
    as_drawn = monomer.from_structure(structure, head=first)

    path = monomer.save(structure, tmp_path / "PS.xyz", head=second)
    turned = monomer.from_block_file(path)

    assert turned.name == "PS"
    assert turned.formula == as_drawn.formula
    # The ends swap: the atom the drawn tail stood for is now the head.
    assert (turned.elements[turned.head_members[0]],
            turned.elements[turned.tail_members[0]]) == ("C", "C")
    np.testing.assert_allclose(
        turned.cart[turned.head_members[0]],
        as_drawn.cart[as_drawn.tail_members[0]], atol=1e-3)


@needs_rdkit
def test_a_molecule_that_is_not_a_monomer_leaves_no_file(tmp_path):
    """A refused save that still wrote its file would put an entry in
    the polymer builder's library that fails when it is chosen."""
    from xtal.build import from_smiles

    structure = from_smiles("[*:1]c1ccc([*:2])cc1[*:3]").to_structure()

    with pytest.raises(MonomerError, match="branching"):
        monomer.save(structure, tmp_path / "three.xyz")
    assert not (tmp_path / "three.xyz").exists()
    assert monomer.saved(tmp_path) == ()


@needs_rdkit
def test_a_connection_point_is_named_by_the_atom_it_stands_for():
    """The head is picked from a list of these, and two bare X labels
    would ask the user to guess."""
    structure = _styrene()
    names = [monomer.point_name(structure, p)
             for p in monomer.connection_points(structure)]

    assert len(names) == 2
    assert all(" on C" in name for name in names)
    assert names[0] != names[1]
