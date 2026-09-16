"""
xtalapp.heatmap
===============
An energy landscape, drawn by hand and clickable.

A relaxed scan produces a grid of relaxed structures and one number
each.  The picture is the answer -- where the minima are, whether
there are two of them, where the ridge between them runs -- and every
cell of it is a structure somebody will want to open.  So this is a
panel rather than a window, and it draws with nothing extra installed,
which is the rule the whole application keeps (see the note in
``pyproject.toml``).  The matplotlib *window* beside it, with contours
and a vector export, is what :mod:`xtalapp.dialogs.landscape` is for.

**A cell with no number is drawn apart from the rest.**  Hatched, and
outside the colour scale entirely.  This is the feature's likeliest
way to lie: a point that never relaxed plotted as a zero is the
deepest point of every landscape it appears in, and a landscape with
a false minimum in it looks exactly like a landscape with a real one.
A point that finished but never reached the tolerance is a third
state, drawn with a dot, because it *is* a measurement -- just not one
to read to four figures.

The ramp is ordered by lightness rather than by hue, so the picture
still reads where the printer is monochrome and where the reader does
not separate red from green.  Low is dark and high is light, which is
the way round that puts the interesting part -- the basin -- where the
eye goes first.
"""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

#: Room for the labels: left for the y ticks and the turned y title,
#: bottom for the x ticks and title.
LEFT = 72
BOTTOM = 34
TOP = 8
RIGHT = 74          # the colour bar and its numbers
BAR = 14            # the colour bar itself
GAP = 6

#: The size a landscape is written at when it goes beside the run.
SAVE_SIZE = (720, 560)

MARKER = QColor(255, 255, 255)
UNFINISHED = QColor(150, 150, 150)


def ramp(fraction: float) -> QColor:
    """A perceptually ordered colour for ``fraction`` in ``[0, 1]``.

    Dark blue through green to pale yellow: monotone in lightness, so
    the grid still reads printed in grey and still reads for somebody
    who does not separate red from green.  Written out rather than
    imported because importing it would mean a plotting library, and
    five stops interpolated is the whole of what is needed.
    """
    stops = ((0.00, (24, 24, 84)), (0.25, (30, 94, 130)),
             (0.50, (36, 150, 122)), (0.75, (150, 190, 86)),
             (1.00, (250, 240, 160)))
    value = min(max(float(fraction), 0.0), 1.0)
    for (low, first), (high, second) in zip(stops, stops[1:],
                                            strict=False):
        if value <= high:
            span = (value - low) / (high - low) if high > low else 0.0
            return QColor(*[int(round(a + (b - a) * span))
                            for a, b in zip(first, second,
                                            strict=True)])
    return QColor(*stops[-1][1])                    # pragma: no cover


def _tick(value: float) -> str:
    magnitude = abs(value)
    if magnitude < 1e-9:
        return "0"
    if magnitude >= 1e5 or magnitude < 1e-3:
        return f"{value:.0e}"
    if magnitude >= 1000:
        return f"{value:.0f}"
    return f"{value:.3g}"


