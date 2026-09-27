"""
xtalapp.refine.cell
===================
A cell as the space group allows it: the free numbers to type, the
rest derived, and a switch beside each free one to refine or hold it.

A text box of six numbers took ``a = 4.59, b = 4.60`` for a tetragonal
cell, and RietX's ties then quietly made b equal a -- the fit ran on a
cell nobody typed.  Here a cubic group offers one length, a monoclinic
one three lengths and its unique angle, and the rest follow; what the
step is handed is the six numbers and the list held, which is what
``xtal run`` takes as text.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QLabel,
)

from xtal.powder.cell import NAMES, complete, constraints, system_of
from xtal.powder.pawley import parse_cell, parse_hold
from xtalapp.widgets.tone import HINT, set_tone

__all__ = ["CellBox"]

_SHOWN = {"a": "a", "b": "b", "c": "c", "alpha": "α", "beta": "β",
          "gamma": "γ"}


class CellBox(QGroupBox):
    """Six numbers, the free ones editable and switchable.

    ``editable=False`` shows a cell read from a structure -- Rietveld
    refines the cell the atoms are in, and the numbers are not the
    form's to change -- with the switches still live.
    """

    changed = Signal()

    def __init__(self, title: str = "Cell", editable: bool = True,
                 parent=None):
        super().__init__(title, parent)
        self.editable = editable
        self.space_group = ""
        self._rules = constraints("")
        grid = QGridLayout(self)
        self.system = QLabel("")
        set_tone(self.system, HINT)
        grid.addWidget(self.system, 0, 0, 1, 4)
        self.spins: dict[str, QDoubleSpinBox] = {}
        self.boxes: dict[str, QCheckBox] = {}
        self.notes: dict[str, QLabel] = {}
        for row, name in enumerate(NAMES, start=1):
            angle = row > 3
            grid.addWidget(QLabel(_SHOWN[name]), row, 0)
            spin = QDoubleSpinBox()
            spin.setDecimals(3 if angle else 5)
            if angle:
                spin.setRange(10.0, 170.0)
            else:
                spin.setRange(0.5, 1000.0)
            spin.setSuffix(" °" if angle else " Å")
            spin.setValue(90.0 if angle else 10.0)
            spin.setKeyboardTracking(False)
            spin.valueChanged.connect(self._on_edited)
            self.spins[name] = spin
            grid.addWidget(spin, row, 1)
            box = QCheckBox("Refine")
            box.setChecked(True)
            box.setToolTip(f"Refine {_SHOWN[name]}, or hold it at the "
                           f"value given")
            box.toggled.connect(lambda _on: self.changed.emit())
            self.boxes[name] = box
            grid.addWidget(box, row, 2)
            note = QLabel("")
            note.setTextInteractionFlags(Qt.TextSelectableByMouse)
            set_tone(note, HINT)
            self.notes[name] = note
            grid.addWidget(note, row, 3)
        grid.setColumnStretch(3, 1)
        self.set_space_group("")

    # -- the group -----------------------------------------------------

    def set_space_group(self, text) -> None:
        """Offer the numbers this group leaves free, and derive the
        rest from them.  A group nobody knows offers all six."""
        self.space_group = str(text or "").strip()
        try:
            self._rules = constraints(self.space_group)
            system = system_of(self.space_group)
        except (ValueError, RuntimeError):
            self._rules, system = constraints(""), ""
        free = [n for n, r in zip(NAMES, self._rules, strict=True)
                if r is None]
        self.system.setText(
            f"{system}: {', '.join(_SHOWN[n] for n in free)}" if system
            else "no space group: all six numbers")
        for name, rule in zip(NAMES, self._rules, strict=True):
            self.spins[name].setEnabled(rule is None and self.editable)
            self.spins[name].setReadOnly(not self.editable)
            self.boxes[name].setVisible(rule is None)
            if rule is not None:
                self.notes[name].setText(
                    f"= {_SHOWN[rule]}" if isinstance(rule, str)
                    else "fixed by the group")
            elif self.notes[name].text().startswith(("=", "fixed")):
                self.notes[name].setText("")
        self._derive()
        self.changed.emit()

    def _on_edited(self, _value=None) -> None:
        self._derive()
        self.changed.emit()

    def _derive(self) -> None:
        numbers = complete({n: s.value() for n, s in self.spins.items()},
                           self.space_group)
        for name, value in zip(NAMES, numbers, strict=True):
            spin = self.spins[name]
            if abs(spin.value() - value) > 1e-9:
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)

    # -- values --------------------------------------------------------

    def numbers(self) -> tuple[float, ...]:
        return complete({n: s.value() for n, s in self.spins.items()},
                        self.space_group)

    def value(self) -> str:
        """The six numbers as the step's ``cell`` text."""
        a, b, c, alpha, beta, gamma = self.numbers()
        return (f"{a:.5f} {b:.5f} {c:.5f} {alpha:.3f} {beta:.3f} "
                f"{gamma:.3f}")

    def set_value(self, cell) -> None:
        """Six numbers, or text :func:`~xtal.powder.pawley.parse_cell`
        reads.  The free ones are taken; the group derives the rest."""
        if isinstance(cell, str):
            cell = parse_cell(cell)
        for name, value in zip(NAMES, cell, strict=True):
            spin = self.spins[name]
            spin.blockSignals(True)
            spin.setValue(float(value))
            spin.blockSignals(False)
        self._derive()
        self.changed.emit()

    def free(self) -> tuple[str, ...]:
        return tuple(n for n, r in zip(NAMES, self._rules, strict=True)
                     if r is None)

    def hold(self) -> str:
        """The free numbers switched off, as the step's ``hold``."""
        return ", ".join(n for n in self.free()
                         if not self.boxes[n].isChecked())

    def set_hold(self, text) -> None:
        held = set(parse_hold(text))
        for name, box in self.boxes.items():
            box.setChecked(name not in held)

    def set_refined(self, notes: dict) -> None:
        """What a fit made of each free number, beside its switch."""
        for name in self.free():
            self.notes[name].setText(notes.get(name, ""))
