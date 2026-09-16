"""Holding a coordinate while everything else relaxes.

The alternative -- freezing the atoms that define the coordinate --
already worked before any of this, and is wrong for the reason
`test_holding_a_distance_leaves_more_atoms_free_than_freezing_them`
measures: it removes six to twelve degrees of freedom to constrain
one, and what comes back is the profile of the constraint rather than
of the material.
"""

from __future__ import annotations

import numpy as np
import pytest

from xtal.core import p1
from xtal.ff import coordinates as co
from xtal.ff import optimize
from xtal.ff.constraints import ConstraintError, Holonomic
from xtal.ff.registry import ENGINES


def _cell_of(structure):
    cell = p1.expand(structure)
    matrix = structure.lattice.matrix
    return cell, matrix, cell.frac @ matrix


def _moved(structure, frac):
    out = structure.copy()
    for site, row in zip(out.sites, frac, strict=True):
        site.frac = row
    return out


def _value(structure, frac, coordinate):
    out = _moved(structure, frac)
    cell, matrix, positions = _cell_of(out)
    return coordinate.value(positions, matrix)


@pytest.fixture
def zif8():
    from xtal.io import read_cif
    return read_cif("resources/samples/ZIF-8.cif")


def test_a_held_distance_survives_the_relaxation(zif8):
    """The whole promise.  If the distance drifts, the energy reported
    at a scan point is the energy of some other point."""
    cell, matrix, positions = _cell_of(zif8)
    distance = co.internal(zif8, cell, "distance", [(0,), (1,)])
    target = distance.value(positions, matrix) + 0.25
    result = optimize.run(
        ENGINES.build("uff", zif8), zif8, method="lbfgs",
        max_steps=40, constraints=Holonomic(((distance, target),)))
    assert _value(zif8, result.frac, distance) == pytest.approx(
        target, abs=1e-6)


def test_a_held_torsion_survives_the_relaxation(zif8):
    """A torsion is the case the restoration has to be Newton for: it
    is not linear in the coordinates, and one correction pass is not
    enough after a large step."""
    cell, matrix, positions = _cell_of(zif8)
    torsion = co.internal(zif8, cell, "torsion",
                          [(0,), (1,), (2,), (3,)])
    target = torsion.value(positions, matrix) + 5.0
    result = optimize.run(
        ENGINES.build("uff", zif8), zif8, method="lbfgs",
        max_steps=40, constraints=Holonomic(((torsion, target),)))
    error = _value(zif8, result.frac, torsion) - target
    assert abs(error - 360.0 * round(error / 360.0)) < 1e-4


def test_a_held_coordinate_does_not_drift_over_the_whole_run(zif8):
    """Drift, not the endpoint.  A restoration that only ran at the
    end would pass the test above and still hand every intermediate
    step's energy to the wrong point."""
    cell, matrix, positions = _cell_of(zif8)
    distance = co.internal(zif8, cell, "distance", [(0,), (1,)])
    target = distance.value(positions, matrix) + 0.2
    held = Holonomic(((distance, target),))
    worst = 0.0
    for step in optimize.steps(ENGINES.build("uff", zif8), zif8,
                               method="lbfgs", max_steps=25,
                               constraints=held):
        worst = max(worst,
                    abs(_value(zif8, step.frac, distance) - target))
    assert worst < 1e-6


def test_two_coordinates_are_held_at_once(zif8):
    """A two-axis scan holds both, and they are solved together
    rather than one after the other."""
    cell, matrix, positions = _cell_of(zif8)
    first = co.internal(zif8, cell, "distance", [(0,), (1,)])
    second = co.internal(zif8, cell, "distance", [(4,), (5,)])
    targets = (first.value(positions, matrix) + 0.15,
               second.value(positions, matrix) - 0.15)
    result = optimize.run(
        ENGINES.build("uff", zif8), zif8, method="lbfgs",
        max_steps=30, constraints=Holonomic(
            ((first, targets[0]), (second, targets[1]))))
    assert _value(zif8, result.frac, first) == pytest.approx(
        targets[0], abs=1e-6)
    assert _value(zif8, result.frac, second) == pytest.approx(
        targets[1], abs=1e-6)


def test_the_residual_force_ignores_the_direction_being_held(zif8):
    """Otherwise no constrained point ever converges: the force the
    constraint is holding against would sit in |F|max for ever and
    every scan point would report itself unrelaxed."""
    cell, matrix, positions = _cell_of(zif8)
    distance = co.internal(zif8, cell, "distance", [(0,), (1,)])
    stretched = distance.value(positions, matrix) + 0.3
    calculator = ENGINES.build("uff", zif8)
    held = Holonomic(((distance, stretched),))
    dof = optimize.SymmetryDOF(zif8, constraints=held)
    x = dof.restore(dof.start)
    free_dof = optimize.SymmetryDOF(zif8)
    problem = optimize._Problem(calculator, free_dof)
    _energy, whole = problem(x)
    projected = held.project(dof, whole, x)
    # The constraint is pulling hard at a stretched bond, so the part
    # it holds is a real part of the gradient -- not rounding.
    assert np.abs(whole).max() > 1.5 * np.abs(projected).max()


