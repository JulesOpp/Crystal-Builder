"""
xtalapp.dialogs.supercell
=========================
Building a bigger cell -- or a differently shaped one.

Two tabs, because these are two different operations that happen to
share a result type.  **Multiples** is the everyday one: 2x2x2, more
atoms, same shape.  **Transformation** takes a general integer matrix
P, which is the only way to express the cells crystallographers
actually want and cannot write as three multiples -- a primitive cell
out of a centred one (|det P| = 1), a root-2 by root-2 surface cell,
the C-centred setting of a monoclinic structure.

Both land in P1: which sites are independent is a question about a
particular cell, and it stops meaning anything the moment the cell
changes.  The count under each tab says what will come out before it
comes out, because "2x2x2 of a 648-atom framework" is a number worth
seeing first.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from xtal.commands import cell as cell_commands
from xtalapp.widgets.tone import WARNING, set_tone

MAX_MULTIPLE = 20
# A general P is allowed to be this large in any one entry; beyond it
# the cell is almost certainly a typo rather than a plan.
MAX_ENTRY = 12


class SupercellDialog(QDialog):
    """na x nb x nc, or a general integer transformation."""

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Supercell")
        self.document = document

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_multiples(), "Multiples")
        self.tabs.addTab(self._build_matrix(), "Transformation")
        self.tabs.currentChanged.connect(self._preview)

        self.preview = QLabel()
        self.preview.setWordWrap(True)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                        | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addWidget(self.preview)
        layout.addWidget(self.buttons)
        self._preview()

    # -- construction --------------------------------------------------

    def _build_multiples(self) -> QWidget:
        page = QWidget()
        grid = QGridLayout(page)
        self.counts = []
        for column, axis in enumerate("abc"):
            spin = QSpinBox()
            spin.setRange(1, MAX_MULTIPLE)
            spin.setValue(1)
            spin.setPrefix(f"{axis} x ")
            spin.valueChanged.connect(self._preview)
            grid.addWidget(spin, 0, column)
            self.counts.append(spin)
        return page

    def _build_matrix(self) -> QWidget:
        page = QWidget()
        grid = QGridLayout(page)
        grid.addWidget(QLabel(
            "New a, b, c as integer combinations of the old ones"),
            0, 0, 1, 3)
        self.matrix = []
        for row in range(3):
            entries = []
            for column in range(3):
                spin = QSpinBox()
                spin.setRange(-MAX_ENTRY, MAX_ENTRY)
                spin.setValue(1 if row == column else 0)
                spin.valueChanged.connect(self._preview)
                grid.addWidget(spin, row + 1, column)
                entries.append(spin)
            self.matrix.append(entries)
        return page

    # -- values --------------------------------------------------------

    def multiples(self) -> tuple[int, int, int]:
        return tuple(spin.value() for spin in self.counts)

    def p_matrix(self) -> np.ndarray:
        return np.array([[spin.value() for spin in row]
                         for row in self.matrix], dtype=float)

    def command(self):
        if self.tabs.currentIndex() == 0:
            return cell_commands.Supercell(*self.multiples())
        return cell_commands.TransformCell(self.p_matrix())

    # -- preview -------------------------------------------------------

    def _preview(self, *_args) -> None:
        ok_button = self.buttons.button(QDialogButtonBox.Ok)
        try:
            _new, report = self.command().preview(
                self.document.structure)
        except (ValueError, np.linalg.LinAlgError) as exc:
            self.preview.setText(str(exc))
            set_tone(self.preview, WARNING)
            ok_button.setEnabled(False)
            return
        self.preview.setText(report.message)
        self.preview.setStyleSheet("")
        ok_button.setEnabled(True)

    # -- running -------------------------------------------------------

    @classmethod
    def ask(cls, document, parent=None):
        dialog = cls(document, parent)
        if dialog.exec() != QDialog.Accepted:
            return None
        return document.operate(dialog.command())
