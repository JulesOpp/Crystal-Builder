"""
xtalapp.widgets.sketcher.tools
==============================
The sketcher's tools: what a click does down the left of the page,
what is drawn and the commands above it.

What a click does is one choice among select, erase, an element, a
bond, a ring, a charge and a hydrogen count; the rest -- undo, redo,
clean up, fit -- are commands.  **Choosing a tool with something
selected also does it to the selection**, which is the second half of
Ctrl+A: select everything, then Double, and every bond is double.

**The gestures are a palette on the left, as ChemDraw has them**, each
a picture of what it draws -- a bond's strokes, a ring's polygon --
rather than a word, three to a row and scrolling when the page is
short (the polymer builder's rows).  Above the page are the elements
and the commands, wrapping as the dialog narrows.  The pictures are
painted in the palette's text colour and painted again when the theme
changes.

Every element is one click away: the common ones are buttons, the
periodic table is the rest, metals included; a metal drawn from it
gets its shape when the molecule is built
(:mod:`xtal.build.coordination`).  The connection-point tool is only
there when the box below would accept a ``*``.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QEvent, QPointF, QSize, Qt
from PySide6.QtGui import QFont, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QScrollArea,
    QToolButton,
    QWidget,
)

from xtal.build.sketch import TEMPLATES
from xtalapp.widgets.periodic_table import PeriodicTableToolButton
from xtalapp.widgets.sketcher.flow import FlowLayout

#: ``(name, tool, tip)``; the name is the button's text and how a test
#: finds it.
SELECTING = (("Select", "select", "Click or drag a box to select "
              "atoms and bonds; drag a selection to move it; Ctrl+A "
              "selects everything"),
             ("Erase", "erase", "Click an atom or a bond to delete it "
              "(Delete removes the selection)"))
ELEMENTS = ("C", "H", "N", "O", "P", "S", "F", "Cl", "Br", "I", "Si")
BONDS = (("Single", "single"), ("Double", "double"),
         ("Triple", "triple"), ("Aromatic", "aromatic"),
         ("Dative", "dative"))
RINGS = (("3", "3"), ("4", "4"), ("5", "5"), ("6", "6"), ("7", "7"),
         ("8", "8"), ("Benzene", "benzene"), ("Pyridine", "pyridine"),
         ("Cyclopentadiene", "cyclopentadiene"), ("Pyrrole", "pyrrole"),
         ("Furan", "furan"), ("Thiophene", "thiophene"))
CHARGES = (("+", "charge:1", "Raise an atom's charge"),
           ("−", "charge:-1", "Lower an atom's charge"),
           ("H+", "hydrogen:1", "One more hydrogen on an atom"),
           ("H−", "hydrogen:-1", "One fewer hydrogen on an atom"))

#: The palette's width in buttons.
COLUMNS = 3
#: A palette picture's side, in pixels.
ICON = 22


class SketchTools(QWidget):
    """The buttons above the page; ``side`` is the palette left of it,
    which the editor lays out.  A click on either tells the canvas."""

    def __init__(self, canvas, parent=None, connection_points=True):
        super().__init__(parent)
        self.canvas = canvas
        self._buttons: dict[str, QToolButton] = {}
        self._painted: dict[str, object] = {}
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.side = _Palette(self, parent)
        grid = self.side.grid

        def row_of(widgets):
            row = grid.rowCount()
            for column, widget in enumerate(widgets):
                grid.addWidget(widget, row, column)

        def rule():
            grid.addWidget(_rule(self.side.inner), grid.rowCount(), 0,
                           1, COLUMNS)

        inner = self.side.inner
        row_of([self._tool(name, tool, tip, inner, _gesture(tool))
                for name, tool, tip in SELECTING])
        rule()
        bonds = [self._tool(
            name, f"bond:{order}",
            f"{name} bond: click a bond to set it, an atom to grow "
            f"one; with bonds selected, all of them change (or "
            f"hover a bond and type 1-3)", inner,
            _bond_picture(order)) for name, order in BONDS]
        for k in range(0, len(bonds), COLUMNS):
            row_of(bonds[k:k + COLUMNS])
        rule()
        rings = [self._tool(
            name, f"ring:{size}", _ring_tip(name, size), inner,
            _ring_picture(size)) for name, size in RINGS]
        for k in range(0, len(rings), COLUMNS):
            row_of(rings[k:k + COLUMNS])
        rule()
        charges = [self._tool(name, tool, tip, inner)
                   for name, tool, tip in CHARGES]
        row_of(charges[:2])
        row_of(charges[2:])
        grid.setRowStretch(grid.rowCount(), 1)

        layout = FlowLayout(self)
        for symbol in ELEMENTS:
            layout.addWidget(self._tool(
                symbol, f"element:{symbol}",
                f"Draw {symbol}; with atoms selected, make them {symbol}"
                f" (or hover an atom and type {symbol}; typed over a "
                f"{symbol}, one hydrogen fewer)"))
        self.table = PeriodicTableToolButton(
            self, current=lambda: self.canvas.element)
        self.table.chosen.connect(self._from_table)
        layout.addWidget(self.table)
        if connection_points:
            layout.addWidget(self._tool(
                "X", "element:X",
                "A connection point (* in the string): where this "
                "piece joins the next"))
        layout.addWidget(_bar(self))
        for name, slot, tip in (
                ("Undo", canvas.undo, "Undo (Ctrl+Z)"),
                ("Redo", canvas.redo, "Redo (Shift+Ctrl+Z)"),
                ("Clean", canvas.clean, "Lay the drawing out again"),
                ("Fit", canvas.fit, "Fit the drawing to the page "
                 "(Ctrl+0); scroll or pinch to zoom, Space-drag to "
                 "pan")):
            layout.addWidget(self._command(name, slot, tip))
        self._paint()
        self.check("C")

    def _tool(self, name: str, tool: str, tip: str, parent=None,
              picture=None) -> QToolButton:
        button = QToolButton(parent or self)
        button.setText(name)
        button.setToolTip(tip)
        button.setCheckable(True)
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.NoFocus)
        if picture is not None:
            self._painted[name] = picture
            button.setToolButtonStyle(Qt.ToolButtonIconOnly)
            button.setIconSize(QSize(ICON, ICON))
        if parent is not None:
            button.setFixedSize(ICON + 8, ICON + 8)
        button.clicked.connect(lambda _=False, t=tool: self._choose(t))
        self.group.addButton(button)
        self._buttons[name] = button
        return button

    def _command(self, name: str, slot, tip: str) -> QToolButton:
        button = QToolButton(self)
        button.setText(name)
        button.setToolTip(tip)
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.NoFocus)
        button.clicked.connect(lambda _=False: slot())
        self._buttons[name] = button
        return button

    def _paint(self) -> None:
        """Every palette picture, in the text colour of now."""
        ink = self.palette().buttonText().color()
        for name, picture in self._painted.items():
            self._buttons[name].setIcon(_icon(picture, ink))

    def changeEvent(self, event) -> None:                   # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.PaletteChange:
            self._paint()

    def _choose(self, tool: str) -> None:
        self.canvas.choose(tool)
        self.canvas.setFocus(Qt.OtherFocusReason)

    def _from_table(self, symbol: str) -> None:
        """An element from the table is a tool like the buttons'; the
        element buttons all go unchecked, since none of them is it."""
        checked = self.group.checkedButton()
        if checked is not None:
            self.group.setExclusive(False)
            checked.setChecked(False)
            self.group.setExclusive(True)
        self._choose(f"element:{symbol}")

    def button(self, name: str) -> QToolButton | None:
        return self._buttons.get(name)

    def check(self, name: str) -> None:
        """Choose a tool by its button's name, as a click would."""
        self._buttons[name].setChecked(True)
        tool = next(t for n, t in self._tools() if n == name)
        self._choose(tool)

    def _tools(self):
        for name, tool, _tip in SELECTING:
            yield name, tool
        for symbol in ELEMENTS:
            yield symbol, f"element:{symbol}"
        yield "X", "element:X"
        for name, order in BONDS:
            yield name, f"bond:{order}"
        for name, size in RINGS:
            yield name, f"ring:{size}"
        for name, tool, _tip in CHARGES:
            yield name, tool


