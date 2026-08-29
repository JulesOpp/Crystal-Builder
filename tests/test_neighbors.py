"""Periodic neighbour search."""

import numpy as np
import pytest

from xtal import Lattice
from xtal.core import neighbors


def test_perpendicular_widths_and_image_range():
    cubic = Lattice.cubic(3.0)
    assert neighbors.perpendicular_widths(cubic) == pytest.approx(
        [3.0, 3.0, 3.0])
    assert neighbors.image_range(cubic, 2.0) == (1, 1, 1)
    assert neighbors.image_range(cubic, 6.0) == (2, 2, 2)
    assert neighbors.image_range(cubic, 6.5) == (3, 3, 3)

    # A skewed cell is thinner than its edge lengths suggest, which is
    # exactly the case a naive "cutoff / a" would get wrong.
    skew = Lattice.from_parameters(5, 5, 5, 90, 90, 60)
    widths = neighbors.perpendicular_widths(skew)
    assert widths[0] < 5.0 and widths[2] == pytest.approx(5.0)


def test_image_range_rejects_a_zero_cutoff():
    with pytest.raises(ValueError):
        neighbors.image_range(Lattice.cubic(3.0), 0.0)


def test_one_atom_cell_finds_its_own_periodic_images():
    """A single atom in a small cell still has neighbours -- itself,
    one cell over.  Code that skips i == j misses them."""
    pairs = neighbors.neighbor_pairs([[0, 0, 0]], Lattice.cubic(3.0),
                                     cutoff=3.1)
    assert len(pairs) == 3                      # +a, +b, +c
    assert np.allclose(pairs.distance, 3.0)
    assert set(map(tuple, pairs.image)) == {(1, 0, 0), (0, 1, 0),
                                            (0, 0, 1)}


def test_pair_counts_grow_with_the_cutoff():
    lat = Lattice.cubic(3.0)
    assert len(neighbors.neighbor_pairs([[0, 0, 0]], lat, 3.1)) == 3
    # + the six face diagonals at a*sqrt(2)
    assert len(neighbors.neighbor_pairs([[0, 0, 0]], lat, 4.3)) == 9


def test_each_pair_is_listed_once(halite):
    from xtal.core import p1
    cell = p1.expand(halite)
    pairs = neighbors.neighbor_pairs(cell.frac, halite.lattice, 3.0)
    keys = {(int(i), int(j), tuple(t))
            for i, j, t in zip(pairs.i, pairs.j, pairs.image,
                               strict=True)}
    assert len(keys) == len(pairs)
    mirrored = {(j, i, tuple(-np.array(t))) for i, j, t in keys}
    assert not (keys & mirrored)


def test_nacl_first_shell(halite):
    """Every ion has six counter-ions at a/2."""
    from xtal.core import p1
    cell = p1.expand(halite)
    pairs = neighbors.neighbor_pairs(cell.frac, halite.lattice, 3.0)
    counts = np.zeros(cell.n_atoms, dtype=int)
    for i, j in zip(pairs.i, pairs.j, strict=True):
        counts[i] += 1
        counts[j] += 1
    assert list(counts) == [6] * 8
    assert np.allclose(pairs.distance, 5.6402 / 2)


def test_vectors_point_from_i_to_j():
    lat = Lattice.cubic(10.0)
    pairs = neighbors.neighbor_pairs([[0.1, 0, 0], [0.3, 0, 0]], lat,
                                     cutoff=3.0)
    assert len(pairs) == 1
    assert np.allclose(pairs.vector[0], [2.0, 0.0, 0.0])
    assert pairs.distance[0] == pytest.approx(2.0)


def test_min_image_crosses_the_boundary():
    lat = Lattice.cubic(10.0)
    d = neighbors.min_image_distance([0.05, 0, 0], [0.95, 0, 0], lat)
    assert d == pytest.approx(1.0)
    v = neighbors.min_image_vector([0.05, 0, 0], [0.95, 0, 0], lat)
    assert np.allclose(v, [-1.0, 0.0, 0.0])


def test_empty_and_filtered_pair_lists():
    lat = Lattice.cubic(10.0)
    assert len(neighbors.neighbor_pairs([], lat, 2.0)) == 0
    pairs = neighbors.neighbor_pairs(
        [[0, 0, 0], [0.2, 0, 0], [0.5, 0, 0]], lat, cutoff=5.5)
    close = pairs.filter(pairs.distance < 3.5)
    assert len(close) < len(pairs)
    assert np.all(np.diff(pairs.sorted_by_distance().distance) >= 0)
