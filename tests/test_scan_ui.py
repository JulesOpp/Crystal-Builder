"""The energy landscape on screen, and the way into the structures
behind it.

The panel is hand-painted and needs nothing installed, which is the
rule every panel in this application keeps.  What is pinned here is
mostly the honesty of the picture: a point that never finished has to
stay unmistakably absent, and it must take no part in the colour
scale, because a hole rendered as a zero is the deepest point of every
landscape it appears in.
"""

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QWidget  # noqa: E402

from xtal.io import write_cif  # noqa: E402
from xtal.modules.report import Report, Surface  # noqa: E402
from xtalapp.heatmap import HeatmapPlot, ramp, save_surface  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Scan{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


@pytest.fixture
def points(tmp_path, quartz, rutile):
    """Three real CIFs standing in for three relaxed scan points."""
    paths = []
    for name, structure in (("p00", quartz), ("p01", rutile),
                            ("p02", quartz)):
        path = tmp_path / f"{name}.cif"
        write_cif(structure, path)
        paths.append(str(path))
    return paths


@pytest.fixture
def surface(points):
    return Surface(
        title="Energy landscape",
        x=np.array([5.2, 5.4, 5.6]), y=np.array([4.7, 4.9]),
        z=np.array([[4.1, 2.9, 5.1], [0.0, np.nan, 3.5]]),
        x_label="c (A)", y_label="a (A)", z_label="E (kcal/mol)",
        converged=np.array([[1, 1, 0], [1, 1, 1]], dtype=bool),
        paths=(tuple(points), ("", "", "")),
        note="Held: a and c, with the cell fixed at each point.")


@pytest.fixture
def plot(qtbot, surface):
    widget = HeatmapPlot()
    widget.set_surface(surface)
    widget.resize(600, 460)
    qtbot.addWidget(widget)
    widget.grab()               # force one paint, so the grid exists
    return widget


# ----------------------------------------------------------------------
#  The picture
# ----------------------------------------------------------------------

def test_the_colour_scale_ignores_the_points_that_did_not_finish(
        plot):
    """Referencing the scale to a NaN gives no scale; referencing it
    to a zero standing in for one compresses every real difference
    into the top of the ramp."""
    assert plot.limits() == (0.0, 5.1)


def test_the_ramp_runs_dark_to_light(plot):
    """Ordered by lightness rather than hue, so the picture reads
    printed in grey and reads for somebody who does not separate red
    from green."""
    dark, light = ramp(0.0), ramp(1.0)
    assert dark.lightness() < light.lightness()


def test_an_empty_plot_says_so_rather_than_painting_nothing(qtbot):
    widget = HeatmapPlot()
    qtbot.addWidget(widget)
    widget.resize(200, 200)
    widget.grab()
    assert widget.limits() == (0.0, 1.0)


def test_the_low_end_of_the_scale_gets_more_colour(plot):
    """A landscape's interesting part is the basin, which is the
    bottom of its range.

    On an 11x11 scan of MIL-53 the lowest 100 kcal/mol held 13 of 121
    cells while one blown-up corner reached 4151, so a linear ramp
    spent nine tenths of its colour on ground nobody is looking at and
    drew the basin as one flat navy rectangle.
    """
    low, high = 0.0, 100.0
    plot.set_compressed(True)
    assert plot.shade(10.0, low, high) > 0.25
    plot.set_compressed(False)
    assert plot.shade(10.0, low, high) == pytest.approx(0.1)


def test_the_stretch_is_monotonic_and_keeps_both_ends(plot):
    """It is a stretch and not a clip: no cell overtakes another,
    nothing is hidden, and the blown-up corner is still the top of
    the scale rather than quietly thrown away."""
    plot.set_compressed(True)
    shades = [plot.shade(v, 0.0, 100.0)
              for v in (0.0, 1.0, 10.0, 50.0, 99.0, 100.0)]
    assert shades == sorted(shades)
    assert shades[0] == pytest.approx(0.0)
    assert shades[-1] == pytest.approx(1.0)


def test_a_value_past_the_ends_is_held_at_them(plot):
    assert plot.shade(-5.0, 0.0, 10.0) == pytest.approx(0.0)
    assert plot.shade(50.0, 0.0, 10.0) == pytest.approx(1.0)


def test_the_colour_bar_is_labelled_at_round_energies(plot):
    """Placed through the same mapping the cells went through, so the
    uneven ladder of ticks is what says the scale is stretched.  Two
    labels could not say it at all."""
    ticks = plot._bar_ticks(0.0, 4151.0)
    assert ticks[0] == pytest.approx(0.0)
    assert ticks[-1] == pytest.approx(4151.0)
    assert len(ticks) >= 4
    assert all(round(v) % 500 == 0 for v in ticks[1:-1])


def test_the_panel_offers_the_stretch_and_starts_with_it_on(
        window, surface):
    from PySide6.QtWidgets import QCheckBox

    window.results_dock.show_report(Report(blocks=(surface,)), "Scan")
    boxes = [b for b in window.results_dock.findChildren(QCheckBox)
             if "low end" in b.text()]
    assert boxes and boxes[0].isChecked()
    boxes[0].setChecked(False)
    assert not _plot_in(window.results_dock).compressed


def test_a_click_lands_on_the_cell_under_it(plot):
    """The grid is laid out at paint time and read back at click
    time; if the two disagree, every click opens the wrong
    structure."""
    left, top, width, height, rows, columns = plot._grid
    centre = plot.cell_at(left + width / columns * 1.5,
                          top + height / rows * 0.5)
    assert centre == (0, 1)


def test_a_click_outside_the_grid_is_not_a_cell(plot):
    assert plot.cell_at(2, 2) is None


def test_the_readout_names_both_axes_and_the_value(plot):
    said = plot.readout((0, 1))
    assert "a (A)" in said and "c (A)" in said
    assert "2.9" in said


def test_the_readout_says_when_a_point_did_not_finish(plot):
    assert "did not finish" in plot.readout((1, 1))


def test_the_readout_says_when_a_point_did_not_converge(plot):
    assert "not converged" in plot.readout((0, 2))


def test_a_second_branch_is_a_second_sheet(qtbot, surface):
    """Two directions are two sheets and the reader wants each; where
    they differ is the hysteresis."""
    both = Surface(x=surface.x, y=surface.y, z=surface.z,
                   z_label="forward",
                   sheets=(("reverse", surface.z + 1.0),))
    widget = HeatmapPlot()
    qtbot.addWidget(widget)
    widget.set_surface(both, sheet=1)
    assert float(np.nanmin(widget.values())) == pytest.approx(1.0)


def test_the_heat_map_is_written_as_a_png(tmp_path, surface, qtbot):
    """A run folder holding a hundred CIFs and a spreadsheet and no
    picture is one somebody has to reopen the application to look
    at."""
    path = save_surface(surface, tmp_path / "landscape.png")
    assert path.exists()
    assert path.stat().st_size > 1000


# ----------------------------------------------------------------------
#  Clicking through to a structure
# ----------------------------------------------------------------------

def test_clicking_a_cell_opens_that_structure(window, surface,
                                              points):
    """The grid and the files beside it are one scan seen two ways,
    and "what does the crystal look like *there*" is asked at a
    minimum or a ridge -- which makes the picture the fastest way to
    the geometry that made it."""
    window.results_dock.show_report(Report(blocks=(surface,)), "Scan")
    plot = _plot_in(window.results_dock)
    plot.cellClicked.emit(0, 1)
    assert window.tabs.count() == 1
    assert str(window.documents[0].path).endswith("p01.cif")


def test_the_cell_that_was_opened_is_marked(window, surface):
    """So that a reader who has clicked three of them can see which
    one is in front."""
    window.results_dock.show_report(Report(blocks=(surface,)), "Scan")
    plot = _plot_in(window.results_dock)
    plot.cellClicked.emit(0, 2)
    assert plot.marker == (0, 2)


def test_clicking_a_cell_with_no_structure_says_so(window, surface):
    """A control that ignores a click is indistinguishable from one
    that is broken."""
    window.results_dock.show_report(Report(blocks=(surface,)), "Scan")
    plot = _plot_in(window.results_dock)
    plot.cellClicked.emit(1, 1)
    assert window.tabs.count() == 0
    assert plot.marker is None


def test_clicking_a_cell_whose_file_has_gone_says_so(window, surface,
                                                     points):
    """A scan folder somebody has tidied up is an ordinary thing to
    meet."""
    from pathlib import Path
    Path(points[0]).unlink()
    window.results_dock.show_report(Report(blocks=(surface,)), "Scan")
    plot = _plot_in(window.results_dock)
    plot.cellClicked.emit(0, 0)
    assert window.tabs.count() == 0


def test_a_saved_landscape_opens_from_the_workspace(window, surface,
                                                    tmp_path):
    """Double-clicking a run's report puts the landscape back, and
    its cells still open their structures -- after the panel was
    closed, or the application was."""
    from xtal.modules.report import save
    run = tmp_path / "scan-scan-003"
    run.mkdir()
    path = save(Report(title="Relaxed scan", blocks=(surface,)),
                run / "report.json")
    window.results_dock.clear()
    window.open_artifact("report", str(path))
    assert not window.results_dock.isHidden()
    plot = _plot_in(window.results_dock)
    plot.cellClicked.emit(0, 1)
    assert str(window.documents[0].path).endswith("p01.cif")


def test_a_report_that_does_not_read_says_so(window, tmp_path):
    path = tmp_path / "report.json"
    path.write_text("not json")
    window.open_artifact("report", str(path))
    assert not window.results_dock.findChildren(HeatmapPlot)


def test_the_workspace_tree_names_a_report_as_results(window,
                                                     tmp_path):
    from xtalapp.docks.workspace import KIND_LABELS
    assert KIND_LABELS["report"] == "results"


def test_a_point_opened_in_the_window_keeps_the_bonds_it_was_written_with(
        window, tmp_path):
    """The file carries the graph the scan held; the tab has to show
    that graph, not perceive a new one at the stretched cell."""
    from xtal.core import bonding
    from xtal.core.lattice import Lattice
    from xtal.io import read_cif

    mil53 = read_cif("resources/samples/MIL53.cif")
    held = {b.key() for b in bonding.perceive(mil53)}
    parameters = list(mil53.lattice.parameters)
    parameters[0] *= 1.15
    mil53.set_lattice(Lattice.from_parameters(
        *mil53.space_group.cell_constraint.apply(parameters)))
    path = write_cif(mil53, tmp_path / "forward-00.cif",
                     perception=True)
    window.open_path(path)
    structure = window.current_document().structure
    assert {b.key() for b in bonding.perceive(structure)} == held


def _plot_in(dock):
    for widget in dock.findChildren(HeatmapPlot):
        return widget
    raise AssertionError("the report drew no heat map")


# ----------------------------------------------------------------------
#  The panel it sits in
# ----------------------------------------------------------------------

def test_a_surface_renders_in_the_results_panel(window, surface):
    window.results_dock.show_report(Report(blocks=(surface,)), "Scan")
    assert _plot_in(window.results_dock) is not None


def test_the_note_is_shown_under_the_landscape(window, surface):
    """What was held fixed travels with the picture, because a
    profile that does not say it cannot be read."""
    from PySide6.QtWidgets import QLabel
    window.results_dock.show_report(Report(blocks=(surface,)), "Scan")
    said = [w.text() for w in
            window.results_dock.findChildren(QLabel)]
    assert any("Held" in text for text in said)


def test_a_panel_holding_a_landscape_leaves_the_column_free(
        window, surface):
    """A dock area is as wide as the largest minimum of any dock in
    it, tabbed behind or not, so a panel that asked for room here
    would widen the column for every other panel too."""
    from xtalapp.docks import MAXIMUM_MINIMUM

    window.results_dock.show_report(Report(blocks=(surface,)), "Scan")
    hint = window.results_dock.minimumSizeHint()
    assert max(hint.width(), hint.height()) <= MAXIMUM_MINIMUM


def test_the_landscape_plot_asks_for_no_width(qtbot):
    """The rule above, at its source."""
    widget = HeatmapPlot()
    qtbot.addWidget(widget)
    assert widget.minimumWidth() == 0


# ----------------------------------------------------------------------
#  The contour window
# ----------------------------------------------------------------------

def test_the_contour_window_is_offered_only_when_matplotlib_is_there(
        window, surface, monkeypatch):
    from PySide6.QtWidgets import QPushButton

    from xtalapp.dialogs import landscape

    monkeypatch.setattr(landscape, "installed", lambda: False)
    window.results_dock.show_report(Report(blocks=(surface,)), "Scan")
    buttons = [b for b in
               window.results_dock.findChildren(QPushButton)
               if "Contours" in b.text() or "contour" in b.text()]
    assert buttons and not buttons[0].isEnabled()


def test_the_contour_window_draws_the_landscape(qtbot, surface):
    from xtalapp.dialogs import landscape

    if not landscape.installed():
        pytest.skip("matplotlib is not installed")
    dialog = landscape.LandscapeDialog(surface)
    qtbot.addWidget(dialog)
    assert dialog.axes.get_xlabel() == "c (A)"
    assert dialog.axes.get_ylabel() == "a (A)"


def test_the_contour_window_marks_the_points_that_did_not_finish(
        qtbot, surface):
    """A hole in a contour plot is smoothed over by the interpolation
    either side of it, which is the quiet invention this whole
    feature has to avoid."""
    from xtalapp.dialogs import landscape

    if not landscape.installed():
        pytest.skip("matplotlib is not installed")
    dialog = landscape.LandscapeDialog(surface)
    qtbot.addWidget(dialog)
    assert dialog.axes.get_legend() is not None


def test_the_contour_window_stretches_the_low_end_too(qtbot,
                                                      surface):
    """Matched to the panel on purpose: a landscape that reads in the
    dock and goes flat in the window would look like a different
    scan."""
    from xtalapp.dialogs import landscape

    if not landscape.installed():
        pytest.skip("matplotlib is not installed")
    dialog = landscape.LandscapeDialog(surface)
    qtbot.addWidget(dialog)
    assert dialog.stretch.isChecked()
    grid = np.ma.masked_invalid(dialog.values())
    assert dialog._norm(grid) is not None
    dialog.stretch.setChecked(False)
    assert dialog._norm(grid) is None


def test_the_contour_levels_follow_the_stretch(qtbot, surface):
    """Evenly spaced levels under a stretched colour map put almost
    every line in the flat part and none around the basin, which is
    the opposite of what the stretch was for."""
    from xtalapp.dialogs import landscape

    if not landscape.installed():
        pytest.skip("matplotlib is not installed")
    dialog = landscape.LandscapeDialog(surface)
    qtbot.addWidget(dialog)
    levels = dialog._levels(np.ma.masked_invalid(dialog.values()))
    gaps = np.diff(np.asarray(levels))
    assert gaps[0] < gaps[-1]


def test_unticking_fill_does_not_raise(qtbot, surface):
    """``axes.clear()`` detaches the mappable and ``Colorbar.remove``
    then fails restoring a subplotspec that is gone.  The figure is
    rebuilt instead."""
    from xtalapp.dialogs import landscape

    if not landscape.installed():
        pytest.skip("matplotlib is not installed")
    dialog = landscape.LandscapeDialog(surface)
    qtbot.addWidget(dialog)
    for _ in range(3):
        dialog.filled.setChecked(False)
        dialog.filled.setChecked(True)
    assert dialog.axes.get_xlabel() == "c (A)"


# ----------------------------------------------------------------------
#  A one-axis scan: the profile
# ----------------------------------------------------------------------

@pytest.fixture
def profile(points):
    from xtal.modules.report import Curve
    return Curve(
        title="Energy profile",
        x=np.array([900.0, 950.0, 1000.0]),
        y=np.array([3.0, 0.0, np.nan]),
        x_label="volume (A^3)", y_label="E - E(min) (kcal/mol)",
        series=(("backward", np.array([2.5, -1.0, 4.0])),),
        normalised=False,
        paths=((points[0], points[1], ""), tuple(points)))


def _curve_in(dock):
    from xtalapp.curve import CurvePlot
    for widget in dock.findChildren(CurvePlot):
        return widget
    raise AssertionError("the report drew no curve")


def test_clicking_a_point_of_a_profile_opens_that_structure(
        window, profile):
    """The one-axis scan is as much a way into its structures as the
    landscape is; a profile that only draws them left a folder of
    CIFs to hunt through."""
    window.results_dock.show_report(Report(blocks=(profile,)), "Scan")
    plot = _curve_in(window.results_dock)
    plot.pointClicked.emit(1, 2)
    assert str(window.documents[0].path).endswith("p02.cif")
    assert plot.marker == (1, 2)


def test_a_point_of_a_profile_that_did_not_finish_opens_nothing(
        window, profile):
    window.results_dock.show_report(Report(blocks=(profile,)), "Scan")
    plot = _curve_in(window.results_dock)
    plot.pointClicked.emit(0, 2)
    assert window.tabs.count() == 0
    assert plot.marker is None


def test_a_click_lands_on_the_nearest_point_of_a_profile(qtbot,
                                                         profile):
    """And not on a hole: the unfinished point has no place on the
    axis to be near."""
    from xtalapp.curve import CurvePlot
    plot = CurvePlot()
    plot.set_curve(profile)
    plot.resize(500, 300)
    qtbot.addWidget(plot)
    plot.grab()
    across, up = plot._geometry(plot._box)[4][1]
    assert plot.point_at(across[1] + 2, up[1] - 2) == (1, 1)
    assert plot.point_at(across[1], up[1] - 100) is None


def test_a_profile_below_zero_is_drawn_on_its_own_numbers(qtbot,
                                                          profile):
    """Scaled to its maximum, a trace that is negative has none, and
    the panel drew nothing -- which is every DFTB+ energy."""
    from xtalapp.curve import CurvePlot
    plot = CurvePlot()
    plot.set_curve(profile)
    low, high = plot.limits()
    assert low < -1.0 and high > 4.0


def test_a_saved_profile_still_opens_its_points(window, profile,
                                                tmp_path):
    from xtal.modules.report import load, save
    run = tmp_path / "scan-scan-004"
    run.mkdir()
    path = save(Report(title="Relaxed scan", blocks=(profile,)),
                run / "report.json")
    curve, = load(path).curves
    assert curve.path_at(1, 2) == profile.path_at(1, 2)
    assert not curve.normalised


def test_the_plot_window_names_the_profile_axis_not_2_theta(
        qtbot, profile):
    """The pattern window serves a scan's profile too, and every word
    in it said diffraction."""
    from PySide6.QtWidgets import QLabel

    from xtalapp.dialogs import pattern

    if not pattern.installed():
        pytest.skip("matplotlib is not installed")
    window = pattern.PatternDialog(profile)
    qtbot.addWidget(window)
    labels = [label.text() for label in window.findChildren(QLabel)]
    assert "volume" in labels and "2-theta" not in labels
    assert window.axes.get_xlabel() == "volume (A^3)"
    assert window.axes.get_ylabel() == "E - E(min) (kcal/mol)"
    assert window.data_button.text() == "Save data..."
    assert "A^3" in window.low.toolTip()
    # Not scaled: the lowest drawn value is the energy itself.
    assert min(np.nanmin(line.get_ydata())
               for line in window.axes.lines) == -1.0
