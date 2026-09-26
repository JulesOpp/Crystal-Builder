"""
xtalapp.refine.plot
===================
The refinement plot: observed, calculated and their difference, with
the tick combs under them -- the picture every refinement program
draws, and the one a person watches a Rietveld run in.

On counts, not percent.  :class:`~xtalapp.dialogs.pattern.PatternDialog`
scales every trace to its own maximum because a calculated pattern
and a measured one share no units; a fit is in the measurement's
units by construction, and scaling the two traces apart would hide
exactly the misfit the difference curve is there to show.

**The traces are updated, not redrawn**, so a live refinement can
send twenty frames a second without the axes, the zoom or the
toolbar noticing: :meth:`show_calculated` sets new y data on lines
that already exist.  Nothing but a new pattern or a new fit resets
the view: ticking a peak in or out redraws a comb and the lines, and
a person zoomed into one peak to decide about it stays there.

**The combs have a strip of their own** between the pattern and the
difference, rather than hanging below zero on the pattern's axis.
Below zero was fine on counts; on a logarithmic axis there is no
below zero, and on any axis the comb's depth was a second intensity
scale that zooming stretched.
"""

from __future__ import annotations

from contextlib import contextmanager

import numpy as np
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from xtal import install
from xtalapp.dialogs.pattern import _figure_canvas, installed
from xtalapp.widgets.intensity_scale import (
    FOLLOWS,
    apply_scale,
    scale_box,
)
from xtalapp.widgets.tone import WARNING, set_tone

__all__ = ["RefinementPlot"]

#: Observed, calculated, background, difference, ticks, single lines.
COLORS = ("0.15", "#d0473a", "0.6", "#3a6fb0", "#2f8f4e", "#8a5cc2")


