"""
xtalapp.dialogs.draw_group
==========================
Draw a substituent: a SMILES string with one connection point.

Reached from *Draw...* in :mod:`xtalapp.dialogs.substitute`, as the
MOF builder's *Draw...* is reached from a slot
(:mod:`xtalapp.dialogs.draw_block`), and it is that dialog's box and
canvas (:func:`~xtalapp.dialogs.build_molecule.sketch_for`).  What it
checks is the one thing a group must be -- exactly one ``[*]``, the
atom the group hangs off -- by asking
:func:`xtal.build.substitute.group` for it, so the footer says what
Substitute would say.

What is drawn is saved into the workspace's ``groups/``
(:attr:`xtal.workspace.Workspace.groups`) and comes back in the
Substitute dialog's list from then on.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from xtal.build import BuildError, substitute
from xtalapp.dialogs import sketch
from xtalapp.dialogs.build_molecule import sketch_for
from xtalapp.widgets.tone import HINT, WARNING, set_tone

#: The pause after a keystroke before the group is embedded -- the
#: molecule builder's, for the molecule builder's reason.
QUIET_MS = 350


class DrawGroupDialog(QDialog):
    """A name, a SMILES box and a canvas."""

    def __init__(self, folder=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Draw a group")
        self.folder = Path(folder) if folder else None
        self.group = None
        self.drawn: tuple[str, str] | None = None
        self.path: Path | None = None

        self.name = QLineEdit(self)
        self.name.setPlaceholderText("Acetoxy")
        self.smiles = QLineEdit(self)
        self.smiles.setPlaceholderText("[*]OC(C)=O")
        self.smiles.setToolTip(
            "The group as SMILES, with [*] where it bonds to the atom "
            "whose hydrogen (or fluorine) it replaces -- exactly one")
        self.sketch = sketch_for(self, True)
        self.footer = QLabel(self)
        self.footer.setWordWrap(True)
        self.footer.setTextFormat(Qt.RichText)
        where = QLabel(f"saves into {self.folder}" if self.folder else
                       "there is no workspace to save it in: it is "
                       "used, and not kept", self)
        set_tone(where, HINT)
        where.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                   | QDialogButtonBox.Cancel)
        self.use_button = buttons.button(QDialogButtonBox.Ok)
        self.use_button.setText("Save and use" if self.folder
                                else "Use")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("Name", self.name)
        form.addRow("SMILES", self.smiles)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.sketch, 1)
        layout.addWidget(self.footer)
        layout.addWidget(where)
        layout.addWidget(buttons)
        self.resize(480, 520)

        self._quiet = QTimer(self)
        self._quiet.setSingleShot(True)
        self._quiet.setInterval(QUIET_MS)
        self._quiet.timeout.connect(self._rebuild)
        self.smiles.textChanged.connect(self._quiet.start)
        self.sketch.smilesChanged.connect(self._on_sketch)
        self._rebuild()

    def _on_sketch(self, text: str) -> None:
        """What was drawn, into the box, unless it is what the box
        already says -- which is what stops the two chasing each
        other."""
        if sketch.canonical(self.smiles.text()) != sketch.canonical(text):
            self.smiles.setText(text)

    def _rebuild(self) -> None:
        self._quiet.stop()
        text = self.smiles.text().strip()
        self.sketch.set_smiles(text)
        self.group = None
        if not text:
            self._say("", ok=False)
            return
        try:
            self.group = substitute.group(
                text, name=self.name.text().strip() or text)
        except (BuildError, ValueError) as exc:
            self._say(str(exc), ok=False)
            return
        self._say(f"<b>{self.group.formula}</b>, "
                  f"{self.group.n_atoms} atom(s), one connection point",
                  ok=True)

    def _say(self, message: str, ok: bool) -> None:
        self.footer.setText(message)
        set_tone(self.footer, HINT if ok else WARNING)
        self.use_button.setEnabled(ok)

    def accept(self) -> None:
        self._rebuild()
        if self.group is None:
            return
        name = self.name.text().strip() or self.smiles.text().strip()
        if self.folder is not None:
            try:
                self.path = substitute.save_group(
                    self.folder, name, self.smiles.text())
            except (ValueError, OSError) as exc:
                self._say(str(exc), ok=False)
                return
        self.drawn = (name, self.smiles.text().strip())
        super().accept()

    @classmethod
    def ask(cls, folder=None, parent=None):
        """``(name, smiles)`` of the group drawn, or ``None`` if it was
        cancelled."""
        dialog = cls(folder, parent)
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.drawn
