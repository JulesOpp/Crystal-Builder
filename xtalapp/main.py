"""
xtalapp.main
============
Application entry point (``crystal-builder`` on the command line).

Sets QT_API before anything imports VTK's Qt bridge -- VTK picks its
binding from that variable, and getting it wrong is an import-time
crash rather than a friendly error.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_API", "pyside6")


def main(argv=None) -> int:
    from PySide6.QtWidgets import QApplication

    from xtalapp.mainwindow import APP_NAME, MainWindow

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
