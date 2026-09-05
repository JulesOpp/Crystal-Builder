"""
xtalapp.widgets.periodic_table
==============================
Pick an element by pointing at it rather than by typing its symbol.

Every element chooser in the application is the same editable combo,
which is fine for carbon and hopeless for the element somebody knows
by position and not by symbol -- the second-row transition metal two
along from molybdenum.  This is the picture of the table, in the Jmol
colours the viewport already draws atoms in, and one click is the
whole of the interaction.

**The layout is the one new piece of data.**  :mod:`xtal.core.elements`
carries symbol, atomic number, name and colour but no group or period,
because nothing headless has ever needed them -- where an element sits
in the printed table is a fact about the picture and not about the
chemistry, which is why it lives here beside the widget that draws it.

``X`` is not offered.  A dummy is a marker rather than an element and
has a gesture of its own (``Structure > Add centroid``); putting it in
the table would say it is the 119th element.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
)

from xtal.core import elements as el

#: The table as it is printed, one string per row, ``.`` for a gap.
#:
#: Written as a picture rather than as a symbol-to-(row, column) map
#: on purpose: the shape of the periodic table is the thing being
#: stated, and a map of 118 pairs states it in a form nobody can
#: check by eye.  A misplaced element here is visible; in a dict it
#: is not.
#:
#: The f block hangs below as the two rows it is always drawn as, and
#: the group-3 cells above it are left empty -- the conventional
#: picture, and the one that keeps every element in exactly one cell.
_LAYOUT = (
    "H   .   .   .   .   .   .   .   .   .   .   .   .   .   .   .   .   He",
    "Li  Be  .   .   .   .   .   .   .   .   .   .   B   C   N   O   F   Ne",
    "Na  Mg  .   .   .   .   .   .   .   .   .   .   Al  Si  P   S   Cl  Ar",
    "K   Ca  Sc  Ti  V   Cr  Mn  Fe  Co  Ni  Cu  Zn  Ga  Ge  As  Se  Br  Kr",
    "Rb  Sr  Y   Zr  Nb  Mo  Tc  Ru  Rh  Pd  Ag  Cd  In  Sn  Sb  Te  I   Xe",
    "Cs  Ba  .   Hf  Ta  W   Re  Os  Ir  Pt  Au  Hg  Tl  Pb  Bi  Po  At  Rn",
    "Fr  Ra  .   Rf  Db  Sg  Bh  Hs  Mt  Ds  Rg  Cn  Nh  Fl  Mc  Lv  Ts  Og",
    "",
    ".   .   La  Ce  Pr  Nd  Pm  Sm  Eu  Gd  Tb  Dy  Ho  Er  Tm  Yb  Lu  .",
    ".   .   Ac  Th  Pa  U   Np  Pu  Am  Cm  Bk  Cf  Es  Fm  Md  No  Lr  .",
)


def layout_cells() -> list[tuple[str, int, int]]:
    """``(symbol, row, column)`` for every element in the table.

    Parsed from :data:`_LAYOUT` rather than stored, so the picture
    above is the single statement of where things are.
    """
    cells = []
    for row, line in enumerate(_LAYOUT):
        for column, token in enumerate(line.split()):
            if token != ".":
                cells.append((token, row, column))
    return cells


def _text_color(rgb) -> str:
    """Black or white, whichever can be read on ``rgb``.

    Hydrogen is white and iodine is near-black, so a single ink colour
    makes one end of the table or the other unreadable.
    """
    red, green, blue = rgb
    luminance = 0.299 * red + 0.587 * green + 0.114 * blue
    return "#000000" if luminance > 140 else "#ffffff"


class PeriodicTableDialog(QDialog):
    """The table, and a click on it is the answer.

    One click picks *and* closes: the dialog asks exactly one question
    and an OK button after the click would be a second answer to it.
    Cancel is still there, because Escape has to leave with the
    element the caller already had.
    """

    def __init__(self, parent=None, current: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Choose an element")
        self._chosen = el.canonical_symbol(current or "") or ""
        self.buttons = {}

        grid = QGridLayout()
        grid.setSpacing(2)
        filled = set()
        for symbol, row, column in layout_cells():
            grid.addWidget(self._button(symbol), row, column)
            filled.add(row)
        # The blank line in the picture is a real gap.  A grid row
        # holding no widget has no height, so without this the f
        # block sits hard against the main table and reads as part
        # of it.
        for row in range(len(_LAYOUT)):
            if row not in filled:
                grid.setRowMinimumHeight(row, 10)

        self.caption = QLabel()
        self.caption.setTextFormat(Qt.PlainText)

        box = QDialogButtonBox(QDialogButtonBox.Cancel)
        box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(grid)
        layout.addWidget(self.caption)
        layout.addWidget(box)
        self._describe(self._chosen)

    def _button(self, symbol: str) -> QToolButton:
        record = el.element(symbol)
        button = QToolButton(self)
        button.setObjectName(f"element_{symbol}")
        button.setText(symbol)
        button.setFixedSize(38, 30)
        button.setToolTip(f"{record.name} ({record.z})")
        edge = ("2px solid #1a6fd4" if symbol == self._chosen
                else "1px solid #7f7f7f")
        button.setStyleSheet(
            f"QToolButton {{ background: rgb{record.color}; "
            f"color: {_text_color(record.color)}; "
            f"border: {edge}; border-radius: 3px; }}")
        button.clicked.connect(
            lambda checked=False, s=symbol: self.choose(s))
        # The name under the cursor, so the table reads as a table
        # rather than as 118 two-letter abbreviations.
        button.installEventFilter(self)
        self.buttons[symbol] = button
        return button

    def eventFilter(self, watched, event):
        if event.type() == event.Type.Enter:
            self._describe(watched.text())
        return super().eventFilter(watched, event)

    def _describe(self, symbol: str) -> None:
        record = el.canonical_symbol(symbol or "")
        if record is None:
            self.caption.setText("Click an element.")
            return
        found = el.element(record)
        self.caption.setText(
            f"{found.symbol} - {found.name}, Z = {found.z}, "
            f"{found.mass:.3f} u")

    def choose(self, symbol: str) -> None:
        """Take ``symbol`` as the answer and close."""
        self._chosen = symbol
        self.accept()

    def selected(self) -> str:
        return self._chosen

    @classmethod
    def ask(cls, parent=None, current: str = "") -> str | None:
        """The chosen symbol, or ``None`` if the user cancelled."""
        dialog = cls(parent, current)
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.selected()


class PeriodicTableButton(QPushButton):
    """The button that opens the table, for putting beside a combo.

    It exists so that the four element choosers in the application can
    grow the same button by adding one widget rather than by each
    knowing how to open a dialog.  It reports the choice through
    :attr:`chosen` and never touches the widget beside it -- the
    caller decides what a picked element means.
    """

    chosen = Signal(str)

    def __init__(self, parent=None, current=None):
        super().__init__("Table...", parent)
        self.setObjectName("periodic_table_button")
        self.setToolTip("Pick the element from a periodic table")
        #: A callable giving the symbol to start on, or ``None``.
        self.current = current
        self.clicked.connect(self.open_table)

    def open_table(self) -> str | None:
        start = "" if self.current is None else (self.current() or "")
        symbol = PeriodicTableDialog.ask(self, start)
        if symbol:
            self.chosen.emit(symbol)
        return symbol
