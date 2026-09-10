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
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from xtal.core import subgroups as subgroup_core


def _times(ratio: float) -> str:
    """``x2``-style, because "2.0000000004 times" is not a thing a
    dialog should ever say."""
    whole = round(ratio)
    return (f"{whole} times" if abs(ratio - whole) < 1e-6
            else f"{ratio:.3g} times")

COLUMNS = ["Subgroup", "No.", "Index", "Kind", "Step",
           "Same by symmetry", "What splits", "Axes and origin"]

# How wide the split summary gets, and it is a **fixed** width rather
# than a maximum.  A descent that gives up the centring can split every
# site in the structure, so resized to contents the summary takes the
# whole table and carries the axes column off the right-hand edge --
# and because the summary only arrives when a row is selected, sizing
# to contents also means the columns jump every time the selection
# moves.  Fixed costs a little width on a list of short summaries and
# buys a table that holds still.  The detail pane says it all in full
# underneath, so the cell is allowed to elide.
SPLIT_COLUMN_MAX = 300

# The detail pane scrolls inside this rather than growing.  What it
# says is one line for a descent that splits nothing and one line per
# site for a descent that splits everything, and a pane that takes its
# height from that resizes the window -- and moves the table and the
# buttons under the cursor -- every time the selection changes.
DETAIL_HEIGHT = 132

# The order the kinds are offered in, which is the order they cost:
# rotations, then translations, then both.
KINDS = ("t", "k", "t + k")


