"""
xtalapp.dialogs.prepare
=======================
Preparing a deposited structure for simulation: what is wrong with it,
the steps that would fix it, and what each step would do -- all before
anything is done.

Every step is offered and ticked, because a step with nothing to do
says so rather than doing something: "no solvent molecules" is an
answer worth seeing.  What cannot be seen from the file as deposited --
the trimers are not complete, the solvent is not a molecule -- until
the disorder is ordered is why the preview runs the whole chain rather
than asking each step on its own.  It follows the boxes live; MIL-101,
the largest shipped structure, prepares in under a second.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
)

from xtal.core import prepare


class PrepareDialog(QDialog):
    """The diagnosis, a box per step, and each step's sentence."""

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Prepare for simulation")
        self.document = document

        self.found = QLabel(document.diagnose_preparation().text())
        self.found.setWordWrap(True)

        self.boxes = {}
        layout = QVBoxLayout(self)
        layout.addWidget(self.found)
        for step in prepare.STEPS:
            box = QCheckBox(prepare.LABELS[step])
            box.setChecked(True)
            box.toggled.connect(self._preview)
            self.boxes[step] = box
            layout.addWidget(box)

        self.headline = QLabel("")
        self.headline.setWordWrap(True)
        font = self.headline.font()
        font.setBold(True)
        self.headline.setFont(font)

        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMinimumHeight(150)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                        | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Prepare")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout.addWidget(self.headline)
        layout.addWidget(self.detail)
        layout.addWidget(self.buttons)
        self.resize(600, 480)
        self._preview()

    def steps(self) -> list[str]:
        return [step for step, box in self.boxes.items()
                if box.isChecked()]

    def _preview(self, *_args) -> None:
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            _out, report = self.document.preview_preparation(
                self.steps())
        finally:
            QApplication.restoreOverrideCursor()
        self.headline.setText(report.message)
        chosen = [s for s in prepare.STEPS if s in self.steps()]
        self.detail.setPlainText("\n\n".join(
            f"{prepare.LABELS[step]}: {message}"
            for step, message in zip(chosen, report.warnings,
                                     strict=False)))
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(report.ok)

    @classmethod
    def ask(cls, document, parent=None):
        """The report of the preparation, or ``None`` if cancelled."""
        dialog = cls(document, parent)
        if dialog.exec() != QDialog.Accepted:
            return None
        return document.prepare_for_simulation(dialog.steps())
