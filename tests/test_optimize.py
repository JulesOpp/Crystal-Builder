"""Geometry optimisation, and the symmetry it has to preserve.

The interesting tests here are not "did the energy go down".  They are
about the degrees of freedom: an optimisation of a structure in
P4_2/mnm must come out in P4_2/mnm, with the titanium still exactly at
the origin and the oxygen still on the diagonal it is confined to.
Getting that wrong does not produce a visibly broken structure -- it
produces one that has quietly lost its symmetry, in the fifth decimal
place, and that the next symmetry detection will report as P1.
"""

import numpy as np
import pytest

from tests.conftest_ff import benzene, ethane, water
from xtal import Structure
from xtal.core import p1, symmetry
from xtal.ff import ENGINES, optimize

# UFF's own equilibrium water: the geometry it must relax to, whatever
# it starts from.
UFF_OH = 0.9903
UFF_HOH = 104.51


def relax(structure, method="lbfgs", **kwargs):
    calculator = ENGINES.build("uff", structure)
    kwargs.setdefault("max_steps", 400)
    kwargs.setdefault("force_tolerance", 1e-4)
    return optimize.run(calculator, structure, method=method,
                        **kwargs)


def moved(structure, result) -> Structure:
    """The structure the optimiser produced."""
    out = structure.copy()
    for site, frac in zip(out.sites, result.frac, strict=True):
        site.frac = frac
    out.touch()
    return out


def geometry(structure, result):
    cart = result.frac @ structure.lattice.matrix
    return cart


# ----------------------------------------------------- does it work

@pytest.mark.parametrize("method", ["fire", "lbfgs"])
def test_water_relaxes_to_the_geometry_uff_asks_for(method):
    """Both optimisers, from a deliberately wrong start, to the same
    answer -- which is the check that neither is quietly stopping
    somewhere convenient."""
    result = relax(water(oh=1.10, angle=88.0), method=method)
    assert result.converged
    cart = geometry(water(), result)
    oh1 = np.linalg.norm(cart[1] - cart[0])
    oh2 = np.linalg.norm(cart[2] - cart[0])
    angle = np.degrees(np.arccos(
        (cart[1] - cart[0]) @ (cart[2] - cart[0]) / (oh1 * oh2)))
    assert oh1 == pytest.approx(UFF_OH, abs=1e-3)
    assert oh2 == pytest.approx(UFF_OH, abs=1e-3)
    assert angle == pytest.approx(UFF_HOH, abs=0.05)


EVERY_METHOD = sorted(optimize.METHODS)


@pytest.mark.parametrize("method", EVERY_METHOD)
def test_every_optimiser_reaches_the_same_water(method):
    """Materials Studio's set -- steepest descent, conjugate gradient,
    quasi-Newton, ABNR, and the cascade through them -- is offered
    beside FIRE and L-BFGS.  An optimiser that stopped somewhere
    convenient would come out a different molecule."""
    result = relax(water(oh=1.10, angle=88.0), method=method,
                   max_steps=3000, force_tolerance=1e-3)
    assert result.converged, result.message
    cart = geometry(water(), result)
    oh = np.linalg.norm(cart[1] - cart[0])
    assert oh == pytest.approx(UFF_OH, abs=2e-3)


@pytest.mark.parametrize("method", EVERY_METHOD)
def test_every_optimiser_keeps_rutile_on_its_special_positions(method,
                                                               rutile):
    """The projection is applied to the gradient, and every direction
    here is built out of gradients -- so a method that mixed in a
    vector from anywhere else would walk titanium off the origin."""
    result = relax(rutile, method=method, max_steps=300,
                   force_tolerance=1e-3)
    assert np.allclose(result.frac[0], [0.0, 0.0, 0.0], atol=1e-12)
    x, y, z = result.frac[1]
    assert x == pytest.approx(y, abs=1e-12)
    assert z == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("method", EVERY_METHOD)
def test_every_optimiser_leaves_a_frozen_site_alone(method):
    structure = water(oh=1.15, angle=95.0)
    result = relax(structure, method=method, frozen=[0], max_steps=50,
                   force_tolerance=1e-4)
    assert np.allclose(result.frac[0], structure.sites[0].frac,
                       atol=1e-12)


def test_the_cascade_goes_through_its_stages_in_order():
    """Steepest descent while the forces are large, ABNR through the
    middle, quasi-Newton to finish -- and never back."""
    structure = water(oh=0.75, angle=80.0)
    calculator = ENGINES.build("uff", structure)
    stages = [step.method for step in optimize.steps(
        calculator, structure, "smart", max_steps=500,
        force_tolerance=1e-4)]
    order = [s for k, s in enumerate(stages)
             if k == 0 or s != stages[k - 1]]
    assert order == ["steepest descent", "ABNR", "quasi-Newton"]