class SubgroupDialog(QDialog):
    """Pick one of the maximal subgroups of the current group."""

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Descend to a subgroup")
        self.document = document
        self.all_subgroups = []
        self.subgroups = []
        self._rows: list[int] = []
        self._splits: dict[int, object] = {}
        self.resize(820, 560)

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
            "A t descent gives up rotations and keeps every "
            "translation; a k descent keeps the rotations and gives up "
            "translations, either part of the centring in the same "
            "cell or enough of the lattice that the cell grows -- "
            "which is a superstructure. Subgroups that differ only in "
            "orientation give the same crystal and share one row.")
        self.blurb.setWordWrap(True)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(
            COLUMNS.index("What splits"), QHeaderView.Interactive)
        # Capping the split column leaves slack at the right-hand edge,
        # and an empty ninth column reads as a column with nothing in it.
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.currentCellChanged.connect(self._selected)

        self.kinds = QComboBox()
        self.kinds.currentIndexChanged.connect(self._show_rows)
        self.kind_row = QWidget()
        kind_layout = QHBoxLayout(self.kind_row)
        kind_layout.setContentsMargins(0, 0, 0, 0)
        kind_layout.addWidget(QLabel("Kind:"))
        kind_layout.addWidget(self.kinds)
        kind_layout.addStretch(1)

        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.detail.setStyleSheet("padding: 4px;")
        # Fixed height, scrolling what does not fit: see DETAIL_HEIGHT.
        self.detail_area = QScrollArea()
        self.detail_area.setWidget(self.detail)
        self.detail_area.setWidgetResizable(True)
        self.detail_area.setFrameShape(QFrame.NoFrame)
        self.detail_area.setFixedHeight(DETAIL_HEIGHT)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                        | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Descend")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.heading)
        layout.addWidget(self.blurb)
        layout.addWidget(self.kind_row)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.detail_area)
        layout.addWidget(self.buttons)

        self._fill()

    # -- the list ------------------------------------------------------

    def _fill(self) -> None:
        self.all_subgroups = self.document.subgroups()
        self._offer_kinds()
        self._show_rows()

    def _offer_kinds(self) -> None:
        """The kinds this group actually has, with how many of each.

        Only the ones that are there: a primitive group has no k
        descent to offer and a dropdown whose every entry but one is
        empty is a dropdown that has to be tried to be believed.  Where
        there is only one kind the whole row goes away, because a
        filter with a single choice is not a filter.
        """
        present = [kind for kind in KINDS
                   if any(s.kind == kind for s in self.all_subgroups)]
        self.kinds.blockSignals(True)
        self.kinds.clear()
        self.kinds.addItem(f"All ({len(self.all_subgroups)})", None)
        for kind in present:
            count = sum(1 for s in self.all_subgroups if s.kind == kind)
            self.kinds.addItem(f"{kind} ({count})", kind)
        self.kinds.blockSignals(False)
        self.kind_row.setVisible(len(present) > 1)

    def _show_rows(self, *_args) -> None:
        """Fill the table with the subgroups the filter lets through.

        ``_rows`` is what keeps the split cache honest across a change
        of filter: it maps a row of the table back to its place in the
        unfiltered list, so a split worked out under one filter is
        still that subgroup's split under the next one, and is shown
        again rather than recomputed.
        """
        wanted = self.kinds.currentData()
        self._rows = [i for i, sub in enumerate(self.all_subgroups)
                      if wanted is None or sub.kind == wanted]
        self.subgroups = [self.all_subgroups[i] for i in self._rows]
        self.table.setRowCount(len(self.subgroups))
        for row, sub in enumerate(self.subgroups):
            known = self._splits.get(self._rows[row])
            values = [
                sub.group.hm if sub.group else "unnamed",
                str(sub.group.number) if sub.group else "",
                str(sub.index),
                sub.kind,
                "maximal" if sub.maximal else "",
                "" if sub.n_conjugates == 1 else f"1 of {sub.n_conjugates}",
                known.summary() if known else "",   # else when selected
                subgroup_core.basis_description(sub),
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column in (1, 2, 3, 4, 5):
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, column, item)
        self._size_columns()
        if not self.subgroups:
            # Only ever the whole list being empty: the dropdown offers
            # a kind only when the group has one, so choosing a kind
            # cannot empty the table.
            self.detail.setText(
                f"{self.document.structure.space_group.short_name} has "
                f"no proper subgroups: it is already the smallest "
                f"group there is.")
            self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
            return
        self.table.setCurrentCell(0, 0)
        # Again by hand: where row 0 was already current, changing the
        # filter changes what is *in* it without moving the selection,
        # so nothing is emitted and the detail pane would still be
        # describing a subgroup that is no longer on this row.
        self._selected(0)

    def _selected(self, row: int, *_args) -> None:
        sub = self.subgroup()
        if sub is None:
            return
        split = self._split_for(row)
        self.table.item(row, COLUMNS.index("What splits")).setText(
            split.summary())
        self.detail.setText(self._describe(sub, split))
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(
            split.ok and sub.named)

    def _size_columns(self) -> None:
        """Size every column once per fill, and never on a selection.

        The split column is given its fixed width rather than its
        content's, because its content arrives one row at a time as
        rows are selected -- and a table that resizes itself under the
        cursor while somebody is reading down it is worse than a table
        with a wide column.
        """
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(COLUMNS.index("What splits"),
                                  SPLIT_COLUMN_MAX)

    def _split_for(self, row: int):
        """The split for one row, worked out once and remembered.

        It costs an expansion of the cell and an asymmetric unit found
        inside it, which is tenths of a second on a framework of a few
        hundred atoms -- fast enough to do on the UI thread and slow
        enough to be worth saying so, because a window that has stopped
        painting and a window that is busy look the same.
        """
        key = self._rows[row]
        if key not in self._splits:
            QGuiApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                self._splits[key] = self.document.subgroup_split(
                    self.all_subgroups[key])
            finally:
                QGuiApplication.restoreOverrideCursor()
        return self._splits[key]

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
        if sub.k_index > 1:
            parent = self.document.structure.space_group.short_name
            lines.append(
                f"Translations are given up: only one lattice "
                f"translation in {sub.k_index} is still a symmetry of "
                f"{parent}, so atoms related only by the others become "
                f"independent."
                + (f" The cell grows {_times(sub.volume_ratio)}: "
                   f"this is a superstructure."
                   if sub.enlarges_the_lattice else
                   " The cell is the same cell -- this is not a "
                   "superstructure."))
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
