"""
xtalapp.docks.results
=====================
What the last module run came to.

Every module before Zeo++ answered in a sentence, and a sentence fits
in the status bar.  Three pore diameters do not, and a pore size
distribution is a picture -- so this is where a
:class:`~xtal.modules.report.Report` is shown.

**It knows no module.**  It renders tables and histograms, and which
module produced them is a string in the heading.  A module that grows
a report appears here without this file changing, which is the same
promise the module tree makes.

**It is the run's answer, not a history.**  One report at a time, the
last one, and the run folder underneath the structure is where the
older ones are -- with the same numbers in ``run.log``, written there
by the module itself.  A panel that accumulated runs would be a second
answer to a question the workspace tree already answers, and the one
that goes stale.

**A number is shown with what makes it mean something.**  Each row can
carry a sentence, and it is the row's tooltip rather than a footnote:
a surface area quoted without its probe radius, or a free sphere
diameter read as an included one, is a number that will be wrong in a
paper.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDockWidget,
    QHeaderView,
    QLabel,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from xtal.modules.report import Histogram, Table
from xtalapp.histogram import HistogramPlot

COLUMNS = ["Quantity", "Value", "Unit"]

EMPTY = ("Nothing has been run yet.\n\n"
         "A module that produces a table or a histogram -- Zeo++'s "
         "pore diameters, its surface area, its pore size "
         "distribution -- shows it here when it finishes.")


class ResultsDock(QDockWidget):
    """The report from the last module run."""

    def __init__(self, parent=None):
        super().__init__("Results", parent)
        self.setObjectName("ResultsDock")
        self.setAllowedAreas(Qt.LeftDockWidgetArea |
                             Qt.RightDockWidgetArea |
                             Qt.BottomDockWidgetArea)

        self.heading = QLabel("")
        self.heading.setWordWrap(True)
        font = self.heading.font()
        font.setBold(True)
        self.heading.setFont(font)

        self.note = QLabel(EMPTY)
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color: palette(mid);")

        self.body = QVBoxLayout()
        self.body.setContentsMargins(8, 8, 8, 8)
        self.body.setSpacing(6)
        self.body.addWidget(self.heading)
        self.body.addWidget(self.note)
        self.body.addStretch(1)

        inner = QWidget()
        inner.setLayout(self.body)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(inner)
        self.setWidget(area)
        self._blocks: list[QWidget] = []
        self.clear()

    # -- what is in it -------------------------------------------------

    def clear(self) -> None:
        self.heading.setText("")
        self.heading.setVisible(False)
        self.note.setText(EMPTY)
        self.note.setVisible(True)
        self._drop_blocks()

    def show_report(self, report, title: str = "") -> None:
        """Render a report, or go back to empty when there is none.

        Called for every finished run, including the ones with nothing
        to show -- otherwise the panel would go on displaying the
        previous run's numbers under the current run's heading, which
        is the one failure that would make it worse than no panel.
        """
        self._drop_blocks()
        if report is None or not report:
            self.clear()
            if title:
                self.heading.setText(title)
                self.heading.setVisible(True)
                self.note.setText(
                    "This run had nothing to tabulate.  What it said "
                    "is in the status bar, and what it wrote is in "
                    "its run folder.")
            return
        self.heading.setText(title or report.title or "Results")
        self.heading.setVisible(True)
        self.note.setText(report.note)
        self.note.setVisible(bool(report.note))
        for block in report.blocks:
            widget = self._render(block)
            if widget is not None:
                self._blocks.append(widget)
                # Before the stretch, which is always the last item.
                self.body.insertWidget(self.body.count() - 1, widget)

    def _render(self, block):
        if isinstance(block, Table):
            return _table_widget(block)
        if isinstance(block, Histogram):
            return _histogram_widget(block)
        return None                                 # pragma: no cover

    def _drop_blocks(self) -> None:
        for widget in self._blocks:
            self.body.removeWidget(widget)
            widget.setParent(None)
            widget.deleteLater()
        self._blocks = []


def _table_widget(table: Table) -> QWidget:
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(3)
    if table.title:
        layout.addWidget(QLabel(table.title))

    widget = QTableWidget(len(table.rows), len(COLUMNS))
    widget.setHorizontalHeaderLabels(COLUMNS)
    widget.verticalHeader().setVisible(False)
    widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectRows)
    widget.horizontalHeader().setSectionResizeMode(
        0, QHeaderView.Stretch)
    widget.horizontalHeader().setSectionResizeMode(
        1, QHeaderView.ResizeToContents)
    widget.horizontalHeader().setSectionResizeMode(
        2, QHeaderView.ResizeToContents)
    for row, entry in enumerate(table.rows):
        name = f"{entry.label} ({entry.symbol})" if entry.symbol \
            else entry.label
        for column, text in enumerate((name, entry.value, entry.unit)):
            item = QTableWidgetItem(text)
            if entry.note:
                item.setToolTip(entry.note)
            if column == 1:
                item.setTextAlignment(Qt.AlignRight |
                                      Qt.AlignVCenter)
            widget.setItem(row, column, item)
    # Tall enough for its own rows and no taller: several tables in a
    # column, each with its own scrollbar, is unreadable.
    height = widget.horizontalHeader().height() + 2
    for row in range(widget.rowCount()):
        height += widget.rowHeight(row)
    widget.setFixedHeight(height + 2)
    widget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    layout.addWidget(widget)

    if table.note:
        note = QLabel(table.note)
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(mid);")
        layout.addWidget(note)
    return box


def _histogram_widget(histogram: Histogram) -> QWidget:
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(3)
    if histogram.title:
        layout.addWidget(QLabel(histogram.title))
    plot = HistogramPlot()
    plot.set_histogram(histogram)
    layout.addWidget(plot)
    if histogram.note:
        note = QLabel(histogram.note)
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(mid);")
        layout.addWidget(note)
    return box
