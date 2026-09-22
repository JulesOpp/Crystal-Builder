"""
xtalapp.dialogs.spacegroup
==========================
Picking a space group -- and saying what picking it means.

Two things make this more than a list of 230 names:

**Settings.**  The list is every *setting*, not every group: P21/c and
P21/n are the same group down different axes, and Fd-3m has two origin
choices whose atoms are a quarter of a cell apart.  Choosing by number
alone is how structures end up silently wrong, so the Hall symbol is
shown next to every entry and travels with the choice.

**Two ways to mean it.**  Adopting a group can mean "these sites are an
asymmetric unit, generate the rest" or "these sites are the whole cell,
find the asymmetric unit in it".  The atom count goes up under the
first and down under the second, so the dialog shows the count it would
produce before anything happens.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QRadioButton,
    QVBoxLayout,
)

from xtal.commands import symmetry as symmetry_commands
from xtal.core import spacegroup as sg
from xtalapp.widgets.tone import WARNING_BOX, set_tone

MODES = [
    ("reinterpret", "Generate: the sites are the asymmetric unit",
     "The group generates the rest of the cell. This is what you want "
     "when you have built or typed in an asymmetric unit."),
    ("impose", "Impose: the sites are already the whole cell",
     "An asymmetric unit is found inside the existing atoms. Atoms "
     "the group cannot explain are reported, not dropped."),
]


class SpaceGroupDialog(QDialog):
    """Choose a space group and how to apply it."""

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set space group")
        self.document = document
        self.resize(520, 520)

        self.search = QLineEdit()
        self.search.setPlaceholderText(
            "number, H-M symbol, Hall symbol or crystal system")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)

        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._preview)

        self.modes = []
        mode_box = QVBoxLayout()
        for index, (_name, label, tip) in enumerate(MODES):
            button = QRadioButton(label)
            button.setToolTip(tip)
            button.setChecked(index == 0)
            button.toggled.connect(self._preview)
            self.modes.append(button)
            mode_box.addWidget(button)

        self.preview = QLabel()
        self.preview.setWordWrap(True)
        self.preview.setStyleSheet("padding: 4px;")

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                        | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        header = QHBoxLayout()
        header.addWidget(QLabel("Search"))
        header.addWidget(self.search, 1)

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(self.list, 1)
        layout.addLayout(mode_box)
        layout.addWidget(self.preview)
        layout.addWidget(self.buttons)

        self._fill(sg.table())
        self.select(document.structure.space_group)

    # -- the list ------------------------------------------------------

    def _fill(self, groups) -> None:
        self.list.clear()
        for group in groups:
            item = QListWidgetItem(
                f"{group.number:>3}   {group.hm:<16}  {group.hall}")
            item.setData(Qt.UserRole, group.hall)
            item.setToolTip(f"{group.crystal_system}, "
                            f"{group.order} operations, "
                            f"centring {group.centring}")
            self.list.addItem(item)

    def _filter(self, text: str) -> None:
        self._fill(sg.search(text))
        if self.list.count():
            self.list.setCurrentRow(0)
        else:
            self._preview()

    def select(self, group) -> None:
        """Highlight a group, scrolling it into view."""
        hall = sg.SpaceGroup.from_any(group).hall
        for row in range(self.list.count()):
            if self.list.item(row).data(Qt.UserRole) == hall:
                self.list.setCurrentRow(row)
                self.list.scrollToItem(self.list.item(row))
                return

    # -- values --------------------------------------------------------

    def group(self):
        item = self.list.currentItem()
        if item is None:
            return None
        return sg.SpaceGroup.from_hall(item.data(Qt.UserRole))

    def mode(self) -> str:
        for button, (name, _label, _tip) in zip(self.modes, MODES,
                                                strict=True):
            if button.isChecked():
                return name
        return "reinterpret"

    # -- preview -------------------------------------------------------

    def _preview(self, *_args) -> None:
        group = self.group()
        ok_button = self.buttons.button(QDialogButtonBox.Ok)
        if group is None:
            self.preview.setText("Nothing selected.")
            ok_button.setEnabled(False)
            return
        ok_button.setEnabled(True)
        command = symmetry_commands.SetSpaceGroup(group, self.mode())
        try:
            _new, report = command.preview(self.document.structure)
        except (ValueError, RuntimeError) as exc:
            self.preview.setText(str(exc))
            return
        lines = [report.message] + list(report.warnings)
        self.preview.setText("\n".join(lines))
        set_tone(self.preview,
                 WARNING_BOX if report.warnings or not report.ok
                 else None, padding=4)

    # -- running -------------------------------------------------------

    @classmethod
    def ask(cls, document, parent=None):
        """Show the dialog and apply the choice; returns the report, or
        None if it was cancelled."""
        dialog = cls(document, parent)
        if dialog.exec() != QDialog.Accepted:
            return None
        group = dialog.group()
        if group is None:
            return None
        return document.set_space_group(group, dialog.mode())
