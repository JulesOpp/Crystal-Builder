"""
xtalapp.docks.sites
===================
The asymmetric unit as a table.

One row per site -- not per drawn atom -- because that is what the file
holds and what an edit changes.  The multiplicity column says how many
atoms each row puts in the cell, which is the connection back to the
viewport: select a row and the whole orbit lights up.

The table is editable in place: element, label, coordinates,
occupancy.  Every edit goes through the Document, so it will become
undoable for free when the command stack lands.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import (
    QAbstractTableModel,
    QItemSelection,
    QItemSelectionModel,
    QModelIndex,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDockWidget,
    QHeaderView,
    QTableView,
)

from xtal.core import elements as el

COLUMNS = ["Label", "El", "x", "y", "z", "Occ", "Uiso", "Wyckoff",
           "Mult"]
# Qt's model API takes a parent index by value; one shared invalid
# index stands in for "the root" everywhere.
NO_PARENT = QModelIndex()
# Rows sampled when sizing a column to its contents.
RESIZE_SAMPLE_ROWS = 30
EDITABLE = {0, 1, 2, 3, 4, 5, 6}


class SiteTableModel(QAbstractTableModel):
    """Qt model over the sites of the asymmetric unit."""

    def __init__(self, document=None, parent=None):
        super().__init__(parent)
        self.document = document
        self._shown = self._coordinates()

    def set_document(self, document) -> None:
        self.beginResetModel()
        self.document = document
        self._shown = self._coordinates()
        self.endResetModel()

    def refresh(self) -> None:
        self.beginResetModel()
        self._shown = self._coordinates()
        self.endResetModel()

    def moved(self) -> None:
        """The atoms moved and nothing else changed: repaint the rows
        whose sites did, and leave the table's shape alone.

        A reset re-lays-out every row and throws the selection away, and
        a drag asks for one per mouse event -- a third of a drag step on
        MFU-4l went here.  Which rows moved is read off the coordinates
        rather than trusted from the caller, so an optimiser that moves
        everything and a drag that moves one site are the same call.
        """
        now = self._coordinates()
        before = self._shown
        if before is None or now is None or before.shape != now.shape:
            self.refresh()
            return
        self._shown = now
        rows = np.flatnonzero(np.any(now != before, axis=1))
        if not len(rows):
            return
        # A move can put a site on a special position, so the
        # multiplicity column is news as well as the coordinates.
        self.dataChanged.emit(self.index(int(rows[0]), 2),
                              self.index(int(rows[-1]), 8))

    def _coordinates(self):
        if self.document is None:
            return None
        sites = self.document.structure.sites
        if not sites:
            return np.zeros((0, 3))
        return np.array([site.frac for site in sites], dtype=float)

    # -- shape ---------------------------------------------------------

    def rowCount(self, parent=NO_PARENT) -> int:
        if parent.isValid() or self.document is None:
            return 0
        return self.document.structure.n_sites

    def columnCount(self, parent=NO_PARENT) -> int:
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return COLUMNS[section]
        return section

    # -- reading -------------------------------------------------------

    def site(self, row: int):
        return self.document.structure.sites[row]

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or self.document is None:
            return None
        site = self.site(index.row())
        column = index.column()

        if role in (Qt.DisplayRole, Qt.EditRole):
            if column == 0:
                return site.label or ""
            if column == 1:
                return site.element
            if column in (2, 3, 4):
                return f"{site.frac[column - 2]:.5f}"
            if column == 5:
                return f"{site.occupancy:.4f}"
            if column == 6:
                return "" if site.u_iso is None else f"{site.u_iso:.5f}"
            if column == 7:
                return site.wyckoff or ""
            if column == 8:
                return str(self.document.cell.multiplicity(index.row()))
        elif role == Qt.BackgroundRole and column == 1:
            r, g, b = el.color(site.element)
            return QColor(r, g, b, 90)
        elif role == Qt.TextAlignmentRole and column >= 2:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        elif role == Qt.ToolTipRole:
            return (f"site {index.row()} · "
                    f"{self.document.cell.multiplicity(index.row())} "
                    f"atoms in the cell")
        return None

    def flags(self, index):
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() in EDITABLE:
            return base | Qt.ItemIsEditable
        return base

    # -- writing -------------------------------------------------------

    def setData(self, index, value, role=Qt.EditRole) -> bool:
        if role != Qt.EditRole or self.document is None:
            return False
        row, column = index.row(), index.column()
        text = str(value).strip()
        try:
            if column == 0:
                self.document.set_site_property(row, label=text)
            elif column == 1:
                symbol = el.canonical_symbol(text)
                if symbol is None:
                    return False
                self.document.set_site_property(row, element=symbol)
            elif column in (2, 3, 4):
                frac = self.site(row).frac.copy()
                frac[column - 2] = float(text)
                self.document.set_site_property(row, frac=frac)
            elif column == 5:
                self.document.set_site_property(
                    row, occupancy=float(text))
            elif column == 6:
                self.document.set_site_property(
                    row, u_iso=float(text) if text else None)
            else:
                return False
        except (ValueError, TypeError):
            return False
        self.dataChanged.emit(index, index)
        return True


class SitesDock(QDockWidget):
    """The site table, kept in step with the viewport selection."""

    siteActivated = Signal(int)

    def __init__(self, parent=None):
        super().__init__("Sites", parent)
        self.setObjectName("SitesDock")
        self.document = None
        self._syncing = False

        self.model = SiteTableModel(parent=self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(20)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        # Sizing a column to its contents means asking the model for
        # every cell in it.  A structure reduced to P1 has thousands of
        # sites, and every one of them would be measured on every
        # edit; sampling the first few rows sizes the columns just as
        # well, because they all hold the same kind of number.
        header.setResizeContentsPrecision(RESIZE_SAMPLE_ROWS)
        self.table.selectionModel().selectionChanged.connect(
            self._on_rows_selected)
        self.setWidget(self.table)

    def set_document(self, document) -> None:
        self.document = document
        self.model.set_document(document)
        self.refresh()

    def refresh(self, positions_only: bool = False) -> None:
        if positions_only:
            self.model.moved()
            return
        self.model.refresh()
        self.sync_selection()

    def sync_selection(self) -> None:
        """Highlight the rows whose sites are selected in the
        viewport.

        Built as one QItemSelection and applied in a single call:
        selecting rows one at a time makes Qt re-lay-out the table once
        per row, which a P1 structure with hundreds of sites feels.
        """
        if self.document is None:
            return
        self._syncing = True
        rows = sorted(self.document.selected_sites())
        last = self.model.columnCount() - 1
        chosen = QItemSelection()
        for row in rows:
            chosen.select(self.model.index(row, 0),
                          self.model.index(row, last))
        self.table.selectionModel().select(
            chosen, QItemSelectionModel.ClearAndSelect)
        if rows:
            self.table.scrollTo(self.model.index(rows[0], 0))
        self._syncing = False

    def _on_rows_selected(self, *_args) -> None:
        if self._syncing or self.document is None:
            return
        rows = {index.row() for index in
                self.table.selectionModel().selectedRows()}
        if not rows:
            return
        atoms = set()
        for row in rows:
            atoms |= {int(k) for k in
                      self.document.cell.indices_of_site(row)}
        self.document.select(atoms, "set")
        self.siteActivated.emit(min(rows))
