"""
xtalapp.widgets.sketcher.tools
==============================
The sketcher's tools, above the page, wrapping as the dialog narrows.

What a click does is one choice among select, erase, an element, a
bond, a ring, a charge and a hydrogen count; the rest -- undo, redo,
clean up, fit -- are commands.  **Choosing a tool with something
selected also does it to the selection**, which is the second half of
Ctrl+A: select everything, then Double, and every bond is double.

Every element is one click away: the common ones are buttons, the
periodic table is the rest, metals included; a metal drawn from it
gets its shape when the molecule is built
(:mod:`xtal.build.coordination`).  The connection-point tool is only
there when the box below would accept a ``*``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QToolButton,
    QWidget,
)

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
         ("8", "8"), ("Benzene", "benzene"))
CHARGES = (("+", "charge:1", "Raise an atom's charge"),
           ("−", "charge:-1", "Lower an atom's charge"),
           ("H+", "hydrogen:1", "One more hydrogen on an atom"),
           ("H−", "hydrogen:-1", "One fewer hydrogen on an atom"))


class SketchTools(QWidget):
    """The buttons; a click on one tells the canvas."""

    def __init__(self, canvas, parent=None, connection_points=True):
        super().__init__(parent)
        self.canvas = canvas
        self._buttons: dict[str, QToolButton] = {}
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        layout = FlowLayout(self)

        for name, tool, tip in SELECTING:
            layout.addWidget(self._tool(name, tool, tip))
        layout.addWidget(_bar(self))
        for symbol in ELEMENTS:
            layout.addWidget(self._tool(
                symbol, f"element:{symbol}",
                f"Draw {symbol}; with atoms selected, make them {symbol}"
                f" (or hover an atom and type {symbol})"))
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
        for name, order in BONDS:
            layout.addWidget(self._tool(
                name, f"bond:{order}",
                f"{name} bond: click a bond to set it, an atom to grow "
                f"one; with bonds selected, all of them change"))
        layout.addWidget(_bar(self))
        for name, size in RINGS:
            layout.addWidget(self._tool(
                name, f"ring:{size}",
                "Benzene" if size == "benzene" else
                f"A {size}-membered ring: on empty page, an atom "
                f"(spiro) or a bond (fused)"))
        layout.addWidget(_bar(self))
        for name, tool, tip in CHARGES:
            layout.addWidget(self._tool(name, tool, tip))
        layout.addWidget(_bar(self))
        for name, slot, tip in (
                ("Undo", canvas.undo, "Undo (Ctrl+Z)"),
                ("Redo", canvas.redo, "Redo (Shift+Ctrl+Z)"),
                ("Clean", canvas.clean, "Lay the drawing out again"),
                ("Fit", canvas.fit, "Fit the drawing to the page")):
            layout.addWidget(self._command(name, slot, tip))
        self.check("C")

    def _tool(self, name: str, tool: str, tip: str) -> QToolButton:
        button = QToolButton(self)
        button.setText(name)
        button.setToolTip(tip)
        button.setCheckable(True)
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.NoFocus)
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


def _bar(parent) -> QFrame:
    line = QFrame(parent)
    line.setFrameShape(QFrame.VLine)
    line.setFrameShadow(QFrame.Sunken)
    line.setFixedSize(6, 20)
    return line
