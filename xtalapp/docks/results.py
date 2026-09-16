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

from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from xtal.modules.report import (
    Bands,
    Curve,
    Dos,
    Histogram,
    Modes,
    Surface,
    Table,
    Zone,
    is_number,
)
from xtalapp.curve import CurvePlot
from xtalapp.dialogs import landscape as landscape_window
from xtalapp.dialogs import pattern as pattern_window
from xtalapp.heatmap import HeatmapPlot
from xtalapp.histogram import HistogramPlot

#: The fewest rows a table is ever squeezed to.  Below this it stops
#: being a table and becomes a slot, and the panel is better off
#: scrolling instead.
#:
#: Three and not four, and the difference is one row of the *whole
#: panel*: with the curve at its own 200 px minimum, four rows put a
#: PXRD report fourteen pixels over a 640 px dock -- so the outer
#: scrollbar came back for the sake of one row of a table that is
#: scrolling anyway.
MIN_TABLE_ROWS = 3

#: Pixels held back when dividing the panel up.  The arithmetic
#: lands a few short of the frame's own, and a five-pixel outer
#: scrollbar is the exact thing :meth:`ResultsDock.fit_tables` exists
#: to remove.  It usually costs nothing, because the heights are
#: snapped to whole rows afterwards and a row is thirty pixels.
SLACK = 8

#: What a long table is given before the panel has a size to divide up
#: -- :meth:`ResultsDock.fit_tables` replaces it the moment there is
#: one.
FIT_ROWS = 24

#: Qt's "no parent", as a singleton: the row and column counts take
#: one as a default and constructing a fresh ``QModelIndex`` in a
#: signature is both wasteful and what B008 is about.
NO_PARENT = QModelIndex()

EMPTY = ("Nothing has been run yet.\n\n"
         "A module that produces a table, a histogram or a curve -- "
         "Zeo++'s pore diameters, its pore size distribution, a "
         "calculated PXRD pattern -- shows it here when it "
         "finishes.")


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
        stretched = False
        # A density of states from the same run as a band structure is
        # drawn beside it on the one energy axis, not as a block below.
        self._beside = report.doses[0] if report.bands and report.doses \
            else None
        for block in report.blocks:
            if isinstance(block, Dos) and block is self._beside:
                continue
            widget = self._render(block)
            if widget is None:
                continue
            self._blocks.append(widget)
            # A table is the only block that can be any height it
            # likes -- a curve wants its aspect and a label wants its
            # text -- so it is the one given a stretch factor, and the
            # layout hands it whatever the others are not using.
            grows = bool(widget.findChildren(QTableView))
            self.body.addWidget(widget, 1 if grows else 0)
            stretched = stretched or grows
        self._set_tail(stretched)

    # -- one scrollbar, not two ----------------------------------------

    def _set_tail(self, stretched: bool) -> None:
        """Keep the blocks at the top, unless a table is taking the
        slack.

        **The panel had two scrollbars and they fought.**  A long
        table was laid out at a fixed number of rows, which left the
        panel taller than the dock -- so the reflection list scrolled
        inside a panel that also scrolled, and reaching the *Export
        table* button under a table meant scrolling the outer one past
        a widget that swallowed the wheel.

        The fix is a size policy and not arithmetic, and it is worth
        saying that the arithmetic was written first: measure the
        other blocks, give the difference to the tables, correct on a
        second pass.  It could not be made to settle.  Every quantity
        it needed -- a wrapped label's height, the viewport's height,
        the layout's cached size hint -- is only true *after* the
        layout has run, and changing a table's height runs it again;
        the passes raced with the resize and the panel came up
        differently on the same dock twice running.

        So the table is told what it is instead: at least
        :data:`MIN_TABLE_ROWS` tall, never taller than its own rows,
        and vertically expanding with a stretch factor of one.  Qt
        then gives it exactly the space the other blocks are not
        using, synchronously, on every layout, and the trailing
        spacer -- which would otherwise compete for the same slack --
        is only added when there is no table to take it.
        """
        last = self.body.itemAt(self.body.count() - 1)
        if last is not None and last.spacerItem() is not None:
            self.body.takeAt(self.body.count() - 1)
        if not stretched:
            self.body.addStretch(1)

    def _render(self, block):
        if isinstance(block, Table):
            return _table_widget(block)
        if isinstance(block, Histogram):
            return _histogram_widget(block)
        if isinstance(block, Curve):
            return _curve_widget(block, self)
        if isinstance(block, Bands):
            return _bands_widget(block, getattr(self, "_beside", None))
        if isinstance(block, Dos):
            return _dos_widget(block)
        if isinstance(block, Modes):
            return _modes_widget(block, self)
        if isinstance(block, Zone):
            return _zone_widget(block)
        if isinstance(block, Surface):
            return _surface_widget(block, self)
        return None                                 # pragma: no cover

    def _drop_blocks(self) -> None:
        for widget in self._blocks:
            self.body.removeWidget(widget)
            widget.setParent(None)
            widget.deleteLater()
        self._blocks = []


