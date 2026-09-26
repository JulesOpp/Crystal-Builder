"""
xtalapp.refine.bravais
======================
The fourteen Bravais lattices as boxes to tick -- TOPAS's
``Bravais_*_sgs`` lines, one row a crystal system.

A text box of symbols is what ``xtal run`` takes and what the step
declares; a person choosing which lattices a search may spend its
minute on wants to see all fourteen and untick the ones it cannot be.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QLabel,
)

from xtal.powder.index import parse_bravais

__all__ = ["BravaisBox"]

#: ``(row label, symbols)``.  Hexagonal holds hR as well, as TOPAS's
#: ``Bravais_Trigonal_Hexagonal_sgs`` does.
ROWS = (("Triclinic", ("aP",)),
        ("Monoclinic", ("mP", "mC")),
        ("Orthorhombic", ("oP", "oC", "oI", "oF")),
        ("Tetragonal", ("tP", "tI")),
        ("Hexagonal", ("hP", "hR")),
        ("Cubic", ("cP", "cI", "cF")))

_TIPS = {"hP": "Hexagonal and trigonal P: one lattice",
         "hR": "Rhombohedral, searched on hexagonal axes"}


class BravaisBox(QGroupBox):
    """A box per lattice, and one per crystal system that ticks or
    unticks its row; :meth:`value` is the step's ``bravais``."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__("Bravais lattices", parent)
        self.setToolTip("Which lattices to search.  Unticking the low "
                        "symmetries saves most of the time.")
        grid = QGridLayout(self)
        self.boxes: dict[str, QCheckBox] = {}
        #: the row boxes, by row label: partly checked when some of
        #: the row is ticked
        self.rows: dict[str, QCheckBox] = {}
        for r, (label, symbols) in enumerate(ROWS):
            grid.addWidget(QLabel(label), r, 0)
            whole = QCheckBox()
            whole.setTristate(True)
            whole.setToolTip(f"Tick or untick every {label.lower()} "
                             f"lattice")
            whole.clicked.connect(
                lambda _on, row=label: self._toggle_row(row))
            self.rows[label] = whole
            grid.addWidget(whole, r, 1)
            for c, symbol in enumerate(symbols, start=3):
                box = QCheckBox(symbol)
                box.setChecked(True)
                box.setToolTip(_TIPS.get(symbol, ""))
                box.toggled.connect(lambda _on: self._on_toggled())
                self.boxes[symbol] = box
                grid.addWidget(box, r, c)
        # a rule between the row boxes and the lattices, so a box that
        # ticks a whole row is not read as one more lattice
        self.rule = QFrame()
        self.rule.setFrameShape(QFrame.VLine)
        self.rule.setFrameShadow(QFrame.Sunken)
        grid.addWidget(self.rule, 0, 2, len(ROWS), 1)
        self._sync_rows()

    def _toggle_row(self, label: str) -> None:
        """All of a row on, unless all of it already is: a partly
        ticked row goes to all, as a file manager's does."""
        symbols = dict(ROWS)[label]
        on = not all(self.boxes[s].isChecked() for s in symbols)
        for symbol in symbols:
            self.boxes[symbol].blockSignals(True)
            self.boxes[symbol].setChecked(on)
            self.boxes[symbol].blockSignals(False)
        self._on_toggled()

    def _on_toggled(self) -> None:
        self._sync_rows()
        self.changed.emit()

    def _sync_rows(self) -> None:
        for label, symbols in ROWS:
            ticked = sum(self.boxes[s].isChecked() for s in symbols)
            state = Qt.Checked if ticked == len(symbols) else \
                Qt.Unchecked if not ticked else Qt.PartiallyChecked
            whole = self.rows[label]
            whole.blockSignals(True)
            whole.setCheckState(state)
            whole.blockSignals(False)

    def value(self) -> str:
        """``"all"``, ``"none"``, or the ticked symbols separated by
        commas.  Never empty: the step reads empty as all of them."""
        ticked = [s for s, box in self.boxes.items() if box.isChecked()]
        if len(ticked) == len(self.boxes):
            return "all"
        return ",".join(ticked) or "none"

    def set_value(self, text) -> None:
        chosen = parse_bravais(text)
        for symbol, box in self.boxes.items():
            box.blockSignals(True)
            box.setChecked(symbol in chosen)
            box.blockSignals(False)
        self._on_toggled()
