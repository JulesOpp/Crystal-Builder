"""A calculated pattern on screen: in the panel, and in the window
that can zoom into it.

Two plots and the split between them is the point.  The Results panel
draws a curve with ``QPainter`` and has to work on a machine with the
four core packages and Qt -- so the first thing here is that a curve
renders with matplotlib nowhere in sight.  The second is the window
that needs it: pan, zoom, an overlaid measurement and a vector export
whose text is still text, behind a button that greys out naming the
extra rather than being absent.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QFocusEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from xtal import install  # noqa: E402
from xtal.io.xy import read_xy, write_xy  # noqa: E402
from xtal.modules.report import Curve, Report  # noqa: E402
from xtalapp.curve import CurvePlot, save_curve  # noqa: E402
from xtalapp.dialogs import pattern as pattern_window  # noqa: E402
from xtalapp.docks.results import ResultsDock  # noqa: E402

needs_matplotlib = pytest.mark.skipif(
    not pattern_window.installed(), reason=pattern_window.MISSING)


def a_pattern() -> Curve:
    x = np.arange(5.0, 50.0, 0.01)
    y = np.exp(-((x - 12.0) ** 2) / 0.02) * 100.0
    y += np.exp(-((x - 21.0) ** 2) / 0.02) * 40.0
    return Curve(
        title="PXRD, Cu Ka1 (1.5406 A)", x=x, y=y,
        x_label="2-theta (degrees)", y_label="calculated",
        tick_sets=(("allowed", np.array([12.0, 21.0, 33.5])),
                   ("forbidden", np.array([16.0, 27.0]))),
        note="Calculated intensities assume the structure is "
             "complete.")


@pytest.fixture
def dock(qtbot):
    widget = ResultsDock()
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def measured(tmp_path):
    x = np.arange(5.0, 50.0, 0.05)
    y = 800.0 * np.exp(-((x - 12.1) ** 2) / 0.05) + 40.0
    return write_xy(x, y, tmp_path / "measured.xy",
                    header="a measured pattern")


# ------------------------------------------------------- the panel

def test_a_curve_becomes_a_plot_in_the_panel(dock, qtbot):
    dock.show_report(Report(blocks=(a_pattern(),)), "PXRD: Simulate")

    assert dock.heading.text() == "PXRD: Simulate"
    assert len(dock._blocks) == 1
    plot = dock._blocks[0].findChild(CurvePlot)
    assert plot is not None
    assert plot.curve.n_points == len(a_pattern().x)


def test_the_panel_draws_a_pattern_with_no_plotting_library(qtbot,
                                                            monkeypatch):
    """The one failure that would make the extra load-bearing: a
    Results panel that goes blank because matplotlib is not there."""
    monkeypatch.setattr(pattern_window, "installed", lambda: False)
    dock = ResultsDock()
    qtbot.addWidget(dock)
    dock.show_report(Report(blocks=(a_pattern(),)), "PXRD")
    dock.show()
    qtbot.waitExposed(dock)

    plot = dock._blocks[0].findChild(CurvePlot)
    assert plot is not None
    assert plot.curve is not None


def test_the_plot_button_greys_out_naming_the_extra(qtbot,
                                                    monkeypatch):
    monkeypatch.setattr(pattern_window, "installed", lambda: False)
    dock = ResultsDock()
    qtbot.addWidget(dock)
    dock.show_report(Report(blocks=(a_pattern(),)), "PXRD")

    button = dock._blocks[0].findChild(QPushButton)
    assert not button.isEnabled()
    assert install.command("pxrd") in button.toolTip()


@needs_matplotlib
def test_pressing_the_button_opens_the_window(dock, qtbot):
    """The gap a widget test cannot see: a broken ``triggered``
    connection passes every assertion about the panel's contents."""
    dock.show_report(Report(blocks=(a_pattern(),)), "PXRD")
    button = dock._blocks[0].findChild(QPushButton)
    button.click()

    window = dock.findChild(pattern_window.PatternDialog)
    assert window is not None
    assert window.isVisible()
    assert not window.isModal()
    window.close()


def test_a_second_report_replaces_the_curve(dock):
    dock.show_report(Report(blocks=(a_pattern(),)), "PXRD")
    dock.show_report(Report(), "Something else")

    assert dock._blocks == []
    assert "nothing to tabulate" in dock.note.text()


# -------------------------------------------------- the hand-drawn plot