def test_holding_a_distance_leaves_more_atoms_free_than_freezing_them(
        zif8):
    """The reason this machinery exists at all.

    Freezing the two atoms that define a distance removes six degrees
    of freedom to constrain one; holding it removes one.  The two
    atoms are *supposed* to move -- just not apart.
    """
    cell, matrix, positions = _cell_of(zif8)
    distance = co.internal(zif8, cell, "distance", [(0,), (1,)])
    target = distance.value(positions, matrix) + 0.2
    calculator = ENGINES.build("uff", zif8)

    held = optimize.run(calculator, zif8, method="lbfgs",
                        max_steps=30,
                        constraints=Holonomic(((distance, target),)))
    frozen = optimize.run(calculator, zif8, method="lbfgs",
                          max_steps=30,
                          frozen=[int(cell.site_idx[0]),
                                  int(cell.site_idx[1])])
    start = zif8.frac
    assert (np.linalg.norm(held.frac - start, axis=1).max()
            > np.linalg.norm(frozen.frac - start, axis=1).max())


def test_a_coordinate_the_space_group_forbids_is_refused(halite):
    """Every Na-Cl distance in Fm-3m is fixed by the group: both atoms
    are on special positions with no free coordinate between them.

    Without this the failure is a singular solve several screens below
    anything the user did.
    """
    cell, matrix, _positions = _cell_of(halite)
    distance = co.internal(halite, cell, "distance", [(0,), (1,)])
    held = Holonomic(((distance, 3.0),))
    with pytest.raises(ConstraintError, match="space group"):
        next(optimize.steps(ENGINES.build("uff", halite), halite,
                            constraints=held))


def test_a_coordinate_the_group_leaves_free_is_not_refused(rutile):
    """The refusal above must not catch an ordinary coordinate.  In
    rutile the oxygen has one free parameter and the Ti-O distance
    moves with it."""
    cell, matrix, positions = _cell_of(rutile)
    distance = co.internal(rutile, cell, "distance", [(0,), (2,)])
    dof = optimize.SymmetryDOF(
        rutile, constraints=(held := Holonomic(
            ((distance, distance.value(positions, matrix)),))))
    held.check(dof, dof.start)          # does not raise


def test_a_site_on_a_special_position_stays_on_it_while_held(quartz):
    """Constraints compose with symmetry rather than overriding it.

    The projector is applied last, so it can only ever remove freedom
    -- silicon on the 3a position of P3_221 has one free coordinate
    and must still have exactly one after a held run.
    """
    cell, matrix, positions = _cell_of(quartz)
    distance = co.internal(quartz, cell, "distance", [(0,), (3,)])
    target = distance.value(positions, matrix) + 0.05
    result = optimize.run(
        ENGINES.build("uff", quartz), quartz, method="lbfgs",
        max_steps=20, constraints=Holonomic(((distance, target),)))
    silicon = result.frac[0]
    assert silicon[1] == pytest.approx(0.0, abs=1e-9)
    assert silicon[2] == pytest.approx(2 / 3, abs=1e-9)


def test_a_frozen_site_stays_frozen_while_a_coordinate_is_held(zif8):
    """The other half of the same argument."""
    cell, matrix, positions = _cell_of(zif8)
    distance = co.internal(zif8, cell, "distance", [(0,), (1,)])
    target = distance.value(positions, matrix) + 0.2
    result = optimize.run(
        ENGINES.build("uff", zif8), zif8, method="lbfgs",
        max_steps=20, frozen=[7],
        constraints=Holonomic(((distance, target),)))
    assert np.allclose(result.frac[7], zif8.frac[7], atol=1e-12)


def test_an_unconstrained_run_is_untouched(zif8):
    """The constraint machinery must cost nothing when nobody asked
    for it: the default path has to descend exactly as it did."""
    calculator = ENGINES.build("uff", zif8)
    plain = optimize.run(calculator, zif8, method="lbfgs",
                         max_steps=15)
    again = optimize.run(calculator, zif8, method="lbfgs",
                         max_steps=15, constraints=Holonomic(()))
    assert plain.energy == pytest.approx(again.energy, rel=1e-12)


@pytest.mark.parametrize("method", ["lbfgs", "fire"])
def test_every_optimiser_holds_the_coordinate(zif8, method):
    """FIRE takes its own steps rather than going through the line
    search, so it restores its own; a hook added to one loop and not
    the other is the obvious way for this to half-work."""
    cell, matrix, positions = _cell_of(zif8)
    distance = co.internal(zif8, cell, "distance", [(0,), (1,)])
    target = distance.value(positions, matrix) + 0.1
    result = optimize.run(
        ENGINES.build("uff", zif8), zif8, method=method,
        max_steps=20, constraints=Holonomic(((distance, target),)))
    assert _value(zif8, result.frac, distance) == pytest.approx(
        target, abs=1e-6)
