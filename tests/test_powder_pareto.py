"""The Pareto sweep: Rietveld with energies at a list of weights, the
points no other beats on both counts, and the weight suggested."""

from __future__ import annotations

import math

import numpy as np
import pytest

from xtal.powder.data import PowderError
from xtal.powder.pareto import (
    DEFAULT_WEIGHTS,
    ParetoPoint,
    front,
    knee,
    parse_weights,
)


class _Fit:
    """What a point reads off its fit, and nothing else."""

    def __init__(self, rwp, energy, converged=True):
        self.rwp, self.energy = rwp, energy
        self.converged = converged
        self.status = "converged" if converged else "stopped at 5 steps"


def _points(*pairs):
    return [ParetoPoint(0.1 * k, _Fit(rwp, energy))
            for k, (rwp, energy) in enumerate(pairs)]


def test_the_front_keeps_only_non_dominated_points():
    """(0.16, 6) is beaten by (0.11, 6) on Rwp and loses on nothing,
    so it is off the front; a tie on both is two points on it."""
    points = _points((0.10, 10.0), (0.11, 6.0), (0.16, 6.0),
                     (0.15, 3.0), (0.30, 2.9), (0.11, 6.0))
    assert front(points) == [0, 1, 3, 4, 5]


def test_an_unconverged_point_has_no_numbers_and_is_on_no_front():
    """A hole scored as a number would be a point of the front that is
    not there -- and, being "best" at whatever it stopped on, could
    push real points off it."""
    points = _points((0.10, 10.0), (0.20, 2.0))
    points.append(ParetoPoint(0.9, _Fit(0.01, 0.0, converged=False)))
    assert math.isnan(points[2].rwp) and math.isnan(points[2].energy)
    assert front(points) == [0, 1]


def test_the_knee_is_the_point_furthest_from_the_chord():
    """An L: the pattern gets almost all of its fit back for a little
    energy at (0.11, 3), and that corner is the suggestion."""
    points = _points((0.10, 10.0), (0.105, 6.0), (0.11, 3.0),
                     (0.20, 2.5), (0.30, 2.0))
    assert knee(points) == 2


def test_a_front_with_nothing_off_its_chord_suggests_no_weight():
    assert knee(_points((0.1, 3.0), (0.2, 2.0), (0.3, 1.0))) is None
    assert knee(_points((0.1, 3.0), (0.2, 2.0))) is None


def test_weights_are_read_sorted_and_each_once():
    assert parse_weights("0.5, 0 0.1,0.5") == (0.0, 0.1, 0.5)
    assert parse_weights("") == DEFAULT_WEIGHTS
    with pytest.raises(PowderError, match="1.5"):
        parse_weights("0, 1.5")
    with pytest.raises(PowderError, match="numbers"):
        parse_weights("0, half")


# ----------------------------------------------------------------------
#  A real sweep
# ----------------------------------------------------------------------

def _rutile():
    from xtal.core.lattice import Lattice
    from xtal.core.structure import Bond, Structure

    structure = Structure.from_arrays(
        Lattice.from_parameters(4.5940, 4.5940, 2.9590, 90, 90, 90),
        ["Ti", "O"], [[0.0, 0.0, 0.0], [0.29, 0.29, 0.0]],
        space_group="P4_2/mnm")
    structure.add_bond(Bond(0, 1))
    return structure


def _uff(structure):
    from xtal.ff.registry import ENGINES

    return ENGINES.build("uff", structure)


@pytest.fixture(scope="module")
def rutile_data(rutile_xy_shared):
    pytest.importorskip("rietx")
    from xtal.powder.data import PowderData

    return PowderData.from_xy(rutile_xy_shared)