class TableModel(QAbstractTableModel):
    """A :class:`~xtal.modules.report.Table`, as a model.

    A model rather than the ``QTableWidget`` this used to build, and
    the reason is one table: a reflection list is a few thousand rows
    of five columns, which is fifteen thousand ``QTableWidgetItem``
    objects to construct, own and lay out for a panel that shows
    twenty of them at a time.  A model constructs none -- Qt asks for
    the cells it is about to paint -- so the list opens instantly and
    scrolls at whatever the view can draw.

    It is not a PXRD model.  It reads :attr:`Row.texts`, so the three
    columns every other table has and the five this one has are the
    same case.
    """

    def __init__(self, table: Table, parent=None):
        super().__init__(parent)
        self.table = table

    def rowCount(self, parent=NO_PARENT) -> int:
        return 0 if parent.isValid() else len(self.table.rows)

    def columnCount(self, parent=NO_PARENT) -> int:
        return 0 if parent.isValid() else len(self.table.columns)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():                     # pragma: no cover
            return None
        row = self.table.rows[index.row()]
        cells = row.texts
        text = (cells[index.column()]
                if index.column() < len(cells) else "")
        if role == Qt.DisplayRole:
            return text
        if role == Qt.ToolTipRole:
            return row.note or None
        if role == Qt.TextAlignmentRole:
            # Numbers right so the decimal points line up, words
            # left -- decided by the cell, see `report.is_number`.
            return int(Qt.AlignRight | Qt.AlignVCenter) \
                if is_number(text) \
                else int(Qt.AlignLeft | Qt.AlignVCenter)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole or orientation != Qt.Horizontal:
            return None
        return self.table.columns[section]


class FittedTable(QTableView):
    """A table that asks for the least it can live with.

    ``QScrollArea`` with ``widgetResizable`` sizes its child to
    ``max(viewport, sizeHint)`` and never to its *minimum*, so a
    panel whose size hint exceeds the viewport scrolls rather than
    compressing -- and a table's own hint is its content, which for a
    reflection list is enormous.  That is what kept the outer
    scrollbar alive after everything else was in place.

    So this hints at its minimum and grows by policy instead: the
    layout hands it whatever the other blocks are not using, up to its
    maximum, and the panel's hint stays small enough that the
    scrollbar has nothing to do.
    """

    def sizeHint(self):
        hint = super().sizeHint()
        hint.setHeight(self.minimumHeight())
        return hint


