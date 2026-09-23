"""
xtalapp.docks.info
==================
The structure-information panel: formula, Z, cell, density, and any
warnings the reader raised.

Warnings are shown here rather than in a modal dialog because they are
almost always about a file, not about an action: "this CIF's symmetry
operations disagree with its space-group symbol" is something you want
to see while you look at the structure, not something to click away.
"""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDockWidget,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from xtalapp.widgets.tone import WARNING_BOX, set_tone


class InfoDock(QDockWidget):
    """Read-only summary of the active document."""

    def __init__(self, parent=None):
        super().__init__("Structure", parent)
        self.setObjectName("InfoDock")

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        # The panel is a monospace table; wrapping it turns the
        # coordinate columns into mush.
        self.text.setLineWrapMode(QPlainTextEdit.NoWrap)
        # No minimum width.  It was 380 px, the longest line the panel
        # writes, and a minimum here is a minimum for the whole left
        # column: the divider would not drag past it.  The first-run
        # width is set by ``layout.apply_default_layout`` instead, and a
        # narrower panel scrolls its text sideways.
        font = QFont("Menlo")
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(11)
        self.text.setFont(font)

        self.warnings = QLabel()
        self.warnings.setWordWrap(True)
        set_tone(self.warnings, WARNING_BOX, padding=6)
        self.warnings.hide()

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.text, 1)
        layout.addWidget(self.warnings)

        container = QWidget()
        container.setLayout(layout)
        self.setWidget(container)

    def show_document(self, document) -> None:
        if document is None:
            self.text.setPlainText("No structure open.")
            self.warnings.hide()
            return
        self.text.setPlainText(self._describe(document))
        if document.warnings:
            self.warnings.setText("\n".join(
                f"warning: {w}" for w in document.warnings))
            self.warnings.show()
        else:
            self.warnings.hide()

    @staticmethod
    def _describe(document) -> str:
        structure = document.structure
        if not structure.n_sites:
            return "Empty cell."
        lines = [document.info().text()]
        # The hand belongs on a panel that is always on screen rather
        # than inside the menu item that changes it: a structure solved
        # in the wrong hand looks perfectly good, and nobody goes
        # looking for an inversion they have no reason to suspect.
        lines.append(f"hand           {document.hand()}")
        source = structure.meta.get("source")
        if source:
            lines.append(f"\nfile           {source}")
        counts = {}
        for site in structure.sites:
            counts[site.element] = counts.get(site.element, 0) + 1
        lines.append("\nasymmetric unit")
        for site in structure.sites:
            x, y, z = site.frac
            occ = ("" if site.occupancy == 1.0
                   else f"  occ {site.occupancy:.3f}")
            label = site.label or site.element
            lines.append(f"  {label:<8s} {site.element:<3s} "
                         f"{x: .5f} {y: .5f} {z: .5f}{occ}")
        return "\n".join(lines)
