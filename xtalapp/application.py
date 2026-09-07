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

The desktop asks for one other thing this object is the only one to
hear: **quit**.  Cmd-Q does not travel through the window -- macOS
sends it here -- so ``MainWindow.closeEvent`` is not where a quit can
be questioned, and with a dialog open the question about unsaved work
was raised behind a modal that holds the keyboard.  The application
asks a guard first: :func:`xtalapp.main.main` hands it the window's
``confirm_quit`` and a "no" cancels the quit.  Nothing is guarded when
no guard was set, which is what a bare ``Application`` in a test is.

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

#: What the desktop asking us to quit arrives as.  Two of them because
#: the answer depends on the Qt version and the platform: a menu Quit
#: reaches the application as ``Quit``, and macOS's own terminate is
#: delivered as a ``Close`` on the application object, whose accepted
#: flag is read as the answer.  Both mean the same thing here.
QUIT_EVENTS = (QEvent.Type.Quit, QEvent.Type.Close)


class Application(QApplication):
    """The application object, with somewhere for a path to land."""

    #: A file the desktop asked us to open.  Connected to the window
    #: in :func:`xtalapp.main.main`; nothing else listens.
    file_opened = Signal(str)

    def __init__(self, argv=None):
        super().__init__(list(argv or []))
        self._pending: list[str] = []
        self._delivering = False
        self._quit_guard = None

    # -- the event ------------------------------------------------------

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.FileOpen:
            path = self._path_of(event)
            if path:
                self.open_later(path)
                return True
        if event.type() in QUIT_EVENTS and not self.may_quit():
            # Ignored as well as swallowed: the terminate the Cocoa
            # plugin sends reads the flag back off the event, so
            # returning True on its own quits anyway.
            event.ignore()
            return True
        return super().event(event)

    # -- quitting -------------------------------------------------------

    def guard_quit(self, guard) -> None:
        """Ask ``guard()`` before a quit from the desktop goes ahead.

        One guard, set by :func:`xtalapp.main.main` to the window's
        ``confirm_quit``; a second window would be a second question
        and there has never been one.
        """
        self._quit_guard = guard

    def may_quit(self) -> bool:
        """Whether the quit the desktop asked for may go ahead."""
        return True if self._quit_guard is None else bool(
            self._quit_guard())

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
        self._quit_guard = None

    def _flush(self) -> None:
        # Popped one at a time rather than iterated over a copy, so
        # that a path arriving *during* delivery is delivered too
        # rather than left in a list the loop has already finished
        # with.  Finder sends one event per file when several are
        # opened at once, and Qt is free to deliver the second while
        # the first is still being handled.
        while self._pending:
            self.file_opened.emit(self._pending.pop(0))
