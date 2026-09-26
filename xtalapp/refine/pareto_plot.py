"""
xtalapp.refine.pareto_plot
==========================
A weight sweep drawn two ways, beside its table: Rwp and the energy
against the weight on one axis with two scales, and Rwp against the
energy -- the front itself.

**Both are here and not only in the Results panel**, which already
draws the second: the Results panel is a dock of the main window, and
a person reading a sweep in the workbench had to go to another window
to see the curve the table was a list of.  The Results panel keeps
its copy (*Show the front*), because there a point opens its
structure the way a scan's profile does.

A point clicked on either plot chooses its row in the table, which
draws its fit over the pattern; the chosen point is ringed on both.
An unconverged point is a hole, never plotted (see CLAUDE.md, "An
unconverged scan point is not a number").
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from xtal import install
from xtalapp.dialogs.pattern import _figure_canvas, installed
from xtalapp.widgets.tone import WARNING, set_tone

__all__ = ["ParetoPlots"]

#: Rwp, energy, the front, the knee.  Rwp is the pattern plot's
#: calculated red and the energy its difference blue, so the two
#: scales read as the two things they are across both windows.
COLORS = ("#d0473a", "#3a6fb0", "0.2", "#2f8f4e")


class ParetoPlots(QWidget):
    """Rwp and E against w, and Rwp against E, for one sweep."""

    #: A point was clicked: its index in the sweep's own order.
    pointPicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.figure = None
        self._weights = np.zeros(0)
        self._rwp = np.zeros(0)
        self._energy = np.zeros(0)
        self._rings: list = []
        #: each pickable line's points in the sweep's own numbering
        self._orders: dict = {}
        if not installed():
            label = QLabel(f"The plots need matplotlib: "
                           f"{install.command('pxrd')}.")
            label.setWordWrap(True)
            set_tone(label, WARNING)
            layout.addWidget(label)
            layout.addStretch(1)
            return
        canvas_class, _toolbar, figure_class = _figure_canvas()
        self.figure = figure_class(figsize=(6.0, 3.0),
                                   layout="constrained")
        self.by_weight = self.figure.add_subplot(1, 2, 1)
        self.energy_axis = self.by_weight.twinx()
        self.front = self.figure.add_subplot(1, 2, 2)
        self.canvas = canvas_class(self.figure)
        self.canvas.setMinimumSize(300, 180)
        self.canvas.mpl_connect("pick_event", self._on_pick)
        layout.addWidget(self.canvas, 1)
        self.show_result(None)

    def show_result(self, result) -> None:
        """Draw a :class:`~xtal.powder.pareto.ParetoResult`, or the
        empty axes for ``None``."""
        if self.figure is None:
            return
        for axes in (self.by_weight, self.energy_axis, self.front):
            axes.clear()
        self._rings = []
        self._orders = {}
        points = result.points if result is not None else []
        self._weights = np.array([p.weight for p in points], dtype=float)
        self._rwp = np.array([100 * p.rwp for p in points], dtype=float)
        self._energy = np.array([p.energy for p in points], dtype=float)
        self._label_axes()
        if points:
            self._draw(result)
        self.canvas.draw_idle()

    def _label_axes(self) -> None:
        self.by_weight.set_xlabel("energy weight w")
        self.by_weight.set_ylabel("Rwp (%)", color=COLORS[0])
        # clear() puts a twin's axis back on the left, over Rwp's
        self.energy_axis.yaxis.tick_right()
        self.energy_axis.yaxis.set_label_position("right")
        self.energy_axis.set_ylabel("E (kcal/mol)", color=COLORS[1])
        self.by_weight.tick_params(axis="y", colors=COLORS[0])
        self.energy_axis.tick_params(axis="y", colors=COLORS[1])
        self.by_weight.set_title("Against the weight", fontsize=9)
        self.front.set_xlabel("E (kcal/mol)")
        self.front.set_ylabel("Rwp (%)")
        self.front.set_title("Rwp against E", fontsize=9)

    def _draw(self, result) -> None:
        order = np.argsort(self._weights, kind="stable")
        w, rwp, energy = (self._weights[order], self._rwp[order],
                          self._energy[order])
        # every point pickable, in the sweep's own numbering
        (line,) = self.by_weight.plot(w, rwp, "o-", color=COLORS[0],
                                      ms=4, lw=1.0, picker=5)
        self._orders[line] = order
        (line,) = self.energy_axis.plot(w, energy, "s--", color=COLORS[1],
                                        ms=4, lw=1.0, picker=5)
        self._orders[line] = order
        (line,) = self.front.plot(self._energy, self._rwp, "o",
                                  color="0.6", ms=4, picker=5,
                                  label="every weight")
        self._orders[line] = np.arange(len(self._rwp))
        on = [k for k in result.front
              if np.isfinite(self._rwp[k]) and np.isfinite(self._energy[k])]
        if on:
            on.sort(key=lambda k: self._energy[k])
            self.front.plot(self._energy[on], self._rwp[on], "-",
                            color=COLORS[2], lw=1.0, label="front")
        knee = result.knee
        if knee is not None:
            self.front.plot([self._energy[knee]], [self._rwp[knee]], "*",
                            color=COLORS[3], ms=11, label="knee")
            self.by_weight.axvline(self._weights[knee], color=COLORS[3],
                                   lw=0.8, ls=":")
        for k, point in enumerate(result.points):
            if np.isfinite(self._energy[k]) and np.isfinite(self._rwp[k]):
                self.front.annotate(f"{point.weight:g}",
                                    (self._energy[k], self._rwp[k]),
                                    textcoords="offset points",
                                    xytext=(4, 3), fontsize=7,
                                    color="0.35")
        self.front.legend(loc="best", frameon=False, fontsize=8)
        # energies are 171.54 against 171.62, and an offset ("+1.715e2")
        # lands on the axis label; the numbers themselves read better
        for axes in (self.by_weight, self.energy_axis, self.front):
            axes.ticklabel_format(useOffset=False, axis="y")
        self.front.ticklabel_format(useOffset=False, axis="x")

    def mark(self, index: int | None) -> None:
        """Ring the chosen point on both plots."""
        if self.figure is None:
            return
        for ring in self._rings:
            ring.remove()
        self._rings = []
        if index is not None and 0 <= index < len(self._rwp) \
                and np.isfinite(self._rwp[index]):
            style = dict(marker="o", ms=11, mfc="none", mec="0.1",
                         mew=1.2, ls="none")
            w, rwp, energy = (self._weights[index], self._rwp[index],
                              self._energy[index])
            self._rings += self.by_weight.plot([w], [rwp], **style)
            self._rings += self.front.plot([energy], [rwp], **style)
        self.canvas.draw_idle()

    def _on_pick(self, event) -> None:
        indices = getattr(event, "ind", None)
        order = self._orders.get(event.artist)
        if indices is None or not len(indices) or order is None:
            return
        self.pointPicked.emit(int(np.asarray(order)[indices[0]]))

    @property
    def series(self) -> dict[str, np.ndarray]:
        """What is drawn, by name -- for a test and nothing else."""
        return {"weight": self._weights, "rwp": self._rwp,
                "energy": self._energy}
