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


@pytest.mark.parametrize("n, m", [(10, 10), (40, 39)])
def test_a_bond_too_short_for_the_flat_sheet_is_refused_naming_the_bond(
        n, m):
    """Below about 0.97 A the flat sheet's own second neighbours,
    sqrt(3) bonds apart, are within C-C's bonding distance, so every
    tube is refused however wide.  The sentence names the bond; it
    used to blame a 34 A tube for being thin."""
    with pytest.raises(NanotubeError) as e:
        tube.build(Recipe(n, m, bond=0.9))
    assert str(e.value) == (
        "at a 0.90 A bond even the flat sheet puts second neighbours "
        "1.56 A apart, within bonding distance (1.68 A)")


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


def _bond_lengths(built):
    """Each stated bond's length, and whether it carries a hydrogen."""
    sites = built.structure.sites
    return [(b.distance, "H" in (sites[b.i].element, sites[b.j].element))
            for b in built.structure.perceived.bonds]


@pytest.mark.parametrize("n, m", [(10, 0), (6, 5)])
def test_a_capped_tube_in_a_small_vacuum_keeps_its_bonds_short(n, m):
    """At 0.5 A of vacuum the bottom hydrogens start below z = 0 and
    are wrapped into the cell.  Unless each bond's image follows its
    atoms, every one of those bonds is stated across the cell, 17 A
    or more long, and a force field pulls the tube apart."""
    built = tube.build(Recipe(n, m, ends="capped", vacuum=0.5))
    for distance, to_h in _bond_lengths(built):
        if to_h:
            assert distance == pytest.approx(1.081, abs=0.002)
        else:
            assert 0.9 * 1.42 <= distance <= 1.42 + 1e-6


@pytest.mark.parametrize("ends", ["periodic", "bare"])
def test_a_tube_with_no_vacuum_keeps_its_bonds_short(ends):
    """With no vacuum the atom at angle zero sits exactly on the cell's
    far face and is wrapped to the near one.  Its bonds must follow it,
    or one is stated 13-23 A long."""
    built = tube.build(Recipe(10, 10, ends=ends, vacuum=0.0))
    for distance, _ in _bond_lengths(built):
        assert 0.9 * 1.42 <= distance <= 1.42 + 1e-6


@pytest.mark.parametrize("ends", ["capped", "bare"])
def test_a_finite_tube_leaves_the_vacuum_asked_for_between_its_ends(ends):
    """Along c, as across, the gap between the tube and its image is
    the vacuum, atom centre to atom centre, hydrogens included.
    Counting only the carbon span let the caps reach 1.08 A into the
    gap at each end, so 12 A of vacuum left under 10 A between
    images."""
    built = tube.build(Recipe(10, 10, ends=ends, vacuum=12.0))
    c = built.structure.lattice.parameters[2]
    z = built.structure.cart[:, 2]
    assert c - (z.max() - z.min()) == pytest.approx(12.0, abs=1e-6)


def test_a_left_handed_tube_says_nothing_of_its_mirror_image():
    """(5,6) is (6,5)'s mirror image, which the report's Chirality row
    says.  A note saying it too would print it twice."""
    assert not tube.build(Recipe(5, 6)).notes


def test_a_bare_tube_has_no_hydrogen():
    """Bare means the cut edge is left as it is.  A hydrogen here would
    be chemistry the person did not ask for, and its count would be
    wrong in the report."""
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
    B-N, rolled from Pyykko's aromatic B-N, 1.47 A.  The note names
    h-BN's own 1.446 A beside it, because the two differ."""
    built = tube.build(Recipe(10, 10, element_a="B", element_b="N"))
    sites = built.structure.sites
    for bond in built.structure.perceived.bonds:
        assert {sites[bond.i].element, sites[bond.j].element} == {"B", "N"}
    assert built.recipe.title == "(10,10) BN nanotube"
    assert built.recipe.bond_length == pytest.approx(1.47)
    assert built.chirality.bond == pytest.approx(1.47)
    assert ("h-BN's own B-N bond is 1.446 A; this tube was built at "
            "1.47 A") in built.notes


