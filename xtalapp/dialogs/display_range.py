"""
xtalapp.dialogs.display_range
=============================
How much of the crystal to draw.

The toolbar's three spinboxes cover the common case -- whole cells from
the origin -- and this dialog covers the rest: a range that starts
below zero so the origin corner is complete, a slab one cell thick in
*c* and three wide in *a*, a half-cell to look inside a framework.

Ranges are fractional and **inclusive at both ends**, which is what
makes a picture look right rather than gnawed: with a range of (0, 1)
the atom at x = 0 is drawn again at x = 1, so the cell closes.

The boundary option is the other half of the same question.  A bond is
between an atom and a translation of another atom, and at the edge of
the range one of those two is outside the picture.  There are three
answers and each is right for a different picture: drop the bond,
draw the partner as well -- the only way a coordination polyhedron at
the cell edge stays whole -- or draw the near half and nothing on the
end of it, which is what a surface bond has always been drawn as.

Nothing here touches the structure: this is view state, so it never
lands on the undo stack and never marks the document modified.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from xtalapp.widgets.tone import WARNING, set_tone

AXES = ["a", "b", "c"]

BOUNDARIES = [
    ("in_range", "Draw only atoms inside the range",
     "Every atom on the surface of the picture is then drawn "
     "under-coordinated"),
    ("bonded", "Also draw the atoms just outside that complete a bond",
     "Keeps coordination polyhedra whole at the edge of the picture, "
     "at the cost of a halo of extra atoms around the box"),
    ("half", "Draw the near half of the bond, and nothing on the end",
     "The usual notation for a bond that leaves the picture, and the "
     "only one that draws a six-coordinate net vertex with six "
     "edges"),
]


class DisplayRangeDialog(QDialog):
    """Fractional display range and boundary handling."""

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Display range")
        self.document = document

        grid = QGridLayout()
        grid.addWidget(QLabel("from"), 0, 1)
        grid.addWidget(QLabel("to"), 0, 2)
        self.los, self.his = [], []
        for row, (axis, (lo, hi)) in enumerate(
                zip(AXES, document.view.ranges, strict=True), start=1):
            grid.addWidget(QLabel(axis), row, 0)
            for values, value, column in ((self.los, lo, 1),
                                          (self.his, hi, 2)):
                spin = QDoubleSpinBox()
                spin.setRange(-20.0, 20.0)
                spin.setDecimals(3)
                spin.setSingleStep(0.25)
                spin.setValue(float(value))
                spin.valueChanged.connect(self._preview)
                grid.addWidget(spin, row, column)
                values.append(spin)

        # Radio buttons and not a combo: the three are one question
        # with three answers and the trade-off between them is in the
        # wording, which a collapsed combo hides.
        box = QGroupBox("A bond that leaves the range")
        choices = QVBoxLayout(box)
        self.boundaries = {}
        for name, label, tip in BOUNDARIES:
            button = QRadioButton(label)
            button.setToolTip(tip)
            button.setChecked(document.view.boundary == name)
            choices.addWidget(button)
            self.boundaries[name] = button
        if not any(b.isChecked() for b in self.boundaries.values()):
            self.boundaries["in_range"].setChecked(True)

        self.preview = QLabel()
        self.preview.setWordWrap(True)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                        | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        whole = QPushButton("One whole cell")
        whole.clicked.connect(self.reset)
        self.buttons.addButton(whole, QDialogButtonBox.ResetRole)

        layout = QVBoxLayout(self)
        layout.addLayout(grid)
        layout.addWidget(box)
        layout.addWidget(self.preview)
        layout.addWidget(self.buttons)
        self._preview()

    # -- values --------------------------------------------------------

    def ranges(self) -> tuple[tuple[float, float], ...]:
        return tuple((lo.value(), hi.value())
                     for lo, hi in zip(self.los, self.his,
                                       strict=True))

    def boundary(self) -> str:
        for name, button in self.boundaries.items():
            if button.isChecked():
                return name
        return "in_range"                           # pragma: no cover

    def reset(self) -> None:
        for lo, hi in zip(self.los, self.his, strict=True):
            for spin, value in ((lo, 0.0), (hi, 1.0)):
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)
        self._preview()

    # -- preview -------------------------------------------------------

    def _preview(self, *_args) -> None:
        ranges = self.ranges()
        ok_button = self.buttons.button(QDialogButtonBox.Ok)
        empty = [axis for axis, (lo, hi) in zip(AXES, ranges,
                                                strict=True)
                 if hi < lo]
        if empty:
            self.preview.setText(
                f"the {', '.join(empty)} range ends before it starts")
            set_tone(self.preview, WARNING)
            ok_button.setEnabled(False)
            return
        ok_button.setEnabled(True)
        self.preview.setStyleSheet("")
        spans = " x ".join(f"{hi - lo:g}" for lo, hi in ranges)
        atoms = self.document.cell.n_atoms
        volume = 1.0
        for lo, hi in ranges:
            volume *= max(hi - lo, 0.0)
        self.preview.setText(
            f"{spans} cells -- roughly {round(atoms * volume)} atoms "
            f"of the {atoms} in one cell, plus the closing faces.")

    # -- running -------------------------------------------------------

    @classmethod
    def ask(cls, document, parent=None) -> bool:
        """Apply the range to the document's view; returns whether
        anything was applied."""
        dialog = cls(document, parent)
        if dialog.exec() != QDialog.Accepted:
            return False
        a, b, c = dialog.ranges()
        document.update_view(range_a=a, range_b=b, range_c=c,
                             boundary=dialog.boundary())
        return True
