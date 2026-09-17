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
from xtal.ff.registry import ENGINES
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


def test_a_group_of_atoms_is_written_with_pluses(quartz):
    """Which is how "the centroid of these three" is said in one word
    on a command line and in a log."""
    cell = p1.expand(quartz)
    distance = module.parse_axis(quartz, cell,
                                 "distance 0+1+2, 3+4+5")
    assert distance.label == "distance {0+1+2}-{3+4+5}"


def test_a_comma_separates_two_atoms(quartz):
    """"32, 33" is what a person writes for the two ends of a
    distance, and what Add the selection writes."""
    cell = p1.expand(quartz)
    for spec in ("distance 0, 3", "distance 0,3", "distance 0 3"):
        distance = module.parse_axis(quartz, cell, spec)
        assert [a.atoms for a in distance.anchors] == [(0,), (3,)]


def test_an_axis_written_in_the_first_grammar_still_reads(quartz):
    """A log line printed before '+' existed is still something a
    scan can be re-run from."""
    cell = p1.expand(quartz)
    plane = module.parse_axis(quartz, cell, "plane 0,1,2 3,4,5")
    assert [a.atoms for a in plane.anchors] == [(0, 1, 2), (3, 4, 5)]
    distance = module.parse_axis(quartz, cell, "distance 0,1,2 3")
    assert [a.atoms for a in distance.anchors] == [(0, 1, 2), (3,)]


def test_the_spelling_of_anchors_reads_back_as_them(quartz):
    cell = p1.expand(quartz)
    groups = [[0, 1, 2], [3]]
    text = module.spell_anchors(groups)
    assert text == "0+1+2, 3"
    distance = module.parse_axis(quartz, cell, f"distance {text}")
    assert [list(a.atoms) for a in distance.anchors] == groups


def test_the_grammar_is_the_same_everywhere(quartz):
    """One way of writing an axis for the dialog, the command line and
    the log, so a scan can be re-run from the line it printed."""
    cell = p1.expand(quartz)
    for spec in ("a", "volume", "distance 0 3", "angle 0 1 2",
                 "torsion 0, 1, 2, 3", "plane 0+1+2, 3+4+5"):
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


def test_the_landscape_shown_first_is_the_lower_of_the_branches(
        quartz):
    """Neither branch alone is the landscape: each is the energy of
    whichever basin that direction of travel arrived in, so drawing
    one of them makes half the picture an artefact of the direction.

    The branches are still there, one click away, because their
    difference is the hysteresis -- but that is the second question.
    """
    result = module.run_scan(_cell_scan(quartz, direction="both"))
    surface = result.report.surfaces[0]
    labels = [label for label, _z in surface.all_sheets()]
    assert labels[0].endswith("lowest of both")
    assert "forward" in labels and "reverse" in labels
    assert any("-" in label for label in labels[1:])


def test_the_first_sheet_is_no_higher_than_either_branch(quartz):
    """What "lowest of both" has to mean, asserted rather than
    assumed."""
    result = module.run_scan(_cell_scan(quartz, direction="both"))
    surface = result.report.surfaces[0]
    sheets = dict(surface.all_sheets())
    for name in ("forward", "reverse"):
        assert np.all(np.nan_to_num(surface.z, nan=np.inf)
                      <= np.nan_to_num(sheets[name], nan=np.inf)
                      + 1e-9)


def test_one_direction_still_draws_that_direction(quartz):
    """The envelope only means anything when there are two branches
    to take it of."""
    result = module.run_scan(_cell_scan(quartz, direction="forward"))
    surface = result.report.surfaces[0]
    assert surface.z_label.endswith("forward")
    assert len(surface.all_sheets()) == 1


def test_a_cell_opens_the_branch_that_gave_its_energy(quartz,
                                                      folder):
    """With the envelope on screen, clicking a cell has to open the
    structure that *made* that number -- not the forward one
    regardless, which would show a crystal whose energy is not the
    one under the cursor.

    Checked against the CSV, which records every point of both
    branches: for each cell, the file the surface points at must be
    the one whose row has the lower energy.  Or either, where the two
    rows print the same energy: the corner the reverse walk starts
    from is the forward walk's last point relaxed again, and which of
    two equal energies is lower below the CSV's ten figures is
    rounding, and differs between machines.
    """
    result = module.run_scan(_cell_scan(quartz, folder,
                                        direction="both"))
    surface = result.report.surfaces[0]
    import csv as _csv
    rows = list(_csv.DictReader(
        (folder.path / "scan.csv").open(encoding="utf-8")))
    xs = list(surface.x)
    ys = list(surface.y)
    for row in range(len(ys)):
        for column in range(len(xs)):
            here = [r for r in rows
                    if float(r["a target"]) == pytest.approx(ys[row])
                    and float(r["c target"]) == pytest.approx(
                        xs[column])]
            lowest = min(float(r["energy (kcal/mol)"]) for r in here)
            best = [r["file"] for r in here
                    if float(r["energy (kcal/mol)"]) == lowest]
            opened = surface.path_at(row, column)
            assert any(opened.endswith(name) for name in best)


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

