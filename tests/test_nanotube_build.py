"""A nanotube built from a recipe: xtal.nanotube.build."""

from collections import Counter

import numpy as np
import pytest

from xtal.nanotube import build as tube
from xtal.nanotube.build import NanotubeError, Recipe


def _framework_degrees(structure):
    """Bonds per atom among the non-hydrogen atoms, from the stated
    bonds."""
    heavy = {k for k, s in enumerate(structure.sites)
             if s.element != "H"}
    degree = Counter()
    for bond in structure.perceived.bonds:
        if bond.i in heavy and bond.j in heavy:
            degree[bond.i] += 1
            degree[bond.j] += 1
    return {k: degree[k] for k in heavy}


@pytest.mark.parametrize("n, m, reason", [
    (1, 0, "compressed to 1.06 A"),
    (1, 1, "compressed to 1.17 A"),
    (2, 0, "within bonding distance (1.68 A)"),
])
def test_a_tube_too_thin_to_roll_is_refused_saying_why(n, m, reason):
    """A bond crushed below 90%, or unbonded atoms within the
    application's own bonding distance: either way the tube is not the
    one asked for, and the sentence says which."""
    with pytest.raises(NanotubeError, match=r"tube is .* A across") as e:
        tube.build(Recipe(n, m))
    assert reason in str(e.value)


def test_a_thin_tube_that_rolls_is_built_with_a_compression_note():
    """(3,0) rolls, but with its bonds 3% short; (5,0) is within 3%
    and gets no note.  The note tells a person to relax it before
    trusting the geometry."""
    thin = tube.build(Recipe(3, 0))
    assert any("compresses bonds by up to 3%" in n for n in thin.notes)
    assert not tube.build(Recipe(5, 0)).notes


def test_a_periodic_tube_is_whole_periods_with_every_atom_three_bonded():
    """20 A of (10,10) is 8 periods of 2.46 A.  c is exactly that, and
    every atom has three stated bonds, the ones across the top
    included.  A bond lost at the seam or the top would leave an atom
    two-coordinate."""
    built = tube.build(Recipe(10, 10, length=20.0))
    assert built.periods == 8
    a, b, c = built.structure.lattice.parameters[:3]
    assert c == pytest.approx(8 * built.chirality.t_length)
    assert len(built.structure.sites) == 320
    assert set(_framework_degrees(built.structure).values()) == {3}


def test_the_box_leaves_the_vacuum_asked_for_between_images():
    """a = b = d + vacuum: the gap between the tube's wall and its
    image's is what the form says."""
    built = tube.build(Recipe(10, 10, vacuum=12.0))
    a, b = built.structure.lattice.parameters[:2]
    assert a == pytest.approx(built.chirality.diameter + 12.0)
    assert b == pytest.approx(a)


def test_a_capped_tube_has_one_hydrogen_on_each_edge_atom_at_uff_length():
    """Every framework atom keeps two or more bonds, each
    two-coordinate atom carries one H, and each H sits at UFF's
    natural C-H, 1.081 A, where Add Hydrogens would put it."""
    built = tube.build(Recipe(10, 10, ends="capped", length=20.0))
    structure = built.structure
    degrees = _framework_degrees(structure)
    assert min(degrees.values()) >= 2
    edge = sum(1 for d in degrees.values() if d == 2)
    hydrogens = [k for k, s in enumerate(structure.sites)
                 if s.element == "H"]
    assert len(hydrogens) == built.hydrogens == edge == 40
    cart = structure.cart
    for bond in structure.perceived.bonds:
        if bond.j in hydrogens or bond.i in hydrogens:
            assert bond.distance == pytest.approx(1.081, abs=0.002)
    assert np.isfinite(cart).all()


def test_a_bare_tube_has_no_hydrogen():
    built = tube.build(Recipe(10, 10, ends="bare", length=20.0))
    assert built.hydrogens == 0
    assert "H" not in {s.element for s in built.structure.sites}


def test_a_piece_too_short_to_be_a_tube_is_refused():
    """3 A of (10,0) is a ring of two-coordinate atoms after the cut,
    not a tube."""
    with pytest.raises(NanotubeError, match="must be longer than 3.00 A"):
        tube.build(Recipe(10, 0, ends="bare", length=3.0))


def test_a_bn_tube_alternates_and_says_its_own_bond_length():
    """B on one sublattice and N on the other: every framework bond is
    B-N.  The note names h-BN's own 1.446 A, because 1.42 is
    carbon's."""
    built = tube.build(Recipe(10, 10, element_a="B", element_b="N"))
    sites = built.structure.sites
    for bond in built.structure.perceived.bonds:
        assert {sites[bond.i].element, sites[bond.j].element} == {"B", "N"}
    assert built.recipe.title == "(10,10) BN nanotube"
    assert any("1.446 A" in n for n in built.notes)


@pytest.mark.parametrize("element_a, element_b, wanted", [
    ("Xx", "C", "'Xx' is not an element"),
    ("C", "Kryptonite", "'Kryptonite' is not an element"),
])
def test_an_unknown_element_is_refused_by_name(element_a, element_b,
                                               wanted):
    with pytest.raises(NanotubeError, match=wanted):
        tube.checked(Recipe(element_a=element_a, element_b=element_b))


def test_elements_are_read_whatever_their_case():
    assert tube.checked(Recipe(element_a="b", element_b="N")).element_a \
        == "B"


def test_n_below_one_is_refused():
    with pytest.raises(NanotubeError, match=r"n >= 1 and m >= 0"):
        tube.checked(Recipe(0, 0))


@pytest.mark.parametrize("symbol, length", [("C", 1.081), ("B", 1.181),
                                            ("N", 1.043)])
def test_hydrogen_lengths_are_uff_s_natural_ones(symbol, length):
    """The same X-H as Add Hydrogens (xtal/ff/hydrogens.py), which
    match experiment within 0.02 A (spec, Science)."""
    assert tube.hydrogen_length(symbol) == pytest.approx(length, abs=1e-3)


@pytest.mark.parametrize("n, m, wanted", [
    (10, 10, "metallic (armchair)"),
    (9, 0, "small-gap"),
    (10, 0, "semiconducting"),
    (5, 0, "unreliable this thin"),
])
def test_the_electronic_character_follows_n_minus_m_mod_3(n, m, wanted):
    """The textbook rule (Hamada 1992; Kane and Mele 1997) with Blase
    1994's caveat for tubes under 7 A."""
    assert wanted in tube.electronic_character(Recipe(n, m))


def test_a_bn_tube_is_semiconducting_and_another_pair_unclassified():
    bn = Recipe(element_a="N", element_b="B")
    assert "wide gap" in tube.electronic_character(bn)
    assert tube.electronic_character(
        Recipe(element_a="Si", element_b="C")) == "not classified"


def test_the_stated_bonds_survive_a_project_round_trip(tmp_path):
    """Saved and reopened, the tube keeps its stated bonds; none are
    perceived again, which would bond nothing new on a good tube but
    is not the builder's graph."""
    from xtal.io.project import read_project_structure, write_project

    built = tube.build(Recipe(6, 5, ends="capped"))
    path = write_project(built.structure, tmp_path / "tube")
    again = read_project_structure(path)
    before = sorted((b.i, b.j, tuple(b.image))
                    for b in built.structure.perceived.bonds)
    after = sorted((b.i, b.j, tuple(b.image))
                   for b in again.perceived.bonds)
    assert after == before
