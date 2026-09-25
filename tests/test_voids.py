"""Channels and pockets on the distance grid.

Every answer here was checked against Zeo++ 0.3 with ``-ha`` and its
own radii, at an N2 probe of 1.86 A: MOF-5, HKUST-1 and MIL-53 are one
channel and no pockets, ZIF-8 is pockets only (its windows are 3.27 A
across and N2 needs 3.72), UiO-66 is one channel through windows that
clear N2 by 0.045 A on the radius.  The frameworks are real because
the failures were: each rule the module rejected got one of these
wrong.

Nothing here needs Zeo++, and nothing here imports Qt.
"""

from functools import cache
from pathlib import Path

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.analysis import porosity, voids
from xtal.analysis.grid import distance_grid
from xtal.io.cif_reader import read_cif

SAMPLES = Path(__file__).resolve().parents[1] / "resources" / "samples"
NITROGEN = 1.86


@cache
def split(name, spacing=0.4, probe=NITROGEN):
    structure = read_cif(SAMPLES / f"{name}.cif")
    field = distance_grid(structure, porosity.zeo_radius, spacing=spacing)
    return voids.classify(structure, field, porosity.zeo_radius, probe)


def test_mof5_is_one_channel_and_no_pockets():
    found = split("MOF-5")
    assert (found.n_channels, found.n_pockets) == (1, 0)
    assert not found.borderline
    # Zeo++'s AV fraction is 0.3918.
    assert found.channels.mean() == pytest.approx(0.3918, abs=0.002)


def test_zif8_windows_do_not_let_nitrogen_through():
    """Joining all 26 neighbours on their endpoints alone stepped
    diagonally between the atoms of a 3.27 A window and called ZIF-8
    one channel.  Zeo++'s NAV fraction is 0.1916."""
    found = split("ZIF-8")
    assert found.n_channels == 0
    assert found.n_pockets >= 1
    assert not found.channels.any()
    assert found.pockets.mean() == pytest.approx(0.1916, abs=0.002)


def test_a_window_clear_of_the_probe_is_not_borderline():
    """ZIF-8's windows are 0.225 A too small for N2 on the radius, more
    than half a 0.4 A step, so the grid can say so with confidence."""
    assert not split("ZIF-8").borderline


def test_hkust1_small_cages_are_not_false_pockets():
    """Joining face neighbours only closed windows that are open, and
    left HKUST-1 with 104 pockets that Zeo++ does not have."""
    found = split("HKUST1")
    assert (found.n_channels, found.n_pockets) == (1, 0)


def test_a_one_dimensional_channel_percolates_along_its_axis():
    """MIL-53's channels run along one axis only, so the channel is
    found by the union-find's offsets and not by filling the cell."""
    found = split("MIL53")
    assert found.n_channels == 1
    assert found.n_pockets == 0


def test_a_window_within_half_a_spacing_of_the_probe_is_borderline():
    """UiO-66's windows clear N2 by 0.045 A.  A 0.3 A grid puts no point
    in that gap and calls the cages sealed; it must say it cannot tell
    rather than report pockets with confidence."""
    found = split("UIO66", spacing=0.3)
    assert found.borderline


def test_the_same_window_seen_by_a_grid_that_resolves_it_is_open():
    found = split("UIO66", spacing=0.4)
    assert found.n_channels == 1


def test_a_sealed_box_is_a_pocket_and_an_open_one_a_channel():
    """A cage of atoms with no way out, and the same cage with the
    walls taken away: the smallest case where the answer is known
    without any program's word for it."""
    side = 12.0
    wall = [(x, y, z) for x in np.linspace(0, 1, 13)[:-1]
            for y in np.linspace(0, 1, 13)[:-1]
            for z in (0.0,)]
    walls = sorted({tuple(np.roll(p, r)) for p in wall for r in range(3)})
    sealed = Structure.from_arrays(Lattice.cubic(side),
                                   ["C"] * len(walls), walls)
    radius = {"C": 1.7}.get
    field = distance_grid(sealed, radius, spacing=0.4)
    found = voids.classify(sealed, field, radius, 1.0)
    assert (found.n_channels, found.n_pockets) == (0, 1)

    rods = [p for p in walls if sum(c == 0.0 for c in p) >= 2]
    open_ = Structure.from_arrays(Lattice.cubic(side),
                                  ["C"] * len(rods), rods)
    field = distance_grid(open_, radius, spacing=0.4)
    found = voids.classify(open_, field, radius, 1.0)
    assert (found.n_channels, found.n_pockets) == (1, 0)


def test_the_split_covers_exactly_the_space_the_probe_fits_in():
    """Every open point is channel or pocket and none is both: a point
    lost between them would vanish from AV and NAV alike."""
    structure = read_cif(SAMPLES / "ZIF-8.cif")
    field = distance_grid(structure, porosity.zeo_radius, spacing=0.4)
    found = voids.classify(structure, field, porosity.zeo_radius,
                           NITROGEN)
    assert not (found.channels & found.pockets).any()
    assert np.array_equal(found.channels | found.pockets,
                          field >= NITROGEN)


def test_an_empty_cell_is_one_channel():
    empty = Structure.from_arrays(Lattice.cubic(8.0), [], np.empty((0, 3)))
    field = distance_grid(empty, {}.get, spacing=1.0)
    found = voids.classify(empty, field, {}.get, NITROGEN)
    assert (found.n_channels, found.n_pockets) == (1, 0)
