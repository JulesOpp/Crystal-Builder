"""A fullerene built from a recipe: xtal.fullerene.build."""

from collections import Counter

import numpy as np
import pytest

from xtal.core import pyykko
from xtal.fullerene import build as cage
from xtal.fullerene.build import FullereneError, Recipe

C60 = "1 7 9 11 13 15 18 20 22 24 26 32"


def _degrees(structure):
    degree = Counter()
    for bond in structure.perceived.bonds:
        degree[bond.i] += 1
        degree[bond.j] += 1
    return degree


def _cart(structure):
    return np.array([s.frac for s in structure.sites]) \
        @ structure.lattice.matrix


def test_c60_with_uff_is_a_round_cage_seven_angstroms_across():
    """The default is buckminsterfullerene, relaxed: 60 atoms, every
    one three-bonded, about 7 A across, the bonds within a few
    hundredths of each other (UFF's C_R makes them nearly equal)."""
    built = cage.build(Recipe())
    assert built.title == "C60-Ih"
    assert len(built.structure.sites) == 60
    assert set(_degrees(built.structure).values()) == {3}
    assert built.diameter == pytest.approx(7.0, abs=0.15)
    assert built.longest_bond - built.shortest_bond < 0.03
    assert built.order == 120 and built.ipr
    assert any("C_R" in note for note in built.notes)


def test_the_bonds_are_stated_and_survive_a_relaxation_unchanged():
    """90 bonds, the cage's own, and the same 90 after UFF: nothing is
    perceived, so a squeezed cage keeps its graph."""
    built = cage.build(Recipe(relax="none"))
    before = {(b.i, b.j) for b in built.structure.perceived.bonds}
    assert len(before) == 90
    relaxed = cage.build(Recipe())
    assert {(b.i, b.j) for b in relaxed.structure.perceived.bonds} \
        == before


def test_left_unrelaxed_the_mean_bond_is_the_one_asked_for():
    built = cage.build(Recipe(relax="none", bond="1.5"))
    cart = _cart(built.structure)
    lengths = [np.linalg.norm(cart[b.i] - cart[b.j])
               for b in built.structure.perceived.bonds]
    assert np.mean(lengths) == pytest.approx(1.5, abs=0.02)
    assert built.relaxed == ""


def test_a_silicon_cage_takes_silicon_s_aromatic_bond():
    built = cage.build(Recipe(element="si", relax="none"))
    assert built.title == "Si60-Ih"
    cart = _cart(built.structure)
    lengths = [np.linalg.norm(cart[b.i] - cart[b.j])
               for b in built.structure.perceived.bonds]
    assert np.mean(lengths) == pytest.approx(
        pyykko.aromatic_bond("Si", "Si"), abs=0.03)


@pytest.mark.parametrize("element", ["B N", "B/N", "B,N"])
def test_two_elements_are_refused_naming_the_odd_rings(element):
    with pytest.raises(FullereneError, match="odd rings"):
        cage.build(Recipe(element=element))


def test_a_word_that_is_no_element_is_refused_naming_it():
    with pytest.raises(FullereneError, match="'Qq' is not an element"):
        cage.checked(Recipe(element="Qq"))


def test_a_hydrogenated_cage_has_a_hydrogen_on_every_atom_pointing_out():
    """C60H60: one hydrogen per carbon, each bonded to it alone and
    further from the centre than its carbon."""
    built = cage.build(Recipe(hydrogenate=True, relax="none"))
    assert built.title == "C60H60-Ih"
    sites = built.structure.sites
    assert Counter(s.element for s in sites) == {"C": 60, "H": 60}
    cart = _cart(built.structure)
    centre = cart[:60].mean(axis=0)
    degree = _degrees(built.structure)
    for bond in built.structure.perceived.bonds:
        i, j = sorted((bond.i, bond.j))
        if sites[j].element == "H":
            assert degree[j] == 1
            assert np.linalg.norm(cart[j] - centre) \
                > np.linalg.norm(cart[i] - centre)
    assert built.hydrogens == 60


def test_a_typed_spiral_is_named_after_its_table_row():
    built = cage.build(Recipe(spiral=C60, relax="none"))
    assert built.isomer is not None and built.title == "C60-Ih"


def test_a_typed_spiral_that_is_not_canonical_says_which_is():
    """C70's spiral read from another start is the same cage; the
    report gives the canonical one."""
    from xtal.fullerene import spiral

    rotation = spiral.wind(70, (1, 7, 9, 11, 13, 15, 27, 29, 31, 33,
                                35, 37))
    other = None
    for first in range(len(rotation)):
        order = spiral.spiral_from(rotation, first, rotation[first][0])
        if order is not None:
            places = [i + 1 for i, f in enumerate(order)
                      if len(rotation[f]) == 5]
            if tuple(places) != (1, 7, 9, 11, 13, 15, 27, 29, 31, 33,
                                 35, 37):
                other = " ".join(map(str, places))
                break
    built = cage.build(Recipe(n=70, spiral=other, relax="none"))
    assert built.title == "C70-D5h"
    assert any("not the cage's canonical" in note
               for note in built.notes)


@pytest.mark.parametrize("text, match", [
    ("1 2 3", "twelve pentagons, not 3"),
    ("1 7 9 eleven", "twelve whole numbers"),
    ("1 7 9 11 14 16 23 25 32 34 36 38", "does not close"),
])
def test_a_bad_spiral_is_refused_saying_why(text, match):
    with pytest.raises(FullereneError, match=match):
        cage.build(Recipe(n=72, spiral=text))


def test_a_cage_with_touching_pentagons_says_how_many_bonds_they_share():
    """C20 is all pentagons: 30 pentagon-pentagon bonds, said."""
    built = cage.build(Recipe(n=20, relax="none"))
    assert built.pentagon_pairs == 30 and not built.ipr
    assert any("30 pentagon-pentagon bonds" in note
               for note in built.notes)


def test_the_box_leaves_the_vacuum_asked_for():
    built = cage.build(Recipe(relax="none", vacuum=10.0))
    side = built.structure.lattice.matrix[0, 0]
    cart = _cart(built.structure)
    assert side - np.ptp(cart, axis=0).max() == pytest.approx(10.0,
                                                              abs=1e-6)
