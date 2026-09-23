"""
xtalapp.dialogs.run_progress
============================
A window that says a module is running.

The module tree's footer already said it, and that was not enough.
Zeo++'s pore size distribution is minutes of a binary printing Voronoi
housekeeping into a log, and from the outside a status line reading
``running Zeo++: Pore size distribution...`` at the bottom of a panel
that may not even be open is indistinguishable from a frozen
application.  So there is a window, and it is where Stop is.

Three decisions make it a help rather than an interruption.

**It does not appear for a run that is over before it is noticed.**
The stub module counts to five in a second and the diameters of a small
cell come back in two; a dialog that flashes up and away for those is
worse than none.  So it is armed on a timer and shows only if the run
is still going when the timer fires -- the same rule ``QProgressDialog``
uses, and for the same reason.

**It is not modal.**  A run takes the structure's *copy*, so nothing
the user does to the document while it goes can affect it, and being
unable to turn the crystal round for four minutes would be a punishment
for asking a question.  It floats above the window, says what is
happening, and gets out of the way when asked.

**The bar does not lie.**  Zeo++ reports no fraction of anything -- it
prints stages -- so the bar is indeterminate and the *text* carries the
progress.  A bar creeping to 90% and sitting there is a worse lie than
a bar that never claimed to know.
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from xtalapp.widgets.tone import HINT, set_tone

#: How long a run has to have been going before the window appears.
#: Long enough that a fast module never shows one, short enough that a
#: slow one has not yet had time to look like a hang.
DELAY_MS = 400

#: How often the elapsed time is redrawn.  It is the only part of this
#: window that changes on its own, and it is what says the application
#: is alive while a binary is quiet.
TICK_MS = 500

#: Progress lines are one line of a log and can be very long.
WIDTH = 96


class RunProgressDialog(QDialog):
    """What is running, how long it has been, and a way to stop it."""

    stopRequested = Signal()

    def __init__(self, parent=None):
        # A tool window: it floats above the main window and does not
        # get its own entry in the window list, which is what a
        # transient thing like this should be.
        super().__init__(parent, Qt.Tool)
        self.setWindowTitle("Running")
        self.setModal(False)

        self.title = QLabel("")
        font = self.title.font()
        font.setBold(True)
        self.title.setFont(font)

        self.bar = QProgressBar()
        self.bar.setRange(0, 0)             # indeterminate, honestly
        self.bar.setTextVisible(False)

        self.elapsed = QLabel("")
        set_tone(self.elapsed, HINT)
        self.line = QLabel("")
        self.line.setWordWrap(False)
        set_tone(self.line, HINT)
        self.line.setMinimumWidth(360)

        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self._on_stop)
        self.hide_button = QPushButton("Hide")
        self.hide_button.clicked.connect(self.hide)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.hide_button)
        buttons.addWidget(self.stop_button)

        body = QVBoxLayout(self)
        body.setContentsMargins(14, 12, 14, 12)
        body.setSpacing(8)
        body.addWidget(self.title)
        body.addWidget(self.bar)
        body.addWidget(self.line)
        body.addWidget(self.elapsed)
        body.addLayout(buttons)

        self._started = 0.0
        self._ticker = QTimer(self)
        self._ticker.timeout.connect(self._tick)
        self._opener = QTimer(self)
        self._opener.setSingleShot(True)
        self._opener.timeout.connect(self._appear)

    # -- the run -------------------------------------------------------

    def start(self, label: str, delay_ms: int = DELAY_MS) -> None:
        """Arm the window for a run that has just begun.

        Armed, not shown: see the module docstring for why a run that
        is over in two seconds must not put a window on the screen.
        """
        self.title.setText(label)
        self.line.setText("starting...")
        self.stop_button.setEnabled(True)
        self.stop_button.setText("Stop")
        self._started = time.monotonic()
        self._tick()
        self._ticker.start(TICK_MS)
        if delay_ms <= 0:
            self._appear()
        else:
            self._opener.start(int(delay_ms))

    def set_progress(self, text: str) -> None:
        if text:
            self.line.setText(_short(text))

    def finish(self) -> None:
        """The run ended, however it ended."""
        self._opener.stop()
        self._ticker.stop()
        self.hide()

    @property
    def armed(self) -> bool:
        """Waiting to appear, or already up."""
        return self._opener.isActive() or self.isVisible()

    # -- inside ---------------------------------------------------------

    def _appear(self) -> None:
        self.show()
        self.raise_()

    def _tick(self) -> None:
        seconds = time.monotonic() - self._started
        self.elapsed.setText(f"{_duration(seconds)} so far")

    def _on_stop(self) -> None:
        # Said here rather than by the window, because the gap between
        # asking a binary to stop and it stopping is exactly when a
        # user presses the button again.
        self.stop_button.setEnabled(False)
        self.stop_button.setText("Stopping...")
        self.line.setText("waiting for it to put itself away...")
        self.stopRequested.emit()

    def closeEvent(self, event):
        """Closing the window hides it; it does not stop the run.

        A window that killed a four-minute calculation because it was
        in the way would be the worst thing in this file.  Stop is a
        button and says so.
        """
        event.ignore()
        self.hide()


def _short(text: str) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= WIDTH else text[:WIDTH - 1] + "…"


def _duration(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    if seconds < 60:
        return f"{seconds:.0f} s"
    minutes, rest = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes} min {rest:02d} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min"