def test_the_bonding_is_the_same_at_every_point(quartz):
    """A scan must not re-perceive bonds as the cell opens.

    Distance perception is re-run on any structure that has none
    stored, and a scan hands the engine a new cell at every point, so
    without holding it the framework quietly comes apart: on
    MIL53.cif, stretching a by 15% loses 24 of its 126 bonds and by
    30% loses 78.  The landscape then has a cliff in it that is a
    change of topology rather than anything about the material.
    """
    from xtal.core import bonding

    a, _b, _c = quartz.lattice.parameters[:3]
    seen = []
    job = _job(quartz, axis1="a", axis1_start=a * 0.80,
               axis1_stop=a * 1.30, axis1_steps=4, max_steps=5)

    real = ENGINES.build

    def spy(name, structure, **options):
        seen.append(len(bonding.graph(structure).bonds))
        return real(name, structure, **options)

    ENGINES.build = spy
    try:
        module.run_scan(job)
    finally:
        ENGINES.build = real
    assert len(set(seen)) == 1


def test_a_stretched_point_opens_with_the_bonds_the_scan_held(
        tmp_path):
    """Clicking a cell of the landscape opened a structure bonded
    afresh at the stretched geometry, because the file held only the
    bonds the user drew.  MIL-53 at +15% on *a* loses 24 of its 126
    bonds that way, and the crystal on screen was not the molecule
    the energy was scored over."""
    from xtal.core import bonding
    from xtal.io import FORMATS, read_cif

    source = "resources/samples/MIL53.cif"
    mil53 = read_cif(source)
    held = {b.key() for b in bonding.perceive(mil53)}
    entry = Workspace.create(tmp_path / "ws").add_structure(source)
    folder = entry.next_run("scan", "scan")
    a = mil53.lattice.parameters[0]
    job = _job(mil53, folder, axis1="a", axis1_start=a * 1.15,
               axis1_stop=a * 1.15, axis1_steps=1, max_steps=2)
    result = module.run_scan(job)
    point = next(p for p in result.artifacts if p.suffix == ".cif")
    opened = FORMATS.read(point)
    assert opened.perceived is not None     # from the file, not asked
    assert {b.key() for b in bonding.perceive(opened)} == held


def test_a_scan_leaves_a_report_that_opens_again(quartz, folder):
    """Close the panel, or the application, and an overnight scan was
    a folder of CSV with no way back to its landscape."""
    from xtal.modules.report import REPORT_NAME, load

    result = module.run_scan(_cell_scan(quartz, folder, max_steps=3))
    path = folder.path / REPORT_NAME
    assert path in result.artifacts
    again = load(path)
    (surface,) = again.surfaces
    (shown,) = result.report.surfaces
    np.testing.assert_allclose(surface.z, shown.z)
    assert surface.paths == shown.paths
    assert again.tables[0].rows == result.report.tables[0].rows


def test_a_distance_the_group_holds_is_refused_before_any_point(
        halite):
    """Every Na-Cl distance in Fm-3m is fixed by the group.  Refused
    once, up front, where the dialog can say so -- not as a grid of
    holes each carrying the same message."""
    from xtal.ff.scan import ScanError, plan

    cell = p1.expand(halite)
    axis = module.axes_from(_job(halite, axis1="distance 0, 4",
                                 axis1_start=2.5, axis1_stop=3.0),
                            halite)
    assert cell.elements[0] != cell.elements[4]
    with pytest.raises(ScanError, match="space group"):
        plan(halite, axis)


def test_a_bond_set_by_hand_survives_the_whole_scan(quartz):
    """Explicit bonds ride on top of the held perception, which is
    how a bond type set before the scan is still set at the last
    point."""
    from xtal.core.structure import Bond

    structure = quartz.copy()
    before = len(structure.bonds)
    structure.bonds.append(Bond(0, 1, (0, 0, 0), order=2.0,
                                kind="explicit"))
    a, _b, _c = structure.lattice.parameters[:3]
    seen = []
    real = ENGINES.build

    def spy(name, st, **options):
        seen.append([(b.i, b.j, b.order) for b in st.bonds])
        return real(name, st, **options)

    ENGINES.build = spy
    try:
        module.run_scan(_job(structure, axis1="a",
                             axis1_start=a * 0.9, axis1_stop=a * 1.2,
                             axis1_steps=3, max_steps=5))
    finally:
        ENGINES.build = real
    assert all(len(bonds) == before + 1 for bonds in seen)
    assert all((0, 1, 2.0) in bonds for bonds in seen)


