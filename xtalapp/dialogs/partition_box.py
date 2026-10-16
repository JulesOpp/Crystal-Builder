"""
xtalapp.dialogs.partition_box
=============================
The MOF builder's *Partition pores* section.

Live only for an open M3O trimer on ``acs``, because that is the only
framework a pyridyl partitioner has sites to take in.  The arithmetic
is :mod:`xtal.mof.partition` and nothing here repeats it: each
partitioner is listed with the cell it would make, a refused one
stays in the list greyed with its reason as the tooltip -- a choice
that disappears says nothing about why -- and the linkers the chosen
partitioner asks for are offered the other way round.

Greyed rather than hidden, as the stacking rows are: a section that
comes and goes as the net list is scrolled moves the Build button
under the cursor.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from xtal.mof import linkers, partition
from xtal.mof.trimer import TrimerError
from xtalapp.widgets.tone import HINT, WARNING, set_tone

#: How many linkers *Suggest linkers* lists.
SUGGESTIONS = 5


class PartitionBox(QWidget):
    """A partitioner for the trimer and linker chosen above it."""

    #: The person asked for a suggested linker to be used.
    use_linker = Signal(str)                         # noqa: N815
    #: The person picked a compatible node from the note.
    use_node = Signal(str)                           # noqa: N815

    def __init__(self, parent=None):
        super().__init__(parent)
        self.choice = QComboBox(self)
        self.choice.setToolTip(
            "A C3 pyridyl on every channel axis, bonded to the "
            "trimers' open metal sites.  It sets the cell's a and the "
            "linker its c; one that cannot close the cell is listed "
            "greyed, with the reason.")
        self.choice.currentIndexChanged.connect(self._say)
        self.nodes = QLabel(self)
        self.nodes.setWordWrap(True)
        self.nodes.setTextFormat(Qt.RichText)
        self.nodes.linkActivated.connect(self.use_node)
        set_tone(self.nodes, HINT)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        set_tone(self.status, HINT)

        self.suggest = QPushButton("Suggest linkers", self)
        self.suggest.setToolTip(
            "The linkers this partitioner asks for, from every "
            "two-connected block in the catalogue: the span that puts "
            "the linker at the elevation the pacs frameworks show")
        self.suggest.clicked.connect(self._suggest)
        self.suggestions = QLabel(self)
        self.suggestions.setWordWrap(True)
        self.suggestions.setTextFormat(Qt.RichText)
        self.suggestions.linkActivated.connect(self.use_linker)
        set_tone(self.suggestions, HINT)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.choice, 1)
        row.addWidget(self.suggest)
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.addRow("Partitioner", row)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(form)
        layout.addWidget(self.nodes)
        layout.addWidget(self.status)
        layout.addWidget(self.suggestions)

        self._catalog = None
        self._compatible = None
        self._node = None
        self._linker = ""
        self._fits: dict[str, partition.Fit] = {}
        self._fill([])
        self.set_framework(None, "", "", "")

    # -- what it is told -----------------------------------------------

    def set_framework(self, catalog, topology: str, node: str,
                      linker: str) -> None:
        """The net, trimer and linker chosen above, as names."""
        if catalog is not self._catalog:
            self._compatible = None
        self._catalog = catalog
        self._node = None
        self._linker = linker
        self._say_nodes(node)
        reason = ""
        if topology != "acs":
            reason = ("Pore-space partition is of an acs framework "
                      "(MIL-88): pick acs and an M3O trimer.")
        elif not node:
            reason = "Pick an M3O trimer for the node."
        else:
            try:
                self._node = partition.node_geometry(
                    catalog.building_block(node))
            except (TrimerError, KeyError, ValueError) as exc:
                reason = f"{node} cannot be partitioned: {exc}"
        live = self._node is not None
        for widget in (self.choice, self.suggest):
            widget.setEnabled(live)
        self.suggestions.clear()
        if not live:
            self._fill([])
            self.status.setText(reason)
            set_tone(self.status, HINT)
            return
        fits = []
        if linker:
            span = partition.linker_span(catalog.building_block(linker))
            fits = partition.rank(self._node, linker, span)
        self._fill(fits)

    def _say_nodes(self, chosen: str) -> None:
        """The note of nodes a pacs build takes, each a link that puts
        it in the node row.  Worked out once per catalogue -- 14 ms
        over every six-connected block."""
        if self._catalog is None:
            self.nodes.clear()
            return
        if self._compatible is None:
            self._compatible = partition.compatible_nodes(self._catalog)
        if not self._compatible:
            self.nodes.setText("No node in the catalogue can be "
                               "partitioned: none is an M3O trimer "
                               "with open metal sites.")
            return
        items = ", ".join(
            (f"<b>{n.name}</b>" if n.name == chosen
             else f"<a href='{n.name}'>{n.name}</a>") + f" ({n.metal})"
            for n in self._compatible)
        self.nodes.setText(
            f"Nodes that can be partitioned: {items} -- M3O trimers "
            f"whose metals each have an open octahedral site.  A "
            f"trimer carrying terminal waters (N9, N354) or with "
            f"tetrahedral zinc is not one.")

    # -- what it hands back --------------------------------------------

    def value(self) -> str:
        """``""``, ``"auto"`` or a partitioner's name."""
        if not self.choice.isEnabled():
            return ""
        return str(self.choice.currentData() or "")

    def set_value(self, name: str) -> bool:
        at = self.choice.findData(str(name or ""))
        if at >= 0 and self._enabled(at):
            self.choice.setCurrentIndex(at)
            return True
        return False

    # -- inside ----------------------------------------------------------

    def _fill(self, fits) -> None:
        kept = self.choice.currentData()
        self._fits = {f.partitioner: f for f in fits}
        self.choice.blockSignals(True)
        self.choice.clear()
        self.choice.addItem("None", "")
        self.choice.addItem("Best fit", partition.AUTO)
        model = self.choice.model()
        for fit in fits:
            p = partition.partitioner(fit.partitioner)
            self.choice.addItem(f"{p.name} -- {p.full_name}", p.name)
            at = self.choice.count() - 1
            self.choice.setItemData(at, fit.sentence(), Qt.ToolTipRole)
            if not fit.ok and isinstance(model, QStandardItemModel):
                model.item(at).setEnabled(False)
        if fits and not any(f.ok for f in fits):
            model.item(1).setEnabled(False)
        at = self.choice.findData(kept)
        self.choice.setCurrentIndex(at if at >= 0 and self._enabled(at)
                                    else 0)
        self.choice.blockSignals(False)
        self._say()

    def _enabled(self, at: int) -> bool:
        model = self.choice.model()
        if not isinstance(model, QStandardItemModel):
            return True
        return model.item(at).isEnabled()

    def _chosen_fit(self):
        value = self.value()
        if value == partition.AUTO:
            # The fits arrive in the ranker's order, so the first that
            # can be built is the one ``auto`` builds.
            return next((f for f in self._fits.values() if f.ok), None)
        return self._fits.get(value)

    def _say(self, *_args) -> None:
        if self._node is None:
            return
        if not self._linker:
            self.status.setText("Pick a linker to see the cell each "
                                "partitioner makes.")
            set_tone(self.status, HINT)
            return
        refused = [f for f in self._fits.values() if not f.ok]
        fit = self._chosen_fit()
        lines = []
        if fit is not None:
            lines.append(f"Predicted: {fit.sentence()}.")
        elif not self.value():
            lines.append("Built as acs, with the open sites left as "
                         "they are.")
        if refused:
            lines.append("Cannot close the cell: " + "; ".join(
                f.sentence() for f in refused) + ".")
        self.status.setText("  ".join(lines))
        set_tone(self.status, WARNING if refused and fit is None
                 and self.value() else HINT)

    def _suggest(self) -> None:
        """What the chosen partitioner asks of a linker, and what the
        linker chosen asks of a partitioner -- the two reverses -- with
        the nearest molecules for each, catalogue and generated."""
        fit = self._chosen_fit() if self.value() else None
        name = fit.partitioner if fit else "tpt"
        need = partition.linker_requirement(self._node,
                                            partition.partitioner(name))
        found = linkers.suggest(need, self._catalog, n=SUGGESTIONS)
        lines = []
        if found:
            items = ", ".join(
                f"<a href='{s.candidate.name}'>{s.candidate.name}</a>"
                f"{'*' if s.candidate.source == 'series' else ''} "
                f"({s.miss:+.2f})" for s in found)
            generated = any(s.candidate.source == "series"
                            for s in found)
            lines.append(f"{name} asks for {need.sentence()}.  "
                         f"Closest: {items} -- click one to use it"
                         f"{'; * is generated' if generated else ''}.")
        else:
            lines.append(f"Nothing fits {name}: it asks for "
                         f"{need.sentence()}.")
        if self._linker:
            span = partition.linker_span(
                self._catalog.building_block(self._linker))
            back = partition.partitioner_requirement(self._node, span)
            others = linkers.suggest(back, None, n=3)
            said = ", ".join(f"{s.candidate.name} "
                             f"({s.candidate.value:.2f} A)"
                             for s in others)
            lines.append(f"{self._linker} asks for {back.sentence()}"
                         f"{': ' + said if said else ''}.")
        self.suggestions.setText("<br>".join(lines))