def _table_widget(table: Table) -> QWidget:
    box = QWidget()
    box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(3)
    if table.title:
        layout.addWidget(QLabel(table.title))

    widget = FittedTable()
    model = TableModel(table, widget)
    widget.setModel(model)
    widget.verticalHeader().setVisible(False)
    widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectRows)
    widget.setAlternatingRowColors(len(table.rows) > FIT_ROWS)
    # Uniform heights lets the view size itself without measuring
    # every row, which is the other half of a long table being cheap.
    widget.verticalHeader().setDefaultSectionSize(
        widget.fontMetrics().height() + 8)
    widget.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
    header = widget.horizontalHeader()
    # The first column takes the slack in a Quantity/Value/Unit
    # table, because that is where the sentence is; in a table with
    # columns of its own every column is measured -- see `_widths`.
    if table.named_columns:
        # Nothing stretches: a reflection table is five narrow
        # columns of numbers, and giving the slack to the last of
        # them puts I(%) an inch away from the 2-theta it belongs
        # to.  Empty space to the right of a packed table reads as
        # empty space; a stretched column reads as a mistake.
        header.setStretchLastSection(False)
        for column, width in enumerate(_widths(table, widget)):
            header.setSectionResizeMode(column, QHeaderView.Interactive)
            widget.setColumnWidth(column, width)
    else:
        header.setVisible(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, len(table.columns)):
            header.setSectionResizeMode(
                column, QHeaderView.ResizeToContents)

    rows = len(table.rows)
    row_height = widget.verticalHeader().defaultSectionSize()
    # `isHidden` and not `isVisible`: this widget has not been shown
    # yet, so `isVisible` is False for a header that is going to be
    # there and the table would come up one header short.
    # The header plus the frame, and nothing else: a table whose
    # height is its chrome plus a whole number of rows shows whole
    # rows, and every pixel over shows a sliver of the next one.
    chrome = ((0 if header.isHidden() else header.sizeHint().height())
              + 2 * widget.frameWidth())
    # What it would be at its full height, and the two numbers
    # `ResultsDock.fit_tables` needs to shrink it to a whole number of
    # rows.  Recorded on the widget rather than returned, so that the
    # dock can find every table in a report without this function and
    # `_render` both having to carry them out.
    natural = chrome + rows * row_height
    widget.setProperty("naturalHeight", natural)
    widget.setProperty("rowHeight", row_height)
    widget.setProperty("chrome", chrome)
    widget.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
    # Between four rows and all of them, and expanding in between --
    # see `ResultsDock._set_tail` for why this is a size policy and
    # not a calculation.
    widget.setMinimumHeight(min(natural,
                                chrome + MIN_TABLE_ROWS * row_height))
    widget.setMaximumHeight(natural)
    widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
    layout.addWidget(widget, 1)

    export = QPushButton("Export table...")
    export.setToolTip(
        "Write this table as a .csv -- the heading row and the cells, "
        "which is what a spreadsheet reads")
    export.clicked.connect(lambda: _export_table(table, box))
    row = QHBoxLayout()
    row.addWidget(export)
    row.addStretch(1)
    layout.addLayout(row)

    if table.note:
        note = QLabel(table.note)
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(mid);")
        layout.addWidget(note)
    return box


def _widths(table: Table, widget) -> list[int]:
    """A pixel width per column, wide enough for every cell in it.

    Measured here rather than left to ``ResizeToContents``, and both
    halves of that are deliberate.  ``ResizeToContents`` measures
    *every* row, which on a few thousand is O(rows) per layout and is
    paid again on every scroll; capping it with
    ``setResizeContentsPrecision`` fixes the cost and introduces a
    worse bug, because the cap measures the first fifty rows and a
    reflection list's hundredth row is the first one whose **No.** is
    three digits.  The column then truncates for the rest of the
    table.

    So: the longest string in each column decides it.  Only the
    longest few are handed to the font -- ties are common in a column
    of numbers and measuring three thousand strings is the cost this
    is avoiding -- and the heading is always one of the candidates,
    because a one-character column still has to fit ``No.``.
    """
    metrics = widget.fontMetrics()
    padding = 18                    # the cell's own margins, plus air
    out = []
    for column, heading in enumerate(table.columns):
        texts = [row.texts[column] for row in table.rows
                 if column < len(row.texts)]
        longest = max((len(text) for text in texts), default=0)
        candidates = [heading] + [text for text in texts
                                  if len(text) == longest]
        out.append(max(metrics.horizontalAdvance(text)
                       for text in candidates[:32]) + padding)
    return out


def _export_table(table: Table, parent) -> None:
    """Write one table as a ``.csv`` where the user asks for it.

    Every table, not only the reflection list: the panel knows no
    module, and a pore-diameter table somebody wants in a spreadsheet
    is the same request.  What gets written is
    :meth:`~xtal.modules.report.Table.as_csv`, so the file is the same
    one the CLI would produce.
    """
    from xtal.workspace import safe_name

    suggested = safe_name(table.title or "table", "table").lower()
    path, _filter = QFileDialog.getSaveFileName(
        parent, "Export the table", f"{suggested}.csv",
        "Comma-separated values (*.csv);;All files (*)")
    if not path:
        return
    try:
        Path(path).write_text(table.as_csv(), encoding="utf-8")
    except OSError as exc:
        QMessageBox.warning(parent, "Export the table", str(exc))


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


