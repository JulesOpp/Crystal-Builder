"""
xtalapp.docks
=============
The panels around the viewport.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QScrollArea

#: The most room, in either direction, a panel may insist on.  A dock
#: area can be no smaller than the largest minimum of any dock shown in
#: it, so this is also the narrowest a column can be dragged to.
MAXIMUM_MINIMUM = 200


def scrolling(inner) -> QScrollArea:
    """*inner* in a frameless scroll area, ready for ``setWidget``.

    A dock's minimum size is its contents' minimum, and a dock area's
    is the largest minimum of every dock shown in it -- **tabbed behind
    another or not**.  So the Measure panel, laid out at 419 px, held
    the whole right-hand column at 419 px once it had been opened, and
    dragging the divider did nothing below that however narrow the
    panel in front was.  Which panels had been opened decided whether
    a drag worked, which is why it seemed to work only sometimes.

    Inside a scroll area the panel scrolls instead of holding the
    column, in both directions, and the divider goes where it is
    dragged.  Frameless, so a panel wide enough to need no scroll bar
    looks exactly as it did.
    """
    area = QScrollArea()
    area.setWidget(inner)
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    return area
