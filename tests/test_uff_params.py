"""The UFF parameter table, and the quantities derived straight from
it.

A parameter table is data, and data is checked two ways: that it is
internally consistent (every row parses, every element is one the rest
of the application knows, no duplicates), and that the numbers the
formulas make out of it are the ones the paper prints.  The second is
the one that matters -- a transcription slip in a single radius is
invisible until a bond comes out 0.05 A too long.
"""

import numpy as np
import pytest

from xtal.core import elements as el
from xtal.ff.uff import params, terms

# Values quoted in Rappe et al. 1992 and reproduced by every
# implementation of UFF.  These are the load-bearing ones: get any of
# them wrong and organic geometries are wrong everywhere.
KNOWN_BOND_LENGTHS = [
    ("C_3", "C_3", 1.0, 1.5140),
    ("C_3", "H_", 1.0, 1.1094),
    ("C_R", "C_R", 1.5, 1.3793),
    ("N_3", "H_", 1.0, 1.0444),
    ("O_3", "H_", 1.0, 0.9903),
]
KNOWN_FORCE_CONSTANTS = [("C_3", "C_3", 699.6)]


def test_the_table_has_every_type_the_paper_lists():
    assert len(params.PARAMS) == 127
    assert "C_3" in params.PARAMS
    assert "Lw6+3" in params.PARAMS      # lawrencium, in 1992 spelling


def test_every_row_parsed_into_finite_numbers():
    for name, row in params.PARAMS.items():
        values = [row.r1, row.theta0, row.x1, row.d1, row.zeta,
                  row.z1, row.vi, row.uj, row.chi, row.hard,
                  row.radius]
        assert all(np.isfinite(values)), name
        assert row.r1 > 0 and row.x1 > 0, name
        assert 0 < row.theta0 <= 180.0, name


def test_every_type_belongs_to_an_element_the_application_knows():
    """A type whose element the rest of the code cannot parse is a
    type nothing can ever be assigned.

    ``Lw`` is the one exception, and a deliberate one: it is the
    paper's spelling of lawrencium, kept because the type name is a
    quotation, and reachable under ``Lr`` as well.
    """
    for element in params.BY_ELEMENT:
        assert el.is_symbol(element) or element == "Lw", element


def test_lawrencium_answers_to_its_modern_symbol():
    """The paper spells it Lw and IUPAC settled on Lr; a structure
    written today uses the second."""
    assert params.types_for("Lr") == ["Lw6+3"]


def test_the_type_name_states_the_coordination_it_expects():
    """The typer leans on this for every element it has no rule for,
    so it is a contract and not a coincidence."""
    assert params.get("Fe6+2").coordination == 6
    assert params.get("Fe3+2").coordination == 4
    assert params.get("Ni4+2").coordination == 4
    assert params.get("C_R").coordination is None
    assert params.get("Fe6+2").oxidation_state == 2
    assert params.get("W_6+6").element == "W"


def test_an_unknown_type_is_refused_by_name():
    with pytest.raises(KeyError, match="not a UFF atom type"):
        params.get("Xx9")


# ----------------------------------------------- the derived formulas

@pytest.mark.parametrize(("a", "b", "order", "expected"),
                         KNOWN_BOND_LENGTHS)
def test_natural_bond_lengths_match_the_paper(a, b, order, expected):
    assert terms.natural_bond_length(a, b, order) == pytest.approx(
        expected, abs=5e-4)


@pytest.mark.parametrize(("a", "b", "expected"),
                         KNOWN_FORCE_CONSTANTS)
def test_bond_force_constants_match_the_paper(a, b, expected):
    r0 = terms.natural_bond_length(a, b, 1.0)
    assert terms.bond_force_constant(a, b, r0) == pytest.approx(
        expected, rel=1e-3)


