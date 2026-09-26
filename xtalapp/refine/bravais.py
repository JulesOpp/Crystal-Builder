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

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QGridLayout, QGroupBox, QLabel

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
    """A box per lattice; :meth:`value` is the step's ``bravais``."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__("Bravais lattices", parent)
        self.setToolTip("Which lattices to search.  Unticking the low "
                        "symmetries saves most of the time.")
        grid = QGridLayout(self)
        self.boxes: dict[str, QCheckBox] = {}
        for r, (label, symbols) in enumerate(ROWS):
            grid.addWidget(QLabel(label), r, 0)
            for c, symbol in enumerate(symbols, start=1):
                box = QCheckBox(symbol)
                box.setChecked(True)
                box.setToolTip(_TIPS.get(symbol, ""))
                box.toggled.connect(lambda _on: self.changed.emit())
                self.boxes[symbol] = box
                grid.addWidget(box, r, c)

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
            box.setChecked(symbol in chosen)
