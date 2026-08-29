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

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
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
EDITABLE = {0, 1, 2, 3, 4, 5, 6}


class SiteTableModel(QAbstractTableModel):
    """Qt model over the sites of the asymmetric unit."""

    def __init__(self, document=None, parent=None):
        super().__init__(parent)
        self.document = document

    def set_document(self, document) -> None:
        self.beginResetModel()
        self.document = document
        self.endResetModel()

    def refresh(self) -> None:
        self.beginResetModel()
        self.endResetModel()

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
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.table.selectionModel().selectionChanged.connect(
            self._on_rows_selected)
        self.setWidget(self.table)

    def set_document(self, document) -> None:
        self.document = document
        self.model.set_document(document)
        self.refresh()

    def refresh(self) -> None:
        self.model.refresh()
        self.sync_selection()

    def sync_selection(self) -> None:
        """Highlight the rows whose sites are selected in the
        viewport."""
        if self.document is None:
            return
        self._syncing = True
        selection_model = self.table.selectionModel()
        selection_model.clearSelection()
        for row in sorted(self.document.selected_sites()):
            self.table.selectRow(row)
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
