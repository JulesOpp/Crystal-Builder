"""
xtalapp.widgets.net_search
==========================
The four MOF+ fields over a list of nets, shared by the MOF builder
and the Net builder.

The two dialogs look at the same nets from different ends, and a
person who has learned to search one has learned the other -- which
is only true while they are the same widget.  So the fields, the
2D / 3D boxes, what a row carries and how a row is hidden all live
here, and the dialogs own nothing but the list itself.

**A field that cannot be read keeps the list as it was.**  Emptying
it would say "no net is like that", which is a claim about nets; a
red box and the reason beneath it is a claim about the typing, and
the typing is what was wrong.  The query is in
:mod:`xtal.analysis.netsearch`; this is its face.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from xtal.analysis.netsearch import NetFacts, NetQuery, NetQueryError
from xtalapp.widgets.tone import WARNING, set_tone

#: Where a row keeps its name, what it is matched on, and whether it
#: is a layer.  The name at ``UserRole`` is what both dialogs have
#: always selected by.
NAME_ROLE = Qt.UserRole
FACTS_ROLE = Qt.UserRole + 1
LAYER_ROLE = Qt.UserRole + 2

#: The border a field it cannot read is given; the reason is in the
#: note beneath; its colour is the warning tone every other one here
#: uses (:mod:`xtalapp.widgets.tone`).
_UNREAD = "QLineEdit { border: 1px solid #b3261e; }"


def add_row(nets: QListWidget, text: str, facts: NetFacts,
            layer: bool) -> QListWidgetItem:
    """One row of a net list, carrying what :meth:`NetSearch.narrow`
    matches it on."""
    item = QListWidgetItem(text)
    item.setData(NAME_ROLE, facts.name)
    item.setData(FACTS_ROLE, facts)
    item.setData(LAYER_ROLE, bool(layer))
    nets.addItem(item)
    return item


class NetSearch(QWidget):
    """Name, coordination (exclusive or not), group number and
    transitivity, and which periodicities to list."""

    #: Something was typed or ticked; ask :meth:`narrow` again.
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.name = QLineEdit(self)
        self.name.setPlaceholderText("Name -- pcu, dia, hcb")
        self.coordination = QLineEdit(self)
        self.coordination.setPlaceholderText("3,6")
        self.coordination.setToolTip(
            "Coordination numbers the net has, like 3,6.  With "
            "Exclusive, it has those and no others.")
        self.exclusive = QCheckBox("Exclusive", self)
        self.exclusive.setToolTip(
            "Only nets whose vertices have exactly the numbers given")
        self.number = QLineEdit(self)
        self.number.setPlaceholderText("225 or 221-230")
        self.number.setToolTip(
            "Space group number, a list, or a range.  A layer net "
            "answers to its plane group number, 1 to 17 -- hcb is "
            "17.")
        self.transitivity = QLineEdit(self)
        self.transitivity.setPlaceholderText("p q r s, * for any")
        self.transitivity.setToolTip(
            "Kinds of vertex, edge, face and tile, like 1 1 1 1 or "
            "11, as the RCSR gives them.  A layer has no tiles, and "
            "a net with no tiling on record has no faces or tiles "
            "either; there r and s match only *.")
        self._tips = {field: field.toolTip() for field in self._fields()}

        # Both ticked is both; the counts say whether the second kind
        # is worth asking for at all.
        self.three_d = QCheckBox(self)
        self.three_d.setToolTip("Nets periodic in three directions")
        self.two_d = QCheckBox(self)
        self.two_d.setToolTip(
            "Layer nets, periodic in two directions and stacked "
            "along c -- the RCSR's, such as hcb for Ni3(HITP)2")
        for box in (self.three_d, self.two_d):
            box.setChecked(True)
            box.toggled.connect(self._on_dimension)

        self.note = QLabel(self)
        self.note.setWordWrap(True)
        set_tone(self.note, WARNING)
        self.note.hide()

        for field in self._fields():
            field.setClearButtonEnabled(True)
            field.textChanged.connect(self._on_edit)
        self.exclusive.toggled.connect(self._on_edit)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.addWidget(self.name, 0, 0, 1, 4)
        grid.addWidget(QLabel("Coordination", self), 1, 0)
        grid.addWidget(self.coordination, 1, 1)
        grid.addWidget(self.exclusive, 1, 2, 1, 2)
        grid.addWidget(QLabel("Spg #", self), 2, 0)
        grid.addWidget(self.number, 2, 1)
        grid.addWidget(QLabel("Transitivity", self), 2, 2)
        grid.addWidget(self.transitivity, 2, 3)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        kinds = QHBoxLayout()
        kinds.setContentsMargins(0, 0, 0, 0)
        kinds.addWidget(self.three_d)
        kinds.addWidget(self.two_d)
        kinds.addStretch(1)

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.addLayout(grid)
        column.addLayout(kinds)
        column.addWidget(self.note)

        self._query = NetQuery()

    def _fields(self) -> tuple[QLineEdit, ...]:
        return (self.name, self.coordination, self.number,
                self.transitivity)

    # -- reading -------------------------------------------------------

    def query(self) -> NetQuery:
        """The last query that could be read."""
        return self._query

    def dimensions(self) -> tuple[bool, bool]:
        return self.three_d.isChecked(), self.two_d.isChecked()

    def unread(self) -> str:
        """The field that could not be read, or ``""``."""
        for key, field in self._by_key().items():
            if field.styleSheet() == _UNREAD:
                return key
        return ""

    def _by_key(self) -> dict[str, QLineEdit]:
        return {"name": self.name, "coordination": self.coordination,
                "number": self.number,
                "transitivity": self.transitivity}

    def _on_edit(self, *_args) -> None:
        for field in self._fields():
            field.setStyleSheet("")
            field.setToolTip(self._tips[field])
        try:
            self._query = NetQuery.parse(
                name=self.name.text(),
                coordination=self.coordination.text(),
                exclusive=self.exclusive.isChecked(),
                number=self.number.text(),
                transitivity=self.transitivity.text())
        except NetQueryError as exc:
            field = self._by_key()[exc.field]
            field.setStyleSheet(_UNREAD)
            field.setToolTip(str(exc))
            self.note.setText(str(exc))
            self.note.show()
            return
        self.note.hide()
        self.changed.emit()

    def _on_dimension(self, checked: bool) -> None:
        """Keep at least one kind ticked -- an empty list from two
        unticked boxes answers a question nobody asked."""
        if not checked and not any(self.dimensions()):
            other = (self.two_d if self.sender() is self.three_d
                     else self.three_d)
            other.setChecked(True)
            return
        self.changed.emit()

    # -- the list ------------------------------------------------------

    def count(self, nets: QListWidget) -> None:
        """Label the boxes with how many rows each kind has."""
        layers = sum(bool(nets.item(i).data(LAYER_ROLE))
                     for i in range(nets.count()))
        self.three_d.setText(f"3D ({nets.count() - layers})")
        self.two_d.setText(f"2D ({layers})")

    def narrow(self, nets: QListWidget) -> None:
        """Hide every row the query or the boxes rule out."""
        query = self._query
        three_d, two_d = self.dimensions()
        for index in range(nets.count()):
            item = nets.item(index)
            wanted = two_d if item.data(LAYER_ROLE) else three_d
            item.setHidden(not wanted
                           or not query.matches(item.data(FACTS_ROLE)))
