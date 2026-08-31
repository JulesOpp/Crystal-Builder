"""
xtalapp.dialogs.subgroup
========================
Descending to a maximal subgroup -- and saying what each descent costs
before any of them happens.

**Every subgroup, not only the maximal ones.**  A maximal subgroup is
the smallest step that can be taken and rarely the one wanted: an
ordering model usually knows the group it is heading for, and making
it reachable only by descending through three dialogs is asking the
user to walk the subgroup lattice by hand.  The maximal ones are
marked, so the step-by-step path is still there for anyone who wants
it.

**One row per conjugacy class.**  Fm-3m has three maximal tetragonal
subgroups that differ only in which cubic axis they keep, and the
parent's own three-fold carries any one onto any other -- so all three
give the same crystal, in the same group and the same cell, differing
only in where the origin and the axes ended up inside it.  Offering
that as a choice is offering a choice nobody can make usefully.  The
row says how many it stands for rather than hiding them, because the
count is what tells a crystallographer that the orientation was
arbitrary and not that the list is short.

**Descending is a choice; raising the symmetry is a measurement.**  The
two look like a matched pair in the menu and only one of them is a
decision: `Symmetry > Find symmetry` reads the coordinates and reports
what is there, while this dialog offers several subgroups that the
coordinates cannot choose between.  The dialog says so, because the
symmetry of the pair of menu items implies otherwise.

What makes the list usable is the third column.  Most descents split
nothing: six of rutile's seven maximal subgroups leave both sites
whole, because the site symmetry drops by the same factor as the group
order and what changes is the *freedom* each site has, not how many
there are.  A list that did not say so would look broken for every
entry but one -- and that one, for rutile, is also the entry that no
amount of pattern-matching on symbols would have found.

The split is what the whole feature is for, so it is computed by
actually performing the descent on a copy, not guessed from
multiplicities.  That costs a full expansion per row, so it is done for
the selected row only and remembered.  On MFU-4l -- 10 sites, 648 atoms
in the cell, ten maximal subgroups -- that is under a tenth of a second
a row, which is what makes doing it on the UI thread honest rather than
merely convenient.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from xtal.core import subgroups as subgroup_core

COLUMNS = ["Subgroup", "No.", "Index", "Step", "Same by symmetry",
           "What splits", "Axes and origin"]


class SubgroupDialog(QDialog):
    """Pick one of the maximal subgroups of the current group."""

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Descend to a subgroup")
        self.document = document
        self.subgroups = []
        self._splits: dict[int, object] = {}
        self.resize(760, 520)

        group = document.structure.space_group
        self.heading = QLabel(
            f"Subgroups of {group.hm} (#{group.number}), "
            f"{group.order} operations.")
        font = self.heading.font()
        font.setBold(True)
        self.heading.setFont(font)

        self.blurb = QLabel(
            "Descending is a choice, not a measurement: each of these "
            "keeps every atom where it is and splits a different orbit "
            "into independent sites. Going the other way -- finding "
            "the symmetry the coordinates already have -- is "
            "Symmetry ▸ Find symmetry, and that one has a single "
            "answer.\n"
            "Same lattice throughout (translationengleiche): no cell "
            "is doubled, so no superstructure appears here. Subgroups "
            "that differ only in orientation give the same crystal and "
            "share one row.")
        self.blurb.setWordWrap(True)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.table.currentCellChanged.connect(self._selected)

        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setStyleSheet("padding: 4px;")

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                        | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Descend")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.heading)
        layout.addWidget(self.blurb)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.detail)
        layout.addWidget(self.buttons)

        self._fill()

    # -- the list ------------------------------------------------------

    def _fill(self) -> None:
        self.subgroups = self.document.subgroups()
        self.table.setRowCount(len(self.subgroups))
        for row, sub in enumerate(self.subgroups):
            values = [
                sub.group.hm if sub.group else "unnamed",
                str(sub.group.number) if sub.group else "",
                str(sub.index),
                "maximal" if sub.maximal else "",
                "" if sub.n_conjugates == 1 else f"1 of {sub.n_conjugates}",
                "",                      # filled in when selected
                subgroup_core.basis_description(sub),
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column in (1, 2, 3, 4):
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, column, item)
        if not self.subgroups:
            self.detail.setText(
                f"{self.document.structure.space_group.short_name} has "
                f"no proper subgroups: it is already the smallest "
                f"group there is.")
            self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
            return
        self.table.setCurrentCell(0, 0)

    def _selected(self, row: int, *_args) -> None:
        sub = self.subgroup()
        if sub is None:
            return
        split = self._split_for(row)
        self.table.item(row, 5).setText(split.summary())
        self.table.resizeColumnsToContents()
        self.detail.setText(self._describe(sub, split))
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(
            split.ok and sub.named)

    def _split_for(self, row: int):
        """The split for one row, worked out once and remembered.

        It costs an expansion of the cell and an asymmetric unit found
        inside it, which is tenths of a second on a framework of a few
        hundred atoms -- fast enough to do on the UI thread and slow
        enough to be worth saying so, because a window that has stopped
        painting and a window that is busy look the same.
        """
        if row not in self._splits:
            QGuiApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                self._splits[row] = self.document.subgroup_split(
                    self.subgroups[row])
            finally:
                QGuiApplication.restoreOverrideCursor()
        return self._splits[row]

    def _describe(self, sub, split) -> str:
        if not split.ok:
            self.detail.setStyleSheet(
                "padding: 4px; color: #8a5a00; background: #fdf3e0;")
            return split.message
        self.detail.setStyleSheet("padding: 4px;")
        lines = []
        if split.splits:
            for label, element, multiplicity, pieces in split.per_site:
                if pieces > 1:
                    lines.append(
                        f"{label} ({element}), multiplicity "
                        f"{multiplicity}, becomes {pieces} independent "
                        f"sites")
        else:
            lines.append(
                "No orbit splits: every site stays one site. The site "
                "symmetry drops by the same factor as the group order, "
                "so what this buys is freedom for the atoms already "
                "there, not more of them.")
        if not sub.keeps_the_cell:
            lines.append(
                f"The cell is re-expressed in the standard setting of "
                f"{sub.symbol} ({subgroup_core.basis_description(sub)})"
                f". The crystal does not move; the axes do.")
        if sub.n_conjugates > 1:
            lines.append(
                f"{sub.n_conjugates} subgroups of "
                f"{self.document.structure.space_group.short_name} are "
                f"this one in a different orientation. They are "
                f"conjugate under the parent, so each gives the same "
                f"crystal in the same cell -- differing only in where "
                f"the origin and axes land inside it, which is the "
                f"parent's choice and not yours.")
        if not sub.maximal:
            lines.append(
                "Not a maximal subgroup: there is at least one group "
                "between this and the one you are in. Descending "
                "straight here is the same result as descending "
                "through them.")
        return "\n".join(lines)

    # -- values --------------------------------------------------------

    def subgroup(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.subgroups):
            return self.subgroups[row]
        return None

    # -- running -------------------------------------------------------

    @classmethod
    def ask(cls, document, parent=None):
        """Show the dialog and apply the choice; returns the report, or
        None if it was cancelled."""
        dialog = cls(document, parent)
        if dialog.exec() != QDialog.Accepted:
            return None
        sub = dialog.subgroup()
        if sub is None:
            return None
        return document.descend_to_subgroup(sub)
