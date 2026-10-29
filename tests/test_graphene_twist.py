"""Twisted bilayers at commensurate angles: xtal.graphene.twist."""

import math
import re
from collections import Counter

import numpy as np
import pytest

from xtal.core import limits
from xtal.graphene import build as sheet
from xtal.graphene import twist
from xtal.graphene.build import GrapheneError, Recipe
from xtal.graphene.twist import Twist

#: The hexagonal cell build.py uses, a = 1.
_HEXAGONAL = np.array([[1.0, 0.0], [-0.5, math.sqrt(3) / 2]])


def _turn(degrees):
    t = math.radians(degrees)
    return np.array([[math.cos(t), -math.sin(t)],
                     [math.sin(t), math.cos(t)]])


def _twisted(angle="21.79", **changes):
    return sheet.build(Recipe(stacking="twisted", layers=2, twist=angle,
                              **changes))


def test_m1_r1_is_21_79_degrees_with_28_atoms():
    """The smallest commensurate cell, and the formula's own check:
    cos t = (3 + 3 + 1/2) / (3 + 3 + 1)."""
    smallest = Twist(1, 1)
    assert smallest.angle == pytest.approx(21.786789, abs=1e-6)
    assert math.cos(math.radians(smallest.angle)) \
        == pytest.approx(6.5 / 7)
    assert smallest.atoms == 28
    assert twist.read("21.79") == smallest
    assert len(_twisted().structure.sites) == 28


def test_the_magic_angle_is_30_1_with_11164_atoms():
    magic = twist.read("1.08")
    assert magic == Twist(30, 1)
    assert magic.angle == pytest.approx(1.0845, abs=1e-4)
    assert magic.atoms == 11164


def test_an_angle_is_read_to_the_precision_it_was_written_at():
    """The angles are dense, so the cell is the smallest at the angle
    written: two decimals at the coarsest -- "2" is not 2.45 -- and
    more where more were written."""
    assert twist.read("2") == twist.read("2.00") == Twist(16, 1)
    assert twist.tolerance("2") == twist.tolerance("2.0") == 0.005
    assert twist.tolerance("1.0845") == pytest.approx(5e-5)
    assert twist.read("1.0845") == Twist(30, 1)
    # (30, 1) is 1.08455, so three places put it out of reach, and
    # no cell under a million atoms is within 0.0005 of 1.084.
    with pytest.raises(twist.TwistError, match="the nearest is 1.08 "):
        twist.read("1.084")


def test_every_angle_the_form_lists_reads_back_to_its_own_cell():
    """The list writes each angle as :func:`twist.spelled` spells it,
    and a choice that came back as a smaller cell nearby would build
    something other than what was chosen."""
    for angle in (0.5, 1.08, 3.0, 9.43, 21.79, 38.0, 55.0):
        for each in twist.nearest(angle, 8, max_atoms=200_000):
            assert twist.read(twist.spelled(each)) == each


def test_an_angle_no_cell_is_near_is_refused_naming_the_nearest():
    with pytest.raises(GrapheneError, match="the nearest is 59.80"):
        _twisted("59.9")
    with pytest.raises(GrapheneError, match="between 0 and 60"):
        _twisted("0")
    with pytest.raises(GrapheneError, match="an angle in degrees"):
        _twisted("magic")


def test_a_twist_needs_two_layers():
    with pytest.raises(GrapheneError, match="at least two layers"):
        sheet.build(Recipe(stacking="twisted"))


def test_the_two_layers_share_the_cell_exactly():
    """Each layer's integer cell, the upper one turned by the twist,
    is the same two vectors: each layer is a whole sublattice of the
    twisted cell, so nothing is strained to close it."""
    angles, ms, rs = twist.table()
    for k in range(0, len(angles), 997):
        each = Twist(int(ms[k]), int(rs[k]))
        lower, upper = twist.matrices(each)
        assert lower.dtype.kind == upper.dtype.kind == "i"
        assert round(np.linalg.det(lower)) == each.cells
        assert np.allclose(lower @ _HEXAGONAL,
                           upper @ _HEXAGONAL @ _turn(each.angle).T,
                           atol=1e-9 * each.cells)


