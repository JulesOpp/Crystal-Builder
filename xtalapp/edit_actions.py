"""
xtalapp.edit_actions
====================
The window's editing, selecting, bonding and measuring commands, moved
out of :mod:`xtalapp.mainwindow` unchanged.
"""

from __future__ import annotations

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QInputDialog, QMessageBox

from xtal.build import BuildError
from xtal.commands.clipboard import Fragment
from xtalapp.dialogs.add_atom import AddAtomDialog
from xtalapp.dialogs.add_centroid import AddCentroidDialog
from xtalapp.dialogs.bond_rules import BondRulesDialog


class EditActions:
    """Undo and redo, the clipboard, adding and changing atoms,
    connection points, bonds, selection, planes and measurements.

    A mixin of :class:`~xtalapp.mainwindow.MainWindow`: the methods
    read the window's own attributes through ``self``, which is what
    let them move without a line of their bodies changing.  Every one
    asks the :class:`~xtalapp.document.Document` to make the change;
    none edits a structure itself.
    """

    def undo(self) -> None:
        document = self.current_document()
        if document is not None and document.can_undo:
            self.statusBar().showMessage(
                f"undid {document.undo()}", 4000)

    def redo(self) -> None:
        document = self.current_document()
        if document is not None and document.can_redo:
            self.statusBar().showMessage(
                f"redid {document.redo()}", 4000)

    def copy(self) -> None:
        """Copy the selection, to our own clipboard and the system's."""
        document = self.current_document()
        if document is None or not document.selection.atoms:
            return
        self.clipboard_fragment = document.copy_selection()
        QGuiApplication.clipboard().setText(
            self.clipboard_fragment.to_xyz())
        self.statusBar().showMessage(
            f"copied {self.clipboard_fragment.n_atoms} atoms "
            f"({self.clipboard_fragment.formula})", 4000)

    def cut(self) -> None:
        document = self.current_document()
        if document is None or not document.selection.atoms:
            return
        self.clipboard_fragment = document.cut_selection()
        QGuiApplication.clipboard().setText(
            self.clipboard_fragment.to_xyz())
        self.statusBar().showMessage(
            f"cut {self.clipboard_fragment.n_atoms} atoms", 4000)

    def paste(self) -> None:
        """Paste our fragment, or whatever XYZ is on the system
        clipboard -- so a fragment copied from another program lands
        here too."""
        document = self.current_document()
        if document is None:
            return
        fragment = self.clipboard_fragment
        text = QGuiApplication.clipboard().text()
        if text.strip():
            try:
                external = Fragment.from_xyz(text)
            except ValueError:
                external = None
            if external is not None and (
                    fragment.is_empty
                    or text.strip() != fragment.to_xyz().strip()):
                fragment = external
        if fragment.is_empty:
            self.statusBar().showMessage("nothing to paste", 4000)
            return
        self.statusBar().showMessage(document.paste(fragment), 6000)

    def duplicate(self) -> None:
        document = self.current_document()
        if document is not None and document.selection.atoms:
            self.statusBar().showMessage(
                document.duplicate_selection(), 6000)

    def add_atom_dialog(self) -> None:
        document = self.current_document()
        if document is None:
            return
        values = AddAtomDialog.ask(document.structure.lattice, self,
                                   self.element_combo.currentText())
        if values is None:
            return
        self.statusBar().showMessage(document.add_atom(**values), 4000)

    def insert_molecule_dialog(self) -> None:
        """Build a molecule from a string and paste it into this cell.

        A shell action rather than a module one, and
        :mod:`xtal.modules.build` gives the reason: a module's
        returned structure either replaces the open document or opens
        a tab of its own, and a paste is neither.  What it borrows
        from the registry is the parameter declaration and the dialog
        name, so the box that inserts and the box that builds a new
        document are one dialog with one set of parameters.
        """
        document = self.current_document()
        if document is None:
            return
        from xtal.modules.build import BUILD, INSERT, molecule_for
        from xtalapp.dialogs import module_dialog
        values = module_dialog(INSERT.dialog).ask(
            BUILD, INSERT, self, self._insert_values)
        if values is None:
            return
        self._insert_values = values
        try:
            molecule = molecule_for(values, connection_points=False)
        except BuildError as exc:
            self.show_message(str(exc))
            return
        self.show_status(document.paste(molecule.to_fragment(),
                                        self.paste_offset()))

    def paste_offset(self):
        """Where something dropped into the structure lands.

        The camera's focal point -- the middle of the picture -- or
        ``None``, which is what
        :meth:`xtal.commands.clipboard.Fragment.to_sites` already
        reads as the centre of the cell.

        Asked for defensively rather than assumed, because the
        viewport is injected: the stub the widget tests use is a bare
        ``QWidget`` with no camera and no intention of growing one,
        and a shell that needed it to would be a shell that cannot be
        tested without a GL context.  Both answers are real -- the
        cell centre is where a paste has always landed -- so a missing
        camera is not an error to report.
        """
        viewport = self.current_viewport()
        focal = getattr(viewport, "focal_point", None)
        if focal is None:
            return None
        try:
            return focal()
        except Exception:                           # noqa: BLE001
            # A tab whose render window has not been realised yet has
            # a renderer but nothing for it to look at.
            return None

    def save_building_block(self) -> None:
        """Write the open molecule into the folder the MOF builder
        reads its own blocks from.

        The last step of the building-block path and the one that
        closes it: what is written here appears in the MOF picker next
        time with nothing further clicked -- see
        :mod:`xtalapp.dialogs.save_block`.
        """
        document = self.current_document()
        if document is None:
            return
        from xtal.mof.block import BlockError, write_building_block
        from xtalapp.dialogs.save_block import SaveBlockDialog
        path = SaveBlockDialog.ask(document.structure, self,
                                   self.settings.mof_bb_dir)
        if path is None:
            return
        try:
            written = write_building_block(document.structure, path)
        except (BlockError, OSError) as exc:
            self.show_message(f"could not write the block: {exc}")
            return
        self.show_status(f"wrote {written.name} -- it is in the MOF "
                         f"builder's picker now")

    def mark_connection_points(self) -> None:
        document = self.current_document()
        if document is not None:
            self.show_status(document.mark_connection_points())

    def mark_one_connection_point(self) -> None:
        document = self.current_document()
        if document is not None:
            self.show_status(document.mark_one_connection_point())

    def add_centroid_dialog(self) -> None:
        document = self.current_document()
        if document is None:
            return
        values = AddCentroidDialog.ask(len(document.selection.atoms),
                                       self,
                                       self.element_combo.currentText())
        if values is None:
            return
        self.show_status(document.add_centroid(**values))

    def merge_atoms(self) -> None:
        document = self.current_document()
        if document is not None:
            self.show_status(document.merge_atoms())

    def recompute_bonds(self) -> None:
        document = self.current_document()
        if document is not None:
            self.show_status(document.recompute_bonds())

    def reset_bonds(self) -> None:
        """Throw away the bond edits and perceive again.

        Separate from Recalculate because the two answer different
        questions: recalculating asks the geometry, resetting also
        withdraws every answer the user has given.  This is the one
        with the key on it -- see the note in :mod:`xtalapp.menus`.
        """
        document = self.current_document()
        if document is not None:
            self.show_status(document.reset_bonds())

    def edit_bond_rules(self) -> None:
        document = self.current_document()
        if document is None:
            return
        message = BondRulesDialog.ask(document, self, self.settings)
        if message:
            self.show_status(message)

    def set_bonds_follow_geometry(self, on: bool) -> None:
        """The preference, and every document already open.

        Applied to the open documents as well as saved, because a
        preference that only takes effect on the next file is one the
        user has to discover twice.
        """
        self.settings.bonds_follow_geometry = bool(on)
        for document in self.documents:
            document.bonds_follow_geometry = bool(on)
        self.show_status(
            "bonds now follow the geometry" if on else
            "bonds change when you recalculate them")

    def set_bond_type(self, order) -> None:
        """Call the selected bonds single, double, triple, aromatic --
        or nothing, and let the geometry decide again."""
        document = self.current_document()
        if document is not None and document.selection.bonds:
            self.show_status(document.set_selected_bond_type(order))

    def select_all(self) -> None:
        document = self.current_document()
        if document is not None:
            document.select_all()

    def select_none(self) -> None:
        document = self.current_document()
        if document is not None:
            document.select_none()

    def invert_selection(self) -> None:
        document = self.current_document()
        if document is not None:
            document.invert_selection()

    def select_element(self, symbol: str) -> None:
        document = self.current_document()
        if document is not None:
            document.select_element(symbol)

    def select_same_element(self) -> None:
        """Grow a one-atom selection to every atom of that element."""
        document = self.current_document()
        if document is None or not document.selection.atoms:
            return
        from xtal.core import selection as sel
        elements = {document.cell.elements[a]
                    for a in document.selection.atoms}
        atoms = set()
        for symbol in elements:
            atoms |= sel.by_element(document.cell, symbol)
        document.select(atoms, "set")

    def expand_selection(self, how: str) -> None:
        document = self.current_document()
        if document is not None:
            document.expand_selection(how)

    def define_plane(self) -> None:
        """A plane through the selected atoms."""
        document = self.current_document()
        if document is not None:
            self.show_status(document.define_plane())

    def measure_selection(self) -> None:
        """Measure what is selected, in the order it was picked.

        Two atoms are a distance, three an angle about the middle one,
        four a torsion -- the same rule the measuring mode works to,
        taken over atoms that are already selected rather than making
        somebody click them a second time.

        **A selected bond is its own measurement.**  Clicking a bond
        and asking for a distance is the shortest way anybody asks how
        long a bond is, and until this branch existed it was the one
        thing Measure would not answer -- the selection held no atoms,
        so the entry was greyed out over the very thing being asked
        about.  Bonds are read only when no atom is selected, which is
        the state :meth:`Document.select_bond` puts the selection in
        anyway; an atom in hand still means the atoms are the question.
        """
        document = self.current_document()
        if document is None:
            return
        selection = document.selection
        try:
            if selection.bonds and not selection.atoms:
                self.show_status(
                    document.add_bond_measurements(selection.bonds))
            else:
                self.show_status(
                    document.add_measurement(selection.order))
        except ValueError as exc:
            self.show_status(str(exc))

    def measure_plane_angles(self) -> None:
        """The angle between every pair of planes defined so far."""
        document = self.current_document()
        if document is not None:
            self.show_status(document.measure_plane_angles())

    def clear_planes(self) -> None:
        document = self.current_document()
        if document is not None:
            document.clear_planes()

    def clear_measurements(self) -> None:
        document = self.current_document()
        if document is not None:
            document.clear_measurements()

    def delete_bonds(self) -> None:
        document = self.current_document()
        if document is not None and document.selection.bonds:
            self.show_status(document.delete_selected_bonds())

    def delete_selection(self) -> None:
        """Delete whatever is in hand.

        One key for all three: net edges, then bonds, then sites --
        each when it is what is selected and nothing else is.  Clicking
        a bond and pressing delete should delete the bond, and the
        alternative -- a second key, or a mode -- is how the
        application ended up with deletion living inside a tool called
        Add Bond.
        """
        document = self.current_document()
        if document is None:
            return
        if document.selection.topology and not document.selection.atoms:
            self.show_status(document.delete_selected_topology())
            return
        if document.selection.bonds and not document.selection.atoms:
            self.delete_bonds()
            return
        if not document.selection.atoms:
            return
        if not document.selection_is_orbit_complete():
            answer = QMessageBox.question(
                self, "Symmetry",
                f"{document.selection_orbit_report()}.\n\n"
                f"Delete the whole orbit?",
                QMessageBox.Yes | QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        self.statusBar().showMessage(document.delete_selection(), 5000)

    def change_element(self) -> None:
        document = self.current_document()
        if document is None or not document.selection.atoms:
            return
        current = sorted({document.cell.elements[a]
                          for a in document.selection.atoms})[0]
        symbol, ok = QInputDialog.getText(
            self, "Change element", "New element:", text=current)
        if not ok or not symbol.strip():
            return
        from xtal.core import elements as el
        canonical = el.canonical_symbol(symbol)
        if canonical is None:
            QMessageBox.warning(
                self, "Unknown element",
                f"{symbol.strip()!r} is not an element symbol.")
            return
        symbol = canonical
        self.statusBar().showMessage(
            document.set_selection_element(symbol), 5000)
