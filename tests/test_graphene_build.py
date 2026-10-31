"""Honeycomb sheets from a recipe: xtal.graphene.build."""

import itertools
from collections import Counter

import numpy as np
import pytest

from xtal.core import limits
from xtal.graphene import build as sheet
from xtal.graphene.build import GrapheneError, Recipe


def _bonds(structure):
    """Each stated bond's length, and each atom's bond count."""
    matrix = structure.lattice.matrix
    cart = np.array([s.frac for s in structure.sites]) @ matrix
    degree, lengths = Counter(), []
    for bond in structure.perceived.bonds:
        degree[bond.i] += 1
        degree[bond.j] += 1
        lengths.append(np.linalg.norm(
            cart[bond.j] + np.array(bond.image) @ matrix - cart[bond.i]))
    return degree, np.array(lengths)


def test_a_single_sheet_is_two_atoms_each_three_bonded_across_faces():
    """Graphene's own cell: two atoms, three bonds, every one 1.42 A
    and two of them through a face."""
    built = sheet.build(Recipe())
    degree, lengths = _bonds(built.structure)
    assert len(built.structure.sites) == 2
    assert dict(degree) == {0: 3, 1: 3}
    assert lengths == pytest.approx([1.42] * 3, abs=1e-9)
    assert built.a == pytest.approx(2.4595, abs=1e-3)
    assert built.gamma == pytest.approx(120.0)


def test_ab_graphite_has_c_6_70_and_no_interlayer_bonds():
    """Bulk Bernal graphite: two layers a period, c = 2 x 3.35, every
    bond inside a layer, and the layers 3.35 A apart."""
    built = sheet.build(Recipe(layers=2, stack="bulk"))
    structure = built.structure
    assert built.c == pytest.approx(6.70)
    z = [s.frac[2] for s in structure.sites]
    for bond in structure.perceived.bonds:
        assert z[bond.i] == pytest.approx(z[bond.j])
    assert built.closest_contact == pytest.approx(3.35)


def test_every_build_is_three_bonded_at_its_own_bond_length():
    """Every cell, repeat, stacking and stack: each atom three bonds,
    each bond exactly the sheet's.  The rectangular cell put atoms a
    rounding error short of a face, and wrapping them without their
    bonds stated some 16 A long.  Twisted at 21.79 degrees, its
    smallest cell."""
    for rectangular, cells, layers, stacking, stack in itertools.product(
            (False, True), ((1, 1), (3, 2)), (1, 2, 3, 6),
            sheet.STACKINGS, sheet.STACKS):
        elements = ("B", "N") if stacking == "AA'" else ("C", "C")
        try:
            built = sheet.build(Recipe(
                element_a=elements[0], element_b=elements[1],
                rectangular=rectangular, cells_a=cells[0],
                cells_b=cells[1], layers=layers, stacking=stacking,
                stack=stack, twist="21.79"))
        except GrapheneError:
            continue
        degree, lengths = _bonds(built.structure)
        assert set(degree.values()) == {3}
        assert len(degree) == len(built.structure.sites)
        assert np.ptp(lengths) < 1e-9


def test_abc_needs_three_layers_per_period_in_bulk():
    """A bulk stack repeats its sequence along c, so ABC in four
    layers would be ABCA then A again: refused, naming the counts that
    work.  A slab of four is fine."""
    with pytest.raises(GrapheneError, match="multiple of 3: 3 or 6"):
        sheet.build(Recipe(layers=4, stacking="ABC", stack="bulk"))
    assert len(sheet.build(Recipe(layers=4, stacking="ABC"))
               .structure.sites) == 8


def test_ab_stacking_puts_half_the_atoms_over_the_hexagon_centres():
    """Bernal: one sublattice of each layer sits over an atom of the
    one below, the other over a hexagon's centre.  AA puts every atom
    over another."""
    def over(stacking):
        built = sheet.build(Recipe(layers=2, stacking=stacking,
                                   stack="bulk"))
        cart = np.array([s.frac for s in built.structure.sites]) \
            @ built.structure.lattice.matrix
        z = cart[:, 2]
        low, high = cart[z < z.mean()], cart[z > z.mean()]
        matrix = built.structure.lattice.matrix[:2, :2]
        count = 0
        for atom in high:
            for below in low:
                d = (atom[:2] - below[:2]) @ np.linalg.inv(matrix)
                if np.allclose(d - np.round(d), 0, atol=1e-6):
                    count += 1
        return count

    assert over("AA") == 2
    assert over("AB") == 1


def test_aa_prime_alternates_the_elements_and_needs_two():
    built = sheet.build(Recipe(element_a="B", element_b="N", layers=2,
                               stacking="AA'", stack="bulk"))
    sites = built.structure.sites
    z = [s.frac[2] for s in sites]
    for i, j in itertools.combinations(range(len(sites)), 2):
        if np.allclose(sites[i].frac[:2], sites[j].frac[:2]) \
                and z[i] != z[j]:
            assert {sites[i].element, sites[j].element} == {"B", "N"}
    with pytest.raises(GrapheneError, match="is AA when"):
        sheet.checked(Recipe(stacking="AA'"))


def test_a_rectangular_cell_has_four_atoms_a_layer_and_right_angles():
    built = sheet.build(Recipe(rectangular=True))
    assert built.atoms_per_layer == 4
    assert built.gamma == pytest.approx(90.0)
    assert built.b / built.a == pytest.approx(np.sqrt(3))


def test_the_spacing_follows_the_elements_unless_one_is_typed():
    assert Recipe().interlayer == 3.35
    assert Recipe(element_a="B", element_b="N").interlayer == 3.33
    recipe = sheet.checked(Recipe(spacing="3.4"))
    assert recipe.interlayer == 3.4 and recipe.spacing_source == "as given"
    with pytest.raises(GrapheneError, match="the layer spacing must "
                                            "be a number, not 'wide'"):
        sheet.checked(Recipe(spacing="wide"))
    with pytest.raises(GrapheneError, match="the layer spacing must "
                                            "be 1.0 to 20.0 A, not 25"):
        sheet.checked(Recipe(spacing="25"))


def test_a_slab_leaves_the_vacuum_above_its_top_layer():
    built = sheet.build(Recipe(layers=3, vacuum=20.0))
    assert built.c == pytest.approx(2 * 3.35 + 20.0)


@pytest.mark.parametrize("rectangular, cells, layers", [
    (False, (1, 1), 1), (False, (5, 3), 2), (True, (4, 4), 3)])
def test_the_estimate_is_exact(rectangular, cells, layers):
    recipe = Recipe(rectangular=rectangular, cells_a=cells[0],
                    cells_b=cells[1], layers=layers)
    assert limits.graphene_atoms(recipe) == len(
        sheet.build(recipe).structure.sites)


def test_a_sheet_over_the_hard_limit_names_a_repeat_that_fits():
    verdict = limits.check_graphene(Recipe(cells_a=200, cells_b=200,
                                           layers=3), limits.STANDARD)
    assert verdict.refused
    assert "182 x 182 is the largest repeat that fits" in verdict.sentence
    assert not limits.check_graphene(Recipe(cells_a=182, cells_b=182,
                                            layers=3),
                                     limits.STANDARD).refused
