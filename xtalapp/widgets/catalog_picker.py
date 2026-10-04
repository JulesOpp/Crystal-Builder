"""
xtalapp.widgets.catalog_picker
==============================
One choice out of a long catalogue grouped into families: a family
box, the box of what is in it, and a search line over everything.

ORCA has 440 basis sets in 22 families and 95 functionals in nine.
Two boxes find a thing whose family is known; the search finds one
whose name is -- "tzvp" offers every TZVP in every family, and
picking one sets both boxes.  The completer matches anywhere in the
line, not only at the start, because nobody types "Karlsruhe def2"
to reach def2-TZVP.
"""

from __future__ import annotations

from PySide6.QtCore import QStringListModel, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QHBoxLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

ARROW = " \N{BLACK RIGHT-POINTING SMALL TRIANGLE} "


class CatalogPicker(QWidget):
    """``families`` is ``{family: entries}``; an entry has a ``key``
    and, optionally, a ``label`` shown beside it."""

    changed = Signal(str)

    def __init__(self, families: dict, parent=None, placeholder=""):
        super().__init__(parent)
        self._families = {name: tuple(entries)
                          for name, entries in families.items()
                          if entries}
        self._by_line = {}
        for family, entries in self._families.items():
            for entry in entries:
                self._by_line[self._line(family, entry)] = (family,
                                                            entry.key)

        self.family = QComboBox()
        self.family.addItems(list(self._families))
        self.item = QComboBox()
        self.search = QLineEdit()
        self.search.setPlaceholderText(placeholder or "Search")
        self.search.setClearButtonEnabled(True)
        # Parented and held: a model handed to QCompleter inline has
        # no Python owner, is collected, and the completer then
        # searches nothing -- no popup, and no error to say why.
        self.lines = QStringListModel(list(self._by_line), self)
        completer = QCompleter(self.lines, self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setMaxVisibleItems(15)
        completer.activated.connect(self._picked)
        self.search.setCompleter(completer)
        self.search.returnPressed.connect(self._entered)
        self.completer = completer

        boxes = QHBoxLayout()
        boxes.setContentsMargins(0, 0, 0, 0)
        boxes.addWidget(self.family, 1)
        boxes.addWidget(self.item, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(boxes)
        layout.addWidget(self.search)

        self.family.currentIndexChanged.connect(self._fill)
        self.item.currentIndexChanged.connect(self._item_changed)
        self._fill()

    @staticmethod
    def _line(family, entry) -> str:
        label = getattr(entry, "label", "")
        line = f"{family}{ARROW}{entry.key}"
        return f"{line} \N{EM DASH} {label}" if label else line

    # -- state ---------------------------------------------------------

    def key(self) -> str:
        return self.item.currentData() or ""

    def set_key(self, key: str) -> bool:
        """Show ``key``, in its family; ``False`` if there is none."""
        wanted = str(key or "").lower()
        for family, entries in self._families.items():
            for entry in entries:
                if entry.key.lower() == wanted:
                    self._show(family, entry.key)
                    return True
        return False

    def _show(self, family, key) -> None:
        self.family.setCurrentText(family)     # refills the items
        index = self.item.findData(key)
        if index >= 0:
            self.item.setCurrentIndex(index)

    # -- reactions -----------------------------------------------------

    def _fill(self) -> None:
        family = self.family.currentText()
        self.item.blockSignals(True)
        self.item.clear()
        for entry in self._families.get(family, ()):
            label = getattr(entry, "label", "")
            self.item.addItem(entry.key, entry.key)
            if label:
                self.item.setItemData(self.item.count() - 1, label,
                                      Qt.ToolTipRole)
        self.item.blockSignals(False)
        self._item_changed()

    def _item_changed(self, *_args) -> None:
        self.changed.emit(self.key())

    def _picked(self, line: str) -> None:
        found = self._by_line.get(line)
        if found is not None:
            self._show(*found)
            # Once the completer has written its line into the box,
            # which it does after this slot returns.
            QTimer.singleShot(0, self.search.clear)

    def _entered(self) -> None:
        """Return in the search line: the exact key if it is one, else
        the first thing the completer offers."""
        text = self.search.text().strip()
        if self.set_key(text):
            self.search.clear()
            return
        matches = [line for line in self._by_line
                   if text.lower() in line.lower()]
        if matches:
            self._picked(matches[0])
