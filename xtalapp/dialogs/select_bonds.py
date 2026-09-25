"""
xtalapp.dialogs.select_bonds
============================
Which two elements a bond selection joins.

Only the elements the structure has are offered: a pair that cannot
occur is a question with one answer.  The count beside the choice is
the one the selection will have, so an empty pair is seen before OK
rather than reported after it -- the usual reason for one is bonds
that were never perceived, and Recalculate Bonds is the user's to
press, not this dialog's.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)

from xtalapp.widgets.tone import HINT, set_tone

ANY = "Any element"


class SelectBondsDialog(QDialog):
    """Two elements, and how many bonds join them."""

    def __init__(self, elements, count: Callable, parent=None,
                 first: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("Select bonds")
        self._count = count
        elements = list(elements)

        self.first = QComboBox()
        self.first.addItems(elements)
        if first in elements:
            self.first.setCurrentText(first)
        self.second = QComboBox()
        self.second.addItems([*elements, ANY])
        self.second.setToolTip(
            f"{ANY} selects every bond the first element makes")

        self.found = QLabel()
        set_tone(self.found, HINT)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.addRow("Between", self.first)
        form.addRow("and", self.second)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                        | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.found)
        layout.addWidget(self.buttons)

        self.first.currentTextChanged.connect(self._recount)
        self.second.currentTextChanged.connect(self._recount)
        self._recount()

    def result_values(self) -> dict:
        second = self.second.currentText()
        return {"first": self.first.currentText(),
                "second": None if second == ANY else second}

    def _recount(self) -> None:
        values = self.result_values()
        n = self._count(values["first"], values["second"])
        self.found.setText(f"{n} bond(s) in the cell" if n
                           else "No bonds join these -- Recalculate "
                                "Bonds if they should")
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(n > 0)

    @classmethod
    def ask(cls, elements, count: Callable, parent=None,
            first: str | None = None) -> dict | None:
        dialog = cls(elements, count, parent, first)
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.result_values()
