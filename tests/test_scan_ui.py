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
