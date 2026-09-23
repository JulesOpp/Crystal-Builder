"""
xtalapp.docks.workspace
=======================
The left bar: the workspace, and the filesystem beside it.

Before this the left bar was a ``QFileSystemModel`` filtered to
structure extensions.  A directory listing cannot express *this run
belongs to that structure*, and that is the one thing the tree now has
to say, so this is a real model over a :class:`xtal.workspace.Workspace`
rather than over a folder::

    MFU4l                            the structure, as opened
    ├── MFU4l.cif                    a copy, so the workspace is whole
    ├── uff-optimise-001
    │   ├── final.cif                the relaxed structure
    │   ├── trajectory.extxyz        every step
    │   └── run.log                  what happened, in order
    └── uff-single-point-002
        └── run.log

The filesystem browser stays, on the other page of the stack: opening a
file from somewhere else is still how everything starts.

**Activating a node says what it is, not what it is called.**  The
signal carries the artefact's kind, because a ``.cif`` that is a run's
output and a ``.cif`` that is the input want the same viewer and
different labelling, which an extension cannot tell you.  What each
kind opens is the window's business (``MainWindow.open_artifact``) and
not the tree's.

The tree is rebuilt from the directory rather than kept in step with
it.  A workspace is a few dozen folders; the filesystem is the
authority on what is in it, and a model that cached would be a second
answer to the same question -- the one that goes stale when somebody
moves a folder in Finder, which is a supported thing to do.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from xtal.workspace import Workspace
from xtalapp.docks.filetree import FileBrowser

# Role carrying (kind, path) on every row.  A tuple rather than two
# roles because every consumer wants both or neither.
ARTIFACT_ROLE = Qt.UserRole + 1

# What the tree calls each kind, where the file name alone would not
# say.  "final.cif" is a structure and so is "MFU4l.cif", and which is
# which is the whole point of the tree.
KIND_LABELS = {
    "structure": "",
    "final": "final structure",
    "trajectory": "trajectory",
    "log": "log",
    "image": "plot",
    "report": "results",
    "project": "session",
    "file": "",
}


class WorkspaceTree(QTreeView):
    """The structures of a workspace, and the runs underneath them."""

    artifactActivated = Signal(str, str)        # kind, path
    contextRequested = Signal(object)           # global position

    def __init__(self, parent=None):
        super().__init__(parent)
        self.workspace: Workspace | None = None
        #: The file the current tab is, drawn bold.
        self.open_path: Path | None = None
        self.model_ = QStandardItemModel(self)
        self.setModel(self.model_)
        self.setHeaderHidden(True)
        self.activated.connect(self._on_activated)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context)

    # -- building ------------------------------------------------------

    def set_workspace(self, workspace: Workspace | None) -> None:
        self.workspace = workspace
        self.refresh()

    def refresh(self) -> None:
        """Read the workspace again and rebuild.

        Expansion is preserved by path, so a run folder the user opened
        does not fold itself back up every time a run finishes.  So are
        the selection and the scroll position: opening a file from the
        tree rebuilds it, and a cleared model puts the view back at the
        top -- away from the row that was just double-clicked.
        """
        expanded = self._expanded_paths()
        scroll = self.verticalScrollBar().value()
        current = self._payload(self.currentIndex())
        self.model_.clear()
        root = self.model_.invisibleRootItem()
        if self.workspace is None:
            root.appendRow(_row("No workspace open", None, None,
                                enabled=False))
            return
        entries = self.workspace.entries()
        if not entries:
            root.appendRow(_row("Nothing in this workspace yet", None,
                                None, enabled=False))
        for entry in entries:
            root.appendRow(self._entry_item(entry))
        self._restore_expanded(expanded or self._default_expanded())
        self._mark_open()
        if current is not None:
            found = self._find(current[1])
            if found is not None:
                self.setCurrentIndex(found)
        # The scroll range is laid out lazily; without this the value
        # is clamped to the empty model's range of nothing.
        self.doItemsLayout()
        self.verticalScrollBar().setValue(scroll)

    def _entry_item(self, entry) -> QStandardItem:
        item = _row(entry.name, "entry", entry.path)[0]
        for artifact in entry.files():
            item.appendRow(_row(_label(artifact), artifact.kind,
                                artifact.path))
        for run in entry.runs():
            item.appendRow(self._run_item(run))
        return item

    def _run_item(self, run) -> QStandardItem:
        item = _row(run.name, "run", run.path)[0]
        item.setToolTip(run.label)
        for artifact in run.artifacts():
            item.appendRow(_row(_label(artifact), artifact.kind,
                                artifact.path))
        if not run.artifacts():
            item.appendRow(_row("(empty)", None, None, enabled=False))
        return item

    # -- what is open --------------------------------------------------

    def _walk(self):
        stack = [self.model_.index(r, 0)
                 for r in range(self.model_.rowCount())]
        while stack:
            index = stack.pop()
            yield index
            for row in range(self.model_.rowCount(index)):
                stack.append(self.model_.index(row, 0, index))

    def _expanded_paths(self) -> set:
        return {str(self.model_.itemFromIndex(i).data(ARTIFACT_ROLE)[1])
                for i in self._walk()
                if self.isExpanded(i)
                and self.model_.itemFromIndex(i).data(ARTIFACT_ROLE)}

    def _default_expanded(self) -> set:
        """Entries open, runs closed.

        A workspace with fifty runs in it opened fully is a wall of
        file names; the structure names are the level anybody is
        looking for.
        """
        return {str(entry.path) for entry in self.workspace.entries()} \
            if self.workspace else set()

    def _restore_expanded(self, paths: set) -> None:
        for index in self._walk():
            payload = self.model_.itemFromIndex(index).data(
                ARTIFACT_ROLE)
            if payload and str(payload[1]) in paths:
                self.setExpanded(index, True)

    def _payload(self, index):
        item = self.model_.itemFromIndex(index) if index.isValid() \
            else None
        return item.data(ARTIFACT_ROLE) if item is not None else None

    def _find(self, path):
        wanted = str(path)
        for index in self._walk():
            payload = self._payload(index)
            if payload and str(payload[1]) == wanted:
                return index
        return None

    def select_path(self, path) -> None:
        """Highlight a path, if it is in the tree."""
        index = self._find(path)
        if index is not None:
            self.setCurrentIndex(index)
            self.scrollTo(index)

    def set_open_path(self, path) -> None:
        """Mark the file the current tab is, and select it.

        Bold rather than only selected, because a selection is the
        user's to move and the question "which of these is the one I
        am looking at" should still have an answer after they have.
        The entry above it is bold too, so the answer survives the
        entry being folded.
        """
        self.open_path = _resolved(path)
        found = self._mark_open()
        if found is not None:
            self.setCurrentIndex(found)
            self.scrollTo(found)

    def _mark_open(self):
        """Embolden the open file and its entry; the row, or None."""
        found = None
        for index in self._walk():
            payload = self._payload(index)
            if (self.open_path is not None and payload
                    and payload[0] not in ("entry", "run")
                    and _resolved(payload[1]) == self.open_path):
                found = index
        # The file itself, and the top-level entry it sits under.
        top = found
        while top is not None and top.parent().isValid():
            top = top.parent()
        for index in self._walk():
            item = self.model_.itemFromIndex(index)
            wanted = found is not None and index in (found, top)
            font = item.font()
            if font.bold() != wanted:
                font.setBold(wanted)
                item.setFont(font)
        return found

    # -- activation ----------------------------------------------------

    def selected_artifact(self):
        """``(kind, path)`` of the highlighted row, or ``None``."""
        payload = self._payload(self.currentIndex())
        return (str(payload[0]), Path(payload[1])) if payload else None

    def _on_context(self, position) -> None:
        """Right-click: pick the row under the cursor, then ask.

        The row and not the selection: a menu about whatever was last
        clicked, raised over something else, is how the wrong folder
        goes in the bin.
        """
        index = self.indexAt(position)
        if index.isValid():
            self.setCurrentIndex(index)
        if self.selected_artifact() is not None:
            self.contextRequested.emit(self.viewport().mapToGlobal(position))

    def _on_activated(self, index) -> None:
        item = self.model_.itemFromIndex(index)
        payload = item.data(ARTIFACT_ROLE) if item is not None else None
        if not payload:
            return
        kind, path = payload
        if kind in ("entry", "run"):
            self.setExpanded(index, not self.isExpanded(index))
            return
        self.artifactActivated.emit(str(kind), str(path))


def _resolved(path) -> Path | None:
    if not path:
        return None
    try:
        return Path(path).resolve()
    except OSError:                                 # pragma: no cover
        return Path(path)


def _label(artifact) -> str:
    note = KIND_LABELS.get(artifact.kind, "")
    return (f"{artifact.path.name}   ({note})" if note
            else artifact.path.name)


def _row(text: str, kind, path, enabled: bool = True) -> list:
    item = QStandardItem(text)
    item.setEditable(False)
    if kind is not None and path is not None:
        item.setData((kind, str(path)), ARTIFACT_ROLE)
    item.setEnabled(enabled)
    return [item]


class WorkspaceDock(QDockWidget):
    """The workspace tree, with the filesystem browser beside it."""

    artifactActivated = Signal(str, str)        # kind, path
    fileActivated = Signal(str)
    workspaceRequested = Signal(str)            # "open" | "new"
    contextRequested = Signal(object)           # global position

    def __init__(self, root=None, parent=None):
        super().__init__("Workspace", parent)
        # The object name is what a saved window layout is keyed on.
        # This dock replaced the file tree in the same place, so it
        # keeps the old name and a layout saved before Phase C still
        # restores.
        self.setObjectName("FileTreeDock")
        self.setAllowedAreas(Qt.LeftDockWidgetArea |
                             Qt.RightDockWidgetArea)

        self.tree = WorkspaceTree()
        self.tree.artifactActivated.connect(self.artifactActivated)
        self.tree.contextRequested.connect(self.contextRequested)
        self.browser = FileBrowser(root)
        self.browser.fileActivated.connect(self.fileActivated)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.tree)
        self.stack.addWidget(self.browser)
        # Both pages scroll, so the stack need not insist on the
        # browser's header-plus-tree: that alone put the panel's
        # minimum height at 196 px of the 200 a dock may ask for, and
        # over it wherever the font is larger.
        self.stack.setMinimumHeight(60)

        self.name_label = QLabel("No workspace")
        self.name_label.setWordWrap(True)
        # A one-word folder name cannot wrap, so a long one held the
        # left column at its width.  Clipped instead; the tooltip
        # already carries the full path.
        self.name_label.setMinimumWidth(1)

        self.switcher = QToolButton()
        self.switcher.setText("Workspace")
        self.switcher.setPopupMode(QToolButton.InstantPopup)
        self.menu = QMenu(self.switcher)
        self.switcher.setMenu(self.menu)
        self._rebuild_menu()

        self.mode_button = QPushButton("Browse files")
        self.mode_button.setCheckable(True)
        self.mode_button.setToolTip(
            "Look at the filesystem instead of the workspace -- which "
            "is how a structure from somewhere else gets opened")
        self.mode_button.toggled.connect(self.set_browsing)

        header = QHBoxLayout()
        header.setContentsMargins(6, 4, 6, 4)
        header.addWidget(self.name_label, 1)
        header.addWidget(self.switcher)

        footer = QHBoxLayout()
        footer.setContentsMargins(6, 0, 6, 4)
        footer.addWidget(self.mode_button)

        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(2)
        body.addLayout(header)
        body.addWidget(self.stack, 1)
        body.addLayout(footer)

        container = QWidget()
        container.setLayout(body)
        self.setWidget(container)

    # -- the two modes -------------------------------------------------

    def set_browsing(self, browsing: bool) -> None:
        self.stack.setCurrentIndex(1 if browsing else 0)
        self.mode_button.setChecked(browsing)
        self.mode_button.setText("Show the workspace" if browsing
                                 else "Browse files")

    @property
    def browsing(self) -> bool:
        return self.stack.currentIndex() == 1

    # -- the workspace -------------------------------------------------

    def set_workspace(self, workspace: Workspace | None,
                      recent=()) -> None:
        self.tree.set_workspace(workspace)
        self.name_label.setText(workspace.root.name if workspace
                                else "No workspace")
        self.name_label.setToolTip(str(workspace.root) if workspace
                                   else "")
        self._rebuild_menu(recent)
        if workspace is not None:
            self.set_browsing(False)

    def refresh(self) -> None:
        self.tree.refresh()

    def _rebuild_menu(self, recent=()) -> None:
        self.menu.clear()
        self.menu.addAction(
            "Open Workspace...",
            lambda: self.workspaceRequested.emit("open"))
        self.menu.addAction(
            "New Workspace...",
            lambda: self.workspaceRequested.emit("new"))
        paths = [p for p in recent if p]
        if paths:
            self.menu.addSeparator()
            for path in paths:
                self.menu.addAction(
                    Path(path).name,
                    lambda checked=False, p=path:
                    self.workspaceRequested.emit(str(p))
                ).setToolTip(str(path))

    # -- the filesystem side, which the window still drives -------------
    #
    # There are two trees in this dock now, so nothing here pretends
    # there is one: the workspace is ``dock.tree`` and the filesystem
    # is ``dock.browser.tree``.  Only the root is unambiguous, because
    # only the browser has one.

    def set_root(self, path) -> None:
        self.browser.set_root(path)

    @property
    def root(self) -> Path:
        return self.browser.root