def _curve_widget(curve: Curve, dock) -> QWidget:
    """A trace, and the button that opens it properly.

    The plot in the panel is :mod:`xtalapp.curve` and needs nothing
    installed; the button is the matplotlib window, which is the
    ``pxrd`` extra.  Both are here rather than one instead of the
    other because the panel has to *show* the answer on any machine,
    and only the second can zoom into it, lay a measured file over it
    and write a vector figure.

    Nothing about this is PXRD.  The panel knows no module, and a
    curve from the next one that produces a curve gets the same
    button for the same reason.
    """
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(3)
    if curve.title:
        layout.addWidget(QLabel(curve.title))

    plot = CurvePlot()
    plot.set_curve(curve)
    layout.addWidget(plot)

    open_plot = QPushButton("Plot and overlay data...")
    open_plot.setEnabled(pattern_window.installed())
    open_plot.setToolTip(
        "Zoom, overlay a measured .xy pattern, and export a figure"
        if pattern_window.installed() else pattern_window.MISSING)
    open_plot.clicked.connect(lambda: _open_pattern(curve, dock))
    row = QHBoxLayout()
    row.addWidget(open_plot)
    row.addStretch(1)
    layout.addLayout(row)

    if curve.note:
        note = QLabel(curve.note)
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(mid);")
        layout.addWidget(note)
    return box


def _surface_widget(surface: Surface, dock) -> QWidget:
    """An energy landscape, and the way into the structures behind it.

    Clicking a cell opens that point as a tab.  The grid and the
    hundred CIFs beside it are the same scan seen two ways, and "what
    does the crystal look like *there*" is a question asked at a
    minimum or a ridge -- which makes the picture the fastest way to
    reach the geometry that made it.  The same argument
    :class:`xtalapp.plot.TracePlot` makes about a step of a run.

    A cell whose point never finished has no file, and clicking it
    says so rather than doing nothing: a control that ignores a click
    is indistinguishable from one that is broken.
    """
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(3)
    if surface.title:
        layout.addWidget(QLabel(surface.title))

    plot = HeatmapPlot()
    plot.set_surface(surface)
    plot.cellClicked.connect(
        lambda row, column: _open_point(surface, plot, dock,
                                        row, column))
    layout.addWidget(plot)

    sheets = surface.all_sheets()
    row = QHBoxLayout()
    if len(sheets) > 1:
        # Two directions are two sheets and the reader wants to see
        # each: where they differ is the hysteresis, which is the
        # whole reason a scan is walked both ways.
        chooser = QComboBox()
        chooser.addItems([label for label, _z in sheets])
        chooser.currentIndexChanged.connect(
            lambda index: plot.set_surface(surface, index))
        row.addWidget(QLabel("Branch:"))
        row.addWidget(chooser)

    open_plot = QPushButton("Plot with contours...")
    open_plot.setEnabled(landscape_window.installed())
    open_plot.setToolTip(
        "Contour the landscape, zoom into it, and export a figure"
        if landscape_window.installed() else landscape_window.MISSING)
    open_plot.clicked.connect(lambda: _open_landscape(surface, dock))
    row.addWidget(open_plot)
    row.addStretch(1)
    layout.addLayout(row)

    if surface.note:
        note = QLabel(surface.note)
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(mid);")
        layout.addWidget(note)
    return box


def _open_point(surface, plot, dock, row: int, column: int) -> None:
    """Open the structure behind one cell of a landscape."""
    path = surface.path_at(row, column)
    window = dock.window()
    if not path or not Path(path).exists():
        if hasattr(window, "show_message"):
            window.show_message(
                "that point left no structure behind -- it did not "
                "finish" if not path else
                f"{Path(path).name} is no longer there")
        return
    plot.set_marker((row, column))
    if hasattr(window, "open_path"):
        window.open_path(path)


