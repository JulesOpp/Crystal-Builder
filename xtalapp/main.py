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
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_API", "pyside6")


def main(argv=None) -> int:
    from PySide6.QtWidgets import QApplication

    from xtal import plugins
    from xtalapp.mainwindow import APP_NAME, MainWindow

    report = plugins.load()
    for name, message in report.failures:
        # A broken plugin is a line on stderr, not a window that will
        # not open.
        print(f"warning: plugin {name} failed to load: {message}",
              file=sys.stderr)

    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("CrystalBuilder")

    paths = [a for a in argv[1:] if not a.startswith("-")]
    window = MainWindow(paths=paths)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
