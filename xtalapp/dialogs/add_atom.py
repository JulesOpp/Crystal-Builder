"""
xtalapp.dialogs.add_atom
========================
Add an atom by typing its coordinates.

The fractional/cartesian switch is not a convenience: fractional
coordinates are what a structure stores, cartesian is what a chemist
measures, and a dialog that offers only one of them forces arithmetic
on the user.  Switching converts what is already typed rather than
clearing it.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from xtal.core import elements as el
from xtalapp.docks.inspector import COMMON_ELEMENTS
from xtalapp.widgets.periodic_table import PeriodicTableButton


class AddAtomDialog(QDialog):
    """Element, position, occupancy, label."""

    def __init__(self, lattice, parent=None, element="C", frac=None):
        super().__init__(parent)
        self.setWindowTitle("Add atom")
        self.lattice = lattice
        self._updating = False

        self.element = QComboBox()
        self.element.setEditable(True)
        self.element.addItems(COMMON_ELEMENTS)
        self.element.setCurrentText(element)

        # The combo is faster for carbon and useless for the element
        # somebody knows by position; the button is the other half.
        # It writes into the combo rather than replacing it, so the
        # dialog still has one field holding the answer.
        self.table = PeriodicTableButton(
            self, current=self.element.currentText)
        self.table.chosen.connect(self.element.setCurrentText)

        self.units = QComboBox()
        self.units.addItems(["fractional", "cartesian (A)"])
        self.units.currentIndexChanged.connect(self._convert)

        self.coords = []
        for _axis in range(3):
            spin = QDoubleSpinBox()
            spin.setRange(-999.0, 999.0)
            spin.setDecimals(5)
            spin.setSingleStep(0.05)
            self.coords.append(spin)
        for spin, value in zip(self.coords,
                               frac if frac is not None else
                               (0.5, 0.5, 0.5), strict=True):
            spin.setValue(float(value))

        self.occupancy = QDoubleSpinBox()
        self.occupancy.setRange(0.001, 1.0)
        self.occupancy.setDecimals(4)
        self.occupancy.setValue(1.0)

        self.label = QLineEdit()
        self.label.setPlaceholderText("auto")

        self.warning = QLabel()
        self.warning.setStyleSheet("color: #8a5a00;")
        self.warning.setWordWrap(True)
        self.warning.hide()

        position = QHBoxLayout()
        for spin in self.coords:
            position.addWidget(spin)

        chooser = QHBoxLayout()
        chooser.addWidget(self.element, 1)
        chooser.addWidget(self.table)

        form = QFormLayout()
        form.addRow("Element", chooser)
        form.addRow("Coordinates", self.units)
        form.addRow("Position", position)
        form.addRow("Occupancy", self.occupancy)
        form.addRow("Label", self.label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                   | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.warning)
        layout.addWidget(buttons)

    # -- values --------------------------------------------------------

    def _values(self) -> np.ndarray:
        return np.array([spin.value() for spin in self.coords])

    def _convert(self) -> None:
        """Keep the point the same when the units change."""
        if self._updating:
            return
        self._updating = True
        values = self._values()
        if self.units.currentIndex() == 1:          # to cartesian
            converted = self.lattice.to_cart(values)
        else:                                       # back to fractional
            converted = self.lattice.to_frac(values)
        for spin, value in zip(self.coords, converted, strict=True):
            spin.setValue(float(value))
        self._updating = False

    def fractional(self) -> np.ndarray:
        values = self._values()
        if self.units.currentIndex() == 1:
            return self.lattice.to_frac(values)
        return values

    def _accept(self) -> None:
        if el.canonical_symbol(self.element.currentText()) is None:
            self.warning.setText(
                f"{self.element.currentText().strip()!r} is not an "
                f"element symbol.")
            self.warning.show()
            return
        self.accept()

    def result_values(self) -> dict:
        return {
            "element": el.canonical_symbol(self.element.currentText()),
            "frac": self.fractional(),
            "occupancy": self.occupancy.value(),
            "label": self.label.text().strip(),
        }

    @classmethod
    def ask(cls, lattice, parent=None, element="C") -> dict | None:
        dialog = cls(lattice, parent, element)
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.result_values()
