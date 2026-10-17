"""
xtalapp.dialogs.topcryst
========================
Structure ▸ Determine topology on TopCryst...: what was written, and
what happens next, before the browser opens.

**Nothing is sent from here.**  The CIF is already on disk when this
asks; *Open TopCryst* shows it in its folder and opens the site, and
the upload is a person dragging that file into a page.  The daily limit
is said first because the site refuses past it, and a structure
uploaded twice to check a fix is two of the ten.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)

from xtal.io.export import TOPCRYST_DAILY_LIMIT, TOPCRYST_URL
from xtal.references import TOPCRYST
from xtalapp.dialogs.answered import answered
from xtalapp.widgets.links import SourceLinks
from xtalapp.widgets.tone import HINT, set_tone


class TopCrystDialog(QDialog):
    """The file, the limit, and a button that opens the site."""

    def __init__(self, path: Path, dropped: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Determine topology on TopCryst")
        written = QLabel(
            f"Wrote <b>{path.name}</b> in {path.parent}.  Upload it at "
            f"{TOPCRYST_URL} to have its topology named by ToposPro.")
        written.setWordWrap(True)
        notes = [f"TopCryst takes at most {TOPCRYST_DAILY_LIMIT} "
                 f"structures a day from each person.",
                 "Nothing leaves this computer unless you upload it."]
        if dropped:
            notes.insert(0, dropped[0].upper() + dropped[1:] + ".")
        hint = QLabel("  ".join(notes))
        hint.setWordWrap(True)
        set_tone(hint, HINT)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        buttons.addButton("Open TopCryst", QDialogButtonBox.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(written)
        layout.addWidget(hint)
        self.sources = SourceLinks(TOPCRYST, self)
        layout.addWidget(self.sources)
        layout.addWidget(buttons)

    @classmethod
    def ask(cls, path: Path, dropped: str = "", parent=None) -> bool:
        """Whether to open the site and show the file."""
        with answered(cls(path, dropped, parent)) as dialog:
            return dialog.exec() == QDialog.Accepted


__all__ = ["TopCrystDialog"]
