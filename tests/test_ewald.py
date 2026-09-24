"""Periodic electrostatics.

A lattice sum of 1/r is conditionally convergent, so "it returned a
number" proves nothing at all -- a truncated sum returns a number too,
and a different one for every cutoff.  The tests that matter are
therefore that the answer is a *known* one (the Madelung constant of
rock salt, to six figures) and that it does not depend on where the
work was split between real and reciprocal space.
"""

import numpy as np
import pytest

from xtal import Lattice
from xtal.core import neighbors
from xtal.ff import ewald

# Rock salt, in the conventional cell: four formula units.
SALT_A = 5.6402
SALT_FRAC = np.array([[0, 0, 0], [.5, .5, 0], [.5, 0, .5],
                      [0, .5, .5],
                      [.5, .5, .5], [0, 0, .5], [0, .5, 0],
                      [.5, 0, 0]])
SALT_CHARGES = np.array([1.0] * 4 + [-1.0] * 4)
# Madelung constant of the rock-salt lattice.
MADELUNG_NACL = 1.7475645946


def salt_pairs(cutoff, lattice):
    pairs = neighbors.neighbor_pairs(SALT_FRAC, lattice, cutoff)
    return pairs.i, pairs.j, pairs.image


def test_the_madelung_constant_of_rock_salt():
    """The one number in this module that can be looked up."""
    lattice = Lattice.cubic(SALT_A)
    conf = ewald.setup(lattice.matrix, real_cutoff=12.0,
                       accuracy=1e-10)
    energy = ewald.madelung(lattice.to_cart(SALT_FRAC),
                            lattice.matrix, SALT_CHARGES,
                            salt_pairs(12.0, lattice), setup_=conf)
    # Four ion pairs, each -alpha e^2 / r with r = a/2.
    constant = -energy * (SALT_A / 2) / 4
    assert constant == pytest.approx(MADELUNG_NACL, abs=1e-6)


@pytest.mark.parametrize("cutoff", [8.0, 10.0, 14.0])
def test_the_answer_does_not_depend_on_where_the_split_is_made(cutoff):
    """A shorter real-space cutoff means a wider screening and more
    reciprocal vectors.  If those two do not compensate exactly, the
    implementation is wrong however plausible its numbers look."""
    lattice = Lattice.cubic(SALT_A)
    conf = ewald.setup(lattice.matrix, real_cutoff=cutoff,
                       accuracy=1e-10)
    energy = ewald.madelung(lattice.to_cart(SALT_FRAC),
                            lattice.matrix, SALT_CHARGES,
                            salt_pairs(cutoff, lattice), setup_=conf)
    constant = -energy * (SALT_A / 2) / 4
    assert constant == pytest.approx(MADELUNG_NACL, abs=1e-6)


def test_the_gradient_is_the_gradient():
    rng = np.random.default_rng(3)
    lattice = Lattice.from_parameters(5.64, 6.1, 5.2, 90, 97, 90)
    frac = np.mod(rng.random((6, 3)), 1.0)
    charges = np.array([1.0, 1.0, 1.0, -1.0, -1.0, -1.0])
    conf = ewald.setup(lattice.matrix, real_cutoff=10.0,
                       accuracy=1e-10)
    pairs = neighbors.neighbor_pairs(frac, lattice, 10.0)
    listed = (pairs.i, pairs.j, pairs.image)
    positions = lattice.to_cart(frac)

    _energy, analytic = ewald.energy_and_gradient(
        positions, lattice.matrix, charges, listed, setup_=conf)
    numeric = np.zeros_like(positions)
    h = 1e-6
    for atom in range(len(positions)):
        for axis in range(3):
            up = positions.copy()
            up[atom, axis] += h
            down = positions.copy()
            down[atom, axis] -= h
            numeric[atom, axis] = (
                ewald.energy_and_gradient(up, lattice.matrix, charges,
                                          listed, setup_=conf)[0]
                - ewald.energy_and_gradient(down, lattice.matrix,
                                            charges, listed,
                                            setup_=conf)[0]) / (2 * h)
    assert np.abs(analytic - numeric).max() / np.abs(
        numeric).max() < 1e-6


