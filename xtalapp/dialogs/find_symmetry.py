"""
xtalapp.dialogs.find_symmetry
=============================
"What symmetry do these coordinates have?" -- with the tolerance in
plain sight.

Symmetry detection has no answer without a tolerance.  The same
coordinates are P1 at 10^-5 and Fd-3m at 10^-2, and which one is *the*
answer depends on where the numbers came from: a refined structure
deserves a tight tolerance, one relaxed by a force field does not.  So
the tolerance is the first control in the dialog, the detected group
follows it live, and nothing is committed until the user says so.

The Wyckoff table underneath is the check that the answer is the
expected one: a chemist recognises "Ti on 2a, O on 4f" long before
they would notice a wrong Hall symbol.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from xtalapp.widgets.tone import WARNING_BOX, set_tone

# Spanning five decades, which is the range real structures need: a
# published CIF resolves at 10^-5, anything that has been through an
# optimiser needs 10^-3 or looser.
TOLERANCES = ["1e-5", "1e-4", "1e-3", "1e-2", "0.05", "0.1"]
# The loose end, because the structures this dialog is opened on are
# rarely refined ones: a framework drawn by hand, dragged, or relaxed
# by a force field sits a few hundredths of an Angstrom off its group,
# and at 1e-3 it came back as a subgroup and needed the box opened
# every time.
# A published CIF still finds its group here; it is the tighter
# presets that exist to tell two close groups apart.
DEFAULT_TOLERANCE = "0.1"

COLUMNS = ["Site", "El", "Wyckoff", "Site symmetry", "Mult"]


class FindSymmetryDialog(QDialog):
    """Detect the space group at a tolerance and adopt it."""

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Find symmetry")
        self.document = document
        self.info = None
        #: Whether *Adopt* moved the atoms.  The window reads it to
        #: decide whether the camera still frames the cell: *Adopt*
        #: and *Label Wyckoff only* both come back Accepted and only
        #: one of them re-expresses anything.
        self.re_expressed = False
        self.resize(460, 460)

        self.tolerance = QComboBox()
        self.tolerance.setEditable(True)
        self.tolerance.addItems(TOLERANCES)
        self.tolerance.setCurrentText(DEFAULT_TOLERANCE)
        self.tolerance.setToolTip(
            "How far an atom may be from its symmetric position, in "
            "Angstrom")
        self.tolerance.currentTextChanged.connect(self.refresh)

        # Ticked, because the common case is a cell that is not in the
        # standard setting and adopting the group is what the dialog
        # was opened to do.  Left unticked it needed a box found and
        # ticked before *Adopt* would do the thing that was asked for.
        # The note stays and is what says what re-expressing costs --
        # it is now the thing happening without being asked for.
        self.standardize = QCheckBox(
            "Re-express the cell in the standard setting first")
        self.standardize.setChecked(True)
        self.standardize.setToolTip(
            "Needed whenever the cell as given is not already in the "
            "standard setting of the detected group")

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        font = self.summary.font()
        font.setBold(True)
        self.summary.setFont(font)

        self.note = QLabel()
        self.note.setWordWrap(True)
        set_tone(self.note, WARNING_BOX)
        self.note.hide()

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)

        form = QFormLayout()
        form.addRow("Tolerance (A)", self.tolerance)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.adopt_button = QPushButton("Adopt this group")
        self.adopt_button.setToolTip(
            "Keep the group and reduce the cell to its asymmetric "
            "unit")
        self.adopt_button.clicked.connect(self.adopt)
        self.wyckoff_button = QPushButton("Label Wyckoff only")
        self.wyckoff_button.setToolTip(
            "Write the Wyckoff letters onto the sites and change "
            "nothing else")
        self.wyckoff_button.clicked.connect(self.label_only)
        self.buttons.addButton(self.wyckoff_button,
                               QDialogButtonBox.ActionRole)
        self.buttons.addButton(self.adopt_button,
                               QDialogButtonBox.AcceptRole)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.standardize)
        layout.addWidget(self.summary)
        layout.addWidget(self.note)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.buttons)
        # Only once the box is inside the dialog.  setDefault tells the
        # *dialog* which button Return presses, and a button not yet in
        # one has no dialog to tell -- so called any earlier, the
        # dialog chose its own on show, and it chose Close.
        self.adopt_button.setDefault(True)

        self.refresh()

    # -- values --------------------------------------------------------

    def symprec(self) -> float:
        try:
            value = float(self.tolerance.currentText())
        except ValueError:
            return 0.0
        return value if value > 0 else 0.0

    # -- detection -----------------------------------------------------

    def refresh(self, *_args) -> None:
        """Re-detect at the current tolerance and show what came
        back."""
        symprec = self.symprec()
        self.table.setRowCount(0)
        self.info = None
        if symprec <= 0:
            self._fail("Type a tolerance greater than zero.")
            return
        try:
            self.info = self.document.detect_symmetry(symprec)
        except ValueError as exc:
            self._fail(str(exc))
            return

        self.summary.setText(self.info.summary())
        self.adopt_button.setEnabled(True)
        self.wyckoff_button.setEnabled(True)
        self._show_setting_note()
        self._fill_table()

    def _fail(self, message: str) -> None:
        self.summary.setText("No symmetry found")
        self.note.setText(message)
        self.note.show()
        self.adopt_button.setEnabled(False)
        self.wyckoff_button.setEnabled(False)

    def _show_setting_note(self) -> None:
        current = self.document.structure.space_group
        if not self.info.is_standard_setting:
            self.standardize.setEnabled(True)
            self.note.setText(
                "This cell is not in the standard setting of "
                f"{self.info.international}. Adopting the group will "
                "re-express the cell, which moves the atoms; untick "
                "the box above to keep the cell as it is.")
            self.note.show()
            return
        self.standardize.setEnabled(True)
        if current.number == self.info.number:
            self.note.setText(
                f"Already {current.short_name} -- adopting reduces the "
                f"cell to its asymmetric unit.")
            self.note.show()
        else:
            self.note.hide()

    def _fill_table(self) -> None:
        cell = self.document.cell
        seen: dict[int, int] = {}
        for atom in range(cell.n_atoms):
            parent = int(self.info.equivalent_atoms[atom])
            seen[parent] = seen.get(parent, 0) + 1

        self.table.setRowCount(len(seen))
        for row, (parent, multiplicity) in enumerate(
                sorted(seen.items())):
            values = [
                cell.labels[parent] or str(parent),
                cell.elements[parent],
                f"{multiplicity}{self.info.wyckoffs[parent]}",
                self.info.site_symmetry[parent],
                str(multiplicity),
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column >= 2:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, column, item)

    # -- committing ----------------------------------------------------

    def adopt(self) -> None:
        standardize = self.standardize.isChecked()
        report = self.document.find_symmetry(self.symprec(),
                                             standardize)
        if report is not None and not report.ok:
            self.note.setText(report.message)
            self.note.show()
            return
        # Only when there was a setting to move out of: adopting in
        # the standard setting reduces the cell to its asymmetric unit
        # and leaves the box where it was, and a camera reset there
        # would be the view jumping for nothing.
        self.re_expressed = (standardize
                             and not self.info.is_standard_setting)
        self.accept()

    def label_only(self) -> None:
        self.document.assign_wyckoff(self.symprec())
        self.accept()

    @classmethod
    def ask(cls, document, parent=None) -> bool:
        """Returns whether the structure was changed."""
        return cls(document, parent).exec() == QDialog.Accepted
