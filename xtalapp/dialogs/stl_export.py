"""
xtalapp.dialogs.stl_export
==========================
Where the STL goes, and how the model is built -- in one color or two
(:class:`PrintExportDialog`); and, the same form, where Render in
Blender's picture goes.

The generated form with two things it cannot do: Browse asks where to
*save*, and the path starts filled in -- the structure's own name, in
the folder the last export went to -- because a run that fails a
minute into Blender for want of a destination is a worse way to learn
there was a field than seeing it filled.  Run stays off while the
field is empty for the same reason.

What the form holds is still ``values()``, so the run is exactly the
one the CLI and the Modules tree make.  See
:mod:`xtal.modules.print3d` and :mod:`xtal.modules.blender`.
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
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from xtal.core import elements as el
from xtal.core import p1
from xtal.modules.print3d import ColorError, parse_colors, with_suffix
from xtalapp.dialogs.answered import answered
from xtalapp.dialogs.module_form import ModuleDialog
from xtalapp.widgets.tone import WARNING, set_tone


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


class PrintExportDialog(StlExportDialog):
    """File > Export as STL: one color through Blender, or, with
    *Two-color printing* ticked, two bodies in a 3MF.

    One form because the two exports are one question -- what to
    print -- and share every setting but three: *Remesh* means
    something to Blender alone, and the bond choice and the color
    tables only to two colors, so each is shown only when it applies.
    Ticking the box swaps the path's suffix, ``.stl`` and ``.3mf``.
    Without Blender the form still opens, says so, and keeps Run off
    until the box is ticked: the two-color export needs no Blender,
    and a menu entry that refused to open would have hidden it.

    The run takes the colors as text -- ``element_colors`` (``Zn=2``)
    and ``atom_colors`` (P1 atoms, ``17=2``) -- so the CLI and an agent
    can say them; here they are a row per element present and a row per
    atom group, and :meth:`values` writes the text.  An atom group's
    choice overrides its atoms' element, and of two groups the later
    wins, as it does for a group's drawn color.

    With nothing remembered, metals start in color 2: a framework's
    nodes and linkers in two colors is the print most people want
    first, and every row is one click to change.
    """

    TITLE = "Export as STL"
    FILTERS = {False: "STL meshes (*.stl)", True: "3MF models (*.3mf)"}

    #: A group row's choices, in order: what ``values`` reads off.
    GROUP_CHOICES = ("As its elements", "Color 1", "Color 2")
    #: Rows that mean something with one color only, or two only.
    ONE_COLOR = ("remesh",)
    TWO_COLOR = ("bonds",)

    def __init__(self, module, action, parent=None, initial=None):
        from xtal.modules import blender

        self.blender = blender.available()
        super().__init__(module, action, parent, initial)
        self.two_color = self.form.widgets["two_color"]
        for name in ("element_colors", "atom_colors"):
            self._show_row(name, False)

        document = None
        if parent is not None and hasattr(parent, "current_document"):
            document = parent.current_document()
        structure = getattr(document, "structure", None)
        present = []
        if structure is not None:
            seen = dict.fromkeys(p1.expand(structure).elements)
            present = [e for e in seen if not el.is_dummy(e)]
        try:
            remembered = parse_colors(
                (initial or {}).get("element_colors", ""))
        except ColorError:
            remembered = {}
        self.groups = [g for g in getattr(document, "atom_groups", [])
                       if not g.empty]

        self.colors = QGroupBox("Colors")
        column = QVBoxLayout(self.colors)
        first_time = not remembered

        def color(symbol):
            metal = el.element(symbol).is_metal
            default = 2 if first_time and metal else 1
            return remembered.get(symbol, default) - 1

        self.elements = self._table(
            ("Element", "Color"),
            [(symbol, ("Color 1", "Color 2"), color(symbol))
             for symbol in present])
        column.addWidget(self.elements)
        if self.groups:
            self.group_table = self._table(
                ("Atom group", "Color"),
                [(g.name, self.GROUP_CHOICES, 0) for g in self.groups])
            column.addWidget(self.group_table)
        else:
            self.group_table = None
        self.no_blender = QLabel(
            f"{self.blender.reason}.  Tick Two-color printing, which "
            f"needs no Blender, or install it and set it in "
            f"Preferences > Engines.")
        self.no_blender.setWordWrap(True)
        set_tone(self.no_blender, WARNING)
        layout = self.layout()
        at = layout.indexOf(self.form) + 1
        layout.insertWidget(at, self.colors)
        layout.insertWidget(at + 1, self.no_blender)
        self.two_color.toggled.connect(self._switch)
        self._switch(self.two_color.isChecked())

    def _show_row(self, name: str, visible: bool) -> None:
        widget = self.form.widgets[name]
        widget.setVisible(visible)
        label = self.form.layout().labelForField(widget)
        if label is not None:
            label.setVisible(visible)

    def _switch(self, two: bool) -> None:
        """Show what applies to one color or to two, and give the path
        the suffix of what will be made."""
        for name in self.ONE_COLOR:
            self._show_row(name, not two)
        for name in self.TWO_COLOR:
            self._show_row(name, two)
        self.colors.setVisible(two)
        self.output.filter = self.FILTERS[two]
        text = self.output.text().strip()
        if text:
            self.output.setText(str(with_suffix(text, two)))
        self._refresh()
        self.adjustSize()

    def _refresh(self) -> None:
        if not hasattr(self, "no_blender"):
            return super()._refresh()
        two = self.two_color.isChecked()
        missing = not two and not self.blender
        self.no_blender.setVisible(missing)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(
            bool(self.output.text().strip()) and not missing)

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

    def color_of(self, table, row: int) -> int:
        return table.cellWidget(row, 1).currentIndex()

    def values(self) -> dict:
        values = super().values()
        values["element_colors"] = " ".join(
            f"{self.elements.item(row, 0).text()}="
            f"{self.color_of(self.elements, row) + 1}"
            for row in range(self.elements.rowCount()))
        atoms: dict[int, int] = {}
        for row, group in enumerate(self.groups):
            choice = self.color_of(self.group_table, row)
            if choice:
                atoms.update(dict.fromkeys(sorted(group.atoms), choice))
        values["atom_colors"] = " ".join(
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
