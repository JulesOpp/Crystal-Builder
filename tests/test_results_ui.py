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

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QTableView  # noqa: E402

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


def cell(widget, row, column, role=Qt.DisplayRole):
    return widget.model().data(widget.model().index(row, column),
                               role)


def test_a_table_becomes_a_table(dock):
    dock.show_report(a_table(), "Zeo++: Pore diameters")

    assert dock.heading.text() == "Zeo++: Pore diameters"
    assert len(dock._blocks) == 1
    widget = dock._blocks[0].findChild(QTableView)
    assert widget.model().rowCount() == 2
    assert cell(widget, 0, 0) == "Largest free sphere (D_f)"
    assert cell(widget, 0, 2) == "A"


def test_a_quantity_table_needs_no_column_headings(dock):
    """Drawing ``Quantity | Value | Unit`` over three pore diameters
    would be labelling the obvious; a table with columns of its own
    shows them, because those are the ones a reader needs."""
    dock.show_report(a_table(), "Zeo++")
    widget = dock._blocks[0].findChild(QTableView)

    assert widget.horizontalHeader().isHidden()


def test_a_table_with_its_own_columns_shows_them(dock):
    columns = ("No.", "hkl", "d")
    dock.show_report(Report(blocks=(Table(
        columns=columns,
        rows=tuple(Row.of(n, f"({n} 0 0)", f"{9.0 / n:.3f}")
                   for n in range(1, 4))),)), "PXRD")
    widget = dock._blocks[0].findChild(QTableView)

    assert not widget.horizontalHeader().isHidden()
    assert [widget.model().headerData(i, Qt.Horizontal)
            for i in range(3)] == list(columns)
    assert cell(widget, 1, 1) == "(2 0 0)"
    # A number goes right so the decimal points line up, a word left.
    assert cell(widget, 1, 2, Qt.TextAlignmentRole) == \
        int(Qt.AlignRight | Qt.AlignVCenter)
    assert cell(widget, 1, 1, Qt.TextAlignmentRole) == \
        int(Qt.AlignLeft | Qt.AlignVCenter)


def test_a_column_is_wide_enough_for_its_hundredth_row(dock):
    """The bug capping the measurement introduced: a reflection
    list's hundredth row is the first whose No. is three digits, so a
    width decided from the first fifty truncates for the rest of the
    table."""
    rows = tuple(Row.of(n, f"({n} 0 0)") for n in range(1, 4001))
    dock.show_report(Report(blocks=(Table(columns=("No.", "hkl"),
                                          rows=rows),)), "PXRD")
    widget = dock._blocks[0].findChild(QTableView)
    metrics = widget.fontMetrics()

    assert widget.columnWidth(0) > metrics.horizontalAdvance("4000")
    assert widget.columnWidth(1) > metrics.horizontalAdvance("(4000 0 0)")


def test_a_column_is_wide_enough_for_its_heading(dock):
    """A one-character column still has to fit ``No.``"""
    dock.show_report(Report(blocks=(Table(
        columns=("No.", "hkl"),
        rows=(Row.of(1, "(1 0 0)"),)),)), "PXRD")
    widget = dock._blocks[0].findChild(QTableView)

    assert widget.columnWidth(0) > \
        widget.fontMetrics().horizontalAdvance("No.")


def test_a_table_exports_as_csv(dock, tmp_path, monkeypatch):
    """Every table, not only the reflection list: the panel knows no
    module, and a pore-diameter table somebody wants in a spreadsheet
    is the same request."""
    from PySide6.QtWidgets import QFileDialog, QPushButton

    target = tmp_path / "out.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(target), "")))
    dock.show_report(Report(blocks=(Table(
        columns=("No.", "hkl", "d"),
        rows=(Row.of(1, "(1 0 0)", "9.000"),
              Row.of(2, "(2 0 0)", "4.500"))),)), "PXRD")
    button = next(b for b in dock._blocks[0].findChildren(QPushButton)
                  if "Export" in b.text())
    button.click()

    assert target.read_text() == ("No.,hkl,d\n"
                                  "1,(1 0 0),9.000\n"
                                  "2,(2 0 0),4.500\n")


