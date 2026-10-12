"""The thermochemistry arithmetic: frequencies in, H, S and G out.

Nothing here builds a Hessian -- the frequencies are experimental or
made up -- so a failure is in the statistical mechanics, not in a
force field.
"""

from __future__ import annotations

import importlib.util
from types import SimpleNamespace

import numpy as np
import pytest

from xtal.ff import thermo

# Experimental fundamentals and geometries (NIST CCCBDB).
WATER_FREQUENCIES = [1595.0, 3657.0, 3756.0]
CO2_FREQUENCIES = [667.4, 667.4, 1333.0, 2349.0]


def _water():
    r, half = 0.9572, np.radians(104.52) / 2
    cart = np.array([[0.0, 0.0, 0.0],
                     [r * np.sin(half), 0.0, r * np.cos(half)],
                     [-r * np.sin(half), 0.0, r * np.cos(half)]])
    return [15.999, 1.008, 1.008], cart


def _co2():
    cart = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 1.162],
                     [0.0, 0.0, -1.162]])
    return [12.011, 15.999, 15.999], cart


def _gas_entropy_j(frequencies, masses, cart, sigma):
    gas = thermo.IdealGas(masses=masses, cart=cart, sigma=sigma)
    result = thermo.thermochemistry(frequencies, temperature=298.15,
                                    gas=gas)
    return result.s * thermo.CAL


def test_water_as_an_ideal_gas_has_nists_entropy():
    """S(298.15 K, 1 bar) of water vapour is 188.8 J/(mol K).  If it
    is off by more than one, the translational or rotational term is
    wrong, and every molecule's G is with it."""
    masses, cart = _water()
    assert _gas_entropy_j(WATER_FREQUENCIES, masses, cart, 2) \
        == pytest.approx(188.8, abs=1.0)


def test_carbon_dioxide_is_linear_with_symmetry_number_two():
    """213.8 J/(mol K): a linear molecule has two rotations, not three,
    and taking it as nonlinear (its third moment is zero) would put a
    logarithm of zero in the entropy."""
    masses, cart = _co2()
    gas = thermo.IdealGas(masses=masses, cart=cart, sigma=2)
    assert gas.terms(298.15).linear
    assert _gas_entropy_j(CO2_FREQUENCIES, masses, cart, 2) \
        == pytest.approx(213.8, abs=1.0)


def test_a_harmonic_oscillator_has_its_zero_point_energy_at_zero_kelvin():
    """At 0 K a mode holds h c nu / 2 and nothing else: no thermal
    energy, no entropy, no heat capacity -- and no overflow from
    exp(h c nu / k T) on the way there."""
    terms = thermo.harmonic([1000.0], temperature=0.0)
    expected = 0.5 * 1000.0 * thermo.CM_TO_KCAL
    assert terms.zpe == pytest.approx(expected)
    assert terms.zpe == pytest.approx(1.4295, abs=1e-3)
    assert terms.u_vib == 0.0
    assert terms.s_vib == 0.0
    assert terms.cv == 0.0
    assert terms.f_vib == pytest.approx(expected)


def test_a_mode_far_below_kt_is_classical():
    """kT per mode of heat capacity once h c nu << k T: R, 1.987 cal."""
    terms = thermo.harmonic([10.0], temperature=5000.0)
    assert terms.cv == pytest.approx(thermo.R / thermo.CAL, rel=1e-3)


def test_quasi_rrho_is_harmonic_when_stiff_and_a_rotor_when_soft():
    """Grimme's interpolation is the harmonic entropy where a mode is
    stiff.  Where it is soft it is a free rotor's, which grows as half
    the logarithm the harmonic one does and is capped by B_av as the
    mode vanishes -- where the harmonic entropy runs away."""
    stiff = 2000.0
    assert thermo.quasi_rrho([stiff], temperature=298.15).s_vib \
        == pytest.approx(thermo.harmonic(
            [stiff], temperature=298.15).s_vib, abs=1e-5)

    def spread(entropy, low, high):
        return entropy(low) - entropy(high)

    def harmonic(f):
        return thermo.harmonic([f], temperature=298.15,
                               zero_below=0.0).s_vib

    def quasi(f):
        return thermo.quasi_rrho([f], temperature=298.15,
                                 zero_below=0.0).s_vib

    assert spread(quasi, 0.5, 2.0) / spread(harmonic, 0.5, 2.0) \
        == pytest.approx(0.5, abs=0.03)
    assert quasi(1e-6) < 20.0 < harmonic(1e-6)
    assert quasi(1.0) < harmonic(1.0)


def test_quasi_rrho_leaves_the_zero_point_energy_and_enthalpy_alone():
    """Grimme's correction is to the entropy only."""
    h = thermo.harmonic([30.0, 500.0], temperature=298.15)
    q = thermo.quasi_rrho([30.0, 500.0], temperature=298.15)
    assert q.zpe == pytest.approx(h.zpe)
    assert q.u_vib == pytest.approx(h.u_vib)
    assert q.s_vib < h.s_vib


