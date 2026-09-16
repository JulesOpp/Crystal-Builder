"""The relaxed scan as a module: what it is asked, what it leaves on
disk, and what comes back.

The disk half carries most of the weight.  A scan is an overnight job,
so a point that finished has to be on disk before the next one starts
-- Stop, a crash or a full disk must leave a landscape behind rather
than lose one.
"""

from __future__ import annotations

import numpy as np
import pytest

from xtal.core import p1
from xtal.io import write_cif
from xtal.modules import scan as module
from xtal.modules.job import Cancellation, Job
from xtal.modules.registry import MODULES
from xtal.modules.report import Curve, Surface
from xtal.params import ParamError
from xtal.workspace import Workspace


@pytest.fixture
def folder(tmp_path, quartz):
    source = tmp_path / "quartz.cif"
    write_cif(quartz, source)
    entry = Workspace.create(tmp_path / "ws").add_structure(source)
    return entry.next_run("scan", "scan")


def _job(structure, folder=None, **params):
    defaults = dict(engine="uff", method="lbfgs", max_steps=30,
                    tolerance=0.05, direction="forward",
                    seed="previous", axis1="", axis2="",
                    axis1_steps=3, axis2_steps=3)
    defaults.update(params)
    job = Job(structure=structure, folder=folder, params=defaults,
              cancel=Cancellation())
    job.on_progress = lambda _text: None
    return job


def _cell_scan(quartz, folder=None, **extra):
    a, _b, c = quartz.lattice.parameters[:3]
    return _job(quartz, folder,
                axis1="a", axis1_start=a * 0.97, axis1_stop=a * 1.03,
                axis2="c", axis2_start=c * 0.97, axis2_stop=c * 1.03,
                **extra)


# ----------------------------------------------------------------------
#  Saying what to scan
# ----------------------------------------------------------------------

def test_a_cell_parameter_is_written_as_its_name(quartz):
    cell = p1.expand(quartz)
    assert module.parse_axis(quartz, cell, "a").label == "a"
    assert module.parse_axis(quartz, cell, "volume").label == "volume"


def test_an_internal_coordinate_is_written_as_its_atoms(quartz):
    cell = p1.expand(quartz)
    torsion = module.parse_axis(quartz, cell, "torsion 0 1 2 3")
    assert torsion.label == "torsion 0-1-2-3"


def test_a_group_of_atoms_is_written_with_commas(quartz):
    """Which is how "the centroid of these three" is said in one word
    on a command line and in a log."""
    cell = p1.expand(quartz)
    distance = module.parse_axis(quartz, cell, "distance 0,1,2 3,4,5")
    assert distance.label == "distance {0,1,2}-{3,4,5}"


def test_the_grammar_is_the_same_everywhere(quartz):
    """One way of writing an axis for the dialog, the command line and
    the log, so a scan can be re-run from the line it printed."""
    cell = p1.expand(quartz)
    for spec in ("a", "volume", "distance 0 3", "angle 0 1 2",
                 "torsion 0 1 2 3", "plane 0,1,2 3,4,5"):
        assert module.parse_axis(quartz, cell, spec) is not None


def test_a_coordinate_nobody_can_read_is_refused_by_name(quartz):
    cell = p1.expand(quartz)
    with pytest.raises(ParamError, match="not a coordinate"):
        module.parse_axis(quartz, cell, "wibble 1 2")
    with pytest.raises(ParamError, match="takes 4 anchors"):
        module.parse_axis(quartz, cell, "torsion 0 1 2")


def test_a_scan_with_no_axis_is_refused(quartz):
    with pytest.raises(ParamError, match="at least one axis"):
        module.run_scan(_job(quartz))


# ----------------------------------------------------------------------
#  What it leaves on disk
# ----------------------------------------------------------------------

def test_a_scan_writes_one_cif_for_every_finished_point(quartz,
                                                        folder):
    module.run_scan(_cell_scan(quartz, folder))
    written = sorted(p.name for p in folder.path.glob("forward-*.cif"))
    assert len(written) == 9
    assert written[0] == "forward-00-00.cif"


def test_a_scan_writes_a_row_for_every_point(quartz, folder):
    module.run_scan(_cell_scan(quartz, folder, direction="both"))
    lines = [line for line in
             (folder.path / "scan.csv").read_text().splitlines()
             if line]
    assert len(lines) == 1 + 18


def test_the_csv_reports_the_achieved_value_beside_the_target(
        quartz, folder):
    """So a kink in the landscape can be told from a cell that drifted
    off the point it was supposed to be at."""
    module.run_scan(_cell_scan(quartz, folder))
    header = (folder.path / "scan.csv").read_text().splitlines()[0]
    assert "a target" in header
    assert "a achieved" in header


def test_the_csv_names_the_file_behind_each_row(quartz, folder):
    """What makes a landscape worth keeping: every point is a
    structure somebody can open again."""
    module.run_scan(_cell_scan(quartz, folder))
    text = (folder.path / "scan.csv").read_text()
    assert "forward-01-01.cif" in text


def test_a_point_is_on_disk_before_the_next_one_starts(quartz,
                                                       folder):
    """The whole reason writing is per-point.  Counting the files
    from inside the run is the only way to see the difference between
    this and saving everything at the end."""
    seen = []
    job = _cell_scan(quartz, folder)
    job.on_progress = lambda _t: seen.append(
        len(list(folder.path.glob("forward-*.cif"))))
    module.run_scan(job)
    assert seen[-1] > 1
    assert seen == sorted(seen)