def test_a_cancelled_export_writes_nothing(dock, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QPushButton

    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: ("", "")))
    dock.show_report(a_table(), "Zeo++")
    button = next(b for b in dock._blocks[0].findChildren(QPushButton)
                  if "Export" in b.text())
    button.click()

    assert list(tmp_path.iterdir()) == []


def a_long_table(rows: int = 4000) -> Report:
    return Report(blocks=(Table(
        title="Reflections",
        columns=("No.", "hkl"),
        rows=tuple(Row.of(n, f"({n} 0 0)")
                   for n in range(1, rows + 1))),))


def test_a_long_table_scrolls_instead_of_growing(dock):
    """Laid out at its full height a reflection list is a widget tens
    of thousands of pixels tall inside the panel's own scroll area,
    and the panel has to lay that out again for every wheel click --
    which is what made it scroll badly."""
    dock.show_report(a_long_table(), "PXRD")
    widget = dock._blocks[0].findChild(QTableView)

    assert widget.model().rowCount() == 4000
    assert widget.height() < 800


def test_only_the_table_scrolls_and_not_the_panel_too(dock, qtbot):
    """Two scrollbars fought: reaching the Export button under a long
    table meant scrolling the outer one past a widget that swallowed
    the wheel."""
    dock.show_report(a_long_table(), "PXRD")
    dock.resize(700, 620)
    dock.show()
    qtbot.waitExposed(dock)
    qtbot.wait(150)

    assert dock.widget().verticalScrollBar().maximum() == 0


def test_the_table_takes_the_height_the_panel_grows_by(dock, qtbot):
    """The whole point of the size policy: the leftover is the
    table's, at every size, without anybody computing it."""
    dock.show_report(a_long_table(), "PXRD")
    dock.show()
    qtbot.waitExposed(dock)
    view = dock._blocks[0].findChild(QTableView)

    heights = []
    for height in (500, 700, 900):
        dock.resize(700, height)
        qtbot.wait(150)
        heights.append(view.height())

    assert heights == sorted(heights)
    assert heights[0] < heights[-1]
    assert dock.widget().verticalScrollBar().maximum() == 0


def test_a_table_hints_at_its_minimum_so_the_panel_can_shrink(dock):
    """``QScrollArea`` sizes its child to ``max(viewport, sizeHint)``
    and never to its minimum, so a table that hinted at its content
    kept the outer scrollbar alive whatever else was done."""
    dock.show_report(a_long_table(), "PXRD")
    view = dock._blocks[0].findChild(QTableView)

    assert view.sizeHint().height() == view.minimumHeight()
    assert view.minimumHeight() < int(view.property("naturalHeight"))


def test_a_short_table_is_left_at_its_own_height(dock, qtbot):
    """The leftover goes to the table, but never past its own content
    -- three pore diameters do not become a tall empty box."""
    dock.show_report(a_table(), "Zeo++")
    dock.resize(700, 700)
    dock.show()
    qtbot.waitExposed(dock)
    qtbot.wait(150)
    view = dock._blocks[0].findChild(QTableView)

    assert view.height() == int(view.property("naturalHeight"))
    assert view.maximumHeight() == int(view.property("naturalHeight"))


def test_a_rows_meaning_is_its_tooltip(dock):
    """A free sphere diameter read as an included one is a number that
    will be wrong in a paper, so the caveat is where the number is."""
    dock.show_report(a_table(), "Zeo++")
    widget = dock._blocks[0].findChild(QTableView)

    assert "admit" in cell(widget, 0, 0, Qt.ToolTipRole)


def test_a_histogram_becomes_a_plot(dock):
    dock.show_report(a_histogram(), "Zeo++: PSD")
    plot = dock._blocks[0].findChild(HistogramPlot)
    assert plot is not None
    assert plot.histogram.n_bins == 40


def test_a_second_report_replaces_the_first(dock):
    dock.show_report(a_histogram(), "one")
    dock.show_report(a_table(), "two")

    assert len(dock._blocks) == 1
    assert dock._blocks[0].findChild(HistogramPlot) is None
    assert dock._blocks[0].findChild(QTableView) is not None


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
