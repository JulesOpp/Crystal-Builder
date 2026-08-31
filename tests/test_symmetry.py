"""Detection, adoption, reduction: the symmetry workflow."""

import numpy as np
import pytest

from xtal import Lattice, SpaceGroup, Structure
from xtal.core import p1, symmetry
from xtal.core.site import Site

# ------------------------------------------------------------- detect

@pytest.mark.parametrize("name,number,orbits", [
    ("rutile", 136, 2), ("quartz", 154, 2), ("halite", 225, 2),
    ("dry_ice", 205, 2),
])
def test_detect_recovers_the_known_group(name, number, orbits, request):
    structure = request.getfixturevalue(name)
    info = symmetry.detect(structure)
    assert info.number == number
    assert info.n_orbits == orbits
    assert info.space_group == structure.space_group
    assert info.is_standard_setting
    assert str(number) in info.summary()


def test_detection_works_from_p1(rutile):
    """The interesting direction: throw the symmetry away, get it back.
    """
    flat = symmetry.reduce_to_p1(rutile)
    assert flat.is_p1 and flat.n_sites == 6
    info = symmetry.detect(flat)
    assert info.number == 136
    assert info.n_operations == 16


def test_tolerance_decides_what_counts_as_symmetric(rutile):
    """A small distortion is invisible at a loose tolerance and fatal
    at a tight one -- which is why the tolerance is a user control."""
    flat = symmetry.reduce_to_p1(rutile)
    flat.sites[2].frac = flat.sites[2].frac + np.array([0.004, 0, 0])
    flat.touch()

    assert symmetry.detect(flat, symprec=1e-5).number < 136
    assert symmetry.detect(flat, symprec=0.1).number == 136


def test_detect_rejects_an_empty_cell():
    with pytest.raises(ValueError):
        symmetry.detect(Structure.empty())


def test_detection_separates_sites_by_occupancy():
    """Two half-occupied sites of the same element are not equivalent
    to a full one; species ids must carry the occupancy."""
    full = Structure.from_arrays(
        Lattice.cubic(4.0), ["Na", "Na"],
        [[0, 0, 0], [0.5, 0.5, 0.5]])
    mixed = Structure.from_arrays(
        Lattice.cubic(4.0), ["Na", "Na"],
        [[0, 0, 0], [0.5, 0.5, 0.5]], occupancies=[1.0, 0.5])
    # Identical atoms at (0,0,0) and (1/2,1/2,1/2) are body-centred;
    # making one of them half-occupied breaks the centring translation.
    assert symmetry.detect(full).number == 229          # Im-3m
    assert symmetry.detect(mixed).number == 221         # Pm-3m


def test_wyckoff_assignment(quartz):
    labelled = symmetry.assign_wyckoff(quartz)
    assert labelled.sites[0].wyckoff == "3a"
    assert labelled.sites[1].wyckoff == "6c"


# ---------------------------------------------------------------- P1

def test_reduce_to_p1_preserves_the_crystal(quartz):
    from xtal.core import properties
    flat = symmetry.reduce_to_p1(quartz)
    assert flat.n_sites == p1.expand(quartz).n_atoms == 9
    assert flat.space_group.is_p1
    assert flat.lattice == quartz.lattice
    assert properties.density(flat) == pytest.approx(
        properties.density(quartz))
    assert all(s.label for s in flat.sites)


def test_reduce_to_p1_is_idempotent(rutile):
    once = symmetry.reduce_to_p1(rutile)
    twice = symmetry.reduce_to_p1(once)
    assert twice.n_sites == once.n_sites


# ------------------------------------------------------- asymmetrize

@pytest.mark.parametrize("name", ["rutile", "quartz", "halite",
                                  "dry_ice"])
def test_p1_then_asymmetrize_round_trips(name, request):
    """The round trip every structure must survive: expand to P1,
    detect, reduce back, and land on the same crystal."""
    original = request.getfixturevalue(name)
    flat = symmetry.reduce_to_p1(original)
    back, report = symmetry.asymmetrize(flat)

    assert report.ok, report.message
    assert back.space_group == original.space_group
    assert back.n_sites == original.n_sites
    assert p1.expand(back).n_atoms == p1.expand(original).n_atoms
    assert report.n_before == p1.expand(original).n_atoms
    assert report.n_after == original.n_sites


