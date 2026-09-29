"""
xtalapp.dialogs.origin
======================
Cell > Move origin...: put the corner of the cell somewhere else.

What it is for is cutting a cluster out of a crystal.  Reduce to P1,
select the node, invert, delete -- and if a face of the cell runs
through the node, the block comes out in pieces on opposite sides of
the box.  *Centre the selection* moves the origin so that the middle
of whatever is selected is the middle of the cell, which is the
answer to that in one press.

The shift is the new origin in the old cell's fractional coordinates:
every atom moves by minus it and is folded back in, its bonds with it
(:meth:`xtal.core.structure.Structure.fold_sites`).  P1 only -- the
menu entry is greyed in a group, and says why.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from xtal.commands import cell as cell_commands
from xtalapp.widgets.tone import HINT, WARNING, set_tone

DECIMALS = 4


class OriginDialog(QDialog):
    """The new origin as a, b, c, or the middle of the selection."""

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Move Origin")
        self.document = document

        intro = QLabel(
            "The new origin, in fractions of a, b and c.  Every atom "
            "moves by minus this and is folded back into the cell; "
            "its bonds go with it.")
        intro.setWordWrap(True)
        set_tone(intro, HINT)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.axes = []
        for axis in "abc":
            spin = QDoubleSpinBox()
            spin.setRange(-1.0, 1.0)
            spin.setDecimals(DECIMALS)
            spin.setSingleStep(0.05)
            spin.valueChanged.connect(self._preview)
            form.addRow(f"{axis}:", spin)
            self.axes.append(spin)

        self.centre = QPushButton("Centre the selection")
        self.centre.setToolTip(
            "Put the middle of the selected atoms at the middle of the "
            "cell, gathered across the faces -- a cluster the cell "
            "cuts in two comes out whole")
        self.centre.clicked.connect(self.centre_selection)
        self.centre.setEnabled(bool(document.selection.atoms))

        self.preview = QLabel()
        self.preview.setWordWrap(True)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                        | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(self.centre)
        layout.addWidget(self.preview)
        layout.addWidget(self.buttons)
        self._preview()

    # -- values --------------------------------------------------------

    def shift(self) -> np.ndarray:
        return np.array([spin.value() for spin in self.axes])

    def set_shift(self, shift) -> None:
        for spin, value in zip(self.axes, shift, strict=True):
            spin.setValue(round(float(value), DECIMALS))

    def centre_selection(self) -> None:
        shift = self.document.selection_centring_shift()
        if shift is not None:
            self.set_shift(shift)

    def command(self):
        return cell_commands.ShiftOrigin(self.shift())

    # -- preview -------------------------------------------------------

    def _preview(self, *_args) -> None:
        ok_button = self.buttons.button(QDialogButtonBox.Ok)
        if not np.any(self.shift()):
            # An undo step that changes nothing would make Ctrl+Z lie.
            self.preview.setText("The origin is where it was.")
            set_tone(self.preview, HINT)
            ok_button.setEnabled(False)
            return
        _new, report = self.command().preview(self.document.structure)
        self.preview.setText(report.message)
        set_tone(self.preview, HINT if report.ok else WARNING)
        ok_button.setEnabled(report.ok)

    # -- running -------------------------------------------------------

    @classmethod
    def ask(cls, document, parent=None):
        dialog = cls(document, parent)
        if dialog.exec() != QDialog.Accepted:
            return None
        return document.operate(dialog.command())
