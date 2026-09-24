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

**A sample can be the answer too.**  Somebody launching this for the
first time may own no CIF yet, and "choose a workspace" is a question
about where work goes before there is any work.  Open Sample answers
both at once: the selected workspace, and MOF-5 or one of the others
opened in it.  The chooser only *names* the sample -- :meth:`ask`
returns it beside the workspace and :func:`xtalapp.main.open_window`
opens it once the window exists, through the same
``MainWindow.open_sample`` as File > Open Sample, so it is copied into
the workspace like any other.

**Not reached by the test suite**, and that is deliberate.  It lives
here and is called from :func:`xtalapp.main.main` rather than from
``MainWindow.__init__`` -- every widget test builds a window directly,
and ``tests/conftest.py`` patches ``QDialog.exec`` to raise, so a
chooser inside the constructor would fail the suite entire.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QFont, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

import xtal
from xtal.workspace import NotAWorkspace, Workspace
from xtalapp import samples

#: The path a row carries, and the two halves of what it says.
_PATH = Qt.UserRole + 1
_NAME = Qt.UserRole + 2
_DETAIL = Qt.UserRole + 3

#: Where the side panel's picture and icon are.  ``resources/`` and not
#: ``packaging/``, because this subtree travels with a bundle -- see
#: ``RESOURCES`` in ``packaging/bundle.py`` -- and is drawn by
#: ``packaging/render_chooser_art.py``.
ART = Path(__file__).resolve().parents[2] / "resources" / "chooser"
SIDE_WIDTH = 220
ICON_SIZE = 64


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


class _RecentDelegate(QStyledItemDelegate):
    """One line per workspace: the name in bold, then when and where
    in the muted colour.

    A delegate because a list item's text has one font: the two-line
    rows it replaced put the name on a line of its own to make it stand
    out, which made the list half as long as the dialog could show.
    The folder is what gets elided, in the middle, because both ends
    of a path are the parts that say which one it is.
    """

    GAP = 12

    def sizeHint(self, option, index) -> QSize:
        hint = super().sizeHint(option, index)
        return QSize(hint.width(), max(hint.height(),
                                       option.fontMetrics.height() + 10))

    def paint(self, painter: QPainter, option, index) -> None:
        self.initStyleOption(option, index)
        name, detail = index.data(_NAME), index.data(_DETAIL)
        option.text = ""
        style = option.widget.style() if option.widget else None
        if style is not None:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem,
                              option, painter, option.widget)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        # The colour group the row was drawn in: a dialog that is not
        # the active window draws its selection grey, and the active
        # group's highlighted text is white -- on grey, unreadable.
        group = (QPalette.ColorGroup.Active
                 if option.state & QStyle.StateFlag.State_Active
                 else QPalette.ColorGroup.Inactive)
        rect = option.rect.adjusted(8, 0, -8, 0)
        painter.save()
        bold = QFont(option.font)
        bold.setBold(True)
        painter.setFont(bold)
        ink = option.palette.color(
            group, QPalette.ColorRole.HighlightedText if selected
            else QPalette.ColorRole.Text)
        painter.setPen(ink)
        metrics = painter.fontMetrics()
        name = metrics.elidedText(name, Qt.ElideRight, rect.width())
        painter.drawText(rect, Qt.AlignVCenter | Qt.AlignLeft, name)
        used = metrics.horizontalAdvance(name) + self.GAP

        painter.setFont(option.font)
        muted = QPalette.ColorRole.HighlightedText if selected \
            else QPalette.ColorRole.PlaceholderText
        painter.setPen(option.palette.color(group, muted))
        rest = rect.adjusted(used, 0, 0, 0)
        detail = painter.fontMetrics().elidedText(
            detail, Qt.ElideMiddle, max(rest.width(), 0))
        painter.drawText(rest, Qt.AlignVCenter | Qt.AlignLeft, detail)
        painter.restore()


