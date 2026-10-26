"""
xtalapp.widgets.choices
=======================
Greying one entry of a combo box, and asking whether it is.

The way every example shows -- ``combo.model().item(at)`` and
``setEnabled`` on it -- broke the workspace menu.  PySide has the
model keep the wrapper ``item()`` returns, and an entry Qt made with
``addItem`` cannot tell shiboken when it is freed, so after
``combo.clear()`` the freed address still maps to that wrapper.  The
next object Qt makes there and hands to Python comes back as the old
QStandardItem: in CI a QAction from ``menu.addAction(text, callable)``
(*no attribute 'connect'*), and in a probe a combo's whole model.

**So an entry is never taken as an item.**  Its flags are written as
data, in the role ``QStandardItem.setFlags`` itself writes them to,
and read back with ``model.flags``: nothing is wrapped, so there is
nothing to strand.  ``tests/test_combo_choices.py`` holds that the
role still greys the entry.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import QComboBox

#: Where ``QStandardItem`` keeps its flags (``qstandarditemmodel.cpp``).
_FLAGS_ROLE = Qt.ItemDataRole.UserRole - 1


def set_choice_enabled(combo: QComboBox, at: int, enabled: bool) -> None:
    """Grey entry *at* of *combo*, or make it choosable again."""
    model = combo.model()
    if not isinstance(model, QStandardItemModel):
        return
    flags = model.flags(model.index(at, combo.modelColumn()))
    if enabled:
        flags |= Qt.ItemFlag.ItemIsEnabled
    else:
        flags &= ~Qt.ItemFlag.ItemIsEnabled
    combo.setItemData(at, flags, _FLAGS_ROLE)


def choice_enabled(combo: QComboBox, at: int) -> bool:
    """Whether entry *at* of *combo* can be chosen."""
    model = combo.model()
    return bool(model.flags(model.index(at, combo.modelColumn()))
                & Qt.ItemFlag.ItemIsEnabled)
