"""
xtalapp.dialogs.bond_rules
==========================
The criteria bond perception works to, made reachable.

``BondRules`` has carried all of this since phase 1 -- ``scale``,
``delta``, ``min_distance``, ``pair_ranges``, ``forbidden``,
``allow_metal_metal`` -- ``SetBondRules`` has made a change to it
undoable, and ``bonds.json`` has saved it.  What was missing was any
way to reach it, so a structure whose bonds came out wrong could only
be edited one bond at a time.

Three things about the design are deliberate.

**The preview says what changes, not what there is.**  "6 added, 2
removed" against the bonds as they currently stand.  A total alone
hides the setting that swaps one bond for another, which is the most
confusing thing perception does and the one a person most needs to
see.

**Tolerance is a number, not a slider.**  ``scale`` is not linear in
the way people expect: rutile keeps exactly its 12 Ti-O bonds anywhere
from 1.05 to 1.45 and then jumps to 28 at 1.6 when the second
coordination shell arrives.  A slider with no figure beside it makes
the plateau invisible and the cliff a surprise, so the count travels
with the number and the slider is there to sweep, not to set.

**Metal-metal is its own control, not a finer tolerance.**  No amount
of loosening ``scale`` gives rutile a Ti-Ti bond while the flag is off;
turning it on at the default 1.15 takes the cell from 12 bonds to 22.
An alloy needs it first and needs it findable, so it sits at the top
rather than in the table.

The per-pair table is keyed on the elements actually in the structure,
which keeps it to a handful of rows for anything real -- and makes
"which atoms are included" a question about this crystal rather than
about the periodic table.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from xtal.commands import bonds as bond_commands
from xtal.core import bonding

# The slider is a coarse sweep over the useful range of ``scale``; the
# spin box beside it is what actually sets the value.
SLIDER_STEPS = 100
SCALE_MIN = 0.80
SCALE_MAX = 2.00

#: A blank min/max cell means "use the covalent radii", which is what
#: every pair does until someone says otherwise.
AUTOMATIC = ""


class BondRulesDialog(QDialog):
    """Edit a structure's bond perception criteria, with a live count
    of what they would change."""

    def __init__(self, document=None, parent=None, rules=None):
        super().__init__(parent)
        # With no document this is the same form over the criteria a
        # *newly opened* structure starts from -- Preferences >
        # Bonding, where they could previously be reached only by
        # opening this dialog on a structure and ticking a box, so a
        # user with no file open could not set them at all.
        self.document = document
        self.structure = None if document is None else document.structure
        self.defaults_mode = document is None
        self.setWindowTitle("Default bond rules" if self.defaults_mode
                            else "Bond rules")
        self._loading = True

        if rules is None:
            rules = {} if self.structure is None else \
                self.structure.bond_rules
        rules = bonding.BondRules.from_dict(rules)
        # Nothing to compare against with no structure, which is what
        # makes this the mode with no preview: the count of what a
        # rule changes is a fact about a crystal.
        self._before = set() if self.structure is None else \
            {b.key() for b in bonding.perceive(self.structure)}

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_tolerance(rules))
        layout.addWidget(self._build_pairs(rules))

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.remember = QCheckBox(
            "Use these rules for structures opened from now on")
        self.remember.setToolTip(
            "The rules belong to this structure and travel with the "
            "project; this also makes them the starting point for new "
            "documents")
        # In defaults mode there is nothing else these could be for.
        self.remember.setVisible(not self.defaults_mode)
        layout.addWidget(self.remember)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
            | QDialogButtonBox.RestoreDefaults)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(
            QDialogButtonBox.RestoreDefaults).clicked.connect(
                self.restore_defaults)
        layout.addWidget(self.buttons)

        if self.defaults_mode:
            # Nothing here is a table of a crystal's elements, so the
            # form is a column of numbers and does not want the width
            # one needs.
            self.resize(520, self.sizeHint().height())

        self._loading = False
        self._preview()

    # ==================================================================
    #  CONSTRUCTION
    # ==================================================================

    def _build_tolerance(self, rules) -> QGroupBox:
        box = QGroupBox("Tolerance")
        form = QFormLayout(box)

        self.scale = QDoubleSpinBox()
        self.scale.setDecimals(2)
        self.scale.setSingleStep(0.05)
        self.scale.setRange(SCALE_MIN, SCALE_MAX)
        self.scale.setValue(rules.scale)
        # The slider beside it takes the width it is given; without a
        # floor the number this dialog is *about* is squeezed until
        # its own digits are clipped.
        self.scale.setMinimumWidth(80)
        self.scale.setToolTip(
            "Two atoms bond when they are closer than this multiple of "
            "the sum of their covalent radii")
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, SLIDER_STEPS)
        self.slider.setValue(self._to_slider(rules.scale))
        self.scale.valueChanged.connect(self._on_scale)
        self.slider.valueChanged.connect(self._on_slider)

        row = QHBoxLayout()
        row.addWidget(self.scale)
        row.addWidget(self.slider, 1)
        form.addRow("Radius factor", row)

        self.delta = QDoubleSpinBox()
        self.delta.setDecimals(2)
        self.delta.setSingleStep(0.05)
        self.delta.setRange(-1.0, 1.0)
        self.delta.setSuffix(" A")
        self.delta.setValue(rules.delta)
        self.delta.setToolTip(
            "Added to every cutoff after the radius factor; leave at "
            "zero unless one particular contact needs rescuing")
        form.addRow("Extra allowance", self.delta)
        self.delta.valueChanged.connect(self._preview)

        self.min_distance = QDoubleSpinBox()
        self.min_distance.setDecimals(2)
        self.min_distance.setSingleStep(0.05)
        self.min_distance.setRange(0.0, 2.0)
        self.min_distance.setSuffix(" A")
        self.min_distance.setValue(rules.min_distance)
        self.min_distance.setToolTip(
            "Closer than this is two atoms on top of each other, not a "
            "bond -- disordered sites and partial occupancies")
        form.addRow("Ignore closer than", self.min_distance)
        self.min_distance.valueChanged.connect(self._preview)

        self.metal_metal = QCheckBox("Allow metal-metal bonds")
        self.metal_metal.setChecked(rules.allow_metal_metal)
        self.metal_metal.setToolTip(
            "Off by default, because a metal oxide otherwise draws its "
            "cations bonded to each other.  An alloy or an "
            "intermetallic needs it on, and no amount of loosening the "
            "radius factor substitutes for it.")
        self.metal_metal.toggled.connect(self._preview)
        form.addRow(self.metal_metal)
        return box

    def _build_pairs(self, rules) -> QGroupBox:
        """One row per unordered pair of elements *in this structure*.

        Not per pair in the periodic table: MFU-4l has six elements and
        therefore twenty-one rows, which is a table somebody can read.
        """
        box = QGroupBox("Element pairs")
        layout = QVBoxLayout(box)
        blank_note = QLabel(
            "Leave the distances blank to use the covalent radii.")
        layout.addWidget(blank_note)

        if self.structure is None:
            # No crystal to key the rows on, so the only pairs worth a
            # row are the ones the stored defaults already name.  The
            # rest of the periodic table would be 8000 rows of
            # "automatic".
            self.pairs = sorted(
                {tuple(sorted(pair)) for pair in
                 list(rules.pair_ranges) + list(rules.forbidden)})
        else:
            elements = sorted(self.structure.elements)
            self.pairs = sorted(
                (a, b) for i, a in enumerate(elements)
                for b in elements[i:])
        self.table = QTableWidget(len(self.pairs), 4)
        self.table.setHorizontalHeaderLabels(
            ["Pair", "Bond", "Min (A)", "Max (A)"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        forbidden = {tuple(sorted(p)) for p in rules.forbidden}

        for row, pair in enumerate(self.pairs):
            name = QTableWidgetItem(f"{pair[0]} - {pair[1]}")
            name.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 0, name)

            allowed = QTableWidgetItem()
            allowed.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            allowed.setCheckState(Qt.Unchecked if pair in forbidden
                                  else Qt.Checked)
            self.table.setItem(row, 1, allowed)

            lo, hi = rules.pair_ranges.get(pair, (None, None))
            self.table.setItem(row, 2, QTableWidgetItem(
                AUTOMATIC if lo is None else f"{float(lo):g}"))
            self.table.setItem(row, 3, QTableWidgetItem(
                AUTOMATIC if hi is None else f"{float(hi):g}"))

        self.table.itemChanged.connect(self._preview)
        layout.addWidget(self.table)
        if self.structure is None and not self.pairs:
            # An empty four-column table reads as something that
            # failed to load, and the note above it is about cells
            # there are none of.  Say why there is nothing in it
            # instead.
            self.table.setVisible(False)
            blank_note.setVisible(False)
            empty = QLabel(
                "A pair's own distances are set from a structure, "
                "because the rows are the elements that are in one.  "
                "Any that a default already carries appear here.")
            # Wrapped, or this one sentence sets the width of the
            # whole dialog.
            empty.setWordWrap(True)
            layout.addWidget(empty)
        return box

    # ==================================================================
    #  VALUES
    # ==================================================================

    def rules(self) -> bonding.BondRules:
        """The criteria the dialog currently describes."""
        ranges: dict = {}
        forbidden: set = set()
        for row, pair in enumerate(self.pairs):
            if self.table.item(row, 1).checkState() != Qt.Checked:
                forbidden.add(pair)
                continue
            lo = _number(self.table.item(row, 2))
            hi = _number(self.table.item(row, 3))
            if hi is None:
                # A minimum on its own has nothing to bound: without a
                # maximum the pair is following the radii anyway, and
                # half a range would silently do nothing.
                continue
            ranges[pair] = (0.0 if lo is None else lo, hi)
        return bonding.BondRules(
            scale=self.scale.value(),
            delta=self.delta.value(),
            min_distance=self.min_distance.value(),
            pair_ranges=ranges, forbidden=forbidden,
            allow_metal_metal=self.metal_metal.isChecked())

    def restore_defaults(self) -> None:
        self._loading = True
        self.scale.setValue(bonding.DEFAULT_SCALE)
        self.slider.setValue(self._to_slider(bonding.DEFAULT_SCALE))
        self.delta.setValue(bonding.DEFAULT_DELTA)
        self.min_distance.setValue(bonding.MIN_BOND_DISTANCE)
        self.metal_metal.setChecked(False)
        for row in range(self.table.rowCount()):
            self.table.item(row, 1).setCheckState(Qt.Checked)
            self.table.item(row, 2).setText(AUTOMATIC)
            self.table.item(row, 3).setText(AUTOMATIC)
        self._loading = False
        self._preview()

    # ==================================================================
    #  PREVIEW
    # ==================================================================

    def _to_slider(self, value: float) -> int:
        span = SCALE_MAX - SCALE_MIN
        return int(round((float(value) - SCALE_MIN) / span
                         * SLIDER_STEPS))

    def _on_scale(self, value: float) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(self._to_slider(value))
        self.slider.blockSignals(False)
        self._preview()

    def _on_slider(self, position: int) -> None:
        span = SCALE_MAX - SCALE_MIN
        self.scale.setValue(SCALE_MIN + span * position / SLIDER_STEPS)

    def difference(self) -> tuple[int, int, int]:
        """``(added, removed, total)`` against the bonds as they
        stand.

        Perceived with the dialog's rules passed in explicitly, which
        is what keeps a preview a preview: rules handed to
        :func:`xtal.core.bonding.perceive` are a question, and neither
        read nor overwrite the graph the structure is carrying.
        """
        after = {b.key() for b in
                 bonding.perceive(self.structure, self.rules())}
        return (len(after - self._before), len(self._before - after),
                len(after))

    def _preview(self) -> None:
        if self._loading:
            return
        if self.defaults_mode:
            self.summary.setText(
                "What a structure opened from now on starts with.  A "
                "structure carries its own rules once it has been "
                "given some, and a project keeps the ones it was "
                "saved with.")
            return
        added, removed, total = self.difference()
        if not added and not removed:
            self.summary.setText(
                f"{total} bonds -- no change from the current rules.")
            return
        self.summary.setText(
            f"{added} bond(s) added, {removed} removed "
            f"-- {total} bonds in the cell.")

    # ==================================================================
    #  ENTRY POINT
    # ==================================================================

    @classmethod
    def ask(cls, document, parent=None, settings=None) -> str | None:
        dialog = cls(document, parent)
        if dialog.exec() != QDialog.Accepted:
            return None
        added, removed, total = dialog.difference()
        rules = dialog.rules().to_dict()
        if settings is not None and dialog.remember.isChecked():
            settings.set_default_bond_rules(rules)

        if not added and not removed:
            return f"bond rules unchanged: {total} bonds"
        document.run(bond_commands.SetBondRules(rules))
        return (f"bond rules applied: {added} added, {removed} removed "
                f"-- {total} bonds")


    @classmethod
    def edit_defaults(cls, settings, parent=None) -> bool:
        """The same form over the criteria new structures start from.

        Returns whether they were changed.  The rules are written to
        the preference and to nothing else -- there is no document
        here to apply them to, and the ones already open keep what
        they were opened with, which is the same promise a document
        makes about its own rules.
        """
        dialog = cls(None, parent, rules=settings.default_bond_rules())
        if dialog.exec() != QDialog.Accepted:
            return False
        settings.set_default_bond_rules(dialog.rules().to_dict())
        return True


def _number(item) -> float | None:
    """A distance typed into the table, or ``None`` for "automatic".

    Anything unparseable reads as automatic rather than raising: the
    cell is free text and the honest response to "1.6q" is the
    behaviour the pair had before it was typed.
    """
    text = (item.text() if item else "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None