def test_the_plot_caches_its_geometry_between_repaints(qtbot):
    """Ten thousand ``QPointF`` rebuilt inside ``paintEvent`` is tens
    of milliseconds paid again on every wheel click, which is what
    made the panel scroll badly."""
    plot = CurvePlot()
    qtbot.addWidget(plot)
    plot.set_curve(a_pattern())
    plot.resize(500, 260)
    plot.grab()                     # a synchronous paint
    built = dict(plot._cache)

    plot.grab()
    assert built and plot._cache.keys() == built.keys()
    assert all(plot._cache[k] is built[k] for k in built)

    plot.resize(420, 260)
    plot.grab()
    assert plot._cache.keys() != built.keys()


def test_the_plot_draws_a_trace_a_comb_and_a_legend(qtbot):
    plot = CurvePlot()
    qtbot.addWidget(plot)
    plot.set_curve(a_pattern())
    plot.resize(500, 260)
    plot.show()
    qtbot.waitExposed(plot)

    assert plot.toolTip().startswith("Calculated intensities")


def test_the_plot_draws_without_a_curve(qtbot):
    plot = CurvePlot()
    qtbot.addWidget(plot)
    plot.resize(300, 200)
    plot.show()
    qtbot.waitExposed(plot)

    assert plot.curve is None


def test_two_series_are_each_scaled_to_their_own_maximum(tmp_path):
    """A calculation is in electrons squared and a measurement is in
    counts; on one absolute axis one of them is the bottom pixel row.

    Asserted by drawing the same overlay at one times and at five
    thousand times and comparing the pictures, which is the claim
    itself rather than a proxy for it.
    """
    base = a_pattern()

    def picture(factor):
        curve = Curve(title=base.title, x=base.x, y=base.y,
                      y_label="calculated",
                      tick_sets=base.tick_sets,
                      series=(("measured", base.y * factor),))
        return save_curve(curve,
                          tmp_path / f"x{factor:g}.png").read_bytes()

    assert picture(1.0) == picture(5000.0)


def test_a_curve_is_written_beside_the_run_that_produced_it(tmp_path,
                                                            qtbot):
    """A run folder holding ten thousand numbers and no picture is one
    somebody has to reopen the application to look at."""
    path = save_curve(a_pattern(), tmp_path / "pxrd.png")

    assert path.exists() and path.stat().st_size > 0


# ------------------------------------------------------ the window

@needs_matplotlib
def test_the_window_plots_the_curve_and_its_reflections(qtbot):
    window = pattern_window.PatternDialog(a_pattern())
    qtbot.addWidget(window)

    assert len(window.axes.lines) == 1
    assert len(window.comb_axes.collections) == 2  # allowed, forbidden
    assert "% of maximum" in window.axes.get_ylabel()


@needs_matplotlib
def test_a_measured_pattern_is_drawn_over_the_calculation(
        qtbot, monkeypatch, measured):
    from PySide6.QtWidgets import QFileDialog

    window = pattern_window.PatternDialog(a_pattern())
    qtbot.addWidget(window)
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(measured), "")))
    window.add_overlay()

    assert [label for label, _x, _y in window.overlays] == ["measured"]
    assert len(window.axes.lines) == 2
    assert "overlaid" in window.status.text()


@needs_matplotlib
def test_a_measured_pattern_is_drawn_on_its_own_step(qtbot,
                                                     monkeypatch,
                                                     measured):
    """Not resampled onto the calculated grid: interpolating a
    measurement onto somebody else's step invents intensity between
    the points that were actually counted."""
    from PySide6.QtWidgets import QFileDialog

    window = pattern_window.PatternDialog(a_pattern())
    qtbot.addWidget(window)
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(measured), "")))
    window.add_overlay()

    calculated, overlaid = window.axes.lines
    assert len(overlaid.get_xdata()) != len(calculated.get_xdata())


@needs_matplotlib
def test_a_file_that_is_not_a_pattern_is_reported_rather_than_raised(
        qtbot, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    bad = tmp_path / "notes.txt"
    bad.write_text("# nothing here\n")
    said = []
    window = pattern_window.PatternDialog(a_pattern())
    qtbot.addWidget(window)
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(bad), "")))
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: said.append(a[2])))
    window.add_overlay()

    assert said and "2-theta and intensity" in said[0]
    assert window.overlays == []


@needs_matplotlib
@pytest.mark.parametrize("suffix", [".pdf", ".svg", ".png"])
def test_the_figure_is_written_in_the_format_the_suffix_asks_for(
        qtbot, monkeypatch, tmp_path, suffix):
    from PySide6.QtWidgets import QFileDialog

    target = tmp_path / f"figure{suffix}"
    window = pattern_window.PatternDialog(a_pattern())
    qtbot.addWidget(window)
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(target), "")))
    window.save_figure()

    assert target.exists() and target.stat().st_size > 0


