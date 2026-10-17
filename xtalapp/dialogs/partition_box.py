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

*Draw...* is the slot rows' own dialog aimed at a tritopic pyridyl,
saved into the workspace's ``blocks/partitioners``
(:data:`xtal.mof.partition.DRAWN`), never ``blocks/`` itself, where
PORMAKE would offer it to every three-connected node slot.  Drawn
pyridines are enough: their free nitrogens are the points.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from xtal.mof import linkers, partition
from xtal.mof.trimer import TrimerError
from xtalapp.busy import busy
from xtalapp.dialogs.mof_preview import BlockPreview
from xtalapp.dialogs.rod_build import PREVIEW, drawn_linker
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
        # A name and its full name is 60 characters: as wide as the
        # row allows, never wider.
        self.choice.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.choice.setMinimumContentsLength(10)
        self.choice.currentIndexChanged.connect(self._say)
        self.choice.currentIndexChanged.connect(self._draw)
        #: The partitioner chosen, drawn: the molecule that will sit on
        #: the channel axis, its three points on the donor nitrogens.
        #: Laid out as a slot row is, so it sits in the column of the
        #: node's and the linker's pictures; an empty box for None.
        self.picture = BlockPreview(self, minimum=PREVIEW)
        self.picture.setFixedSize(*PREVIEW)
        self.picture.empty_text = "no partitioner"
        self.count = QLabel(self)
        self.count.setWordWrap(True)
        set_tone(self.count, HINT)
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
        self.draw = QPushButton("Draw...", self)
        self.draw.setToolTip(
            "Draw a partitioner of your own: three pyridines on a C3 "
            "core, drawn as they are -- each free ring nitrogen is a "
            "point.  It is listed with the others and ranked by the "
            "cell it makes.")
        self.draw.clicked.connect(self._draw_one)
        #: Where a drawn partitioner's folder is: a callable giving the
        #: blocks folder the builder draws into, set by the dialog.
        self.blocks_folder = None
        self.suggestions = QLabel(self)
        self.suggestions.setWordWrap(True)
        self.suggestions.setTextFormat(Qt.RichText)
        self.suggestions.linkActivated.connect(self.use_linker)
        set_tone(self.suggestions, HINT)

        # The slot rows' shape: a heading, the choice and its button,
        # a count, and the picture to the right of all three.
        picker = QHBoxLayout()
        picker.setContentsMargins(0, 0, 0, 0)
        picker.addWidget(self.choice, 1)
        picker.addWidget(self.suggest)
        # Under the choice, beside the count: a third button on its
        # line made the builder scroll sideways at 560 px.
        below = QHBoxLayout()
        below.setContentsMargins(0, 0, 0, 0)
        below.addWidget(self.count, 1)
        below.addWidget(self.draw)
        grid = QGridLayout()
        grid.setContentsMargins(0, 4, 0, 4)
        grid.addWidget(QLabel("<b>Partitioner</b>", self), 0, 0)
        grid.addLayout(picker, 1, 0)
        grid.addLayout(below, 2, 0)
        grid.addWidget(self.picture, 0, 1, 3, 1)
        grid.setColumnStretch(0, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(grid)
        layout.addWidget(self.nodes)
        layout.addWidget(self.status)
        layout.addWidget(self.suggestions)

        self._catalog = None
        self._compatible = None
        self._node = None
        self._linker = ""
        self._fits: dict[str, partition.Fit] = {}
        self._framework = (None, "", "", "")
        self._fill([])
        self.set_framework(None, "", "", "")

    # -- what it is told -----------------------------------------------

    def set_framework(self, catalog, topology: str, node: str,
                      linker: str) -> None:
        """The net, trimer and linker chosen above, as names."""
        self._framework = (catalog, topology, node, linker)
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
        for widget in (self.choice, self.suggest, self.draw):
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
            fits = partition.rank(self._node, linker, span,
                                  partition.candidates(catalog))
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
            p = partition.partitioner(fit.partitioner, self._catalog)
            self.choice.addItem(f"{p.name} -- {p.full_name}", p.name)
            at = self.choice.count() - 1
            self.choice.setItemData(at, fit.sentence(), Qt.ToolTipRole)
            if not fit.ok and isinstance(model, QStandardItemModel):
                model.item(at).setEnabled(False)
        if fits and not any(f.ok for f in fits):
            model.item(1).setEnabled(False)
        closing = sum(f.ok for f in fits)
        self.count.setText(
            f"{closing} of {len(fits)} close the cell" if fits else
            f"{len(partition.candidates(self._catalog))} "
            f"partitioners")
        at = self.choice.findData(kept)
        self.choice.setCurrentIndex(at if at >= 0 and self._enabled(at)
                                    else 0)
        self.choice.blockSignals(False)
        self._say()
        self._draw()

    def _enabled(self, at: int) -> bool:
        model = self.choice.model()
        if not isinstance(model, QStandardItemModel):
            return True
        return model.item(at).isEnabled()

    def shown(self) -> str:
        """The partitioner the picture is of, ``""`` for none: the one
        chosen, or the one *Best fit* builds."""
        value = self.value()
        if value == partition.AUTO:
            fit = self._chosen_fit()
            return fit.partitioner if fit is not None else ""
        return value

    def _draw(self, *_args) -> None:
        name = self.shown()
        block = None
        if name:
            try:
                with busy():
                    block = partition.drawn(name, self._catalog)
            except Exception:                       # noqa: BLE001
                block = None
        self.picture.set_block(drawn_linker(block, name)
                               if block is not None else None)

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
        need = partition.linker_requirement(
            self._node, partition.partitioner(name, self._catalog))
        found = linkers.suggest(need, self._catalog, n=SUGGESTIONS,
                                invent=True)
        lines = []
        if found:
            items = ", ".join(
                f"<a href='{s.candidate.name}'>{s.candidate.name}</a>"
                f"{linkers.mark(s)} ({s.miss:+.2f})" for s in found)
            said = linkers.legend(found)
            lines.append(f"{name} asks for {need.sentence()}.  "
                         f"Closest: {items} -- click one to use it"
                         f"{'; ' + said if said else ''}.")
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

    # -- drawing one -----------------------------------------------------

    def drawn_folder(self) -> Path | None:
        """Where a drawn partitioner goes, ``None`` with nowhere."""
        folder = self.blocks_folder() if self.blocks_folder else ""
        return Path(folder) / partition.DRAWN if folder else None

    def _start_smiles(self) -> str:
        """The partitioner shown, as Draw starts from it."""
        name = self.shown()
        if not name:
            return ""
        try:
            p = partition.partitioner(name, self._catalog)
            if p.smiles:
                return p.smiles
            from xtal.build.chem import block_smiles

            block = partition.drawn(name, self._catalog)
            return block_smiles(block.symbols, block.bonds)
        except Exception:                           # noqa: BLE001
            return ""

    def _draw_one(self) -> None:
        from xtalapp.dialogs.draw_block import DrawBlockDialog

        folder = self.drawn_folder()
        if folder is None:
            return
        slot = SimpleNamespace(label="Partitioner", coordination=3,
                               nitrogen=True)
        written = DrawBlockDialog.ask(slot, str(folder), self,
                                      smiles=self._start_smiles())
        if written is None:
            return
        self.set_framework(*self._framework)
        name = written.stem
        if self.set_value(name):
            return
        if any(p.name == name for p in partition.PARTITIONERS):
            said = (f"{name} is saved, but a shipped partitioner has "
                    f"that name and is the one listed: draw it again "
                    f"under another name.")
        elif name in self._fits:
            said = (f"{name} is saved, and cannot close this cell: "
                    f"{self._fits[name].sentence()}.")
        else:
            said = (f"{name} is saved into {folder}, which this "
                    f"catalogue does not read.")
        self.status.setText(said)
        set_tone(self.status, WARNING)