def test_a_sweep_walks_from_the_pattern_to_the_energy(rutile_data):
    """Rwp can only rise with the weight and the energy only fall,
    point by point -- each is the minimum of an objective that weighs
    the energy more than the last one's did."""
    from xtal.powder.data import Radiation
    from xtal.powder.pareto import sweep

    written = []
    result = sweep(_rutile(), rutile_data, Radiation("cu"), _uff,
                   weights=(0.0, 0.3, 0.7, 1.0), on_point=written.append)
    assert [p.weight for p in result.points] == [0.0, 0.3, 0.7, 1.0]
    # w = 1 is the relaxation that sets the scale, so it is first
    assert [p.weight for p in written] == [1.0, 0.0, 0.3, 0.7]
    assert all(p.converged for p in result.points)
    rwp = [p.rwp for p in result.points]
    energy = [p.energy for p in result.points]
    assert rwp == sorted(rwp)
    assert energy == sorted(energy, reverse=True)
    assert result.points[-1].energy == pytest.approx(
        result.scale.relaxed)
    assert result.front == [0, 1, 2, 3]
    for point in result.points:
        assert len(point.fit.structure.sites) == 2


def test_a_stopped_sweep_leaves_every_finished_point_on_disk(
        tmp_path, rutile_xy_shared):
    """Stop after the second point: both are written -- a CIF each and
    their rows of points.csv -- and the run says it stopped rather
    than failing."""
    pytest.importorskip("rietx")
    from xtal.io import write_cif
    from xtal.modules import MODULES
    from xtal.modules import record as module_record
    from xtal.modules.job import Cancellation, Job
    from xtal.workspace import Workspace

    source = tmp_path / "rutile.cif"
    write_cif(_rutile(), source)
    entry = Workspace.create(tmp_path / "ws").add_structure(source)
    module = MODULES.get("pxrd")
    action = module.action("pareto")
    params = {"xy": str(rutile_xy_shared), "weights": "0, 0.2, 0.5, 1",
              "engine": "uff", "frame_interval": -1}
    folder = module_record.open_run(entry, module, action, params,
                                    _rutile())
    cancel = Cancellation()
    job = Job(structure=_rutile(), folder=folder, params=params,
              cancel=cancel)

    def on_say(text):
        # the third point's first word: two are on disk by now
        if text.startswith("[3/"):
            cancel.cancel()

    job.say = on_say
    result = action.run(job)
    assert result.ok and result.cancelled, result.message
    assert result.message.startswith("stopped")
    finished = result.answer.points
    assert [p.weight for p in finished] == [0.0, 1.0]
    rows = (folder.path / "points.csv").read_text().splitlines()
    assert [row.split(",")[0] for row in rows[1:]] == ["1", "0"]
    for point in finished:
        assert (folder.path / f"w-{point.weight:.3f}.cif").exists()
    assert (folder.path / "report.json").exists()


def test_the_report_draws_the_front_and_opens_each_point(
        tmp_path, rutile_xy_shared):
    """The curve's points carry their CIFs, as a scan's profile does,
    and the report reopens from the run folder."""
    pytest.importorskip("rietx")
    from xtal.io import write_cif
    from xtal.modules import MODULES
    from xtal.modules import record as module_record
    from xtal.modules import report as module_report
    from xtal.modules.job import Job
    from xtal.workspace import Workspace

    source = tmp_path / "rutile.cif"
    write_cif(_rutile(), source)
    entry = Workspace.create(tmp_path / "ws").add_structure(source)
    module = MODULES.get("pxrd")
    action = module.action("pareto")
    params = {"xy": str(rutile_xy_shared), "weights": "0, 0.5, 1",
              "engine": "uff", "frame_interval": -1}
    folder = module_record.open_run(entry, module, action, params,
                                    _rutile())
    result = action.run(Job(structure=_rutile(), folder=folder,
                            params=params))
    assert result.ok, result.message
    curve = result.report.curves[0]
    assert curve.n_points == 3
    assert all(curve.path_at(0, k).endswith(".cif") for k in range(3))
    # sorted by energy, so the energy-alone end is first
    assert curve.x[0] == pytest.approx(result.answer.points[-1].energy)
    assert np.all(np.isfinite(curve.series[0][1]))
    again = module_report.load(folder.path / "report.json")
    assert again.curves[0].path_at(0, 0) == curve.path_at(0, 0)
