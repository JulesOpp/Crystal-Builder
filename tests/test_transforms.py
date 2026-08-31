"""Geometry over a bare set of points: the best-fit plane, and the
smallest move that flattens things onto it.

Free functions with no structure, no symmetry and no undo stack behind
them, so the arithmetic can be checked against answers worked out by
hand -- which is the only way to be sure that "planarised, moved by up
to 0.08 A" is a true statement about what happened.
"""

import numpy as np
import pytest

from xtal.core.transforms import best_fit_plane, planarize, plane_deviation


def test_the_plane_of_flat_points_is_the_plane_they_are_in():
    points = [[0, 0, 3], [1, 0, 3], [0, 1, 3], [2, 5, 3]]
    centroid, normal = best_fit_plane(points)
    assert centroid[2] == pytest.approx(3.0)
    assert abs(float(normal @ np.array([0.0, 0.0, 1.0]))) == \
        pytest.approx(1.0)
    assert plane_deviation(points) == pytest.approx(0.0)


def test_the_normal_is_the_direction_the_points_vary_along_least():
    """A ring lying in the xy plane, tilted a little about x.  The
    normal has to follow the tilt, or every flatness test is answering
    a question about the wrong plane."""
    angle = np.radians(20.0)
    flat = np.array([[1, 0, 0], [0, 1, 0], [-1, 0, 0], [0, -1, 0]],
                    dtype=float)
    tilt = np.array([[1, 0, 0],
                     [0, np.cos(angle), -np.sin(angle)],
                     [0, np.sin(angle), np.cos(angle)]])
    _centroid, normal = best_fit_plane(flat @ tilt.T)
    expected = tilt @ np.array([0.0, 0.0, 1.0])
    assert abs(float(normal @ expected)) == pytest.approx(1.0)


def test_three_points_are_always_flat():
    """Asked as a question about flatness, and a triangle is flat --
    so the answer is zero rather than an error."""
    assert plane_deviation([[0, 0, 0], [1, 0, 0], [0, 1, 9]]) == 0.0
    assert plane_deviation([[0, 0, 0], [1, 2, 3]]) == 0.0


def test_a_plane_needs_three_points():
    with pytest.raises(ValueError):
        best_fit_plane([[0, 0, 0], [1, 0, 0]])


def test_flattening_moves_every_point_onto_one_plane():
    puckered = [[0, 0, 0.1], [1, 0, -0.1], [1, 1, 0.1], [0, 1, -0.1]]
    moved, displacement = planarize(puckered)
    assert plane_deviation(moved) == pytest.approx(0.0, abs=1e-12)
    assert displacement == pytest.approx(0.1)


def test_flattening_moves_along_the_normal_and_no_further():
    """The smallest displacement that makes the set coplanar.  Any
    other direction moves atoms sideways, which turns a fix into a
    rebuild."""
    puckered = np.array([[0, 0, 0.05], [2, 0, -0.05], [2, 3, 0.05],
                         [0, 3, -0.05]], dtype=float)
    moved, _displacement = planarize(puckered)
    _centroid, normal = best_fit_plane(puckered)
    sideways = (moved - puckered) - np.outer(
        (moved - puckered) @ normal, normal)
    assert np.allclose(sideways, 0.0, atol=1e-12)


def test_flattening_something_already_flat_changes_nothing():
    flat = np.array([[0, 0, 2], [1, 0, 2], [1, 1, 2]], dtype=float)
    moved, displacement = planarize(flat)
    assert np.allclose(moved, flat)
    assert displacement == pytest.approx(0.0)
