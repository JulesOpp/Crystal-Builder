"""
xtalapp.docks.columns
=====================
Groups of controls that sit side by side when a panel has the room and
stack when it does not.

A panel lives in a column the user drags.  Laid out for the width it
was designed at, it either wastes half of a wide column or, once the
column is dragged narrower, grows a horizontal scroll bar -- and a
panel read by scrolling sideways is one whose right-hand half nobody
finds.  :class:`ReflowColumns` decides at every width: two columns when
the widest group fits twice, one below that, never wider than the
panel it is in.

It is a layout rather than a widget that moves its children between
two boxes on ``resizeEvent``: a scroll area asks its widget's layout
for *height for width*, and only a layout that answers can be given
the right height at the width it is about to be -- the other way round,
the panel is laid out one resize late and the bottom group is cut off
until the next one.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLayout,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

#: Wider than any panel is ever given.
_WIDE = 4096


def _height(item, width: int) -> int:
    """How tall ``item`` is at ``width``, measured on its widget.

    Not on the layout item: on macOS a group box's item is its frame
    without the title, and the item at the top of a column was set
    through Qt's edge rule that keeps a widget inside its parent --
    every column's first group came out 15 px short of its frame, its
    last row of buttons squashed flat.  :meth:`_ReflowLayout.
    setGeometry` places the widget itself to match.
    """
    widget = item.widget()
    if widget is None:
        if item.hasHeightForWidth():
            return max(item.heightForWidth(width),
                       item.minimumSize().height())
        return item.sizeHint().height()
    if widget.hasHeightForWidth():
        return max(widget.heightForWidth(width), widget.minimumHeight())
    return max(widget.sizeHint().height(), widget.minimumHeight())


def _unwrapped(item) -> int:
    """The narrowest width at which ``item`` is no taller than it is
    when given all the width it could want -- where its form stops
    folding labels over fields."""
    low = item.minimumSize().width()
    if not item.hasHeightForWidth():
        return low
    flat = _height(item, _WIDE)
    high = max(low, item.sizeHint().width())
    if _height(item, high) > flat:
        high = _WIDE
    while low < high:
        middle = (low + high) // 2
        if _height(item, middle) > flat:
            low = middle + 1
        else:
            high = middle
    return low


class _ReflowLayout(QLayout):
    """The first ``split`` items on the left, the rest on the right --
    or all of them in one column, in that same order.  With ``split``
    ``None`` the cut is wherever the two columns come out most nearly
    the same height."""

    def __init__(self, parent=None, split: int | None = 0):
        super().__init__(parent)
        self._items = []
        self.split = split

    # -- QLayout's bookkeeping ----------------------------------------

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        return self._items[index] if 0 <= index < len(self._items) \
            else None

    def takeAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    # -- sizes ---------------------------------------------------------

    def _shown(self) -> list:
        return [item for item in self._items if not item.isEmpty()]

    def _margins(self) -> tuple[int, int]:
        m = self.contentsMargins()
        return m.left() + m.right(), m.top() + m.bottom()

    def invalidate(self) -> None:
        self._two_column_width = None
        super().invalidate()

    def two_column_width(self) -> int:
        """The narrowest width at which neither column wraps a row.

        Not the groups' minimum: a form squeezed to it puts every label
        above its field, and two columns of that were a worse picture
        than one column of rows.  Not their hint either: a hint is what
        a group would like with every combo at its longest entry, and
        waiting for that kept the Style panel in one column at 646 px,
        wider than the column ever opens.
        """
        if getattr(self, "_two_column_width", None) is None:
            widest = max((_unwrapped(item) for item in self._shown()),
                         default=0)
            self._two_column_width = (2 * widest + self.spacing()
                                      + self._margins()[0])
        return self._two_column_width

    def two_columns_at(self, width: int) -> bool:
        shown = len(self._shown())
        split = 1 if self.split is None else self.split
        return 0 < split < shown and width >= self.two_column_width()

    def _balanced(self, shown: list, column: int) -> int:
        """How many go on the left for the shorter of the two columns.

        A fixed split is right for one picture of the panel only: a
        style that shows four more rows, a fold opened, a group with
        nothing to say hidden, and the column that was balanced is
        half empty.  The Style panel's right-hand column ran 550 px
        past its left that way.
        """
        heights = [_height(item, column) for item in shown]
        total = sum(heights)
        best, best_split, left = None, 1, 0
        for split in range(1, len(shown)):
            left += heights[split - 1]
            tallest = max(left, total - left)
            if best is None or tallest < best:
                best, best_split = tallest, split
        return best_split

    def _columns(self, width: int) -> list[tuple[list, int]]:
        """Each column's items and its width, for a total ``width``."""
        shown = self._shown()
        inner = width - self._margins()[0]
        if not self.two_columns_at(width):
            return [(shown, inner)]
        half = (inner - self.spacing()) // 2
        split = (self._balanced(shown, half) if self.split is None
                 else self.split)
        return [(shown[:split], half),
                (shown[split:], inner - self.spacing() - half)]

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        tallest = 0
        for items, column in self._columns(width):
            heights = [_height(item, column) for item in items]
            tallest = max(tallest, sum(heights)
                          + self.spacing() * max(len(heights) - 1, 0))
        return tallest + self._margins()[1]

    def minimumSize(self) -> QSize:
        """The one-column minimum width: never two columns' worth, or
        the panel would hold its column open at twice the width.

        And no height beyond the tallest item's.  The height at any
        width is :meth:`heightForWidth`, which the scroll area asks;
        a minimum reporting the one-column height held the Style panel
        at 1345 px when its two columns were 850, and the panel
        scrolled on into 500 px of nothing.
        """
        shown = self._shown()
        width = max((item.minimumSize().width() for item in shown),
                    default=0) + self._margins()[0]
        height = max((item.minimumSize().height() for item in shown),
                     default=0) + self._margins()[1]
        return QSize(width, height)

    def sizeHint(self) -> QSize:
        shown = self._shown()
        width = max((item.sizeHint().width() for item in shown),
                    default=0) + self._margins()[0]
        return QSize(width, self.heightForWidth(width))

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        m = self.contentsMargins()
        x = rect.x() + m.left()
        for items, column in self._columns(rect.width()):
            y = rect.y() + m.top()
            for item in items:
                height = _height(item, column)
                place = QRect(QPoint(x, y), QSize(column, height))
                if item.widget() is not None:
                    item.widget().setGeometry(place)
                else:
                    item.setGeometry(place)
                y += height + self.spacing()
            x += column + self.spacing()
        owner = self.parentWidget()
        if getattr(owner, "_hold_height", False):
            # Here and not on resize: a fold opened inside a group
            # makes it taller at the same width.
            need = self.heightForWidth(rect.width())
            if owner.minimumHeight() != need:
                owner.setMinimumHeight(need)


