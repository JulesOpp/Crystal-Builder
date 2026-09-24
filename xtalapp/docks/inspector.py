"""
xtalapp.docks.inspector
=======================
What is selected, and the fields that edit it.

The panel always tells the truth about symmetry.  Clicking one atom of
a four-fold orbit and typing a new element changes all four, because
the asymmetric unit is what the file stores -- so the panel says so, in
the line above the buttons, before anything is changed.  The way out is
the same as in VESTA: reduce to P1 first, then the atoms are
independent.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from xtal.core import elements as el
from xtal.core import neighbors
from xtalapp.docks import scrolling
from xtalapp.widgets.tone import WARNING_BOX, set_tone

COMMON_ELEMENTS = ["H", "C", "N", "O", "F", "Na", "Mg", "Al", "Si",
                   "P", "S", "Cl", "K", "Ca", "Ti", "Cr", "Mn", "Fe",
                   "Co", "Ni", "Cu", "Zn", "Br", "Zr", "Ag", "Cd",
                   "I", "Ba", "W", "Pt", "Au", "Pb"]


def _force_field_type(document, atom: int) -> str:
    """``"Zn3+2  (tetrahedral Zn(II))"`` for one atom of the cell.

    Both, never one: the five-character name is what the Force Field
    panel's override is stored as and what a paper is checked against,
    and the words are the only half of it that can be read.  A
    structure the force field cannot type at all -- an element outside
    UFF -- simply has no such line, because the Inspector is not where
    that gets explained.
    """
    from xtal.ff.uff import params

    try:
        typing = document.atom_types()
        name = typing.types[atom].name
        description = params.get(name).description
    except Exception:                               # noqa: BLE001
        return ""
    return f"{name}  ({description})" if description else name


class InspectorDock(QDockWidget):
    """Properties of the current selection."""

    deleteRequested = Signal()
    reduceToP1Requested = Signal()

    def __init__(self, parent=None):
        super().__init__("Inspector", parent)
        self.setObjectName("InspectorDock")
        self.document = None
        self._refreshing = False

        self.headline = QLabel("Nothing selected")
        self.headline.setWordWrap(True)
        font = self.headline.font()
        font.setBold(True)
        self.headline.setFont(font)

        self.element = QComboBox()
        self.element.setEditable(True)
        self.element.addItems(COMMON_ELEMENTS)
        self.element.setInsertPolicy(QComboBox.NoInsert)
        self.element.activated.connect(self._commit_element)
        self.element.lineEdit().editingFinished.connect(
            self._commit_element)

        self.label = QLineEdit()
        self.label.editingFinished.connect(self._commit_label)

        self.coords = []
        for axis in "xyz":
            spin = QDoubleSpinBox()
            spin.setRange(-99.0, 99.0)
            spin.setDecimals(5)
            spin.setSingleStep(0.001)
            spin.setToolTip(f"fractional {axis} of the parent site")
            spin.editingFinished.connect(self._commit_coordinates)
            self.coords.append(spin)

        self.occupancy = QDoubleSpinBox()
        self.occupancy.setRange(0.001, 1.0)
        self.occupancy.setDecimals(4)
        self.occupancy.setSingleStep(0.05)
        self.occupancy.editingFinished.connect(self._commit_occupancy)

        self.u_iso = QDoubleSpinBox()
        self.u_iso.setRange(0.0, 5.0)
        self.u_iso.setDecimals(5)
        self.u_iso.setSingleStep(0.005)
        self.u_iso.editingFinished.connect(self._commit_u_iso)

        self.charge = QDoubleSpinBox()
        self.charge.setRange(-9.0, 9.0)
        self.charge.setDecimals(3)
        self.charge.setSingleStep(0.5)
        self.charge.editingFinished.connect(self._commit_charge)

        form = QFormLayout()
        form.setContentsMargins(8, 6, 8, 6)
        form.addRow("Element", self.element)
        form.addRow("Label", self.label)
        coordinates = QHBoxLayout()
        for spin in self.coords:
            coordinates.addWidget(spin)
        form.addRow("Fractional", coordinates)
        form.addRow("Occupancy", self.occupancy)
        form.addRow("U iso", self.u_iso)
        form.addRow("Charge", self.charge)
        self.form_widget = QWidget()
        self.form_widget.setLayout(form)

        self.symmetry_note = QLabel()
        self.symmetry_note.setWordWrap(True)
        set_tone(self.symmetry_note, WARNING_BOX)
        self.symmetry_note.hide()

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        mono = QFont("Menlo")
        mono.setStyleHint(QFont.Monospace)
        mono.setPointSize(10)
        self.details.setFont(mono)
        self.details.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.details.setMaximumHeight(190)

        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self.deleteRequested.emit)
        self.p1_button = QPushButton("Reduce to P1")
        self.p1_button.setToolTip(
            "Expand every symmetry orbit into independent sites, so "
            "single atoms can be edited")
        self.p1_button.clicked.connect(self.reduceToP1Requested.emit)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(8, 0, 8, 8)
        buttons.addWidget(self.delete_button)
        buttons.addWidget(self.p1_button)
        buttons.addStretch(1)

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 0)
        layout.setSpacing(6)
        layout.addWidget(self.headline)
        layout.addWidget(self.symmetry_note)
        layout.addWidget(self.form_widget)
        layout.addWidget(self.details, 1)
        layout.addLayout(buttons)

        container = QWidget()
        container.setLayout(layout)
        # Scrolls rather than holding the column open -- see
        # xtalapp.docks.scrolling.
        self.setWidget(scrolling(container))
        self.set_document(None)

    # -- binding -------------------------------------------------------

    def set_document(self, document) -> None:
        self.document = document
        self.refresh()

    def refresh(self) -> None:
        document = self.document
        if document is None or document.selection.is_empty:
            self.headline.setText("Nothing selected")
            self.form_widget.setEnabled(False)
            self.details.setPlainText(
                "Click an atom or a bond in the viewport.")
            self.symmetry_note.hide()
            self.delete_button.setEnabled(False)
            self.p1_button.setEnabled(document is not None
                                      and not document.structure.is_p1)
            return

        selection = document.selection
        self.delete_button.setEnabled(bool(selection.atoms))
        self.p1_button.setEnabled(not document.structure.is_p1)

        if selection.atoms:
            self.headline.setText(document.selection_summary())
            self._show_symmetry_note(document)
            if len(selection.atoms) == 1:
                self._show_single_atom(document,
                                       next(iter(selection.atoms)))
            else:
                self._show_many_atoms(document)
        else:
            self.headline.setText(document.selection_summary())
            self.form_widget.setEnabled(False)
            self.details.setPlainText(self._describe_bonds(document))
            self.symmetry_note.hide()

    def _show_symmetry_note(self, document) -> None:
        if document.selection_is_orbit_complete():
            self.symmetry_note.hide()
            return
        self.symmetry_note.setText(
            f"{document.selection_orbit_report()}. Editing or deleting "
            f"here changes every image. Reduce to P1 to edit atoms "
            f"one at a time.")
        self.symmetry_note.show()

    def _show_single_atom(self, document, atom: int) -> None:
        cell = document.cell
        site_index = int(cell.site_idx[atom])
        site = document.structure.sites[site_index]

        self._refreshing = True
        self.form_widget.setEnabled(True)
        if self.element.findText(site.element) < 0:
            self.element.addItem(site.element)
        self.element.setCurrentText(site.element)
        self.label.setText(site.label)
        for spin, value in zip(self.coords, site.frac, strict=True):
            spin.setValue(float(value))
        self.occupancy.setValue(float(site.occupancy))
        self.u_iso.setValue(float(site.u_iso or 0.0))
        self.charge.setValue(float(site.charge or 0.0))
        self._refreshing = False

        self.details.setPlainText(
            self._describe_atom(document, atom, site_index, site))

    def _show_many_atoms(self, document) -> None:
        self._refreshing = True
        self.form_widget.setEnabled(True)
        for widget in (self.label, self.occupancy, self.u_iso,
                       self.charge, *self.coords):
            widget.setEnabled(False)
        self._refreshing = False
        sites = sorted(document.selected_sites())
        lines = [f"{len(document.selection.atoms)} atoms from "
                 f"{len(sites)} site(s)", ""]
        for index in sites:
            site = document.structure.sites[index]
            x, y, z = site.frac
            lines.append(f"  {site.label or site.element:<8s} "
                         f"{site.element:<3s} {x: .5f} {y: .5f} "
                         f"{z: .5f}  x{document.cell.multiplicity(index)}")
        lines.append("")
        lines.append("The element box applies to all of them.")
        self.details.setPlainText("\n".join(lines))

    def _describe_atom(self, document, atom, site_index, site) -> str:
        cell = document.cell
        lattice = document.structure.lattice
        op = int(cell.op_idx[atom])
        frac = cell.frac[atom]
        cart = lattice.to_cart(frac)
        lines = [
            f"site           {site_index}  "
            f"({site.label or site.element})",
            f"element        {site.element}  "
            f"(Z = {el.atomic_number(site.element)}, "
            f"{el.element(site.element).name})",
            f"multiplicity   {cell.multiplicity(site_index)}"
            + (f"   Wyckoff {site.wyckoff}" if site.wyckoff else ""),
            f"operation      "
            f"{document.structure.space_group.triplets[op]}",
            f"fractional     {frac[0]: .5f} {frac[1]: .5f} "
            f"{frac[2]: .5f}",
            f"cartesian      {cart[0]: .4f} {cart[1]: .4f} "
            f"{cart[2]: .4f}   (A)",
            f"occupancy      {site.occupancy:.4f}",
        ]
        force_field = _force_field_type(document, atom)
        if force_field:
            lines.append(f"force field    {force_field}")
        graph = document.graph
        partners = graph.bonds_of(atom)
        if partners:
            lines.append("")
            lines.append("neighbours")
            # As long as the bonds are now: ``distance`` is from when
            # they were perceived, which a relaxation or a drag since
            # has made a number from before.
            matrix = lattice.matrix
            lengths = [(bond.length(cell.frac, matrix), bond)
                       for bond in partners]
            for length, bond in sorted(lengths, key=lambda p: p[0]):
                other = bond.j if bond.i == atom else bond.i
                name = cell.labels[other] or cell.elements[other]
                lines.append(f"  {name:<8s} {length:6.3f} A")
        return "\n".join(lines)

    def _describe_bonds(self, document) -> str:
        cell = document.cell
        lattice = document.structure.lattice
        lines = []
        for key in sorted(document.selection.bonds):
            i, j, _image = key
            if i < 0 or j < 0 or max(i, j) >= cell.n_atoms:
                continue
            distance = neighbors.min_image_distance(
                cell.frac[i], cell.frac[j], lattice)
            a = cell.labels[i] or cell.elements[i]
            b = cell.labels[j] or cell.elements[j]
            lines.append(f"{a} - {b}   {distance:.3f} A")
        return "\n".join(lines) or "bond"

    # -- committing edits ----------------------------------------------

    def _site(self) -> int | None:
        document = self.document
        if document is None or len(document.selection.atoms) != 1:
            return None
        atom = next(iter(document.selection.atoms))
        return int(document.cell.site_idx[atom])

    def _commit_element(self, *_args) -> None:
        if self._refreshing or self.document is None:
            return
        symbol = el.canonical_symbol(self.element.currentText())
        if symbol is None:
            self.refresh()          # put the old value back
            return
        if self.document.selection.atoms:
            self.document.set_selection_element(symbol)

    def _commit_property(self, **values) -> None:
        site = self._site()
        if site is None or self._refreshing:
            return
        self.document.set_site_property(site, **values)

    def _commit_label(self) -> None:
        self._commit_property(label=self.label.text().strip())

    def _commit_occupancy(self) -> None:
        self._commit_property(occupancy=self.occupancy.value())

    def _commit_u_iso(self) -> None:
        value = self.u_iso.value()
        self._commit_property(u_iso=value if value > 0 else None)

    def _commit_charge(self) -> None:
        value = self.charge.value()
        self._commit_property(charge=value if value else None)

    def _commit_coordinates(self) -> None:
        import numpy as np
        self._commit_property(
            frac=np.array([spin.value() for spin in self.coords]))
