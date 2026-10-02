"""A disordered carbon from a recipe: xtal.carbon.build and ribbons."""

import numpy as np
import pytest
from scipy.spatial import cKDTree

from xtal.carbon import build as cb
from xtal.carbon import lattice as lt
from xtal.carbon import surface as sf
from xtal.core import bonding, p1


def _recipe(**changes):
    """One dia cell, unrelaxed: a build in about a second."""
    values = {"repeat": (1, 1, 1), "relax": "none"}
    values.update(changes)
    return cb.Recipe(**values)


@pytest.fixture(scope="module")
def built():
    return cb.build(_recipe())


def _bond_lengths(structure, a="C", b="C"):
    cell = p1.expand(structure)
    matrix = structure.lattice.matrix
    return np.array([
        np.linalg.norm((cell.frac[x.j] + x.image - cell.frac[x.i])
                       @ matrix)
        for x in bonding.graph(structure).bonds
        if {cell.elements[x.i], cell.elements[x.j]} == {a, b}])


def test_the_density_is_the_one_asked_for(built):
    """The cell is solved and the ribbons are cut to the carbon count
    the density asks for: within two percent."""
    assert built.density == pytest.approx(0.42, rel=0.02)


def test_a_ribbon_build_is_one_piece_percolating_in_three_directions(
        built):
    assert built.pieces == 1
    assert built.periodicity == 3


def test_coverage_one_half_keeps_about_half_the_area():
    """Half the closed sheet's carbon is what is kept, near enough --
    the share is what the cell was solved for, and the cut hits the
    count."""
    half = cb.build(_recipe(coverage=0.5))
    # The sheet's carbon is what is carbon now and what became a ring
    # ether's oxygen; the hydroxyl and carbonyl oxygens hang off it.
    elements = [s.element for s in half.structure.sites]
    on_sheet = elements.count("C") + sum(
        1 for k, e in enumerate(elements)
        if e == "O" and _carbon_neighbours(half, k) == 2)
    assert on_sheet / half.closed_carbons == pytest.approx(0.5, abs=0.05)


def _carbon_neighbours(built, k):
    """Neighbours of atom ``k`` that are carbon: two for a ring ether."""
    return sum(1 for b in bonding.graph(built.structure).bonds
               if k in (b.i, b.j)
               and built.structure.sites[b.j if b.i == k else b.i]
               .element == "C")


@pytest.mark.slow
def test_a_bilayers_sheets_are_three_point_three_five_apart_and_share_no_bonds(
):
    """Two sheets, each its own piece with no bond between them, the
    carbons of one about the interlayer spacing from the other's.  A
    bilayer holds twice the carbon a strut, so its cell is larger:
    1500 atoms here, five seconds."""
    two = cb.build(_recipe(layers=2, radius_ratio=0.4, coverage=0.4,
                           density=0.7))
    assert two.pieces == 2
    layer = two.layer
    for bond in bonding.graph(two.structure).bonds:
        assert layer[bond.i] == layer[bond.j]
    cell = p1.expand(two.structure)
    matrix = two.structure.lattice.matrix
    carbon = np.array(cell.elements) == "C"
    shifts = np.array([(a, b, c) for a in (-1, 0, 1) for b in (-1, 0, 1)
                       for c in (-1, 0, 1)])
    outer = cell.frac[carbon & (layer == 1)]
    tree = cKDTree(((outer[None] + shifts[:, None]).reshape(-1, 3))
                   @ matrix)
    inner = cell.frac[carbon & (layer == 0)] @ matrix
    gap, _index = tree.query(inner)
    assert np.median(gap) == pytest.approx(3.35, abs=0.35)


def test_a_build_is_reproducible_from_its_seed(built):
    """The same recipe is the same carbon, atom for atom; another seed
    is another."""
    again = cb.build(_recipe())
    other = cb.build(_recipe(seed=1))
    first = np.array([s.frac for s in built.structure.sites])
    assert np.allclose(first, [s.frac for s in again.structure.sites])
    assert len(other.structure.sites) != len(built.structure.sites) or \
        not np.allclose(first, [s.frac for s in other.structure.sites])


def test_gauss_bonnet_fixes_the_heptagons_a_net_needs():
    """A dia cell's closed sheet has chi -16, so 96 more heptagon
    equivalents than pentagons whatever the seed; srs's, 48."""
    assert cb.gauss_bonnet_need("dia") == -96
    assert cb.gauss_bonnet_need("srs") == -48
    assert cb.gauss_bonnet_need("dia", (2, 2, 2)) == -768


def test_the_report_says_what_was_built(built):
    lines = "\n".join(built.lines())
    for words in ("carbon density", "H/C", "edge carbons", "rings",
                  "Stone-Wales", "percolating in 3 directions"):
        assert words in lines


def test_a_net_ribbons_cannot_follow_is_refused_by_name():
    with pytest.raises(sf.SurfaceError, match="hcb"):
        cb.build(_recipe(net="hcb"))


@pytest.mark.slow
def test_relaxed_carbon_bonds_are_one_point_four_two_within_point_zero_five():
    """UFF at the solved cell, on the stated graph: the carbon-carbon
    bonds come to graphene's 1.42 A, none of them across the cell --
    an atom wrapped back by hand after relaxing kept bonds 39 A long --
    and nothing non-bonded closer than 2 A."""
    relaxed = cb.build(_recipe(relax="uff"))
    lengths = _bond_lengths(relaxed.structure)
    assert lengths.mean() == pytest.approx(1.42, abs=0.05)
    assert lengths.max() < 1.7
    assert relaxed.closest_contact > 2.0
    assert "UFF at the solved cell" in relaxed.relaxed
    assert lt.periodicity(len(relaxed.structure.sites),
                          [(b.i, b.j) for b in bonding.graph(
                              relaxed.structure).bonds],
                          [b.image for b in bonding.graph(
                              relaxed.structure).bonds]) == 3
