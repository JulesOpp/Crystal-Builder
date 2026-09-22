"""
xtalapp.widgets.notice
======================
A bar across the top of the window that says one thing and waits.

For what a six-second status line is too brief for and a modal is too
much: something the user should read once, at the moment it happens,
without being stopped.  It stays until it is dismissed or answered,
and never takes the keyboard.

**Not a QMessageBox**, on purpose: a modal is a question, and these
are statements with at most a choice beside them.  It is also what
lets the suite exercise them -- ``conftest.py`` makes every modal
raise.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
)


class NoticeBar(QFrame):
    """One sentence, its buttons, and a close box."""

    #: The label of the button pressed, or ``""`` for the close box.
    answered = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NoticeBar")
        self.setFrameShape(QFrame.StyledPanel)
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(8, 4, 4, 4)
        self._row.addWidget(self.label, 1)
        self.buttons: list[QPushButton] = []
        self.close_button = QToolButton()
        self.close_button.setText("×")
        self.close_button.setAutoRaise(True)
        self.close_button.clicked.connect(lambda: self._answer(""))
        self._row.addWidget(self.close_button)
        self._handler = None
        self.hide()

    def show_notice(self, text: str, buttons=(), on_answer=None) -> None:
        """Say ``text``, offering ``buttons``; replaces any notice up.

        ``on_answer`` is called once: with the label pressed, ``""``
        when the notice is closed without one, or ``None`` when a
        newer notice takes its place before it was answered -- so
        nothing waits on an answer that will never come, and a caller
        that still wants one can ask again once the bar is free
        (:attr:`answered` says when).
        """
        superseded, self._handler = self._handler, None
        if superseded is not None:
            superseded(None)
        for button in self.buttons:
            self._row.removeWidget(button)
            button.deleteLater()
        self.buttons = []
        for label in buttons:
            button = QPushButton(label)
            button.setAutoDefault(False)
            button.clicked.connect(
                lambda _checked=False, text=label: self._answer(text))
            self._row.insertWidget(self._row.count() - 1, button)
            self.buttons.append(button)
        self.label.setText(text)
        self._handler = on_answer
        self.show()

    def button(self, label: str) -> QPushButton:
        for button in self.buttons:
            if button.text() == label:
                return button
        raise KeyError(label)

    def _answer(self, label: str) -> None:
        handler, self._handler = self._handler, None
        self.hide()
        if handler is not None:
            handler(label)
        self.answered.emit(label)
