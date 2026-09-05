"""
xtalapp.curve
=============
A continuous trace with a comb of ticks under it, drawn by hand.

The third of the hand-drawn plots -- :mod:`xtalapp.plot` is the
optimisation trace, :mod:`xtalapp.histogram` is the pore size
distribution -- and it is hand-drawn for the same reason they are, but
the reason has a boundary now and this is where it runs into it.

**The panel must draw a pattern with nothing installed.**  PXRD's
overlay window is matplotlib and matplotlib is the ``pxrd`` extra, so
a results dock that rendered a curve through it would be a panel that
goes blank on a machine that has everything else.  A hundred lines of
``QPainter`` follow the user's theme, cost nothing to package, and are
what the dock uses; the matplotlib window
(:mod:`xtalapp.dialogs.pattern`) is the *other* thing -- pan, zoom,
picking, overlaying a measured file and writing a vector figure -- and
it is opened deliberately rather than being the only way to see the
answer.

**The combs are not on the trace's scale.**  Reflection positions
have no intensity worth drawing: what a reader wants from them is
*where*, against the peaks above, so they are rows of short vertical
marks in a strip below the axis rather than sticks scaled to
anything.  More than one row, each in its own colour, because the
reflections a space group allows and the ones it forbids are two
different statements and the whole use of the second is telling which
comb an unexpected peak sits over.

**Three things make a pattern cheap to draw, and it needed all
three.**  Scrolling the results panel repaints whatever it uncovers,
so a paint that costs 50 ms is a panel that scrolls at twenty frames
a second; measured on MOF-5 in P1, which is 3701 points and 3177
reflections, it did.

*The geometry is cached.*  Building ten thousand ``QPointF`` in a
Python list comprehension inside ``paintEvent`` is tens of
milliseconds, paid again on every repaint.  It depends on the curve
and the widget size and on nothing else.

*The trace is decimated to the pixel grid.*  Ten thousand points
across four hundred pixels is twenty-five points per pixel column,
twenty-four of which land on a pixel already drawn.  Two points a
column -- the lowest and the highest -- is the same picture to the
pixel, and it keeps a one-point spike at full height, which matters
here more than anywhere: a sharp reflection *is* one point.

*The pen is one pixel wide, and this was the surprise.*  A
``drawPolyline`` of 1600 points costs **11 ms at width 2 and 0.27 ms
at width 1** -- forty times -- because Qt's raster engine strokes any
pen wider than a pixel by building and filling a polygon outline,
where a hairline takes the fast line path.  Nothing about a
diffraction trace wants a fat line; the series are told apart by
colour.

*The trace is a ``QPolygonF`` and not a list*, so ``drawPolyline``
gets the C++ array it wants instead of converting a Python list of
``QPointF`` on every call.

*The comb is one call.*  ``drawLines`` over a prepared list, rather
than three thousand ``drawLine`` calls with the Python overhead of
each, and with antialiasing off -- a vertical hairline gains nothing
from it and looks blurrier for it.

**Every series is normalised to its own maximum.**  A calculated
pattern is in electrons squared and a measured one is in counts, and
drawing them on one absolute axis puts one of them in the bottom pixel
row.  The y axis is therefore labelled as a percentage and says so,
which is what every published overlay does.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

# The same round-number axis the histogram draws.  Imported rather
# than written again: the two plots sit in one column in one panel,
# and two answers to "where do the ticks go" would be visible.
from xtalapp.histogram import _tick, _ticks

#: One per series, in the order they are drawn.  The first is the
#: calculated pattern and the second is whatever was overlaid on it,
#: which is the pair this widget almost always shows.
SERIES_COLORS = (
    QColor(58, 122, 200),
    QColor(206, 110, 40),
    QColor(96, 158, 96),
    QColor(150, 96, 178),
)

#: One per comb.  The first is the allowed reflections and is the
#: neutral grey those have always been; the second is deliberately
#: not another grey, because "forbidden" is the thing a reader is
#: picking out of the row above it.
TICK_COLORS = (
    QColor(120, 120, 120),
    QColor(198, 82, 82),
    QColor(120, 150, 190),
)

LEFT = 46           # room for the tick labels
#: Wider than the histogram's, because the last tick of an angle axis
#: is a four-character number centred on the right-hand edge, and ten
#: pixels of it is the half that gets cut off.
RIGHT = 26
TOP = 8
#: One comb row, and how much of the strip the combs get.  Two rows
#: is the most anything asks for -- allowed and forbidden -- and a
#: third would be drawn over the axis numbers, so the strip is sized
#: for two and a comb beyond that shares the second row's space.
COMB_ROW = 8
COMB = 2 * COMB_ROW
BOTTOM = 32 + COMB

SAVE_SIZE = (760, 320)


class CurvePlot(QWidget):
    """One :class:`xtal.modules.report.Curve`, drawn."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.curve = None
        self._cache: dict = {}
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_curve(self, curve) -> None:
        self.curve = curve
        self._cache = {}
        self.setToolTip(curve.note if curve is not None and curve.note
                        else "")
        self.update()

    def clear(self) -> None:
        self.set_curve(None)

    # -- the cached geometry -------------------------------------------

    def _geometry(self, box):
        """The polylines and the comb segments, in widget pixels.

        Rebuilt only when the curve or the size changes -- see the
        module docstring.  The box is the key and the cache holds one
        entry, so a resize misses and replaces rather than needing a
        ``resizeEvent`` to invalidate it: hooking the resize was tried
        and is worse than useless here, because Qt sends one on the
        way into a ``grab()`` and the cache is cleared between the two
        halves of every synchronous paint.
        """
        key = (box.left(), box.top(), box.width(), box.height())
        found = self._cache.get(key)
        if found is not None:
            return found

        curve = self.curve
        x = np.asarray(curve.x, dtype=float)
        first = float(x[0])
        span = max(float(x[-1]) - first, 1e-9)
        across = box.left() + box.width() * (x - first) / span

        polylines = []
        for label, values in curve.all_series():
            values = np.asarray(values, dtype=float)
            if len(values) != len(x) or not len(values):
                continue                            # pragma: no cover
            top = float(np.max(values))
            if not np.isfinite(top) or top <= 0:
                continue
            up = box.bottom() - box.height() * values / top
            polylines.append((label, _points(across, up)))

        combs = []
        for index, (label, positions) in enumerate(curve.tick_sets):
            positions = np.asarray(positions, dtype=float)
            inside = positions[(positions >= first)
                               & (positions <= first + span)]
            at = box.left() + box.width() * (inside - first) / span
            high = box.bottom() + 3 + index * COMB_ROW
            combs.append((label, [
                QLineF(float(v), high, float(v), high + COMB_ROW - 3)
                for v in at]))

        found = (polylines, combs, first, span)
        self._cache = {key: found}
        return found

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.base())

        curve = self.curve
        if curve is None or curve.n_points < 2:
            painter.setPen(palette.color(palette.ColorRole.Mid))
            painter.drawText(self.rect(), Qt.AlignCenter,
                             "Nothing to plot")
            return

        box = QRectF(LEFT, TOP, self.width() - LEFT - RIGHT,
                     self.height() - TOP - BOTTOM)
        if box.width() < 20 or box.height() < 20:   # pragma: no cover
            return

        polylines, combs, first, span = self._geometry(box)
        x = np.asarray(curve.x, dtype=float)

        self._frame(painter, box, palette)
        self._series(painter, polylines)
        self._combs(painter, combs)
        self._axis_labels(painter, box, curve, first,
                          float(x[-1]), palette)
        self._legend(painter, box, curve)

    def _frame(self, painter, box, palette) -> None:
        pen = QPen(palette.color(palette.ColorRole.Mid))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawRect(box)

    def _series(self, painter, polylines) -> None:
        """Each trace, scaled to its own maximum -- see the module
        docstring for why they cannot share one, and for why the pen
        is a hairline."""
        for index, (_label, polygon) in enumerate(polylines):
            pen = QPen(SERIES_COLORS[index % len(SERIES_COLORS)])
            # One pixel, always -- see the module docstring.  A wider
            # pen is forty times slower to stroke and buys nothing.
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawPolyline(polygon)

    def _combs(self, painter, combs) -> None:
        """The tick rows, stacked under the axis in their own colours.

        One ``drawLines`` a row and antialiasing off -- see the module
        docstring; three thousand ``drawLine`` calls was most of what
        made this widget expensive to repaint.
        """
        painter.setRenderHint(QPainter.Antialiasing, False)
        for index, (_label, segments) in enumerate(combs):
            if not segments:
                continue
            pen = QPen(TICK_COLORS[index % len(TICK_COLORS)])
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawLines(segments)
        painter.setRenderHint(QPainter.Antialiasing, True)

    def _axis_labels(self, painter, box, curve, first, last,
                     palette) -> None:
        painter.setPen(palette.color(palette.ColorRole.Mid))
        font = painter.font()
        font.setPointSizeF(max(7.0, font.pointSizeF() - 2))
        painter.setFont(font)
        # Every series is scaled to its own maximum, so the only two
        # numbers the vertical axis can honestly carry are the ends.
        for value, align in ((100.0, Qt.AlignTop), (0.0, Qt.AlignBottom)):
            painter.drawText(QRectF(0, box.top(), LEFT - 6, box.height()),
                             align | Qt.AlignRight, _tick(value))
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
            painter.drawText(
                QRectF(at - 24, box.bottom() + COMB, 48, 14),
                Qt.AlignCenter, _tick(value))
        if curve.x_label:
            painter.drawText(
                QRectF(box.left(), box.bottom() + COMB + 12,
                       box.width(), 14),
                Qt.AlignCenter, curve.x_label)

    def _legend(self, painter, box, curve) -> None:
        """Which trace is which, on a patch of the background.

        On a patch because a pattern's tallest peak can be anywhere,
        including exactly under the name of the series it belongs to.
        """
        entries = [(label, SERIES_COLORS[i % len(SERIES_COLORS)])
                   for i, (label, _y) in
                   enumerate(curve.all_series())]
        entries += [(label, TICK_COLORS[i % len(TICK_COLORS)])
                    for i, (label, _p) in enumerate(curve.tick_sets)]
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


