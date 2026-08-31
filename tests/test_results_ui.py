"""The panel a module's tables and histograms land in.

Every module before Zeo++ answered in a sentence, and a sentence fits
in the status bar.  These are about the panel that exists because
three pore diameters do not: that it renders what it is given, that it
knows no module by name, and -- the one way it could be worse than no
panel at all -- that it never leaves one run's numbers on screen under
another run's heading.
"""

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from xtal.modules.report import (  # noqa: E402
    Histogram,
    Report,
    Row,
    Table,
)
from xtalapp.docks.results import ResultsDock  # noqa: E402
from xtalapp.histogram import HistogramPlot, _ticks  # noqa: E402


def a_table() -> Report:
    return Report(
        title="Pore diameters",
        blocks=(Table(rows=(
            Row.number("Largest free sphere", 9.18, "A",
                       "what the framework will admit", "D_f"),
            Row.number("Largest included sphere", 18.73, "A"),
        ), note="D_f is the smallest of the three."),),
        note="radii from Zeo++'s own table")


def a_histogram() -> Report:
    x = np.linspace(10.0, 20.0, 40)
    y = np.exp(-((x - 15.0) ** 2))
    return Report(title="Pore size distribution", blocks=(Histogram(
        title="Pore size distribution", x=x, y=y,
        x_label="pore diameter (A)", y_label="sample points",
        curve=y * 0.5, curve_label="dV/dD",
        markers=((12.0, "probe"),)),))


@pytest.fixture
def dock(qtbot):
    widget = ResultsDock()
    qtbot.addWidget(widget)
    return widget


def test_it_starts_empty_and_says_what_would_fill_it(dock):
    assert not dock._blocks
    assert "Nothing has been run yet" in dock.note.text()


def test_a_table_becomes_a_table(dock):
    dock.show_report(a_table(), "Zeo++: Pore diameters")

    from PySide6.QtWidgets import QTableWidget

    assert dock.heading.text() == "Zeo++: Pore diameters"
    assert len(dock._blocks) == 1
    widget = dock._blocks[0].findChild(QTableWidget)
    assert widget.rowCount() == 2
    assert widget.item(0, 0).text() == "Largest free sphere (D_f)"
    assert widget.item(0, 2).text() == "A"


def test_a_rows_meaning_is_its_tooltip(dock):
    """A free sphere diameter read as an included one is a number that
    will be wrong in a paper, so the caveat is where the number is."""
    from PySide6.QtWidgets import QTableWidget

    dock.show_report(a_table(), "Zeo++")
    widget = dock._blocks[0].findChild(QTableWidget)
    assert "admit" in widget.item(0, 0).toolTip()


def test_a_histogram_becomes_a_plot(dock):
    dock.show_report(a_histogram(), "Zeo++: PSD")
    plot = dock._blocks[0].findChild(HistogramPlot)
    assert plot is not None
    assert plot.histogram.n_bins == 40


def test_a_second_report_replaces_the_first(dock):
    dock.show_report(a_histogram(), "one")
    dock.show_report(a_table(), "two")

    from PySide6.QtWidgets import QTableWidget
    assert len(dock._blocks) == 1
    assert dock._blocks[0].findChild(HistogramPlot) is None
    assert dock._blocks[0].findChild(QTableWidget) is not None


def test_a_run_with_nothing_to_show_clears_it(dock):
    """The one failure that would make this worse than no panel: the
    previous run's numbers sitting under this run's heading."""
    dock.show_report(a_table(), "Zeo++: Pore diameters")
    dock.show_report(None, "Forcefield: Single point")

    assert not dock._blocks
    assert "nothing to tabulate" in dock.note.text()
    assert dock.heading.text() == "Forcefield: Single point"


def test_clearing_goes_all_the_way_back(dock):
    dock.show_report(a_table(), "Zeo++")
    dock.clear()
    assert not dock._blocks
    assert not dock.heading.isVisible()


# ---------------------------------------------------------- the drawing

def test_the_plot_draws_without_a_histogram(qtbot):
    """It is on screen before the first run finishes."""
    plot = HistogramPlot()
    qtbot.addWidget(plot)
    plot.resize(400, 200)
    plot.grab()                         # must not raise


def test_the_plot_draws_bars_a_curve_and_a_marker(qtbot):
    plot = HistogramPlot()
    qtbot.addWidget(plot)
    plot.set_histogram(a_histogram().histograms[0])
    plot.resize(600, 260)
    image = plot.grab().toImage()

    # Something was drawn in both colours, which is the whole of
    # "the bars and the curve are both there".
    colors = {image.pixelColor(x, y).name()
              for x in range(0, image.width(), 3)
              for y in range(0, image.height(), 3)}
    from xtalapp.histogram import BAR_COLOR, CURVE_COLOR
    assert BAR_COLOR.name() in colors
    assert CURVE_COLOR.name() in colors


def test_an_empty_histogram_says_so_rather_than_dividing_by_zero(qtbot):
    plot = HistogramPlot()
    qtbot.addWidget(plot)
    plot.set_histogram(Histogram(title="nothing"))
    plot.resize(300, 150)
    plot.grab()                         # must not raise


def test_the_ticks_are_round_numbers_inside_the_range():
    ticks = _ticks(10.15, 19.25)
    assert ticks == [12, 14, 16, 18]
    assert all(10.15 <= t <= 19.25 for t in ticks)


def test_the_ticks_scale_with_the_range():
    assert _ticks(0.0, 1000.0)[-1] == 1000
    assert len(_ticks(3.2, 3.9)) >= 2
