"""The Brillouin zone of a cell, and a band path through it."""

import numpy as np
import pytest

from xtal import Lattice
from xtal.analysis import kpath

A = 5.431
FCC = Lattice(np.array([[0, A / 2, A / 2], [A / 2, 0, A / 2],
                        [A / 2, A / 2, 0]]))

needs_ase = pytest.mark.skipif(not kpath.installed(),
                               reason="the band path needs ASE")


def test_the_fcc_zone_is_a_truncated_octahedron():
    zone = kpath.brillouin_zone(FCC)
    assert len(zone.faces) == 14
    assert len(zone.vertices) == 24
    assert len(zone.edges) == 36
    assert sorted(len(face) for face in zone.faces) == [4] * 6 + [6] * 8


def test_a_cubic_zone_is_a_cube_centred_on_gamma():
    zone = kpath.brillouin_zone(Lattice.cubic(4.0))
    assert (len(zone.faces), len(zone.vertices)) == (6, 8)
    assert zone.vertices.mean(axis=0) == pytest.approx([0, 0, 0],
                                                       abs=1e-9)
    assert np.abs(zone.vertices).max() == pytest.approx(np.pi / 4.0)


def test_a_sheared_cell_still_closes_its_zone(quartz):
    zone = kpath.brillouin_zone(quartz.lattice)
    assert len(zone.faces) == 8                 # a hexagonal prism
    assert len(zone.vertices) == 12


@needs_ase
def test_gamma_is_the_origin_and_the_path_is_the_cells_own():
    path = kpath.band_path(FCC)
    assert path.points["G"] == (0.0, 0.0, 0.0)
    assert path.text == "GXWKGLUWLK,UX"
    # In this primitive cell X is (1/2, 0, 1/2), not the textbook
    # (0, 1/2, 1/2) of the conventional one.
    assert path.points["X"] == pytest.approx((0.5, 0.0, 0.5))


@needs_ase
def test_the_rutile_path_matches_ase(rutile):
    from ase.cell import Cell
    expected = Cell(rutile.lattice.matrix).bandpath(npoints=0)
    path = kpath.band_path(rutile.lattice)
    assert path.text == expected.path
    for name, k in expected.special_points.items():
        assert path.points[name] == pytest.approx(tuple(k))


def test_a_path_is_read_longest_name_first():
    points = {"X": (0, 0, 0), "X1": (1, 0, 0), "G": (0, 0, 0)}
    assert kpath.parse_path("GX1X,XG", points) == (("G", "X1", "X"),
                                                   ("X", "G"))
    with pytest.raises(ValueError, match="not a point"):
        kpath.parse_path("GQ", points)
    with pytest.raises(ValueError, match="two points"):
        kpath.parse_path("G", points)


def test_klines_start_each_run_with_one_point_and_ticks_join_a_jump():
    points = {"G": (0.0, 0.0, 0.0), "X": (0.5, 0.0, 0.5),
              "L": (0.5, 0.5, 0.5)}
    path = kpath.BandPath(points, (("G", "X"), ("L", "G")))
    lines = kpath.klines(path, FCC, density=10)
    counts = [count for count, _k in lines.segments]
    assert counts[0] == 1 and counts[2] == 1
    assert all(count >= 2 for count in (counts[1], counts[3]))
    x, ticks = kpath.positions(lines, FCC)
    assert len(x) == lines.n_points
    assert np.all(np.diff(x) >= 0)
    assert [label for _x, label in ticks] == ["Γ", "X|L", "Γ"]
    gx = np.linalg.norm(np.array(points["X"]) @ kpath.reciprocal(FCC))
    assert ticks[1][0] == pytest.approx(gx)
