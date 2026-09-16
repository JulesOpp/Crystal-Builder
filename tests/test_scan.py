"""The relaxed scan driver.

The landscape it draws is only as honest as its bookkeeping, so most
of what is pinned here is bookkeeping: that every point is visited,
that each starts from its neighbour and not from a geometry an axis
away, that a tied cell parameter is carried along, that a point which
failed does not quietly become a zero.
"""

from __future__ import annotations

import numpy as np
import pytest

from xtal.core import p1
from xtal.core.lattice import Lattice
from xtal.ff import coordinates as co
from xtal.ff import scan as sc
from xtal.ff.registry import ENGINES


def _build(structure):
    return ENGINES.build("uff", structure)


def _run(structure, axes, **kwargs):
    kwargs.setdefault("direction", "forward")
    kwargs.setdefault("method", "lbfgs")
    kwargs.setdefault("max_steps", 20)
    used = sc.plan(structure, axes,
                   seed=kwargs.get("seed", "previous"),
                   direction=kwargs["direction"])
    return sc.collect(sc.scan(_build, structure, axes, **kwargs),
                      used)


@pytest.fixture
def cell_axes(quartz):
    a, _b, c = quartz.lattice.parameters[:3]
    return [sc.Axis.over(co.CellParameter("a"), a * 0.97, a * 1.03, 3),
            sc.Axis.over(co.CellParameter("c"), c * 0.97, c * 1.03, 3)]


# ----------------------------------------------------------------------
#  The plan
# ----------------------------------------------------------------------

def test_scanning_every_free_parameter_fixes_the_cell(quartz):
    """The measurement the whole design turns on.

    P3_221 leaves a and c free and nothing else, so scanning both
    determines the cell completely -- no strain variables, exact, and
    on an engine without an analytic stress twelve energy evaluations
    a step cheaper.
    """
    a, _b, c = quartz.lattice.parameters[:3]
    used = sc.plan(quartz, [
        sc.Axis.over(co.CellParameter("a"), a, a * 1.02, 2),
        sc.Axis.over(co.CellParameter("c"), c, c * 1.02, 2)])
    assert not used.relax_cell


def test_scanning_some_of_them_leaves_the_rest_to_relax(quartz):
    """Scanning a alone must not silently freeze c as well: that is
    the profile of the constraint rather than of the crystal."""
    a = quartz.lattice.parameters[0]
    used = sc.plan(quartz,
                   [sc.Axis.over(co.CellParameter("a"), a, a * 1.02, 2)])
    assert used.relax_cell
    assert used.freedom.held == ("a",)


def test_a_volume_axis_relaxes_the_shape(quartz):
    """Which is the point of scanning volume rather than parameters."""
    volume = quartz.lattice.volume
    used = sc.plan(quartz, [sc.Axis.over(co.CellVolume(), volume,
                                         volume * 1.1, 2)])
    assert used.relax_cell
    assert used.freedom.held == ("volume",)


def test_a_parameter_the_group_does_not_leave_free_is_refused(
        quartz):
    """b follows a in a trigonal group, so scanning b is asking for a
    crystal whose own operations no longer map it onto itself."""
    with pytest.raises(sc.ScanError, match="not free"):
        sc.plan(quartz, [sc.Axis.over(co.CellParameter("b"),
                                      4.0, 5.0, 2)])


def test_scanning_the_volume_and_a_parameter_together_is_refused(
        quartz):
    """Setting one changes the other; there is no answer to give."""
    volume = quartz.lattice.volume
    a = quartz.lattice.parameters[0]
    with pytest.raises(sc.ScanError, match="ambiguous"):
        sc.plan(quartz, [sc.Axis.over(co.CellVolume(), volume,
                                      volume * 1.1, 2),
                         sc.Axis.over(co.CellParameter("a"), a,
                                      a * 1.02, 2)])


def test_a_scan_takes_one_or_two_axes(quartz):
    a = quartz.lattice.parameters[0]
    axis = sc.Axis.over(co.CellParameter("a"), a, a * 1.02, 2)
    with pytest.raises(sc.ScanError, match="one or two"):
        sc.plan(quartz, [axis, axis, axis])