@needs_matplotlib
def test_the_text_in_a_vector_figure_is_still_text(qtbot, monkeypatch,
                                                   tmp_path):
    """``svg.fonttype: none`` emits ``<text>`` rather than outlined
    paths, and without it the axis labels arrive in Illustrator as
    shapes -- which is the one thing somebody exporting a vector
    figure wanted."""
    from PySide6.QtWidgets import QFileDialog

    target = tmp_path / "figure.svg"
    window = pattern_window.PatternDialog(a_pattern())
    qtbot.addWidget(window)
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(target), "")))
    window.save_figure()
    svg = target.read_text()

    assert "2-theta" in svg
    assert "<text" in svg


@needs_matplotlib
def test_the_two_combs_are_two_colours(qtbot):
    """Allowed and forbidden are two statements about one axis, and
    telling which one an unexpected peak sits over is the whole use of
    the second."""
    window = pattern_window.PatternDialog(a_pattern())
    qtbot.addWidget(window)

    allowed, forbidden = window.comb_axes.collections
    assert allowed.get_label() == "allowed"
    assert forbidden.get_label() == "forbidden"
    assert not np.allclose(allowed.get_colors(),
                           forbidden.get_colors())
    # Stacked, not on top of each other: the strip counts rows down.
    assert window.comb_axes.yaxis_inverted()
    assert forbidden.get_segments()[0][0][1] > \
        allowed.get_segments()[0][0][1]


@needs_matplotlib
def test_the_range_boxes_start_at_what_is_on_screen(qtbot):
    window = pattern_window.PatternDialog(a_pattern())
    qtbot.addWidget(window)
    low, high = window.axes.get_xlim()

    assert float(window.low.text()) == pytest.approx(low, abs=0.01)
    assert float(window.high.text()) == pytest.approx(high, abs=0.01)


@needs_matplotlib
def test_typing_a_range_moves_the_axis_with_no_apply_button(qtbot):
    window = pattern_window.PatternDialog(a_pattern())
    qtbot.addWidget(window)
    window.low.setText("10")
    window.high.setText("25")
    window.low.editingFinished.emit()

    assert window.axes.get_xlim() == pytest.approx((10.0, 25.0))


@needs_matplotlib
def test_a_reversed_range_is_swapped_rather_than_refused(qtbot):
    """Unambiguously what was meant, so refusing it would be a dialog
    about nothing."""
    window = pattern_window.PatternDialog(a_pattern())
    qtbot.addWidget(window)
    window.low.setText("30")
    window.high.setText("12")
    window.high.editingFinished.emit()

    assert window.axes.get_xlim() == pytest.approx((12.0, 30.0))
    assert float(window.low.text()) == pytest.approx(12.0)


@needs_matplotlib
def test_an_emptied_box_means_all_of_that_end(qtbot):
    """Clearing a box is a request and not a mistake: it is how
    somebody asks for that end of the axis back."""
    curve = a_pattern()
    window = pattern_window.PatternDialog(curve)
    qtbot.addWidget(window)
    window.low.setText("20")
    window.high.setText("30")
    window.low.editingFinished.emit()
    assert window.axes.get_xlim() == pytest.approx((20.0, 30.0))

    window.low.setText("")
    window.low.editingFinished.emit()
    low, high = window.axes.get_xlim()

    assert low == pytest.approx(float(curve.x[0]))
    assert high == pytest.approx(30.0)      # the other end is left
    assert float(window.low.text()) == pytest.approx(float(curve.x[0]))


def _tab_out_of(entry) -> None:
    """Leave a box the way tabbing out of it does.

    The focus *event*, and not the Tab key, because Tab only moves
    anything in a window the desktop has made key -- and a test run
    that is not the frontmost application never gets one.  On macOS
    two processes showing a window at the same time is enough: the
    one that loses never activates, ``waitActive`` spends its five
    seconds waiting for something that was never going to happen, and
    the test fails on the timeout rather than on either assertion
    below.  Which is the whole of why this used to fail one run in
    three, and why waiting harder is not the fix.

    Nothing is weakened by sending the event: ``QLineEdit`` emits
    ``editingFinished`` from ``focusOutEvent`` and only if
    ``hasAcceptableInput``, which is the gate a validator closes over
    an empty box.  Put a ``QDoubleValidator`` back on the boxes and
    the second assertion below still fails.
    """
    QApplication.sendEvent(
        entry, QFocusEvent(QEvent.FocusOut, Qt.TabFocusReason))