class HeatmapPlot(QWidget):
    """A grid of energies, with the structure behind each cell.

    Clicking a cell emits :attr:`cellClicked` with ``(row, column)``
    into the surface's own indexing, which the panel turns into the
    file to open.  The same shape :class:`xtalapp.plot.TracePlot`
    established for turning a point of a plot into the geometry that
    made it.
    """

    cellClicked = Signal(int, int)
    cellHovered = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.surface = None
        self.sheet = 0
        self.marker: tuple[int, int] | None = None
        self._hover: tuple[int, int] | None = None
        self._grid: tuple | None = None
        self.setMinimumHeight(240)
        self.setMouseTracking(True)
        # Deliberately no minimum *width*.  A dock area is as wide as
        # the largest minimum of any dock in it, tabbed behind or not,
        # so a panel that asked for room here would widen the whole
        # column for every other panel too.
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_surface(self, surface, sheet: int = 0) -> None:
        self.surface = surface
        self.sheet = int(sheet)
        self.marker = None
        self._hover = None
        self.update()

    def set_marker(self, cell) -> None:
        """Ring the cell whose structure is open."""
        if cell != self.marker:
            self.marker = cell
            self.update()

    # -- the numbers ---------------------------------------------------

    def values(self) -> np.ndarray | None:
        if self.surface is None:
            return None
        sheets = self.surface.all_sheets()
        if not sheets:
            return None                             # pragma: no cover
        return np.asarray(
            sheets[min(self.sheet, len(sheets) - 1)][1], dtype=float)

    def limits(self) -> tuple[float, float]:
        """The range the colour scale covers.

        Over the finished points alone.  A hole takes no part in it:
        referencing the scale to a NaN would give no scale, and
        referencing it to a zero standing in for one would compress
        every real difference into the top of the ramp.
        """
        values = self.values()
        if values is None or not np.any(np.isfinite(values)):
            return 0.0, 1.0
        low = float(np.nanmin(values))
        high = float(np.nanmax(values))
        return (low, high) if high > low else (low, low + 1.0)

    def cell_at(self, x: float, y: float):
        """Which cell a point on the widget is in, or ``None``."""
        if self._grid is None:
            return None
        left, top, width, height, rows, columns = self._grid
        if not (left <= x < left + width
                and top <= y < top + height):
            return None
        column = int((x - left) / width * columns)
        row = int((y - top) / height * rows)
        if not (0 <= row < rows and 0 <= column < columns):
            return None                             # pragma: no cover
        return row, column

    # -- pointing ------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        cell = self.cell_at(event.position().x(), event.position().y())
        if cell is not None:
            self.cellClicked.emit(int(cell[0]), int(cell[1]))
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        cell = self.cell_at(event.position().x(), event.position().y())
        if cell != self._hover:
            self._hover = cell
            if cell is not None:
                self.cellHovered.emit(int(cell[0]), int(cell[1]))
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        if self._hover is not None:
            self._hover = None
            self.update()
        super().leaveEvent(event)

    def readout(self, cell) -> str:
        """What the corner says about one cell."""
        surface = self.surface
        if surface is None or cell is None:
            return ""
        row, column = cell
        values = self.values()
        if values is None:
            return ""                               # pragma: no cover
        where = (f"{surface.y_label or 'y'} "
                 f"{_tick(float(surface.y[row]))}, "
                 f"{surface.x_label or 'x'} "
                 f"{_tick(float(surface.x[column]))}")
        value = values[row, column]
        if not np.isfinite(value):
            return f"{where}: did not finish"
        mark = ""
        if (surface.converged is not None
                and not surface.converged[row, column]):
            mark = "  (not converged)"
        return f"{where}: {value:.4f}{mark}"

    # -- painting ------------------------------------------------------

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.base())
        surface = self.surface
        values = self.values()
        if surface is None or values is None or not values.size:
            painter.setPen(palette.color(palette.ColorRole.Mid))
            painter.drawText(self.rect(), Qt.AlignCenter,
                             "No scan yet")
            self._grid = None
            return

        rows, columns = values.shape
        width = max(self.width() - LEFT - RIGHT, 20)
        height = max(self.height() - TOP - BOTTOM, 20)
        self._grid = (LEFT, TOP, width, height, rows, columns)
        low, high = self.limits()

        self._cells(painter, values, low, high)
        self._frame(painter, palette)
        self._axes(painter, palette, surface, rows, columns)
        self._bar(painter, palette, low, high)
        if self._hover is not None:
            self._readout(painter, palette)

    def _cells(self, painter, values, low, high) -> None:
        left, top, width, height, rows, columns = self._grid
        surface = self.surface
        span = (high - low) or 1.0
        for row in range(rows):
            for column in range(columns):
                box = QRectF(
                    left + column * width / columns,
                    top + row * height / rows,
                    width / columns + 1.0, height / rows + 1.0)
                value = values[row, column]
                if not np.isfinite(value):
                    self._hatch(painter, box)
                    continue
                painter.fillRect(box, ramp((value - low) / span))
                if (surface.converged is not None
                        and not surface.converged[row, column]):
                    self._doubt(painter, box)
        if self.marker is not None:
            self._ring(painter, self.marker, MARKER, 2.5)
        if self._hover is not None:
            self._ring(painter, self._hover,
                       QColor(255, 255, 255, 170), 1.5)

    def _hatch(self, painter, box) -> None:
        """A cell with no number, drawn so it cannot be read as one."""
        painter.fillRect(box, self.palette().base())
        painter.setPen(QPen(UNFINISHED, 1))
        painter.setClipRect(box)
        step = 5
        start = int(box.left() - box.height())
        for offset in range(start, int(box.right()) + 1, step):
            painter.drawLine(QPointF(offset, box.bottom()),
                             QPointF(offset + box.height(),
                                     box.top()))
        painter.setClipping(False)

    def _doubt(self, painter, box) -> None:
        """A point that finished without reaching the tolerance.

        A dot rather than a hatch: it is a measurement, just not one
        to read to four figures.
        """
        painter.setBrush(QBrush(QColor(20, 20, 20, 190)))
        painter.setPen(Qt.NoPen)
        radius = min(box.width(), box.height()) * 0.12
        painter.drawEllipse(box.center(), radius, radius)
        painter.setBrush(Qt.NoBrush)

    def _ring(self, painter, cell, color, thickness) -> None:
        left, top, width, height, rows, columns = self._grid
        row, column = cell
        if not (0 <= row < rows and 0 <= column < columns):
            return                                  # pragma: no cover
        painter.setPen(QPen(color, thickness))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(
            left + column * width / columns + 1,
            top + row * height / rows + 1,
            width / columns - 2, height / rows - 2))

    def _frame(self, painter, palette) -> None:
        left, top, width, height, _rows, _columns = self._grid
        painter.setPen(QPen(palette.color(palette.ColorRole.Mid), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(left, top, width, height))

    def _axes(self, painter, palette, surface, rows, columns) -> None:
        left, top, width, height, _r, _c = self._grid
        painter.setPen(palette.color(palette.ColorRole.Text))
        metrics = painter.fontMetrics()
        # Every label if they fit, otherwise every second, and so on.
        across = max(1, math.ceil(
            columns * (metrics.horizontalAdvance("00.00") + 10)
            / max(width, 1)))
        for column in range(0, columns, across):
            centre = left + (column + 0.5) * width / columns
            painter.drawText(
                QRectF(centre - 40, top + height + 2, 80,
                       metrics.height()),
                Qt.AlignCenter, _tick(float(surface.x[column])))
        down = max(1, math.ceil(
            rows * (metrics.height() + 4) / max(height, 1)))
        for row in range(0, rows, down):
            middle = top + (row + 0.5) * height / rows
            painter.drawText(
                QRectF(0, middle - metrics.height() / 2, LEFT - 6,
                       metrics.height()),
                Qt.AlignRight | Qt.AlignVCenter,
                _tick(float(surface.y[row])))
        painter.drawText(
            QRectF(left, top + height + metrics.height() + 2, width,
                   metrics.height()),
            Qt.AlignCenter, surface.x_label or "")
        if surface.y_label:
            # Turned on its side against the axis it names.  Saved and
            # restored rather than left rotated, because everything
            # drawn after this -- the colour bar, the readout -- is
            # laid out in widget coordinates.
            painter.save()
            painter.translate(12, top + height / 2)
            painter.rotate(-90)
            painter.drawText(QRectF(-height / 2, -metrics.height() / 2,
                                    height, metrics.height()),
                             Qt.AlignCenter, surface.y_label)
            painter.restore()

    def _bar(self, painter, palette, low, high) -> None:
        left, top, width, height, _r, _c = self._grid
        x = left + width + GAP
        steps = max(int(height), 2)
        for pixel in range(steps):
            fraction = 1.0 - pixel / (steps - 1)
            painter.fillRect(QRectF(x, top + pixel, BAR, 1.0),
                             ramp(fraction))
        painter.setPen(QPen(palette.color(palette.ColorRole.Mid), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(x, top, BAR, height))
        painter.setPen(palette.color(palette.ColorRole.Text))
        metrics = painter.fontMetrics()
        for fraction, value in ((0.0, high), (1.0, low)):
            painter.drawText(
                QRectF(x + BAR + 3, top + fraction * height
                       - metrics.height() / 2, RIGHT - BAR - GAP - 3,
                       metrics.height()),
                Qt.AlignLeft | Qt.AlignVCenter, _tick(value))

    def _readout(self, painter, palette) -> None:
        text = self.readout(self._hover)
        if not text:
            return                                  # pragma: no cover
        metrics = painter.fontMetrics()
        box = QRectF(LEFT + 4, TOP + 4,
                     metrics.horizontalAdvance(text) + 10,
                     metrics.height() + 4)
        painter.fillRect(box, palette.base())
        painter.setPen(QPen(palette.color(palette.ColorRole.Mid), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(box)
        painter.setPen(palette.color(palette.ColorRole.Text))
        painter.drawText(box, Qt.AlignCenter, text)


def save_surface(surface, path, size=SAVE_SIZE, scale: int = 2):
    """Draw a landscape into a PNG beside the run that produced it.

    The same argument :func:`xtalapp.curve.save_curve` makes: a run
    folder holding a hundred CIFs and a spreadsheet and no picture is
    one somebody has to reopen the application to look at.  ``scale``
    is a device pixel ratio rather than a resize, so the labels come
    out sharp rather than enlarged.
    """
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QPixmap

    width, height = int(size[0]), int(size[1])
    scale = max(1, int(scale))
    plot = HeatmapPlot()
    plot.set_surface(surface)
    plot.resize(width, height)
    pixmap = QPixmap(width * scale, height * scale)
    pixmap.setDevicePixelRatio(scale)
    pixmap.fill(plot.palette().base().color())
    plot.render(pixmap, QPoint(0, 0))
    pixmap.save(str(path), "PNG")
    plot.deleteLater()
    return path
