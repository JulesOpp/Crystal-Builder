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


def main(argv=None) -> int:
    from xtal import __version__, plugins
    from xtalapp import applog, extras
    from xtalapp.application import Application
    from xtalapp.mainwindow import APP_NAME, MainWindow

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
    window = MainWindow(paths=paths)
    window.show()
    app.file_opened.connect(window.open_from_desktop)
    # Cmd-Q is delivered to the application and not to the window, so
    # the question about unsaved work is asked from here or not at
    # all.  See :mod:`xtalapp.application`.
    app.guard_quit(window.confirm_quit)
    app.start_delivering()

    # After the queue is released, and only if it left nothing: a
    # launch that named a file wants that file, not the sample or the
    # last session's structure in front of it.  Preferences > General
    # owns this, and its default is the empty window this application
    # has always opened with.
    if not window.documents:
        window.open_at_startup()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
