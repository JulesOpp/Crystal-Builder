"""
xtalapp.widgets.tone
====================
Hint text and warnings that read in a dark window as well as a light
one.

They were written as literals in fifty places: ``color: #8a5a00`` for
a warning, the same on ``background: #fdf3e0`` for a warning box, and
``color: palette(mid)`` for a hint.  The Qt chrome already follows the
system theme, and those three did not -- dark amber on a dark panel is
barely there, the cream box is a light patch in a dark window, and
``mid`` on the macOS dark palette is nearly the background, which is
how the sentence explaining what Save File does became invisible.

**A tone is a property, and the colour is worked out from the
palette.**  :func:`set_tone` records which of the three a widget is
and styles it for the palette in force; :func:`retone` styles every
widget that has one again, which the window calls when the theme
changes.  A dialog is built afresh each time it opens, so it is always
current.  In a light window the colours are exactly the literals they
replace.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget

HINT = "hint"
WARNING = "warning"
WARNING_BOX = "warning-box"

#: The literals these replace, kept for a light window, and what reads
#: the same way on a dark one.
_AMBER = {False: "#8a5a00", True: "#f0b44c"}
_CREAM = {False: "#fdf3e0", True: "#3d3016"}

#: How far from the text colour toward the background a hint sits.
_HINT_ALPHA = 0.62


def is_dark(palette: QPalette | None = None) -> bool:
    palette = palette or QApplication.palette()
    return palette.color(QPalette.Window).lightness() < 128


def style(kind: str | None, palette: QPalette | None = None,
          padding: int | None = None) -> str:
    """The style sheet for ``kind`` under ``palette``.

    ``padding`` goes with any tone, plain included, because a box that
    loses its padding when its warning clears jumps under the cursor.
    A warning box has 5 px unless told otherwise.
    """
    palette = palette or QApplication.palette()
    dark = is_dark(palette)
    if kind == WARNING_BOX and padding is None:
        padding = 5
    padded = "" if padding is None else f" padding: {padding}px;"
    if not kind:
        return padded.strip()
    if kind == HINT:
        text = QColor(palette.color(QPalette.WindowText))
        return (f"color: rgba({text.red()}, {text.green()}, "
                f"{text.blue()}, {_HINT_ALPHA});" + padded)
    if kind == WARNING:
        return f"color: {_AMBER[dark]};" + padded
    if kind == WARNING_BOX:
        return (f"color: {_AMBER[dark]}; background: {_CREAM[dark]};"
                + padded)
    raise ValueError(f"no tone called {kind!r}")


def set_tone(widget: QWidget, kind: str | None,
             padding: int | None = None) -> None:
    """Style ``widget`` as a hint, a warning, a warning box, or plain."""
    widget.setProperty("tone", kind or "")
    widget.setProperty("tone_padding", -1 if padding is None else padding)
    widget.setStyleSheet(style(kind, padding=padding))


def retone(root: QWidget) -> int:
    """Style every widget under ``root`` that has a tone again.

    For a theme change: the colours were worked out from the palette
    that was in force when each was set.  How many were restyled.
    """
    count = 0
    for widget in [root, *root.findChildren(QWidget)]:
        kind = widget.property("tone")
        if kind:
            padding = widget.property("tone_padding")
            padding = None if padding in (None, -1) else int(padding)
            widget.setStyleSheet(style(kind, padding=padding))
            count += 1
    return count
