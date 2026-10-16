"""
xtalapp.dialogs.net_explorer
============================
Modules ▸ MOF ▸ Merged-net explorer: the 352 merged nets of Jiang et
al. (Science 2024) as a table to sort and narrow, each with the two
nets it merges.

The table is :mod:`xtal.mof.merged_nets` and nothing here repeats it.
Choosing a row says "spn + hxg → sph", each name a link that draws
that net.  *Open net* draws the merged net through the Net builder --
so it is a document with an entry like any other -- with each parent
an atom group in a colour of its own: unticking one in the Atom
groups panel leaves the other.  *Build on this net* opens the MOF
builder with the net picked.  *Components of the tab in front* breaks
whatever net is drawn there into the nets its kinds of edge span
(:mod:`xtal.analysis.components`), a built framework included.

A window of its own and not a modal: a person compares rows while
nets open behind it.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from xtal.mof import merged_nets
from xtalapp.busy import busy
from xtalapp.widgets.tone import HINT, WARNING, set_tone

#: The columns, in order.
COLUMNS = ("Net", "Parents", "Type", "Coordination", "Merged CN",
           "Edge ratio", "Proposed", "Made")

#: Every choice of the type and cluster boxes.
ANY = "Any"


class _Number(QTableWidgetItem):
    """A cell that sorts by its number, not its text."""

    def __init__(self, text: str, value: float):
        super().__init__(text)
        self.setData(Qt.UserRole, value)

    def __lt__(self, other) -> bool:
        mine, theirs = self.data(Qt.UserRole), other.data(Qt.UserRole)
        if mine is None or theirs is None:
            return super().__lt__(other)
        return mine < theirs


class NetExplorer(QMainWindow):
    """The merged-net table, for one main window."""

    def __init__(self, window=None):
        super().__init__(window, Qt.Window)
        self.window_ = window
        self.setWindowTitle("Merged-net explorer")
        self.rows = merged_nets.table()

        self.search = QLineEdit(self)
        self.search.setPlaceholderText("A net or a parent: sph, spn, "
                                       "pcu")
        self.search.textChanged.connect(self._narrow)
        self.kind = QComboBox(self)
        self.kind.addItems([ANY, *merged_nets.TYPES])
        self.kind.setToolTip("What the second parent is: a 3-periodic "
                             "net, a layer, a rod or a polyhedron")
        self.kind.currentIndexChanged.connect(self._narrow)
        self.cluster = QComboBox(self)
        self.cluster.addItem(ANY)
        for cn in sorted({r.merged_cn for r in self.rows if r.merged_cn}):
            self.cluster.addItem(str(cn))
        self.cluster.setToolTip("The coordination of the vertex the "
                                "parents share -- the cluster's")
        self.cluster.currentIndexChanged.connect(self._narrow)
        self.made = QCheckBox("Made", self)
        self.made.setToolTip("Only nets a MOF has been made on")
        self.made.toggled.connect(self._narrow)
        self.count = QLabel(self)
        set_tone(self.count, HINT)

        filters = QHBoxLayout()
        filters.addWidget(self.search, 1)
        filters.addWidget(QLabel("Type", self))
        filters.addWidget(self.kind)
        filters.addWidget(QLabel("Merged CN", self))
        filters.addWidget(self.cluster)
        filters.addWidget(self.made)
        filters.addWidget(self.count)

        self.diagram = QLabel(self)
        self.diagram.setTextFormat(Qt.RichText)
        self.diagram.setAlignment(Qt.AlignCenter)
        self.diagram.linkActivated.connect(self.open_net)
        self.details = QLabel(self)
        self.details.setWordWrap(True)
        set_tone(self.details, HINT)

        self.table = QTableWidget(0, len(COLUMNS), self)
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._chosen_changed)
        self.table.itemDoubleClicked.connect(
            lambda _item: self.open_net(self.chosen_name()))

        self.open_button = QPushButton("Open net", self)
        self.open_button.setToolTip(
            "Draw the merged net in a new tab, each parent an atom "
            "group of its own colour")
        self.open_button.clicked.connect(
            lambda: self.open_net(self.chosen_name()))
        self.build_button = QPushButton("Build on this net...", self)
        self.build_button.setToolTip("Open the MOF builder with this "
                                     "net picked")
        self.build_button.clicked.connect(self.build_on)
        self.parts_button = QPushButton("Components of the tab in front",
                                        self)
        self.parts_button.setToolTip(
            "Break the net drawn in the tab in front -- a drawn net "
            "or a built framework -- into the nets its kinds of edge "
            "span")
        self.parts_button.clicked.connect(self.components_in_front)
        self.parts = QLabel(self)
        self.parts.setWordWrap(True)
        set_tone(self.parts, HINT)
        buttons = QHBoxLayout()
        buttons.addWidget(self.open_button)
        buttons.addWidget(self.build_button)
        buttons.addStretch(1)
        buttons.addWidget(self.parts_button)

        source = QLabel(merged_nets.SOURCE, self)
        source.setWordWrap(True)
        set_tone(source, HINT)

        body = QWidget(self)
        layout = QVBoxLayout(body)
        layout.addLayout(filters)
        layout.addWidget(self.diagram)
        layout.addWidget(self.details)
        layout.addWidget(self.table, 1)
        layout.addLayout(buttons)
        layout.addWidget(self.parts)
        layout.addWidget(source)
        self.setCentralWidget(body)
        self.resize(980, 640)

        self._fill()
        self._narrow()
        if not self.rows:
            self.diagram.setText("The merged-net table did not travel "
                                 "with this installation.")
            set_tone(self.diagram, WARNING)

    # -- the table ---------------------------------------------------------

    def _fill(self) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.rows))
        for at, r in enumerate(self.rows):
            ratio = r.ratio[1] if r.ratio else ""
            try:
                value = float(ratio)
            except ValueError:
                value = None
            cells = (
                QTableWidgetItem(r.name),
                QTableWidgetItem(" + ".join(r.parents)),
                QTableWidgetItem(r.type),
                QTableWidgetItem(
                    "-".join(str(c) for c in r.coordination)),
                _Number(str(r.merged_cn or ""), r.merged_cn),
                _Number(str(ratio), value),
                _Number(str(len(r.proposed) or ""), len(r.proposed)),
                QTableWidgetItem(", ".join(r.made)),
            )
            for column, cell in enumerate(cells):
                if column == 0:
                    cell.setData(Qt.UserRole + 1, r.name)
                self.table.setItem(at, column, cell)
        self.table.setSortingEnabled(True)
        self.table.sortItems(0, Qt.AscendingOrder)

    def _narrow(self, *_args) -> None:
        text = self.search.text().strip().lower()
        kind = self.kind.currentText()
        cluster = self.cluster.currentText()
        shown = 0
        for at in range(self.table.rowCount()):
            r = merged_nets.row(self._name_at(at))
            keep = r is not None and (
                (not text or text == r.name or text in r.parents
                 or r.name.startswith(text))
                and (kind == ANY or r.type == kind)
                and (cluster == ANY or str(r.merged_cn) == cluster)
                and (not self.made.isChecked() or bool(r.made)))
            self.table.setRowHidden(at, not keep)
            shown += keep
        self.count.setText(f"{shown} of {len(self.rows)}")

    def _name_at(self, at: int) -> str:
        item = self.table.item(at, 0)
        return str(item.data(Qt.UserRole + 1)) if item else ""

    def visible_names(self) -> list[str]:
        return [self._name_at(at) for at in range(self.table.rowCount())
                if not self.table.isRowHidden(at)]

    def chosen_name(self) -> str:
        rows = self.table.selectionModel().selectedRows()
        return self._name_at(rows[0].row()) if rows else ""

    def choose(self, name: str) -> bool:
        for at in range(self.table.rowCount()):
            if self._name_at(at) == name:
                self.table.selectRow(at)
                return True
        return False

    def _chosen_changed(self) -> None:
        r = merged_nets.row(self.chosen_name())
        live = r is not None
        self.open_button.setEnabled(live)
        self.build_button.setEnabled(live and self._buildable(r.name))
        if r is None:
            self.diagram.clear()
            self.details.clear()
            return
        first, second = r.parents
        self.diagram.setText(
            f"<a href='{first}'>{first}</a> + "
            f"<a href='{second}'>{second}</a> &rarr; "
            f"<a href='{r.name}'><b>{r.name}</b></a>")
        lines = [r.sentence()]
        if r.ratio:
            lines.append(f"edge ratio {r.ratio[0]} as the parents "
                         f"have it, {r.ratio[1]} in the Systre model")
        if r.proposed:
            lines.append(f"proposed on clusters "
                         f"{', '.join(r.proposed)} (Data S7)")
        if not self._buildable(r.name):
            lines.append("the MOF builder cannot read this net as it "
                         "is embedded")
        self.details.setText(".  ".join(lines) + ".")

    def _buildable(self, name: str) -> bool:
        try:
            self._catalog().topology(name)
        except Exception:                           # noqa: BLE001
            return False
        return True

    def _catalog(self):
        from xtal.mof.catalog import Catalog

        if not hasattr(self, "_cat"):
            self._cat = Catalog.default()
        return self._cat

    # -- what it does --------------------------------------------------------

    def open_net(self, name: str) -> None:
        """Draw ``name`` in a new tab: a merged net with its parents
        as groups, any other the RCSR's."""
        if not name or self.window_ is None:
            return
        self.window_.run_module_action("net", "draw", {"net": name})

    def build_on(self) -> None:
        name = self.chosen_name()
        if name and self.window_ is not None:
            self.window_.run_module_action("mof", "build",
                                           initial={"topology": name})

    def components_in_front(self) -> None:
        """The nets the drawn net of the tab in front breaks into."""
        from xtal.analysis import components
        from xtal.analysis.topology import net_of_chemistry

        document = (self.window_.current_document()
                    if self.window_ is not None else None)
        if document is None:
            self.parts.setText("Open a net or a framework first.")
            return
        try:
            with busy():
                net, kinds = components.drawn_kinds(document.structure)
                if not net.edges:
                    # A drawn net (the Net builder's) is its bonds.
                    net = net_of_chemistry(document.structure)
                    kinds = components.edge_kinds(net)
                found = components.components(net, kinds)
        except (ValueError, KeyError) as exc:
            self.parts.setText(f"No net drawn in front to break up: "
                               f"{exc}.")
            return
        named = [c.sentence() for c in found if c.name]
        rest = sum(1 for c in found if not c.name)
        self.parts.setText(
            "Components: " + ("; ".join(named) or "none named")
            + (f" (and {rest} set(s) of edges that span no named "
               f"net)" if rest else "") + ".")