def test_the_plan_says_what_it_held(quartz, cell_axes):
    """Written into every report, because a profile that does not say
    what was fixed while it was taken cannot be read."""
    said = sc.plan(quartz, cell_axes).describe()
    assert "held fixed" in said
    assert "previous" in said


# ----------------------------------------------------------------------
#  The grid
# ----------------------------------------------------------------------

def test_the_raster_never_steps_more_than_one_cell(quartz):
    """A plain nested loop jumps a whole axis at every row end, which
    is the seeding silently not happening once per row."""
    for index, following in zip(order := sc.raster((4, 5)), order[1:],
                               strict=False):
        assert sum(abs(a - b) for a, b in
                   zip(index, following, strict=True)) == 1


def test_the_raster_visits_every_cell_once(quartz):
    order = sc.raster((4, 5))
    assert len(order) == 20
    assert len(set(order)) == 20


def test_a_reverse_raster_ends_where_the_forward_one_began(quartz):
    forward = sc.raster((3, 4))
    assert sc.raster((3, 4), reverse=True) == forward[::-1]


def test_a_two_axis_scan_visits_every_point_of_the_grid(quartz,
                                                        cell_axes):
    result = _run(quartz, cell_axes)
    assert len(result.points) == 9
    assert {p.index for p in result.points} == {
        (i, j) for i in range(3) for j in range(3)}


def test_both_directions_give_two_branches(quartz, cell_axes):
    """Kept apart rather than averaged: where they differ is the
    hysteresis, which is the interesting part of a breathing
    framework and the thing a single curve hides."""
    result = _run(quartz, cell_axes, direction="both")
    assert len(result.branch("forward")) == 9
    assert len(result.branch("reverse")) == 9


def test_the_way_back_starts_where_the_way_out_finished(quartz,
                                                        cell_axes):
    """A hysteresis loop is one continuous path out and back.

    Started from the input instead, the return branch's first point is
    a jump the whole width of the scan: on a volume scan of MIL-53
    that left the reverse branch 606 kcal/mol above the forward one at
    the same volume, for three points, before it found its way back.
    Only the *first* point is borrowed -- two branches sharing
    geometries the whole way along would have no hysteresis left to
    measure.
    """
    seen = []

    def spy(structure):
        seen.append(structure.frac.copy())
        return _build(structure)

    used = sc.plan(quartz, cell_axes, direction="both")
    points = list(sc.scan(spy, quartz, cell_axes, direction="both",
                          method="lbfgs", max_steps=20))
    sc.collect(iter(points), used)
    half = len(points) // 2
    # The reverse branch opens on the geometry the forward branch left
    # at that same cell, not on the structure the scan was given.
    assert not np.allclose(seen[half], quartz.frac)


def test_the_return_branch_opens_on_the_last_point_of_the_first(
        quartz, cell_axes):
    """The loop closed, asserted on the one geometry that says so.

    The reverse raster begins at the cell the forward raster ended on,
    so its first point must open on the geometry that point left --
    not on the structure the scan was handed.
    """
    seen = []

    def spy(structure):
        seen.append(structure.frac.copy())
        return _build(structure)

    used = sc.plan(quartz, cell_axes, direction="both")
    result = sc.collect(
        sc.scan(spy, quartz, cell_axes, direction="both",
                method="lbfgs", max_steps=30), used)
    forward = result.branch("forward")
    half = len(seen) // 2
    assert np.allclose(seen[half], forward[-1].frac)
    assert not np.allclose(seen[half], quartz.frac)


def test_a_point_starts_from_the_relaxed_geometry_of_its_neighbour(
        quartz, cell_axes):
    """Seeding is what makes a scan of a real framework affordable.

    Asserted on the geometry handed to the engine rather than on how
    many steps were saved: on a two-site cell every relaxation
    converges in eight steps whatever it starts from, so a timing
    argument here would pass or fail on the fixture rather than on
    the behaviour.
    """
    seen = []

    def spy(structure):
        seen.append(structure.frac.copy())
        return _build(structure)

    used = sc.plan(quartz, cell_axes, direction="forward")
    sc.collect(sc.scan(spy, quartz, cell_axes, direction="forward",
                       method="lbfgs", max_steps=20), used)
    start = quartz.frac
    assert np.allclose(seen[0], start)
    # Every later point arrives somewhere the relaxation put it.
    assert all(not np.allclose(frac, start) for frac in seen[1:])


