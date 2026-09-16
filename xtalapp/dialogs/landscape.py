"""
xtalapp.dialogs.landscape
=========================
An energy landscape, contoured, in a window of its own.

The panel draws the same grid with nothing installed -- see
:mod:`xtalapp.heatmap`, and the note in ``pyproject.toml`` about why
every panel must.  This is the other half of the bargain the PXRD
pattern already struck: the *window* may need matplotlib, and buys
contours, a colour bar with a scale somebody chose, zoom, and a
vector figure for a paper.

Picking stays in the panel.  A reader opens this to look at the shape
of the landscape and to export it; the click that opens the structure
at a point belongs where the hundred files are one click away, which
is the dock.

The contours are the reason this exists.  A grid of coloured squares
says where the minimum is; contour lines say how *steep* the walls
around it are and whether there are two basins with a ridge between
them, which is the entire question asked of a flexible framework.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
)

from xtalapp.dialogs.pattern import (
    EDITABLE_TEXT,
    FIGURE_FILTERS,
    RASTER_DPI,
    VECTOR_SUFFIXES,
    _figure_canvas,
)

MISSING = ("matplotlib is not installed, so a landscape can be "
           "looked at in the panel but not contoured, zoomed or "
           "exported as a figure -- "
           "pip install 'crystal-builder[pxrd]'")

#: How many contour lines to draw by default.  Enough to read the
#: shape of a basin and few enough to read the labels on them.
LEVELS = 12

#: The ramp, matched to :func:`xtalapp.heatmap.ramp` in *ordering*
#: rather than in exact colour: both run dark-to-light so the panel
#: and this window say the same thing about which way is uphill.
COLORMAP = "viridis"


def installed() -> bool:
    """Whether matplotlib is importable -- without importing it."""
    try:
        return importlib.util.find_spec("matplotlib") is not None
    except (ImportError, ValueError):               # pragma: no cover
        return False


class LandscapeDialog(QDialog):
    """One :class:`xtal.modules.report.Surface`, contoured.

    Built from the report block rather than from a scan result, for
    the reason :class:`xtalapp.dialogs.pattern.PatternDialog` is: the
    panel that opens it holds a report and knows no module, and a
    window wanting the result would have made the panel know about
    scans.
    """

    def __init__(self, surface, parent=None, directory: str = ""):
        super().__init__(parent)
        self.setWindowTitle(surface.title or "Energy landscape")
        self.surface = surface
        self.directory = str(directory or "")
        self.sheet = 0

        canvas_class, toolbar_class, figure_class = _figure_canvas()
        self.figure = figure_class(figsize=(6.4, 5.0))
        self.axes = self.figure.add_subplot(111)
        self.canvas = canvas_class(self.figure)
        self.canvas.setMinimumSize(520, 400)
        self.canvas.setFocusPolicy(Qt.StrongFocus)
        self.toolbar = toolbar_class(self.canvas, self)
        self._bar = None

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: palette(mid);")

        self.levels = QSpinBox()
        self.levels.setRange(2, 60)
        self.levels.setValue(LEVELS)
        self.levels.setToolTip(
            "How many contour lines to draw between the lowest and "
            "highest point")
        self.levels.valueChanged.connect(self.draw)

        self.filled = QCheckBox("Fill")
        self.filled.setChecked(True)
        self.filled.setToolTip(
            "Colour between the contours as well as drawing them")
        self.filled.toggled.connect(self.draw)

        self.branch = QComboBox()
        self.branch.addItems(
            [label for label, _z in surface.all_sheets()])
        self.branch.setToolTip(
            "A scan walked both ways has two branches; where they "
            "differ is the hysteresis")
        self.branch.currentIndexChanged.connect(self._pick_branch)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.figure_button = buttons.addButton(
            "Save figure...", QDialogButtonBox.ActionRole)
        self.figure_button.setToolTip(
            "PDF, SVG or EPS keeps the text editable in a vector "
            "editor; PNG and TIFF are raster")
        self.figure_button.clicked.connect(self.save_figure)
        self.data_button = buttons.addButton(
            "Save data...", QDialogButtonBox.ActionRole)
        self.data_button.setToolTip(
            "One row per point, with the file behind each")
        self.data_button.clicked.connect(self.save_data)
        buttons.rejected.connect(self.reject)

        controls = QHBoxLayout()
        if len(surface.all_sheets()) > 1:
            controls.addWidget(QLabel("Branch:"))
            controls.addWidget(self.branch)
        controls.addWidget(QLabel("Contours:"))
        controls.addWidget(self.levels)
        controls.addWidget(self.filled)
        controls.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, 1)
        layout.addLayout(controls)
        layout.addWidget(self.status)
        layout.addWidget(buttons)
        self.resize(720, 640)
        self.draw()

    # -- drawing -------------------------------------------------------

    def _pick_branch(self, index: int) -> None:
        self.sheet = int(index)
        self.draw()

    def values(self) -> np.ndarray:
        sheets = self.surface.all_sheets()
        return np.asarray(
            sheets[min(self.sheet, len(sheets) - 1)][1], dtype=float)

    def draw(self) -> None:
        """Redraw from scratch.

        Cheap -- a landscape is tens of points, not the ten thousand a
        pattern has -- and it keeps the contour count, the fill and the
        branch from having to be undone one at a time.
        """
        # The whole figure, not ``axes.clear()`` and a colour bar
        # taken off afterwards.  Clearing the axes detaches the
        # mappable the bar was made from, and ``Colorbar.remove`` then
        # fails restoring a subplotspec that is no longer there --
        # which is what unticking Fill used to do.  A landscape is
        # tens of points, so building the figure again costs nothing
        # and there is no teardown order left to get wrong.
        self.figure.clear()
        self.axes = self.figure.add_subplot(111)
        self._bar = None
        surface = self.surface
        values = self.values()
        if values.size < 4:
            self.axes.text(0.5, 0.5, "not enough points to contour",
                           ha="center", va="center",
                           transform=self.axes.transAxes)
            self.canvas.draw_idle()
            return

        # A masked array rather than NaN: matplotlib contours NaN by
        # leaving a hole, which is right, but the colour limits have
        # to come from the finished points alone or a single hole
        # takes the whole scale with it.
        grid = np.ma.masked_invalid(values)
        levels = int(self.levels.value())
        if self.filled.isChecked():
            drawn = self.axes.contourf(surface.x, surface.y, grid,
                                       levels=levels, cmap=COLORMAP)
            self._bar = self.figure.colorbar(drawn, ax=self.axes)
            self._bar.set_label(surface.z_label or "")
            self.axes.contour(surface.x, surface.y, grid,
                              levels=levels, colors="white",
                              linewidths=0.4, alpha=0.5)
        else:
            drawn = self.axes.contour(surface.x, surface.y, grid,
                                      levels=levels, cmap=COLORMAP)
            self.axes.clabel(drawn, inline=True, fontsize=7)

        self._mark_minimum(grid)
        self._mark_unfinished(grid)
        self.axes.set_xlabel(surface.x_label or "")
        self.axes.set_ylabel(surface.y_label or "")
        self.axes.set_title(surface.title or "")
        self.figure.tight_layout()
        self.canvas.draw_idle()
        self.status.setText(surface.note or "")

    def _mark_minimum(self, grid) -> None:
        if grid.count() == 0:                       # pragma: no cover
            return
        flat = int(np.ma.argmin(grid))
        row, column = np.unravel_index(flat, grid.shape)
        self.axes.plot(self.surface.x[column], self.surface.y[row],
                       marker="+", color="white", markersize=11,
                       markeredgewidth=1.6)

    def _mark_unfinished(self, grid) -> None:
        """Cross out the points that never produced a number.

        A hole in a contour plot is smoothed over by the interpolation
        on either side of it, which is exactly the kind of quiet
        invention this whole feature has to avoid.
        """
        rows, columns = np.where(np.ma.getmaskarray(grid))
        if not len(rows):
            return
        self.axes.scatter(self.surface.x[columns],
                          self.surface.y[rows], marker="x",
                          color="0.35", s=28, linewidths=1.0,
                          label="did not finish")
        self.axes.legend(loc="best", fontsize=7, framealpha=0.7)

    # -- writing -------------------------------------------------------

    def save_figure(self) -> None:
        """Write the figure, vector or raster, from the suffix."""
        path, _filter = QFileDialog.getSaveFileName(
            self, "Save the figure",
            str(Path(self.directory) / f"{self._stem()}.pdf"),
            FIGURE_FILTERS)
        if not path:
            return
        import matplotlib as mpl

        try:
            with mpl.rc_context(EDITABLE_TEXT):
                self.figure.savefig(path, dpi=RASTER_DPI,
                                    bbox_inches="tight",
                                    facecolor="white")
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Save the figure", str(exc))
            return
        self.directory = str(Path(path).parent)
        self.status.setText(
            f"Wrote {Path(path).name}"
            + (" -- the text in it is still text."
               if Path(path).suffix.lower() in VECTOR_SUFFIXES
               else ""))

    def save_data(self) -> None:
        """Write one row per point, with the file behind each."""
        path, _filter = QFileDialog.getSaveFileName(
            self, "Save the landscape",
            str(Path(self.directory) / f"{self._stem()}.csv"),
            "Comma-separated values (*.csv);;All files (*)")
        if not path:
            return
        try:
            Path(path).write_text(self.surface.as_csv(),
                                  encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Save the landscape", str(exc))
            return
        self.directory = str(Path(path).parent)
        self.status.setText(f"Wrote {Path(path).name}")

    def _stem(self) -> str:
        from xtal.workspace import safe_name
        return safe_name(self.surface.title or "landscape",
                         "landscape").lower()