class ReflowColumns(QWidget):
    """Widgets in two columns when there is room for them, else one.

    ``split`` is how many go in the left-hand column; one column reads
    in the order they were given, so the order is chosen for the
    narrow case and the split for the wide one.  ``None`` cuts where
    the columns come out most even, at every width and every time a
    group grows or shrinks.

    ``hold_height`` is for a parent that does not ask for height for
    width -- a splitter -- which would otherwise squeeze one column's
    worth of groups into the height of the tallest of them.
    """

    def __init__(self, widgets, split: int | None, parent=None,
                 hold_height: bool = False):
        super().__init__(parent)
        self.widgets = list(widgets)
        layout = _ReflowLayout(self, split)
        layout.setContentsMargins(0, 0, 0, 0)
        # A group's title is inside the rectangle it is given (see
        # `_height`), so this is the gap from one frame to the next
        # title.  It was 14 when the title sat outside, and doubled.
        layout.setSpacing(6)
        for widget in self.widgets:
            layout.addWidget(widget)
        policy = QSizePolicy(QSizePolicy.Policy.Preferred,
                             QSizePolicy.Policy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self._hold_height = hold_height

    def two_columns(self) -> bool:
        """Whether it is laid out in two columns at its present width."""
        return self.layout().two_columns_at(self.width())

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self.layout().heightForWidth(width)


class Collapsible(QWidget):
    """A header with an arrow, and a body the arrow shows and hides.

    ``switch``, when given, is a widget that sits in the header beside
    the arrow -- a checkbox that turns the whole group on -- so that
    whether a feature is on can be read, and changed, with its settings
    folded away.
    """

    #: The body was shown (``True``) or hidden, by a click or by code.
    toggled = Signal(bool)

    def __init__(self, title: str, body: QWidget, switch=None,
                 parent=None):
        super().__init__(parent)
        self._title = title
        self.body = body
        self.arrow = QToolButton()
        self.arrow.setCheckable(True)
        self.arrow.setAutoRaise(True)
        # Borderless: framed, macOS draws the arrow as a button the size
        # of the checkbox beside it, and it reads as a second control.
        self.arrow.setStyleSheet("QToolButton { border: none; }")
        self.arrow.setArrowType(Qt.RightArrow)
        self.arrow.setToolTip(f"Show or hide the {title.lower()} "
                              "settings")
        self.arrow.toggled.connect(self._on_arrow)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(self.arrow)
        if switch is not None:
            header.addWidget(switch)
        else:
            self.arrow.setText(title)
            self.arrow.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        header.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(header)
        layout.addWidget(body)
        body.setVisible(False)

    def title(self) -> str:
        return self._title

    def is_open(self) -> bool:
        return self.arrow.isChecked()

    def set_open(self, open_: bool) -> None:
        self.arrow.setChecked(bool(open_))

    def _on_arrow(self, open_: bool) -> None:
        self.arrow.setArrowType(Qt.DownArrow if open_ else Qt.RightArrow)
        self.body.setVisible(open_)
        self.toggled.emit(open_)