class RefinementPlot(QWidget):
    """A pattern and a fit to it, or a sentence naming the extra."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.available = installed()
        self.figure = None
        self._lines: dict = {}
        self._components_shown = True
        if not self.available:
            label = QLabel(
                f"The plot needs matplotlib: {install.command('pxrd')}"
                f".  The fit still runs, and its table and fit.xy are "
                f"written without it.")
            label.setWordWrap(True)
            set_tone(label, WARNING)
            layout.addWidget(label)
            layout.addStretch(1)
            return
        canvas_class, toolbar_class, figure_class = _figure_canvas()
        # Constrained layout re-fits the axes to whatever size the
        # splitter gives them; a fixed figure left half its height
        # blank and cut the difference axis's label off.
        self.figure = figure_class(figsize=(7.0, 4.5),
                                   layout="constrained")
        grid = self.figure.add_gridspec(3, 1,
                                        height_ratios=(4, 0.4, 1))
        self.axes = self.figure.add_subplot(grid[0])
        self.strip = self.figure.add_subplot(grid[1], sharex=self.axes)
        self.difference = self.figure.add_subplot(grid[2],
                                                  sharex=self.axes)
        self.canvas = canvas_class(self.figure)
        self.canvas.setMinimumSize(360, 240)
        self.toolbar = toolbar_class(self.canvas, self)
        self.scale_box = scale_box()
        self.scale_box.currentIndexChanged.connect(
            lambda _i: self.set_scale(self.scale_box.currentData()))
        top = QHBoxLayout()
        top.addWidget(self.toolbar, 1)
        top.addWidget(QLabel("Intensity"))
        top.addWidget(self.scale_box)
        layout.addLayout(top)
        layout.addWidget(self.canvas, 1)
        self._x = np.zeros(0)
        self._observed = np.zeros(0)
        self.clear()

    # -- what is drawn -------------------------------------------------

    def clear(self) -> None:
        if self.figure is None:
            return
        self.axes.clear()
        self.strip.clear()
        self.difference.clear()
        self._lines = {}
        self.axes.set_ylabel("counts")
        self.difference.set_xlabel(r"2$\theta$ (degrees)")
        self.difference.set_ylabel("obs - calc")
        self.axes.tick_params(labelbottom=False)
        self.strip.tick_params(labelbottom=False, left=False,
                               labelleft=False)
        # row 0 (the peaks) on top, row 1 (a cell's lines) under it
        self.strip.set_ylim(2.0, 0.0)
        self.canvas.draw_idle()

    @property
    def scale(self) -> str:
        return self.scale_box.currentData() if self.figure is not None \
            else "linear"

    def set_scale(self, key: str) -> None:
        """Linear, square-root or logarithmic counts on the pattern's
        axis; the difference stays linear, where its sign is."""
        if self.figure is None:
            return
        index = self.scale_box.findData(key)
        if index != self.scale_box.currentIndex():
            self.scale_box.setCurrentIndex(index)   # comes back here
            return
        apply_scale(self.axes, key)
        self.canvas.draw_idle()

    @contextmanager
    def _view_kept(self):
        """Whatever is redrawn inside, the zoom stays where it was."""
        xlim, ylim = self.axes.get_xlim(), self.axes.get_ylim()
        try:
            yield
        finally:
            self.axes.set_xlim(*xlim)
            self.axes.set_ylim(*ylim)

    def show_observed(self, x, y, label: str = "observed") -> None:
        """A measurement on its own: the first thing after loading."""
        if self.figure is None:
            return
        self.clear()
        self._x = np.asarray(x, dtype=float)
        self._observed = np.asarray(y, dtype=float)
        (self._lines["observed"],) = self.axes.plot(
            self._x, self._observed, lw=0.9, color=COLORS[0],
            label=label)
        self.axes.legend(loc="upper right", frameon=False, fontsize=9)
        self.axes.margins(x=0.01)
        apply_scale(self.axes, self.scale)
        self.canvas.draw_idle()

    def show_fit(self, x, observed, calculated, background=None,
                 ticks=()) -> None:
        """A fit, from scratch: the observed trace is its grid's."""
        if self.figure is None:
            return
        self.show_observed(x, observed)
        # The intensity axis is the measurement's, at every scale: a
        # Rietveld run's first frame comes before the scale is refined,
        # 2.5 million counts against 5000 on rutile, and an axis sized
        # to it left the data a flat line under every later frame.
        if background is not None:
            (self._lines["background"],) = self.axes.plot(
                self._x, np.asarray(background, dtype=float), lw=0.8,
                color=COLORS[2], label="background", scaley=False, gid=FOLLOWS)
        (self._lines["calculated"],) = self.axes.plot(
            self._x, np.asarray(calculated, dtype=float), lw=1.0,
            color=COLORS[1], label="calculated", scaley=False, gid=FOLLOWS)
        (self._lines["difference"],) = self.difference.plot(
            self._x, self._observed - np.asarray(calculated, dtype=float),
            lw=0.8, color=COLORS[3])
        self.difference.axhline(0.0, lw=0.5, color="0.5")
        self.set_ticks(ticks)
        self.axes.legend(loc="upper right", frameon=False, fontsize=9)
        apply_scale(self.axes, self.scale)
        self.canvas.draw_idle()

    def set_ticks(self, positions) -> None:
        """Where the peaks are: a comb under zero."""
        self._comb("ticks", positions, 0, COLORS[4])

    def set_reflections(self, positions) -> None:
        """Where a candidate cell puts its lines: a second comb under
        the peaks', so a peak with no line beneath it is seen at once
        -- how a person judges a cell by eye."""
        self._comb("reflections", positions, 1, COLORS[1])

    def _comb(self, name: str, positions, row: int, color) -> None:
        if self.figure is None:
            return
        old = self._lines.pop(name, None)
        if old is not None:
            old.remove()
        positions = np.asarray(positions, dtype=float)
        if positions.size:
            with self._view_kept():
                self._lines[name] = self.strip.vlines(
                    positions, row + 0.15, row + 0.85, colors=color,
                    linewidths=0.8)
        self.canvas.draw_idle()

    def set_components(self, background, curves) -> None:
        """Each fitted line drawn on its own over the background, so a
        person can see which line is carrying which part of a peak.

        ``curves`` is one array per line on the observed grid, ``None``
        for a line not drawn.  Drawn as one collection, and each line
        only where it rises above a thousandth of its height: a list
        of a hundred lines is a hundred short strokes, not a hundred
        full-width traces.
        """
        if self.figure is None:
            return
        from matplotlib.collections import LineCollection

        old = self._lines.pop("components", None)
        if old is not None:
            old.remove()
        background = np.asarray(background, dtype=float)
        segments = []
        for curve in curves:
            if curve is None or not np.any(curve > 0):
                continue
            curve = np.asarray(curve, dtype=float)
            keep = np.flatnonzero(curve > 1e-3 * curve.max())
            sl = slice(max(keep[0] - 1, 0), keep[-1] + 2)
            segments.append(np.column_stack(
                [self._x[sl], background[sl] + curve[sl]]))
        if segments:
            collection = LineCollection(segments, colors=COLORS[5],
                                        linewidths=0.8, alpha=0.9)
            collection.set_visible(self._components_shown)
            # inside the observed trace's own limits, so nothing to
            # rescale to -- and a rescale would throw the zoom away
            self._lines["components"] = self.axes.add_collection(
                collection, autolim=False)
        self.canvas.draw_idle()

    def show_components(self, shown: bool) -> None:
        """The individual lines on or off, all together."""
        self._components_shown = bool(shown)
        collection = self._lines.get("components")
        if collection is not None:
            collection.set_visible(self._components_shown)
            self.canvas.draw_idle()

    def show_calculated(self, calculated) -> None:
        """A new calculated curve on the same grid -- a live frame.

        Only the y data of two existing lines changes, which is what
        lets a refinement stream frames without the zoom the user set
        being thrown away or the axes being laid out again.
        """
        line = self._lines.get("calculated")
        if self.figure is None or line is None:
            return
        calculated = np.asarray(calculated, dtype=float)
        line.set_ydata(calculated)
        self._lines["difference"].set_ydata(self._observed - calculated)
        self.difference.relim()
        self.difference.autoscale_view(scalex=False)
        self.canvas.draw_idle()

    @property
    def traces(self) -> list[str]:
        """What is drawn, by name -- for a test and nothing else."""
        return sorted(self._lines)

