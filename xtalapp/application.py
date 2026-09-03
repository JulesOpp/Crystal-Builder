"""
xtalapp.application
===================
The ``QApplication``, and the file the desktop hands it.

There are two ways a double-clicked ``.cif`` reaches this program and
only one of them was ever handled.

**On the command line** -- which is also how Windows file
associations and a *cold* macOS launch deliver a file -- the path is
in ``argv``, and :func:`xtalapp.main.main` has always passed it to the
window.  That still happens and is unchanged.

**On macOS, to an application that is already running**, there is no
argv to put it in: the path arrives as a ``QFileOpenEvent`` on the
application object.  Nothing handled that, so opening a second
structure from Finder with the window already up did *nothing at
all*, which reads as the file association being broken -- and it is
the first thing anybody tries after installing.

The ordering is the part worth being careful about, because getting
it backwards produces a bug that works every time it is tested by
hand.  **The event can arrive before there is a window.**  A cold
launch by double-click delivers it during start-up, ahead of
``MainWindow`` being constructed, so a handler that opens the file
immediately drops it on the floor exactly when a person launched the
application *by opening a file*.  So every path is queued, and the
queue is released once something is listening.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Signal
from PySide6.QtWidgets import QApplication


class Application(QApplication):
    """The application object, with somewhere for a path to land."""

    #: A file the desktop asked us to open.  Connected to the window
    #: in :func:`xtalapp.main.main`; nothing else listens.
    file_opened = Signal(str)

    def __init__(self, argv=None):
        super().__init__(list(argv or []))
        self._pending: list[str] = []
        self._delivering = False

    # -- the event ------------------------------------------------------

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.FileOpen:
            path = self._path_of(event)
            if path:
                self.open_later(path)
                return True
        return super().event(event)

    @staticmethod
    def _path_of(event) -> str:
        """The local file the event names, or ``""``.

        ``file()`` is empty when the event carries a URL instead --
        which is what a custom scheme registered against this
        application would arrive as -- and a URL that is not a local
        file is not something this application can open.
        """
        path = event.file()
        if path:
            return str(path)
        url = event.url()
        return str(url.toLocalFile()) if url.isLocalFile() else ""

    # -- the queue ------------------------------------------------------

    def open_later(self, path) -> None:
        """Open ``path`` now, or as soon as there is a window."""
        self._pending.append(str(path))
        if self._delivering:
            self._flush()

    def start_delivering(self) -> None:
        """Release the queue.  Called once the window is connected."""
        self._delivering = True
        self._flush()

    @property
    def pending(self) -> tuple[str, ...]:
        """What is waiting for a window.  For tests and for nothing
        else -- the queue empties itself."""
        return tuple(self._pending)

    def reset(self) -> None:
        """Empty the queue and stop delivering.

        For the suite, whose ``qapp`` is one session-scoped object
        shared by every test in the run -- so a queue left behind by
        one test is a file opened in another one's window.  The same
        reason :func:`xtalapp.applog.reset` exists.
        """
        self._pending.clear()
        self._delivering = False

    def _flush(self) -> None:
        # Popped one at a time rather than iterated over a copy, so
        # that a path arriving *during* delivery is delivered too
        # rather than left in a list the loop has already finished
        # with.  Finder sends one event per file when several are
        # opened at once, and Qt is free to deliver the second while
        # the first is still being handled.
        while self._pending:
            self.file_opened.emit(self._pending.pop(0))
