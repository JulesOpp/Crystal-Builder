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

Planes are the exception, and are made from the *selection* rather than
from a run of clicks: three atoms determine one and a ring is six, so
there is no useful number to count clicks up to.  Select the atoms,
press the button, and the plane joins a list of its own; the angle
between planes is then taken between the rows of that list and lands in
the same table as every other measurement.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QComboBox,
    QDockWidget,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from xtal.core.measure import KINDS

#: The swatch beside each plane in the list, in pixels.
SWATCH = 12

COLUMNS = ["Atoms", "Kind", "Value"]
# (label, how many atoms), in the order the chooser offers them.
TARGETS = [(f"{kind.capitalize()} ({count} atoms)", count)
           for count, kind in sorted(KINDS.items())]


def _swatch(color) -> QIcon:
    """A plane's colour, as an icon for its row."""
    pixmap = QPixmap(SWATCH, SWATCH)
    pixmap.fill(QColor(*color))
    return QIcon(pixmap)


class MeasureDock(QDockWidget):
    """Distances, angles and torsions taken in the viewport."""

    targetChanged = Signal(int)
    #: What a plane command did, for the status bar.
    statusMessage = Signal(str)

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
        layout.addWidget(self._build_planes())

        container = QWidget()
        container.setLayout(layout)
        self.setWidget(container)
        self.set_document(None)

    def _build_planes(self) -> QGroupBox:
        box = QGroupBox("Planes")
        self.plane_list = QListWidget()
        self.plane_list.setSelectionMode(
            QAbstractItemView.ExtendedSelection)
        self.plane_list.setToolTip(
            "Planes defined from the selection.  Choose two or more, "
            "then take the angle between them.")
        self.plane_list.itemSelectionChanged.connect(
            self._on_plane_chosen)

        self.define_button = QPushButton("From selection")
        self.define_button.setToolTip(
            "Fit a plane through the selected atoms -- exactly through "
            "three, least-squares through more")
        self.define_button.clicked.connect(self.define_plane)
        self.angle_button = QPushButton("Angle")
        self.angle_button.setToolTip(
            "The angle between the chosen planes, or between all of "
            "them when none is chosen -- one measurement per pair")
        self.angle_button.clicked.connect(self.measure_plane_angle)
        # Its own colour per plane, and not one setting for all of
        # them: the reason for drawing a quad is to see where two
        # planes cross, and two quads in the same colour is the
        # picture that cannot be read.  It takes the chosen rows
        # rather than all of them, because "colour every plane the
        # same" is what the Planes swatch in the Style panel is.
        self.plane_color_button = QPushButton("Colour")
        self.plane_color_button.setToolTip(
            "Give the chosen planes a colour of their own, so two of "
            "them can be told apart where they cross")
        self.plane_color_button.clicked.connect(self.color_planes)
        self.remove_plane_button = QPushButton("Remove")
        self.remove_plane_button.clicked.connect(self.remove_planes)

        row = QHBoxLayout()
        row.addWidget(self.define_button)
        row.addWidget(self.angle_button)
        row.addWidget(self.plane_color_button)
        row.addWidget(self.remove_plane_button)

        inner = QVBoxLayout(box)
        inner.addWidget(self.plane_list)
        inner.addLayout(row)
        return box

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
        self.refresh_planes()

    def refresh_planes(self) -> None:
        """The plane list, and what can be done with it."""
        document = self.document
        planes = document.planes if document else []
        chosen = {i.row() for i in
                  self.plane_list.selectionModel().selectedRows()}
        self.plane_list.blockSignals(True)
        self.plane_list.clear()
        for plane in planes:
            self.plane_list.addItem(QListWidgetItem(
                _swatch(self._plane_color(plane)), plane.text()))
        for row in chosen:
            if row < self.plane_list.count():
                self.plane_list.item(row).setSelected(True)
        self.plane_list.blockSignals(False)
        selected_atoms = bool(document is not None
                              and len(document.selection.atoms) >= 3)
        self.define_button.setEnabled(selected_atoms)
        self.angle_button.setEnabled(len(planes) >= 2)
        self.plane_color_button.setEnabled(bool(chosen))
        self.remove_plane_button.setEnabled(bool(planes))

    def _plane_color(self, plane) -> tuple:
        """What this plane is actually drawn in: its own colour, or
        the default it has not been moved off."""
        if plane.color is not None:
            return tuple(plane.color)
        return tuple(self.document.view.plane_color)

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

    def define_plane(self) -> None:
        if self.document is not None:
            self.statusMessage.emit(self.document.define_plane())

    def measure_plane_angle(self) -> None:
        """The angle between the chosen planes, or between all of them.

        Choosing none and meaning all is the common case: two planes
        are defined and the angle between them is the question.
        """
        if self.document is None:
            return
        rows = sorted({i.row() for i in
                       self.plane_list.selectionModel().selectedRows()})
        self.statusMessage.emit(
            self.document.measure_plane_angles(rows if len(rows) >= 2
                                               else None))

    def color_planes(self) -> None:
        """Recolour the chosen planes.

        Opened on the first chosen plane's current colour, so a small
        adjustment starts where the plane already is rather than at
        whatever the dialog last showed.
        """
        rows = sorted({i.row() for i in
                       self.plane_list.selectionModel().selectedRows()})
        if self.document is None or not rows:
            return
        current = self._plane_color(self.document.planes[rows[0]])
        chosen = QColorDialog.getColor(QColor(*current), self,
                                       "Plane colour")
        if chosen.isValid():
            self.document.set_plane_color(
                rows, (chosen.red(), chosen.green(), chosen.blue()))

    def remove_planes(self) -> None:
        rows = sorted({i.row() for i in
                       self.plane_list.selectionModel().selectedRows()},
                      reverse=True)
        for row in rows or [len(self.document.planes) - 1]:
            self.document.remove_plane(row)

    def _on_plane_chosen(self) -> None:
        """Choosing a plane lights up the atoms it was fitted through,
        and narrows the picture to that plane's own quad.

        Lighting up the atoms is the only way to tell two rings apart
        in a picture of a framework; narrowing the drawing is what
        makes the quads usable once there are several of them, and
        choosing none goes back to showing them all.
        """
        if self.document is None:
            return
        rows, atoms = [], set()
        for item in self.plane_list.selectionModel().selectedRows():
            row = item.row()
            if 0 <= row < len(self.document.planes):
                rows.append(row)
                atoms |= set(self.document.planes[row].atoms)
        self.document.set_shown_planes(rows)
        if atoms:
            self.document.select(atoms, "set")

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
