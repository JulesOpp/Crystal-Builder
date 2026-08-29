"""Supercells, cell transformations, reduction, vacuum."""

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.core import p1, properties, supercell, symmetry


def test_supercell_counts_and_density(rutile):
    big = supercell.supercell(rutile, 2, 2, 2)
    assert big.n_sites == 48                # 6 atoms x 8 cells
    assert big.is_p1                        # symmetry is not carried
    assert big.lattice.volume == pytest.approx(
        8 * rutile.lattice.volume)
    assert properties.density(big) == pytest.approx(
        properties.density(rutile))
    assert properties.formula(big)[0] == properties.formula(rutile)[0]


def test_supercell_lattice_parameters(rutile):
    a, b, c = rutile.lattice.lengths
    big = supercell.supercell(rutile, 2, 1, 3)
    assert big.lattice.lengths == pytest.approx((2 * a, b, 3 * c))
    assert big.n_sites == 36


def test_supercell_of_one_is_just_p1(quartz):
    same = supercell.supercell(quartz, 1, 1, 1)
    assert same.n_sites == p1.expand(quartz).n_atoms
    assert same.lattice.almost_equal(quartz.lattice)


@pytest.mark.parametrize("bad", [(0, 1, 1), (1, -2, 1)])
def test_supercell_rejects_non_positive_counts(rutile, bad):
    with pytest.raises(ValueError):
        supercell.supercell(rutile, *bad)


def test_general_transformation_matrix(rutile):
    """A rotated, doubled cell: |det P| = 2, so twice the atoms."""
    out = supercell.transform_cell(rutile, [[1, 1, 0], [-1, 1, 0],
                                            [0, 0, 1]])
    assert out.n_sites == 12
    assert out.lattice.volume == pytest.approx(
        2 * rutile.lattice.volume)
    assert properties.density(out) == pytest.approx(
        properties.density(rutile))


def test_identity_transformation_changes_nothing(quartz):
    out = supercell.transform_cell(quartz, np.eye(3))
    assert out.n_sites == p1.expand(quartz).n_atoms
    assert out.lattice.almost_equal(quartz.lattice)


def test_transformation_rejects_bad_matrices(rutile):
    with pytest.raises(ValueError):
        supercell.transform_cell(rutile, np.eye(3) * 1.5)   # not integer
    with pytest.raises(ValueError):
        supercell.transform_cell(rutile, np.zeros((3, 3)))  # singular
    with pytest.raises(ValueError):
        supercell.transform_cell(rutile, np.eye(2))         # wrong shape


def test_niggli_reduction_shortens_the_basis():
    """A deliberately skewed description of a cubic lattice reduces
    back to the cube."""
    skewed = Structure.from_arrays(
        Lattice(np.array([[4.0, 0, 0], [4.0, 4.0, 0], [4.0, 4.0, 4.0]])),
        ["Na"], [[0, 0, 0]])
    reduced = supercell.niggli_reduce(skewed)
    assert reduced.lattice.volume == pytest.approx(64.0)
    assert reduced.lattice.lengths == pytest.approx((4.0, 4.0, 4.0))
    assert reduced.lattice.angles == pytest.approx((90.0, 90.0, 90.0))
    assert reduced.n_sites == 1


def test_delaunay_reduction_preserves_the_crystal(rutile):
    flat = symmetry.reduce_to_p1(rutile)
    reduced = supercell.delaunay_reduce(flat)
    assert reduced.n_sites == flat.n_sites
    assert reduced.lattice.volume == pytest.approx(
        flat.lattice.volume)
    assert properties.density(reduced) == pytest.approx(
        properties.density(flat))


def test_origin_shift_moves_every_atom(rutile):
    shifted = supercell.shift_origin(rutile, [0.25, 0.0, 0.0])
    assert shifted.sites[0].frac[0] == pytest.approx(0.75)
    assert shifted.lattice == rutile.lattice
    assert shifted.space_group == rutile.space_group


def test_wrap_into_cell():
    s = Structure.from_arrays(Lattice.cubic(4.0), ["Na"],
                              [[1.25, -0.5, 2.0]])
    wrapped = supercell.wrap_into_cell(s)
    assert np.allclose(wrapped.sites[0].frac, [0.25, 0.5, 0.0])
    assert np.allclose(s.sites[0].frac, [1.25, -0.5, 2.0])  # unchanged


def test_add_vacuum_keeps_cartesian_positions(rutile):
    slab = supercell.add_vacuum(rutile, 10.0, axis=2)
    assert slab.lattice.lengths[2] == pytest.approx(2.9590 + 10.0)
    assert slab.lattice.lengths[:2] == pytest.approx(
        rutile.lattice.lengths[:2])
    original = p1.expand(rutile)
    moved = p1.expand(slab)
    assert np.allclose(np.sort(original.cart, axis=0),
                       np.sort(moved.cart, axis=0), atol=1e-9)


def test_add_vacuum_validates_its_arguments(rutile):
    with pytest.raises(ValueError):
        supercell.add_vacuum(rutile, 5.0, axis=3)
    with pytest.raises(ValueError):
        supercell.add_vacuum(rutile, -1.0)


def test_supercell_symmetry_can_be_recovered(rutile):
    """Supercells drop to P1, but the symmetry is still there to find
    -- that is the honest path back."""
    big = supercell.supercell(rutile, 2, 1, 1)
    assert symmetry.detect(big).number == 136