def test_restarting_from_the_input_really_does_restart(quartz,
                                                       cell_axes):
    """The other seed policy, and the knob that makes path dependence
    the user's choice instead of a hidden property of the driver."""
    seen = []

    def spy(structure):
        seen.append(structure.frac.copy())
        return _build(structure)

    used = sc.plan(quartz, cell_axes, seed="input",
                   direction="forward")
    sc.collect(sc.scan(spy, quartz, cell_axes, seed="input",
                       direction="forward", method="lbfgs",
                       max_steps=20), used)
    assert all(np.allclose(frac, quartz.frac) for frac in seen)


# ----------------------------------------------------------------------
#  What comes out
# ----------------------------------------------------------------------

def test_scanning_a_in_a_trigonal_group_moves_b_with_it(quartz):
    """Without ``CellConstraint.apply`` the cell stops being trigonal
    and the stored operations stop mapping the structure onto itself.
    Nothing else reports that."""
    a = quartz.lattice.parameters[0]
    result = _run(quartz, [sc.Axis.over(co.CellParameter("a"),
                                        a * 1.05, a * 1.05, 1)])
    parameters = result.points[0].parameters
    assert parameters[1] == pytest.approx(parameters[0], rel=1e-9)
    assert parameters[5] == pytest.approx(120.0, abs=1e-6)


def test_a_fixed_cell_point_lands_exactly_on_its_target(quartz,
                                                        cell_axes):
    """With no strain variables the cell is set, not relaxed towards,
    so target and achieved must agree to the last figure."""
    for point in _run(quartz, cell_axes).points:
        assert point.achieved == pytest.approx(point.targets,
                                               abs=1e-12)


def test_a_held_distance_lands_on_its_target(quartz):
    """The internal half of the same promise."""
    cell = p1.expand(quartz)
    matrix = quartz.lattice.matrix
    distance = co.internal(quartz, cell, "distance", [(0,), (3,)])
    start = distance.value(cell.frac @ matrix, matrix)
    result = _run(quartz, [sc.Axis.over(distance, start,
                                        start + 0.1, 3)])
    for point in result.points:
        assert point.achieved[0] == pytest.approx(point.targets[0],
                                                  abs=1e-6)


def test_the_landscape_has_its_minimum_where_the_optimiser_does(
        quartz):
    """The consistency check between the two halves of the force
    field: relax the cell freely, scan a grid centred on where that
    landed, and the middle of the grid must come out lowest.

    Centred on the *relaxed* cell and not the experimental one --
    UFF puts quartz's c 1.5% short of the measured value, which is a
    fact about UFF and would make this a test of the force field
    rather than of the scan.
    """
    from xtal.ff import optimize
    relaxed = Lattice(optimize.run(
        _build(quartz), quartz, method="lbfgs", max_steps=200,
        relax_cell=True).matrix).parameters
    axes = [sc.Axis.over(co.CellParameter("a"), relaxed[0] * 0.97,
                         relaxed[0] * 1.03, 3),
            sc.Axis.over(co.CellParameter("c"), relaxed[2] * 0.97,
                         relaxed[2] * 1.03, 3)]
    result = _run(quartz, axes, max_steps=60)
    assert result.minimum().index == (1, 1)


def test_energies_are_reported_from_the_lowest_finished_point(
        quartz, cell_axes):
    result = _run(quartz, cell_axes, max_steps=40)
    relative = result.relative()
    assert np.nanmin(relative) == pytest.approx(0.0, abs=1e-9)
    assert np.nanmax(relative) > 0.0


