"""
xtalapp.dialogs.add_centroid
============================
What to put at the middle of the selected atoms.

Two answers, and they are different kinds of thing rather than two
values of one field, which is why they are radio buttons and not a
combo box with ``X`` at the top of it.  A **dummy atom** is a position
somebody wants named -- the centre of a ring, the vertex of a net --
and bonds to nothing; an **element** is chemistry, and building a
bridging atom into the middle of a ring is a different act with the
same gesture.

The dummy is the default because a centroid usually is one, and
because it is the answer that cannot quietly change what the crystal
means.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QVBoxLayout,
)

from xtal.core import elements as el
from xtalapp.docks.inspector import COMMON_ELEMENTS

DUMMY = "X"


class AddCentroidDialog(QDialog):
    """A dummy atom, or an element, at the centre of the selection."""

    def __init__(self, count: int, parent=None, element="C"):
        super().__init__(parent)
        self.setWindowTitle("Add centroid")

        self.dummy = QRadioButton("Dummy atom (X)")
        self.dummy.setChecked(True)
        self.dummy.setToolTip(
            "A marker rather than chemistry: it bonds to nothing, and "
            "net edges and measurements take it like any other atom")
        self.real = QRadioButton("Element")
        group = QButtonGroup(self)
        group.addButton(self.dummy)
        group.addButton(self.real)

        self.element = QComboBox()
        self.element.setEditable(True)
        self.element.addItems(COMMON_ELEMENTS)
        self.element.setCurrentText(element)
        self.element.setEnabled(False)
        self.real.toggled.connect(self.element.setEnabled)

        self.label = QLineEdit()
        self.label.setPlaceholderText("auto")

        self.warning = QLabel()
        self.warning.setStyleSheet("color: #8a5a00;")
        self.warning.setWordWrap(True)
        self.warning.hide()

        choice = QHBoxLayout()
        choice.addWidget(self.real)
        choice.addWidget(self.element)

        form = QFormLayout()
        form.addRow("Place", self.dummy)
        form.addRow("", choice)
        form.addRow("Label", self.label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                   | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            f"At the centre of the {count} selected atoms."))
        layout.addLayout(form)
        layout.addWidget(self.warning)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        if self.dummy.isChecked():
            self.accept()
            return
        if el.canonical_symbol(self.element.currentText()) is None:
            self.warning.setText(
                f"{self.element.currentText().strip()!r} is not an "
                f"element symbol.")
            self.warning.show()
            return
        self.accept()

    def result_values(self) -> dict:
        element = (DUMMY if self.dummy.isChecked()
                   else el.canonical_symbol(self.element.currentText()))
        return {"element": element, "label": self.label.text().strip()}

    @classmethod
    def ask(cls, count: int, parent=None, element="C") -> dict | None:
        dialog = cls(count, parent, element)
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.result_values()
