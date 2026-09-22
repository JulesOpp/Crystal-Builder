"""
xtalapp.dialogs.save_block
==========================
The open molecule, out to the folder the MOF builder reads.

The last step of Phase U's building-block path, and the one that makes
it a loop rather than a line: a linker built from a SMILES string,
marked, and written here appears in the MOF builder's picker beside
the 867 PORMAKE ships, **with nothing further clicked**.  That is why
the folder defaults to :attr:`~xtalapp.settings.AppSettings.mof_bb_dir`
and is written back on the way out -- it is the same box
:mod:`xtalapp.dialogs.mof_build` reads its extra blocks from, and a
block saved somewhere else is a block the user then has to go and find
again.

**The refusals are shown, not discovered.**
:func:`xtal.mof.block.problems` lists everything that stops this
structure being a block and it is shown live, because every one of
them is something the user has to go back and change -- a connection
point they have not marked, an atom with two bonds, a cell with two
molecules in it.  Told after pressing Save, each of those is a dialog
dismissed and a dialog reopened.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from xtal.mof.block import problems
from xtal.workspace import safe_name
from xtalapp.widgets.tone import HINT, set_tone


class SaveBlockDialog(QDialog):
    """Name it, say where it goes, and be told if it is not a block."""

    def __init__(self, structure, parent=None, folder: str = ""):
        super().__init__(parent)
        self.structure = structure
        self.setWindowTitle("Save as a building block")
        self._settings = getattr(parent, "settings", None)

        self.name = QLineEdit(_suggested(structure), self)
        self.name.setPlaceholderText(
            "the file name, which is the block's name in the picker")
        self.name.textChanged.connect(self._refresh)
        self.folder = QLineEdit(
            str(folder or self._remembered() or ""), self)
        self.folder.setPlaceholderText(
            "the folder the MOF builder reads your own blocks from")
        self.folder.textChanged.connect(self._refresh)
        browse = QPushButton("Browse...", self)
        browse.clicked.connect(self._browse)

        self.summary = QLabel(self)
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.RichText)
        self._build_ui(browse)
        self._refresh()

    def _build_ui(self, browse) -> None:
        where = QHBoxLayout()
        where.setContentsMargins(0, 0, 0, 0)
        where.addWidget(self.folder, 1)
        where.addWidget(browse)

        form = QFormLayout()
        form.addRow("Name", self.name)
        form.addRow("Building blocks folder", where)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok |
                                   QDialogButtonBox.Cancel)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)
        self.ok_button.setText("Save")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.summary)
        layout.addWidget(buttons)
        self.resize(520, 220)

    def _remembered(self) -> str:
        return str(getattr(self._settings, "mof_bb_dir", "") or "")

    def _browse(self) -> None:                      # pragma: no cover
        chosen = QFileDialog.getExistingDirectory(
            self, "Building blocks folder",
            self.folder.text() or str(Path.home()))
        if chosen:
            self.folder.setText(chosen)

    # -- what it will write --------------------------------------------

    def _refresh(self) -> None:
        found = self.problems()
        self.summary.setText("<br>".join(found) if found
                             else self._describe())
        if found:
            set_tone(self.summary, None)
            self.summary.setStyleSheet("color: palette(link-visited);")
        else:
            set_tone(self.summary, HINT)
        self.ok_button.setEnabled(not found)

    def problems(self) -> list[str]:
        """Everything stopping this from being written, the empty
        boxes included."""
        found = list(problems(self.structure))
        if not self.name.text().strip():
            found.append("it needs a name -- that is what the picker "
                         "will show")
        if not self.folder.text().strip():
            found.append("it needs a folder, and the MOF builder's "
                         "own is the one that makes it appear in the "
                         "picker")
        return found

    def _describe(self) -> str:
        from xtal.core import p1
        cell = p1.expand(self.structure)
        points = sum(1 for symbol in cell.elements if symbol == "X")
        return (f"{points}-connected -- it will appear in the MOF "
                f"builder's picker as <b>{self.values()['name']}</b>")

    def values(self) -> dict:
        return {"name": safe_name(self.name.text(), "block"),
                "folder": self.folder.text().strip()}

    def path(self) -> Path:
        values = self.values()
        return Path(values["folder"]) / f"{values['name']}.xyz"

    def accept(self) -> None:
        # Written back so that the next MOF build reads this folder
        # without being pointed at it again -- the whole of "with
        # nothing further clicked".
        if self._settings is not None:
            self._settings.mof_bb_dir = self.folder.text().strip()
        super().accept()

    @classmethod
    def ask(cls, structure, parent=None, folder: str = ""):
        """Where to write it, or ``None`` if it was cancelled."""
        dialog = cls(structure, parent, folder)
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.path()


def _suggested(structure) -> str:
    """A name to start from: what the tab is called.

    Through ``safe_name`` because this becomes a file name and the
    block's name in the picker at once -- a title with a slash in it
    would be a folder somebody did not ask for.
    """
    title = str(structure.meta.get("title", "") or "")
    return safe_name(Path(title).stem, "block") if title else ""
