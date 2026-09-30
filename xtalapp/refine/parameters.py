"""
xtalapp.refine.parameters
=========================
The numbers every fitting step starts from, on show: TOPAS's input
file as a table.

**One table, one set, every step.**  The workbench holds one
:class:`~xtal.powder.parameters.ParameterSet` and shows it through
this one widget, moved into whichever fitting step is in front -- so
switching from Pawley to Rietveld shows the same U V W and background,
which is the check a person makes before trusting a run.  A finished
fit hands its set back and the table shows it with its esds, the rows
it moved marked for a moment.

**The structure's numbers stay the structure's.**  An atom's Biso and
occupancy are shown here, but typing one is an edit of the site, one
undo step on the Document -- :attr:`ParameterTable.siteEdited` is how
the workbench is asked -- never a second copy here that drifts from
it.  A held row (tied, or fixed by symmetry) is shown greyed and never
edited: RietX would refuse it.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from xtal.powder import parameters as ps
from xtal.powder.data import PowderError
from xtalapp.widgets.tone import HINT, set_tone

__all__ = ["ParameterTable"]

HEADERS = ("Parameter", "Value", "± esd", "Refine")
NAME, VALUE, ESD, REFINE = range(4)

#: How long a row a fit moved stays marked.  Long enough to be seen
#: after looking back from the plot, short enough that the next run's
#: marks are not mixed with this one's.
MOVED_SECONDS = 4.0

#: The role a row's name (or a group's title) is kept under.
_ROW = Qt.UserRole
_GROUP = Qt.UserRole + 1


class ParameterTable(QWidget):
    """Name, value, esd and a Refine box for every row of a set; a
    group's box turns the whole group on or off."""

    #: A value or a flag the person set here.
    changed = Signal()
    #: ``{row name: value}`` typed or pasted into rows the structure
    #: owns: the workbench makes them one edit of the Document.
    siteEdited = Signal(dict)
    #: ``(text, warn)``: what Copy, Paste and Reset did, for the
    #: status line.
    said = Signal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parameters: ps.ParameterSet | None = None
        #: what Reset puts back: a callable, since the preset depends
        #: on the radiation and the data as they are when it is pressed
        self.defaults = None
        #: the rows the last fit moved, shown bold for a moment
        self.moved: set[str] = set()
        self._flags_enabled, self._flags_why = True, ""
        self._closed: set[str] = set()
        #: the groups and rows the tree has items for
        self._shown: tuple = ()
        self._unmark = QTimer(self)
        self._unmark.setSingleShot(True)
        self._unmark.setInterval(int(MOVED_SECONDS * 1000))
        self._unmark.timeout.connect(self._clear_moved)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.hint = QLabel("")
        self.hint.setWordWrap(True)
        set_tone(self.hint, HINT)
        layout.addWidget(self.hint)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(len(HEADERS))
        self.tree.setHeaderLabels(HEADERS)
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(NAME, QHeaderView.Stretch)
        for column in (VALUE, ESD, REFINE):
            header.setSectionResizeMode(column,
                                        QHeaderView.ResizeToContents)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.setUniformRowHeights(True)
        # a column of a dozen rows at least: fewer and the table is a
        # slot scrolled through a line at a time
        self.tree.setMinimumHeight(260)
        self.tree.setToolTip(
            "Double-click a value to set it.  An atom's Biso and "
            "occupancy are the structure's, and editing one is an undo "
            "step there.  Grey rows are held by RietX: tied to another, "
            "or fixed by symmetry.")
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.itemDoubleClicked.connect(self._on_double_clicked)
        self.tree.itemExpanded.connect(
            lambda item: self._closed.discard(item.data(NAME, _GROUP)))
        self.tree.itemCollapsed.connect(
            lambda item: self._closed.add(item.data(NAME, _GROUP)))
        layout.addWidget(self.tree, 1)

        buttons = QHBoxLayout()
        self.reset_button = QPushButton("Reset Parameters")
        self.reset_button.setToolTip(
            "The background, scale, line positions, peak shape and "
            "broadening back to where a first run starts -- for when "
            "one has run away.  The atoms and the cell are left alone, "
            "and what is refined is kept.")
        self.reset_button.clicked.connect(self.reset)
        self.copy_button = QPushButton("Copy")
        self.copy_button.setToolTip(
            "Every row as text, one a line -- name value ± esd Refine "
            "-- to keep, or to paste into another workbench")
        self.copy_button.clicked.connect(self.copy)
        self.paste_button = QPushButton("Paste")
        self.paste_button.setToolTip(
            "Rows in the text Copy writes.  A row not named keeps its "
            "value; a line that cannot be read changes nothing.")
        self.paste_button.clicked.connect(lambda: self.paste())
        buttons.addWidget(self.reset_button)
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.paste_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self.set_parameters(None)

    # -- showing a set ---------------------------------------------------

    def set_parameters(self, parameters: ps.ParameterSet | None,
                       moved=(), why: str = "") -> None:
        """Show ``parameters`` -- the set itself, which the table edits
        in place -- with the rows named in ``moved`` marked.  ``None``
        shows ``why`` instead."""
        self.parameters = parameters
        if moved:
            self.moved = set(moved)
            self._unmark.start()
        self.hint.setText(why)
        self.hint.setVisible(parameters is None and bool(why))
        for button in (self.reset_button, self.copy_button,
                       self.paste_button):
            button.setEnabled(parameters is not None)
        self._fill()

    def set_flags_enabled(self, on: bool, why: str = "") -> None:
        """The Refine column live or greyed with ``why``: a RietX plan
        decides for itself what is freed, and a live box beside it
        would claim a say it does not have."""
        if (bool(on), why) == (self._flags_enabled, self._flags_why):
            return
        self._flags_enabled, self._flags_why = bool(on), why
        self._fill()

    def _fill(self) -> None:
        """The tree as the set stands.  Rebuilt only when the rows
        themselves change: an edit arrives from inside the tree's own
        ``itemChanged``, and clearing the tree there deletes the item
        Qt is still in the middle of setting, which crashes."""
        layout = self._layout()
        if layout != self._shown:
            self._rebuild(layout)
        self._sync()

    def _layout(self) -> tuple:
        if self.parameters is None:
            return ()
        return tuple((group, tuple(row.name for row in
                                   self.parameters.in_group(group)))
                     for group in ps.GROUPS
                     if self.parameters.in_group(group))

    def _rebuild(self, layout) -> None:
        tree = self.tree
        tree.blockSignals(True)
        tree.clear()
        for group, names in layout:
            item = QTreeWidgetItem([group, "", "", ""])
            item.setData(NAME, _GROUP, group)
            font = item.font(NAME)
            font.setBold(True)
            item.setFont(NAME, font)
            tree.addTopLevelItem(item)
            for name in names:
                child = QTreeWidgetItem(["", "", "", ""])
                child.setData(NAME, _ROW, name)
                child.setToolTip(NAME, name)
                for column in (VALUE, ESD):
                    child.setTextAlignment(column,
                                           Qt.AlignRight | Qt.AlignVCenter)
                item.addChild(child)
            item.setExpanded(group not in self._closed)
        self._shown = layout
        tree.blockSignals(False)

    def _sync(self) -> None:
        """Every item's text, flags and boxes from the set, in place."""
        if self.parameters is None:
            return
        tree = self.tree
        tree.blockSignals(True)
        for k in range(tree.topLevelItemCount()):
            group = tree.topLevelItem(k)
            rows = []
            for j in range(group.childCount()):
                child = group.child(j)
                row = self.parameters[child.data(NAME, _ROW)]
                self._show_row(child, row)
                rows.append(row)
            self._show_group(group, rows)
        tree.blockSignals(False)

    def _show_group(self, item, rows) -> None:
        free = [row for row in rows if not row.held]
        flags = Qt.ItemIsEnabled
        if self._flags_enabled and free:
            flags |= Qt.ItemIsUserCheckable
        item.setFlags(flags)
        on = sum(row.refine for row in free)
        item.setCheckState(REFINE, Qt.Checked if free and on == len(free)
                           else Qt.Unchecked if not on
                           else Qt.PartiallyChecked)
        item.setToolTip(REFINE, self._flags_why or "Refine every row of "
                        + str(item.data(NAME, _GROUP)).lower())

    def _show_row(self, item, row: ps.Parameter) -> None:
        value, esd = shown(row.value, row.esd)
        item.setText(NAME, row.label)
        item.setText(VALUE, value)
        item.setText(ESD, esd)
        bold = row.name in self.moved
        for column in (NAME, VALUE, ESD):
            font = item.font(column)
            font.setBold(bold)
            item.setFont(column, font)
        if row.held:
            # disabled is grey in every theme, and says "not yours to
            # change" the way the rest of the application does
            item.setFlags(Qt.ItemIsSelectable)
            item.setCheckState(REFINE, Qt.Checked if row.refine
                               else Qt.Unchecked)
            item.setToolTip(VALUE, f"held: {row.held}")
            item.setToolTip(REFINE, f"held: {row.held}")
            return
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if row.value is not None:
            flags |= Qt.ItemIsEditable
        if self._flags_enabled:
            flags |= Qt.ItemIsUserCheckable
        item.setFlags(flags)
        item.setCheckState(REFINE, Qt.Checked if row.refine
                           else Qt.Unchecked)
        item.setToolTip(REFINE, "" if self._flags_enabled
                        else self._flags_why)
        item.setToolTip(VALUE, "The structure's own number: editing it "
                               "is an undo step there"
                        if row.owner == "structure" and row.value
                        is not None else "")

    def _clear_moved(self) -> None:
        if self.moved:
            self.moved = set()
            self._fill()

    # -- editing ---------------------------------------------------------

    def _on_double_clicked(self, item, column: int) -> None:
        if column == VALUE and item.flags() & Qt.ItemIsEditable:
            self.tree.editItem(item, VALUE)

    def _on_item_changed(self, item, column: int) -> None:
        if self.parameters is None:
            return
        group = item.data(NAME, _GROUP)
        if group is not None:
            if column == REFINE:
                on = item.checkState(REFINE) != Qt.Unchecked
                for row in self.parameters.in_group(group):
                    if not row.held:
                        row.refine = on
                self._edited()
            return
        name = item.data(NAME, _ROW)
        if name is None or name not in self.parameters:
            return
        if column == REFINE:
            self.parameters.set_refine(
                name, item.checkState(REFINE) == Qt.Checked)
            self._edited()
        elif column == VALUE:
            self.set_value(name, item.text(VALUE))

    def set_value(self, name: str, text: str) -> bool:
        """``text`` typed as ``name``'s value; ``False`` with the reason
        said, and the old value shown again, when it is not a number."""
        try:
            value = float(str(text).split("±")[0].strip())
        except ValueError:
            self.said.emit(f"{text!r} is not a number", True)
            self._fill()
            return False
        row = self.parameters[name]
        if row.owner == "structure":
            # the Document changes, and the table follows it when it
            # hears so; until then it shows what it had
            self._fill()
            self.siteEdited.emit({name: value})
            return True
        self.parameters.set_value(name, value)
        self._edited()
        return True

    def _edited(self) -> None:
        self._fill()
        self.changed.emit()

    # -- the buttons -----------------------------------------------------

    def reset(self) -> None:
        if self.parameters is None or self.defaults is None:
            return
        try:
            defaults = self.defaults()
        except PowderError as exc:
            self.said.emit(str(exc), True)
            return
        self.parameters.reset(defaults)
        self._edited()
        self.said.emit("the instrument and peak shape are back at "
                       "their starting values", False)

    def copy(self) -> None:
        if self.parameters is None:
            return
        QApplication.clipboard().setText(self.parameters.to_text())
        self.said.emit(f"copied {len(self.parameters)} parameters",
                       False)

    def paste(self, text: str | None = None) -> int:
        """Rows in the text form -- ``text``, or the clipboard's -- into
        the set; how many were read.  All or nothing: a line that
        cannot be read is said, and the set is as it was."""
        if self.parameters is None:
            return 0
        if text is None:
            text = QApplication.clipboard().text()
        trial = self.parameters.copy()
        try:
            count = trial.paste(text)
        except PowderError as exc:
            self.said.emit(f"nothing pasted: {exc}", True)
            return 0
        sites = {row.name: row.value for row in trial
                 if row.owner == "structure" and row.value is not None
                 and row.value != self.parameters[row.name].value}
        # read once more into the set itself, which cannot fail now;
        # the structure's numbers go to the Document instead
        held = {name: self.parameters[name].value for name in sites}
        self.parameters.paste(text)
        for name, value in held.items():
            self.parameters[name].value = value
        self._edited()
        if sites:
            self.siteEdited.emit(sites)
        self.said.emit(f"pasted {count} parameter"
                       f"{'' if count == 1 else 's'}", False)
        return count

    # -- for tests and the workbench -------------------------------------

    def item(self, name: str) -> QTreeWidgetItem | None:
        """The tree item showing row ``name`` (or group ``name``)."""
        for k in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(k)
            if group.data(NAME, _GROUP) == name:
                return group
            for j in range(group.childCount()):
                child = group.child(j)
                if child.data(NAME, _ROW) == name:
                    return child
        return None


def shown(value: float | None, esd: float | None) -> tuple[str, str]:
    """``(value, esd)`` as the table's two columns: the value to the
    esd's precision when there is one, to six figures when there is
    not.  The set keeps every digit; this is only what is read."""
    if value is None:
        return "", ""
    text = ps.format_value(value, esd)
    if " ± " in text:
        number, error = text.split(" ± ")
        return number, error
    return f"{value:.6g}", ""
