"""
xtalapp.applog
==============
Where the application writes down what happened.

Nothing used to be written down.  Plugin load failures went to
``sys.stderr``, Qt's own warnings went to ``sys.stderr``, and an
uncaught exception printed a traceback there and took the window with
it.  In a terminal that is fine.  In a packaged build there is no
terminal at all -- a ``--windowed`` PyInstaller bundle has no stderr
-- so all three go nowhere, and the first bug report is "it closed",
with nothing attached to it.

So: one rotating file, in the place each platform keeps application
data, plus the three things that would otherwise be lost to it.

**Not called from a window.**  :func:`start` installs a process-wide
excepthook and creates a directory under the user's home, and neither
belongs to an object a test builds forty times.  It is called from
:func:`xtalapp.main.main` and from nowhere else; a test that wants
the file handler calls :func:`setup` with a directory of its own, and
``XTAL_LOG_DIR`` is honoured before anything else precisely so that a
suite can make that impossible to get wrong.

**The handler goes on the root logger**, which is what makes
:mod:`xtal`'s modules and a dependency's modules land in the same
file without either of them knowing this exists.  Two things already
in this application move the root logger around, and both are safe:
:func:`xtalapp.dialogs.sketch._canvas` saves and restores its level
and handlers around rdeditor's ``basicConfig``, and
:func:`xtal.mof.build.import_pormake` swaps ``logging.FileHandler``
only for the duration of an import.  There are tests for both, in
``tests/test_applog.py``, because "still true" is the whole claim.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import threading
import traceback
from pathlib import Path

#: The folder name under the platform's application-data directory.
#: Not :class:`QStandardPaths`' own ``AppDataLocation``, which appends
#: the organisation and application names *when a QApplication has
#: been given them* -- so the same call answers differently depending
#: on when it is made, and on Windows would give
#: ``CrystalBuilder/CrystalBuilder``.  A generic location plus one
#: name is the same answer whenever it is asked.
FOLDER = "CrystalBuilder"
FILE = "crystal-builder.log"

#: Set this and nothing looks anywhere else.  The test suite sets it
#: at import, for the reason in the module docstring.
DIR_VAR = "XTAL_LOG_DIR"
LEVEL_VAR = "XTAL_LOG_LEVEL"

#: A megabyte, three times over.  A tool that runs two-hundred-step
#: relaxations and tails Zeo++ -- which prints tens of thousands of
#: voro++ housekeeping lines per run -- writes a log that grows
#: without bound otherwise, in a folder nobody ever looks in.
MAX_BYTES = 1_000_000
BACKUPS = 3

FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_log_file: Path | None = None
_handler: logging.Handler | None = None
_added: list = []
_in_hook = False


def app_data() -> Path:
    """This application's folder under the platform's data directory.

    ``~/Library/Application Support/CrystalBuilder`` here,
    ``%APPDATA%\\CrystalBuilder`` on Windows.  The log lives in it and
    so does the folder :mod:`xtalapp.extras` puts on ``sys.path``,
    which is why the lookup is a name of its own rather than part of
    the log's.
    """
    try:
        from PySide6.QtCore import QStandardPaths
    except ImportError:                             # pragma: no cover
        return Path.home() / f".{FOLDER.lower()}"
    root = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.GenericDataLocation)
    if not root:                                    # pragma: no cover
        return Path.home() / f".{FOLDER.lower()}"
    return Path(root) / FOLDER


def default_directory() -> Path:
    """Where the log goes when nobody says otherwise."""
    given = os.environ.get(DIR_VAR, "").strip()
    return Path(given).expanduser() if given else app_data()


def log_file() -> Path | None:
    """The file being written, or ``None`` if logging never started."""
    return _log_file


def setup(directory=None) -> Path:
    """Attach the rotating file handler to the root logger.

    Idempotent: a second call returns the same path and does not add
    a second handler.  Both the GUI and the tests call this, and in
    the same process during a suite run.
    """
    global _log_file, _handler
    if _handler is not None and _log_file is not None:
        return _log_file

    folder = Path(directory) if directory else default_directory()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / FILE

    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=MAX_BYTES, backupCount=BACKUPS,
        encoding="utf-8", delay=True)
    handler.setFormatter(logging.Formatter(FORMAT, DATE_FORMAT))

    level = os.environ.get(LEVEL_VAR, "").strip().upper() or "INFO"
    root = logging.getLogger()
    root.setLevel(getattr(logging, level, logging.INFO))
    root.addHandler(handler)
    _added.append(handler)

    # Keep stderr working where there is one.  The file is for the
    # packaged build; a developer running from a terminal should not
    # lose the messages they have always had, and would otherwise
    # have to open a file to read a warning they used to see.
    if getattr(sys, "stderr", None) is not None:
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter(FORMAT, DATE_FORMAT))
        root.addHandler(stream)
        _added.append(stream)

    _handler, _log_file = handler, path
    return path


def reset() -> None:
    """Detach everything this module attached.

    For the suite, which needs each test's log in a directory of its
    own and would otherwise get the first test's file for all of
    them -- :func:`setup` is idempotent by design, and that is the
    right behaviour everywhere except here.

    Only what :func:`setup` attached, tracked rather than deduced.
    Clearing the root logger's handlers wholesale would take pytest's
    own capture handler with it, and the tests that lost their output
    would be somebody else's, three files away.
    """
    global _log_file, _handler
    root = logging.getLogger()
    while _added:
        handler = _added.pop()
        root.removeHandler(handler)
        handler.close()
    _handler, _log_file = None, None


def install_excepthook() -> None:
    """Write down what killed it, then say so.

    Both hooks, because the long work in this application happens off
    the GUI thread: :mod:`xtalapp.workers` runs an optimisation and a
    module in one, and an exception raised there reaches
    ``threading.excepthook`` rather than ``sys.excepthook``.
    """
    sys.excepthook = _excepthook
    threading.excepthook = _thread_excepthook


def _excepthook(kind, value, tb) -> None:
    if issubclass(kind, KeyboardInterrupt):
        sys.__excepthook__(kind, value, tb)
        return
    _record("Unhandled exception", kind, value, tb)
    _tell_somebody(kind, value)


def _thread_excepthook(args) -> None:
    if issubclass(args.exc_type, SystemExit):
        return
    _record(f"Unhandled exception in thread {args.thread}",
            args.exc_type, args.exc_value, args.exc_traceback)


def _record(title, kind, value, tb) -> None:
    """Log a traceback without ever raising one of our own.

    A hook that fails has nowhere to report it and, on the
    ``sys.excepthook`` path, is running because something has already
    gone wrong -- so the fallback is the interpreter's own hook and
    not a second exception nobody will see.
    """
    global _in_hook
    if _in_hook:                                    # pragma: no cover
        return
    _in_hook = True
    try:
        text = "".join(traceback.format_exception(kind, value, tb))
        logging.getLogger("xtalapp").critical("%s\n%s", title, text)
    except Exception:                               # noqa: BLE001
        try:                                        # pragma: no cover
            sys.__excepthook__(kind, value, tb)
        except Exception:                           # noqa: BLE001
            pass
    finally:
        _in_hook = False


def _tell_somebody(kind, value) -> None:
    """A dialog naming the log, when there is a GUI left to show one.

    Guarded three ways, because this runs at the worst possible
    moment: no application object during start-up or shutdown, no
    dialog if Qt itself is what failed, and never a second exception
    out of the handler for the first.
    """
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        if QApplication.instance() is None:
            return
        box = QMessageBox(QMessageBox.Icon.Critical, "Crystal Builder",
                          f"{kind.__name__}: {value}")
        box.setInformativeText(
            "Something went wrong and the details have been written "
            f"to:\n{_log_file}")
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()
    except Exception:                               # noqa: BLE001
        pass


def install_qt_handler() -> None:
    """Send Qt's own warnings to the same file.

    Every one of these goes to stderr today, which in a packaged
    build means nowhere -- and Qt's warnings are the ones that
    explain a layout that came out wrong or a signal that never
    connected, which is exactly what a bug report needs.
    """
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    levels = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }
    logger = logging.getLogger("qt")

    def handler(mode, context, message) -> None:
        logger.log(levels.get(mode, logging.INFO), "%s", message)

    qInstallMessageHandler(handler)


def start(directory=None) -> Path:
    """Everything, for :func:`xtalapp.main.main`."""
    path = setup(directory)
    install_excepthook()
    install_qt_handler()
    return path


def reveal() -> bool:
    """Show the log's folder in Finder or Explorer.

    The folder and not the file: opening a rotating megabyte of text
    in whatever the desktop has claimed ``.log`` is a worse answer
    than putting the user where all three of them are.
    """
    if _log_file is None:
        return False
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    return bool(QDesktopServices.openUrl(
        QUrl.fromLocalFile(str(_log_file.parent))))
