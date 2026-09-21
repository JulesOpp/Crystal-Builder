"""
xtalapp.dialogs.interpenetrate
==============================
Choosing where the copies of an interpenetrated framework go.

**A list, not an answer.**  Which placements a framework can take is
geometric -- whether the voids are big enough -- and there is no test
that says so ahead of measuring, so every candidate is measured and
shown with its closest contact between copies, best first.  The top
row is selected, which is the answer for somebody who wants the one
with the most room; the rest are there because the one with the most
room is not always the one in the paper.

**The ones that collide stay in the list, greyed, with the reason.**
A dense framework offers nothing, and a list that had silently dropped
everything could not say why; a row that names the two atoms that
would land on each other can.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QPalette
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from xtal.analysis.interpenetrate import MAX_FOLD, InterpenetrationError

COLUMNS = ("Placement", "Relation", "Closest contact", "Room")


class InterpenetrateDialog(QDialog):
    """Pick a fold and a placement for the copies."""

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Interpenetrate")
        self.document = document
        self.placements = []
        self.resize(720, 460)

        self.blurb = QLabel(
            "Copies of this framework threaded through its own pores. "
            "Class Ia copies are related by a translation of the "
            "whole array, Class II by an inversion; each placement is "
            "measured by the closest contact between two copies, and "
            "one where atoms would land on each other cannot be "
            "chosen. The copies keep the bonds and the net they had, "
            "and the result is in P1.")
        self.blurb.setWordWrap(True)

        self.fold = QSpinBox()
        self.fold.setRange(2, MAX_FOLD)
        self.fold.setValue(2)
        self.fold.setSuffix("-fold")
        self.fold.valueChanged.connect(self._fill)
        form = QFormLayout()
        form.addRow("Copies", self.fold)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.currentCellChanged.connect(self._selected)

        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                        | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText(
            "Interpenetrate")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.blurb)
        layout.addLayout(form)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.detail)
        layout.addWidget(self.buttons)
        self._fill()

    # -- the list ------------------------------------------------------

    def _fill(self, *_args) -> None:
        """Measure every placement at the fold shown.

        On the UI thread and said so with the cursor: seventy
        placements of a four-hundred-atom framework is half a second,
        which is too short for a progress bar and too long for a
        window that simply stops.
        """
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.placements = self.document.interpenetration_candidates(
                self.fold.value())
            problem = ""
        except InterpenetrationError as exc:
            self.placements, problem = [], str(exc)
        finally:
            QGuiApplication.restoreOverrideCursor()
        self.table.setRowCount(len(self.placements))
        # Greyed by colour and not disabled: a disabled row cannot be
        # selected, and selecting it is how its reason is read.
        grey = self.palette().color(QPalette.Disabled, QPalette.Text)
        for row, placement in enumerate(self.placements):
            values = (placement.name, placement.relation,
                      placement.contact_text(),
                      "collides" if placement.collides else "room")
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if placement.collides:
                    item.setForeground(grey)
                self.table.setItem(row, column, item)
        if problem:
            self.detail.setText(problem[0].upper() + problem[1:] + ".")
            self._allow(False)
            return
        self.table.setCurrentCell(0, 0)
        # By hand as well: where row 0 was already current a new fold
        # changes what is in it without moving the selection, and the
        # detail would describe the row that used to be there.
        self._selected(0)

    def _selected(self, row: int, *_args) -> None:
        placement = self.placement()
        if placement is None:
            self._allow(False)
            return
        if placement.collides:
            self.detail.setText(
                f"{placement.name} {placement.collision}, so it "
                f"cannot be made.")
        else:
            a, b = placement.pair
            self.detail.setText(
                f"{placement.fold} copies, {placement.name} "
                f"({placement.relation}). The closest two atoms of "
                f"different copies are {a} and {b}, "
                f"{placement.contact_text()} apart.")
        self._allow(not placement.collides)

    def _allow(self, ok: bool) -> None:
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(ok)

    def placement(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.placements):
            return self.placements[row]
        return None

    # -- asking --------------------------------------------------------

    @classmethod
    def ask(cls, document, parent=None):
        """Show the dialog and apply the choice; returns the report, or
        None if it was cancelled."""
        dialog = cls(document, parent)
        if dialog.exec() != QDialog.Accepted:
            return None
        placement = dialog.placement()
        if placement is None or placement.collides:
            return None
        return document.interpenetrate(placement)
