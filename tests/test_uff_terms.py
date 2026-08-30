"""Every energy term, against a finite difference of its own energy.

This is the only test that can catch a wrong gradient.  An analytic
derivative that is subtly wrong still produces smooth, plausible
optimisations -- they just converge to the wrong geometry, or stop
short, and nothing about the run says so.  Comparing against a
numerical derivative of the same code's own energy catches it
immediately and cannot be fooled by a shared misunderstanding of the
physics.

Each term is exercised at a deliberately awkward geometry: nothing
sits at its minimum, nothing is symmetric, and the periodic ones carry
non-zero lattice translations.  A gradient that is only right at the
minimum is no use at all.
"""

import numpy as np
import pytest

from xtal.ff.uff import terms

MATRIX = np.array([[12.0, 0.0, 0.0],
                   [0.6, 11.0, 0.0],
                   [-0.4, 0.3, 13.0]])       # deliberately not cubic
# Four atoms in a general arrangement, plus two spectators.
POSITIONS = np.array([[0.00, 0.00, 0.00],
                      [1.50, 0.10, -0.20],
                      [2.05, 1.35, 0.35],
                      [3.40, 1.60, 0.40],
                      [5.90, 0.20, 0.10],
                      [0.30, 4.00, 0.20]])

ZERO = np.zeros((1, 3))
ONE = np.zeros((2, 3))


def numerical_gradient(term, positions, h=1e-6):
    out = np.zeros_like(positions)
    for atom in range(len(positions)):
        for axis in range(3):
            up = positions.copy()
            up[atom, axis] += h
            down = positions.copy()
            down[atom, axis] -= h
            out[atom, axis] = (term.energy(up, MATRIX)
                               - term.energy(down, MATRIX)) / (2 * h)
    return out


def assert_gradient(term, positions=POSITIONS):
    energy, analytic = term.energy_and_gradient(positions, MATRIX)
    numeric = numerical_gradient(term, positions)
    scale = max(1.0, float(np.abs(numeric).max()))
    assert np.abs(analytic - numeric).max() / scale < 1e-6
    # A gradient that does not sum to zero is a term that pushes the
    # whole crystal in one direction, which no internal coordinate can
    # do.
    assert np.abs(analytic.sum(axis=0)).max() < 1e-6 * scale
    return energy


def test_bond_gradient():
    assert_gradient(terms.BondTerm(
        np.array([0, 1]), np.array([1, 2]), ONE,
        np.array([1.5, 1.2]), np.array([700.0, 500.0])))


def test_bond_across_a_periodic_boundary():
    """The translation has to be differentiated through, not around:
    it moves where the partner is, and the force on both ends with
    it."""
    assert_gradient(terms.BondTerm(
        np.array([0]), np.array([1]), np.array([[1.0, 0.0, -1.0]]),
        np.array([1.5]), np.array([700.0])))


@pytest.mark.parametrize("form", [terms.GENERAL, terms.LINEAR,
                                  terms.TRIGONAL, terms.SQUARE])
def test_angle_gradient_for_every_expansion(form):
    assert_gradient(terms.AngleTerm(
        np.array([0]), np.array([1]), np.array([2]), ZERO, ZERO,
        np.array([100.0]), np.array([1.2]), np.array([-0.9]),
        np.array([0.3]), np.array([form])))


def test_a_linear_angle_is_smooth_through_180_degrees():
    """Written in the angle rather than its cosine, this term has a
    1/sin singularity exactly where a nitrile or a carbon dioxide
    sits."""
    term = terms.AngleTerm(
        np.array([0]), np.array([1]), np.array([2]), ZERO, ZERO,
        np.array([50.0]), np.array([0.0]), np.array([0.0]),
        np.array([0.0]), np.array([terms.LINEAR]))
    straight = np.array([[-1.2, 0, 0], [0, 0, 0], [1.2, 0, 0],
                         [9, 9, 9], [8, 8, 8], [7, 7, 7]])
    energy, gradient = term.energy_and_gradient(straight, MATRIX)
    assert energy == pytest.approx(0.0, abs=1e-12)
    assert np.all(np.isfinite(gradient))
    # And just off it, the energy rises and the gradient is finite.
    bent = straight.copy()
    bent[2] = [1.2 * np.cos(0.01), 1.2 * np.sin(0.01), 0]
    assert term.energy(bent, MATRIX) > 0
    assert_gradient(term, bent)


@pytest.mark.parametrize("periodicity", [2, 3, 6])
def test_torsion_gradient_for_every_periodicity(periodicity):
    assert_gradient(terms.TorsionTerm(
        np.array([0]), np.array([1]), np.array([2]), np.array([3]),
        ZERO, ZERO, ZERO, np.array([2.5]),
        np.array([periodicity]), np.array([-1.0])))


def test_torsion_across_periodic_boundaries():
    assert_gradient(terms.TorsionTerm(
        np.array([0]), np.array([1]), np.array([2]), np.array([3]),
        np.array([[1.0, 0, 0]]), np.array([[0, -1.0, 0]]),
        np.array([[0, -1.0, 1.0]]), np.array([1.5]),
        np.array([3]), np.array([-1.0])))


