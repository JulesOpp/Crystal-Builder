"""Symmetry expansion and the provenance it carries."""

import numpy as np
import pytest

from xtal.core import p1


def test_expansion_counts_and_multiplicities(rutile):
    cell = p1.expand(rutile)
    assert cell.n_atoms == len(cell) == 6
    assert list(cell.multiplicities(2)) == [2, 4]     # Ti 2a, O 4f
    assert cell.elements.count("Ti") == 2
    assert cell.elements.count("O") == 4


def test_special_positions_are_generated_once(quartz):
    """Si sits on a 2-fold axis: six operations, three atoms."""
    cell = p1.expand(quartz)
    assert quartz.space_group.order == 6
    assert cell.multiplicity(0) == 3            # Si, special position
    assert cell.multiplicity(1) == 6            # O, general position
    assert cell.n_atoms == 9


def test_centring_translations_are_included(halite):
    cell = p1.expand(halite)
    assert cell.n_atoms == 8                    # 4 Na + 4 Cl
    assert np.all(cell.frac >= 0.0)
    assert np.all(cell.frac < 1.0)


def test_provenance_reproduces_every_atom(quartz):
    """frac[k] == op[op_idx[k]](parent) + tau[k], for every atom."""
    cell = p1.expand(quartz)
    ops = quartz.space_group.operations
    for k in range(cell.n_atoms):
        parent = quartz.sites[cell.site_idx[k]].frac
        rebuilt = ops[cell.op_idx[k]].apply(parent) + cell.tau[k]
        assert np.allclose(rebuilt, cell.frac[k], atol=1e-12)


def test_parent_coordinates_inverts_the_image(quartz):
    cell = p1.expand(quartz)
    for k in range(cell.n_atoms):
        back = p1.parent_coordinates(quartz, cell, k, cell.frac[k])
        parent = quartz.sites[cell.site_idx[k]].frac
        d = back - parent
        assert np.allclose(d - np.round(d), 0.0, atol=1e-10)


def test_moving_an_image_moves_the_whole_orbit(rutile):
    """The mechanism behind symmetry-aware dragging: drop an image at a
    new position, map it back to the parent, and every image follows.

    The displacement here keeps O on its mirror plane (x, x, 0), so the
    site symmetry -- and the atom count -- is preserved."""
    cell = p1.expand(rutile)
    k = 4                                       # one of the O images
    op = rutile.space_group.operations[int(cell.op_idx[k])]
    target = cell.frac[k] + op.rot @ np.array([0.01, 0.01, 0.0])
    new_parent = p1.parent_coordinates(rutile, cell, k, target)

    moved = rutile.copy()
    moved.set_frac(int(cell.site_idx[k]), new_parent)
    moved_cell = p1.expand(moved)

    assert np.allclose(moved_cell.frac[k], target, atol=1e-12)
    assert moved_cell.n_atoms == cell.n_atoms
    for image in cell.orbit_of(k):              # the orbit all moved
        assert not np.allclose(moved_cell.frac[image],
                               cell.frac[image])


def test_dragging_off_a_special_position_multiplies_the_orbit(rutile):
    """O sits on the mirror plane x = y.  Moving it off that plane is
    legal, and the orbit doubles from 4 atoms to 8 -- behaviour the
    editor has to warn about rather than hide."""
    cell = p1.expand(rutile)
    assert cell.n_atoms == 6
    moved = rutile.copy()
    moved.set_frac(1, [0.2953, 0.3053, 0.0])    # off the plane
    assert p1.expand(moved).n_atoms == 10       # 2 Ti + 8 O


def test_orbit_and_index_helpers(rutile):
    cell = p1.expand(rutile)
    assert list(cell.indices_of_site(0)) == [0, 1]
    assert list(cell.orbit_of(3)) == [2, 3, 4, 5]
    assert list(cell.numbers[:2]) == [22, 22]


def test_expansion_is_cached_until_a_mutation(rutile):
    first = p1.expand(rutile)
    assert p1.expand(rutile) is first
    rutile.set_frac(0, [0.01, 0.0, 0.0])
    assert p1.expand(rutile) is not first


def test_p1_structure_expands_to_itself(dry_ice):
    from xtal.core.symmetry import reduce_to_p1
    flat = reduce_to_p1(dry_ice)
    cell = p1.expand(flat)
    assert cell.n_atoms == flat.n_sites == 12
    assert list(set(cell.op_idx)) == [0]        # identity only


def test_empty_structure_expands_to_nothing():
    from xtal import Lattice, Structure
    cell = p1.expand(Structure.empty(Lattice.cubic(5.0)))
    assert cell.n_atoms == 0
    assert cell.frac.shape == (0, 3)


def test_cart_uses_the_lattice(halite):
    cell = p1.expand(halite)
    assert np.allclose(cell.cart, halite.lattice.to_cart(cell.frac))
    assert cell.cart.shape == (8, 3)


@pytest.mark.parametrize("name", ["rutile", "quartz", "halite",
                                  "dry_ice"])
def test_no_two_atoms_coincide(name, request):
    """Expansion must never emit the same atom twice."""
    structure = request.getfixturevalue(name)
    cell = p1.expand(structure)
    for i in range(cell.n_atoms):
        for j in range(i + 1, cell.n_atoms):
            d = cell.frac[i] - cell.frac[j]
            d -= np.round(d)
            assert np.linalg.norm(d @ structure.lattice.matrix) > 0.5


# ------------------------------------------------------------ lookups

def test_multiplicity_and_orbits_agree_with_a_full_scan(quartz):
    """Both are memoised groupings now; they must still say exactly
    what counting by hand says."""
    cell = p1.expand(quartz)
    for site in range(quartz.n_sites):
        expected = np.flatnonzero(cell.site_idx == site)
        assert np.array_equal(cell.indices_of_site(site), expected)
        assert cell.multiplicity(site) == len(expected)
    assert np.array_equal(cell.multiplicities(quartz.n_sites),
                          [3, 6])           # Si is on a special position
    assert cell.multiplicity(99) == 0
    assert len(cell.indices_of_site(99)) == 0


def test_orbit_lookups_do_not_scan_the_cell(halite):
    """The site table asks for these once per row.  Scanning the whole
    cell each time makes drawing it quadratic, which a P1 structure
    with a thousand sites notices."""
    import time

    from xtal.core import symmetry

    flat = symmetry.reduce_to_p1(symmetry.reduce_to_p1(halite))
    cell = p1.expand(flat)
    assert cell.n_atoms >= 8

    cell.indices_of_site(0)                 # build the grouping once
    start = time.perf_counter()
    for _ in range(200):
        for site in range(flat.n_sites):
            cell.multiplicity(site)
            cell.indices_of_site(site)
    assert time.perf_counter() - start < 1.0


def test_expansion_keeps_the_first_operation_that_reaches_a_point(
        quartz):
    """Which operation is recorded for an atom on a special position
    decides how an edit maps back onto its parent, so it has to be
    reproducible: the first operation to get there wins."""
    cell = p1.expand(quartz)
    again = p1._expand_uncached(quartz, p1.SPECIAL_POSITION_TOL)
    assert np.array_equal(cell.op_idx, again.op_idx)
    assert np.array_equal(cell.tau, again.tau)
    for atom in range(cell.n_atoms):
        op = quartz.space_group.operations[int(cell.op_idx[atom])]
        parent = quartz.sites[int(cell.site_idx[atom])]
        assert np.allclose(op.apply(parent.frac) + cell.tau[atom],
                           cell.frac[atom], atol=1e-9)
