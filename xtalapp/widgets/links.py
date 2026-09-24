"""
xtalapp.widgets.links
=====================
A line of links to where something comes from.

The Force Field and DFTB+ panels, the MOF and net builders and
Preferences > Engines all say where a method, a database or a program
comes from.  One label so they all look and behave alike: each link on
its own line, in the hint tone, and opened in the browser -- nothing
here follows a link itself.
"""

from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from xtalapp.widgets.tone import HINT, set_tone


def sources_html(references) -> str:
    """One link to a line, each labelled with what it opens."""
    return "<br>".join(
        f'<a href="{html.escape(r.url, quote=True)}">'
        f"{html.escape(r.label)}</a>" for r in references)


class SourceLinks(QLabel):
    """Links that open in the browser, hidden when there are none."""

    def __init__(self, references=(), parent=None):
        super().__init__(parent)
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setOpenExternalLinks(True)
        set_tone(self, HINT)
        self.set_references(references)

    def set_references(self, references) -> None:
        references = tuple(references)
        self.setText(sources_html(references))
        self.setVisible(bool(references))

    def urls(self) -> list[str]:
        """Where the links go, for a test to read without parsing."""
        import re

        return re.findall(r'href="([^"]+)"', self.text())
