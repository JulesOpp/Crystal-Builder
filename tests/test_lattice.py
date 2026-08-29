"""Unit-cell geometry."""

import math

import numpy as np
import pytest

from xtal.core.lattice import Lattice

TRICLINIC = (5.1, 6.2, 7.3, 88.0, 92.0, 101.0)


def test_parameters_round_trip():
    lat = Lattice.from_parameters(*TRICLINIC)
    assert lat.parameters == pytest.approx(TRICLINIC, abs=1e-9)


def test_standard_orientation_puts_a_on_x_and_b_in_xy():
    lat = Lattice.from_parameters(*TRICLINIC)
    assert lat.matrix[0, 1] == pytest.approx(0.0)
    assert lat.matrix[0, 2] == pytest.approx(0.0)
    assert lat.matrix[1, 2] == pytest.approx(0.0)
    assert lat.matrix[1, 1] > 0 and lat.matrix[2, 2] > 0
    assert lat.is_right_handed


def test_volume_matches_the_closed_form():
    a, b, c, al, be, ga = TRICLINIC
    ca, cb, cg = (math.cos(math.radians(x)) for x in (al, be, ga))
    expected = a * b * c * math.sqrt(
        1 - ca**2 - cb**2 - cg**2 + 2 * ca * cb * cg)
    assert Lattice.from_parameters(*TRICLINIC).volume == pytest.approx(
        expected)


def test_cubic_volume():
    assert Lattice.cubic(4.0).volume == pytest.approx(64.0)


def test_coordinate_round_trip():
    lat = Lattice.from_parameters(*TRICLINIC)
    frac = np.array([[0.1, 0.2, 0.3], [-0.4, 0.9, 1.7], [0.0, 0.0, 0.0]])
    assert np.allclose(lat.to_frac(lat.to_cart(frac)), frac)
    # single point, not just blocks
    assert np.allclose(lat.to_cart([1, 0, 0]), lat.matrix[0])


def test_reciprocal_is_the_dual_basis():
    lat = Lattice.from_parameters(*TRICLINIC)
    rec = lat.reciprocal()
    assert np.allclose(lat.matrix @ rec.matrix.T, np.eye(3))
    rec2 = lat.reciprocal(two_pi=True)
    assert np.allclose(lat.matrix @ rec2.matrix.T, 2 * math.pi * np.eye(3))


def test_d_spacing_of_a_cubic_cell():
    lat = Lattice.cubic(4.0)
    assert lat.d_spacing((1, 0, 0)) == pytest.approx(4.0)
    assert lat.d_spacing((1, 1, 1)) == pytest.approx(4.0 / math.sqrt(3))
    with pytest.raises(ValueError):
        lat.d_spacing((0, 0, 0))


def test_metric_tensor_gives_lengths():
    lat = Lattice.from_parameters(*TRICLINIC)
    g = lat.metric_tensor
    f = np.array([0.3, -0.2, 0.7])
    assert math.sqrt(f @ g @ f) == pytest.approx(
        np.linalg.norm(lat.to_cart(f)))


def test_transform_builds_a_supercell():
    lat = Lattice.cubic(4.0)
    sup = lat.transform(np.diag([2, 2, 3]))
    assert sup.volume == pytest.approx(12 * lat.volume)
    assert sup.lengths == pytest.approx((8.0, 8.0, 12.0))


def test_transform_rejects_singular_and_handedness_flips():
    lat = Lattice.cubic(4.0)
    with pytest.raises(ValueError):
        lat.transform(np.zeros((3, 3)))
    with pytest.raises(ValueError):
        lat.transform(np.diag([-1, 1, 1]))


def test_strain_and_rescaling():
    lat = Lattice.cubic(4.0)
    assert lat.strained(0.01).lengths == pytest.approx((4.04,) * 3)
    shear = np.array([[0.0, 0.1, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]])
    assert lat.strained(shear).volume == pytest.approx(lat.volume)
    assert lat.scaled_to_volume(128.0).volume == pytest.approx(128.0)


def test_with_parameters_changes_only_what_is_given():
    lat = Lattice.from_parameters(*TRICLINIC)
    grown = lat.with_parameters(c=10.0)
    assert grown.parameters == pytest.approx(
        (5.1, 6.2, 10.0, 88.0, 92.0, 101.0))


def test_standard_orientation_removes_a_rigid_rotation():
    lat = Lattice.from_parameters(*TRICLINIC)
    theta = 0.7
    rot = np.array([[math.cos(theta), -math.sin(theta), 0],
                    [math.sin(theta), math.cos(theta), 0],
                    [0, 0, 1]])
    rotated = Lattice(lat.matrix @ rot.T)
    assert rotated.parameters == pytest.approx(lat.parameters)
    assert not np.allclose(rotated.matrix, lat.matrix)
    assert rotated.standard_orientation().almost_equal(lat)


def test_immutability_and_equality():
    lat = Lattice.cubic(4.0)
    with pytest.raises(ValueError):
        lat.matrix[0, 0] = 99.0
    assert lat == Lattice.cubic(4.0)
    assert lat != Lattice.cubic(4.1)
    assert hash(lat) == hash(Lattice.cubic(4.0))
    assert Lattice.from_dict(lat.to_dict()) == lat


def test_rejects_impossible_cells():
    with pytest.raises(ValueError):
        Lattice.from_parameters(0.0, 1.0, 1.0, 90, 90, 90)
    with pytest.raises(ValueError):
        Lattice.from_parameters(1.0, 1.0, 1.0, 190, 90, 90)
    with pytest.raises(ValueError):     # angles that cannot close
        Lattice.from_parameters(1.0, 1.0, 1.0, 10, 20, 170)
    with pytest.raises(ValueError):
        Lattice(np.zeros((3, 3)))
    with pytest.raises(ValueError):
        Lattice(np.eye(2))