class _Palette(QScrollArea):
    """The gestures, down the left of the page; it scrolls rather than
    holding a short dialog open."""

    def __init__(self, tools, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidgetResizable(True)
        self.inner = QWidget(self)
        self.grid = QGridLayout(self.inner)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(1)
        self.setWidget(self.inner)

    def sizeHint(self) -> QSize:                            # noqa: N802
        inner = self.inner.sizeHint()
        bar = self.verticalScrollBar().sizeHint().width()
        return QSize(inner.width() + bar, inner.height())

    def minimumSizeHint(self) -> QSize:                     # noqa: N802
        return QSize(self.sizeHint().width(), 0)


def _ring_tip(name: str, size: str) -> str:
    if size in TEMPLATES:
        return (f"{name}: on empty page, an atom (hung off it) or a "
                f"bond (fused)")
    typed = f"; or hover a bond and type {size}" if size != "3" else ""
    return (f"A {size}-membered ring: on empty page, an atom (spiro) "
            f"or a bond (fused){typed}")


def _bar(parent) -> QFrame:
    line = QFrame(parent)
    line.setFrameShape(QFrame.VLine)
    line.setFrameShadow(QFrame.Sunken)
    line.setFixedSize(6, 20)
    return line


def _rule(parent) -> QFrame:
    line = QFrame(parent)
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    return line


# ======================================================================
#  THE PICTURES: each a function of a painter, a pen and the side
# ======================================================================

def _icon(picture, ink) -> QIcon:
    scale = 2                           # drawn at twice for a sharp Retina
    pixmap = QPixmap(ICON * scale, ICON * scale)
    pixmap.setDevicePixelRatio(scale)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(ink, 1.6)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    picture(painter, pen, float(ICON))
    painter.end()
    return QIcon(pixmap)


def _gesture(tool: str):
    def select(painter, pen, side):
        dashed = QPen(pen)
        dashed.setStyle(Qt.DashLine)
        dashed.setWidthF(1.2)
        painter.setPen(dashed)
        painter.drawRect(3.5, 3.5, side - 7, side - 7)

    def erase(painter, pen, side):
        painter.translate(side / 2, side / 2)
        painter.rotate(-40)
        painter.drawRoundedRect(-8, -4.5, 16, 9, 2, 2)
        painter.drawLine(QPointF(-2, -4.5), QPointF(-2, 4.5))
        painter.fillRect(-8, -4.5, 6, 9, pen.color())
    return {"select": select, "erase": erase}[tool]


def _bond_picture(order: str):
    def draw(painter, pen, side):
        a, b = QPointF(4, side - 4), QPointF(side - 4, 4)
        across = QPointF(2.6, 2.6)
        if order == "single":
            painter.drawLine(a, b)
        elif order == "double":
            painter.drawLine(a - across / 2, b - across / 2)
            painter.drawLine(a + across / 2, b + across / 2)
        elif order == "triple":
            for shift in (-1, 0, 1):
                painter.drawLine(a + across * shift, b + across * shift)
        elif order == "aromatic":
            painter.drawLine(a - across / 2, b - across / 2)
            dashed = QPen(pen)
            dashed.setDashPattern([2, 2])
            painter.setPen(dashed)
            painter.drawLine(a + across / 2, b + across / 2)
        elif order == "dative":
            painter.drawLine(a, b)
            painter.setBrush(pen.color())
            painter.drawPolygon(QPolygonF([
                b, b + QPointF(-6.5, 1.5), b + QPointF(-1.5, 6.5)]))
    return draw


def _ring_picture(size: str):
    """A regular polygon, point up; a template's double bonds inside
    it and its heteroatom written at the corner the model puts it."""
    count, aromatic, hetero = (TEMPLATES[size] if size in TEMPLATES
                               else (int(size), False, ""))

    def draw(painter, pen, side):
        centre = QPointF(side / 2, side / 2 + (1 if count % 2 else 0))
        radius = side / 2 - 2.5
        corners = [centre + QPointF(
            radius * math.cos(math.pi / 2 + 2 * math.pi * k / count),
            -radius * math.sin(math.pi / 2 + 2 * math.pi * k / count))
            for k in range(count)]
        painter.drawPolygon(QPolygonF(corners))
        if aromatic:
            thin = QPen(pen)
            thin.setWidthF(1.2)
            painter.setPen(thin)
            for k in range(0, count - 1, 2):
                p, q = corners[k], corners[k + 1]
                inward = (centre - (p + q) / 2) * 0.28
                along = (q - p) * 0.18
                painter.drawLine(p + inward + along, q + inward - along)
        if hetero:
            at = corners[-1]
            font = QFont()
            font.setPixelSize(9)
            font.setBold(True)
            painter.setFont(font)
            box = painter.fontMetrics().boundingRect(hetero)
            painter.setPen(Qt.NoPen)
            painter.setBrush(Qt.transparent)
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.drawEllipse(at, 4.6, 4.6)
            painter.setCompositionMode(
                QPainter.CompositionMode_SourceOver)
            painter.setPen(pen)
            painter.drawText(QPointF(at.x() - box.width() / 2,
                                     at.y() + box.height() / 2 - 2.5),
                             hetero)
    return draw