def test_the_engine_is_built_with_the_options_it_was_given(quartz):
    """They were collected by the dialog and then dropped on the
    floor, so a scan set up with plain UFF ran UFF4MOF."""
    seen = []
    real = ENGINES.build

    def spy(name, structure, **options):
        seen.append(options)
        return real(name, structure, **options)

    a, _b, _c = quartz.lattice.parameters[:3]
    ENGINES.build = spy
    try:
        module.run_scan(_job(
            quartz, axis1="a", axis1_start=a, axis1_stop=a * 1.02,
            axis1_steps=2, max_steps=3,
            engine_options={"parameter_set": "uff"}))
    finally:
        ENGINES.build = real
    assert seen and all(o["parameter_set"] == "uff" for o in seen)


def test_missing_engine_options_fall_back_to_the_defaults(quartz):
    """A command line that names one option must not have to name all
    five."""
    settings = module.engine_settings(
        _job(quartz, engine_options={"parameter_set": "uff"}), "uff")
    assert settings["parameter_set"] == "uff"
    assert settings["vdw_cutoff"] == 12.0


def test_the_report_names_the_parameter_set_it_used(quartz):
    """"UFF" and "UFF4MOF" are different numbers and the report has
    to say which."""
    said = module.run_scan(_cell_scan(
        quartz, engine_options={"parameter_set": "uff"})).report.note
    assert "(uff)" in said


def test_the_default_optimiser_is_smart_at_five_hundred_steps():
    _module_found, action = MODULES.find("scan.run")
    defaults = dict(action.defaults())
    assert defaults["method"] == "smart"
    assert defaults["max_steps"] == 500


def test_a_scan_pre_relaxes_with_the_engine_it_was_given(quartz):
    """UFF ahead of MACE is two engines with two sets of options, and
    the cheap one's must not be taken from the main one's."""
    seen = []
    real = ENGINES.build

    def spy(name, structure, **options):
        seen.append(options["parameter_set"])
        return real(name, structure, **options)

    a, _b, _c = quartz.lattice.parameters[:3]
    ENGINES.build = spy
    try:
        module.run_scan(_job(
            quartz, axis1="a", axis1_start=a, axis1_stop=a * 1.02,
            axis1_steps=2, max_steps=3,
            engine_options={"parameter_set": "uff"},
            pre_engine="uff", pre_max_steps=3,
            pre_engine_options={"parameter_set": "uff4mof"}))
    finally:
        ENGINES.build = real
    assert seen == ["uff4mof", "uff"] * 2


def test_a_scan_is_not_pre_relaxed_unless_asked(quartz):
    """An overnight job does not grow a second engine by default."""
    _module_found, action = MODULES.find("scan.run")
    assert dict(action.defaults())["pre_engine"] == ""
    assert module._prerelax(_job(quartz)) == (None, "")


def test_the_report_says_what_pre_relaxed_it(quartz):
    """Two engines touched every point, and a reader has to know
    which one the energies are from."""
    result = module.run_scan(_cell_scan(
        quartz, max_steps=3, pre_engine="uff", pre_max_steps=3,
        pre_engine_options={"parameter_set": "uff"}))
    assert "pre-relaxed with UFF (uff) for up to 3 steps" \
        in result.report.note


def test_the_csv_counts_the_pre_relaxation_steps(quartz, folder):
    import csv as _csv
    module.run_scan(_cell_scan(quartz, folder, max_steps=3,
                               pre_engine="uff", pre_max_steps=2))
    rows = list(_csv.DictReader(
        (folder.path / "scan.csv").open(encoding="utf-8")))
    assert rows and all(
        0 < int(r["pre-relaxation steps"]) <= 2 for r in rows)


def test_a_skipped_pre_relaxation_is_said_in_the_log(quartz):
    """A finished point's line shows no message of its own, so a
    shortcut not taken would otherwise go unmentioned all night."""
    from xtal.ff import scan as driver
    a = quartz.lattice.parameters[0]
    plan = driver.plan(quartz, [driver.Axis.over(
        module.parse_axis(quartz, p1.expand(quartz), "a"), a, a, 1)])
    point = driver.ScanPoint(
        index=(0,), targets=(a,), achieved=(a,), energy=-1.0,
        converged=True, steps=3, max_force=0.0,
        frac=quartz.frac, matrix=quartz.lattice.matrix,
        parameters=tuple(quartz.lattice.parameters),
        pre_skipped="no parameters for Xe")
    assert "pre-relaxation skipped: no parameters for Xe" in \
        module._said(plan, point, 1)


def test_the_scan_is_registered_as_a_module():
    module_found, action = MODULES.find("scan.run")
    assert module_found.name == "scan"
    assert action.kind == "scan"
    assert action.label == "Relaxed scan..."


def test_the_action_offers_every_engine():
    _module_found, action = MODULES.find("scan.run")
    engines = dict(action.defaults())
    assert engines["engine"] == "uff"
