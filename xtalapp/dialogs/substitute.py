"""
xtalapp.dialogs.substitute
==========================
Which group, and on which hydrogens.

Two answers to *where*: the hydrogens selected, or one on every
aromatic ring -- which is how MOF-5 becomes IRMOF-3 without somebody
clicking forty-eight hydrogens.  The placing itself is
:mod:`xtal.build.substitute` and the command
:class:`xtal.commands.atoms.SubstituteHydrogens`; this only asks.

What the answer will do to the space group is said *before* it is
done: one per ring always reduces to P1, and a selected hydrogen
stands for its whole orbit.  A dialog that changed the group silently
would leave somebody wondering where their symmetry went.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)

from xtal.build import substitute
from xtalapp.dialogs.answered import answered

#: The two answers to *Where*.
SELECTED = "The selected hydrogens"
PER_RING = "One on every aromatic ring"


class SubstituteDialog(QDialog):
    """A group, and whether it goes on the selection or every ring."""

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Substitute hydrogens")
        self.document = document

        self.group = QComboBox()
        self.group.addItems(list(substitute.names()))
        self.group.setToolTip(
            "What replaces each hydrogen.  Its first atom goes where the "
            "hydrogen pointed, a bond's length out, and the rest is "
            "turned to where it has the most room")
        self.where = QComboBox()
        self.where.addItems([SELECTED, PER_RING])
        self.where.setToolTip(
            "The hydrogens you selected -- each standing for every copy "
            "of itself the space group makes -- or one on each "
            "aromatic ring, the one with the most room")
        if not self._hydrogens():
            self.where.setCurrentText(PER_RING)

        self.headline = QLabel("")
        self.headline.setWordWrap(True)
        font = self.headline.font()
        font.setBold(True)
        self.headline.setFont(font)
        self.detail = QLabel("")
        self.detail.setWordWrap(True)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                        | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Substitute")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("Group", self.group)
        form.addRow("Where", self.where)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.headline)
        layout.addWidget(self.detail)
        layout.addWidget(self.buttons)
        self.resize(440, 0)

        self.group.currentIndexChanged.connect(self._preview)
        self.where.currentIndexChanged.connect(self._preview)
        self._preview()

    @property
    def per_ring(self) -> bool:
        return self.where.currentText() == PER_RING

    def _hydrogens(self) -> list[int]:
        cell = self.document.cell
        return [a for a in self.document.selection.atoms
                if cell.elements[a] == "H"]

    def _preview(self, *_args) -> None:
        ok = self.buttons.button(QDialogButtonBox.Ok)
        name = self.group.currentText()
        group = self.document.structure.space_group
        notes = []
        if self.per_ring:
            self.headline.setText(
                f"{name} on one hydrogen of every aromatic ring")
            if not group.is_p1:
                notes.append(f"The structure is {group.short_name}: it "
                             f"will be reduced to P1 first, in the same "
                             f"undo step, because one group per ring is "
                             f"not an orbit of any group.")
            ok.setEnabled(bool(name))
        else:
            chosen = self._hydrogens()
            if not chosen:
                self.headline.setText("select the hydrogens to replace, "
                                      "or choose every ring")
                self.detail.setText("")
                ok.setEnabled(False)
                return
            self.headline.setText(
                f"{name} in place of {len(chosen)} selected hydrogen(s)")
            if not group.is_p1:
                notes.append(
                    f"The structure is {group.short_name}: each "
                    f"hydrogen stands for every copy of itself, and "
                    f"all of them are replaced.  If the group does not "
                    f"keep that symmetry the cell is reduced to P1 "
                    f"first, and you are told.")
            ok.setEnabled(bool(name))
        notes.append("Nothing is perceived: the group arrives with its "
                     "own bonds and the one to the atom the hydrogen "
                     "was on.")
        self.detail.setText("  ".join(notes))

    def substitute(self):
        """Run it, with what the dialog shows.  The report."""
        return self.document.substitute(self.group.currentText(),
                                        per_ring=self.per_ring)

    @classmethod
    def ask(cls, document, parent=None):
        with answered(cls(document, parent)) as dialog:
            if dialog.exec() != QDialog.Accepted:
                return None
            return dialog.substitute()
