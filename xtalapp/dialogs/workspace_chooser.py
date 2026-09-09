"""
xtalapp.dialogs.workspace_chooser
=================================
The first thing the application shows: which workspace is this work
going in?

A workspace decides where a run is filed, what Save offers, and which
structures the tree lists, and until now it was never asked about --
a first run made ``~/Crystal Builder`` silently and every launch after
that reopened whatever was last used.  That is fine until somebody
keeps two pieces of work apart, at which point the folder they are in
is the one thing they cannot see and did not choose.

So it is asked, every launch, with the last one already selected: the
answer for somebody who has one workspace is Return, and the answer
for somebody who has four is now askable at all.

**Not reached by the test suite**, and that is deliberate.  It lives
here and is called from :func:`xtalapp.main.main` rather than from
``MainWindow.__init__`` -- every widget test builds a window directly,
and ``tests/conftest.py`` patches ``QDialog.exec`` to raise, so a
chooser inside the constructor would fail the suite entire.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from xtal.workspace import NotAWorkspace, Workspace

#: The path a row carries.
_PATH = Qt.UserRole + 1


def _when(path: Path) -> str:
    """How long ago that folder was last written, said briefly."""
    try:
        stamp = datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return ""
    seconds = (datetime.now() - stamp).total_seconds()
    if seconds < 90:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    if seconds < 7 * 86400:
        return stamp.strftime("%a")
    return stamp.strftime("%d %b")


def _where(path: Path) -> str:
    """The folder it is in, with the home directory as ``~``.

    Written short because it is the second line of a row and the paths
    are long: an absolute path under a temporary or a synced folder
    pushes everything after it out of the dialog.
    """
    parent = path.parent
    try:
        return f"~/{parent.relative_to(Path.home())}".rstrip("/")
    except ValueError:
        return str(parent)


def ask_for_new(parent, settings) -> str:
    """Where to put a workspace that does not exist yet."""
    return QFileDialog.getSaveFileName(
        parent, "New workspace",
        str(settings.default_workspace_root))[0]


def ask_for_existing(parent, settings) -> str:
    """Which folder is the workspace to open."""
    return QFileDialog.getExistingDirectory(
        parent, "Open workspace",
        settings.last_workspace or
        str(settings.default_workspace_root.parent))


class WorkspaceChooser(QDialog):
    """Recent workspaces, and the two ways to name another one."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Crystal Builder")
        self.settings = settings
        #: Set by :meth:`_accept_choice` once a folder has proved to be
        #: a workspace.  The dialog closes on a workspace, never on a
        #: path that might not be one.
        self.workspace: Workspace | None = None

        layout = QVBoxLayout(self)
        heading = QLabel("Choose a workspace")
        heading.setStyleSheet("font-weight: bold;")
        layout.addWidget(heading)
        blurb = QLabel("Structures, calculations and everything they "
                       "leave behind are kept in one folder.")
        blurb.setWordWrap(True)
        layout.addWidget(blurb)

        self.list = QListWidget()
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.ElideMiddle)
        self.list.itemDoubleClicked.connect(lambda _i: self._accept())
        layout.addWidget(self.list, 1)

        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: palette(bright-text);")
        self.error.hide()
        layout.addWidget(self.error)

        row = QHBoxLayout()
        new = QPushButton("New Workspace...")
        new.clicked.connect(self._new)
        other = QPushButton("Open Other...")
        other.clicked.connect(self._other)
        for button in (new, other):
            # Otherwise the first button in the dialog takes Return,
            # and Return is meant to be Continue -- the whole reason
            # the last workspace is selected on the way in.
            button.setAutoDefault(False)
        row.addWidget(new)
        row.addWidget(other)
        row.addStretch(1)
        layout.addLayout(row)

        buttons = QDialogButtonBox()
        # Rejecting this dialog ends the launch, so the button says so
        # rather than saying Cancel: there is nothing behind it to go
        # back to.  Which is also why it must not be the one Return
        # presses -- added first, it takes the default on macOS unless
        # it is told twice not to.
        self.quit = buttons.addButton("Quit",
                                      QDialogButtonBox.RejectRole)
        self.quit.setAutoDefault(False)
        self.quit.setDefault(False)
        self.go = buttons.addButton("Continue",
                                    QDialogButtonBox.AcceptRole)
        self.go.setAutoDefault(True)
        self.go.setDefault(True)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._fill()
        self.list.setFocus()
        self.setMinimumWidth(460)

    # -- the list ------------------------------------------------------

    def _fill(self) -> None:
        """The recent workspaces, with the last one selected.

        A first run has none, so the folder Preferences names is
        offered as a row that does not exist yet -- which keeps the
        default workspace the one-keystroke answer it used to be when
        it was made without asking.
        """
        self.list.clear()
        recent = [Path(p) for p in self.settings.recent_workspaces()]
        if not recent:
            recent = [self.settings.default_workspace_root]
        last = self.settings.last_workspace
        for path in recent:
            # The time first, because the path is what gets elided.
            when = _when(path) if path.is_dir() else "will be created"
            detail = f"{when}    {_where(path)}"
            item = QListWidgetItem(f"{path.name}\n{detail}")
            item.setData(_PATH, str(path))
            self.list.addItem(item)
            if last and Path(last) == path:
                self.list.setCurrentItem(item)
        if self.list.currentRow() < 0:
            self.list.setCurrentRow(0)

    def _chosen(self) -> Path | None:
        item = self.list.currentItem()
        return Path(item.data(_PATH)) if item is not None else None

    # -- the three ways out --------------------------------------------

    def _accept(self) -> None:
        path = self._chosen()
        if path is not None:
            self._accept_choice(path, create=not Workspace.is_workspace(path))

    def _new(self) -> None:
        chosen = ask_for_new(self, self.settings)
        if chosen:
            self._accept_choice(Path(chosen), create=True)

    def _other(self) -> None:
        chosen = ask_for_existing(self, self.settings)
        if chosen:
            self._accept_choice(Path(chosen), create=False)

    def _accept_choice(self, path: Path, create: bool) -> None:
        """Open or make the folder, and close only if that worked.

        The dialog stays open on a failure and says why, because there
        is no window behind it to report into and no workspace to open
        one with.  A folder that cannot be made is a question still
        being asked, not an answer.
        """
        try:
            self.workspace = (Workspace.create(path) if create
                              else Workspace.open(path))
        except (NotAWorkspace, OSError) as exc:
            self.error.setText(f"{path.name}: {exc}")
            self.error.show()
            return
        self.accept()

    @classmethod
    def ask(cls, settings, parent=None) -> Workspace | None:
        """The workspace to work in, or ``None`` if the user quit."""
        dialog = cls(settings, parent)
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.workspace
