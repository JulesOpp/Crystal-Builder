"""
xtalapp.dialogs.fill_pores
==========================
Which molecule, how many, and how much room there is for them.

The guest comes from somewhere else: a solvent is drawn in a tab of
its own, in a cell of its own, and what is wanted out of that is the
molecule and not the box.  So the first choice is a *source* -- any
open tab, or a file -- and the second is which of the molecules in it,
listed by formula.  A framework in the source is not offered; it is
not something that fits in a pore.

The count is asked for against a number, because the question nobody
can answer by eye is whether forty will fit.  :func:`capacity
<xtal.build.fill.capacity>` is quoted as the most there could be room
for, and when the host has symmetry the dialog says it will be reduced
to P1 first -- a structure that changes space group on the way to
having solvent put in it should not be a surprise found afterwards.

**Or one beside each selected atom** -- a counter-ion by every charged
site of a framework, which random insertion has no reason to put
there.  The count is then the selection's, so its box greys out, and
the dialog says which atoms before anything is placed.  It is a mode
of this dialog and not a command of its own because everything else
about it is the same question: which molecule, and does it fit.

**Or one at a point** -- fractional coordinates somebody already has:
the template in its cage, the molecule a diffraction study located.
It is the third answer to *Where* for the same reason: the question is
still which molecule, and how much room it has there.  The room is
*shown*, not enforced -- the point was chosen, so a crowded one is
inserted anyway and the closest contact is named before and after.
*Turn for most room* tries orientations under the seed; *Keep the
space group* lets the host's operations copy the molecule, and the
preview says how many atoms that makes, which is how a special
position shows itself.

Nothing is placed until Fill is pressed.  Placing is random and a
second or so, and a preview that re-ran it on every spinbox step would
be a dialog that stutters for an answer the user has not asked for.
A point is different: one molecule, and turning it is 15 ms, so its
preview is the placement itself.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from xtal.build import fill
from xtal.io import FORMATS
from xtalapp.widgets import tone

DEFAULT_COUNT = 20

#: The two answers to *Where*.
IN_THE_PORES = "In the pores"
BESIDE = "One beside each selected atom"
AT_POINT = "One at a point (fractional)"


class FillPoresDialog(QDialog):
    """A guest, a count, and the room there is."""

    def __init__(self, document, sources=(), parent=None,
                 directory: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Fill pores with molecules")
        self.document = document
        self.directory = directory
        # ``(name, structure)`` per row of the source combo; molecules
        # are lifted out of a source once, when it is first chosen.
        self._sources: list[tuple[str, object]] = []
        self._guests: dict[int, list] = {}
        self._capacity: dict[tuple, int] = {}

        self.source = QComboBox()
        self.source.setToolTip(
            "Where the molecule comes from: an open tab, or a file.  "
            "Only the molecule is taken, not the cell it was drawn in")
        self.browse = QPushButton("Browse...")
        self.browse.clicked.connect(self._browse)
        source_row = QHBoxLayout()
        source_row.addWidget(self.source, 1)
        source_row.addWidget(self.browse)

        self.molecule = QComboBox()
        self.molecule.setToolTip(
            "Each distinct molecule in the source, by formula.  A "
            "framework is not listed: it never closes, so it is not "
            "something a pore can hold")

        self.where = QComboBox()
        self.where.addItems([IN_THE_PORES, BESIDE, AT_POINT])
        self.where.setToolTip(
            "Anywhere there is room, one copy by each atom that is "
            "selected -- a counter-ion beside every charged site -- or "
            "one copy with its centre at the point given")

        self.xyz = []
        point_row = QHBoxLayout()
        point_row.setContentsMargins(0, 0, 0, 0)
        for axis in "xyz":
            box = QDoubleSpinBox()
            box.setRange(-1.0, 2.0)
            box.setDecimals(4)
            box.setSingleStep(0.05)
            box.setValue(0.5)
            box.setToolTip(f"Fractional {axis} of the molecule's centre")
            self.xyz.append(box)
            point_row.addWidget(box)
        self.from_selection = QPushButton("From selection")
        self.from_selection.setToolTip(
            "The middle of the selected atoms -- a cage's, say")
        self.from_selection.clicked.connect(self._point_from_selection)
        point_row.addWidget(self.from_selection)
        self.point = QWidget()
        self.point.setLayout(point_row)

        self.turn = QCheckBox("Turn for most room")
        self.turn.setToolTip(
            "Try orientations and keep the one whose closest contact "
            "is furthest.  Off, the molecule is put the way round it "
            "was drawn in its source")
        self.keep_group = QCheckBox("Keep the space group")
        self.keep_group.setToolTip(
            "Add the molecule to the asymmetric unit, so the group "
            "copies it to every equivalent point.  Off, the host is "
            "reduced to P1 and gets this one molecule")

        self.warning = QLabel("")
        self.warning.setWordWrap(True)
        tone.set_tone(self.warning, tone.WARNING_BOX)
        self.warning.hide()

        self.inner = self._distance(fill.NEAR[0])
        self.outer = self._distance(fill.NEAR[1])
        near_row = QHBoxLayout()
        near_row.addWidget(self.inner)
        near_row.addWidget(QLabel("to"))
        near_row.addWidget(self.outer)
        near_row.addWidget(QLabel("A"))
        self.near = QWidget()
        self.near.setLayout(near_row)
        near_row.setContentsMargins(0, 0, 0, 0)
        self.near.setToolTip(
            "How far each copy's centre is put from its atom")

        self.count = QSpinBox()
        self.count.setRange(1, 100000)
        self.count.setValue(DEFAULT_COUNT)
        self.count.setToolTip("How many copies to try to place.  "
                              "Fewer are placed when there is no room")

        self.scale = QDoubleSpinBox()
        self.scale.setRange(0.5, 1.2)
        self.scale.setSingleStep(0.05)
        self.scale.setDecimals(2)
        self.scale.setValue(fill.DEFAULT_OVERLAP_SCALE)
        self.scale.setToolTip(
            "Two atoms clash when closer than this times the sum of "
            "their van der Waals radii.  1.0 lets nothing touch, which "
            "is sparser than a real liquid")

        self.seed = QSpinBox()
        self.seed.setRange(0, 2 ** 31 - 1)
        self.seed.setToolTip("The same seed puts the same molecules in "
                             "the same places")

        self.headline = QLabel("")
        self.headline.setWordWrap(True)
        font = self.headline.font()
        font.setBold(True)
        self.headline.setFont(font)
        self.detail = QLabel("")
        self.detail.setWordWrap(True)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                        | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Fill")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("Source", source_row)
        form.addRow("Molecule", self.molecule)
        form.addRow("Where", self.where)
        form.addRow("Point", self.point)
        form.addRow("", self.turn)
        form.addRow("", self.keep_group)
        form.addRow("Distance", self.near)
        form.addRow("Count", self.count)
        form.addRow("Overlap scale", self.scale)
        form.addRow("Seed", self.seed)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.headline)
        layout.addWidget(self.detail)
        layout.addWidget(self.warning)
        layout.addWidget(self.buttons)
        self.resize(460, 0)

        for name, structure in sources:
            self.add_source(name, structure, choose=False)
        self._choose_first_source_with_molecules()
        self.source.currentIndexChanged.connect(self._source_changed)
        self.molecule.currentIndexChanged.connect(self._preview)
        self.count.valueChanged.connect(self._preview)
        self.where.currentIndexChanged.connect(self._preview)
        self.inner.valueChanged.connect(self._preview)
        self.outer.valueChanged.connect(self._preview)
        self.scale.valueChanged.connect(self._preview)
        self.seed.valueChanged.connect(self._preview)
        for box in self.xyz:
            box.valueChanged.connect(self._preview)
        self.turn.toggled.connect(self._preview)
        self.keep_group.toggled.connect(self._preview)
        self._source_changed()

    @staticmethod
    def _distance(value: float) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(1.0, 15.0)
        box.setSingleStep(0.5)
        box.setDecimals(1)
        box.setValue(value)
        return box

    @property
    def beside(self) -> bool:
        """Whether each copy goes by a selected atom."""
        return self.where.currentText() == BESIDE

    @property
    def at_point(self) -> bool:
        """Whether one copy goes at the point given."""
        return self.where.currentText() == AT_POINT

    @property
    def frac(self) -> tuple:
        return tuple(box.value() for box in self.xyz)

    def set_point(self, frac) -> None:
        for box, value in zip(self.xyz, frac, strict=True):
            box.setValue(float(value))

    def _point_from_selection(self) -> None:
        centre = self.document.selection_centre()
        if centre is not None:
            self.set_point(centre)

    # -- sources -------------------------------------------------------

    def add_source(self, name: str, structure, choose: bool = True
                   ) -> None:
        self._sources.append((name, structure))
        self.source.addItem(name)
        if choose:
            self.source.setCurrentIndex(self.source.count() - 1)

    def open_file(self, path) -> bool:
        """Add a file as a source and choose it.  Says whether it read."""
        path = Path(path)
        try:
            structure = FORMATS.read(path)
        except (ValueError, OSError, KeyError) as exc:
            self.headline.setText(f"could not read {path.name}")
            self.detail.setText(str(exc))
            return False
        self.add_source(path.name, structure)
        return True

    def _browse(self) -> None:
        filters = [f.filter_string() for f in FORMATS.readable()]
        filters.append("All files (*)")
        path, _ = QFileDialog.getOpenFileName(
            self, "Molecule to fill with", self.directory,
            ";;".join(filters))
        if path:
            self.open_file(path)

    def guests(self, row: int | None = None) -> list:
        row = self.source.currentIndex() if row is None else row
        if row < 0:
            return []
        if row not in self._guests:
            try:
                self._guests[row] = fill.guest_molecules(
                    self._sources[row][1])
            except ValueError:
                self._guests[row] = []
        return self._guests[row]

    def _choose_first_source_with_molecules(self) -> None:
        """Another tab with a molecule in it, before this one.

        The tab being filled is usually a framework and has none, and
        when it has some -- solvent already in the pore -- the likelier
        wish is still the molecule somebody drew somewhere else.
        """
        rows = range(len(self._sources))
        others = [r for r in rows
                  if self._sources[r][1] is not self.document.structure]
        for row in [*others, *rows]:
            if self.guests(row):
                self.source.setCurrentIndex(row)
                return

    def _source_changed(self, *_args) -> None:
        self.molecule.blockSignals(True)
        self.molecule.clear()
        for guest in self.guests():
            self.molecule.addItem(
                f"{guest.formula}  ({guest.n_atoms} atoms)")
        self.molecule.blockSignals(False)
        self._preview()

    # -- the answer ----------------------------------------------------

    def guest(self):
        guests = self.guests()
        row = self.molecule.currentIndex()
        return guests[row] if 0 <= row < len(guests) else None

    def capacity(self) -> int:
        guest = self.guest()
        if guest is None:
            return 0
        key = (self.source.currentIndex(), self.molecule.currentIndex(),
               round(self.scale.value(), 3))
        if key not in self._capacity:
            self._capacity[key] = fill.capacity(
                self.document.structure, guest, self.scale.value())
        return self._capacity[key]

    def _preview(self, *_args) -> None:
        ok = self.buttons.button(QDialogButtonBox.Ok)
        guest = self.guest()
        if guest is None:
            self.headline.setText(
                "no molecule to fill with" if self._sources
                else "open a molecule, or browse for one")
            self.detail.setText(
                "The source has no discrete molecule in it -- only a "
                "framework, or nothing at all." if self._sources
                else "")
            ok.setEnabled(False)
            self.warning.hide()
            return
        self.count.setEnabled(not (self.beside or self.at_point))
        self.near.setEnabled(self.beside)
        self.point.setEnabled(self.at_point)
        self.from_selection.setEnabled(
            self.at_point and bool(self.document.selection.atoms))
        self.turn.setEnabled(self.at_point)
        self.keep_group.setEnabled(
            self.at_point
            and not self.document.structure.space_group.is_p1)
        ok.setText("Insert" if self.at_point else "Fill")
        if self.at_point:
            self._preview_point(guest, ok)
            return
        self.warning.hide()
        if self.beside:
            self._preview_beside(guest, ok)
            return
        room = self.capacity()
        count = self.count.value()
        self.headline.setText(
            f"room for at most about {room} {guest.formula}; "
            f"will try to place {count}")
        notes = []
        if count > room:
            notes.append("That is more than the free volume could "
                         "hold, so fewer will be placed.")
        group = self.document.structure.space_group
        if not group.is_p1:
            n = self.document.cell.n_atoms
            notes.append(
                f"The host is {group.short_name}: it will be reduced "
                f"to P1 ({n} atoms) first, in the same undo step, so "
                f"that each molecule is placed once rather than "
                f"multiplied by the group.")
        notes.append("Bonds are not recalculated: each molecule keeps "
                     "its own and gains none to the host.")
        self.detail.setText("  ".join(notes))
        ok.setEnabled(True)

    def _preview_beside(self, guest, ok) -> None:
        selected = len(self.document.selection.atoms)
        if not selected:
            self.headline.setText(
                "select the atoms to put one beside first")
            self.detail.setText(
                "One copy goes by each selected atom -- a carboxylate "
                "oxygen for a cation, say.  Close this, select them, "
                "and open it again.")
            ok.setEnabled(False)
            return
        self.headline.setText(
            f"will place one {guest.formula} beside each of "
            f"{selected} selected atom(s)")
        notes = ["An atom with no room within the distance is named "
                 "afterwards, and the others still get theirs."]
        group = self.document.structure.space_group
        if not group.is_p1:
            notes.append(
                f"The host is {group.short_name}: it will be reduced "
                f"to P1 first, in the same undo step, and only the "
                f"atoms selected get one -- not their symmetry "
                f"copies.")
        notes.append("Nothing is bonded: each copy sits beside its "
                     "atom, not on it.")
        self.detail.setText("  ".join(notes))
        ok.setEnabled(self.inner.value() < self.outer.value())

    def placement(self):
        """Where the molecule would go at the point, as the dialog
        stands -- what the preview shows and Insert commits."""
        guest = self.guest()
        if guest is None:
            return None
        return fill.at_point(
            self.document.structure, guest, self.frac,
            turn=self.turn.isChecked(), keep_group=self.keeping_group,
            overlap_scale=self.scale.value(), seed=self.seed.value())

    @property
    def keeping_group(self) -> bool:
        return self.keep_group.isEnabled() and self.keep_group.isChecked()

    def _preview_point(self, guest, ok) -> None:
        placement = self.placement()
        where = ", ".join(f"{x:.4f}" for x in self.frac)
        self.headline.setText(f"will insert one {guest.formula} at "
                              f"({where})")
        notes = []
        if placement.contact is not None:
            notes.append(f"Closest: {placement.contact.sentence()}.")
        group = self.document.structure.space_group
        if self.keeping_group:
            notes.append(
                f"Kept in {group.short_name}: the group copies it to "
                f"{placement.atoms_made} atoms.")
        elif not group.is_p1:
            n = self.document.cell.n_atoms
            notes.append(
                f"The host is {group.short_name}: it will be reduced "
                f"to P1 ({n} atoms) first, in the same undo step, so "
                f"that this is the one molecule added.")
        notes.append("Bonds are not recalculated: the molecule keeps "
                     "its own and gains none to the host.")
        self.detail.setText("  ".join(notes))
        warnings = placement.warnings()
        self.warning.setText("\n\n".join(
            [*warnings, "It will still be inserted: the point is "
             "yours."] if warnings else []))
        self.warning.setVisible(bool(warnings))
        ok.setEnabled(True)

    def fill(self):
        """Run it, with what the dialog shows: a status line, or for a
        point the report with its warnings."""
        guest = self.guest()
        if guest is None:
            return ""
        if self.at_point:
            return self.document.place_molecule(
                guest, self.frac, turn=self.turn.isChecked(),
                keep_group=self.keeping_group,
                overlap_scale=self.scale.value(),
                seed=self.seed.value())
        return self.document.fill_pores(
            guest, self.count.value(),
            overlap_scale=self.scale.value(), seed=self.seed.value(),
            beside=self.beside,
            near=(self.inner.value(), self.outer.value()))

    @classmethod
    def ask(cls, document, sources=(), parent=None,
            directory: str = ""):
        dialog = cls(document, sources, parent, directory)
        if dialog.exec() != QDialog.Accepted:
            return ""
        return dialog.fill()