def test_asymmetrize_refuses_a_non_standard_setting(rutile):
    """A cell that is not in the standard setting cannot simply adopt
    the group -- the caller is told, not handed a wrong structure."""
    flat = symmetry.reduce_to_p1(rutile)
    shifted = flat.copy()
    for s in shifted.sites:                 # move the origin
        s.frac = np.mod(s.frac + np.array([0.13, 0.07, 0.21]), 1.0)
    shifted.touch()

    result, report = symmetry.asymmetrize(shifted)
    assert not report.ok
    assert "standard setting" in report.message
    assert result is shifted                # unchanged

    fixed, report2 = symmetry.asymmetrize(shifted,
                                          standardize_cell=True)
    assert report2.ok, report2.message
    assert fixed.space_group.number == 136
    assert fixed.n_sites == 2


def test_asymmetrize_keeps_labels_when_the_cell_is_untouched(rutile):
    flat = symmetry.reduce_to_p1(rutile)
    flat.sites[0].u_iso = 0.0123
    back, report = symmetry.asymmetrize(flat)
    assert report.ok
    assert back.sites[0].u_iso == 0.0123    # site metadata survived
    assert back.sites[0].wyckoff == "2a"


# ---------------------------------------------------- set_space_group

def test_reinterpret_generates_the_orbit(rutile):
    """Two sites in P1, reinterpreted in P4_2/mnm, become six atoms."""
    seed = Structure.from_arrays(
        rutile.lattice, ["Ti", "O"],
        [[0, 0, 0], [0.3053, 0.3053, 0]])
    out, report = symmetry.set_space_group(seed, "P4_2/mnm")
    assert out.n_sites == 2                 # asymmetric unit unchanged
    assert p1.expand(out).n_atoms == 6      # cell contents grew
    assert report.n_before == 2 and report.n_after == 6
    assert not report.warnings


def test_reinterpret_warns_about_overlaps(rutile):
    """Applying a group to coordinates that were already the full cell
    is the classic mistake; it must be reported, not hidden."""
    flat = symmetry.reduce_to_p1(rutile)
    _out, report = symmetry.set_space_group(flat, "P4_2/mnm")
    assert report.warnings
    assert "overlap" in report.warnings[0]


def test_impose_finds_the_asymmetric_unit(quartz):
    flat = symmetry.reduce_to_p1(quartz)
    out, report = symmetry.set_space_group(flat, "P3221", mode="impose")
    assert report.ok, report.warnings
    assert out.n_sites == 2
    assert p1.expand(out).n_atoms == 9


def test_impose_reports_symmetry_the_structure_does_not_have(halite):
    flat = symmetry.reduce_to_p1(halite)
    flat.remove_sites([3])                  # break the symmetry
    _out, report = symmetry.set_space_group(flat, "Fm-3m",
                                            mode="impose")
    assert not report.ok
    assert "not present" in report.warnings[0]


def test_unknown_mode_raises(rutile):
    with pytest.raises(ValueError):
        symmetry.set_space_group(rutile, "P 1", mode="guess")


# ------------------------------------------------------- housekeeping

def test_standardize_returns_a_conventional_cell(quartz):
    out, report = symmetry.standardize(quartz)
    assert out.is_p1
    assert out.n_sites == 9
    assert "standardised" in report.message
    assert symmetry.detect(out).number == 154


def test_standardize_to_primitive_shrinks_a_centred_cell(halite):
    out, _report = symmetry.standardize(halite, to_primitive=True)
    assert out.n_sites == 2                 # F centring: 8 -> 2
    assert out.lattice.volume == pytest.approx(
        halite.lattice.volume / 4)


def test_merge_duplicates():
    s = Structure.from_arrays(
        Lattice.cubic(5.0), ["Na", "Na", "Cl"],
        [[0, 0, 0], [0.001, 0, 0], [0.5, 0.5, 0.5]])
    merged, report = symmetry.merge_duplicates(s, tol=0.05)
    assert merged.n_sites == 2
    assert report.merged == 1
    assert "merged 1" in report.message

    untouched, report2 = symmetry.merge_duplicates(s, tol=0.001)
    assert untouched.n_sites == 3
    assert report2.merged == 0
    assert "no duplicates" in report2.message


