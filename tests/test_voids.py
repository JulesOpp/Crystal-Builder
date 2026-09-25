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

import json
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


# ------------------------------------------------------------ the numbers

REFERENCE = json.loads(
    (Path(__file__).parent / "data" / "zeopp_reference.json").read_text())


@cache
def measured(name, occupiable=True):
    structure = read_cif(SAMPLES / f"{name}.cif")
    field = distance_grid(structure, porosity.zeo_radius, spacing=0.4)
    found = voids.classify(structure, field, porosity.zeo_radius,
                           NITROGEN)
    return (voids.surface_area(structure, found, porosity.zeo_radius),
            voids.volume(structure, field, found, occupiable=occupiable))


@pytest.mark.parametrize("name", ["MOF-5", "HKUST1", "MIL53", "MFU4l"])
def test_surface_area_agrees_with_zeopp_within_two_percent(name):
    """Measured on the spheres, 0.1-0.9 % from Zeo++ on every sample.
    The marched mesh read 2-3 % low; a regression to it fails here."""
    area, _volume = measured(name)
    assert area.accessible_area == pytest.approx(REFERENCE[name]["asa"],
                                                 rel=0.02)
    assert area.inaccessible_area == 0


@pytest.mark.parametrize("name", ["MOF-5", "HKUST1", "MIL53", "MFU4l"])
def test_accessible_volume_agrees_with_zeopp_within_half_a_percent_of_the_cell(
        name):
    _area, volume = measured(name, occupiable=False)
    assert not volume.occupiable
    assert volume.accessible_fraction == pytest.approx(
        REFERENCE[name]["av"], abs=0.005)


def test_a_pocket_s_surface_is_counted_as_non_accessible():
    """ZIF-8's cages are sealed to N2: all its area is NASA, and an
    isotherm would see none of it."""
    area, _volume = measured("ZIF-8")
    assert area.accessible_area == 0
    assert area.inaccessible_area == pytest.approx(
        REFERENCE["ZIF-8"]["nasa"], rel=0.03)


def test_a_pocket_s_occupiable_volume_agrees_with_zeopp():
    """The case the probe-radius criterion got 0.021 of the cell wrong,
    because it ignored the open space between grid points."""
    _area, volume = measured("ZIF-8")
    cell = volume.volume
    mass = volume.density * cell * 1e-24
    fraction = volume.inaccessible_per_gram * mass / (cell * 1e-24)
    assert fraction == pytest.approx(REFERENCE["ZIF-8"]["ponav"],
                                     abs=0.01)
    assert volume.accessible_fraction == 0


def lone_atom(radius=2.0, side=12.0):
    structure = Structure.from_arrays(Lattice.cubic(side), ["C"],
                                      [[0.5, 0.5, 0.5]])
    return structure, {"C": radius}.get


def test_a_lone_sphere_has_the_area_and_volumes_geometry_says():
    """One atom in a box: the accessible surface is the sphere of
    r + probe, the centre's volume is the box outside it, and the
    probe occupies everything outside the atom itself -- a convex
    atom leaves no corner a probe cannot reach."""
    structure, radius_of = lone_atom()
    field = distance_grid(structure, radius_of, spacing=0.25)
    found = voids.classify(structure, field, radius_of, NITROGEN)
    area = voids.surface_area(structure, found, radius_of)
    box = 12.0 ** 3
    assert area.accessible_area == pytest.approx(
        4 * np.pi * (2.0 + NITROGEN) ** 2, rel=1e-3)
    centre = voids.volume(structure, field, found, occupiable=False)
    assert centre.accessible_fraction == pytest.approx(
        1 - 4 / 3 * np.pi * (2.0 + NITROGEN) ** 3 / box, abs=0.003)
    occupied = voids.volume(structure, field, found, occupiable=True)
    assert occupied.accessible_fraction == pytest.approx(
        1 - 4 / 3 * np.pi * 2.0 ** 3 / box, abs=0.003)


@pytest.mark.slow
def test_the_occupiable_volume_is_the_union_of_the_probe_spheres():
    """Zeo++'s -volpo reads MIL-53 at 0.6511 and HKUST-1 at 0.6535,
    but probe spheres centred on a 0.15 A grid of open points already
    cover 0.6629 and 0.6790 -- so the true value is at least that, and
    Zeo++ is short of it.  This is that brute force, re-derived on
    MIL-53: ours may not exceed what the spheres cover (plus the
    resolution of the fine grid) nor fall far below it."""
    structure = read_cif(SAMPLES / "MIL53.cif")
    lattice = structure.lattice
    fine = distance_grid(structure, porosity.zeo_radius, spacing=0.15)
    shape = np.array(fine.shape)
    open_ = np.argwhere(fine >= NITROGEN) / shape
    pad = (NITROGEN + 0.3) / np.linalg.norm(lattice.to_cart(np.eye(3)),
                                            axis=1)
    images = np.vstack([open_ + np.array(s) for s in np.ndindex(3, 3, 3)]
                       ) - 1
    images = images[np.all((images > -pad) & (images < 1 + pad), axis=1)]
    from scipy.spatial import cKDTree
    tree = cKDTree(lattice.to_cart(images))
    points = lattice.to_cart(np.random.default_rng(1).random((100000, 3)))
    nearest, _ = tree.query(points)
    covered = float((nearest <= NITROGEN).mean())

    _area, volume = measured("MIL53")
    assert volume.accessible_fraction <= covered + 0.01
    assert volume.accessible_fraction >= covered - 0.006
    assert volume.accessible_fraction > REFERENCE["MIL53"]["poav"]


def test_the_same_seed_gives_the_same_area():
    structure, radius_of = lone_atom()
    field = distance_grid(structure, radius_of, spacing=0.5)
    found = voids.classify(structure, field, radius_of, NITROGEN)
    first = voids.surface_area(structure, found, radius_of, seed=4)
    again = voids.surface_area(structure, found, radius_of, seed=4)
    assert first.accessible_area == again.accessible_area


def test_density_and_per_gram_values_are_zeopp_s():
    """The per-gram columns are the ones a paper quotes; a wrong mass
    or a unit slip would move all of them and none of the fractions."""
    area, volume = measured("MOF-5")
    assert volume.density == pytest.approx(REFERENCE["MOF-5"]["density"],
                                           rel=1e-3)
    # Zeo++: 3644.13 m^2/g for 3727.11 A^2; 0.662858 cm^3/g for AV.
    assert area.accessible_per_gram / area.accessible_area == \
        pytest.approx(3644.13 / 3727.11, rel=1e-3)
    centre = measured("MOF-5", occupiable=False)[1]
    assert centre.accessible_per_gram / centre.accessible_fraction == \
        pytest.approx(0.662858 / 0.39176, rel=1e-3)
