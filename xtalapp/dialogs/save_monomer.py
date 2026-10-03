"""
xtalapp.dialogs.save_monomer
============================
The open molecule, out to the workspace's monomers for the polymer
builder.

A monomer drawn here -- a molecule with two connection points, marked
with *Mark connection points* or, for a ladder, *Mark as one
connection point* -- is written as a block file with **its head
first**, because that is the order
:func:`xtal.polymer.monomer.from_block_file` reads.  Which ``X`` is
the head is asked, not guessed: head to tail is the chain's
regiochemistry, and the file has no other way to say it.

**The verdict is the reader's.**  What the footer says is
:func:`xtal.polymer.monomer.from_structure` -- the file written to a
scratch folder and read back -- so a monomer this dialog accepts is
one the polymer builder accepts, and a refusal is the sentence the
builder would have failed with.

It goes to :attr:`xtal.workspace.Workspace.monomers` and nowhere else,
which is what makes it appear in the polymer builder's library with
nothing further clicked.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from xtal.polymer import monomer
from xtal.workspace import safe_name
from xtalapp.dialogs.answered import answered
from xtalapp.widgets.tone import HINT, WARNING, set_tone


class SaveMonomerDialog(QDialog):
    """Name it, say which end is the head, and be told if it is not a
    monomer."""

    def __init__(self, structure, folder, parent=None):
        super().__init__(parent)
        self.structure = structure
        self.folder = Path(folder)
        self.setWindowTitle("Save as a monomer")

        self.name = QLineEdit(_suggested(structure), self)
        self.name.setPlaceholderText(
            "the file name, which is its name in the polymer builder")
        self.name.textChanged.connect(self._refresh)
        self.head = QComboBox(self)
        for point in monomer.connection_points(structure):
            self.head.addItem(monomer.point_name(structure, point),
                              point)
        self.head.setToolTip(
            "The end the unit before it joins.  The other is the tail, "
            "which the next unit joins -- head to tail is what a chain "
            "of them is.")
        self.head.currentIndexChanged.connect(self._refresh)

        self.summary = QLabel(self)
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.RichText)

        form = QFormLayout()
        form.addRow("Name", self.name)
        form.addRow("Head", self.head)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                   | QDialogButtonBox.Cancel)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)
        self.ok_button.setText("Save")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.summary)
        layout.addWidget(buttons)
        self.resize(480, 200)
        self._refresh()

    def problem(self) -> str:
        """Why this cannot be saved, or ``""``."""
        if not self.name.text().strip():
            return "it needs a name -- that is what the polymer " \
                   "builder will list"
        try:
            monomer.from_structure(self.structure, self.head_point(),
                                   name=self.values()["name"])
        except (monomer.MonomerError, ValueError) as exc:
            return str(exc)
        return ""

    def _refresh(self, *_args) -> None:
        problem = self.problem()
        if problem:
            self.summary.setText(problem)
            set_tone(self.summary, WARNING)
        else:
            self.summary.setText(
                f"it will be in the polymer builder's library as "
                f"<b>{self.values()['name']}</b>, in "
                f"{self.folder.name}/ of this workspace")
            set_tone(self.summary, HINT)
        self.ok_button.setEnabled(not problem)

    def head_point(self) -> int | None:
        return self.head.currentData()

    def values(self) -> dict:
        return {"name": safe_name(self.name.text(), "monomer"),
                "head": self.head_point()}

    def path(self) -> Path:
        return self.folder / f"{self.values()['name']}.xyz"

    @classmethod
    def ask(cls, structure, folder, parent=None):
        """``(path, head)`` to write, or ``None`` if it was cancelled.

        """
        with answered(cls(structure, folder, parent)) as dialog:
            if dialog.exec() != QDialog.Accepted:
                return None
            return dialog.path(), dialog.head_point()


def _suggested(structure) -> str:
    """What the tab is called, as a file name."""
    title = str(structure.meta.get("title", "") or "")
    return safe_name(Path(title).stem, "monomer") if title else ""
