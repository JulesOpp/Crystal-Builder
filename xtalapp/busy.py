"""
xtalapp.busy
============
The wait cursor, for work done on the UI thread.

Supercell on MFU-4l is over a second and Set Bond Type on a large
framework is three, and a window that has stopped painting looks
exactly like one that has missed the click.  Moving that work to a
thread is the larger fix; saying it is happening is the one that makes
everything under a couple of seconds legible.
"""

from __future__ import annotations

from contextlib import contextmanager

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication


@contextmanager
def busy():
    """Show the wait cursor for the duration, and always put it back.

    Without an application there is no cursor to set, which is what a
    headless caller of a Document is.
    """
    if QGuiApplication.instance() is None:
        yield
        return
    QGuiApplication.setOverrideCursor(Qt.WaitCursor)
    try:
        yield
    finally:
        QGuiApplication.restoreOverrideCursor()
