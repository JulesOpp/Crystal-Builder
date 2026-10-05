"""Merge Duplicate Sites puts a site back on the special position it
was moved off.

A site moved 0.06 A off a three-fold axis is generated three times,
0.1 A apart -- MOF-5's Zn1, 32 zinc becoming 96 -- and merging used to
say "no duplicates found" at any tolerance, because it compared a site
against the images of *other* sites and never against its own.  The
three are one atom, so merging now averages them back onto the
position they split from, and says so.
"""

import pathlib

import numpy as np
import pytest

from xtal.commands import Host
from xtal.commands.atoms import MoveSites
from xtal.core import bonding, p1, symmetry

MOF5 = (pathlib.Path(__file__).resolve().parent.parent
        / "resources" / "samples" / "MOF-5.cif")


def _off_the_axis(structure, by=(0.0, 0.01, 0.0)):
    """Quartz's Si moved off its two-fold axis, its two copies about
    0.1 A apart: six atoms where there were three."""
    moved = structure.copy()
    MoveSites({0: moved.sites[0].frac + np.array(by)}).do(Host(moved))
    return moved


def test_merging_puts_a_site_back_on_the_axis_it_was_moved_off(quartz):
    moved = _off_the_axis(quartz)
    assert p1.expand(moved).n_atoms == 12
    out, report = symmetry.merge_duplicates(moved, tol=0.2)
    assert p1.expand(out).n_atoms == 9
    assert out.n_sites == quartz.n_sites
    assert report.snapped == 1
    assert "Si" in report.message or "site 1" in report.message
    x, y, _z = out.sites[0].frac
    assert y == pytest.approx(0.0, abs=1e-9)        # (x, 0, 2/3)


def test_a_site_further_off_than_the_tolerance_is_left_where_it_is(
        quartz):
    """A tolerance is a promise about how far things move."""
    moved = _off_the_axis(quartz, by=(0.0, 0.03, 0.0))
    out, report = symmetry.merge_duplicates(moved, tol=0.1)
    assert report.snapped == 0
    assert p1.expand(out).n_atoms == 12
    assert np.allclose(out.sites[0].frac, moved.sites[0].frac)


def test_a_site_on_its_position_already_is_not_moved(quartz):
    out, report = symmetry.merge_duplicates(quartz, tol=0.5)
    assert report.snapped == 0
    assert np.allclose(out.sites[0].frac, quartz.sites[0].frac)


def test_the_preview_counts_what_the_snap_takes_away(quartz):
    moved = _off_the_axis(quartz)
    plan = symmetry.preview_merge(moved, tol=0.2)
    assert plan
    assert plan.snapped == 1
    assert (plan.atoms_before, plan.atoms_after) == (12, 9)
    assert "special position" in plan.message()


def test_snapping_back_keeps_the_bonds_the_structure_had(quartz,
                                                         monkeypatch):
    """Merging is not Recalculate Bonds: the snapped atom comes back
    with the bonds it had, and nothing is perceived to find them."""
    held = quartz.copy()
    bonding.perceive(held)
    held.perceived.bonds = held.perceived.bonds[::2]
    held.drop_cache("bonds:")
    before = sorted(b.key() for b in bonding.perceive(held))
    moved = _off_the_axis(held)
    bonding.perceive(moved)

    def no_perception(*args, **kwargs):
        raise AssertionError("the cell was perceived again")

    monkeypatch.setattr(bonding, "_search", no_perception)
    out, _ = symmetry.merge_duplicates(moved, tol=0.2)
    assert sorted(b.key() for b in bonding.perceive(out)) == before


@pytest.mark.skipif(not MOF5.exists(), reason="sample not present")
def test_mof5s_zinc_dragged_off_its_axis_merges_back_to_32():
    """The report: Zn1 at (0.29305, 0.29019, 0.20709), 96 zinc, and
    "no duplicates found" at 0.05, 0.2 and 0.5 A."""
    from xtal.io import read_cif

    structure, _ = symmetry.asymmetrize(read_cif(MOF5))
    moved = structure.copy()
    MoveSites({0: np.array([0.29305, 0.29019, 0.20709])}).do(
        Host(moved))
    assert len(p1.expand(moved).indices_of_site(0)) == 96
    assert not symmetry.merge_duplicates(moved)[1].snapped  # 0.1 A apart
    out, report = symmetry.merge_duplicates(moved, tol=0.2)
    assert len(p1.expand(out).indices_of_site(0)) == 32
    assert p1.expand(out).n_atoms == 424
    x, y, z = out.sites[0].frac
    assert x == pytest.approx(y, abs=1e-9)