def test_the_bond_follows_the_elements_unless_one_is_typed():
    """Left empty the bond is the two elements' aromatic one from
    Pyykko's radii; a number given is used instead, as text from the
    form or a float from a script.  Regressing, a typed bond would be
    ignored or an empty one refused."""
    assert Recipe().bond_length == 1.42
    assert Recipe(element_a="Si", element_b="Si").bond_length \
        == pytest.approx(2.23)
    assert tube.checked(Recipe(bond="")).bond is None
    assert tube.checked(Recipe(bond=" 1.5 ")).bond_length == 1.5
    assert tube.checked(Recipe(bond=1.6)).bond_length == 1.6
    built = tube.build(Recipe(10, 10, element_a="B", element_b="N",
                              bond="1.446"))
    assert built.chirality.bond == 1.446
    assert not built.notes


@pytest.mark.parametrize("bond, wanted", [
    ("one", "the bond length must be a number, not 'one'"),
    ("0.5", "the bond length must be 0.8 to 3.0 A, not 0.5"),
    ("3.5", "the bond length must be 0.8 to 3.0 A, not 3.5"),
    (4.0, "the bond length must be 0.8 to 3.0 A, not 4"),
])
def test_a_bond_that_is_no_length_is_refused_by_name(bond, wanted):
    """A word, or a number outside 0.8-3.0 A, typed in the bond box is
    refused in one sentence naming it.  The box is text, so nothing
    else stops it: float() would raise a bare ValueError, and an
    out-of-range bond would roll a tube nobody can mean."""
    with pytest.raises(NanotubeError) as e:
        tube.checked(Recipe(bond=bond))
    assert str(e.value) == wanted


def test_an_element_with_no_double_bond_radius_is_noted():
    """Pyykko gives hydrogen no double-bond radius, so its single one
    stands in, and the note says so -- once a bond is typed it is not
    the radii's and the note goes."""
    built = tube.build(Recipe(10, 10, element_a="H", element_b="C"))
    assert built.recipe.bond_length == pytest.approx(1.03)
    assert ("Pyykkö gives no double-bond radius for H; its "
            "single-bond radius was used") in built.notes
    typed = tube.build(Recipe(10, 10, element_a="H", element_b="C",
                              bond="1.1"))
    assert not any("double-bond" in n for n in typed.notes)


@pytest.mark.parametrize("element_a, element_b, wanted", [
    ("Xx", "C", "'Xx' is not an element"),
    ("C", "Kryptonite", "'Kryptonite' is not an element"),
])
def test_an_unknown_element_is_refused_by_name(element_a, element_b,
                                               wanted):
    """A misspelt element is named back in the refusal.  Without it the
    build would fail somewhere deeper, or build with a symbol nothing
    else in the application knows, and the person would not learn
    which box was wrong."""
    with pytest.raises(NanotubeError, match=wanted):
        tube.checked(Recipe(element_a=element_a, element_b=element_b))


def test_elements_are_read_whatever_their_case():
    """"b" is boron.  Refusing it, or keeping it lower case, would fail
    a person who typed the symbol in a hurry or give the structure
    sites no element table recognises."""
    assert tube.checked(Recipe(element_a="b", element_b="N")).element_a \
        == "B"


def test_n_below_one_is_refused():
    """(0,0) has no circumference.  Let through, the roll divides by
    zero or builds an empty cell instead of saying what is wrong."""
    with pytest.raises(NanotubeError, match=r"n >= 1 and m >= 0"):
        tube.checked(Recipe(0, 0))


@pytest.mark.parametrize("symbol, length", [("C", 1.081), ("B", 1.181),
                                            ("N", 1.043)])
def test_hydrogen_lengths_are_uff_s_natural_ones(symbol, length):
    """The same X-H as Add Hydrogens (xtal/ff/hydrogens.py), which
    match experiment within 0.02 A (spec, Science)."""
    assert tube.hydrogen_length(symbol) == pytest.approx(length, abs=1e-3)


def test_an_element_with_no_sp2_type_takes_its_first_uff_type():
    """Silicon has no Si_R or Si_2, only Si3.  Without the fallback a
    capped Si tube would raise instead of building; its X-H is then
    UFF's Si3-H, 1.471 A."""
    assert tube.hydrogen_length("Si") == pytest.approx(1.471, abs=1e-3)