def _open_landscape(surface: Surface, dock) -> None:
    """Open the matplotlib window, modelessly, as a pattern does."""
    window = landscape_window.LandscapeDialog(surface, dock)
    window.setAttribute(Qt.WA_DeleteOnClose)
    window.setModal(False)
    window.show()
    window.raise_()


def _open_pattern(curve: Curve, dock) -> None:
    """Open the matplotlib window, or say why it did not.

    Modeless and owned by the dock, so a pattern can stay on screen
    while the structure it came from is worked on -- which is most of
    what somebody comparing a calculation with a measurement is doing.
    """
    window = pattern_window.PatternDialog(curve, dock)
    window.setAttribute(Qt.WA_DeleteOnClose)
    window.setModal(False)
    window.show()
    window.raise_()


def _window_spinboxes(values, targets):
    """Two energy spinboxes that drive every plot in ``targets``."""
    from PySide6.QtWidgets import QDoubleSpinBox

    low, high = QDoubleSpinBox(), QDoubleSpinBox()
    for spin, value in ((low, values[0]), (high, values[1])):
        spin.setRange(-200.0, 200.0)
        spin.setDecimals(1)
        spin.setSingleStep(0.5)
        spin.setSuffix(" eV")
        spin.setValue(value)
        spin.valueChanged.connect(
            lambda _v: [plot.set_window(low.value(), high.value())
                        for plot in targets])
    low.setToolTip("Lowest energy shown, relative to the Fermi level")
    high.setToolTip("Highest energy shown, relative to the Fermi level")
    return low, high


def _dos_widget(dos: Dos) -> QWidget:
    from xtalapp.bands import DosPlot

    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(3)
    if dos.title:
        layout.addWidget(QLabel(dos.title))
    plot = DosPlot()
    plot.set_dos(dos)
    layout.addWidget(plot)
    low, high = _window_spinboxes(dos.window, [plot])
    export = QPushButton("Export DOS...")
    export.setToolTip("The broadened curves as a .dat table")
    export.clicked.connect(lambda: _export_dos(dos, box))
    row = QHBoxLayout()
    for widget in (QLabel("From"), low, QLabel("to"), high):
        row.addWidget(widget)
    row.addStretch(1)
    row.addWidget(export)
    layout.addLayout(row)
    box.plot, box.low, box.high = plot, low, high
    if dos.note:
        note = QLabel(dos.note)
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(mid);")
        layout.addWidget(note)
    return box


def _export_dos(dos: Dos, parent) -> None:
    path, _chosen = QFileDialog.getSaveFileName(
        parent, "Export the density of states", "dos.dat",
        "DOS table (*.dat);;All files (*)")
    if not path:
        return
    try:
        Path(path).write_text(dos.as_dat(), encoding="utf-8")
    except OSError as exc:
        QMessageBox.warning(parent, "Export the density of states",
                            str(exc))


def _bands_widget(bands: Bands, dos: Dos | None = None) -> QWidget:
    """The band structure, the energy window, and the export.

    The window is two spinboxes rather than a zoom: what a reader
    changes is which few eV around the gap are shown, and a number
    typed is a number that can be quoted in a caption.
    """
    from xtalapp.bands import BandsPlot, DosPlot

    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(3)
    if bands.title:
        layout.addWidget(QLabel(bands.title))
    plot = BandsPlot()
    plot.set_bands(bands)
    plots = [plot]
    side = None
    if dos is not None:
        side = DosPlot(axis=False)
        side.set_dos(dos)
        side.set_window(*bands.window)
        plots.append(side)
        pair = QHBoxLayout()
        pair.setSpacing(0)
        pair.addWidget(plot, 3)
        pair.addWidget(side, 1)
        layout.addLayout(pair)
    else:
        layout.addWidget(plot)

    low, high = _window_spinboxes(bands.window, plots)
    export = QPushButton("Export band structure...")
    export.setToolTip("The numbers as .dat or .csv, or the figure as "
                      "PNG, SVG or PDF")
    export.clicked.connect(
        lambda: _export_bands(bands, plot.energy_window, box, dos))
    row = QHBoxLayout()
    row.addWidget(QLabel("From"))
    row.addWidget(low)
    row.addWidget(QLabel("to"))
    row.addWidget(high)
    row.addStretch(1)
    row.addWidget(export)
    layout.addLayout(row)
    # Held on the box so a test -- and nothing else -- can reach them.
    box.plot, box.low, box.high, box.export = plot, low, high, export
    box.dos = side
    if bands.note:
        note = QLabel(bands.note)
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(mid);")
        layout.addWidget(note)
    return box


