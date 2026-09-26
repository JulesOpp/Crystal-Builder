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
that already exist.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from xtal import install
from xtalapp.dialogs.pattern import _figure_canvas, installed
from xtalapp.widgets.tone import WARNING, set_tone

__all__ = ["RefinementPlot"]

#: Observed, calculated, background, difference, ticks.
COLORS = ("0.15", "#d0473a", "0.6", "#3a6fb0", "#2f8f4e")


class RefinementPlot(QWidget):
    """A pattern and a fit to it, or a sentence naming the extra."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.available = installed()
        self.figure = None
        self._lines: dict = {}
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
        grid = self.figure.add_gridspec(2, 1, height_ratios=(4, 1))
        self.axes = self.figure.add_subplot(grid[0])
        self.difference = self.figure.add_subplot(grid[1],
                                                  sharex=self.axes)
        self.canvas = canvas_class(self.figure)
        self.canvas.setMinimumSize(360, 240)
        self.toolbar = toolbar_class(self.canvas, self)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, 1)
        self._x = np.zeros(0)
        self._observed = np.zeros(0)
        self.clear()

    # -- what is drawn -------------------------------------------------

    def clear(self) -> None:
        if self.figure is None:
            return
        self.axes.clear()
        self.difference.clear()
        self._lines = {}
        self.axes.set_ylabel("counts")
        self.difference.set_xlabel(r"2$\theta$ (degrees)")
        self.difference.set_ylabel("obs - calc")
        self.axes.tick_params(labelbottom=False)
        self.canvas.draw_idle()

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
        self.canvas.draw_idle()

    def show_fit(self, x, observed, calculated, background=None,
                 ticks=()) -> None:
        """A fit, from scratch: the observed trace is its grid's."""
        if self.figure is None:
            return
        self.show_observed(x, observed)
        if background is not None:
            (self._lines["background"],) = self.axes.plot(
                self._x, np.asarray(background, dtype=float), lw=0.8,
                color=COLORS[2], label="background")
        (self._lines["calculated"],) = self.axes.plot(
            self._x, np.asarray(calculated, dtype=float), lw=1.0,
            color=COLORS[1], label="calculated")
        (self._lines["difference"],) = self.difference.plot(
            self._x, self._observed - np.asarray(calculated, dtype=float),
            lw=0.8, color=COLORS[3])
        self.difference.axhline(0.0, lw=0.5, color="0.5")
        self.set_ticks(ticks)
        self.axes.legend(loc="upper right", frameon=False, fontsize=9)
        self.canvas.draw_idle()

    def set_ticks(self, positions) -> None:
        """Where the peaks (or reflections) are: a comb under zero."""
        if self.figure is None:
            return
        old = self._lines.pop("ticks", None)
        if old is not None:
            old.remove()
        positions = np.asarray(positions, dtype=float)
        if positions.size and self._observed.size:
            top = float(self._observed.max())
            depth = 0.04 * top
            self._lines["ticks"] = self.axes.vlines(
                positions, -2.0 * depth, -depth, colors=COLORS[4],
                linewidths=0.8)
            self.axes.set_ylim(-2.5 * depth, 1.05 * top)
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