def test_a_stopped_scan_leaves_the_points_it_finished(quartz,
                                                      folder):
    job = _cell_scan(quartz, folder)
    counted = []

    def stop_after_four(_text):
        counted.append(1)
        if len(counted) > 4:
            job.cancel.cancel()

    job.on_progress = stop_after_four
    result = module.run_scan(job)
    written = list(folder.path.glob("forward-*.cif"))
    assert 0 < len(written) < 9
    assert "Stopped" in result.message
    assert result.cancelled


def test_a_scan_runs_without_a_workspace(quartz):
    """Nothing to write to is not an error state: the answer is a
    landscape on screen, and where a file is saved is the user's to
    choose.  The same argument PXRD makes about its pattern."""
    result = module.run_scan(_cell_scan(quartz))
    assert result.report.surfaces
    assert not result.artifacts


# ----------------------------------------------------------------------
#  What comes back
# ----------------------------------------------------------------------

def test_a_two_axis_scan_reports_a_surface(quartz):
    report = module.run_scan(_cell_scan(quartz)).report
    assert len(report.surfaces) == 1
    assert isinstance(report.blocks[1], Surface)


def test_a_one_axis_scan_reports_a_curve_instead(quartz):
    volume = quartz.lattice.volume
    result = module.run_scan(_job(
        quartz, axis1="volume", axis1_start=volume * 0.97,
        axis1_stop=volume * 1.03, axis1_steps=3, max_steps=40))
    assert not result.report.surfaces
    assert isinstance(result.report.blocks[1], Curve)


def test_a_volume_scan_reports_the_pressure_beside_the_energy(
        quartz):
    volume = quartz.lattice.volume
    result = module.run_scan(_job(
        quartz, axis1="volume", axis1_start=volume * 0.95,
        axis1_stop=volume * 1.05, axis1_steps=4, max_steps=40))
    assert [c.title for c in result.report.curves] == [
        "Energy profile", "Pressure"]


def test_the_surface_puts_the_first_axis_down_the_rows(quartz):
    """Getting this backwards draws the right numbers about the wrong
    axes and looks entirely plausible on a square grid, so the two
    axes are given different lengths here."""
    a, _b, c = quartz.lattice.parameters[:3]
    result = module.run_scan(_job(
        quartz, axis1="a", axis1_start=a * 0.98, axis1_stop=a * 1.02,
        axis1_steps=2, axis2="c", axis2_start=c * 0.98,
        axis2_stop=c * 1.02, axis2_steps=3))
    surface = result.report.surfaces[0]
    assert surface.shape == (2, 3)
    assert surface.y_label.startswith("a")
    assert surface.x_label.startswith("c")


def test_the_surface_carries_the_file_behind_each_cell(quartz,
                                                       folder):
    """It is in the block rather than reconstructed by the panel
    because only the run knew where it wrote them."""
    result = module.run_scan(_cell_scan(quartz, folder))
    surface = result.report.surfaces[0]
    assert surface.path_at(0, 0).endswith("forward-00-00.cif")


def test_both_directions_come_back_as_two_sheets(quartz):
    """Kept apart rather than averaged: where they differ is the
    hysteresis."""
    result = module.run_scan(_cell_scan(quartz, direction="both"))
    surface = result.report.surfaces[0]
    assert [label for label, _z in surface.all_sheets()][1] == \
        "reverse"


def test_the_report_says_what_was_held(quartz):
    """A profile that does not say what was fixed while it was taken
    cannot be read."""
    said = module.run_scan(_cell_scan(quartz)).report.as_text()
    assert "held fixed" in said


def test_the_report_says_it_is_an_energy_and_not_a_free_energy(
        quartz):
    """The caveat that matters most for the case this was built for:
    at temperature the two can order a framework's phases
    differently."""
    said = module.run_scan(_cell_scan(quartz)).report.note
    assert "free energy" in said


def test_a_scan_does_not_replace_the_structure_it_ran_on(quartz):
    """A module handing back a geometry replaces the document it ran
    on, which is right for an optimisation and wrong for this: the
    tab is the crystal the landscape is *of*."""
    assert module.run_scan(_cell_scan(quartz)).structure is None


def test_unconverged_points_are_counted_in_the_message(quartz):
    """A landscape built from points that never relaxed is the most
    likely way for this feature to lie, so the count is in the
    sentence the user reads first."""
    result = module.run_scan(_cell_scan(quartz, max_steps=1))
    assert "did not reach the force tolerance" in result.message


def test_the_energies_on_the_surface_are_relative_to_the_lowest(
        quartz):
    surface = module.run_scan(_cell_scan(quartz)).report.surfaces[0]
    assert np.nanmin(surface.z) == pytest.approx(0.0, abs=1e-9)


# ----------------------------------------------------------------------
#  The registry
# ----------------------------------------------------------------------

def test_the_scan_is_registered_as_a_module():
    module_found, action = MODULES.find("scan.run")
    assert module_found.name == "scan"
    assert action.kind == "scan"
    assert action.label == "Relaxed scan..."


def test_the_action_offers_every_engine():
    _module_found, action = MODULES.find("scan.run")
    engines = dict(action.defaults())
    assert engines["engine"] == "uff"
