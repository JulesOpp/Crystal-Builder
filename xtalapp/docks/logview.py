"""
xtalapp.docks.logview
=====================
``run.log``, on screen, while it is still being written.

Nothing used to be written down.  The report box in the Force Field
panel was cleared by the next run, and the reasons behind every typing
decision went with it -- so "why is this number what it is" had no
answer at all once the window had moved on.  Now every run writes a
log into its own folder as it goes (:mod:`xtal.ff.record`) and this is
the thing that reads it.

**It tails.**  A log is most wanted while the run is going, which is
exactly when it is incomplete, so the view polls for growth and
appends what is new.  Appending rather than rereading is what keeps
the scroll position where the user put it -- a viewer that jumped to
the top every half second would be unusable for the one job it has.

**It follows the end only while the user is at the end.**  Scroll up to
read something and it stays there; scroll back to the bottom and it
starts following again.  This is what every log viewer does and the
thing everybody notices when it is missing.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontDatabase, QTextCursor
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

POLL_MS = 500
# Below this the view is treated as being at the end, in pixels of
# scroll bar.  Exactly-at-the-bottom is too strict: a log that grows
# while the user is reading moves the bar by a line, and following
# would then switch itself off.
AT_END_SLOP = 24


class LogDock(QDockWidget):
    """A read-only monospaced view of one log file."""

    def __init__(self, parent=None):
        super().__init__("Log", parent)
        self.setObjectName("LogDock")
        self.path: Path | None = None
        self._offset = 0

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.view.setFont(QFontDatabase.systemFont(
            QFontDatabase.FixedFont))
        self.view.setMaximumBlockCount(200000)

        self.title = QLabel("No log open")
        self.title.setWordWrap(True)
        self.title.setTextInteractionFlags(
            Qt.TextSelectableByMouse)
        self.follow = QPushButton("Follow")
        self.follow.setCheckable(True)
        self.follow.setChecked(True)
        self.follow.setToolTip(
            "Keep the view at the end as the run writes to it")

        header = QHBoxLayout()
        header.setContentsMargins(6, 4, 6, 0)
        header.addWidget(self.title, 1)
        header.addWidget(self.follow)

        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(2)
        body.addLayout(header)
        body.addWidget(self.view, 1)
        container = QWidget()
        container.setLayout(body)
        self.setWidget(container)

        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self.poll)

    # -- opening -------------------------------------------------------

    def show_file(self, path) -> None:
        """Open a log, from the beginning."""
        self.path = Path(path)
        self._offset = 0
        self.view.clear()
        self.title.setText(str(self.path))
        self.title.setToolTip(str(self.path))
        self.poll()
        self._timer.start()
        self.show()
        self.raise_()

    def relocate(self, path) -> None:
        """The same log, in a folder that has moved.

        A build's run folder is filed under the module while it is
        running and under the structure it built once there is one to
        name it after, which happens with the log open.  The offset is
        deliberately kept: these are the same bytes, and reopening
        would print the whole run a second time and raise the dock
        over whatever is being looked at.
        """
        if self.path is None:
            return
        self.path = Path(path)
        self.title.setText(str(self.path))
        self.title.setToolTip(str(self.path))

    def clear(self) -> None:
        self._timer.stop()
        self.path = None
        self._offset = 0
        self.view.clear()
        self.title.setText("No log open")

    # -- tailing -------------------------------------------------------

    def poll(self) -> None:
        """Append whatever has been written since the last look."""
        if self.path is None:
            return
        try:
            size = self.path.stat().st_size
        except OSError:
            return
        if size < self._offset:
            # Truncated, or replaced by a new run in the same folder.
            self._offset = 0
            self.view.clear()
        if size == self._offset:
            return
        try:
            with self.path.open("r", encoding="utf-8",
                                errors="replace") as handle:
                handle.seek(self._offset)
                text = handle.read()
                self._offset = handle.tell()
        except OSError:
            return
        if text:
            self.append(text)

    def append(self, text: str) -> None:
        at_end = self.is_at_end()
        cursor = self.view.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        if self.follow.isChecked() and at_end:
            self.scroll_to_end()

    def is_at_end(self) -> bool:
        bar = self.view.verticalScrollBar()
        return bar.value() >= bar.maximum() - AT_END_SLOP

    def scroll_to_end(self) -> None:
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.maximum())

    @property
    def text(self) -> str:
        return self.view.toPlainText()

    def closeEvent(self, event):                    # pragma: no cover
        self._timer.stop()
        super().closeEvent(event)