def test_excluding_a_pair_removes_exactly_its_bare_interaction():
    """A bonded pair is described by the bond term, so its Coulomb
    interaction has to come out -- all of it, including the part the
    reciprocal sum contributed, which is the half that is easy to
    forget."""
    from xtal.ff.uff.params import COULOMB

    lattice = Lattice.cubic(SALT_A)
    conf = ewald.setup(lattice.matrix, real_cutoff=12.0,
                       accuracy=1e-10)
    positions = lattice.to_cart(SALT_FRAC)
    pairs = neighbors.neighbor_pairs(SALT_FRAC, lattice, 12.0)

    drop = np.zeros(len(pairs.i), dtype=bool)
    for k in range(len(pairs.i)):
        if (int(pairs.i[k]), int(pairs.j[k])) == (0, 4) and \
                tuple(pairs.image[k]) == (0, 0, 0):
            drop[k] = True
    assert drop.any()
    keep = ~drop

    whole, _g = ewald.energy_and_gradient(
        positions, lattice.matrix, SALT_CHARGES,
        (pairs.i, pairs.j, pairs.image), setup_=conf)
    without, _g = ewald.energy_and_gradient(
        positions, lattice.matrix, SALT_CHARGES,
        (pairs.i[keep], pairs.j[keep], pairs.image[keep]),
        excluded=(pairs.i[drop], pairs.j[drop], pairs.image[drop]),
        setup_=conf)

    separation = np.linalg.norm(positions[4] - positions[0])
    bare = COULOMB * SALT_CHARGES[0] * SALT_CHARGES[4] / separation
    assert whole - without == pytest.approx(bare, rel=1e-9)


def test_a_cell_with_a_net_charge_gets_a_finite_answer():
    """An infinite one would be the honest answer for a charged
    lattice; a neutralising background is the useful one, and the
    calculator says that is what it did."""
    lattice = Lattice.cubic(SALT_A)
    charges = SALT_CHARGES.copy()
    charges[7] = 0.0
    energy, _g = ewald.energy_and_gradient(
        lattice.to_cart(SALT_FRAC), lattice.matrix, charges,
        salt_pairs(12.0, lattice))
    assert np.isfinite(energy)


def test_a_cell_with_no_volume_is_refused():
    with pytest.raises(ValueError, match="no volume"):
        ewald.setup(np.zeros((3, 3)))


def test_a_tighter_accuracy_asks_for_more_reciprocal_vectors():
    matrix = Lattice.cubic(SALT_A).matrix
    loose = ewald.setup(matrix, accuracy=1e-4)
    tight = ewald.setup(matrix, accuracy=1e-10)
    assert tight.n_k > loose.n_k


# ------------------------------------------------ the pair matrix

def test_the_pair_matrix_gives_rock_salts_madelung_constant():
    """The matrix is what EQeq solves with; half of q M q has to be
    the same lattice sum the energy is."""
    lattice = Lattice.cubic(SALT_A)
    conf = ewald.setup(lattice.matrix, real_cutoff=12.0,
                       accuracy=1e-10)
    m = ewald.pair_matrix(lattice.to_cart(SALT_FRAC), lattice.matrix,
                          conf)
    energy = 0.5 * SALT_CHARGES @ m @ SALT_CHARGES
    assert -energy * (SALT_A / 2) / 4 == pytest.approx(
        MADELUNG_NACL, abs=1e-6)


def test_the_pair_matrix_is_the_energy_the_ewald_sum_gives():
    """Any charges, a skewed cell and a net charge: a matrix that
    agrees only for neutral salt could still be missing the
    background or one of the reciprocal vectors' partners."""
    from xtal.ff.uff.params import COULOMB

    rng = np.random.default_rng(7)
    lattice = Lattice.from_parameters(5.64, 6.1, 5.2, 80, 97, 110)
    frac = rng.random((6, 3))
    charges = rng.normal(size=6)
    conf = ewald.setup(lattice.matrix, real_cutoff=10.0,
                       accuracy=1e-10)
    pairs = neighbors.neighbor_pairs(frac, lattice, 10.0)
    energy, _grad = ewald.energy_and_gradient(
        lattice.to_cart(frac), lattice.matrix, charges,
        (pairs.i, pairs.j, pairs.image), setup_=conf)

    m = ewald.pair_matrix(lattice.to_cart(frac), lattice.matrix, conf)
    assert COULOMB / 2 * charges @ m @ charges == pytest.approx(
        energy, rel=1e-9)


def test_no_entry_of_the_pair_matrix_depends_on_the_split():
    """The energy of a neutral cell would not notice a diagonal that
    shifts with alpha; EQeq's hardness sits on that diagonal and
    would."""
    rng = np.random.default_rng(11)
    lattice = Lattice.from_parameters(6.0, 7.0, 8.0, 90, 100, 90)
    cart = lattice.to_cart(rng.random((5, 3)))
    matrices = [
        ewald.pair_matrix(cart, lattice.matrix, ewald.setup(
            lattice.matrix, real_cutoff=cutoff, accuracy=1e-10))
        for cutoff in (8.0, 14.0)]
    np.testing.assert_allclose(*matrices, atol=1e-8)
