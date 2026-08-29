"""Element reference data and symbol parsing."""

import pytest

from xtal.core import elements as E


def test_symbol_parsing_handles_real_file_junk():
    assert E.parse_symbol("Fe") == "Fe"
    assert E.parse_symbol("fe") == "Fe"
    assert E.parse_symbol("FE") == "Fe"
    assert E.parse_symbol("Fe2+") == "Fe"      # oxidation state
    assert E.parse_symbol("O1-") == "O"
    assert E.parse_symbol("Fe1") == "Fe"       # CIF label
    assert E.parse_symbol("O_23") == "O"
    assert E.parse_symbol("  C  ") == "C"


def test_two_letter_reading_wins_over_one_letter():
    assert E.parse_symbol("Co") == "Co"        # cobalt, not C + o
    assert E.parse_symbol("C1") == "C"         # carbon, not Cl
    assert E.parse_symbol("Ow") == "O"         # water oxygen label


@pytest.mark.parametrize("bad", ["", "   ", "1", "Qq", "42"])
def test_bad_symbols_raise(bad):
    with pytest.raises(ValueError):
        E.parse_symbol(bad)


def test_element_record():
    fe = E.element("Fe")
    assert fe.symbol == "Fe"
    assert fe.z == 26
    assert fe.name == "Iron"
    assert fe.is_metal
    assert fe.mass == pytest.approx(55.845, abs=1e-3)
    assert fe.covalent_radius == pytest.approx(1.32, abs=0.01)


def test_all_118_elements_have_colour_mass_and_radii():
    syms = E.all_symbols()
    assert len(syms) == 118
    assert syms[0] == "H" and syms[-1] == "Og"
    for s in syms:
        el = E.element(s)
        assert 1 <= el.z <= 118
        assert el.mass > 0
        assert el.covalent_radius > 0
        assert el.vdw_radius > 0
        assert len(el.color) == 3
        assert all(0 <= c <= 255 for c in el.color)
        assert el.name and el.name[0].isupper()


def test_atomic_number_round_trip():
    for z in range(1, 119):
        assert E.atomic_number(E.symbol_from_z(z)) == z


def test_vdw_radii_are_sane_for_space_filling():
    # Bondi values for the common non-metals ...
    assert E.vdw_radius("C") == pytest.approx(1.70, abs=0.01)
    assert E.vdw_radius("O") == pytest.approx(1.52, abs=0.01)
    # ... and metals get Alvarez values, not a metallic radius that
    # would draw Fe smaller than the O it is bonded to.
    assert E.vdw_radius("Fe") > E.vdw_radius("O")
    assert E.covalent_radius("Fe") > E.covalent_radius("O")


def test_unknown_colour_falls_back_instead_of_raising():
    assert E.color("Qq") == E.DEFAULT_COLOR
    with pytest.raises(ValueError):
        E.element("Qq")