def test_the_electronegativity_correction_shortens_a_polar_bond():
    """The paper prints this term with a plus sign, which is a known
    slip: added, C-H comes out at 1.113 rather than the 1.109 the same
    paper quotes."""
    plain = 2 * params.get("C_3").r1
    assert terms.natural_bond_length("C_3", "C_3", 1.0) == \
        pytest.approx(plain)                # no correction, same atoms
    ch = terms.natural_bond_length("C_3", "H_", 1.0)
    assert ch < params.get("C_3").r1 + params.get("H_").r1


def test_a_higher_bond_order_gives_a_shorter_bond():
    single = terms.natural_bond_length("C_2", "C_2", 1.0)
    double = terms.natural_bond_length("C_2", "C_2", 2.0)
    triple = terms.natural_bond_length("C_1", "C_1", 3.0)
    assert triple < double < single


def test_hybridisation_is_read_off_the_type_name():
    assert terms.hybridisation("C_3") == "sp3"
    assert terms.hybridisation("C_2") == "sp2"
    assert terms.hybridisation("C_R") == "sp2"
    assert terms.hybridisation("C_1") == "sp"
    assert terms.hybridisation("Fe6+2") == ""       # not a hybrid


def test_the_angle_expansion_is_chosen_by_the_equilibrium_angle():
    assert terms.angle_form(180.0) == terms.LINEAR
    assert terms.angle_form(120.0) == terms.TRIGONAL
    assert terms.angle_form(90.0) == terms.SQUARE
    assert terms.angle_form(109.47) == terms.GENERAL


def test_torsion_barriers_follow_the_hybridisation_rules():
    """The barrier is decided by the two atoms in the middle: sp3
    against sp3 is threefold, sp2 against sp2 twofold, and anything
    involving a metal or an sp centre has no torsion at all."""
    barrier, n, _cos = terms.torsion_parameters("C_3", "C_3", 1.0,
                                                4, 4)
    assert barrier == pytest.approx(2.119)
    assert n == 3

    barrier, n, _cos = terms.torsion_parameters("C_2", "C_2", 1.0,
                                                3, 3)
    assert n == 2
    assert barrier == pytest.approx(10.0)

    assert terms.torsion_parameters("Ti6+4", "O_3", 1.0, 6, 2)[0] == 0
    assert terms.torsion_parameters("C_1", "C_3", 1.0, 2, 4)[0] == 0
    # A bond to a terminal atom has no dihedral to speak of.
    assert terms.torsion_parameters("C_3", "C_3", 1.0, 4, 1)[0] == 0


def test_two_group_16_centres_get_the_twofold_barrier():
    """What makes hydrogen peroxide and a disulfide come out skewed
    instead of planar."""
    barrier, n, cos0 = terms.torsion_parameters("O_3", "O_3", 1.0,
                                                2, 2)
    assert (barrier, n, cos0) == (pytest.approx(2.0), 2, -1.0)


def test_inversion_applies_to_sp2_centres_and_pyramidal_pnictogens():
    strength, c0, c1, c2 = terms.inversion_parameters("C_R", {"H_"})
    assert (strength, c0, c1, c2) == (pytest.approx(2.0), 1.0, -1.0,
                                      0.0)
    # A carbon carrying a carbonyl oxygen is held flat much harder.
    assert terms.inversion_parameters("C_2", {"O_2"})[0] > 15.0
    assert terms.inversion_parameters("P_3+3", {"C_3"})[0] > 0
    # Nothing else has one.
    assert terms.inversion_parameters("Ti6+4", {"O_3"})[0] == 0.0
    assert terms.inversion_parameters("C_3", {"H_"})[0] == 0.0


def test_van_der_waals_pairs_are_geometric_means():
    x, d = terms.vdw_pair("C_3", "H_")
    assert x == pytest.approx(np.sqrt(3.851 * 2.886))
    assert d == pytest.approx(np.sqrt(0.105 * 0.044))
    # Same atom: the mean is the value itself.
    assert terms.vdw_pair("C_3", "C_3") == (pytest.approx(3.851),
                                            pytest.approx(0.105))
