"""
xtalapp.dialogs.slab
====================
A slab along a lattice plane, with vacuum above it.

Four numbers and a fifth for the termination.  The plane is a Miller
index of the cell as it is -- the conventional one for a centred group,
which is what a crystallographer means by (111) of rock salt -- and a
layer is one spacing of that plane.  The line under the form says what
will come out before it comes out: how thick, how many atoms, and how
many bonds the two surfaces cut.  The work is
:mod:`xtal.core.slab`; this only asks.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from xtal.commands import cell as cell_commands
from xtalapp.dialogs.answered import answered
from xtalapp.widgets.tone import WARNING, set_tone

#: The largest Miller index offered.  Beyond it the surface cell is
#: a long thin ribbon nobody meant.
MAX_INDEX = 9
MAX_LAYERS = 50
MAX_VACUUM = 500.0
DEFAULT_VACUUM = 15.0


class SlabDialog(QDialog):
    """(hkl), layers, vacuum above, and where the cut falls."""

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Slab")
        self.document = document

        form = QFormLayout()
        row = QHBoxLayout()
        self.indices = []
        for name, value in zip("hkl", (0, 0, 1), strict=True):
            spin = QSpinBox()
            spin.setRange(-MAX_INDEX, MAX_INDEX)
            spin.setValue(value)
            spin.setPrefix(f"{name} ")
            spin.valueChanged.connect(self._preview)
            row.addWidget(spin)
            self.indices.append(spin)
        form.addRow("Plane (hkl)", row)

        self.layers = QSpinBox()
        self.layers.setRange(1, MAX_LAYERS)
        self.layers.setValue(3)
        self.layers.setToolTip("How many spacings of the plane thick")
        self.layers.valueChanged.connect(self._preview)
        form.addRow("Layers", self.layers)

        self.vacuum = QDoubleSpinBox()
        self.vacuum.setRange(0.0, MAX_VACUUM)
        self.vacuum.setDecimals(1)
        self.vacuum.setValue(DEFAULT_VACUUM)
        self.vacuum.setSuffix(" A")
        self.vacuum.setToolTip("Empty space above the slab, along the "
                               "plane normal")
        self.vacuum.valueChanged.connect(self._preview)
        form.addRow("Vacuum above", self.vacuum)

        self.shift = QDoubleSpinBox()
        self.shift.setRange(0.0, 0.99)
        self.shift.setDecimals(2)
        self.shift.setSingleStep(0.05)
        self.shift.setToolTip(
            "Moves the cut up the normal by this fraction of one "
            "layer -- which atoms end up on the surface")
        self.shift.valueChanged.connect(self._preview)
        form.addRow("Termination", self.shift)

        self.preview = QLabel()
        self.preview.setWordWrap(True)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                        | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.preview)
        layout.addWidget(self.buttons)
        self._preview()

    def hkl(self) -> tuple[int, int, int]:
        return tuple(spin.value() for spin in self.indices)

    def command(self):
        return cell_commands.MakeSlab(self.hkl(), self.layers.value(),
                                      self.vacuum.value(),
                                      self.shift.value())

    def _preview(self, *_args) -> None:
        ok_button = self.buttons.button(QDialogButtonBox.Ok)
        try:
            _new, report = self.command().preview(
                self.document.structure)
        except ValueError as exc:
            self.preview.setText(str(exc))
            set_tone(self.preview, WARNING)
            ok_button.setEnabled(False)
            return
        self.preview.setText(report.message)
        self.preview.setStyleSheet("")
        ok_button.setEnabled(True)

    @classmethod
    def ask(cls, document, parent=None):
        with answered(cls(document, parent)) as dialog:
            if dialog.exec() != QDialog.Accepted:
                return None
            return document.operate(dialog.command())
