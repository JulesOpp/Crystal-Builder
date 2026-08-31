"""
xtalapp.dialogs.add_hydrogens
=============================
Putting the hydrogens back, with the count and the assumptions first.

The dialog exists for one reason: this is an edit that adds atoms the
user cannot see themselves placing, and the two questions they will
have -- *how many* and *where did they come from* -- have to be
answered before the button is pressed rather than after.  So the plan
is computed live, the orbit count is what is shown ("12 hydrogens on 2
sites", not "2"), and every assumption behind it is listed underneath,
including the ones that are genuinely undetermined and the atoms that
were deliberately left alone.

The one choice offered is the bond length.  Neutron and X-ray hydrogen
positions differ by about 0.1 A for a real reason -- X-rays see the
bonding electrons and not the nucleus -- and the short one is offered
rather than defaulted to, because the long one is what the force field
was parameterised against.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
)

from xtal.ff.hydrogens import X_RAY_SHORTENING


class AddHydrogensDialog(QDialog):
    """The plan, then the button that runs it."""

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add hydrogens")
        self.document = document

        self.xray = QCheckBox(
            f"X-ray bond lengths ({X_RAY_SHORTENING:.2f} A shorter)")
        self.xray.setToolTip(
            "Hydrogens refined against X-ray data sit about 0.1 A "
            "closer to their neighbour than the nucleus really is, "
            "because what was fitted is the bonding electron density. "
            "Leave this off to place them where the force field "
            "expects them.")
        self.xray.toggled.connect(self._preview)

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
        self.buttons.button(QDialogButtonBox.Ok).setText("Add")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.xray)
        layout.addWidget(self.headline)
        layout.addWidget(self.detail)
        layout.addWidget(self.buttons)
        self.resize(520, 380)
        self._preview()

    # -- the plan ------------------------------------------------------

    def _preview(self, *_args) -> None:
        ok = self.buttons.button(QDialogButtonBox.Ok)
        try:
            plan = self.document.plan_hydrogens(
                self.xray.isChecked())
        except Exception as exc:                    # noqa: BLE001
            # A structure the force field cannot type at all -- an
            # element outside UFF -- has no answer here, and saying so
            # is better than an empty dialog.
            self.headline.setText("cannot work out where hydrogens "
                                  "would go")
            self.detail.setPlainText(str(exc))
            ok.setEnabled(False)
            return
        self.headline.setText(plan.message())
        self.detail.setPlainText(self._detail(plan))
        ok.setEnabled(bool(plan))

    @staticmethod
    def _detail(plan) -> str:
        lines = list(plan.notes)
        if plan.skipped:
            if lines:
                lines.append("")
            lines.append("left alone:")
            lines.extend(f"  {s}" for s in plan.skipped)
        if not lines:
            lines.append("Every main-group atom already has the "
                         "neighbours its valence calls for.")
        return "\n".join(lines)

    # -- running -------------------------------------------------------

    @classmethod
    def ask(cls, document, parent=None) -> str:
        dialog = cls(document, parent)
        if dialog.exec() != QDialog.Accepted:
            return ""
        return document.add_hydrogens(dialog.xray.isChecked())
