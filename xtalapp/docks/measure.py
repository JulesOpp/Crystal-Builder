"""
xtalapp.docks.measure
=====================
The measurement table.

Measurements are notes about the crystal rather than changes to it, so
nothing here is undoable and nothing here marks the document modified.
They do follow the crystal: move an atom and the numbers change, delete
one and the measurements that named it go with it.  A table of stale
numbers would be worse than no table.

What kind of measurement you get is decided by how many atoms you
pick -- two for a distance, three for an angle, four for a torsion --
so the chooser at the top is really setting "how many clicks", and the
viewport says how many are left as you go.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from xtal.core.measure import KINDS

COLUMNS = ["Atoms", "Kind", "Value"]
# (label, how many atoms), in the order the chooser offers them.
TARGETS = [(f"{kind.capitalize()} ({count} atoms)", count)
           for count, kind in sorted(KINDS.items())]


class MeasureDock(QDockWidget):
    """Distances, angles and torsions taken in the viewport."""

    targetChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__("Measure", parent)
        self.setObjectName("MeasureDock")
        self.document = None

        self.target = QComboBox()
        for label, count in TARGETS:
            self.target.addItem(label, count)
        self.target.setToolTip(
            "How many atoms one measurement takes")
        self.target.currentIndexChanged.connect(self._on_target)

        self.hint = QLabel(
            "Switch to the Measure tool, then click atoms.")
        self.hint.setWordWrap(True)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._on_row_chosen)

        self.remove_button = QPushButton("Remove")
        self.remove_button.clicked.connect(self.remove_selected)
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear)
        buttons = QHBoxLayout()
        buttons.addWidget(self.remove_button)
        buttons.addWidget(self.clear_button)
        buttons.addStretch(1)

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(self.target)
        layout.addWidget(self.hint)
        layout.addWidget(self.table, 1)
        layout.addLayout(buttons)

        container = QWidget()
        container.setLayout(layout)
        self.setWidget(container)
        self.set_document(None)

    # -- binding -------------------------------------------------------

    def set_document(self, document) -> None:
        self.document = document
        self.refresh()

    def refresh(self) -> None:
        document = self.document
        self.widget().setEnabled(document is not None)
        measurements = document.measurements if document else []
        self.table.setRowCount(len(measurements))
        for row, measurement in enumerate(measurements):
            digits = 4 if measurement.kind == "distance" else 2
            values = [
                " - ".join(measurement.labels or
                           [str(a) for a in measurement.atoms]),
                measurement.kind,
                f"{measurement.value:.{digits}f} {measurement.unit}",
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column == 2:
                    item.setTextAlignment(Qt.AlignRight
                                          | Qt.AlignVCenter)
                self.table.setItem(row, column, item)
        has_any = bool(measurements)
        self.remove_button.setEnabled(has_any)
        self.clear_button.setEnabled(has_any)

    # -- actions -------------------------------------------------------

    def atom_count(self) -> int:
        return int(self.target.currentData())

    def _on_target(self, _index: int) -> None:
        self.targetChanged.emit(self.atom_count())

    def remove_selected(self) -> None:
        rows = sorted({i.row() for i in
                       self.table.selectionModel().selectedRows()},
                      reverse=True)
        for row in rows:
            self.document.remove_measurement(row)

    def clear(self) -> None:
        if self.document is not None:
            self.document.clear_measurements()

    def _on_row_chosen(self) -> None:
        """Selecting a measurement lights up the atoms it was taken
        between -- which is the only way to tell two 1.98 A bonds
        apart."""
        if self.document is None:
            return
        rows = {i.row() for i in
                self.table.selectionModel().selectedRows()}
        atoms = set()
        for row in rows:
            if 0 <= row < len(self.document.measurements):
                atoms |= set(self.document.measurements[row].atoms)
        if atoms:
            self.document.select(atoms, "set")