def test_a_collinear_torsion_gives_no_force_instead_of_a_nan():
    """Three atoms in a line leave the dihedral undefined.  Dropping
    the term is right; a NaN would end the optimisation and take the
    structure with it."""
    term = terms.TorsionTerm(
        np.array([0]), np.array([1]), np.array([2]), np.array([3]),
        ZERO, ZERO, ZERO, np.array([2.0]), np.array([3]),
        np.array([-1.0]))
    collinear = np.array([[0, 0, 0], [1.0, 0, 0], [2.0, 0, 0],
                          [3.0, 1.0, 0], [9, 9, 9], [8, 8, 8]],
                         dtype=float)
    energy, gradient = term.energy_and_gradient(collinear, MATRIX)
    assert energy == 0.0
    assert np.all(np.isfinite(gradient))
    assert np.abs(gradient).max() == 0.0


@pytest.mark.parametrize(("c0", "c1", "c2"),
                         [(1.0, -1.0, 0.0),       # sp2
                          (1.019, -0.388, 1.0)])  # pyramidal group 15
def test_inversion_gradient(c0, c1, c2):
    assert_gradient(terms.InversionTerm(
        np.array([0]), np.array([1]), np.array([2]), np.array([3]),
        ZERO, ZERO, ZERO, np.array([2.0]), np.array([c0]),
        np.array([c1]), np.array([c2])))


def test_a_flat_sp2_centre_costs_nothing():
    term = terms.InversionTerm(
        np.array([0]), np.array([1]), np.array([2]), np.array([3]),
        ZERO, ZERO, ZERO, np.array([2.0]), np.array([1.0]),
        np.array([-1.0]), np.array([0.0]))
    flat = np.array([[0, 0, 0], [1.4, 0, 0], [-0.7, 1.2, 0],
                     [-0.7, -1.2, 0], [9, 9, 9], [8, 8, 8]],
                    dtype=float)
    assert term.energy(flat, MATRIX) == pytest.approx(0.0, abs=1e-12)
    lifted = flat.copy()
    lifted[3, 2] = 0.5
    assert term.energy(lifted, MATRIX) > 0.01


def test_van_der_waals_gradient():
    assert_gradient(terms.VanDerWaalsTerm(
        np.array([0, 1]), np.array([3, 4]), ONE,
        np.array([3.8, 3.5]), np.array([0.1, 0.06])))


def test_van_der_waals_is_zero_at_its_own_minimum_separation():
    """The 12-6 well sits at x, not at 2^(1/6) x -- UFF writes it in
    the well position, not the collision diameter."""
    term = terms.VanDerWaalsTerm(
        np.array([0]), np.array([1]), ZERO, np.array([4.0]),
        np.array([0.2]))
    at_minimum = np.array([[0, 0, 0], [4.0, 0, 0], [9, 9, 9],
                           [8, 8, 8], [7, 7, 7], [6, 6, 6]],
                          dtype=float)
    energy, gradient = term.energy_and_gradient(at_minimum, MATRIX)
    assert energy == pytest.approx(-0.2)
    assert np.abs(gradient).max() < 1e-9


def test_the_cutoff_shift_moves_the_energy_and_not_the_force():
    """Rebuilding a pair list must not step the energy, or an
    optimiser reads the step as progress and stops."""
    plain = terms.VanDerWaalsTerm(
        np.array([0]), np.array([4]), ZERO, np.array([3.8]),
        np.array([0.1]))
    shifted = terms.VanDerWaalsTerm(
        np.array([0]), np.array([4]), ZERO, np.array([3.8]),
        np.array([0.1]), shift_energy=np.array([-0.001]))
    e1, g1 = plain.energy_and_gradient(POSITIONS, MATRIX)
    e2, g2 = shifted.energy_and_gradient(POSITIONS, MATRIX)
    assert e2 == pytest.approx(e1 + 0.001)
    assert np.allclose(g1, g2)


def test_coulomb_gradient():
    assert_gradient(terms.CoulombTerm(
        np.array([0, 1]), np.array([3, 4]), ONE,
        np.array([-0.3, 0.2])))


def test_an_empty_term_is_zero_and_not_an_error():
    """Structures with no torsions -- every metal oxide -- go through
    here on every step."""
    empty = terms.TorsionTerm(
        np.zeros(0, int), np.zeros(0, int), np.zeros(0, int),
        np.zeros(0, int), np.zeros((0, 3)), np.zeros((0, 3)),
        np.zeros((0, 3)), np.zeros(0), np.zeros(0, int), np.zeros(0))
    energy, gradient = empty.energy_and_gradient(POSITIONS, MATRIX)
    assert energy == 0.0
    assert gradient.shape == POSITIONS.shape
    assert not gradient.any()


def test_repeated_atoms_accumulate_rather_than_overwrite():
    """Every atom appears in many terms; fancy-index assignment would
    keep only the last one, and the gradient would be quietly too
    small."""
    both = terms.BondTerm(
        np.array([0, 0]), np.array([1, 2]), ONE,
        np.array([1.0, 1.0]), np.array([100.0, 100.0]))
    first = terms.BondTerm(
        np.array([0]), np.array([1]), ZERO, np.array([1.0]),
        np.array([100.0]))
    second = terms.BondTerm(
        np.array([0]), np.array([2]), ZERO, np.array([1.0]),
        np.array([100.0]))
    _e, g = both.energy_and_gradient(POSITIONS, MATRIX)
    _e1, g1 = first.energy_and_gradient(POSITIONS, MATRIX)
    _e2, g2 = second.energy_and_gradient(POSITIONS, MATRIX)
    assert np.allclose(g, g1 + g2)
