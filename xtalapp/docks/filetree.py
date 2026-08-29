"""
xtalapp.docks.filetree
======================
The left bar: a filesystem tree filtered to structure files.

The filter comes from the format registry, so a format added in
``xtal.io`` shows up here without this file changing.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDir, Qt, Signal
from PySide6.QtWidgets import (
    QDockWidget,
    QFileSystemModel,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from xtal.io import FORMATS


def structure_globs() -> list[str]:
    """``["*.cif", "*.xyz", ...]`` from the registry."""
    globs = []
    for fmt in FORMATS:
        if fmt.can_read:
            globs.extend(f"*{ext}" for ext in fmt.extensions)
    return sorted(set(globs))


class FileTreeDock(QDockWidget):
    """Browse a directory and open structures from it."""

    fileActivated = Signal(str)

    def __init__(self, root=None, parent=None):
        super().__init__("Files", parent)
        self.setObjectName("FileTreeDock")
        self.setAllowedAreas(Qt.LeftDockWidgetArea |
                             Qt.RightDockWidgetArea)

        self.model = QFileSystemModel(self)
        self.model.setNameFilters(structure_globs())
        self.model.setNameFilterDisables(False)   # hide, don't grey out
        self.model.setFilter(QDir.AllDirs | QDir.Files |
                             QDir.NoDotAndDotDot)

        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setHeaderHidden(True)
        for column in range(1, self.model.columnCount()):
            self.tree.hideColumn(column)          # name only
        self.tree.doubleClicked.connect(self._on_activated)
        self.tree.activated.connect(self._on_activated)

        self.path_label = QLabel()
        self.path_label.setWordWrap(True)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self.choose_directory)

        header = QHBoxLayout()
        header.setContentsMargins(6, 4, 6, 4)
        header.addWidget(self.path_label, 1)
        header.addWidget(browse)

        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(2)
        body.addLayout(header)
        body.addWidget(self.tree, 1)

        container = QWidget()
        container.setLayout(body)
        self.setWidget(container)

        self.set_root(root or Path.home())

    def set_root(self, path) -> None:
        path = Path(path)
        if path.is_file():
            path = path.parent
        self.model.setRootPath(str(path))
        self.tree.setRootIndex(self.model.index(str(path)))
        self.path_label.setText(str(path))
        self._root = path

    @property
    def root(self) -> Path:
        return self._root

    def choose_directory(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose a folder", str(self._root))
        if chosen:
            self.set_root(chosen)

    def _on_activated(self, index) -> None:
        path = Path(self.model.filePath(index))
        if path.is_dir():
            self.set_root(path)
        else:
            self.fileActivated.emit(str(path))