def test_imaginary_and_zero_modes_are_counted_not_summed():
    """A mode at -200 cm-1 has no partition function and one at 0 has
    an infinite entropy; both are left out of the sum and said."""
    frequencies = [-200.0, -20.0, 0.0, 3.0, 50.0, 400.0]
    terms = thermo.harmonic(frequencies, temperature=298.15)
    alone = thermo.harmonic([50.0, 400.0], temperature=298.15)
    assert terms.n_imaginary == 1
    assert terms.n_zero == 3
    assert terms.n_used == 2
    assert terms.n_soft == 1
    assert terms.s_vib == pytest.approx(alone.s_vib)
    assert terms.zpe == pytest.approx(alone.zpe)


def test_the_imaginary_threshold_is_the_mode_tables():
    """One threshold, so the table and the sum never disagree about
    which modes are imaginary."""
    from xtal.modules.report import Modes
    assert thermo.IMAGINARY_BELOW == Modes.IMAGINARY_BELOW


def test_weights_scale_a_q_mesh_to_one_cell():
    """A mode on a mesh of n points counts 1/n of a Gamma mode."""
    once = thermo.harmonic([300.0], temperature=298.15)
    meshed = thermo.harmonic([300.0] * 4, weights=[0.25] * 4,
                             temperature=298.15)
    assert meshed.s_vib == pytest.approx(once.s_vib)
    assert meshed.zpe == pytest.approx(once.zpe)


def test_a_crystals_g_is_its_helmholtz_energy_per_formula_unit():
    """G = E + F_vib for a solid (PV is nothing at 1 bar), and divided
    by Z per formula unit."""
    result = thermo.thermochemistry([100.0, 200.0, 300.0],
                                    temperature=298.15, e_elec=-50.0,
                                    z=2)
    terms = thermo.harmonic([100.0, 200.0, 300.0], temperature=298.15)
    assert result.kind == "crystal"
    assert result.g == pytest.approx(-50.0 + terms.f_vib)
    assert result.h == pytest.approx(-50.0 + terms.zpe + terms.u_vib)
    assert result.g == pytest.approx(result.h - result.ts)
    assert result.per_unit(result.g) == pytest.approx(result.g / 2)


def test_a_gas_carries_pv_and_the_rigid_body_terms():
    """H of an ideal gas has 5/2 RT of translation (PV included) and
    3/2 RT of rotation for a nonlinear molecule."""
    masses, cart = _water()
    gas = thermo.IdealGas(masses=masses, cart=cart, sigma=2)
    result = thermo.thermochemistry(WATER_FREQUENCIES,
                                    temperature=298.15, gas=gas)
    vib = thermo.harmonic(WATER_FREQUENCIES, temperature=298.15)
    rt = thermo.R * 298.15 / 4184.0
    assert result.kind == "molecule"
    assert result.h == pytest.approx(vib.zpe + vib.u_vib + 4 * rt)


def test_spin_adds_r_ln_of_the_multiplicity():
    masses, cart = _water()
    singlet = thermo.IdealGas(masses=masses, cart=cart, sigma=2)
    triplet = thermo.IdealGas(masses=masses, cart=cart, sigma=2,
                              multiplicity=3)
    gap = triplet.terms(298.15).s - singlet.terms(298.15).s
    assert gap == pytest.approx(thermo.R * np.log(3) / thermo.CAL)


def test_the_dat_file_has_every_temperature_in_both_unit_systems():
    rows = [thermo.thermochemistry([300.0], temperature=t)
            for t in (100.0, 200.0)]
    text = thermo.as_dat(rows)
    assert "kcal/mol" in text and "kJ/mol" in text
    body = [line for line in text.splitlines()
            if line and not line.startswith("#")]
    assert len(body) == 2
    assert float(body[1].split()[0]) == 200.0


@pytest.mark.skipif(importlib.util.find_spec("phonopy") is None,
                    reason="phonopy is the check, and is not installed")
def test_harmonic_terms_match_phonopys_thermal_properties():
    """phonopy's own harmonic numbers, from the same frequencies: if
    ours drift, one of the two is wrong and it is the newer one."""
    from phonopy.phonon.thermal_properties import ThermalProperties
    from phonopy.physical_units import get_physical_units

    rng = np.random.default_rng(3)
    cm = np.sort(rng.uniform(40.0, 1600.0, size=(4, 9)), axis=1)
    weights = np.array([1, 3, 3, 1])
    thz = cm / get_physical_units().THzToCm
    mesh = SimpleNamespace(
        frequencies=thz, weights=weights,
        dynamical_matrix=SimpleNamespace(
            primitive=SimpleNamespace(Z=1)))
    tp = ThermalProperties(mesh)
    tp.temperatures = [300.0]
    tp.run()
    _t, free, entropy, cv = (np.asarray(v)[0] for v in tp.thermal_properties)

    ours = thermo.harmonic(cm.ravel(),
                           weights=np.repeat(weights / weights.sum(), 9),
                           temperature=300.0)
    assert ours.f_vib * 4.184 == pytest.approx(free, rel=1e-4)
    assert ours.s_vib * thermo.CAL == pytest.approx(entropy, rel=1e-4)
    assert ours.cv * thermo.CAL == pytest.approx(cv, rel=1e-4)
