"""
xtalapp.dialogs.stl_export
==========================
Where the STL goes, and how the model is built; and, the same form,
where Render in Blender's picture goes.

The generated form with two things it cannot do: Browse asks where to
*save*, and the path starts filled in -- the structure's own name, in
the folder the last export went to -- because a run that fails a
minute into Blender for want of a destination is a worse way to learn
there was a field than seeing it filled.  Run stays off while the
field is empty for the same reason.

What the form holds is still ``values()``, so the run is exactly the
one the CLI and the Modules tree make.  See
:mod:`xtal.modules.blender`.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from xtal.core import elements as el
from xtal.core import p1
from xtal.modules.print3d import ColourError, parse_colours
from xtalapp.dialogs.answered import answered
from xtalapp.dialogs.module_form import ModuleDialog


class StlExportDialog(ModuleDialog):

    TITLE = "Export as STL"
    FILTER = "STL meshes (*.stl)"
    SUFFIX = ".stl"

    def __init__(self, module, action, parent=None, initial=None):
        super().__init__(module, action, parent, initial)
        self.setWindowTitle(self.TITLE)
        self.output = self.form.widgets["output"]
        self.output.save = True
        self.output.filter = self.FILTER
        if not self.output.text().strip():
            self.output.setText(str(suggested_path(parent, self.SUFFIX)))
        self.form.changed.connect(self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(
            bool(self.output.text().strip()))

    @classmethod
    def ask(cls, module, action, parent=None, initial=None):
        with answered(cls(module, action, parent, initial)) as dialog:
            if dialog.exec() != QDialog.Accepted:
                return None
            return dialog.values()


class RenderDialog(StlExportDialog):

    TITLE = "Render in Blender"
    FILTER = "PNG images (*.png)"
    SUFFIX = ".png"


class TwoColourExportDialog(StlExportDialog):
    """Export for Two-Colour Printing: the generated form, with the two
    colour fields replaced by tables a person can read.

    The run takes text -- ``element_colours`` (``Zn=2``) and
    ``atom_colours`` (P1 atoms, ``17=2``) -- so the CLI and an agent can
    say it; here it is a row per element present and a row per atom
    group, and :meth:`values` writes the text.  An atom group's choice
    overrides its atoms' element, and of two groups the later wins, as
    it does for a group's drawn colour.

    With nothing remembered, metals start in colour 2: a framework's
    nodes and linkers in two colours is the print most people want
    first, and every row is one click to change.
    """

    TITLE = "Export for Two-Colour Printing"
    FILTER = "3MF models (*.3mf)"
    SUFFIX = ".3mf"

    #: A group row's choices, in order: what ``values`` reads off.
    GROUP_CHOICES = ("As its elements", "Colour 1", "Colour 2")

    def __init__(self, module, action, parent=None, initial=None):
        super().__init__(module, action, parent, initial)
        for name in ("element_colours", "atom_colours"):
            widget = self.form.widgets[name]
            label = self.form.layout().labelForField(widget)
            widget.hide()
            if label is not None:
                label.hide()

        document = None
        if parent is not None and hasattr(parent, "current_document"):
            document = parent.current_document()
        structure = getattr(document, "structure", None)
        present = []
        if structure is not None:
            seen = dict.fromkeys(p1.expand(structure).elements)
            present = [e for e in seen if not el.is_dummy(e)]
        try:
            remembered = parse_colours(
                (initial or {}).get("element_colours", ""))
        except ColourError:
            remembered = {}
        self.groups = [g for g in getattr(document, "atom_groups", [])
                       if not g.empty]

        box = QGroupBox("Colours")
        column = QVBoxLayout(box)
        first_time = not remembered

        def colour(symbol):
            metal = el.element(symbol).is_metal
            default = 2 if first_time and metal else 1
            return remembered.get(symbol, default) - 1

        self.elements = self._table(
            ("Element", "Colour"),
            [(symbol, ("Colour 1", "Colour 2"), colour(symbol))
             for symbol in present])
        column.addWidget(self.elements)
        if self.groups:
            self.group_table = self._table(
                ("Atom group", "Colour"),
                [(g.name, self.GROUP_CHOICES, 0) for g in self.groups])
            column.addWidget(self.group_table)
        else:
            self.group_table = None
        layout = self.layout()
        layout.insertWidget(layout.indexOf(self.form) + 1, box)

    def _table(self, headers, rows):
        table = QTableWidget(len(rows), 2, self)
        table.setHorizontalHeaderLabels(list(headers))
        table.verticalHeader().hide()
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        for row, (name, choices, chosen) in enumerate(rows):
            table.setItem(row, 0, QTableWidgetItem(name))
            box = QComboBox(table)
            box.addItems(list(choices))
            box.setCurrentIndex(chosen)
            table.setCellWidget(row, 1, box)
        height = table.horizontalHeader().height() + sum(
            table.rowHeight(r) for r in range(len(rows))) + 4
        table.setMaximumHeight(min(height, 220))
        return table

    def colour_of(self, table, row: int) -> int:
        return table.cellWidget(row, 1).currentIndex()

    def values(self) -> dict:
        values = super().values()
        values["element_colours"] = " ".join(
            f"{self.elements.item(row, 0).text()}="
            f"{self.colour_of(self.elements, row) + 1}"
            for row in range(self.elements.rowCount()))
        atoms: dict[int, int] = {}
        for row, group in enumerate(self.groups):
            choice = self.colour_of(self.group_table, row)
            if choice:
                atoms.update(dict.fromkeys(sorted(group.atoms), choice))
        values["atom_colours"] = " ".join(
            f"{k}={c}" for k, c in sorted(atoms.items()))
        return values


def suggested_path(window, suffix: str = ".stl") -> Path | str:
    """``<last directory>/<structure name><suffix>``, or nothing to go
    on.

    Read defensively off whatever the dialog was parented to: the
    Modules tree and the File menu both pass the window, a test may
    pass nothing.
    """
    document = None
    if window is not None and hasattr(window, "current_document"):
        document = window.current_document()
    if document is None:
        return ""
    stem = Path(document.title.rstrip("*")).stem or "structure"
    settings = getattr(window, "settings", None)
    folder = Path(getattr(settings, "last_directory", "") or Path.home())
    return folder / f"{stem}{suffix}"
