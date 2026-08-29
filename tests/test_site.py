"""Asymmetric-unit sites."""

import numpy as np
import pytest

from xtal.core.lattice import Lattice
from xtal.core.site import Site


def test_construction_normalises_element_and_coordinates():
    s = Site("fe2+", [0.1, 0.2, 0.3])
    assert s.element == "Fe"
    assert isinstance(s.frac, np.ndarray)
    assert s.frac.dtype == float
    assert s.z == 26 and s.mass == pytest.approx(55.845, abs=1e-3)
    assert s.occupancy == 1.0 and not s.is_partial


def test_coordinates_are_copied_not_aliased():
    source = np.array([0.1, 0.2, 0.3])
    s = Site("C", source)
    source[0] = 0.9
    assert s.frac[0] == pytest.approx(0.1)


def test_cart_and_wrapping():
    s = Site("C", [1.25, -0.5, 0.0])
    assert np.allclose(s.wrapped(), [0.25, 0.5, 0.0])
    assert np.allclose(s.cart(Lattice.cubic(4.0)), [5.0, -2.0, 0.0])


def test_partial_occupancy():
    assert Site("Na", [0, 0, 0], occupancy=0.5).is_partial


@pytest.mark.parametrize("bad", [0.0, -0.2])
def test_bad_occupancy_raises(bad):
    with pytest.raises(ValueError):
        Site("Na", [0, 0, 0], occupancy=bad)


def test_non_finite_coordinates_raise():
    with pytest.raises(ValueError):
        Site("C", [0.0, float("nan"), 0.0])


def test_copy_is_deep():
    s = Site("O", [0, 0, 0], props={"uff_type": "O_3"})
    c = s.copy()
    c.frac[0] = 0.5
    c.props["uff_type"] = "O_2"
    assert s.frac[0] == 0.0
    assert s.props["uff_type"] == "O_3"


def test_dict_round_trip_keeps_every_field():
    s = Site("O", [0.1, 0.2, 0.3], occupancy=0.75, label="O1",
             u_iso=0.02, charge=-0.8, wyckoff="4e",
             props={"uff_type": "O_3"})
    assert Site.from_dict(s.to_dict()) == s
    assert Site.from_dict(s.to_dict()).wyckoff == "4e"


def test_equality_ignores_float_noise_but_not_real_differences():
    a = Site("O", [0.1, 0.2, 0.3])
    b = Site("O", [0.1 + 1e-12, 0.2, 0.3])
    assert a == b
    assert a != Site("O", [0.1, 0.2, 0.4])
    assert a != Site("S", [0.1, 0.2, 0.3])