def _icon(size: int) -> QPixmap:
    """The application icon, drawn from its SVG at ``size``."""
    ratio = 2
    pixmap = QPixmap(size * ratio, size * ratio)
    pixmap.fill(Qt.transparent)
    renderer = QSvgRenderer(str(ART / "app.svg"))
    if renderer.isValid():
        painter = QPainter(pixmap)
        renderer.render(painter, QRectF(0, 0, size * ratio,
                                        size * ratio))
        painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


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
        #: The sample Open Sample named, to be opened once the window
        #: exists.  ``None`` for Continue.
        self.sample: str | None = None

        outer = QHBoxLayout(self)
        outer.addWidget(self._side_panel())
        layout = QVBoxLayout()
        outer.addLayout(layout, 1)
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
        self.list.setItemDelegate(_RecentDelegate(self.list))
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
        row.addWidget(self._sample_button())
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
        self.setMinimumWidth(460 + SIDE_WIDTH)

    def _side_panel(self) -> QWidget:
        """What is about to open: its icon, name and version, and a
        framework of the kind it builds."""
        panel = QWidget()
        panel.setFixedWidth(SIDE_WIDTH)
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 8, 8, 0)

        icon = QLabel()
        icon.setPixmap(_icon(ICON_SIZE))
        icon.setAlignment(Qt.AlignHCenter)
        column.addWidget(icon)

        name = QLabel("Crystal Builder")
        font = name.font()
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() * 1.4)
        name.setFont(font)
        name.setAlignment(Qt.AlignHCenter)
        column.addWidget(name)

        #: The version this launch will open: the About box is one
        #: window further in, and "is this the build I just
        #: installed" is asked here.
        # A development build's version carries its commit after a
        # "+", which is longer than the panel is wide; it goes on a
        # line of its own rather than off the edge.
        self.version = QLabel("Version " + xtal.__version__.replace(
            "+", "\n+", 1))
        self.version.setAlignment(Qt.AlignHCenter)
        self.version.setStyleSheet("color: palette(placeholder-text);")
        column.addWidget(self.version)

        column.addStretch(1)
        picture = QPixmap(str(ART / "framework.png"))
        if not picture.isNull():
            picture.setDevicePixelRatio(
                picture.width() / (SIDE_WIDTH - 8))
            art = QLabel()
            art.setPixmap(picture)
            art.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            column.addWidget(art)
        return panel

    def _sample_button(self) -> QPushButton:
        """Open Sample, into the workspace selected in the list.

        A button with a menu of them, drawn as the platform draws a
        pull-down, in the File menu's two sections.  Not auto-default,
        for the reason New and Open Other are not: Return is Continue.
        """
        self.sample_button = QPushButton("Open Sample")
        self.sample_button.setAutoDefault(False)
        menu = QMenu(self.sample_button)
        present = samples.installed()
        for group, title in samples.GROUPS:
            found = [s for s in present if s.group == group]
            if not found:
                continue
            into = menu
            if group != samples.SHIPPED:
                menu.addSeparator()
                into = QMenu(title, menu)
                menu.addMenu(into)
            for sample in found:
                action = into.addAction(sample.label)
                action.setToolTip(sample.description)
                action.triggered.connect(
                    lambda _checked=False, n=sample.name:
                    self.choose_sample(n))
        self.sample_button.setMenu(menu)
        if not samples.installed():
            self.sample_button.setEnabled(False)
            self.sample_button.setToolTip(samples.MISSING)
        else:
            self.sample_button.setToolTip(
                "Open the selected workspace with one of the "
                "structures that ship with the application")
        return self.sample_button

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
            item = QListWidgetItem(f"{path.name}    {detail}")
            item.setData(_PATH, str(path))
            item.setData(_NAME, path.name)
            item.setData(_DETAIL, detail)
            item.setToolTip(str(path))
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

    def choose_sample(self, name: str) -> None:
        """Open the selected workspace, and name ``name`` to be opened
        in it.  A workspace that cannot be made keeps the dialog open
        and forgets the sample, so that Continue afterwards does not
        open one nobody asked for the second time."""
        self.sample = name
        self._accept()
        if self.workspace is None:
            self.sample = None

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
    def ask(cls, settings, parent=None) -> tuple:
        """``(workspace, sample)``: the workspace to work in and the
        sample to open in it, or ``None`` for either.  A workspace of
        ``None`` means the user quit."""
        dialog = cls(settings, parent)
        if dialog.exec() != QDialog.Accepted:
            return None, None
        return dialog.workspace, dialog.sample
