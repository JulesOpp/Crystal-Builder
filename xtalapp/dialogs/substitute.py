"""
xtalapp.dialogs.substitute
==========================
Which group, and on which hydrogens.

Two answers to *where*: the hydrogens selected -- or fluorines, or
any atom on one bond -- or one on every aromatic ring, which is how
MOF-5 becomes IRMOF-3 without somebody clicking forty-eight
hydrogens.  The group is the library's, one drawn here
(:mod:`xtalapp.dialogs.draw_group`), or one drawn before and kept in
the workspace's ``groups/``.  *Share* takes a seeded fraction of the
selection: a partial esterification of a carbon's phenols.  The
placing itself is :mod:`xtal.build.substitute` and the command
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
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from xtal.build import substitute

#: The two answers to *Where*.
SELECTED = "The selected hydrogens (or halogens)"
PER_RING = "One on every aromatic ring"


def _row(*widgets) -> QWidget:
    row = QWidget()
    line = QHBoxLayout(row)
    line.setContentsMargins(0, 0, 0, 0)
    for widget in widgets:
        line.addWidget(widget, 1 if isinstance(widget, QComboBox) else 0)
    return row


class SubstituteDialog(QDialog):
    """A group, and whether it goes on the selection or every ring."""

    def __init__(self, document, parent=None, folder=None):
        super().__init__(parent)
        self.setWindowTitle("Substitute")
        self.document = document
        self.folder = folder

        self.group = QComboBox()
        self.group.addItems(list(substitute.names()))
        for name, smiles in substitute.saved_groups(folder):
            self.group.addItem(name, smiles)
        self.group.setToolTip(
            "What replaces each hydrogen.  Its first atom goes where the "
            "hydrogen pointed, a bond's length out, and the rest is "
            "turned to where it has the most room")
        self.draw = QPushButton("Draw…")
        self.draw.setToolTip(
            "A group of your own, as SMILES with one [*] where it "
            "bonds.  It is kept in the workspace and listed here from "
            "then on")
        self.draw.clicked.connect(self.draw_group)
        self.where = QComboBox()
        self.where.addItems([SELECTED, PER_RING])
        self.where.setToolTip(
            "The hydrogens you selected -- or fluorines, chlorines: any "
            "atom on one bond -- each standing for every copy of itself "
            "the space group makes; or one on each aromatic ring, the "
            "one with the most room")
        if not self._terminals():
            self.where.setCurrentText(PER_RING)
        self.share = QSpinBox()
        self.share.setRange(1, 100)
        self.share.setValue(100)
        self.share.setSuffix(" %")
        self.share.setToolTip(
            "Substitute this share of the selected atoms, chosen at "
            "random by the seed -- the same seed, the same atoms")
        self.seed = QSpinBox()
        self.seed.setRange(0, 999999)
        self.seed.setPrefix("seed ")

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
        form.addRow("Group", _row(self.group, self.draw))
        form.addRow("Where", self.where)
        form.addRow("Share", _row(self.share, self.seed))
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.headline)
        layout.addWidget(self.detail)
        layout.addWidget(self.buttons)
        self.resize(440, 0)

        self.group.currentIndexChanged.connect(self._preview)
        self.where.currentIndexChanged.connect(self._preview)
        self.share.valueChanged.connect(self._preview)
        self._preview()

    @property
    def per_ring(self) -> bool:
        return self.where.currentText() == PER_RING

    @property
    def fraction(self) -> float:
        return 1.0 if self.per_ring else self.share.value() / 100.0

    def _terminals(self) -> list[int]:
        cell = self.document.cell
        return [a for a in self.document.selection.atoms
                if cell.elements[a] in substitute.TERMINAL]

    def chosen(self):
        """The group the dialog says: a library name, or a drawn
        group built from its SMILES under its own name."""
        smiles = self.group.currentData()
        name = self.group.currentText()
        if smiles:
            return substitute.group(smiles, name=name)
        return name

    def draw_group(self) -> None:
        """*Draw...*: a group of one's own, chosen once it is drawn."""
        from xtalapp.dialogs.draw_group import DrawGroupDialog

        drawn = DrawGroupDialog.ask(self.folder, self)
        if drawn is None:
            return
        name, smiles = drawn
        index = self.group.findText(name)
        if index < 0:
            self.group.addItem(name, smiles)
            index = self.group.count() - 1
        else:
            self.group.setItemData(index, smiles)
        self.group.setCurrentIndex(index)

    def _preview(self, *_args) -> None:
        ok = self.buttons.button(QDialogButtonBox.Ok)
        name = self.group.currentText()
        group = self.document.structure.space_group
        notes = []
        self.share.setEnabled(not self.per_ring)
        self.seed.setEnabled(not self.per_ring
                             and self.share.value() < 100)
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
            chosen = self._terminals()
            if not chosen:
                self.headline.setText("select the hydrogens (or "
                                      "fluorines) to replace, or choose "
                                      "every ring")
                self.detail.setText("")
                ok.setEnabled(False)
                return
            kinds = ", ".join(sorted({self.document.cell.elements[a]
                                      for a in chosen}))
            if self.fraction < 1.0:
                count = int(round(self.fraction * len(chosen)))
                self.headline.setText(
                    f"{name} in place of {count} of the {len(chosen)} "
                    f"selected {kinds}, chosen at random")
            else:
                self.headline.setText(
                    f"{name} in place of {len(chosen)} selected {kinds}")
            if self.fraction < 1.0 and not group.is_p1:
                notes.append(f"The structure is {group.short_name}: it "
                             f"will be reduced to P1 first, because a "
                             f"share of an orbit is not an orbit.")
            elif not group.is_p1:
                notes.append(
                    f"The structure is {group.short_name}: each "
                    f"hydrogen stands for every copy of itself, and "
                    f"all of them are replaced.  If the group does not "
                    f"keep that symmetry the cell is reduced to P1 "
                    f"first, and you are told.")
            ok.setEnabled(bool(name))
        notes.append("Nothing is perceived: the group arrives with its "
                     "own bonds and one to the atom the replaced atom "
                     "was on.")
        self.detail.setText("  ".join(notes))

    def substitute(self):
        """Run it, with what the dialog shows.  The report."""
        return self.document.substitute(self.chosen(),
                                        per_ring=self.per_ring,
                                        fraction=self.fraction,
                                        seed=self.seed.value())

    @classmethod
    def ask(cls, document, parent=None, folder=None):
        dialog = cls(document, parent, folder)
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.substitute()