def save_curve(curve, path, size=SAVE_SIZE, scale: int = 2):
    """Draw a curve into a PNG beside the run that produced it.

    The same argument :func:`xtalapp.histogram.save_histogram` makes,
    and the same mechanism: ``scale`` is a device pixel ratio rather
    than a resize, so the labels come out sharp instead of enlarged.

    A raster picture on purpose, even though this module's whole
    subject is a figure somebody will put in a paper: the run folder's
    copy is the record of what the run produced, and the *vector*
    export is a thing the user asks for through
    :mod:`xtalapp.dialogs.pattern` after deciding what should be on
    it.
    """
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QPixmap

    width, height = int(size[0]), int(size[1])
    scale = max(1, int(scale))
    plot = CurvePlot()
    plot.set_curve(curve)
    plot.resize(width, height)

    picture = QPixmap(width * scale, height * scale)
    picture.setDevicePixelRatio(scale)
    picture.fill(plot.palette().base().color())
    painter = QPainter(picture)
    plot.render(painter, QPoint())
    painter.end()

    path = Path(path)
    if not picture.save(str(path), "PNG"):          # pragma: no cover
        raise OSError(f"could not write {path}")
    return path


def _points(across: np.ndarray, up: np.ndarray) -> QPolygonF:
    """The trace as a ``QPolygonF``, thinned to the pixel grid.

    Two points per pixel column -- the lowest and the highest -- which
    is the same picture to the pixel and keeps a one-point spike at
    full height.  That last part is why the obvious "take every nth
    point" is wrong here: a sharp reflection is one point, and a
    stride that misses it draws a pattern with the peak missing.

    Left alone below two points a column, where thinning would cost
    more than it saves and could only lose something.

    A ``QPolygonF`` rather than a list, because a list is converted
    to one on every ``drawPolyline`` -- see the module docstring.
    """
    if len(across) < 2 * max(int(across[-1] - across[0]), 1):
        return QPolygonF([QPointF(float(a), float(b))
                          for a, b in zip(across, up, strict=True)])
    column = np.floor(across).astype(np.int64)
    starts = np.concatenate(([0], np.flatnonzero(np.diff(column)) + 1))
    low = np.minimum.reduceat(up, starts)
    high = np.maximum.reduceat(up, starts)
    at = across[starts]
    out = []
    for a, lo, hi in zip(at, low, high, strict=True):
        out.append(QPointF(float(a), float(lo)))
        if hi != lo:
            out.append(QPointF(float(a), float(hi)))
    return QPolygonF(out)
