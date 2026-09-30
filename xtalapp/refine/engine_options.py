"""The energy engine's options, over the refinement workbench.

*Options...* under Energy engine used to raise the Force Field panel,
which is in the main window -- behind the workbench, so the button
looked as though it did nothing.  This window shows the panel's own
controls instead, lent by :meth:`ForceFieldDock.lend_options` and
given back when it closes: one set of controls, so With energy, a
Pareto sweep and an optimisation in the panel can never be handed
different options for the same engine.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)

from xtal.ff.registry import ENGINES
from xtalapp.widgets.tone import HINT, set_tone

NOTE = ("The same settings as the Force Field panel: a change here is "
        "a change there.")


class EngineOptionsDialog(QDialog):
    """The chosen engine's options, lent by the Force Field panel.

    Non-modal, and it follows the engine: choosing another in the
    workbench or the panel gives the first engine's controls back and
    borrows the next one's.
    """

    def __init__(self, dock, parent=None):
        super().__init__(parent)
        self.dock = dock
        self.widget = None
        self.setWindowTitle("Energy engine options")
        self.heading = QLabel("")
        self.empty = QLabel("")
        set_tone(self.empty, HINT)
        self.holder = QVBoxLayout()
        self.holder.setContentsMargins(0, 0, 0, 0)
        note = QLabel(NOTE)
        note.setWordWrap(True)
        set_tone(note, HINT)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout = QVBoxLayout(self)
        layout.addWidget(self.heading)
        layout.addLayout(self.holder)
        layout.addWidget(self.empty)
        layout.addWidget(note)
        layout.addStretch(1)
        layout.addWidget(buttons)
        dock.engine.currentIndexChanged.connect(self._follow)

    def showEvent(self, event) -> None:
        self._borrow()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        # Hidden, closed or torn down with the workbench: the panel
        # must never be left without its controls.
        self._give_back()
        super().hideEvent(event)

    def _follow(self, _index: int = 0) -> None:
        if self.isVisible():
            self._give_back()
            self._borrow()

    def _borrow(self) -> None:
        if self.widget is not None:
            return
        name = str(self.dock.engine_name())
        entry = ENGINES.get(name)
        label = entry.label if entry is not None else name
        self.heading.setText(f"<b>{label}</b>")
        self.widget = self.dock.lend_options(name)
        if self.widget is not None:
            self.holder.addWidget(self.widget)
            self.widget.setVisible(True)
        self.empty.setText("" if self.widget is not None
                           else f"{label} has no options to set.")
        self.empty.setVisible(self.widget is None)
        self.adjustSize()

    def _give_back(self) -> None:
        widget, self.widget = self.widget, None
        if widget is None:
            return
        self.holder.removeWidget(widget)
        try:
            self.dock.take_back(widget)
        except RuntimeError:            # the panel went first, at quit
            pass
