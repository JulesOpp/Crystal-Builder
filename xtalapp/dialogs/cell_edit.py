"""
xtalapp.dialogs.cell_edit
=========================
Editing the cell parameters -- and answering the question that makes
the edit meaningful.

Stretching *a* from 5 to 6 Angstrom can mean two opposite things.
Keeping the **fractional** coordinates drags every atom along with the
cell: the crystal is scaled, bonds stretch, this is a strain.  Keeping
the **cartesian** coordinates leaves the atoms exactly where they are
in space and rescales the fractions: the crystal is unchanged, the box
around it is not, this is how vacuum gets added.

There is no sensible default, so the dialog asks, and says what each
choice will do to the density before the choice is made.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGridLayout,
    QLabel,
    QRadioButton,
    QVBoxLayout,
)

from xtal.core.lattice import Lattice

LENGTHS = ["a", "b", "c"]
ANGLES = ["alpha", "beta", "gamma"]

KEEPS = [
    ("fractional", "Keep fractional coordinates",
     "The atoms move with the cell: the structure is strained."),
    ("cartesian", "Keep cartesian coordinates",
     "The atoms stay where they are; only the box changes."),
]


class CellEditDialog(QDialog):
    """The six cell parameters, and what to hold fixed."""

    def __init__(self, structure, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit unit cell")
        self.structure = structure

        a, b, c, alpha, beta, gamma = structure.lattice.parameters
        self.lengths = []
        self.angles = []
        grid = QGridLayout()
        for column, (name, value) in enumerate(
                zip(LENGTHS, (a, b, c), strict=True)):
            spin = QDoubleSpinBox()
            spin.setRange(0.1, 1000.0)
            spin.setDecimals(5)
            spin.setSingleStep(0.1)
            spin.setValue(float(value))
            spin.setSuffix(" A")
            spin.valueChanged.connect(self._preview)
            grid.addWidget(QLabel(name), 0, column)
            grid.addWidget(spin, 1, column)
            self.lengths.append(spin)
        for column, (name, value) in enumerate(
                zip(ANGLES, (alpha, beta, gamma), strict=True)):
            spin = QDoubleSpinBox()
            spin.setRange(1.0, 179.0)
            spin.setDecimals(4)
            spin.setSingleStep(1.0)
            spin.setValue(float(value))
            spin.setSuffix(" deg")
            spin.valueChanged.connect(self._preview)
            grid.addWidget(QLabel(name), 2, column)
            grid.addWidget(spin, 3, column)
            self.angles.append(spin)

        self.keeps = []
        keep_box = QVBoxLayout()
        for index, (_name, label, tip) in enumerate(KEEPS):
            button = QRadioButton(label)
            button.setToolTip(tip)
            button.setChecked(index == 0)
            button.toggled.connect(self._preview)
            self.keeps.append(button)
            keep_box.addWidget(button)

        self.preview = QLabel()
        self.preview.setWordWrap(True)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                        | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        reset = self.buttons.addButton(QDialogButtonBox.Reset)
        reset.clicked.connect(self.reset)

        layout = QVBoxLayout(self)
        layout.addLayout(grid)
        layout.addLayout(keep_box)
        layout.addWidget(self.preview)
        layout.addWidget(self.buttons)
        self._preview()

    # -- values --------------------------------------------------------

    def parameters(self) -> tuple[float, ...]:
        return tuple([s.value() for s in self.lengths]
                     + [s.value() for s in self.angles])

    def lattice(self) -> Lattice | None:
        try:
            return Lattice.from_parameters(*self.parameters())
        except ValueError:
            return None

    def keep(self) -> str:
        for button, (name, _label, _tip) in zip(self.keeps, KEEPS,
                                                strict=True):
            if button.isChecked():
                return name
        return "fractional"

    def reset(self) -> None:
        original = self.structure.lattice.parameters
        for spin, value in zip(self.lengths + self.angles, original,
                               strict=True):
            spin.blockSignals(True)
            spin.setValue(float(value))
            spin.blockSignals(False)
        self._preview()

    # -- preview -------------------------------------------------------

    def _preview(self, *_args) -> None:
        ok_button = self.buttons.button(QDialogButtonBox.Ok)
        lattice = self.lattice()
        if lattice is None or lattice.volume <= 0:
            self.preview.setText(
                "Those angles do not close a cell.")
            self.preview.setStyleSheet("color: #8a5a00;")
            ok_button.setEnabled(False)
            return
        ok_button.setEnabled(True)
        self.preview.setStyleSheet("")

        old = self.structure.lattice.volume
        ratio = lattice.volume / old if old else 1.0
        note = ("the atoms move with the cell"
                if self.keep() == "fractional"
                else "the atoms stay where they are")
        self.preview.setText(
            f"V = {lattice.volume:.3f} A^3  "
            f"({ratio:.4g}x the current {old:.3f});  density scales by "
            f"{1 / ratio:.4g}x -- {note}.")

    # -- running -------------------------------------------------------

    @classmethod
    def ask(cls, document, parent=None):
        dialog = cls(document.structure, parent)
        if dialog.exec() != QDialog.Accepted:
            return None
        lattice = dialog.lattice()
        if lattice is None:
            return None
        return document.set_lattice(lattice, dialog.keep())
