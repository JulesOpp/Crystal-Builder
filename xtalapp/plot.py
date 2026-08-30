"""
xtalapp.plot
============
A small trace plot, drawn by hand.

An optimisation needs one picture: is the energy still falling, and is
the force still coming down.  That is two polylines and a pair of axes,
and it is drawn here rather than pulled in from a plotting library
because the library would be a second large dependency to pin, package
and ship for one widget -- and because a hundred lines of ``QPainter``
follow the user's theme for free, which a plotting library has to be
persuaded to do.

Both traces share the step axis.  Energy is linear, because its
absolute value is what people read; force is logarithmic, because it
falls through several orders of magnitude and a linear axis shows the
first two steps and then a flat line along the bottom.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

ENERGY_COLOR = QColor(58, 122, 200)
FORCE_COLOR = QColor(206, 110, 40)
MARGIN = 52        # room on the left for the tick labels
PADDING = 5        # top and bottom
GAP = 14           # between the two boxes
ENERGY_SHARE = 0.6
MARKER_COLOR = QColor(120, 120, 120)


def _tick(value: float) -> str:
    """A short axis label.

    ``%g`` turns a few thousand kcal/mol into "-1.42e+03", which is
    nine characters for a number nobody needs to four figures, and it
    does not fit in the margin.  Energies live in a narrow enough range
    that plain digits almost always do.
    """
    magnitude = abs(value)
    if magnitude < 1e-9:
        return "0"
    if magnitude >= 1e5 or magnitude < 1e-2:
        return f"{value:.0e}"
    if magnitude >= 100:
        return f"{value:.0f}"
    return f"{value:.2f}"


class TracePlot(QWidget):
    """Energy and maximum force against optimisation step.

    Also the way into a trajectory.  The plot and the frames are the
    same run seen two ways, so clicking a point emits the step it
    belongs to (:attr:`pointClicked`) and the frame being played is
    drawn on it as a marker.  "Why did it go there" is a question
    asked at a kink in the energy, and the kink is the fastest way to
    reach the geometry that caused it.
    """

    pointClicked = Signal(int)          # the step nearest the click

    def __init__(self, parent=None):
        super().__init__(parent)
        self.history: list[tuple[int, float, float]] = []
        self.marker: int | None = None
        # The step axis as it was last painted, so a click can be
        # turned back into a step without recomputing the layout.
        self._axis_map: tuple | None = None
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_history(self, history) -> None:
        self.history = list(history)
        self.update()

    def append(self, step: int, energy: float, force: float) -> None:
        self.history.append((step, energy, force))
        self.update()

    def clear(self) -> None:
        self.history = []
        self.marker = None
        self.update()

    def set_marker(self, step: int | None) -> None:
        """Draw a line at one step -- the frame being played."""
        if step != self.marker:
            self.marker = step
            self.update()

    # -- clicking ------------------------------------------------------

    def step_at(self, x: float) -> int | None:
        """The step of the plotted point nearest an x position."""
        if not self.history or self._axis_map is None:
            return None
        left, width, first, span = self._axis_map
        if width <= 0:
            return None                             # pragma: no cover
        wanted = first + (x - left) / width * span
        return min((h[0] for h in self.history),
                   key=lambda s: abs(s - wanted))

    def mousePressEvent(self, event) -> None:
        step = self.step_at(event.position().x())
        if step is not None:
            self.pointClicked.emit(int(step))
        super().mousePressEvent(event)

    # -- painting ------------------------------------------------------

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.base())

        if len(self.history) < 2:
            painter.setPen(palette.color(palette.ColorRole.Mid))
            painter.drawText(self.rect(), Qt.AlignCenter,
                             "No run yet")
            return

        width = self.width() - MARGIN - 8
        # MARGIN is the room the tick labels need on the left; the
        # vertical padding is its own, much smaller, number.
        height = self.height() - 2 * PADDING
        if width <= 10 or height <= 10:             # pragma: no cover
            return
        energy_height = (height - GAP) * ENERGY_SHARE
        force_height = height - GAP - energy_height
        energy_box = QRectF(MARGIN, PADDING, width, energy_height)
        force_box = QRectF(MARGIN, PADDING + energy_height + GAP,
                           width, force_height)

        steps = [h[0] for h in self.history]
        energies = [h[1] for h in self.history]
        forces = [max(h[2], 1e-12) for h in self.history]

        self._axis(painter, energy_box, palette)
        self._axis(painter, force_box, palette)
        self._trace(painter, energy_box, steps, energies,
                    ENERGY_COLOR, log=False)
        self._trace(painter, force_box, steps,
                    [math.log10(f) for f in forces], FORCE_COLOR,
                    log=True)

        self._marker(painter, energy_box, force_box, steps)
        self._label(painter, energy_box, "energy", ENERGY_COLOR,
                    f"{energies[-1]:.4f} kcal/mol")
        self._label(painter, force_box, "|F|max", FORCE_COLOR,
                    f"{forces[-1]:.4g} kcal/mol/A")

    def _axis(self, painter, box, palette) -> None:
        pen = QPen(palette.color(palette.ColorRole.Mid))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawRect(box)

    def _marker(self, painter, energy_box, force_box, steps) -> None:
        """A vertical line at the frame being played."""
        if self.marker is None or self._axis_map is None:
            return
        left, width, first, span = self._axis_map
        if not (steps[0] <= self.marker <= steps[-1]):
            return
        x = left + width * (self.marker - first) / span
        pen = QPen(MARKER_COLOR)
        pen.setWidth(1)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        for box in (energy_box, force_box):
            painter.drawLine(QPointF(x, box.top()),
                             QPointF(x, box.bottom()))

    def _trace(self, painter, box, steps, values, color,
               log: bool) -> None:
        low, high = min(values), max(values)
        if high - low < 1e-12:
            low, high = low - 0.5, high + 0.5
        pad = 0.06 * (high - low)
        low, high = low - pad, high + pad

        first, last = steps[0], steps[-1]
        span = max(last - first, 1)
        self._axis_map = (box.left(), box.width(), first, span)
        points = [
            QPointF(
                box.left() + box.width() * (s - first) / span,
                box.bottom() - box.height() * (v - low) / (high - low),
            )
            for s, v in zip(steps, values, strict=True)
        ]
        pen = QPen(color)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawPolyline(points)

        painter.setPen(self.palette().color(
            self.palette().ColorRole.Mid))
        font = painter.font()
        font.setPointSizeF(max(7.0, font.pointSizeF() - 2))
        painter.setFont(font)
        for value, align in ((high, Qt.AlignTop),
                             (low, Qt.AlignBottom)):
            text = (f"1e{value:.0f}" if log else _tick(value))
            painter.drawText(
                QRectF(0, box.top(), MARGIN - 6, box.height()),
                align | Qt.AlignRight, text)

    def _label(self, painter, box, name, color, value) -> None:
        """The series name and its latest value, over the trace.

        Both sit on a patch of the background: the trace starts in the
        top-left corner, which is exactly where the name goes, and
        without the patch the two draw over each other at the one
        moment the number matters most."""
        area = box.adjusted(6, 3, -6, 0)
        metrics = painter.fontMetrics()
        for text, align, pen in ((name, Qt.AlignLeft, color),
                                 (value, Qt.AlignRight,
                                  self.palette().color(
                                      self.palette().ColorRole.Text))):
            width = metrics.horizontalAdvance(text) + 6
            patch = QRectF(area.left() - 3 if align == Qt.AlignLeft
                           else area.right() - width + 3,
                           area.top(), width, metrics.height())
            painter.fillRect(patch, self.palette().base())
            painter.setPen(pen)
            painter.drawText(area, align | Qt.AlignTop, text)