def test_every_atom_has_three_bonds_within_its_own_layer():
    """Every atom three bonds at the sheet's length, none between the
    layers, for a cell, a repeat of a rectangular one, and a bulk
    h-BN stack."""
    for built in (_twisted("1.08"),
                  _twisted("9.43", rectangular=True, cells_a=2),
                  _twisted("13.17", stack="bulk", element_a="B",
                           element_b="N")):
        structure = built.structure
        matrix = structure.lattice.matrix
        frac = np.array([s.frac for s in structure.sites])
        cart = frac @ matrix
        degree, lengths = Counter(), []
        for bond in structure.perceived.bonds:
            assert frac[bond.i, 2] == pytest.approx(frac[bond.j, 2])
            degree[bond.i] += 1
            degree[bond.j] += 1
            lengths.append(np.linalg.norm(
                cart[bond.j] + np.array(bond.image) @ matrix
                - cart[bond.i]))
        assert set(degree.values()) == {3}
        assert len(degree) == len(structure.sites)
        assert np.ptp(lengths) < 1e-9
        assert lengths[0] == pytest.approx(built.recipe.bond_length)


def test_the_upper_layer_is_the_lower_turned_about_a_shared_atom():
    """Turned back by the twist, the upper layer's atoms are the
    lower layer's own sites: AA twisted about the atom at the
    origin, which both layers have."""
    built = _twisted("9.43")
    structure = built.structure
    matrix = structure.lattice.matrix
    cart = np.array([s.frac for s in structure.sites]) @ matrix
    z = cart[:, 2]
    lower, upper = cart[z < z.mean(), :2], cart[z > z.mean(), :2]
    assert np.isclose(np.linalg.norm(lower, axis=1), 0).any()
    assert np.isclose(np.linalg.norm(upper, axis=1), 0).any()
    back = upper @ _turn(built.recipe.moire.angle)
    a = math.sqrt(3) * built.recipe.bond_length
    # On the lower layer's lattice of sites: a site, or a site and a
    # bond along a1 - a2, at integer cell coordinates.
    hexagonal = _HEXAGONAL * a
    fractional = back @ np.linalg.inv(hexagonal)
    on = [np.all(np.isclose(fractional - shift,
                            np.rint(fractional - shift), atol=1e-6),
                 axis=1)
          for shift in (np.zeros(2), np.array([1 / 3, -1 / 3]))]
    assert np.all(on[0] | on[1])


def test_a_twist_over_the_hard_limit_is_refused_naming_the_nearest_that_fits():
    """0.2 degrees is a third of a million atoms: refused under the
    standard profile, naming the angle nearest it that fits."""
    recipe = sheet.checked(Recipe(stacking="twisted", layers=2,
                                  twist="0.2"))
    verdict = limits.check_graphene(recipe)
    assert verdict.refused
    assert verdict.estimate == recipe.moire.atoms > 200_000
    assert "is the nearest twist that fits" in verdict.sentence
    fits = re.search(r"; ([\d.]+) degrees", verdict.sentence).group(1)
    smaller = sheet.checked(Recipe(stacking="twisted", layers=2,
                                   twist=fits))
    assert not limits.check_graphene(smaller).refused
    assert smaller.moire.angle > recipe.moire.angle


def test_the_estimate_counts_a_twisted_stack_exactly():
    for changes in ({"twist": "21.79", "layers": 3},
                    {"twist": "9.43", "rectangular": True,
                     "cells_b": 2},
                    {"twist": "13.17", "layers": 4, "stack": "bulk"}):
        recipe = Recipe(stacking="twisted", **{"layers": 2, **changes})
        assert limits.graphene_atoms(sheet.checked(recipe)) \
            == len(sheet.build(recipe).structure.sites)