@needs_matplotlib
def test_a_range_box_applies_when_the_focus_leaves_it(qtbot):
    """It had a ``QDoubleValidator``, which suppresses
    ``editingFinished`` while it calls the text *Intermediate* -- and
    an empty box is intermediate.  So clearing a box did nothing until
    the *other* one was edited, which is the one case the reset rule
    was added for.

    Driven with a focus-out event rather than with a Tab key and a
    wait for the window to be activated -- see :func:`_tab_out_of`.
    """
    curve = a_pattern()
    window = pattern_window.PatternDialog(curve)
    qtbot.addWidget(window)

    window.low.setFocus()
    window.low.selectAll()
    qtbot.keyClicks(window.low, "18")
    _tab_out_of(window.low)
    assert window.axes.get_xlim()[0] == pytest.approx(18.0)

    window.low.setFocus()
    window.low.selectAll()
    qtbot.keyClick(window.low, Qt.Key_Backspace)
    _tab_out_of(window.low)

    assert window.axes.get_xlim()[0] == pytest.approx(float(curve.x[0]))


@needs_matplotlib
def test_clicking_the_plot_applies_the_box_too(qtbot):
    """Clicking away from a box has to count as leaving it, so the
    canvas takes the focus."""
    window = pattern_window.PatternDialog(a_pattern())
    qtbot.addWidget(window)

    assert window.canvas.focusPolicy() & Qt.ClickFocus


@needs_matplotlib
def test_emptying_both_boxes_shows_everything(qtbot):
    curve = a_pattern()
    window = pattern_window.PatternDialog(curve)
    qtbot.addWidget(window)
    window.low.setText("20")
    window.high.setText("30")
    window.low.editingFinished.emit()

    window.low.setText("")
    window.high.setText("")
    window.high.editingFinished.emit()

    assert window.axes.get_xlim() == pytest.approx(
        (float(curve.x[0]), float(curve.x[-1])))


@needs_matplotlib
def test_the_limit_covers_a_measurement_that_runs_past_the_calculation(
        qtbot, monkeypatch, tmp_path):
    """"Show me everything" has to mean everything: a measured pattern
    can start before the range the calculation was asked for."""
    from PySide6.QtWidgets import QFileDialog

    wide = write_xy(np.arange(2.0, 60.0, 0.05),
                    np.ones(int(58 / 0.05)), tmp_path / "wide.xy")
    curve = a_pattern()
    window = pattern_window.PatternDialog(curve)
    qtbot.addWidget(window)
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(wide), "")))
    window.add_overlay()

    low, high = window.limits()
    assert low == pytest.approx(2.0)
    assert high > float(curve.x[-1])


@needs_matplotlib
def test_the_boxes_follow_a_zoom_made_with_the_toolbar(qtbot):
    """Boxes that only ever *accepted* a range would disagree with the
    picture the moment anybody used the magnifier beside them."""
    window = pattern_window.PatternDialog(a_pattern())
    qtbot.addWidget(window)
    window.axes.set_xlim(14.0, 18.0)
    window._show_range()

    assert float(window.low.text()) == pytest.approx(14.0)
    assert float(window.high.text()) == pytest.approx(18.0)


@needs_matplotlib
def test_the_pattern_is_written_as_two_columns(qtbot, monkeypatch,
                                               tmp_path):
    from PySide6.QtWidgets import QFileDialog

    target = tmp_path / "pattern.xy"
    curve = a_pattern()
    window = pattern_window.PatternDialog(curve)
    qtbot.addWidget(window)
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(target), "")))
    window.save_pattern()
    x, y = read_xy(target)

    assert len(x) == curve.n_points
    assert y.max() == pytest.approx(curve.y.max())


@needs_matplotlib
def test_a_pattern_can_be_drawn_on_a_square_root_or_logarithmic_axis(
        qtbot):
    """The weak lines that decide a space group are flat along the
    bottom of a linear axis.  The combs keep their own strip, which a
    logarithmic axis -- with no below zero -- would otherwise lose."""
    window = pattern_window.PatternDialog(a_pattern())
    qtbot.addWidget(window)
    window.axes.set_xlim(12.0, 20.0)
    window.scale_box.setCurrentIndex(window.scale_box.findData("log"))
    assert window.axes.get_yscale() == "log"
    assert window.axes.get_xlim() == pytest.approx((12.0, 20.0))
    assert len(window.comb_axes.collections) == 2
    window.scale_box.setCurrentIndex(window.scale_box.findData("sqrt"))
    assert window.axes.get_yscale() == "function"
    window.replot()
    assert window.axes.get_yscale() == "function"
