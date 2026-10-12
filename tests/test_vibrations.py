"""A Gamma-point Hessian by finite differences, under any engine.

UFF throughout: it is the engine that ships and needs nothing, and
the Hessian code never asks which engine it is talking to, so what
holds under UFF holds under MACE.
"""

from __future__ import annotations

import numpy as np
import pytest

from tests.conftest_ff import (
    benzene,
    carbon_dioxide,
    isolated,
    methane,
    water,
)
from xtal.core import molecule
from xtal.core.site import Site
from xtal.ff import ENGINES, optimize, vibrations
from xtal.ff.api import CalculatorStopped


def _relaxed(structure, engine="uff"):
    calculator = ENGINES.build(engine, structure)
    result = optimize.run(calculator, structure, force_tolerance=1e-4,
                          max_steps=2000)
    relaxed = structure.copy()
    for i, frac in enumerate(result.frac):
        relaxed.set_frac(i, frac)
    return relaxed


def _modes(structure, **kwargs):
    calculator = ENGINES.build("uff", structure)
    return vibrations.hessian(calculator, structure, **kwargs)


def test_a_hessian_is_symmetric_and_its_crystal_translations_are_zero(
        rutile):
    """Three acoustic modes at Gamma are exactly zero once the
    translations are projected out; without it they are a few
    wavenumbers either side of zero and S would count them."""
    found = _modes(rutile, kind="crystal")
    assert np.allclose(found.hessian, found.hessian.T)
    n_atoms = 6
    assert len(found.frequencies) == 3 * n_atoms
    nearly = np.sort(np.abs(found.frequencies))[:3]
    assert np.all(nearly < 1e-3)
    assert np.sum(np.abs(found.frequencies) < 1e-3) == 3


def test_water_has_three_modes_after_rotations_are_projected_out():
    """Nine coordinates, six of them rigid: the rotations of a relaxed
    molecule come out at tens of wavenumbers from finite differences,
    and they must not be counted once as vibrations and again by the
    ideal gas."""
    found = _modes(_relaxed(water()), kind="molecule")
    real = found.frequencies[np.abs(found.frequencies) > 1e-3]
    assert len(real) == 3
    assert np.all(real > 1000.0)
    assert found.kind == "molecule"


def test_a_dummy_atom_has_no_mode_and_does_not_move():
    """A marker is held back at the door: it has no mass, it is never
    displaced, and in every mode its row is zero."""
    structure = _relaxed(water())
    centre = structure.cart.mean(axis=0)
    structure.add_site(Site("X", structure.lattice.to_frac(centre)))
    found = _modes(structure, kind="molecule")
    assert found.free.tolist() == [0, 1, 2]
    real = found.frequencies[np.abs(found.frequencies) > 1e-3]
    assert len(real) == 3
    assert np.all(found.displacements[:, 3, :] == 0.0)
    assert found.evaluations == 6 * 3 + 1


def test_deuterium_lowers_an_oh_stretch_by_about_root_two():
    """The engine sees hydrogen and the mass matrix sees deuterium.
    The stretch of D2O is close to H2O's over sqrt(2) (anharmonicity
    and the oxygen's own motion pull it off)."""
    light = _relaxed(water())
    heavy = light.copy()
    for site in heavy.sites:
        if site.element == "H":
            site.element = "D"
    h2o = _modes(light, kind="molecule").frequencies.max()
    d2o = _modes(heavy, kind="molecule").frequencies.max()
    assert h2o / d2o == pytest.approx(np.sqrt(2.0), abs=0.08)


def test_a_frozen_atom_is_left_out_of_the_hessian():
    """Frozen atoms are not displaced, and their rows are zero.
    Translations are not projected out of a partial Hessian: with an
    atom held, a translation is not free."""
    structure = _relaxed(water())
    found = _modes(structure, kind="molecule", frozen=[0])
    assert found.free.tolist() == [1, 2]
    assert len(found.frequencies) == 6
    assert np.all(found.displacements[:, 0, :] == 0.0)
    assert found.evaluations == 6 * 2 + 1


def test_stop_between_displacements_returns_no_thermochemistry():
    """Stop raises out of the Hessian: a Hessian with some of its
    columns is not one, and nothing downstream is handed it.  What
    was done is reported through ``record`` as it finished."""
    recorded = []

    class Cancel:
        requested = False

    cancel = Cancel()

    def record(atom, axis, plus, minus):
        recorded.append((atom, axis))
        if len(recorded) == 2:
            cancel.requested = True

    with pytest.raises(CalculatorStopped):
        _modes(_relaxed(water()), kind="molecule", cancel=cancel,
               record=record)
    assert recorded == [(0, 0), (0, 1)]


def test_frequencies_come_out_in_wavenumbers():
    """A diatomic's harmonic frequency is sqrt(k/mu)/(2 pi c).  A
    wrong unit in the conversion is a factor of tens, so the check is
    against the force constant the Hessian itself reports."""
    structure = _relaxed(isolated(["H", "H"], [[0, 0, 0], [0.74, 0, 0]]))
    found = _modes(structure, kind="molecule")
    stretch = found.frequencies.max()
    k = found.hessian[0, 0]                        # kcal/mol/A^2
    mu = 1.00794 / 2.0
    expected = np.sqrt(k * 4184.0 / 1e-20 / (mu * 1e-3)) / (
        2 * np.pi * 2.99792458e10)
    assert stretch == pytest.approx(expected, rel=1e-6)


def test_the_modes_block_animates_what_the_hessian_found(rutile):
    found = _modes(rutile, kind="crystal")
    block = found.to_modes_block()
    assert block.n_modes == len(found.frequencies)
    assert block.displacements.shape == (18, 6, 3)
    assert np.allclose(
        np.linalg.norm(block.displacements, axis=2).max(axis=1), 1.0)


@pytest.mark.parametrize("build, sigma", [
    (water, 2), (lambda: isolated(
        ["N", "H", "H", "H"],
        [[0, 0, 0.38], [0.94, 0, 0], [-0.47, 0.814, 0],
         [-0.47, -0.814, 0]]), 3),
    (methane, 12), (benzene, 12), (carbon_dioxide, 2)])
def test_symmetry_numbers_of_water_ammonia_methane_benzene_co2(
        build, sigma):
    structure = build()
    elements, cart = molecule.whole(structure)
    assert molecule.rotational_symmetry_number(elements, cart) == sigma


def test_a_molecule_in_a_box_is_isolated_and_a_crystal_is_not(rutile):
    """Methane's hydrogens wrap through the box's faces, and it is
    still one molecule with vacuum all round it."""
    assert molecule.is_isolated(methane())
    assert not molecule.is_isolated(rutile)
    assert not molecule.is_isolated(
        isolated(["O", "H", "H"],
                 [[0, 0, 0], [0.96, 0, 0], [-0.24, 0.93, 0]], box=6.0))
