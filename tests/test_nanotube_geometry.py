"""A nanotube's geometry from (n,m): xtal.nanotube.geometry."""

import numpy as np
import pytest

from xtal.nanotube.geometry import (
    Chirality,
    bonding_clash,
    closest_contact,
    roll,
    shortest_bond,
)


@pytest.mark.parametrize("n, m, diameter, theta, period, atoms", [
    (10, 10, 13.56, 30.0, 2.460, 40),
    (10, 0, 7.83, 0.0, 4.260, 40),
    (6, 5, 7.47, 27.0, 40.64, 364),
])
def test_the_textbook_numbers_come_out(n, m, diameter, theta, period,
                                       atoms):
    """Dresselhaus 1995's d, theta, |T| and atoms a period at 1.42 A.
    If one drifts, every tube is built the wrong size or with the
    wrong repeat."""
    c = Chirality(n, m)
    assert c.diameter == pytest.approx(diameter, abs=0.01)
    assert c.theta == pytest.approx(theta, abs=0.01)
    assert c.t_length == pytest.approx(period, abs=0.01)
    assert c.atoms_per_period == atoms


@pytest.mark.parametrize("n, m", [(10, 10), (10, 0), (6, 5), (12, 3),
                                  (3, 7)])
def test_a_rolled_period_has_every_site_once_with_three_bonds(n, m):
    """Every site of the period once, on the cylinder, each with three
    bonds from an A site to a B site, each a chord no longer than the
    bond and within 2% of it.  A missing or doubled site, or a bond to
    the wrong neighbour, shows here."""
    c = Chirality(n, m)
    rolled = roll(c)
    assert len(rolled.cart) == c.atoms_per_period
    degree = np.bincount(rolled.bonds.ravel(),
                         minlength=len(rolled.cart))
    assert set(degree.tolist()) == {3}
    assert (rolled.sublattice[rolled.bonds[:, 0]] == 0).all()
    assert (rolled.sublattice[rolled.bonds[:, 1]] == 1).all()
    radius = np.hypot(rolled.cart[:, 0], rolled.cart[:, 1])
    assert np.allclose(radius, c.diameter / 2)
    assert 0.98 * c.bond < shortest_bond(c, rolled) <= c.bond + 1e-9
    shift = np.outer(rolled.images, [0.0, 0.0, c.t_length])
    lengths = np.linalg.norm(rolled.cart[rolled.bonds[:, 1]] + shift
                             - rolled.cart[rolled.bonds[:, 0]], axis=1)
    assert (lengths > 0.98 * c.bond).all()
    assert (lengths <= c.bond + 1e-9).all()


@pytest.mark.parametrize("n", [64, 128])
def test_a_wide_zigzag_tube_rolls(n):
    """(64,0) and (128,0) have sites at odd multiples of 1/128 of the
    period, which a decimal key rounds two ways, so roll could not find
    a neighbour and raised KeyError on a tube a user can ask for."""
    c = Chirality(n, 0)
    rolled = roll(c)
    assert len(rolled.cart) == c.atoms_per_period
    degree = np.bincount(rolled.bonds.ravel(),
                         minlength=len(rolled.cart))
    assert set(degree.tolist()) == {3}


def test_m_n_is_the_mirror_image_of_n_m():
    """(3,7) is (7,3) in the other hand: the same size and period, and
    angles from zigzag that sum to 60 degrees.  The builder lets
    either be asked for, so both must come out right."""
    right, left = Chirality(7, 3), Chirality(3, 7)
    assert left.diameter == pytest.approx(right.diameter)
    assert left.t_length == pytest.approx(right.t_length)
    assert left.atoms_per_period == right.atoms_per_period
    assert left.theta + right.theta == pytest.approx(60.0)


def test_a_bonding_clash_is_found_on_a_tube_too_thin_to_roll():
    """(2,0) brings atoms across the tube 1.57 A apart, inside C-C's
    1.68 A bonding distance; (10,10) brings none that close.  This is
    the geometry the builder refuses, because Recalculate bonds would
    bond them."""
    cutoffs = np.full((2, 2), 1.68)
    thin = Chirality(2, 0)
    clash = bonding_clash(thin, roll(thin), cutoffs)
    assert clash is not None
    assert clash[0] == pytest.approx(1.566, abs=0.005)
    assert clash[1] == pytest.approx(1.68)
    wide = Chirality(10, 10)
    assert bonding_clash(wide, roll(wide), cutoffs) is None


def test_a_wide_tube_s_closest_contact_is_nearly_the_sheet_s():
    """(10,10)'s closest unbonded pair is the flat sheet's second
    neighbour, a = 2.46 A, a little shortened by rolling.  It is the
    report's Closest contact row."""
    c = Chirality(10, 10)
    assert closest_contact(c, roll(c)) == pytest.approx(2.452, abs=0.01)
