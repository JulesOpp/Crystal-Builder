"""
xtalapp.actions
===============
One registry for every command in the application.

Menus, the toolbar, keyboard shortcuts and (later) context menus all
read from here, so a command is defined once and appears everywhere it
should.  Phase 4 hangs the undo stack off the same registry; phase 3
adds the interaction-mode group to it.
"""

from __future__ import annotations

from PySide6.QtGui import QAction, QActionGroup, QKeySequence


class ActionRegistry:
    """Named QActions, owned by the main window."""

    def __init__(self, parent):
        self.parent = parent
        self._actions: dict[str, QAction] = {}
        self._groups: dict[str, QActionGroup] = {}

    def add(self, name, text, slot=None, shortcut=None, checkable=False,
            checked=False, tip=None, group=None) -> QAction:
        action = QAction(text, self.parent)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.setCheckable(checkable)
        if checkable:
            action.setChecked(checked)
        if tip:
            action.setToolTip(tip)
            action.setStatusTip(tip)
        if slot is not None:
            action.triggered.connect(slot)
        if group is not None:
            action.setActionGroup(self.group(group))
        self._actions[name] = action
        return action

    def group(self, name: str) -> QActionGroup:
        if name not in self._groups:
            g = QActionGroup(self.parent)
            g.setExclusive(True)
            self._groups[name] = g
        return self._groups[name]

    def __getitem__(self, name: str) -> QAction:
        return self._actions[name]

    def __contains__(self, name: str) -> bool:
        return name in self._actions

    def get(self, name: str, default=None):
        return self._actions.get(name, default)

    def names(self) -> list[str]:
        return list(self._actions)

    def set_enabled(self, names, enabled: bool) -> None:
        for name in names:
            if name in self._actions:
                self._actions[name].setEnabled(enabled)

    def fill_menu(self, menu, names) -> None:
        """Add actions to a menu; None means a separator."""
        for name in names:
            if name is None:
                menu.addSeparator()
            else:
                menu.addAction(self._actions[name])
