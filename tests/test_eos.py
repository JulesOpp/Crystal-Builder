"""The equation of state through a volume scan: what it refuses and
what it recovers."""

import numpy as np
import pytest

from xtal.ff import eos
from xtal.ff.optimize import GPA


def _curve(form=eos.birch_murnaghan, b0=40.0, b0_prime=4.5,
           v0=100.0, e0=-500.0, span=0.06, n=9):
    volumes = np.linspace(v0 * (1 - span), v0 * (1 + span), n)
    return volumes, form(volumes, e0, v0, b0 * GPA, b0_prime)


def test_birch_murnaghan_recovers_the_modulus_of_a_synthetic_curve():
    """Fails if the units slip -- kcal/mol per cubic Angstrom is
    0.144 GPa, and a modulus out by that factor still looks like a
    modulus."""
    volumes, energies = _curve()
    fitted = eos.fit(volumes, energies)
    assert fitted.b0 == pytest.approx(40.0, rel=1e-4)
    assert fitted.b0_prime == pytest.approx(4.5, rel=1e-3)
    assert fitted.v0 == pytest.approx(100.0, rel=1e-6)
    assert fitted.rms < 1e-6


def test_vinet_agrees_with_birch_murnaghan_near_the_minimum():
    """The second form is the check on the first: through points a few
    percent from V0 the two should give one modulus."""
    volumes, energies = _curve(form=eos.vinet)
    birch, vinet = eos.both(volumes, energies)
    assert vinet.b0 == pytest.approx(40.0, rel=1e-4)
    assert birch.b0 == pytest.approx(vinet.b0, rel=0.02)


def test_the_fitted_curve_goes_through_the_points():
    volumes, energies = _curve()
    fitted = eos.fit(volumes, energies)
    assert np.allclose(fitted.energy(volumes), energies, atol=1e-6)


def test_an_unbracketed_minimum_is_refused_not_extrapolated():
    """Every point on one side of V0: the fit would happily report a
    V0 outside the scan and a modulus from the wrong side of it."""
    volumes, energies = _curve(v0=100.0, span=0.3, n=13)
    with pytest.raises(eos.EOSError, match="outside the scan"):
        eos.fit(volumes[7:], energies[7:])


def test_an_unconverged_point_is_left_out_of_the_fit():
    """NaN is how a scan writes a point that never relaxed.  Fitted as
    a number it would be a hole at zero; left out, the rest still
    give the modulus."""
    volumes, energies = _curve()
    energies[2] = np.nan
    fitted = eos.fit(volumes, energies)
    assert fitted.n_points == 8
    assert fitted.b0 == pytest.approx(40.0, rel=1e-4)


def test_too_few_points_are_refused():
    volumes, energies = _curve(n=4)
    with pytest.raises(eos.EOSError, match="at least 5"):
        eos.fit(volumes, energies)
