"""
xtalapp.bands
=============
A band structure, drawn by hand, and written out as a figure.

The fourth hand-drawn plot, for the reason :mod:`xtalapp.curve` gives:
the results panel must show the answer with nothing installed, so it
is ``QPainter`` and follows the theme, and the publication figure is
matplotlib and is asked for.

What makes it not a curve is the y axis.  Energy has a sign, zero is
the Fermi level and gets a dashed line, and which few eV of a hundred
bands are worth looking at is the reader's to choose -- so the window
is a pair of spinboxes under the plot rather than the data's range,
which on a framework is forty eV of core states nobody wanted.  The
named points are vertical rules across the whole height, labelled
under the axis, because a band structure is read column by column at
them.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from xtalapp.histogram import _tick, _ticks

SPIN_COLORS = (QColor(58, 122, 200), QColor(206, 110, 40))
LEFT, RIGHT, TOP, BOTTOM = 46, 12, 8, 28
SAVE_SIZE = (720, 520)


class BandsPlot(QWidget):
    """``energies[spin, k, band]`` against distance along the path."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bands = None
        self.energy_window = (-6.0, 6.0)
        self.setMinimumHeight(260)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def set_bands(self, bands) -> None:
        self.bands = bands
        self.energy_window = tuple(bands.window)
        self.update()

    def set_window(self, low: float, high: float) -> None:
        if high <= low:
            return
        self.energy_window = (float(low), float(high))
        self.update()

    def sizeHint(self):                             # noqa: N802
        from PySide6.QtCore import QSize
        return QSize(420, 320)

    def paintEvent(self, _event) -> None:           # noqa: N802
        painter = QPainter(self)
        try:
            self.paint(painter, QRectF(self.rect()))
        finally:
            painter.end()

    def paint(self, painter, rect) -> None:
        palette = self.palette()
        painter.fillRect(rect, palette.base())
        bands = self.bands
        if bands is None or not len(bands.x):
            return
        plot = QRectF(rect.left() + LEFT, rect.top() + TOP,
                      rect.width() - LEFT - RIGHT,
                      rect.height() - TOP - BOTTOM)
        x0, x1 = float(bands.x[0]), float(bands.x[-1])
        low, high = self.energy_window

        def px(x):
            return plot.left() + (x - x0) / ((x1 - x0) or 1.0) \
                * plot.width()

        def py(e):
            return plot.bottom() - (e - low) / (high - low) \
                * plot.height()

        text = palette.text().color()
        grid = QColor(text)
        grid.setAlpha(60)
        painter.setPen(QPen(grid, 1))
        for x, _label in bands.ticks:
            painter.drawLine(QLineF(px(x), plot.top(), px(x),
                                    plot.bottom()))
        painter.setPen(QPen(text, 1))
        painter.drawRect(plot)
        for value in _ticks(low, high, 6):
            y = py(value)
            painter.drawLine(QLineF(plot.left() - 4, y, plot.left(), y))
            painter.drawText(QRectF(rect.left(), y - 8, LEFT - 6, 16),
                             Qt.AlignRight | Qt.AlignVCenter,
                             _tick(value))
        for x, label in bands.ticks:
            painter.drawText(QRectF(px(x) - 30, plot.bottom() + 4, 60, 18),
                             Qt.AlignHCenter | Qt.AlignTop, label)

        fermi = QPen(text, 1, Qt.DashLine)
        painter.setPen(fermi)
        if low < 0.0 < high:
            painter.drawLine(QLineF(plot.left(), py(0.0), plot.right(),
                                    py(0.0)))

        painter.save()
        painter.setClipRect(plot)
        painter.setRenderHint(QPainter.Antialiasing, True)
        xs = [px(float(x)) for x in bands.x]
        for spin in range(bands.energies.shape[0]):
            painter.setPen(QPen(SPIN_COLORS[spin % len(SPIN_COLORS)], 1))
            for band in range(bands.energies.shape[2]):
                trace = bands.energies[spin, :, band]
                if trace.max() < low or trace.min() > high:
                    continue
                painter.drawPolyline(QPolygonF(
                    [QPointF(x, py(float(e)))
                     for x, e in zip(xs, trace, strict=True)]))
        painter.restore()
        # Under the axis numbers rather than beside the top one, which
        # is where a unit label collides with "6.00".
        painter.setPen(QPen(text, 1))
        painter.drawText(QRectF(rect.left(), plot.bottom() + 10,
                                LEFT - 6, 18),
                         Qt.AlignRight | Qt.AlignTop, "eV")


def save_bands(bands, path, size=SAVE_SIZE, scale: int = 2) -> Path:
    """The panel's picture as a PNG, for the run folder."""
    from PySide6.QtGui import QPixmap
    width, height = int(size[0]), int(size[1])
    plot = BandsPlot()
    plot.set_bands(bands)
    plot.resize(width, height)
    picture = QPixmap(width * scale, height * scale)
    picture.setDevicePixelRatio(scale)
    painter = QPainter(picture)
    plot.paint(painter, QRectF(0, 0, width, height))
    painter.end()
    path = Path(path)
    picture.save(str(path))
    return path


def export_figure(bands, path, window=None) -> Path:
    """A publication figure through matplotlib -- PNG, SVG or PDF by
    the suffix -- or the numbers, for ``.dat`` and ``.csv``."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".dat":
        path.write_text(bands.as_dat())
        return path
    if suffix == ".csv":
        path.write_text(bands.as_csv())
        return path
    # A bare Figure, not pyplot: pyplot would choose a backend for the
    # whole process, and the pattern window has already chosen Qt's.
    from matplotlib.figure import Figure

    low, high = window or bands.window
    figure = Figure(figsize=(4.5, 4.0), dpi=150)
    axes = figure.add_subplot()
    colors = ("tab:blue", "tab:orange")
    for spin in range(bands.energies.shape[0]):
        axes.plot(bands.x, bands.energies[spin], color=colors[spin % 2],
                  linewidth=1.0)
    for x, _label in bands.ticks:
        axes.axvline(x, color="0.7", linewidth=0.6)
    axes.axhline(0.0, color="0.3", linewidth=0.8, linestyle="--")
    axes.set_xticks([x for x, _l in bands.ticks],
                    [label for _x, label in bands.ticks])
    axes.set_xlim(float(bands.x[0]), float(bands.x[-1]))
    axes.set_ylim(low, high)
    axes.set_ylabel("E - E$_F$ (eV)")
    figure.tight_layout()
    figure.savefig(path)
    return path


def figure_formats() -> str:
    """The save dialog's filter.  The numbers need nothing installed;
    the figures are matplotlib, and are offered only where it is."""
    from xtalapp.dialogs import pattern
    numbers = "Band table (*.dat);;Comma-separated values (*.csv)"
    if not pattern.installed():
        return numbers
    return ("PNG image (*.png);;SVG figure (*.svg);;PDF figure (*.pdf);;"
            + numbers)
