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

#: What the New Workspace dialog suggests when Preferences has not
#: been given somewhere else.
BUILT_IN_WORKSPACE_ROOT = Path.home() / "Crystal Builder"

#: What the application does with an empty window when it starts, in
#: the order Preferences offers them.  ``empty`` is the default and is
#: what it has always done.
STARTUP_ACTIONS = ("empty", "recent", "sample")

#: The sample opened by ``startup/action = sample`` when none has been
#: chosen -- the name of an entry in :mod:`xtalapp.samples`.
DEFAULT_STARTUP_SAMPLE = "mof5"


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

    # -- the MOF builder's own folders ---------------------------------
    #
    # PORMAKE's database is a folder of ``.cgd`` nets and a folder of
    # ``.xyz`` building blocks, so "a user's own building block" is a
    # file they drop in a folder rather than a change to this
    # application.  These two are remembered exactly as the last
    # directory is, and for the same reason: a folder found once
    # should not have to be found again next session.

    @property
    def mof_topology_dir(self) -> str:
        return str(self._q.value("mof/topology_dir", "") or "")

    @mof_topology_dir.setter
    def mof_topology_dir(self, value) -> None:
        self._set_or_clear("mof/topology_dir", value)

    @property
    def mof_bb_dir(self) -> str:
        return str(self._q.value("mof/bb_dir", "") or "")

    @mof_bb_dir.setter
    def mof_bb_dir(self, value) -> None:
        self._set_or_clear("mof/bb_dir", value)

    def _set_or_clear(self, key: str, value) -> None:
        """Store a setting, or forget it when it is emptied.

        An empty string stored is not the same as nothing stored: the
        first would have to be told apart from a default every time it
        is read.
        """
        if str(value or "").strip():
            self._q.setValue(key, str(value))
        else:
            self._q.remove(key)

    # -- workspaces ----------------------------------------------------
    #
    # The workspace is remembered and reopened exactly as the last
    # directory is.  What is *not* done is guessing one: a scratch
    # folder cleaned on exit will one day throw away a six-hour run,
    # and a folder chosen under ~/Library/Application Support is one
    # nobody can find in Finder.  So the application asks once and
    # remembers the answer.

    @property
    def last_workspace(self) -> str:
        return str(self._q.value("workspace/last", "") or "")

    @last_workspace.setter
    def last_workspace(self, value) -> None:
        if value:
            self._q.setValue("workspace/last", str(value))
        else:
            self._q.remove("workspace/last")

    def recent_workspaces(self) -> list[str]:
        stored = self._q.value("workspace/recent", [])
        if isinstance(stored, str):
            stored = [stored]
        return [p for p in (stored or []) if Path(p).is_dir()]

    def add_recent_workspace(self, path) -> None:
        path = str(Path(path).resolve())
        paths = [p for p in self.recent_workspaces() if p != path]
        paths.insert(0, path)
        self._q.setValue("workspace/recent", paths[:MAX_RECENT])

    @property
    def auto_workspace(self) -> bool:
        """Make a workspace beside a structure that is opened without
        one.

        Off.  A folder created behind somebody's back is one they find
        later and do not recognise, and the application creating
        directories next to every file anybody opens is worse than the
        problem it solves.  With no workspace open a structure still
        opens and still runs; what it does not do is leave anything
        behind, and the status bar says so once rather than asking a
        question the user has to dismiss on every file.
        """
        return _as_bool(self._q.value("workspace/auto", False))

    @auto_workspace.setter
    def auto_workspace(self, value) -> None:
        self._q.setValue("workspace/auto", bool(value))

    @property
    def default_workspace_root(self) -> Path:
        """What the New Workspace dialog suggests.

        Under the home folder, because a workspace is the user's own
        directory of runs and belongs somewhere they can find it.
        Settable from Preferences for the person who keeps their work
        on another disk, and stored rather than guessed so that answer
        survives the session it was given in.
        """
        stored = str(self._q.value("workspace/root", "") or "")
        return Path(stored) if stored else BUILT_IN_WORKSPACE_ROOT

    @default_workspace_root.setter
    def default_workspace_root(self, value) -> None:
        # Emptied means "back to the built-in one", which is why this
        # forgets the key rather than storing the path it would have
        # answered with -- a stored copy of the default would not
        # follow a home folder that moved.
        self._set_or_clear("workspace/root", value)

    # -- what the application does when it starts -----------------------

    @property
    def startup_action(self) -> str:
        """Empty window, the last file back, or a sample.

        ``empty`` is the default and is what this application has
        always done.  The other two exist because a packaged build's
        first window is the whole of its first impression: somebody
        who works on one structure for a week wants it back, and
        somebody who has just installed it may not own a CIF yet.

        An unrecognised value -- a preference written by a later
        version, then opened by this one -- reads as ``empty``, which
        is the answer that cannot surprise anybody.
        """
        stored = str(self._q.value("startup/action", "empty"))
        return stored if stored in STARTUP_ACTIONS else "empty"

    @startup_action.setter
    def startup_action(self, value) -> None:
        self._q.setValue("startup/action", str(value))

    @property
    def startup_sample(self) -> str:
        """Which sample ``startup_action = "sample"`` opens.

        Checked against the catalogue on the way out, so a name that
        no longer exists -- a sample renamed between versions -- opens
        the default one instead of failing the launch.
        """
        from xtalapp import samples
        stored = str(self._q.value("startup/sample",
                                   DEFAULT_STARTUP_SAMPLE)
                     or DEFAULT_STARTUP_SAMPLE)
        known = [s.name for s in samples.SAMPLES]
        return stored if stored in known else DEFAULT_STARTUP_SAMPLE

    @startup_sample.setter
    def startup_sample(self, value) -> None:
        self._set_or_clear("startup/sample", value)

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
