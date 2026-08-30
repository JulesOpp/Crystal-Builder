"""The neighbour and van der Waals pair lists, against brute force.

These lists are the most expensive thing the force field builds and
the easiest to break while making them faster, so they are pinned here
against an implementation that is slow and obviously right: every atom,
every image in range, no tree and no cleverness.  A rewrite that
changes one pair changes an energy, and this is what says so.
"""

import itertools

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.core import neighbors, p1
from xtal.ff.uff import calculator, terms


def reference_pairs(frac, lattice, cutoff, min_distance=1e-6):
    """Every pair under the cutoff, found by looking at all of them."""
    frac = np.asarray(frac, dtype=float).reshape(-1, 3)
    cart = lattice.to_cart(frac)
    na, nb, nc = neighbors.image_range(lattice, cutoff)
    found = {}
    for i, j in itertools.product(range(len(frac)), repeat=2):
        if j < i:
            continue
        for t in itertools.product(range(-na, na + 1),
                                   range(-nb, nb + 1),
                                   range(-nc, nc + 1)):
            if j == i and t <= (0, 0, 0):
                continue
            vector = (cart[j] + np.array(t, float) @ lattice.matrix
                      - cart[i])
            distance = float(np.linalg.norm(vector))
            if min_distance <= distance <= cutoff:
                found[(i, j, t)] = distance
    return found


def as_dict(pairs):
    return {(int(pairs.i[n]), int(pairs.j[n]),
             tuple(int(v) for v in pairs.image[n])): float(
                 pairs.distance[n])
            for n in range(len(pairs))}


@pytest.fixture
def triclinic():
    """A skewed cell with a short axis -- where a cutoff reaches
    several images along one direction and one along another, and
    where counting images from the cell lengths alone goes wrong."""
    return Structure.from_arrays(
        Lattice.from_parameters(4.1, 6.7, 3.2, 78.0, 96.0, 112.0),
        ["C", "O", "O", "N"],
        [[0.0, 0.0, 0.0], [0.31, 0.12, 0.44],
         [0.62, 0.55, 0.19], [0.08, 0.77, 0.71]])


# ------------------------------------------------------- neighbour list

@pytest.mark.parametrize("cutoff", [3.0, 5.0, 8.0])
def test_neighbour_pairs_match_brute_force(rutile, cutoff):
    cell = p1.expand(rutile)
    got = as_dict(neighbors.neighbor_pairs(cell.frac, rutile.lattice,
                                           cutoff))
    want = reference_pairs(cell.frac, rutile.lattice, cutoff)
    assert set(got) == set(want)
    for key, distance in want.items():
        assert got[key] == pytest.approx(distance)


def test_neighbour_pairs_match_brute_force_in_a_skewed_cell(triclinic):
    cell = p1.expand(triclinic)
    got = as_dict(neighbors.neighbor_pairs(cell.frac, triclinic.lattice,
                                           6.0))
    want = reference_pairs(cell.frac, triclinic.lattice, 6.0)
    assert set(got) == set(want)


def test_neighbour_pairs_match_brute_force_under_symmetry(quartz):
    cell = p1.expand(quartz)
    got = as_dict(neighbors.neighbor_pairs(cell.frac, quartz.lattice,
                                           5.0))
    assert set(got) == set(reference_pairs(cell.frac, quartz.lattice,
                                           5.0))


def test_an_empty_structure_has_no_pairs():
    lattice = Lattice.cubic(5.0)
    assert len(neighbors.neighbor_pairs(np.zeros((0, 3)), lattice,
                                        5.0)) == 0


# ------------------------------------------------------- vdW pair list

def reference_vdw(calc):
    """The van der Waals term, built one pair at a time from the atom
    types -- which is what the fast path has to keep agreeing with."""
    names = calc.typing.names
    term = calc._vdw
    x = np.zeros(len(term.i))
    d = np.zeros(len(term.i))
    for n in range(len(term.i)):
        x[n], d[n] = terms.vdw_pair(names[int(term.i[n])],
                                    names[int(term.j[n])])
    return x, d


@pytest.mark.parametrize("fixture", ["rutile", "quartz", "dry_ice",
                                     "halite"])
def test_vdw_parameters_match_a_pair_at_a_time(request, fixture):
    structure = request.getfixturevalue(fixture)
    calc = calculator.UFFCalculator(structure)
    cell = p1.expand(structure)
    calc.compute(cell.cart, structure.lattice.matrix)

    x, d = reference_vdw(calc)
    assert np.allclose(calc._vdw.x, x)
    assert np.allclose(calc._vdw.d, d)


