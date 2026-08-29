"""
xtalapp.settings
================
Persistent application preferences, on top of QSettings.

Kept to one small class so nothing else in the app has to know the
setting keys, and so tests can point it at a scratch organisation
instead of the user's real preferences.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

ORGANISATION = "CrystalBuilder"
APPLICATION = "CrystalBuilder"
MAX_RECENT = 10


class AppSettings:
    """Window layout, recent files, and view defaults."""

    def __init__(self, organisation=ORGANISATION,
                 application=APPLICATION):
        self._q = QSettings(organisation, application)

    # -- recent files --------------------------------------------------

    def recent_files(self) -> list[str]:
        stored = self._q.value("recent_files", [])
        if isinstance(stored, str):
            stored = [stored]
        return [p for p in (stored or []) if Path(p).exists()]

    def add_recent_file(self, path) -> None:
        path = str(Path(path).resolve())
        files = [p for p in self.recent_files() if p != path]
        files.insert(0, path)
        self._q.setValue("recent_files", files[:MAX_RECENT])

    def clear_recent_files(self) -> None:
        self._q.setValue("recent_files", [])

    # -- directories ---------------------------------------------------

    @property
    def last_directory(self) -> str:
        return str(self._q.value("last_directory", str(Path.home())))

    @last_directory.setter
    def last_directory(self, value) -> None:
        self._q.setValue("last_directory", str(value))

    # -- window state --------------------------------------------------

    def save_window(self, window) -> None:
        self._q.setValue("geometry", window.saveGeometry())
        self._q.setValue("window_state", window.saveState())

    def restore_window(self, window) -> None:
        geometry = self._q.value("geometry")
        state = self._q.value("window_state")
        if geometry:
            window.restoreGeometry(geometry)
        if state:
            window.restoreState(state)

    # -- view defaults -------------------------------------------------

    def default_view(self) -> dict:
        return {
            "style": str(self._q.value("view/style", "ball_stick")),
            "background": tuple(
                int(v) for v in self._q.value(
                    "view/background", (255, 255, 255))),
        }

    def set_default_view(self, style=None, background=None) -> None:
        if style is not None:
            self._q.setValue("view/style", style)
        if background is not None:
            self._q.setValue("view/background", tuple(background))

    def sync(self) -> None:
        self._q.sync()
