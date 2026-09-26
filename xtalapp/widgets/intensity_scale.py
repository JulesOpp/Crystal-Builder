"""
xtalapp.widgets.intensity_scale
===============================
Linear, square-root or logarithmic intensity: the one choice every
diffraction plot offers.

A pattern's strongest line can be a hundred times its weakest, and on
a linear axis the weak ones -- the ones that decide a space group or
betray an impurity -- are a flat line along the bottom.  The square
root is what counting statistics make natural (the noise on every
point comes out the same height); the logarithm shows the background
and the tails.  A difference curve is not offered them: it crosses
zero, and on either scale its sign is what gets lost.

**The square root is signed**, ``sign(y)·√|y|``, so a trace that dips
below zero -- a fit's background going a count negative, a comb drawn
under the pattern -- is still drawn rather than dropped.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import QComboBox

__all__ = ["SCALES", "apply_scale", "scale_box"]

#: ``(key, label)`` in the order the box offers them.
SCALES = (("linear", "Linear"), ("sqrt", "Square root"),
          ("log", "Logarithmic"))

#: How far below its top a logarithmic axis reaches: a calculated
#: pattern's tails go to 1e-12 of the peak, and an axis sized to them
#: would give the pattern a sliver at the top.
_LOG_DECADES = 5


def _signed_sqrt(y):
    y = np.asarray(y, dtype=float)
    return np.sign(y) * np.sqrt(np.abs(y))


def _signed_square(y):
    y = np.asarray(y, dtype=float)
    return np.sign(y) * y * y


def scale_box(parent=None) -> QComboBox:
    """The choice, as a box whose data is the key."""
    box = QComboBox(parent)
    for key, label in SCALES:
        box.addItem(label, key)
    box.setToolTip("How intensity is drawn: square root shows the weak "
                   "lines, logarithmic the background and the tails.  "
                   "The difference curve stays linear.")
    return box


def apply_scale(axes, key: str) -> None:
    """Put ``axes`` on the scale ``key`` names and fit it to what is
    drawn -- a scale change is a new view, not a zoom to keep."""
    if key == "log":
        # Fitted by hand: a pattern's zeros put matplotlib's own
        # autoscale below zero, which a logarithm refuses with a
        # warning, and its tails reach 1e-12 of the peak.
        y = np.concatenate([np.asarray(line.get_ydata(), dtype=float)
                            for line in axes.lines] or [np.ones(1)])
        y = y[np.isfinite(y) & (y > 0)]
        high = float(y.max()) if y.size else 10.0
        low = max(float(y.min()) if y.size else 1.0,
                  high * 10.0 ** -_LOG_DECADES)
        axes.set_ylim(1.0, 10.0)
        axes.set_yscale("log", nonpositive="mask")
        axes.set_ylim(low / 1.5, high * 1.5)
        return
    if key == "sqrt":
        axes.set_yscale("function", functions=(_signed_sqrt,
                                               _signed_square))
    else:
        axes.set_yscale("linear")
    axes.relim()
    axes.autoscale(enable=True, axis="y")
    axes.autoscale_view(scalex=False)
