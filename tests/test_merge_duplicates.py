"""Merging duplicates on the deposited file that shows why it matters.

``Ni2Cl2BTDD.cif`` (CCDC POSWUS) was written with a full cell's worth
of coordinates under ``H-3m``, so 27 of its 40 sites are atoms already
present as a different symmetry image.  Expanded as it stands it puts
1152 atoms in a cell that holds 378 -- three complete copies of the
structure, with the formula, the density and any energy computed from
it wrong by that factor and nothing on screen saying so.

The file also writes ``O1`` at ``y = 0.3505`` where the mirror it sits
on wants ``y = 2x = 0.35046``: 0.0015 A off, which is the fourth
decimal place and not a position.  The expansion used to generate both
sides of that mirror, so the dioxin bridge of a BTDD linker that has
two oxygens arrived with four -- see :data:`p1.SPECIAL_POSITION_TOL`.

Comparing the parent coordinates, which is what merging did until now,
finds none of them at any tolerance: ``C1`` and ``C1X`` are 7.2 A apart
as written.  Through the operations of the group they are 2e-5 A apart.
"""

import pathlib
from collections import Counter

import numpy as np
import pytest

from xtal.core import p1, properties, symmetry
from xtal.io import read_cif

SAMPLE = (pathlib.Path(__file__).resolve().parent.parent
          / "resources" / "samples" / "Ni2Cl2BTDD.cif")

pytestmark = pytest.mark.skipif(not SAMPLE.exists(),
                                reason="sample structure not present")


@pytest.fixture(scope="module")
def btdd():
    return read_cif(SAMPLE)


def label(structure, name: str) -> int:
    return [s.label for s in structure.sites].index(name)


def test_the_duplicate_is_far_away_as_written(btdd):
    """The premise: the two coordinates are as far apart as any two
    atoms in the cell, and are the same atom."""
    i, j = label(btdd, "C1"), label(btdd, "C1X")
    d = btdd.sites[i].frac - btdd.sites[j].frac
    d -= np.round(d)
    assert np.linalg.norm(d @ btdd.lattice.matrix) \
        == pytest.approx(7.2, abs=0.05)

    cell = p1.expand(btdd)
    images = cell.frac[cell.indices_of_site(i)] - btdd.sites[j].frac
    images -= np.round(images)
    assert np.linalg.norm(
        images @ btdd.lattice.matrix, axis=1).min() < 1e-4


def test_the_cell_is_three_copies_of_itself(btdd):
    assert btdd.n_sites == 40
    assert p1.expand(btdd).n_atoms == 1152

    merged, report = symmetry.merge_duplicates(btdd, tol=0.05)
    assert report.merged == 27
    assert merged.n_sites == 13
    assert p1.expand(merged).n_atoms == 378


def test_merging_is_what_makes_the_formula_right(btdd):
    """Z is 9 and the published unit is C12 Cl2 N6 Ni2 O(11.48), so the
    framework of the cell is 108 C, 18 Cl, 54 N, 18 Ni.

    The 108 C are nine BTDD linkers of twelve, and a BTDD linker has
    two bridging oxygens -- so ``O1`` is 18 atoms in the cell, and the
    36 it used to be was four oxygens on a ligand with two.
    """
    merged, _report = symmetry.merge_duplicates(btdd, tol=0.05)
    cell = p1.expand(merged)
    counts = Counter(cell.elements)
    assert (counts["C"], counts["Cl"], counts["N"], counts["Ni"]) \
        == (108, 18, 54, 18)
    assert cell.multiplicity(label(merged, "O1")) == 18
    assert properties.info(merged).formula == "NiC6N3ClO10"


def test_the_count_steps_and_then_goes_flat(btdd):
    """Why the tolerance is shown with its count beside it.

    The duplicates here are exact only to the four and five decimals
    the file was written with, so the count steps 8, 18, 25, 26, 27 as
    the rounding of the last place is crossed and then does not move
    again over three orders of magnitude.  The 0.05 A the menu item
    used to run at silently happens to be right for this file; the
    count is the only thing that says so, and the guess that stops at
    8 of 27 looks exactly like the guess that finds all of them."""
    counts = [symmetry.preview_merge(btdd, tol).merged
              for tol in (1e-6, 5e-5, 2e-4, 5e-4, 0.05, 1.0)]
    assert counts == [8, 18, 25, 26, 27, 27]


def test_the_preview_and_the_merge_agree(btdd):
    plan = symmetry.preview_merge(btdd, 0.05)
    merged, report = symmetry.merge_duplicates(btdd, tol=0.05)
    assert (plan.merged, plan.sites_after, plan.atoms_after) \
        == (report.merged, merged.n_sites, p1.expand(merged).n_atoms)
    assert plan.message() == ("27 of 40 sites merge -- 1152 atoms in "
                              "the cell become 378")
