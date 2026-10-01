"""
xtalapp.widgets.fit
===================
A dialog as tall as its wrapped text needs.

A top-level window does not answer *height for width*: Qt sizes it
from its layout's minimum, which counts a word-wrapped label as one
line.  So a dialog whose status text wraps to four lines keeps the
height it had with one, and Qt finds the difference by squashing the
form above -- the Fill pores dialog drew its Source and Point rows
48 px short, combos and spin boxes cut through the middle of their
text.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget


def fit_height(window: QWidget) -> None:
    """Grow ``window`` to the height its layout needs at its width.

    Only ever grows, and holds that height as the minimum: a dialog
    whose note just got shorter is left where the user has it rather
    than jumping, and one dragged shorter than its contents could
    only be squashed again.
    """
    layout = window.layout()
    if layout is None:
        return
    layout.activate()
    needed = layout.totalHeightForWidth(window.width())
    if needed <= 0:
        return
    window.setMinimumHeight(needed)
    if window.height() < needed:
        window.resize(window.width(), needed)
