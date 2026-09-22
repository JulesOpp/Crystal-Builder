"""UFF's stress, from the virial rather than by finite differences.

A cell relaxation used to take its stress as twelve extra energy
evaluations a step: 13x the cost of relaxing the atoms alone, which on
a framework of a thousand atoms is the difference between a scan that
finishes overnight and one that takes the weekend.  Every UFF term is
written in vectors between atoms, so the virial comes out of the pass
that makes the forces.

What would go wrong unseen is a sign or a missing vector in one term:
the relaxation still runs, converges, and lands on the wrong cell.  So
each term is held to the finite-difference stress of its own energy,
and the whole to the whole, at a geometry nothing is resting at.
"""

import numpy as np
import pytest

from xtal.core import p1
from xtal.ff import ENGINES, optimize
from xtal.io import FORMATS


def disturbed(structure, seed=0):
    """Positions and cell of the P1 cell, shaken and sheared so no
    term is at its minimum and no symmetry hides a wrong component."""
    rng = np.random.default_rng(seed)
    cell = p1.expand(structure)
    positions = cell.cart + rng.normal(scale=0.05, size=cell.cart.shape)
    matrix = (np.asarray(structure.lattice.matrix, dtype=float)
              @ (np.eye(3) + 0.01 * rng.normal(size=(3, 3))))
    return positions, matrix


def strained_derivative(energy, positions, matrix, h=1e-5):
    """(1/V) dE/d(strain), carrying the atoms with the cell: the
    definition ``numeric_stress`` uses, for a single term."""
    frac = positions @ np.linalg.inv(matrix)
    volume = abs(np.linalg.det(matrix))
    out = np.zeros((3, 3))
    for a in range(3):
        for b in range(a, 3):
            d = np.zeros((3, 3))
            d[a, b] += 0.5
            d[b, a] += 0.5
            up, down = matrix @ (np.eye(3) + h * d), \
                matrix @ (np.eye(3) - h * d)
            value = (energy(frac @ up, up) - energy(frac @ down, down)) \
                / (2 * h * volume)
            out[a, b] = out[b, a] = value
    return out


@pytest.mark.parametrize("name", ["rutile", "quartz", "dry_ice"])
def test_uff_analytic_stress_matches_central_differences(name, request):
    structure = request.getfixturevalue(name)
    calculator = ENGINES.build("uff", structure)
    positions, matrix = disturbed(structure)
    analytic = calculator.compute(positions, matrix).stress
    numeric = calculator.numeric_stress(positions, matrix, strain=1e-5)
    scale = max(np.abs(numeric).max(), 1e-3)
    assert np.allclose(analytic, numeric, atol=1e-6 * scale)


def test_uff_analytic_stress_matches_central_differences_on_mfu4l():
    """A real framework: every term type, and half a million vdW pairs
    that run through the blocked evaluation."""
    structure = FORMATS.read("resources/samples/MFU4l.cif")
    calculator = ENGINES.build("uff", structure)
    positions, matrix = disturbed(structure)
    analytic = calculator.compute(positions, matrix).stress
    numeric = calculator.numeric_stress(positions, matrix, strain=1e-5)
    assert np.allclose(analytic, numeric,
                       atol=1e-6 * np.abs(numeric).max())


def test_every_term_carries_its_own_share_of_the_stress():
    """Term by term on MFU-4l, which has bonds, angles, torsions and
    inversions: an error in one small term would hide inside the
    total's tolerance."""
    structure = FORMATS.read("resources/samples/MFU4l.cif")
    calculator = ENGINES.build("uff", structure)
    positions, matrix = disturbed(structure, seed=1)
    calculator.compute(positions, matrix)           # builds the pairs
    topology = calculator.topology
    terms = {"bond": topology.bonds, "angle": topology.angles,
             "torsion": topology.torsions,
             "inversion": topology.inversions,
             "van der Waals": calculator._vdw}
    volume = abs(np.linalg.det(matrix))
    for name, term in terms.items():
        assert len(term), name
        virial = np.zeros((3, 3))
        term.energy_and_gradient(positions, matrix, virial)
        analytic = 0.5 * (virial + virial.T) / volume
        numeric = strained_derivative(term.energy, positions, matrix)
        scale = max(np.abs(numeric).max(), 1e-4)
        assert np.allclose(analytic, numeric, atol=1e-5 * scale), name


def test_with_charges_on_the_stress_is_left_to_finite_differences(
        quartz):
    """The Ewald sum's reciprocal half is not a sum over interatomic
    vectors, so the virial would be missing it.  No stress is better
    than a wrong one: the optimiser then takes the numeric stress."""
    calculator = ENGINES.build("uff", quartz, coulomb=True,
                               charges="qeq")
    assert np.any(calculator.charges)
    assert not calculator.provides_stress
    positions, matrix = disturbed(quartz)
    assert calculator.compute(positions, matrix).stress is None


def test_a_uff_cell_relaxation_never_takes_the_stress_numerically(
        quartz, monkeypatch):
    """The whole point: a variable-cell step is one evaluation, not
    thirteen."""
    def refuse(*_args, **_kwargs):
        raise AssertionError("numeric stress was asked for")
    calculator = ENGINES.build("uff", quartz)
    monkeypatch.setattr(calculator, "numeric_stress", refuse)
    result = optimize.run(calculator, quartz, method="lbfgs",
                          relax_cell=True, max_steps=10)
    assert result.steps > 0