def test_quasi_newton_refuses_a_matrix_it_should_not_hold():
    from xtal.ff.api import CalculatorError
    with pytest.raises(CalculatorError, match="L-BFGS"):
        optimize._QuasiNewton(optimize.QUASI_NEWTON_MAX_VARIABLES + 1)


def test_a_line_search_with_nowhere_to_go_says_so():
    """L-BFGS used to return silently when its search gave up, which
    the panel reported as a run that had simply stopped -- and the
    only advice it had was to run it again, which gave up again."""
    from xtal.ff.api import Calculator, Result

    class Stuck(Calculator):
        """A gradient that points somewhere the energy never falls."""
        name = "stuck"
        provides_forces = True

        @property
        def n_atoms(self):
            return 3

        def compute(self, positions, matrix):
            forces = np.ones_like(positions)
            return Result(0.0, forces, {})

    structure = water()
    result = optimize.run(Stuck(), structure, "lbfgs", max_steps=10,
                          force_tolerance=1e-6)
    assert not result.converged
    assert result.message.startswith("the line search")


def test_the_energy_falls_and_the_force_with_it():
    result = relax(water(oh=1.15, angle=95.0))
    assert result.energy < result.initial_energy
    energies = [e for _s, e, _f in result.history]
    assert energies[-1] < energies[0]
    assert result.max_force < 1e-4


def test_lbfgs_gets_there_in_fewer_steps_than_fire():
    """Not a law of nature, but it is why both are offered: L-BFGS for
    speed near a minimum, FIRE for robustness far from one."""
    start = water(oh=1.10, angle=88.0)
    assert relax(start, "lbfgs").steps < relax(start, "fire").steps


def test_an_already_relaxed_structure_converges_immediately():
    ideal = relax(water())
    again = relax(moved(water(), ideal))
    assert again.converged
    assert again.steps == 0


def test_benzene_stays_flat():
    """It starts at a minimum of the torsion and inversion terms, and
    an optimiser that pushed it out of the plane would be describing
    an sp3 benzene."""
    result = relax(benzene(), force_tolerance=1e-3)
    cart = geometry(benzene(), result)
    assert np.abs(cart[:, 2]).max() < 1e-4


# ------------------------------------------------------- the symmetry

def test_rutile_keeps_its_space_group(rutile):
    result = relax(rutile, force_tolerance=1e-3)
    assert symmetry.detect(moved(rutile, result),
                           symprec=1e-6).space_group.short_name \
        == rutile.space_group.short_name


def test_an_atom_on_a_special_position_stays_on_it(rutile):
    """Rutile's titanium is at the origin, and its site symmetry
    leaves it no direction at all to move in.  The projector has to
    zero its gradient completely; a residual of 1e-6 per step becomes
    a visibly displaced atom over two hundred of them."""
    result = relax(rutile, force_tolerance=1e-3)
    assert np.allclose(result.frac[0], [0.0, 0.0, 0.0], atol=1e-12)


def test_an_atom_relaxes_only_along_the_freedom_it_has(rutile):
    """Rutile's oxygen is on 4f, (x, x, 0): it may move along the
    diagonal and nowhere else."""
    result = relax(rutile, force_tolerance=1e-3)
    x, y, z = result.frac[1]
    assert x == pytest.approx(y, abs=1e-12)
    assert z == pytest.approx(0.0, abs=1e-12)
    assert x != pytest.approx(rutile.sites[1].frac[0], abs=1e-6)


def test_quartz_keeps_the_freedom_of_its_special_position(quartz):
    """Silicon sits on 3a, (x, 0, 2/3)."""
    result = relax(quartz, force_tolerance=1e-3)
    assert result.frac[0][1] == pytest.approx(0.0, abs=1e-12)
    assert result.frac[0][2] == pytest.approx(2 / 3, abs=1e-12)
    assert symmetry.detect(moved(quartz, result),
                           symprec=1e-6).space_group.short_name \
        == "P3221"


def test_the_cell_keeps_the_same_number_of_atoms(halite):
    """A relaxation that broke symmetry would show up here first: the
    P1 expansion of a structure that has left its group has a
    different atom count."""
    before = p1.expand(halite).n_atoms
    result = relax(halite, force_tolerance=1e-2, max_steps=20)
    assert p1.expand(moved(halite, result)).n_atoms == before


def test_a_p1_structure_relaxes_every_atom_independently():
    """The general case falls out of the same code with the identity
    for a projector."""
    result = relax(ethane(twist=30.0), force_tolerance=1e-3)
    assert result.converged
    assert len(result.frac) == 8