def test_merge_respects_element_and_periodicity():
    """Atoms of different elements never merge; atoms across a cell
    boundary do."""
    s = Structure(Lattice.cubic(5.0), [
        Site("Na", [0.0, 0, 0]),
        Site("Cl", [0.001, 0, 0]),
        Site("Na", [0.9999, 0, 0]),         # the same atom, wrapped
    ])
    merged, report = symmetry.merge_duplicates(s, tol=0.05)
    assert merged.n_sites == 2
    assert report.merged == 1
    assert {site.element for site in merged.sites} == {"Na", "Cl"}


def test_report_is_truthy(rutile):
    _out, report = symmetry.set_space_group(rutile, SpaceGroup.p1())
    assert bool(report) is report.ok


# ======================================================================
#  CHANGE OF HAND
# ======================================================================

def test_inversion_changes_the_group_as_well_as_the_coordinates(quartz):
    """Doing only half of it is the bug: negating the coordinates and
    leaving P3_221 in place gives a structure whose atoms no longer
    obey their own symmetry."""
    out, report = symmetry.invert(quartz)
    assert out.space_group.short_name == "P3121"
    assert "P3221 -> P3121" in report.message
    # the inverted structure genuinely has the partner's symmetry
    assert symmetry.detect(out, 1e-5).international == "P3_121"


def test_inversion_is_its_own_inverse(quartz):
    there, _ = symmetry.invert(quartz)
    back, _ = symmetry.invert(there)
    assert back.space_group == quartz.space_group
    before = np.sort(p1.expand(quartz).frac, axis=0)
    after = np.sort(p1.expand(back).frac, axis=0)
    assert np.allclose(before, after, atol=1e-9)


def test_inversion_leaves_the_lattice_alone(quartz):
    out, _ = symmetry.invert(quartz)
    assert np.allclose(out.lattice.matrix, quartz.lattice.matrix)
    assert out.lattice.is_right_handed == quartz.lattice.is_right_handed


@pytest.mark.parametrize("name,partner", [
    ("P41", "P43"), ("P43", "P41"), ("P3121", "P3221"),
    ("P61", "P65"), ("P41212", "P43212"), ("P4132", "P4332"),
])
def test_the_eleven_enantiomorphic_pairs_are_named(name, partner):
    group = SpaceGroup.from_name(name)
    assert symmetry.enantiomorph(group).short_name == partner
    assert partner in symmetry.hand_description(group)


@pytest.mark.parametrize("name", ["I41", "F4132", "P212121"])
def test_a_self_enantiomorphic_group_keeps_its_symbol(name):
    """The case most likely to be mistaken for a no-op: the symbol does
    not change and the structure does."""
    group = SpaceGroup.from_name(name)
    assert symmetry.enantiomorph(group) == group
    assert symmetry.hand_description(group) == "chiral, its own enantiomorph"


def test_the_change_of_hand_op_is_not_always_a_bare_inversion():
    """I4_1 and F4_132 need an origin shift to land back in the
    standard setting; using -x,-y,-z for them would put the structure
    into a non-standard setting without saying so."""
    _rot, tran = symmetry.change_of_hand_op(SpaceGroup.from_name("I41"))
    assert np.allclose(tran, [0.5, 0.0, 0.0])
    _rot, tran = symmetry.change_of_hand_op(
        SpaceGroup.from_name("F4132"))
    assert np.allclose(tran, [0.25, 0.25, 0.25])


def test_inverting_a_centrosymmetric_structure_says_it_changes_nothing(
        rutile):
    out, report = symmetry.invert(rutile)
    assert out.space_group == rutile.space_group
    assert "centrosymmetric" in report.message
    assert report.warnings
    before = np.sort(p1.expand(rutile).frac, axis=0)
    after = np.sort(p1.expand(out).frac, axis=0)
    assert np.allclose(before, after, atol=1e-9)


def test_hand_description_covers_the_three_answers(rutile, quartz):
    assert symmetry.hand_description(rutile.space_group) == \
        "centrosymmetric (achiral)"
    assert symmetry.hand_description(quartz.space_group) == \
        "chiral, enantiomorph P3121"
    assert "achiral" in symmetry.hand_description(
        SpaceGroup.from_name("P4mm"))
