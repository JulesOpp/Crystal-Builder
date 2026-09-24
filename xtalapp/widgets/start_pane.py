"""
xtalapp.widgets.start_pane
==========================
What the middle of the window shows when no structure is open.

It used to be an empty grey tab widget.  The workspace chooser before
it explains itself and offers a sample; the window after it offered
nothing, on the screen where somebody who has just installed the
program decides whether to keep it -- although drag-and-drop already
worked and seven structures were one menu away.  The COD's
sit under a heading of their own, below the seven.

**Nothing here does anything of its own.**  Every button is a view of
a window action (``open``, ``new``, ``sample_<name>``), so what it is
called, whether it is enabled and what its tooltip says are the
registry's, and a sample missing from a wheel install greys here as it
does in the File menu.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from xtalapp import samples
from xtalapp.widgets.tone import HINT, set_tone

#: Samples per row: seven in two rows fits the narrowest viewport a
#: first run now gives (about 340 px at 1024 wide) without clipping.
COLUMNS = 4


def _button(action) -> QToolButton:
    button = QToolButton()
    button.setDefaultAction(action)
    button.setToolButtonStyle(Qt.ToolButtonTextOnly)
    button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return button


class StartPane(QWidget):
    """The icon, how to open something, and the samples."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.setObjectName("StartPane")
        column = QVBoxLayout(self)
        column.addStretch(1)

        # The chooser's own drawing of the icon, so the two screens a
        # first run shows are visibly one program.
        from xtalapp.dialogs.workspace_chooser import _icon
        art = QLabel()
        art.setPixmap(_icon(96))
        art.setAlignment(Qt.AlignHCenter)
        column.addWidget(art)

        hint = QLabel("Open a structure, drop a file here, "
                      "or start from a sample.")
        hint.setAlignment(Qt.AlignHCenter)
        hint.setWordWrap(True)
        column.addWidget(hint)

        row = QHBoxLayout()
        row.addStretch(1)
        self.open_button = _button(window.actions_["open"])
        self.new_button = _button(window.actions_["new"])
        for button in (self.open_button, self.new_button):
            button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            row.addWidget(button)
        row.addStretch(1)
        column.addLayout(row)

        # A grid per group, the COD's under a heading: both groups have
        # a MOF-5, and two buttons of that name in one grid would say
        # nothing about which was which.
        self.sample_buttons = {}
        for group, title in samples.GROUPS:
            if group != samples.SHIPPED:
                heading = QLabel(title.replace("&", ""))
                heading.setAlignment(Qt.AlignHCenter)
                set_tone(heading, HINT)
                column.addWidget(heading)
            grid = QGridLayout()
            for n, sample in enumerate(samples.in_group(group)):
                button = _button(
                    window.actions_[f"sample_{sample.name}"])
                self.sample_buttons[sample.name] = button
                grid.addWidget(button, n // COLUMNS, n % COLUMNS)
            centred = QHBoxLayout()
            centred.addStretch(1)
            centred.addLayout(grid, 4)
            centred.addStretch(1)
            column.addLayout(centred)
        if not samples.installed():
            missing = QLabel(samples.MISSING)
            missing.setAlignment(Qt.AlignHCenter)
            missing.setWordWrap(True)
            column.addWidget(missing)

        column.addStretch(2)