def _export_bands(bands: Bands, window, parent, dos=None) -> None:
    from xtalapp.bands import export_figure, figure_formats

    path, chosen = QFileDialog.getSaveFileName(
        parent, "Export the band structure", "bands.png",
        figure_formats())
    if not path:
        return
    try:
        export_figure(bands, path, window, dos)
    except (OSError, ValueError, ImportError) as exc:
        QMessageBox.warning(parent, "Export the band structure",
                            str(exc))


def _zone_widget(zone: Zone) -> QWidget:
    from xtalapp.widgets.brillouin import BrillouinView

    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(3)
    if zone.title:
        layout.addWidget(QLabel(zone.title))
    view = BrillouinView()
    view.set_lattice(zone.lattice)
    view.set_path(dict(zone.points), zone.runs)
    view.setMinimumHeight(260)
    layout.addWidget(view)
    box.view = view
    return box


def _modes_widget(modes: Modes, dock) -> QWidget:
    """The frequencies, and the button that plays one.

    Animate hands a loop of frames to the transport bar through the
    window the dock belongs to, so a mode is watched the way a
    relaxation is -- scrubbed, looped, and closed without anything
    having been edited.
    """
    from PySide6.QtWidgets import QDoubleSpinBox

    from xtal.modules.report import Row

    rows = tuple(Row.of(n + 1, f"{f:.2f}",
                        "imaginary" if modes.is_imaginary(f) else "")
                 for n, f in enumerate(modes.frequencies))
    box = _table_widget(Table(
        modes.title, rows, columns=("Mode", "cm-1", "")))
    view = box.findChild(QTableView)
    amplitude = QDoubleSpinBox()
    amplitude.setRange(0.01, 2.0)
    amplitude.setSingleStep(0.05)
    amplitude.setValue(0.3)
    amplitude.setSuffix(" A")
    amplitude.setToolTip("How far the atom that moves most travels")
    animate = QPushButton("Animate mode")
    animate.setToolTip("Play the selected mode in the transport bar")
    animate.clicked.connect(
        lambda: _animate_mode(modes, view, amplitude.value(), dock))
    export = QPushButton("Export modes...")
    export.clicked.connect(lambda: _export_modes(modes, box))
    row = QHBoxLayout()
    row.addWidget(QLabel("Amplitude"))
    row.addWidget(amplitude)
    row.addWidget(animate)
    row.addStretch(1)
    row.addWidget(export)
    box.layout().addLayout(row)
    box.view, box.amplitude, box.animate = view, amplitude, animate
    if len(rows):
        # The highest mode is the one anybody checks first, and it is
        # never one of a molecule's near-zero translations.
        view.selectRow(len(rows) - 1)
    if modes.note:
        note = QLabel(modes.note)
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(mid);")
        box.layout().addWidget(note)
    return box


def _animate_mode(modes: Modes, view, amplitude: float, dock) -> bool:
    from xtal.modules.dftb_runs.modes import mode_trajectory

    selected = view.selectionModel().selectedRows()
    if not selected:
        return False
    window = dock.parent()
    trajectories = getattr(window, "trajectory_dock", None)
    if trajectories is None:
        return False
    return trajectories.open_trajectory(
        mode_trajectory(modes, selected[0].row(), amplitude))


def _export_modes(modes: Modes, parent) -> None:
    path, _chosen = QFileDialog.getSaveFileName(
        parent, "Export the modes", "modes.dat",
        "Modes table (*.dat);;All files (*)")
    if not path:
        return
    try:
        Path(path).write_text(modes.as_dat(), encoding="utf-8")
    except OSError as exc:
        QMessageBox.warning(parent, "Export the modes", str(exc))
