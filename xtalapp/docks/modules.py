"""
xtalapp.docks.modules
=====================
The module tree: what can be run, beside what it produced.

The workspace dock on the left shows the *output* of every calculation
that has been run.  This one shows the *input* -- every module and
every entry under it -- and the two panels next to each other are the
whole workflow: pick a thing to run on the left, watch its folder
appear underneath the structure on the other.

It is built from :data:`xtal.modules.MODULES` and knows the name of no
module in particular, which is the point of Phase D.  A module
installed as a plugin appears here and in the Modules menu without
either file changing.

**A module that cannot run says so where it is, not when it is
clicked.**  An external engine whose binary is not installed is the
state it will usually be in, so ``Module.check`` is consulted every
time the tree is built and an unavailable module is greyed out with
the reason as its tooltip -- rather than looking perfectly normal
until it fails.

**Stop lives here.**  A run started from this tree is stopped from the
footer of this tree, which is also the only place that knows whether
one is going. The Force Field panel keeps its own Stop button for its
own runs, because those are its own worker and always have been.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from xtal.modules import MODULES

#: Role carrying ``(module name, action name)`` on every leaf, and
#: ``(module name, "")`` on every module row.
MODULE_ROLE = Qt.UserRole + 1

#: Set on the row under an unavailable module that says why.
WHY_ROLE = Qt.UserRole + 2


class ModuleTree(QTreeView):
    """Every module, and the entries underneath it."""

    actionActivated = Signal(str, str)          # module, action
    setupRequested = Signal(str)                # module

    def __init__(self, registry=MODULES, parent=None):
        super().__init__(parent)
        self.registry = registry
        self.model_ = QStandardItemModel(self)
        self.setModel(self.model_)
        self.setHeaderHidden(True)
        self.setExpandsOnDoubleClick(False)
        self.activated.connect(self._on_activated)
        self.refresh()

    def refresh(self) -> None:
        """Read the registry again and rebuild.

        Cheap, and called whenever something might have changed --
        ``Module.check`` is a ``shutil.which`` and the tree is a
        handful of rows.  Anything more would be a cache of an answer
        the filesystem already has.
        """
        self.model_.clear()
        root = self.model_.invisibleRootItem()
        modules = list(self.registry)
        if not modules:                             # pragma: no cover
            root.appendRow(_row("No modules registered", None, None,
                                enabled=False))
            return
        for module in modules:
            root.appendRow(self._module_item(module))
        self.expandAll()

    def _module_item(self, module) -> QStandardItem:
        available = module.availability()
        item = _row(module.label, module.name, "",
                    enabled=bool(available))[0]
        item.setToolTip(available.reason if not available
                        else (module.description or module.label))
        if not available:
            item.appendRow([_why(module.name, available.reason)])
        for action in module.actions:
            leaf = _row(action.label, module.name, action.name,
                        enabled=bool(available))[0]
            leaf.setToolTip(action.tip or action.label)
            item.appendRow([leaf])
        if not module.actions:                      # pragma: no cover
            item.appendRow(_row("(nothing to run)", None, None,
                                enabled=False))
        return item

    def _on_activated(self, index) -> None:
        item = self.model_.itemFromIndex(index)
        payload = item.data(MODULE_ROLE) if item is not None else None
        if not payload:
            return
        module, action = payload
        if item.data(WHY_ROLE):
            self.setupRequested.emit(str(module))
            return
        if not action:
            self.setExpanded(index, not self.isExpanded(index))
            return
        self.actionActivated.emit(str(module), str(action))


def _row(text: str, module, action, enabled: bool = True) -> list:
    item = QStandardItem(text)
    item.setEditable(False)
    if module is not None:
        item.setData((module, action or ""), MODULE_ROLE)
    item.setEnabled(enabled)
    return [item]


def _why(module: str, reason: str) -> QStandardItem:
    """The row that says why a module is greyed, and is not greyed.

    The reason was already a good sentence -- what was looked for,
    which variable is unset, where to get it -- and it was the
    tooltip of a disabled row: macOS shows none on a disabled item,
    and a disabled row takes no click.  "The Zeo++ menu is greyed
    out" is the commonest question a program like this is asked, and
    the answer was one hover away that nobody could make.  Its first
    line is the row; the whole of it is the tooltip; activating it is
    the way to fix it.
    """
    first = reason.strip().splitlines()[0] if reason.strip() else ""
    item = _row(first or "Not available", module, "")[0]
    item.setData(True, WHY_ROLE)
    item.setToolTip(reason)
    font = item.font()
    font.setItalic(True)
    item.setFont(font)
    return item


class ModulesDock(QDockWidget):
    """The module tree, and the Stop button for what it started."""

    actionActivated = Signal(str, str)          # module, action
    setupRequested = Signal(str)                # module
    stopRequested = Signal()

    def __init__(self, registry=MODULES, parent=None):
        super().__init__("Modules", parent)
        self.setObjectName("ModulesDock")
        self.setAllowedAreas(Qt.LeftDockWidgetArea |
                             Qt.RightDockWidgetArea)

        self.tree = ModuleTree(registry)
        self.tree.actionActivated.connect(self.actionActivated)
        self.tree.setupRequested.connect(self.setupRequested)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: palette(mid);")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stopRequested)

        footer = QHBoxLayout()
        footer.setContentsMargins(6, 0, 6, 4)
        footer.addWidget(self.status, 1)
        footer.addWidget(self.stop_button)

        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(2)
        body.addWidget(self.tree, 1)
        body.addLayout(footer)

        container = QWidget()
        container.setLayout(body)
        self.setWidget(container)
        self.set_idle()

    # -- what is going -------------------------------------------------

    def refresh(self) -> None:
        self.tree.refresh()

    def set_running(self, label: str) -> None:
        """A run has started: say what, and offer to stop it.

        The tree itself is disabled while one runs.  Two module runs
        at once would want two run folders, two progress lines and a
        Stop button that asks which -- and nothing in TODO.md wants
        that yet.
        """
        self.status.setText(f"running {label}...")
        self.status.setVisible(True)
        self.stop_button.setEnabled(True)
        self.tree.setEnabled(False)

    def set_progress(self, text: str) -> None:
        if text:
            self.status.setText(text)
            self.status.setVisible(True)

    def set_idle(self, text: str = "") -> None:
        self.status.setText(text)
        self.status.setVisible(bool(text))
        self.stop_button.setEnabled(False)
        self.tree.setEnabled(True)

    @property
    def running(self) -> bool:
        return self.stop_button.isEnabled()
