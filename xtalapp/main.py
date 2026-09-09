"""
xtalapp.main
============
Application entry point (``crystal-builder`` on the command line).

Sets QT_API before anything imports VTK's Qt bridge -- VTK picks its
binding from that variable, and getting it wrong is an import-time
crash rather than a friendly error.

Plugins are loaded here, before the window is built: the Modules menu,
the module tree, the format lists and the engine chooser are all built
from registries during construction, and a plugin that registered
afterwards would have registered into a window that had already read
them.

Logging starts before any of that -- see :mod:`xtalapp.applog`.  It is
started here and nowhere else: a window must not install a
process-wide excepthook, and a plugin that fails during ``load()``
below is the first thing there is to write down.

The application object is :class:`xtalapp.application.Application`
rather than a plain ``QApplication``, so that a file the desktop
hands over has somewhere to land -- see that module for why the
order below matters.

``--selftest`` is the one flag this entry point takes, and it is here
rather than in a script beside it because the only place it is useful
is *inside a frozen build*, where there is nothing beside it.  See
:mod:`xtalapp.selftest`.
"""

from __future__ import annotations

import logging
import os
import sys

os.environ.setdefault("QT_API", "pyside6")


#: ``--selftest``, and where to put the image it draws.  Parsed by
#: hand rather than with argparse: this entry point takes file paths
#: and nothing else, and an ArgumentParser here would start answering
#: ``-h`` in a windowed build that has no console to answer it into.
SELFTEST = "--selftest"
SELFTEST_SHOT = "--selftest-image"


def choose_workspace(paths, settings, parent=None):
    """Which workspace this launch is in, or ``None`` to give up.

    A file that is already *inside* a workspace skips the question:
    double-clicking a structure in a folder this application filled
    has only one sensible answer, and asking it is a dialog between a
    double-click and the crystal.  Anything else -- an empty launch, a
    CIF from a download folder -- is asked.

    ``paths`` has to include what the *desktop* asked for and not only
    what the command line did.  On macOS a double-click is a
    ``QFileOpenEvent`` and never an argument, so reading ``argv``
    alone would skip the question on the one platform where nobody
    launches this from a shell.
    """
    from xtal.workspace import Workspace
    from xtalapp.dialogs.workspace_chooser import WorkspaceChooser
    for path in paths:
        found = Workspace.find(path)
        if found is not None:
            return found
    return WorkspaceChooser.ask(settings, parent)


def main(argv=None) -> int:
    from xtal import __version__, plugins
    from xtalapp import applog, extras
    from xtalapp.application import Application
    from xtalapp.mainwindow import APP_NAME, MainWindow
    from xtalapp.settings import AppSettings

    applog.start()
    log = logging.getLogger("xtalapp")
    log.info("%s %s starting", APP_NAME, __version__)

    # Before the plugins, because a package the user installed into
    # that folder is one they may have installed a plugin *from*, and
    # a bundle has nowhere else to put one at all.  See
    # :mod:`xtalapp.extras`.
    added = extras.add_to_path()
    if added is not None:
        log.info("added %s to the import path", added)

    report = plugins.load()
    for name, message in report.failures:
        # A broken plugin is a line in the log, not a window that
        # will not open.  It used to be a line on stderr, which a
        # packaged build does not have.
        log.warning("plugin %s failed to load: %s", name, message)

    argv = list(sys.argv if argv is None else argv)

    if SELFTEST in argv:
        from pathlib import Path

        from xtalapp import selftest

        shot = None
        if SELFTEST_SHOT in argv:
            shot = Path(argv[argv.index(SELFTEST_SHOT) + 1])
        return selftest.run(shot=shot)

    app = Application(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("CrystalBuilder")

    # Built before the window, so that a launch-by-double-click --
    # which delivers its QFileOpenEvent during start-up, before there
    # is anything to open it in -- has already been queued by the
    # time the queue is released below.
    paths = [a for a in argv[1:] if not a.startswith("-")]
    # One spin of the loop first: the FileOpen event a double-click
    # sends is already on its way and has not been seen yet, and the
    # question below is about the file it names.
    app.processEvents()
    workspace = choose_workspace(paths + list(app.pending),
                                 AppSettings())
    if workspace is None:
        # Quit from the chooser.  There is no window yet and nothing
        # to close: the launch simply does not happen.
        return 0
    window = MainWindow(paths=paths, workspace=workspace)
    window.show()
    app.file_opened.connect(window.open_from_desktop)
    # Cmd-Q is delivered to the application and not to the window, so
    # the question about unsaved work is asked from here or not at
    # all.  See :mod:`xtalapp.application`.
    app.guard_quit(window.confirm_quit)
    app.start_delivering()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
