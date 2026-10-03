"""Functional groups, found off the bond graph.

What breaks if these regress: an acid counted as a hydroxyl and a
carbonyl (and its hydrogen selected twice), a group that closes
through a cell face missed, or a refinement's bond lengths deciding
which oxygen of an acid carries the hydrogen.
"""

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.core import bonding, groups, p1
from xtal.core.site import Site
from xtal.core.structure import Change


def _molecule(atoms, box=12.0, shift=(4.0, 4.0, 4.0)):
    """A molecule from ``(element, x, y, z)`` in a cubic box, moved by
    ``shift`` A and wrapped."""
    lattice = Lattice.cubic(box)
    sites = [Site(e, (np.array(xyz) + shift) / box % 1.0)
             for e, *xyz in atoms]
    return Structure(lattice=lattice, sites=sites)


def _acetic_acid(double=1.21, single=1.30):
    """CH3-C(=O)OH, with the two C-O bonds of the lengths given."""
    up = np.array([0.5, 0.866, 0.0])
    down = np.array([0.5, -0.866, 0.0])
    carbon = np.array([1.50, 0.0, 0.0])
    o_double = carbon + double * up
    o_single = carbon + single * down
    return _molecule([
        ("C", 0.0, 0.0, 0.0), ("C", *carbon),
        ("O", *o_double), ("O", *o_single),
        ("H", *(o_single + [0.96, 0.0, 0.0])),
        ("H", -0.37, 1.03, 0.0), ("H", -0.37, -0.51, 0.89),
        ("H", -0.37, -0.51, -0.89)])


def _found(structure):
    return groups.detect(p1.expand(structure), bonding.graph(structure))


def test_a_carboxylic_acid_is_one_group_not_a_hydroxyl_and_a_carbonyl():
    """Its OH is a hydroxyl and its C=O a carbonyl to a pattern that
    looks at one oxygen at a time.  Fails if a hydroxyl selection
    takes an acid's hydrogen as well."""
    found = _found(_acetic_acid())
    assert set(found) == {"carboxylic_acid"}
    (acid,) = found["carboxylic_acid"]
    cell = p1.expand(_acetic_acid())
    assert sorted(cell.elements[a] for a in acid.atoms) == [
        "C", "H", "O", "O"]
    assert [cell.elements[a] for a in acid.handle] == ["H"]


def test_a_bond_length_does_not_change_what_a_group_is():
    """The hydroxyl oxygen is the one the hydrogen is on, even when a
    refinement wrote it the shorter of the two.  Fails if lengths
    decide which oxygen is which."""
    swapped = _acetic_acid(double=1.36, single=1.20)
    found = _found(swapped)
    (acid,) = found["carboxylic_acid"]
    cell = p1.expand(swapped)
    graph = bonding.graph(swapped)
    hydrogen = acid.handle[0]
    (oxygen,) = graph.neighbors(hydrogen)
    assert cell.elements[oxygen] == "O"
    assert oxygen == 3


def test_an_epoxide_is_found_through_a_cell_face():
    """An epoxide on a sheet crossing the cell boundary has its two
    carbons a lattice vector apart in the cell.  Fails if the C-C
    closing the three-ring is looked for in the home cell only."""
    epoxide = _molecule([("C", 0.0, 0.0, 0.0), ("C", 1.47, 0.0, 0.0),
                         ("O", 0.735, 1.21, 0.0)],
                        box=10.0, shift=(9.3, 5.0, 5.0))
    cell = p1.expand(epoxide)
    assert abs(cell.frac[0, 0] - cell.frac[1, 0]) > 0.5
    found = _found(epoxide)
    assert set(found) == {"epoxide"}
    assert len(found["epoxide"][0].atoms) == 3


def test_a_phenol_and_an_alcohol_are_told_apart_by_their_carbon():
    """A hydroxyl on a three-coordinate carbon is a phenol; on a
    four-coordinate one an alcohol."""
    methanol = _molecule([
        ("C", 0.0, 0.0, 0.0), ("O", 1.43, 0.0, 0.0),
        ("H", 1.75, 0.9, 0.0), ("H", -0.37, 1.03, 0.0),
        ("H", -0.37, -0.51, 0.89), ("H", -0.37, -0.51, -0.89)])
    assert set(_found(methanol)) == {"alcohol"}
    assert groups.census(methanol) == {"alcohol": 1}


def test_a_dummy_atom_never_matches():
    """A marker where a hydrogen would be is not a hydroxyl."""
    marked = _molecule([
        ("C", 0.0, 0.0, 0.0), ("O", 1.43, 0.0, 0.0),
        ("X", 1.75, 0.9, 0.0)])
    assert "alcohol" not in _found(marked)


def test_ring_ether_ester_and_fluoride_on_a_small_ring():
    """A lactone is an ester whose ether oxygen closes a ring, a C-F
    is its fluorine.  gamma-Butyrolactone with one fluorine."""
    ring = []
    for k, e in enumerate(("O", "C", "C", "C", "C")):
        angle = 2 * np.pi * k / 5
        ring.append((e, 1.24 * np.cos(angle), 1.24 * np.sin(angle), 0.0))
    carbonyl = np.array(ring[1][1:]) * (1 + 1.21 / 1.24)
    fluorine = np.array(ring[3][1:]) * (1 + 1.38 / 1.24)
    lactone = _molecule([*ring, ("O", *carbonyl), ("F", *fluorine)])
    found = _found(lactone)
    assert set(found) == {"lactone", "fluoride"}
    (match,) = found["lactone"]
    assert match.handle == (0,)


def test_groups_are_kept_through_a_drag_and_found_again_after_an_edit():
    """Memoised on the chemistry, as rings are."""
    acid = _acetic_acid()
    first = groups.matches(acid)
    assert groups.matches(acid) is first
    acid.sites[0].frac = acid.sites[0].frac + 0.001
    acid.touch(Change.POSITIONS)
    assert groups.matches(acid) is first
    acid.sites[4].element = "C"
    acid.touch(Change.TOPOLOGY)
    assert "carboxylic_acid" not in groups.matches(acid)


def test_an_unknown_group_or_part_is_refused_by_name():
    with pytest.raises(ValueError, match="unknown group"):
        groups.find(_acetic_acid(), "hydroxyl")
    with pytest.raises(ValueError, match="unknown part"):
        groups.atoms_of({}, "phenol", "tail")
