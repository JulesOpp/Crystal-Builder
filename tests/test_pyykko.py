"""Pyykkö's covalent radii and the aromatic bond: xtal.core.pyykko."""

import pytest

from xtal.core import elements, pyykko


def test_the_table_has_every_element_in_order_with_a_single_radius():
    """118 symbols in atomic-number order, each with a single-bond
    radius, and the double-bond table over the same symbols.  A
    missing element would fail a nanotube of it with a KeyError, not a
    sentence."""
    assert list(pyykko.SINGLE) == elements.all_symbols()
    assert list(pyykko.DOUBLE) == elements.all_symbols()
    assert len(pyykko.SINGLE) == 118
    assert all(isinstance(r, int) for r in pyykko.SINGLE.values())


@pytest.mark.parametrize("symbol, single, double", [
    ("H", 32, None), ("B", 85, 78), ("C", 75, 67), ("N", 71, 60),
    ("Li", 133, 124), ("O", 63, 57), ("F", 64, 59), ("Al", 126, 113),
    ("Si", 116, 107), ("P", 111, 102), ("S", 103, 94), ("Fe", 116, 109),
    ("Ga", 124, 117), ("As", 121, 114), ("Mo", 138, 121),
    ("W", 137, 120), ("Au", 124, 121), ("U", 170, 134),
    ("Fm", 167, None), ("Og", 157, None),
])
def test_the_radii_are_pyykko_s_as_published(symbol, single, double):
    """Spot checks against Pyykkö and Atsumi's tables, in pm, copied
    from the table Julius linked.  A digit slipped in the literal
    table moves every tube of that element."""
    assert pyykko.SINGLE[symbol] == single
    assert pyykko.DOUBLE[symbol] == double


def test_the_aromatic_bond_is_julius_s_142_for_carbon_and_147_for_bn():
    """Each atom's radius is the mean of its single and double radii,
    and the bond their sum: 1.42 A exactly for C-C, his old default,
    and 1.47 A for B-N.  Carbon must come out exactly, or the
    refusals that quote "of 1.42 A" change."""
    assert pyykko.aromatic_bond("C", "C") == 1.42
    assert pyykko.aromatic_bond("B", "N") == pytest.approx(1.47)
    assert pyykko.aromatic_radius("C") == pytest.approx(0.71)


def test_an_element_with_no_double_radius_takes_its_single_one():
    """Pyykkö gives hydrogen no double-bond radius, so its aromatic
    radius is its single-bond one, 0.32 A.  Averaging with None is a
    TypeError."""
    assert pyykko.aromatic_radius("H") == pytest.approx(0.32)
    assert pyykko.aromatic_bond("H", "C") == pytest.approx(1.03)
