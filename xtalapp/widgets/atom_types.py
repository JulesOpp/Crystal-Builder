"""
xtalapp.widgets.atom_types
==========================
The atom types table, wherever an engine that types atoms is set up.

UFF's answer is only as good as its typing, and the typing is a guess
made from coordination and geometry -- so the table shows every site's
type, what the type means, how sure the typer was and the sentence
explaining why, and a double-click overrides it.  It lived inside the
Force Field panel; the relaxed scan runs the same engine over the
same types for hours, and is the place a wrong type costs most, so
the table is here and both use it.

An override is the document's, not the table's
(:meth:`xtalapp.document.Document.set_atom_type`), so one made in
either place is the same edit, on the undo stack, and is what the
other shows next.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
)

from xtal.ff.uff import params

# The type name and the type in words, side by side and never one
# without the other.  ``Zn3+2`` is what Rappe's Table 1 is indexed by,
# what an override is stored as and what anybody cross-checking
# against another program needs; "tetrahedral Zn(II)" is the only one
# of the two that can be checked by reading it.
COLUMNS = ["Site", "Type", "What it means", "Sure?", "Why"]
# Rows sampled when sizing a column to its contents, as in the
# sites dock: every row of a P1 framework is thousands of
# measurements for a width the first few already settle.
RESIZE_SAMPLE_ROWS = 30

#: What the table is headed with, wherever it is.
HEADING = "Atom types (double-click to override)"


def describe(name: str) -> str:
    """The type in words, or nothing if it is not a type we know.

    A UFF4MOF row says so, because ``Cu4+2`` and ``O_3_f`` carry no
    ``f`` in the name and would otherwise read as Rappe's own.
    """
    try:
        description = params.get(name).description
    except KeyError:                                # pragma: no cover
        return ""
    if name in params.UFF4MOF_TYPES:
        description += " (UFF4MOF)"
    return description


def offer(name: str) -> str:
    """One line of the override dialog: the name, then the meaning.

    Offered ``Fe3+2`` and ``Fe6+2``, the user is being asked to choose
    between two strings; offered "tetrahedral Fe(II)" and "octahedral
    Fe(II)" they are being asked a question about their crystal, which
    they can answer.
    """
    description = describe(name)
    return f"{name}  --  {description}" if description else name


def warnings_text(rows) -> str:
    """What to say under the table about the types nobody is sure of.

    A wrong type gives a plausible number rather than an obvious
    error, so the ones the typer guessed at are named.
    """
    unsure = [r for r in rows
              if r[1].confidence == "uncertain" and not r[1].overridden]
    if not unsure:
        return ""
    names = ", ".join(r[1].name for r in unsure[:4])
    more = "" if len(unsure) <= 4 else f" and {len(unsure) - 4} more"
    return (f"{len(unsure)} site(s) have a type the typer is not "
            f"sure of ({names}{more}). Check them before trusting "
            f"the energy -- a wrong type gives a plausible number, "
            f"not an obvious error.")


class AtomTypeTable(QTableWidget):
    """One row per site: its type, what that means, and why."""

    statusMessage = Signal(str)

    def __init__(self, parent=None):
        super().__init__(0, len(COLUMNS), parent)
        self.document = None
        self.setHorizontalHeaderLabels(COLUMNS)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COLUMNS.index("Why"),
                                    QHeaderView.Stretch)
        header.setResizeContentsPrecision(RESIZE_SAMPLE_ROWS)
        self.cellDoubleClicked.connect(self.override_type)

    def fill(self, document, parameter_set=None) -> list:
        """Type ``document``'s sites and show them; the rows back.

        Raises whatever typing raises, with the table emptied, so the
        caller decides where the message goes.
        """
        self.document = document
        if document is None or document.structure.n_sites == 0:
            self.setRowCount(0)
            return []
        try:
            rows = document.site_types(parameter_set)
        except Exception:
            self.setRowCount(0)
            raise

        self.setRowCount(len(rows))
        structure = document.structure
        # Every setItem emits dataChanged, and the view answers each
        # one by asking the header where the row is -- which re-sizes
        # the sized-to-contents columns, which measures and shapes the
        # text of every sampled row again.  Two thousand cells on a P1
        # framework is twenty seconds of font shaping, and because Qt
        # replays those signals from the event loop it is spent
        # *after* the optimisation has finished: the run is instant
        # and then the window stops answering.  Fill the table
        # silently and tell the view once, at the end.
        model = self.model()
        model.blockSignals(True)
        try:
            for row, (index, atom, multiplicity) in enumerate(rows):
                site = structure.sites[index]
                name = site.label or f"{site.element}{index}"
                if multiplicity > 1:
                    name += f"  (x{multiplicity})"
                sure = "set" if atom.overridden else atom.confidence
                for column, text in enumerate(
                        (name, atom.name, describe(atom.name), sure,
                         atom.reason)):
                    item = QTableWidgetItem(text)
                    item.setData(Qt.UserRole, index)
                    # The reason is a sentence and the column is
                    # rarely wide enough for it.
                    item.setToolTip(atom.reason)
                    if column == 3 and sure == "uncertain":
                        item.setForeground(Qt.red)
                    if atom.overridden:
                        font = item.font()
                        font.setItalic(True)
                        item.setFont(font)
                    self.setItem(row, column, item)
        finally:
            model.blockSignals(False)
            model.layoutChanged.emit()
        return rows

    def override_type(self, row: int, _column: int = 0) -> None:
        """Offer the types UFF has for that element, and nothing else.

        Restricting the list to the element's own types is what makes
        the override safe: there is no way to ask for a carbon
        parameter on an oxygen, which would not be a bold modelling
        choice but a silent nonsense.
        """
        if self.document is None or not self.isEnabled():
            return
        item = self.item(row, 0)
        if item is None:                            # pragma: no cover
            return
        index = int(item.data(Qt.UserRole))
        site = self.document.structure.sites[index]
        choices = params.types_for(site.element)
        if not choices:                             # pragma: no cover
            return
        current = self.item(row, COLUMNS.index("Type")).text()
        options = ["(let the force field decide)",
                   *(offer(c) for c in choices)]
        from PySide6.QtWidgets import QInputDialog

        start = (choices.index(current) + 1 if current in choices
                 else 0)
        chosen, ok = QInputDialog.getItem(
            self, "Atom type",
            f"UFF type for {site.label or site.element} "
            f"(and its whole symmetry orbit):",
            options, start, False)
        if not ok:
            return
        name = (None if chosen == options[0]
                else chosen.split("  --  ")[0])
        self.statusMessage.emit(
            self.document.set_atom_type([index], name))

    def fit_rows(self, most: int = 8) -> None:
        """As tall as its rows, up to ``most`` of them, then scroll.

        For a dialog, where the table shares a scrolling column with
        everything else and a stretch factor means nothing.
        """
        shown = max(1, min(self.rowCount(), most))
        height = (self.horizontalHeader().sizeHint().height()
                  + shown * self.verticalHeader().defaultSectionSize()
                  + 2 * self.frameWidth())
        self.setFixedHeight(height)
