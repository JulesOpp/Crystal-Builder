"""
xtalapp.dialogs.mof_build
=========================
Pick a net, then pick something to put on every slot it has.

This is the dialog :attr:`xtal.modules.registry.Action.dialog` names,
and it exists because the generated form cannot ask this question.
:class:`~xtal.params.Param` is a flat, static list on purpose -- the
registry says so and gives the reason -- and a MOF build's parameters
are neither: **how many** node slots there are, and **what
coordination number** each demands, is decided by the topology, and
only a building block with that many connection points may go in one.
So the topology is picked first and the rest of the form is built from
it.

Everything it hands back is the same ``values`` dict the generated
form would have produced, so :func:`xtal.modules.mof.build_framework`
never learns which asked.  The run folder, the worker thread, Stop and
``xtal run`` are all untouched.

Three things it does that are worth stating.

**It shows the pieces rather than naming them.**  A three-letter RCSR
symbol is exact and means nothing until you have memorised it, and
``N59`` means less than that; a list of 210 six-connected blocks by
name is one nobody can choose from.  Both are drawn --
:mod:`xtalapp.dialogs.mof_preview` -- and the vertices of the net are
coloured by node type in the same order the slot rows ask about them,
so "node 2" in the form and the orange vertices in the picture are
visibly the same thing.

**It never imports PORMAKE.**  The catalogue is read from the files,
which takes half a second for the whole 3.7 MB of it; ``import
pormake`` takes ten, and a dialog that pauses for ten seconds before
appearing is one people stop opening.  See :mod:`xtal.mof.catalog`.

**It does not identify the net it is showing.**  Naming a net against
the RCSR is a walk over ten shells and a smallest-ring search at every
angle, which is milliseconds for **pcu** and half a minute for the
worst net in the database -- far too slow for something that happens
on every click in a list of 2399.  The identification is part of the
*run*, where it is a check on what was built rather than a label on
what was picked, and it appears in the report.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from xtal.mof import Catalog
from xtal.mof.build import BuildRequest
from xtalapp.dialogs.mof_preview import (
    ORBIT_COLORS,
    BlockPreview,
    NetPreview,
)

#: What an edge slot offers instead of a linker.  A net has edges
#: whether or not anything is put on them, and PORMAKE builds an empty
#: one as a direct bond between the two nodes -- which is a real
#: answer and worth naming rather than reaching by leaving a box
#: blank.
NO_LINKER = "(none -- join the nodes directly)"


class MofBuildDialog(QDialog):
    """A topology, a block per node slot, a linker per edge type."""

    def __init__(self, module, action, parent=None, initial=None):
        super().__init__(parent)
        self.module = module
        self.action = action
        self.setWindowTitle(f"{module.label}: "
                            f"{action.label.rstrip('.')}")
        self._settings = getattr(parent, "settings", None)
        self._rows: list[_SlotRow] = []
        self._topology = None

        given = dict(action.coerce(initial or {}))
        self.topology_dir = _FolderEdit(
            "Extra topologies", self,
            given.get("topology_dir") or self._remembered(
                "mof_topology_dir"))
        self.bb_dir = _FolderEdit(
            "Extra building blocks", self,
            given.get("bb_dir") or self._remembered("mof_bb_dir"))
        self.catalog = self._catalog()

        self._build_ui()
        self._fill_topologies()
        self._restore(given)

    # -- construction --------------------------------------------------

    def _build_ui(self) -> None:
        self.filter = QLineEdit(self)
        self.filter.setPlaceholderText(
            "Filter by name, coordination or space group -- pcu, 6, "
            "Fm-3m")
        self.filter.textChanged.connect(self._apply_filter)

        self.topologies = QListWidget(self)
        self.topologies.currentItemChanged.connect(
            self._on_topology_changed)

        self.net_preview = NetPreview(self, minimum=(260, 210))
        self.details = QLabel(self)
        self.details.setWordWrap(True)
        self.details.setTextFormat(Qt.RichText)
        self.details.setAlignment(Qt.AlignTop)

        left = QWidget(self)
        column = QVBoxLayout(left)
        column.setContentsMargins(0, 0, 0, 0)
        column.addWidget(self.filter)
        column.addWidget(self.topologies, 1)

        right = QWidget(self)
        column = QVBoxLayout(right)
        column.setContentsMargins(0, 0, 0, 0)
        column.addWidget(self.net_preview, 1)
        column.addWidget(self.details)

        top = QSplitter(Qt.Horizontal, self)
        top.addWidget(left)
        top.addWidget(right)
        top.setStretchFactor(1, 1)

        self.slots_box = QGroupBox("Building blocks", self)
        self.slots_layout = QVBoxLayout(self.slots_box)
        area = QScrollArea(self)
        area.setWidgetResizable(True)
        area.setWidget(self.slots_box)
        area.setMinimumHeight(320)

        folders = QGroupBox("Your own topologies and building blocks",
                            self)
        form = QFormLayout(folders)
        form.addRow(self.topology_dir.label, self.topology_dir)
        form.addRow(self.bb_dir.label, self.bb_dir)
        self.topology_dir.changed.connect(self._reread)
        self.bb_dir.changed.connect(self._reread)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok |
                                   QDialogButtonBox.Cancel)
        self.build_button = buttons.button(QDialogButtonBox.Ok)
        self.build_button.setText("Build")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(top, 1)
        layout.addWidget(area)
        layout.addWidget(folders)
        layout.addWidget(buttons)
        self.resize(900, 780)

    def _remembered(self, name: str) -> str:
        return str(getattr(self._settings, name, "") or "")

    def _catalog(self) -> Catalog:
        return Catalog.default(self.topology_dir.text(),
                               self.bb_dir.text())

    def _reread(self) -> None:
        """A folder was named, so read everything again.

        The whole catalogue rather than the one folder that changed:
        a file in a later directory replaces one of PORMAKE's of the
        same name, so what is in the list depends on all of them.
        Half a second, and only when a path is edited.
        """
        name = self._topology.name if self._topology else ""
        self.catalog = self._catalog()
        self._fill_topologies()
        self._apply_filter(self.filter.text())
        if not self._select(name):
            self.topologies.setCurrentRow(0)

    # -- the topology list ---------------------------------------------

    def _fill_topologies(self) -> None:
        self.topologies.clear()
        for topology in self.catalog.topologies():
            item = QListWidgetItem(
                f"{topology.name}    {topology.summary()}")
            item.setData(Qt.UserRole, topology.name)
            # Everything the filter matches on, lowered once here
            # rather than on every keystroke of a 2399-row list.
            coordinations = " ".join(str(c) for c
                                     in topology.coordinations)
            item.setData(Qt.UserRole + 1,
                         f"{topology.name} {topology.summary()} "
                         f"{coordinations}".lower())
            self.topologies.addItem(item)

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for index in range(self.topologies.count()):
            item = self.topologies.item(index)
            item.setHidden(bool(needle) and needle not in
                           str(item.data(Qt.UserRole + 1)))

    def _select(self, name: str) -> bool:
        for index in range(self.topologies.count()):
            item = self.topologies.item(index)
            if item.data(Qt.UserRole) == name:
                self.topologies.setCurrentItem(item)
                self.topologies.scrollToItem(item)
                return True
        return False

    def _on_topology_changed(self, current, _previous=None) -> None:
        if current is None:
            return
        self._topology = self.catalog.topology(
            current.data(Qt.UserRole))
        self.net_preview.set_topology(self._topology)
        self._rebuild_slots()

    # -- the slots -----------------------------------------------------

    def _rebuild_slots(self) -> None:
        """One row per slot, from the topology that was just picked.

        Thrown away and made again rather than updated: the number of
        rows and what each may contain both change with the topology,
        and a row left over from the previous net is a row whose
        contents no longer fit anything.
        """
        while self.slots_layout.count():
            item = self.slots_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._rows = []
        try:
            slots = self._topology.slots()
        except Exception as exc:                    # noqa: BLE001
            self._refuse(f"{self._topology.name} cannot be built on: "
                         f"{exc}")
            return
        for slot in slots:
            row = _SlotRow(slot, self.catalog, self.slots_box)
            self.slots_layout.addWidget(row)
            self._rows.append(row)
        # So that one row does not stretch to fill a box sized for
        # five: a net with two node types and one edge type is the
        # common case and its rows belong at the top.
        self.slots_layout.addStretch(1)
        self._describe(slots)
        self.build_button.setEnabled(True)

    def _refuse(self, why: str) -> None:
        self.details.setText(
            f"<b>{self._topology.name}</b><br>{why}")
        self.build_button.setEnabled(False)

    def _describe(self, slots) -> None:
        topology = self._topology
        net = topology.net()
        lines = [f"<b>{topology.name}</b> &nbsp; {topology.group}",
                 f"{net.n_vertices} vertices and {len(net.edges)} "
                 f"edges in the cell"]
        for index, coordination in enumerate(topology.coordinations):
            colour = ORBIT_COLORS[index % len(ORBIT_COLORS)].name()
            lines.append(
                f"<span style='color:{colour}'>&#9679;</span> "
                f"node {index + 1}: {coordination}-connected")
        edges = [s for s in slots if s.is_edge]
        lines.append(f"{len(edges)} kind(s) of edge")
        self.details.setText("<br>".join(lines))

    # -- values --------------------------------------------------------

    def _restore(self, given: dict) -> None:
        """Show what was picked last time, as far as it still fits.

        A saved set names a topology and some blocks, and the blocks
        only mean anything against that topology -- so the topology is
        selected first, which rebuilds the rows, and then each row is
        told what it held.  A block that no longer fits its slot is
        left out rather than refused: the parameters outlive the
        catalogue they were chosen from.
        """
        wanted = str(given.get("topology") or "pcu")
        if not self._select(wanted) and not self._select("pcu"):
            self.topologies.setCurrentRow(0)
        try:
            request = BuildRequest.parse(wanted,
                                         given.get("nodes", ""),
                                         given.get("edges", ""))
        except Exception:                           # noqa: BLE001
            return
        if self._topology is None or self._topology.name != wanted:
            return
        for row in self._rows:
            row.set_block(request.block_for(row.slot))

    def values(self) -> dict:
        nodes, edges = [], []
        for row in self._rows:
            chosen = row.block()
            if not chosen:
                continue
            (edges if row.slot.is_edge else nodes).append(
                f"{row.slot.token}={chosen}")
        return self.action.coerce({
            "topology": self._topology.name if self._topology else "",
            "nodes": ",".join(nodes),
            "edges": ",".join(edges),
            "topology_dir": self.topology_dir.text(),
            "bb_dir": self.bb_dir.text(),
        })

    def accept(self) -> None:
        if self._settings is not None:
            self._settings.mof_topology_dir = self.topology_dir.text()
            self._settings.mof_bb_dir = self.bb_dir.text()
        super().accept()

    @classmethod
    def ask(cls, module, action, parent=None, initial=None):
        """The values to run with, or ``None`` if it was cancelled.

        The same contract as
        :meth:`xtalapp.dialogs.module_form.ModuleDialog.ask`, which is
        the whole of what ``Action.dialog`` promises.
        """
        dialog = cls(module, action, parent, initial)
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.values()


# ======================================================================
#  ONE SLOT
# ======================================================================

class _SlotRow(QWidget):
    """What goes in one slot: a label, a choice, and a picture.

    The choice offers only the blocks that fit -- a six-connected slot
    takes a block with six connection points and nothing else fits it
    at all -- because a list that offers the 657 that do not fit is a
    list whose every wrong answer is refused after the fact.
    """

    def __init__(self, slot, catalog: Catalog, parent=None):
        super().__init__(parent)
        self.slot = slot
        self.combo = QComboBox(self)
        # Fixed, not expanding: three slot rows sharing a scroll area
        # should each be a picture and a combo box, not a third of
        # whatever height the dialog happens to be.
        self.preview = BlockPreview(self, minimum=(190, 140))
        self.preview.setFixedSize(190, 140)

        fitting = _ordered(catalog.fitting(slot.coordination))
        if slot.is_edge:
            # A net has edges whether or not anything is put on them,
            # and PORMAKE builds an empty one as a direct bond between
            # the two nodes.  That is a real answer -- it is what a
            # framework with no linker is -- so it is offered rather
            # than reached by leaving a box blank.
            self.combo.addItem(NO_LINKER, "")
        for block in fitting:
            self.combo.addItem(f"{block.name}    {block.summary()}",
                               block.name)
        self.combo.currentIndexChanged.connect(self._on_changed)
        self._catalog = catalog

        heading = QLabel(f"<b>{slot.label}</b>", self)
        count = QLabel(f"{len(fitting)} block(s) fit", self)
        count.setStyleSheet("color: palette(mid);")

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 4, 0, 4)
        grid.addWidget(heading, 0, 0)
        grid.addWidget(self.combo, 1, 0)
        grid.addWidget(count, 2, 0)
        grid.addWidget(self.preview, 0, 1, 3, 1)
        grid.setColumnStretch(0, 1)
        self._on_changed()

    def _on_changed(self, *_args) -> None:
        name = self.block()
        self.preview.set_block(
            self._catalog.building_block(name) if name else None)

    def block(self) -> str:
        return str(self.combo.currentData() or "")

    def set_block(self, name: str) -> None:
        index = self.combo.findData(str(name or ""))
        if index >= 0:
            self.combo.setCurrentIndex(index)


def _ordered(blocks) -> list:
    """Metals first, then by name.

    A node slot is nearly always a metal cluster and an edge slot
    nearly always is not, so putting the metals at the top of both
    lists puts the likely answer where it can be found -- and, in a
    list of 210, "likely" is worth a great deal.
    """
    return sorted(blocks, key=lambda b: (not b.has_metal, b.name))


class _FolderEdit(QWidget):
    """A directory, and the button nobody wants to type one without."""

    changed = Signal()

    def __init__(self, title: str, parent=None, initial: str = ""):
        super().__init__(parent)
        self.label = QLabel(title, parent)
        self.edit = QLineEdit(str(initial or ""), self)
        self.edit.setPlaceholderText(
            "a folder of your own files, read alongside PORMAKE's")
        self.edit.editingFinished.connect(self.changed)
        button = QPushButton("Browse...", self)
        button.clicked.connect(self._browse)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.edit, 1)
        layout.addWidget(button)

    def _browse(self) -> None:                      # pragma: no cover
        chosen = QFileDialog.getExistingDirectory(
            self, self.label.text(), self.edit.text() or
            str(Path.home()))
        if chosen:
            self.edit.setText(chosen)
            self.changed.emit()

    def text(self) -> str:
        return self.edit.text().strip()