def test_an_element_uff_does_not_know_takes_its_covalent_radii():
    """Oganesson has no UFF type at all.  The covalent radii are the
    last answer, so a capped tube of anything the element table holds
    still builds."""
    from xtal.core import elements
    from xtal.ff.uff import params

    assert params.types_for("Og") == []
    assert tube.hydrogen_length("Og") == pytest.approx(
        elements.covalent_radius("Og") + elements.covalent_radius("H"))


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
    """The (n - m) mod 3 rule is carbon's.  Applied to BN, it would call
    an armchair BN tube a metal; applied to Si and C, it would claim a
    classification nobody has made."""
    bn = Recipe(element_a="N", element_b="B")
    assert "wide gap" in tube.electronic_character(bn)
    assert tube.electronic_character(
        Recipe(element_a="Si", element_b="C")) == "not classified"


def test_the_stated_bonds_survive_a_project_round_trip(tmp_path):
    """Saved and reopened, the tube keeps its stated bonds; none are
    perceived again.  Built at 1.75 A, longer than C-C's bonding
    distance, so perceiving on reopening would lose every C-C bond
    and this would fail."""
    from xtal.io.project import read_project_structure, write_project

    built = tube.build(Recipe(6, 5, ends="capped", bond=1.75))
    path = write_project(built.structure, tmp_path / "tube")
    again = read_project_structure(path)
    before = sorted((b.i, b.j, tuple(b.image))
                    for b in built.structure.perceived.bonds)
    after = sorted((b.i, b.j, tuple(b.image))
                   for b in again.perceived.bonds)
    assert after == before


def _closest_unbonded_by_brute_force(structure):
    """Every pair of atoms in the cell and its 26 neighbours, less the
    stated bonds and each atom with itself: the slow, plain answer."""
    from xtal.core import p1

    cell = p1.expand(structure)
    matrix = structure.lattice.matrix
    bonded = set()
    for b in structure.perceived.bonds:
        bonded.add((b.i, b.j, tuple(b.image)))
        bonded.add((b.j, b.i, tuple(-np.asarray(b.image))))
    home = cell.frac @ matrix
    best = np.inf
    for shift in np.ndindex(3, 3, 3):
        image = tuple(int(s) - 1 for s in shift)
        there = (cell.frac + image) @ matrix
        d = np.linalg.norm(home[:, None] - there[None], axis=2)
        for i, j in zip(*np.nonzero(d < 3.0), strict=True):
            if (i, j, image) in bonded or (i == j and image == (0, 0, 0)):
                continue
            best = min(best, float(d[i, j]))
    return best


def test_a_capped_tube_s_closest_contact_counts_its_hydrogens():
    """The report's row says "between atoms not bonded", so it is
    measured over the structure built, caps included.  A ragged cut on
    (6,5) leaves a cove whose two hydrogens point into the same
    half-hexagon, 1.74 A apart; measured over the rolled wall alone,
    the row said 2.43 A, a contact the structure does not have."""
    built = tube.build(Recipe(6, 5, ends="capped", length=20.0))
    assert built.closest_contact == pytest.approx(1.74, abs=0.02)
    assert built.closest_contact == pytest.approx(
        _closest_unbonded_by_brute_force(built.structure), abs=1e-6)


def test_a_periodic_tube_s_closest_contact_reaches_across_the_cell():
    """A periodic (10,10) has no caps: its closest contact is the
    wall's second neighbour, 2.45 A, found across the top of the cell
    as well as inside it.  A bond across the top not recognised as one
    would make the row 1.42 A."""
    built = tube.build(Recipe(10, 10, length=20.0))
    assert built.closest_contact == pytest.approx(2.45, abs=0.01)
    assert built.closest_contact == pytest.approx(
        _closest_unbonded_by_brute_force(built.structure), abs=1e-6)


def test_deuterium_with_no_bond_given_is_refused_asking_for_one():
    """D is an element here but not in Pyykkö's table, so with the bond
    left empty there is no radius to take it from: one sentence asking
    for a bond, never a KeyError.  Typed, it builds."""
    with pytest.raises(NanotubeError) as e:
        tube.checked(Recipe(element_a="D", element_b="C"))
    assert str(e.value) == ("Pyykkö gives no covalent radius for D; "
                            "type a bond length")
    assert tube.checked(Recipe(element_a="D", element_b="C",
                               bond="1.1")).bond_length == 1.1