# ------------------------------------------------------- constraints

def test_frozen_sites_do_not_move():
    structure = water(oh=1.15, angle=95.0)
    calculator = ENGINES.build("uff", structure)
    result = optimize.run(calculator, structure, frozen=[0],
                          max_steps=200, force_tolerance=1e-4)
    assert np.allclose(result.frac[0], structure.sites[0].frac,
                       atol=1e-12)
    # And the rest still relaxed.
    assert not np.allclose(result.frac[1], structure.sites[1].frac,
                           atol=1e-6)


def test_freezing_everything_is_refused_rather_than_run():
    structure = water()
    calculator = ENGINES.build("uff", structure)
    with pytest.raises(Exception, match="nothing to relax"):
        list(optimize.steps(calculator, structure, frozen=[0, 1, 2]))


# ---------------------------------------------------- the step stream

def test_every_step_carries_a_usable_geometry():
    """The GUI draws each one, so a Step whose coordinates were only
    valid at the end would show the structure jumping about."""
    structure = water(oh=1.15)
    calculator = ENGINES.build("uff", structure)
    for step in optimize.steps(calculator, structure, max_steps=5):
        assert step.frac.shape == (3, 3)
        assert np.all(np.isfinite(step.frac))
        assert np.isfinite(step.energy)
        assert step.max_force >= 0.0


def test_a_caller_can_stop_the_run():
    structure = water(oh=1.20)
    calculator = ENGINES.build("uff", structure)
    result = optimize.run(calculator, structure, max_steps=500,
                          callback=lambda step: step.iteration < 3)
    assert result.steps == 3
    assert not result.converged
    assert "stopped" in result.message


def test_the_step_limit_stops_without_claiming_convergence():
    result = relax(water(oh=1.4, angle=70.0), max_steps=2,
                   force_tolerance=1e-8)
    assert not result.converged
    assert result.steps == 2
    assert "without converging" in result.summary()


def test_an_unknown_optimiser_is_refused_by_name():
    structure = water()
    calculator = ENGINES.build("uff", structure)
    with pytest.raises(ValueError, match="unknown optimiser"):
        optimize.steps(calculator, structure, method="gradient-descent")


# ------------------------------------------------------- the guards

@pytest.mark.parametrize("method", ["fire", "lbfgs"])
def test_a_badly_compressed_bond_still_relaxes(method):
    """Half its proper length is a force of several hundred
    kcal/mol/A.  Without a cap on the step the first iteration throws
    the atom out of the cell, and the run never comes back."""
    broken = water(oh=0.60, angle=104.5)
    # Compressed, but not so far that the two hydrogens come within
    # bonding distance of each other -- that would be a different
    # molecule, not a badly built one.
    assert ENGINES.build("uff", broken).topology.counts()["bonds"] == 2
    result = relax(broken, method=method, max_steps=500,
                   force_tolerance=1e-3)
    cart = geometry(broken, result)
    assert np.linalg.norm(cart[1] - cart[0]) == pytest.approx(
        UFF_OH, abs=0.01)


def test_no_single_step_moves_an_atom_further_than_the_cap():
    structure = water(oh=0.60, angle=104.5)
    calculator = ENGINES.build("uff", structure)
    matrix = structure.lattice.matrix
    previous = None
    for step in optimize.steps(calculator, structure, "fire",
                               max_steps=40, max_step=0.2):
        cart = step.frac @ matrix
        if previous is not None:
            assert np.linalg.norm(cart - previous,
                                  axis=1).max() <= 0.2 + 1e-9
        previous = cart


def test_atoms_below_the_bonding_threshold_are_not_bonded_at_all():
    """Not an optimiser property, but the reason a very compressed
    start behaves oddly: bond perception has a floor, and below it two
    atoms are an overlap rather than a bond.  The relaxation then has
    only van der Waals to work with and settles at its minimum."""
    overlapped = water(oh=0.35, angle=60.0)
    calculator = ENGINES.build("uff", overlapped)
    assert calculator.topology.counts()["bonds"] == 0


def test_the_force_reported_is_per_atom_and_not_per_orbit(rutile):
    """A site of multiplicity four collects four atoms' worth of
    gradient.  Reporting that raw would make a tolerance of 0.05 mean
    something different for every Wyckoff position."""
    calculator = ENGINES.build("uff", rutile)
    dof = optimize.SymmetryDOF(rutile)
    assert list(dof.multiplicity) == [2, 4]
    first = next(iter(optimize.steps(calculator, rutile)))
    raw = calculator.compute(p1.expand(rutile).cart,
                             rutile.lattice.matrix).max_force
    assert first.max_force < raw
