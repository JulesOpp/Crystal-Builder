"""
xtalapp.settings
================
Persistent application preferences, on top of QSettings.

Kept to one small class so nothing else in the app has to know the
setting keys, and so tests can point it at a scratch organisation
instead of the user's real preferences.
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QRect, QSettings
from PySide6.QtGui import QGuiApplication

ORGANISATION = "CrystalBuilder"
APPLICATION = "CrystalBuilder"
MAX_RECENT = 10

# How much of the screen a fresh window takes, and the size beyond
# which taking more of it stops helping.  A fixed pixel size is a guess
# about somebody else's monitor: 1280x820 is taller than a 1280x800
# laptop screen before a single dock has asked for room.
DEFAULT_FRACTION = 0.85
MAX_DEFAULT_SIZE = (1600, 1000)


def _as_bool(value) -> bool:
    """QSettings hands booleans back as the strings it wrote them as on
    some platforms, and ``bool("false")`` is True."""
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes")
    return bool(value)


def screen_area(window=None) -> QRect | None:
    """The usable rectangle of the screen ``window`` is on.

    Falls back to the primary screen, and to ``None`` where there is no
    screen at all -- an offscreen test platform, or a headless CI box.
    """
    screen = None
    if window is not None:
        handle = window.windowHandle()
        if handle is not None:
            screen = handle.screen()
        if screen is None:
            screen = QGuiApplication.screenAt(window.pos())
    if screen is None:
        screen = QGuiApplication.primaryScreen()
    return None if screen is None else screen.availableGeometry()


def default_size(window=None) -> tuple[int, int]:
    """A starting size that fits the screen it will open on."""
    area = screen_area(window)
    if area is None or area.isEmpty():
        return MAX_DEFAULT_SIZE
    return (min(MAX_DEFAULT_SIZE[0], int(area.width() * DEFAULT_FRACTION)),
            min(MAX_DEFAULT_SIZE[1], int(area.height() * DEFAULT_FRACTION)))


def fit_to_screen(window) -> None:
    """Bring a window back onto the display, shrinking it if it must.

    This matters most for a *restored* geometry.  A layout saved on an
    external monitor comes back off-screen on the laptop, and because
    it is saved again on quit there is no way out of it short of
    deleting the preferences by hand.  Clamping on the way in is the
    only place that can be fixed.
    """
    area = screen_area(window)
    if area is None or area.isEmpty():
        return
    frame = window.frameGeometry()
    inner = window.geometry()
    # The frame includes the title bar; setGeometry does not.  Keep the
    # difference so clamping the frame does not walk the window down
    # the screen by one title bar every time it runs.
    margins = (inner.left() - frame.left(), inner.top() - frame.top(),
               frame.right() - inner.right(),
               frame.bottom() - inner.bottom())
    if area.contains(frame):
        return
    frame.setSize(frame.size().boundedTo(area.size()))
    if frame.right() > area.right():
        frame.moveRight(area.right())
    if frame.bottom() > area.bottom():
        frame.moveBottom(area.bottom())
    if frame.left() < area.left():
        frame.moveLeft(area.left())
    if frame.top() < area.top():
        frame.moveTop(area.top())
    window.setGeometry(frame.adjusted(margins[0], margins[1],
                                      -margins[2], -margins[3]))


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
        """Put back the saved layout, then make sure it is on screen."""
        geometry = self._q.value("geometry")
        state = self._q.value("window_state")
        if geometry:
            window.restoreGeometry(geometry)
        if state:
            window.restoreState(state)
        fit_to_screen(window)

    def clear_window(self) -> None:
        """Forget the saved layout, for ``Window > Reset layout``.

        Without this a layout that went wrong once is permanent: the
        bad state is what gets saved on quit, and restored on start.
        """
        self._q.remove("geometry")
        self._q.remove("window_state")

    # -- how often a running calculation redraws ------------------------

    @property
    def preview_interval(self) -> int:
        """Milliseconds between redraws while a calculation runs.

        0 draws every step, -1 draws none of them.
        """
        return int(self._q.value("preview_interval", 50))

    @preview_interval.setter
    def preview_interval(self, value) -> None:
        self._q.setValue("preview_interval", int(value))

    # -- bonding -------------------------------------------------------

    @property
    def bonds_follow_geometry(self) -> bool:
        """Re-perceive the bonds after every edit that moves an atom.

        Off, which is the behaviour that was asked for: bonds appearing
        and disappearing under a hand that is dragging one atom, or
        under a relaxation, is what ``Structure > Recalculate bonds``
        exists to be the deliberate alternative to.  It is a preference
        rather than a rule because the opposite is what someone
        building a molecule by hand wants -- drag two atoms together
        and see the bond form.

        It follows *committed* edits only.  A preview -- the geometry a
        running optimisation is drawing -- is not an edit, and
        re-perceiving two hundred times a run would cost more than the
        run.
        """
        return _as_bool(self._q.value("bonds/follow_geometry", False))

    @bonds_follow_geometry.setter
    def bonds_follow_geometry(self, value) -> None:
        self._q.setValue("bonds/follow_geometry", bool(value))

    def default_bond_rules(self) -> dict:
        """Perception criteria for a newly opened structure.

        A structure carries its own rules and they travel with the
        project; this is only what a document that has never had them
        set starts from.
        """
        stored = self._q.value("bonds/default_rules", "")
        if not stored:
            return {}
        try:
            return dict(json.loads(str(stored)))
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}

    def set_default_bond_rules(self, rules: dict | None) -> None:
        if not rules:
            self._q.remove("bonds/default_rules")
        else:
            self._q.setValue("bonds/default_rules", json.dumps(rules))

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
