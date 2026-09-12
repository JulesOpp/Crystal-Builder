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

Nothing is placed until Fill is pressed.  Placing is random and a
second or so, and a preview that re-ran it on every spinbox step would
be a dialog that stutters for an answer the user has not asked for.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
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
)

from xtal.build import fill
from xtal.io import FORMATS

DEFAULT_COUNT = 20


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
        form.addRow("Count", self.count)
        form.addRow("Overlap scale", self.scale)
        form.addRow("Seed", self.seed)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.headline)
        layout.addWidget(self.detail)
        layout.addWidget(self.buttons)
        self.resize(460, 0)

        for name, structure in sources:
            self.add_source(name, structure, choose=False)
        self._choose_first_source_with_molecules()
        self.source.currentIndexChanged.connect(self._source_changed)
        self.molecule.currentIndexChanged.connect(self._preview)
        self.count.valueChanged.connect(self._preview)
        self.scale.valueChanged.connect(self._preview)
        self._source_changed()

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

    def fill(self) -> str:
        """Run it, with what the dialog shows."""
        guest = self.guest()
        if guest is None:
            return ""
        return self.document.fill_pores(
            guest, self.count.value(),
            overlap_scale=self.scale.value(), seed=self.seed.value())

    @classmethod
    def ask(cls, document, sources=(), parent=None,
            directory: str = "") -> str:
        dialog = cls(document, sources, parent, directory)
        if dialog.exec() != QDialog.Accepted:
            return ""
        return dialog.fill()
