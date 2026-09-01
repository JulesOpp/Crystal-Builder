"""
xtalapp.dialogs.cell_edit
=========================
Editing the cell parameters -- and answering the two questions that
make the edit meaningful.

**What is free.**  A space group does not merely describe a cell, it
constrains one.  In a hexagonal group only *a* and *c* are real
numbers: *b* is *a*, the angles are 90, 90 and 120, and typing
something else does not give a hexagonal crystal with an odd cell, it
gives a structure its own symmetry operations no longer map onto
itself.  So the parameters the group ties down are shown, greyed, and
follow the ones that are free.  The way out is the way out of every
symmetry constraint: change the group, or reduce to P1.

**What is held fixed.**  Stretching *a* from 5 to 6 Angstrom can mean
two opposite things.  Keeping the **fractional** coordinates drags
every atom along with the cell: the crystal is scaled, bonds stretch,
this is a strain.  Keeping the **cartesian** coordinates leaves the
atoms exactly where they are in space and rescales the fractions: the
crystal is unchanged, the box around it is not, this is how vacuum gets
added.  There is no sensible default, so the dialog asks, and says what
each choice does to the density before the choice is made.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGridLayout,
    QLabel,
    QRadioButton,
    QVBoxLayout,
)

from xtal.core.lattice import PARAMETER_NAMES, Lattice

KEEPS = [
    ("fractional", "Keep fractional coordinates",
     "The atoms move with the cell: the structure is strained."),
    ("cartesian", "Keep cartesian coordinates",
     "The atoms stay where they are; only the box changes."),
]


class CellEditDialog(QDialog):
    """The six cell parameters, with the ones the group fixes locked
    to the ones it does not."""

    def __init__(self, structure, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit unit cell")
        self.structure = structure
        self.constraint = structure.space_group.cell_constraint
        self._syncing = False

        self.spins = []
        grid = QGridLayout()
        for index, name in enumerate(PARAMETER_NAMES):
            row, column = divmod(index, 3)
            spin = QDoubleSpinBox()
            if index < 3:
                spin.setRange(0.1, 1000.0)
                spin.setDecimals(5)
                spin.setSingleStep(0.1)
                spin.setSuffix(" A")
            else:
                spin.setRange(1.0, 179.0)
                spin.setDecimals(4)
                spin.setSingleStep(1.0)
                spin.setSuffix(" deg")
            spin.valueChanged.connect(self._on_edited)
            grid.addWidget(QLabel(name), 2 * row, column)
            grid.addWidget(spin, 2 * row + 1, column)
            self.spins.append(spin)

        self.symmetry_note = QLabel()
        self.symmetry_note.setWordWrap(True)
        self.symmetry_note.setStyleSheet(
            "color: #8a5a00; background: #fdf3e0; padding: 5px;")

        self.keeps = []
        keep_box = QVBoxLayout()
        for index, (_name, label, tip) in enumerate(KEEPS):
            button = QRadioButton(label)
            button.setToolTip(tip)
            button.setChecked(index == 0)
            button.toggled.connect(self._preview)
            self.keeps.append(button)
            keep_box.addWidget(button)

        self.preview = QLabel()
        self.preview.setWordWrap(True)

        # Phase I: a metric edit used to silently re-perceive the bond
        # graph, which meant a bond drawn by hand could vanish because
        # a lattice constant was nudged to match a refinement.  It no
        # longer does -- said once, here, because the one case where a
        # cell edit *should* change the bonds (stretching one by 20%)
        # needs to be told the way to ask for that explicitly.
        self.bonds_note = QLabel(
            "The bonds are unchanged by this. Structure ▸ "
            "Recalculate bonds afterwards if the new cell should "
            "change them.")
        self.bonds_note.setWordWrap(True)
        self.bonds_note.setStyleSheet("color: palette(mid);")

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                        | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        reset = self.buttons.addButton(QDialogButtonBox.Reset)
        reset.clicked.connect(self.reset)

        layout = QVBoxLayout(self)
        layout.addLayout(grid)
        layout.addWidget(self.symmetry_note)
        layout.addLayout(keep_box)
        layout.addWidget(self.preview)
        layout.addWidget(self.bonds_note)
        layout.addWidget(self.buttons)

        self._apply_constraint()
        self.reset()

    # -- the symmetry constraint ---------------------------------------

    def _apply_constraint(self) -> None:
        """Lock the parameters the group decides, and say which."""
        for index, spin in enumerate(self.spins):
            follows = self.constraint.follows(index)
            fixed = self.constraint.fixed_at(index)
            spin.setEnabled(self.constraint.is_free(index))
            if follows is not None:
                spin.setToolTip(
                    f"{PARAMETER_NAMES[index]} follows "
                    f"{PARAMETER_NAMES[follows]} in "
                    f"{self.structure.space_group.short_name}")
            elif fixed is not None:
                spin.setToolTip(
                    f"{PARAMETER_NAMES[index]} is {fixed:g} in "
                    f"{self.structure.space_group.short_name}")
            else:
                spin.setToolTip("free to edit")

        group = self.structure.space_group
        if len(self.constraint.free_names) == 6:
            self.symmetry_note.setText(
                f"{group.short_name} is triclinic: every parameter is "
                f"free.")
            self.symmetry_note.setStyleSheet("padding: 5px;")
            return
        self.symmetry_note.setStyleSheet(
            "color: #8a5a00; background: #fdf3e0; padding: 5px;")
        self.symmetry_note.setText(
            f"{group.short_name} is {group.crystal_system}: only "
            f"{', '.join(self.constraint.free_names)} "
            f"{'is' if len(self.constraint.free_names) == 1 else 'are'} "
            f"free ({self.constraint.describe()}). To edit the rest, "
            f"change the space group or reduce to P1.")

    # -- values --------------------------------------------------------

    def parameters(self) -> tuple[float, ...]:
        return tuple(spin.value() for spin in self.spins)

    def lattice(self) -> Lattice | None:
        try:
            return Lattice.from_parameters(*self.parameters())
        except ValueError:
            return None

    def keep(self) -> str:
        for button, (name, _label, _tip) in zip(self.keeps, KEEPS,
                                                strict=True):
            if button.isChecked():
                return name
        return "fractional"

    def reset(self) -> None:
        self._set(self.structure.lattice.parameters)

    def _set(self, parameters) -> None:
        self._syncing = True
        for spin, value in zip(self.spins, parameters, strict=True):
            spin.blockSignals(True)
            spin.setValue(float(value))
            spin.blockSignals(False)
        self._syncing = False
        self._preview()

    def _on_edited(self, *_args) -> None:
        """A free parameter moved: bring the ones that follow it
        along, so the cell on screen is always one the group allows."""
        if self._syncing:
            return
        self._set(self.constraint.apply(self.parameters()))

    # -- preview -------------------------------------------------------

    def _preview(self, *_args) -> None:
        ok_button = self.buttons.button(QDialogButtonBox.Ok)
        lattice = self.lattice()
        if lattice is None or lattice.volume <= 0:
            self.preview.setText("Those angles do not close a cell.")
            self.preview.setStyleSheet("color: #8a5a00;")
            ok_button.setEnabled(False)
            return
        ok_button.setEnabled(True)
        self.preview.setStyleSheet("")

        old = self.structure.lattice.volume
        ratio = lattice.volume / old if old else 1.0
        note = ("the atoms move with the cell"
                if self.keep() == "fractional"
                else "the atoms stay where they are")
        self.preview.setText(
            f"V = {lattice.volume:.3f} A^3  "
            f"({ratio:.4g}x the current {old:.3f});  density scales by "
            f"{1 / ratio:.4g}x -- {note}.")

    # -- running -------------------------------------------------------

    @classmethod
    def ask(cls, document, parent=None):
        dialog = cls(document.structure, parent)
        if dialog.exec() != QDialog.Accepted:
            return None
        lattice = dialog.lattice()
        if lattice is None:
            return None
        return document.set_lattice(lattice, dialog.keep())
