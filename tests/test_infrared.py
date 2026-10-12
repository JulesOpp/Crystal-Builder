"""IR intensities from a Gamma Hessian and a charge model.

The frequencies are the engine's, the intensities a charge model's:
none of the machine-learned engines gives a charge or a dipole, so
the Born charges come from EQeq (or the force field's own charges),
fixed or re-solved at each displacement.
"""

from __future__ import annotations

import numpy as np
import pytest

from tests.conftest_ff import carbon_dioxide, isolated, water
from tests.test_vibrations import _relaxed
from xtal.ff import ENGINES, infrared, thermo, vibrations


def _modes(structure, kind="molecule"):
    calculator = ENGINES.build("uff", structure)
    return vibrations.hessian(calculator, structure, kind=kind)


def _spectrum(structure, kind="molecule", charges="fixed"):
    found = _modes(structure, kind)
    born, source = infrared.born_charges(structure, found,
                                         model=charges)
    return found, infrared.intensities(found, born), source


def _bright(found, intensity):
    """The real modes and their intensities, rigid motions left out."""
    real = np.abs(found.frequencies) > thermo.ZERO_BELOW
    return found.frequencies[real], intensity[real]


def test_a_homonuclear_diatomic_has_no_ir_intensity():
    structure = _relaxed(isolated(["H", "H"], [[0, 0, 0], [0.74, 0, 0]]))
    for model in ("fixed", "flux"):
        found, intensity, _source = _spectrum(structure, charges=model)
        _f, bright = _bright(found, intensity)
        assert np.all(bright < 1e-6), model


def test_waters_three_modes_are_all_ir_active():
    found, intensity, _source = _spectrum(_relaxed(water()))
    frequencies, bright = _bright(found, intensity)
    assert len(frequencies) == 3
    assert np.all(bright > 1.0)


def test_co2s_symmetric_stretch_is_dark_and_its_asymmetric_stretch_bright():
    """The selection rule: a mode that keeps the centre of symmetry
    moves no dipole.  If it breaks, the mass weighting or the Z*
    contraction is wrong."""
    found, intensity, _source = _spectrum(_relaxed(carbon_dioxide()))
    frequencies, bright = _bright(found, intensity)
    order = np.argsort(frequencies)
    frequencies, bright = frequencies[order], bright[order]
    assert len(frequencies) == 4
    symmetric, asymmetric = bright[2], bright[3]
    assert symmetric < 1e-6 * asymmetric
    assert asymmetric > 10.0
    assert np.all(bright[:2] > 1.0)         # the bend, twice


def test_acoustic_modes_carry_no_intensity_after_the_sum_rule(rutile):
    found = _modes(rutile, kind="crystal")
    born, _source = infrared.born_charges(rutile, found, model="flux")
    assert np.allclose(born.sum(axis=0), 0.0, atol=1e-9)
    intensity = infrared.intensities(found, born)
    acoustic = np.abs(found.frequencies) < 1e-3
    assert acoustic.sum() == 3
    assert np.all(intensity[acoustic] < 1e-9)


def test_charge_flux_changes_intensities_but_not_frequencies():
    structure = _relaxed(water())
    fixed_modes, fixed, _a = _spectrum(structure, charges="fixed")
    flux_modes, flux, _b = _spectrum(structure, charges="flux")
    assert np.allclose(fixed_modes.frequencies, flux_modes.frequencies)
    real = np.abs(fixed_modes.frequencies) > 1.0
    assert not np.allclose(fixed[real], flux[real], rtol=0.05)


def test_the_report_says_where_the_charges_came_from():
    found, intensity, source = _spectrum(_relaxed(water()))
    block = infrared.spectrum_block(found, intensity, source)
    assert "EQeq" in block.note
    assert "fixed" in block.note
    assert block.sticks().shape[1] == 2


def test_a_broadened_band_peaks_at_its_stick_and_has_its_width():
    found, intensity, source = _spectrum(_relaxed(water()))
    block = infrared.spectrum_block(found, intensity, source)
    x, y = block.broadened(fwhm=10.0)
    top = x[np.argmax(y)]
    strongest = block.frequencies[np.argmax(block.intensities)]
    assert top == pytest.approx(strongest, abs=1.0)
    half = y.max() / 2
    above = x[y > half]
    near = above[np.abs(above - top) < 50]
    assert near.max() - near.min() == pytest.approx(10.0, abs=1.0)
