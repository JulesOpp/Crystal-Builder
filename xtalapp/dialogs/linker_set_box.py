"""
xtalapp.dialogs.linker_set_box
==============================
The MOF builder's *Linker sets* section.

Live for a net with more than one kind of edge, all of them meeting
the slot that holds a metal cluster -- sph on a 12-c cluster, with a
tritopic and a hexatopic to choose.  The arithmetic is
:mod:`xtal.mof.merged` and nothing here repeats it.  Asking is by
button and not on every change, because a scan of the net's free
coordinates is a second.

*Check set* says whether the linkers chosen close every edge at one
scale, and remembers where: the build is then of the net re-embedded
there (``sph@-0.1250``), since PORMAKE fits each block to the file's
own directions and the RCSR draws sph's 3-c vertex as a pyramid.
*Suggest sets* lists the catalogue's pairs that do, and for every
linker already chosen what it asks of the other slots, generated
molecules included; a click puts the block in its row.

Greyed rather than hidden, as the partition section is.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from xtal.mof import linkers, merged
from xtalapp.busy import busy
from xtalapp.widgets.tone import HINT, WARNING, set_tone

#: How many sets and how many single linkers a suggestion lists.
SETS = 5
SUGGESTIONS = 4


class LinkerSetBox(QWidget):
    """A set of linkers for the cluster chosen above it."""

    #: The person clicked a block for one slot: ``(slot key, name)``.
    use_block = Signal(int, str)                     # noqa: N815

    def __init__(self, parent=None):
        super().__init__(parent)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        set_tone(self.status, HINT)
        self.check = QPushButton("Check set", self)
        self.check.setToolTip(
            "Whether the linkers chosen close every kind of edge at "
            "one scale, with each block's shape on its vertex.  A set "
            "that does is built where it fits.")
        self.check.clicked.connect(self._check)
        self.suggest = QPushButton("Suggest sets", self)
        self.suggest.setToolTip(
            "Pairs from the catalogue that close every edge, and what "
            "each linker already chosen asks of the others")
        self.suggest.clicked.connect(self._suggest)
        self.suggestions = QLabel(self)
        self.suggestions.setWordWrap(True)
        self.suggestions.setTextFormat(Qt.RichText)
        self.suggestions.linkActivated.connect(self._clicked)
        set_tone(self.suggestions, HINT)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.check)
        row.addWidget(self.suggest)
        row.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.status)
        layout.addLayout(row)
        layout.addWidget(self.suggestions)

        self._catalog = None
        self._topology = None
        self._chosen: dict[int, str] = {}
        self._cluster_slot: int | None = None
        self._linker_slots: tuple[int, ...] = ()
        #: ``(net, {slot: block}, re-embedded name)`` of the last set
        #: that checked, which :meth:`embedded` hands back while the
        #: rows still hold it.
        self._fitted: tuple | None = None
        self._scans: dict = {}
        self.set_framework(None, None, {})

    # -- what it is told -----------------------------------------------

    def set_framework(self, catalog, topology, chosen: dict) -> None:
        """The net and the node blocks chosen above (``{slot key:
        name}``)."""
        if catalog is not self._catalog:
            self._scans = {}
        self._catalog = catalog
        self._topology = topology
        self._chosen = {k: v for k, v in chosen.items() if v}
        self._cluster_slot = None
        self._linker_slots = ()
        reason = self._plan()
        live = not reason
        self.check.setEnabled(live)
        self.suggest.setEnabled(live)
        if not live:
            self.status.setText(reason)
            set_tone(self.status, HINT)
            self.suggestions.clear()
            return
        self._say_plan()

    def _plan(self) -> str:
        """Why there is no set to work out, or ``""``."""
        if self._catalog is None or self._topology is None:
            return "Pick a net."
        metals = [k for k, name in self._chosen.items()
                  if self._block(name) is not None
                  and self._block(name).has_metal]
        if not metals:
            return ("A linker set is for a net with several kinds of "
                    "edge round one cluster (sph, a merged net): pick "
                    "it, and a metal cluster for one node.")
        # The most connected metal is the cluster: a row always holds
        # some block, and a 6-c slot's first one may be a metal too.
        coordination = self._topology.coordinations
        metals.sort(key=lambda k: -coordination[k])
        problem = ""
        for slot in metals:
            try:
                _free, edge_of = merged.plan(
                    self._topology, slot,
                    self._block(self._chosen[slot]))
                break
            except merged.SetError as exc:
                problem = problem or str(exc)
        else:
            return f"No linker set to work out: {problem}."
        metals = [slot]
        self._cluster_slot = metals[0]
        self._linker_slots = tuple(sorted(set(edge_of.values())))
        return ""

    def _say_plan(self) -> None:
        cluster = self._chosen[self._cluster_slot]
        fitted = self.embedded(self._topology.name, self._chosen)
        if fitted:
            self.status.setText(f"This set fits: it is built on "
                                f"{fitted}, the net where it does.")
            set_tone(self.status, HINT)
            return
        self.status.setText(
            f"{self._topology.name} joins {cluster} to "
            f"{len(self._linker_slots)} kinds of linker, and a set "
            f"must close every edge at one scale.  Check it to build "
            f"where it fits; unchecked, it is built on the net as "
            f"drawn.")
        set_tone(self.status, HINT)

    # -- what it hands back --------------------------------------------

    def embedded(self, topology: str, chosen: dict) -> str:
        """The re-embedded net to build on, while ``chosen`` is the
        set that last checked on ``topology``; ``""`` otherwise."""
        if self._fitted is None:
            return ""
        net, blocks, name = self._fitted
        if net != topology:
            return ""
        held = {k: v for k, v in chosen.items() if v}
        if any(held.get(k) != v for k, v in blocks.items()):
            return ""
        return name

    def adopt(self, name: str, chosen: dict) -> None:
        """A re-embedded net picked last time, with its blocks: built
        there again without asking, as it was."""
        spelled = merged.parse(name)
        if spelled is None:
            return
        self._fitted = (spelled[0], {k: v for k, v in chosen.items()
                                     if v}, name)

    # -- inside ----------------------------------------------------------

    def _block(self, name: str):
        try:
            return self._catalog.building_block(name)
        except Exception:                           # noqa: BLE001
            return None

    def _scan(self):
        key = (self._topology.name, self._chosen[self._cluster_slot])
        if key not in self._scans:
            self._scans[key] = merged.scan(
                self._topology, self._cluster_slot,
                self._block(key[1]))
        return self._scans[key]

    def _check(self) -> None:
        missing = [k for k in self._linker_slots if k not in self._chosen]
        if missing:
            nodes = ", ".join(str(k + 1) for k in missing)
            self.status.setText(f"Pick a block for node {nodes} first, "
                                f"or ask for suggestions.")
            set_tone(self.status, HINT)
            return
        blocks = {k: self._block(self._chosen[k])
                  for k in self._linker_slots}
        cluster = self._block(self._chosen[self._cluster_slot])
        try:
            with busy():
                found = merged.check_set(self._topology,
                                         self._cluster_slot, cluster,
                                         blocks)
        except merged.SetError as exc:
            self._fitted = None
            self.status.setText(f"This set does not fit: {exc}.")
            set_tone(self.status, WARNING)
            return
        name = merged.spelled(self._topology.name, found.sample.u)
        self._fitted = (self._topology.name,
                        {k: self._chosen[k] for k in
                         (*self._linker_slots, self._cluster_slot)},
                        name)
        self.status.setText(f"This set fits -- {found.sentence()}.  "
                            f"It is built on {name}, the net where it "
                            f"does.")
        set_tone(self.status, HINT)

    def _suggest(self) -> None:
        cluster = self._block(self._chosen[self._cluster_slot])
        lines = []
        with busy():
            scanned = self._scan()
            try:
                sets = merged.suggest_sets(self._topology,
                                           self._cluster_slot, cluster,
                                           self._catalog, n=SETS)
            except merged.SetError as exc:
                sets = []
                lines.append(f"{exc}.")
            if sets:
                items = "; ".join(
                    f"<a href='set:{_spelled(s.blocks)}'>"
                    f"{_named(s.blocks)}</a> "
                    f"({100 * s.strain:.1f} %)" for s in sets)
                lines.append(f"Sets from the catalogue: {items} -- "
                             f"click one to use it.")
            elif not lines:
                lines.append("No pair in the catalogue closes every "
                             "edge; see what each linker asks for.")
            for slot in self._linker_slots:
                if slot not in self._chosen:
                    continue
                reach = merged.block_reach(
                    self._block(self._chosen[slot]))
                try:
                    asked = merged.edge_requirements(
                        self._topology, self._cluster_slot, cluster,
                        given={slot: reach}, scanned=scanned)
                except merged.SetError as exc:
                    lines.append(f"{self._chosen[slot]}: {exc}.")
                    continue
                for other, need in asked.items():
                    lines.append(self._asks(slot, other, need))
        self.suggestions.setText("<br>".join(lines))

    def _asks(self, slot: int, other: int, need) -> str:
        found = linkers.suggest(need, self._catalog, n=SUGGESTIONS)
        head = (f"{self._chosen[slot]} asks node {other + 1} for "
                f"{need.sentence()}")
        if not found:
            return head + ": nothing in the catalogue or the series."
        items = ", ".join(
            f"<a href='{other}:{s.candidate.name}'>{s.candidate.name}"
            f"</a>{'*' if s.candidate.source == 'series' else ''} "
            f"({s.miss:+.2f})" for s in found)
        generated = any(s.candidate.source == "series" for s in found)
        return (f"{head}: {items}"
                f"{' -- * is generated' if generated else ''}.")

    def _clicked(self, href: str) -> None:
        if href.startswith("set:"):
            for part in href[4:].split(","):
                key, name = part.split("=", 1)
                self.use_block.emit(int(key), name)
            return
        key, name = href.split(":", 1)
        self.use_block.emit(int(key), name)


def _spelled(blocks: dict) -> str:
    return ",".join(f"{k}={b.name}" for k, b in sorted(blocks.items()))


def _named(blocks: dict) -> str:
    return " + ".join(b.name for _k, b in sorted(blocks.items()))
