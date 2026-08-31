"""
xtalapp.histogram
=================
A bar chart with a curve over it, drawn by hand.

The companion to :mod:`xtalapp.plot`, and here for the same reason:
the one plotting library that would draw this is a second large
dependency to pin, package and ship for one widget, and a hundred
lines of ``QPainter`` follow the user's theme for free.

What it has to show is a pore size distribution, which is two series
and not one.  The **bars** are how many Monte Carlo points landed at
each diameter -- the sampling, which is what says whether the picture
can be believed at all.  The **curve** is the derivative of the
cumulative distribution, which is the distribution as a paper plots
it.  They peak in the same place and have different shapes, and either
one alone invites the wrong reading of the other, so both are drawn
and each is labelled.

Two things the axis does that matter.

**The range is the caller's**, not the data's.  Zeo++ writes a
thousand bins of 0.1 A and a framework occupies forty of them; the
window is chosen in :meth:`PoreSizeDistribution.occupied` so that the
number quoted beside the picture and the picture agree about what is
being shown.

**A marker is a vertical rule with a name.**  The free sphere diameter
drawn over a pore size distribution says, at a glance, which of those
pores anything can actually reach -- which is the question the two
numbers are usually put side by side to answer.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

BAR_COLOR = QColor(58, 122, 200)
CURVE_COLOR = QColor(206, 110, 40)
MARKER_COLOR = QColor(120, 120, 120)

LEFT = 46           # room for the tick labels
RIGHT = 10
TOP = 8
BOTTOM = 32         # room for the axis label and the tick numbers
#: Below this many bins the bars are drawn with a gap between them;
#: above it they are drawn touching, because a one-pixel gap between
#: two hundred bars is a picture of the gaps.
GAPPED = 60


def _tick(value: float) -> str:
    magnitude = abs(value)
    if magnitude < 1e-9:
        return "0"
    if magnitude >= 1e5 or magnitude < 1e-2:
        return f"{value:.0e}"
    if magnitude >= 100:
        return f"{value:.0f}"
    return f"{value:.2f}"


def _ticks(first: float, last: float, wanted: int = 6) -> list[float]:
    """Round numbers across the range, ends included.

    Chosen from the range rather than from the bins: a tick at 12.35
    because that is where a bin edge fell is a number nobody asked
    for, and the axis is continuous whatever the binning was.
    """
    span = last - first
    if span <= 0:                                   # pragma: no cover
        return [first]
    import math
    rough = span / max(wanted, 1)
    magnitude = 10 ** math.floor(math.log10(rough))
    for multiple in (1, 2, 2.5, 5, 10):
        step = multiple * magnitude
        if span / step <= wanted:
            break
    start = math.ceil(first / step) * step
    out, value = [], start
    while value <= last + 1e-9:
        out.append(round(value, 10))
        value += step
    return out or [first, last]


class HistogramPlot(QWidget):
    """One :class:`xtal.modules.report.Histogram`, drawn."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.histogram = None
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_histogram(self, histogram) -> None:
        self.histogram = histogram
        if histogram is not None and histogram.note:
            self.setToolTip(histogram.note)
        else:
            self.setToolTip("")
        self.update()

    def clear(self) -> None:
        self.set_histogram(None)

    # -- painting ------------------------------------------------------

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.base())

        histogram = self.histogram
        if histogram is None or histogram.n_bins < 2:
            painter.setPen(palette.color(palette.ColorRole.Mid))
            painter.drawText(self.rect(), Qt.AlignCenter,
                             "Nothing to plot")
            return

        box = QRectF(LEFT, TOP, self.width() - LEFT - RIGHT,
                     self.height() - TOP - BOTTOM)
        if box.width() < 20 or box.height() < 20:   # pragma: no cover
            return

        x = np.asarray(histogram.x, dtype=float)
        y = np.asarray(histogram.y, dtype=float)
        first, last = float(x[0]), float(x[-1])
        span = max(last - first, 1e-9)
        top = float(np.max(y)) or 1.0

        self._frame(painter, box, palette)
        self._bars(painter, box, x, y, first, span, top)
        self._curve(painter, box, histogram, x, first, span)
        self._markers(painter, box, histogram, first, span)
        self._axis_labels(painter, box, histogram, first, last, top,
                          palette)
        self._legend(painter, box, histogram)

    def _frame(self, painter, box, palette) -> None:
        pen = QPen(palette.color(palette.ColorRole.Mid))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawRect(box)

    def _bars(self, painter, box, x, y, first, span, top) -> None:
        width = box.width() / max(len(x), 1)
        gap = 1.0 if len(x) <= GAPPED else 0.0
        painter.setPen(Qt.NoPen)
        painter.setBrush(BAR_COLOR)
        for value, height in zip(x, y, strict=True):
            if height <= 0:
                continue
            left = box.left() + box.width() * (value - first) / span
            tall = box.height() * height / top
            painter.drawRect(QRectF(left - width / 2 + gap / 2,
                                    box.bottom() - tall,
                                    max(width - gap, 1.0), tall))
        painter.setBrush(Qt.NoBrush)

    def _curve(self, painter, box, histogram, x, first, span) -> None:
        """The second series, on a scale of its own.

        Its own scale because it is a different quantity in different
        units: forcing it onto the bars' axis would draw either a flat
        line along the bottom or a curve off the top, and neither is
        the shape anybody is looking for.
        """
        curve = histogram.curve
        if curve is None or not len(curve):
            return
        curve = np.asarray(curve, dtype=float)
        peak = float(np.max(np.abs(curve)))
        if peak <= 0:
            return
        points = [
            QPointF(box.left() + box.width() * (v - first) / span,
                    box.bottom() - box.height() * abs(c) / peak)
            for v, c in zip(x, curve, strict=True)]
        pen = QPen(CURVE_COLOR)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawPolyline(points)

    def _markers(self, painter, box, histogram, first, span) -> None:
        pen = QPen(MARKER_COLOR)
        pen.setWidth(1)
        pen.setStyle(Qt.DashLine)
        for position, name in histogram.markers or ():
            if not (first <= position <= first + span):
                continue
            at = box.left() + box.width() * (position - first) / span
            painter.setPen(pen)
            painter.drawLine(QPointF(at, box.top()),
                             QPointF(at, box.bottom()))
            painter.setPen(MARKER_COLOR)
            painter.drawText(QRectF(at + 3, box.top(), 120, 16),
                             Qt.AlignLeft | Qt.AlignTop, name)

    def _axis_labels(self, painter, box, histogram, first, last, top,
                     palette) -> None:
        painter.setPen(palette.color(palette.ColorRole.Mid))
        font = painter.font()
        font.setPointSizeF(max(7.0, font.pointSizeF() - 2))
        painter.setFont(font)
        # The vertical axis: the top of the bars and zero, which is
        # every tick a count axis needs.
        for value, align in ((top, Qt.AlignTop), (0.0, Qt.AlignBottom)):
            painter.drawText(
                QRectF(0, box.top(), LEFT - 6, box.height()),
                align | Qt.AlignRight, _tick(value))
        # The horizontal axis: the ends, and a few in between.  Two
        # numbers at the ends of a several-Angstrom axis leave the
        # reader counting pixels to place the peak, which is the one
        # thing they came to the picture for.
        span = max(last - first, 1e-9)
        grid = QPen(palette.color(palette.ColorRole.Mid))
        grid.setWidth(1)
        grid.setStyle(Qt.DotLine)
        for value in _ticks(first, last):
            at = box.left() + box.width() * (value - first) / span
            painter.setPen(grid)
            painter.drawLine(QPointF(at, box.top()),
                             QPointF(at, box.bottom()))
            painter.setPen(palette.color(palette.ColorRole.Mid))
            painter.drawText(QRectF(at - 24, box.bottom() + 2, 48, 14),
                             Qt.AlignCenter, _tick(value))
        below = QRectF(box.left(), box.bottom() + 14, box.width(), 14)
        if histogram.x_label:
            painter.drawText(below, Qt.AlignCenter, histogram.x_label)

    def _legend(self, painter, box, histogram) -> None:
        """Which series is which, over the plot.

        On a patch of the background, because the bars start in the
        top-left corner exactly where the name goes.
        """
        entries = [(histogram.y_label or "count", BAR_COLOR)]
        if histogram.curve is not None and len(histogram.curve):
            entries.append((histogram.curve_label or "curve",
                            CURVE_COLOR))
        metrics = painter.fontMetrics()
        y = box.top() + 3
        for text, color in entries:
            width = metrics.horizontalAdvance(text) + 8
            patch = QRectF(box.right() - width - 4, y, width,
                           metrics.height())
            painter.fillRect(patch, self.palette().base())
            painter.setPen(color)
            painter.drawText(patch, Qt.AlignCenter, text)
            y += metrics.height()
