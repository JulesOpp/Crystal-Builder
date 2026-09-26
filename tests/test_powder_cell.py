"""Which of a cell's six numbers a space group leaves free."""

from __future__ import annotations

import pytest

from xtal.powder.cell import complete, constraints, free_names


def test_a_cubic_cell_is_one_length_and_a_monoclinic_one_four_numbers():
    """What the Pawley form offers: a cubic group takes one length, a
    monoclinic one three lengths and the angle about its unique axis."""
    assert free_names("Fm-3m") == ("a",)
    assert free_names("P42/mnm") == ("a", "c")
    assert free_names("P6_3/mmc") == ("a", "c")
    assert free_names("P3221") == ("a", "c")
    assert free_names("Pnma") == ("a", "b", "c")
    assert free_names("P21/c") == ("a", "b", "c", "beta")
    assert free_names("P-1") == ("a", "b", "c", "alpha", "beta",
                                 "gamma")


def test_the_unique_angle_follows_the_monoclinic_setting():
    """P 1 1 21 has its two-fold along c, so gamma is the free angle;
    offering beta would let a person type a cell RietX then ties."""
    assert free_names("P 1 1 21") == ("a", "b", "c", "gamma")
    assert free_names("A 1 2/m 1") == ("a", "b", "c", "beta")


def test_a_rhombohedral_cell_on_its_own_axes_is_a_length_and_an_angle():
    assert free_names("R -3 :R") == ("a", "alpha")
    assert free_names("R-3") == ("a", "c")          # hexagonal axes


def test_a_group_nobody_knows_leaves_all_six_free():
    """Never a refusal: the form still takes a cell while the group is
    half typed."""
    assert constraints("") == (None,) * 6
    assert constraints("Q42") == (None,) * 6


def test_the_tied_numbers_are_derived_over_whatever_was_typed():
    """b = 4.60 typed for a tetragonal cell is not the cell a fit
    would run on; the group's b is a."""
    cell = complete((4.59, 4.60, 2.96, 91.0, 90.0, 89.0), "P42/mnm")
    assert cell == pytest.approx((4.59, 4.59, 2.96, 90, 90, 90))
    assert complete((5.0, 1, 1, 90, 90, 90), "Fm-3m") == \
        pytest.approx((5.0, 5.0, 5.0, 90, 90, 90))
    assert complete((4.9, 1, 5.4, 1, 1, 1), "P3221")[3:] == \
        pytest.approx((90, 90, 120))
    assert complete((7.0, 1, 1, 80.0, 1, 1), "R -3 :R") == \
        pytest.approx((7, 7, 7, 80, 80, 80))
