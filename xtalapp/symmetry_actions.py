"""
xtalapp.symmetry_actions
========================
The Symmetry and Cell commands of the window, moved out of
:mod:`xtalapp.mainwindow` unchanged.
"""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from xtalapp.dialogs.add_hydrogens import AddHydrogensDialog
from xtalapp.dialogs.cell_edit import CellEditDialog
from xtalapp.dialogs.fill_pores import FillPoresDialog
from xtalapp.dialogs.find_symmetry import FindSymmetryDialog
from xtalapp.dialogs.interpenetrate import InterpenetrateDialog
from xtalapp.dialogs.merge_duplicates import MergeDuplicatesDialog
from xtalapp.dialogs.spacegroup import SpaceGroupDialog
from xtalapp.dialogs.subgroup import SubgroupDialog
from xtalapp.dialogs.supercell import SupercellDialog


class SymmetryActions:
    """Reduce to P1, find and set the group, descend, and every edit
    of the cell -- with ``_run``, ``_report`` and ``_announce``, the
    prologue they share and nothing else calls.

    A mixin of :class:`~xtalapp.mainwindow.MainWindow`: the methods
    read the window's own attributes through ``self``, which is what
    let them move without a line of their bodies changing.

    The dialogs preview their own result, so everything reached from
    here either opens one or is unambiguous enough not to need it.
    """

    def reduce_to_p1(self) -> None:
        document = self.current_document()
        if document is not None:
            self.statusBar().showMessage(document.reduce_to_p1(), 5000)

    def find_symmetry(self) -> None:
        """Detect and adopt, then reframe a cell that was re-expressed.

        The camera belongs to the viewport and not to the dialog, so
        the reset is here -- the same split *Descend to a subgroup*
        keeps.  What the dialog has to say is *which* thing happened:
        *Adopt* and *Label Wyckoff only* both come back Accepted and
        only one of them re-expresses the cell, and a camera that
        framed the old setting frames the new one badly or not at all.
        """
        document = self.current_document()
        if document is None:
            return
        dialog = FindSymmetryDialog(document, self)
        dialog.exec()
        self._announce(document)
        if dialog.re_expressed:
            self.reset_view()

    def set_space_group(self) -> None:
        document = self.current_document()
        if document is not None:
            self._report(SpaceGroupDialog.ask(document, self))

    def standardize_cell(self, to_primitive: bool = False) -> None:
        self._run(lambda d: d.standardize_cell(
            to_primitive=to_primitive))

    def assign_wyckoff(self) -> None:
        self._run(lambda d: d.assign_wyckoff())

    def merge_duplicates(self) -> None:
        """Ask for the tolerance first.

        The count it would merge is flat over a wide range and then
        steps, and where it steps is a property of the file -- so the
        0.05 A default was as likely to be an order of magnitude too
        tight as it was to be right."""
        document = self.current_document()
        if document is not None:
            self._report(MergeDuplicatesDialog.ask(document, self))

    def descend_to_subgroup(self) -> None:
        """Descend, then reset the view.

        A descent can halve the cell or take three quarters of it, and
        can swap which axis is which -- so the camera that framed the
        old cell frames the new one badly or not at all.  Resetting is
        what every other operation that rebuilds the cell would want
        too; this is the one where it is never wrong, because the
        crystal has not moved and only the box around it has.
        """
        document = self.current_document()
        if document is None:
            return
        report = SubgroupDialog.ask(document, self)
        self._report(report)
        if report is not None and report.ok:
            self.reset_view()

    def invert_structure(self) -> None:
        """Swap the structure's hand, after saying what that means.

        Worth a confirmation and not worth a dialog of its own: the
        three answers a user needs -- nothing will change, the symbol
        will change, or the structure will change but the symbol will
        not -- are one sentence, and the command has already worked out
        which one it is.
        """
        document = self.current_document()
        if document is None:
            return
        report = document.preview_inversion()
        group = document.structure.space_group
        if group.is_centrosymmetric:
            QMessageBox.information(
                self, "Invert the structure",
                f"{group.short_name} is centrosymmetric, so inversion "
                f"is already one of its operations and the structure "
                f"you would get is the one you already have.")
            return
        answer = QMessageBox.question(
            self, "Invert the structure",
            f"{report.message}.\n\nThe cell is unchanged; the "
            f"coordinates and the space group both move. Continue?",
            QMessageBox.Yes | QMessageBox.No)
        if answer == QMessageBox.Yes:
            self._run(lambda d: d.invert_structure())

    def add_hydrogens_dialog(self) -> None:
        document = self.current_document()
        if document is None:
            return
        message = AddHydrogensDialog.ask(document, self)
        if message:
            self.statusBar().showMessage(message, 8000)

    def fill_pores_dialog(self) -> None:
        document = self.current_document()
        if document is None:
            return
        sources = [(other.title, other.structure)
                   for other in self.documents]
        message = FillPoresDialog.ask(
            document, sources, self,
            directory=self.settings.last_directory)
        if message:
            self.statusBar().showMessage(message, 8000)

    def interpenetrate_dialog(self) -> None:
        document = self.current_document()
        if document is not None:
            self._report(InterpenetrateDialog.ask(document, self))

    def supercell_dialog(self) -> None:
        document = self.current_document()
        if document is not None:
            self._report(SupercellDialog.ask(document, self))

    def edit_cell(self) -> None:
        document = self.current_document()
        if document is not None:
            message = CellEditDialog.ask(document, self)
            if message:
                self.statusBar().showMessage(message, 6000)

    def reduce_cell(self, kind: str = "niggli") -> None:
        self._run(lambda d: d.reduce_cell(kind))

    def wrap_into_cell(self) -> None:
        self._run(lambda d: d.wrap_into_cell())

    def _run(self, operation) -> None:
        """Run a symmetry or cell operation on the current document and
        say what happened -- including when it declined to happen."""
        document = self.current_document()
        if document is None:
            return
        try:
            self._report(operation(document))
        except ValueError as exc:
            QMessageBox.warning(self, "The operation failed", str(exc))

    def _report(self, report) -> None:
        if report is None:
            return
        self.statusBar().showMessage(report.message, 8000)
        if report.warnings or not report.ok:
            QMessageBox.warning(
                self, "Symmetry",
                "\n\n".join([report.message] + list(report.warnings)))

    def _announce(self, document) -> None:
        self.statusBar().showMessage(document.status_text(), 5000)