@pytest.mark.parametrize("fixture", ["rutile", "quartz", "dry_ice"])
def test_bonded_and_geminal_pairs_are_excluded(request, fixture):
    """1-2 and 1-3 neighbours have no van der Waals interaction: the
    bond and angle terms already describe them.  If the exclusion test
    is vectorised wrongly this is what breaks, silently and in the
    fourth decimal place."""
    structure = request.getfixturevalue(fixture)
    calc = calculator.UFFCalculator(structure)
    cell = p1.expand(structure)
    calc.compute(cell.cart, structure.lattice.matrix)

    listed = {calculator._pair_key(int(i), int(j), image)
              for i, j, image in zip(calc._vdw.i, calc._vdw.j,
                                     calc._vdw.shift, strict=True)}
    assert not (listed & calc.topology.excluded)


def test_the_pair_list_covers_everything_that_is_not_excluded(rutile):
    calc = calculator.UFFCalculator(rutile)
    cell = p1.expand(rutile)
    calc.compute(cell.cart, rutile.lattice.matrix)

    radius = calc.options.vdw_cutoff + calc.options.skin
    everything = reference_pairs(cell.frac, rutile.lattice, radius)
    expected = {key for key in everything
                if calculator._pair_key(key[0], key[1], key[2])
                not in calc.topology.excluded}
    listed = {(int(i), int(j), tuple(int(v) for v in image))
              for i, j, image in zip(calc._vdw.i, calc._vdw.j,
                                     calc._vdw.shift, strict=True)}
    assert listed == expected


#: Quartz's van der Waals energy, in kcal/mol, from the pair list as it
#: was built one pair at a time.  Recorded so that a faster rebuild
#: which changes it is caught as the physics change it would be.
VDW_ENERGY = -26.79963741148963


def test_the_energy_is_unchanged_by_how_the_list_is_built(quartz):
    """The number that must not move.  Recorded from the loop-built
    list; a vectorised rebuild that changes it has changed the physics
    and not the speed."""
    calc = calculator.UFFCalculator(quartz)
    cell = p1.expand(quartz)
    result = calc.compute(cell.cart, quartz.lattice.matrix)
    assert result.terms["van der Waals"] == pytest.approx(
        VDW_ENERGY, abs=1e-9)


# --------------------------------------------------------- pair codes

@pytest.mark.parametrize("fixture", ["rutile", "quartz", "dry_ice",
                                     "halite"])
def test_pair_codes_agree_with_pair_keys(request, fixture):
    """The packed form and the tuple form name the same pairs.

    This is the whole safety net for packing a pair into an int64: if
    the two ever disagree, the exclusion test lets a bonded pair into
    the van der Waals list and the energy is quietly wrong.
    """
    structure = request.getfixturevalue(fixture)
    cell = p1.expand(structure)
    pairs = neighbors.neighbor_pairs(cell.frac, structure.lattice, 7.0)
    assert len(pairs) > 10

    codes = calculator.pair_codes(pairs.i, pairs.j, pairs.image,
                                  cell.n_atoms)
    keys = [calculator._pair_key(int(pairs.i[n]), int(pairs.j[n]),
                                 pairs.image[n])
            for n in range(len(pairs))]

    # Same pairs get the same code; different pairs get different ones.
    by_key = {}
    for key, code in zip(keys, codes, strict=True):
        by_key.setdefault(key, set()).add(int(code))
    assert all(len(v) == 1 for v in by_key.values())
    assert len({next(iter(v)) for v in by_key.values()}) == len(by_key)


def test_a_pair_is_coded_the_same_from_either_end():
    for i, j, shift in [(3, 7, (0, 0, 1)), (7, 3, (0, 0, -1)),
                        (5, 5, (1, 0, 0)), (5, 5, (-1, 0, 0))]:
        forward = calculator.pair_codes([i], [j], [shift], 16)
        backward = calculator.pair_codes([j], [i],
                                         [tuple(-v for v in shift)], 16)
        assert forward[0] == backward[0]


def test_distinct_pairs_do_not_collide():
    i = np.array([1, 1, 1, 2, 1])
    j = np.array([2, 2, 3, 3, 2])
    shift = np.array([[0, 0, 0], [0, 0, 1], [0, 0, 0], [0, 0, 0],
                      [1, 0, 0]])
    codes = calculator.pair_codes(i, j, shift, 8)
    assert len(set(int(c) for c in codes)) == 5


def test_an_unpackable_translation_is_refused_rather_than_wrapped():
    """Silently wrapping would make two different pairs share a code,
    which is an exclusion applied to the wrong pair."""
    with pytest.raises(ValueError, match="cannot be packed"):
        calculator.pair_codes([0], [1], [(1000, 0, 0)], 4)