@pytest.mark.slow
def test_a_volume_scan_reports_the_pressure_it_implies(quartz):
    """P = -dE/dV, and it must cross zero at the energy minimum --
    which is the definition of the equilibrium volume and the cheapest
    check that the whole chain is consistent."""
    volume = quartz.lattice.volume
    result = _run(quartz, [sc.Axis.over(co.CellVolume(), volume * 0.92,
                                        volume * 1.08, 5)],
                  max_steps=50)
    volumes, pressure = result.pressure()
    assert pressure[0] > 0.0        # compressed: pushing back out
    assert pressure[-1] < 0.0       # expanded: pulling back in
    lowest = result.minimum().volume
    crossing = float(np.interp(0.0, pressure[::-1], volumes[::-1]))
    assert crossing == pytest.approx(lowest, rel=0.05)


def test_a_scan_over_something_that_is_not_a_volume_has_no_pressure(
        quartz, cell_axes):
    """-dE/dV of a scan over a bond length is not a pressure, and
    reporting one would be a number nobody could use."""
    assert _run(quartz, cell_axes).pressure() is None


def test_a_point_that_did_not_finish_is_not_a_number(quartz):
    """A hole in the landscape stays a hole.  Plotted as a zero it
    would be the deepest point of every scan it appeared in."""
    a = quartz.lattice.parameters[0]
    axes = [sc.Axis.over(co.CellParameter("a"), a * 0.97, a * 1.03, 3)]
    used = sc.plan(quartz, axes, direction="forward")

    def explode(structure):
        raise ValueError("no parameters for this")

    result = sc.collect(sc.scan(explode, quartz, axes,
                                direction="forward"), used)
    assert all(not p.finished for p in result.points)
    assert np.all(np.isnan(result.grid()))
    assert result.minimum() is None


def test_a_failed_point_does_not_seed_the_next_one(quartz):
    """Otherwise one bad cell takes the rest of its row with it."""
    done = {(0, 0): "first", (0, 2): "third"}
    assert sc._seeded_from(done, (0, 3), "input") == "third"
    assert sc._seeded_from({}, (0, 3), "input") == "input"


def test_stopping_a_scan_keeps_the_points_already_finished(quartz,
                                                           cell_axes):
    """A scan is an overnight job.  Stop has to leave a landscape
    behind rather than lose one."""
    from xtal.modules.job import Cancellation

    cancel = Cancellation()
    points = []
    for point in sc.scan(_build, quartz, cell_axes,
                         direction="forward", cancel=cancel,
                         method="lbfgs", max_steps=20):
        points.append(point)
        if len(points) == 4:
            cancel.cancel()
    assert len(points) == 4
    assert all(p.finished for p in points)


def test_an_axis_of_one_point_is_allowed(quartz):
    """A one-by-N scan is a perfectly ordinary thing to want and the
    linspace of a single point is not."""
    a = quartz.lattice.parameters[0]
    axis = sc.Axis.over(co.CellParameter("a"), a, a, 1)
    assert axis.values == (a,)


def test_an_axis_of_no_points_is_refused(quartz):
    with pytest.raises(sc.ScanError, match="at least one"):
        sc.Axis.over(co.CellParameter("a"), 4.0, 5.0, 0)


def test_an_unknown_seed_or_direction_names_the_ones_there_are(
        quartz, cell_axes):
    with pytest.raises(sc.ScanError, match="seed policy"):
        sc.plan(quartz, cell_axes, seed="sideways")
    with pytest.raises(sc.ScanError, match="direction"):
        sc.plan(quartz, cell_axes, direction="widdershins")


@pytest.mark.slow
def test_a_cell_scan_of_a_real_framework_runs(tmp_path):
    """Small, and on the smallest real framework in the tree: the
    point is that the whole chain survives a structure with 210 atoms
    and a P1 group, not that the landscape means anything at 30
    steps."""
    from xtal.io import read_cif
    structure = read_cif("resources/samples/zn_oac.cif")
    volume = structure.lattice.volume
    axes = [sc.Axis.over(co.CellVolume(), volume * 0.98,
                         volume * 1.02, 3)]
    result = _run(structure, axes, max_steps=30)
    assert len(result.finished()) == 3
    assert all(Lattice(p.matrix).volume == pytest.approx(
        p.targets[0], rel=1e-3) for p in result.points)
