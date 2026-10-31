"""
xtalapp.widgets.agent_strip
===========================
One line under the notice bar: what the AI assistant last changed in
this tab, and a way to take it back.

The bursts are read off the tab's own history
(:mod:`xtal.agent.changes`), so the strip can never list a change Undo
would not take back, nor revert more than it said: the plan is the
history's, and Revert runs it through ``Document.undo``.  Its own bar
rather than the notice bar's, so an autosave offer and the assistant's
last change never hide each other.  Shown only while an assistant can
be connected and this tab has something of the assistant's.
"""

from __future__ import annotations

import time
import weakref

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QPainter
from PySide6.QtGui import Qt as GuiQt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QToolButton,
)

from xtal.agent import changes
from xtalapp import menus
from xtalapp.widgets import tone

HELD = "a calculation or a trajectory holds this tab"


def _menu_text(text: str) -> str:
    """``text`` as a menu shows it literally: an ``&`` in the
    assistant's label would otherwise be eaten as a mnemonic."""
    return text.replace("&", "&&")


def _also(burst) -> str:
    """What else reverting ``burst`` takes, as its button says it:
    later bursts of the assistant's, then the person's own edits."""
    said = []
    if burst.bursts_after:
        later = burst.bursts_after
        said.append(f"and {later} later assistant "
                    f"change{'s' if later > 1 else ''}")
    if burst.person_after:
        said.append(f"also undoes {burst.person_after} of yours")
    return f" ({'; '.join(said)})" if said else ""


class _OneLine(QLabel):
    """A label that stays one line and is elided to its width when it
    paints, whatever the width is then.

    Elided at paint time rather than by ``setText``, so ``text()`` is
    the whole sentence (the tooltip and a screen reader get it, and an
    elision worked out before the strip is laid out is never kept), and
    ignored for its width by the layout, so a long label never holds
    the central column open.

    Plain text throughout, label and tooltip: the line holds the
    assistant's own words, which are not markup."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWordWrap(False)
        self.setTextFormat(Qt.PlainText)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def setText(self, text: str) -> None:
        super().setText(text)
        self.setToolTip(GuiQt.convertFromPlainText(text))

    def paintEvent(self, _event) -> None:
        rect = self.contentsRect()
        shown = self.fontMetrics().elidedText(self.text(), Qt.ElideRight,
                                              rect.width())
        painter = QPainter(self)
        self.style().drawItemText(painter, rect, self.alignment(),
                                  self.palette(), self.isEnabled(), shown,
                                  self.foregroundRole())


class AgentStrip(QFrame):
    """The assistant's latest burst in this tab, Revert / Restore, and
    every burst in History."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.setObjectName("AgentStrip")
        self.setFrameShape(QFrame.StyledPanel)
        self.window = window
        self.label = _OneLine()
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.action_button = QPushButton("Revert")
        self.action_button.setAutoDefault(False)
        self.action_button.clicked.connect(self._act)
        self.history_button = QToolButton()
        self.history_button.setText("History ▾")
        self.history_button.setAutoRaise(True)
        self.history_button.clicked.connect(self._show_history)
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 2, 4, 2)
        row.addWidget(self.label, 1)
        row.addWidget(self.action_button)
        row.addWidget(self.history_button)
        tone.set_tone(self.label, tone.HINT)
        self._document = None
        # What a Revert here took back in each tab, while Restore can
        # still bring exactly that back: (label, the commands it
        # undid, as Redo holds them, weakly -- an edit since drops
        # them from Redo, and the strip must not be what keeps a
        # crystal's copy).  The strip's own and not
        # ``restore_plan``'s, which brings back the burst alone -- a
        # Revert that also took later steps must give them back too.
        # Kept per document, so looking at another tab and back is
        # not what loses the way back; weakly, so a closed tab goes.
        self._reverts: weakref.WeakKeyDictionary = \
            weakref.WeakKeyDictionary()
        # The History menu last raised: unparented and replaced, so
        # raising it again does not pile menus up under the strip.
        self._history: QMenu | None = None
        self.hide()

    @property
    def _reverted(self) -> tuple[str, tuple] | None:
        if self._document is None:
            return None
        return self._reverts.get(self._document)

    @_reverted.setter
    def _reverted(self, value) -> None:
        if self._document is None:
            return
        if value is None:
            self._reverts.pop(self._document, None)
        else:
            self._reverts[self._document] = value

    # -- following the window --------------------------------------------

    def follow(self, document) -> None:
        """Show ``document``'s bursts (``None``: no tab)."""
        if document is self._document:
            # The window rebinds on more than a tab change; forgetting
            # the Revert then would lose the way back to it.
            self.refresh()
            return
        if self._document is not None:
            for signal in self._signals(self._document):
                try:
                    signal.disconnect(self.refresh)
                except (RuntimeError, TypeError):
                    pass
        self._document = document
        if document is not None:
            for signal in self._signals(document):
                signal.connect(self.refresh)
        self.refresh()

    @staticmethod
    def _signals(document) -> tuple:
        """What changes the line or greys its button: the history,
        and a hold or a playback, either of which refuses undo."""
        return (document.historyChanged, document.heldChanged,
                document.playbackChanged)

    def _serving(self) -> bool:
        # Asked of the window's one server, made if need be: it is
        # made unstarted, and its token is then the one it keeps.
        return self.window.ensure_agent_server().running

    def _restorable(self) -> bool:
        """Whether the top of Redo is still exactly what the strip's
        Revert took, the same commands in the same order.

        Counted, it was not: one more Ctrl+Z puts an older step on
        top, and redoing as many would bring that back and leave the
        newest behind.  An edit since clears Redo, and a redo from
        Edit spends it, and both end it the same way."""
        if self._reverted is None:
            return False
        taken = self._reverted[1]
        top = self._document.stack.undone()[-len(taken):]
        return len(top) == len(taken) and all(
            a is b() for a, b in zip(top, taken, strict=True))

    def refresh(self, *_args) -> None:
        document = self._document
        if document is None or not self._serving():
            self.hide()
            return
        busy = document.is_busy
        if self._restorable():
            self._show(f"Reverted '{self._reverted[0]}'", "Restore",
                       HELD if busy else "")
            return
        self._reverted = None
        found = changes.bursts(document.stack)
        if not found:
            self.hide()
            return
        latest = found[0]
        when = time.strftime("%H:%M", time.localtime(latest.started))
        steps = "1 step" if latest.steps == 1 else f"{latest.steps} steps"
        # The request first: a narrow column elides from the right.
        text = f"{latest.label} · {steps} by the assistant · {when}"
        button = "Revert"
        if latest.person_after:
            button += f" (also undoes {latest.person_after} of yours)"
        self._show(text, button, HELD if busy else latest.reason)

    def _show(self, text: str, button: str, reason: str) -> None:
        self.label.setText(text)
        self.action_button.setText(button)
        self.action_button.setEnabled(not reason)
        self.action_button.setToolTip(reason)
        self.show()

    # -- acting -----------------------------------------------------------

    def _act(self) -> None:
        if self._restorable():
            self.restore()
            return
        found = changes.bursts(self._document.stack)
        if found:
            self.revert(found[0].number)

    def revert(self, number: int) -> None:
        """Undo back to just before burst ``number``, as one gesture."""
        document = self._document
        if document is None or document.is_busy:
            return
        plan = changes.revert_plan(document.stack, number)
        if not isinstance(plan, int):
            return
        label = next(b.label for b in changes.bursts(document.stack)
                     if b.number == number)
        for _ in range(plan):
            document.undo()
        self._reverted = (label, tuple(
            weakref.ref(c) for c in document.stack.undone()[-plan:]))
        self.refresh()

    def restore(self) -> None:
        """Redo exactly what the last Revert here took back."""
        document = self._document
        if document is None or document.is_busy \
                or self._reverted is None:
            return
        restorable = self._restorable()
        count = len(self._reverted[1])
        self._reverted = None
        if restorable:
            for _ in range(count):
                document.redo()
        else:
            self.window.show_message(
                f"Nothing was restored: {changes.REPLACED}")
        self.refresh()

    # -- history ----------------------------------------------------------

    def history_menu(self) -> QMenu:
        """Every burst, to revert or restore; unparented, so the
        caller owns it."""
        menu = QMenu()
        # A greyed entry's reason is its tooltip, which a menu hides.
        menu.setToolTipsVisible(True)
        if self._document is None:
            return menu
        stack = self._document.stack
        busy = self._document.is_busy
        for burst in changes.bursts(stack):
            text = _menu_text(burst.label) + _also(burst)
            if burst.applied == "none":
                action = menu.addAction(f"Restore: {text}")
                action.triggered.connect(
                    lambda _=False, n=burst.number: self._restore_burst(n))
                plan = changes.restore_plan(stack, burst.number)
                reason = HELD if busy else (
                    "" if isinstance(plan, int) else plan)
            else:
                action = menu.addAction(f"Revert: {text}")
                action.triggered.connect(
                    lambda _=False, n=burst.number: self.revert(n))
                reason = HELD if busy else burst.reason
            action.setEnabled(not reason)
            action.setToolTip(reason)
        return menu

    def _restore_burst(self, number: int) -> None:
        """Bring back burst ``number`` and what Redo passes on the
        way, never what came after it."""
        document = self._document
        if document is None or document.is_busy:
            return
        plan = changes.restore_plan(document.stack, number)
        if isinstance(plan, int):
            for _ in range(plan):
                document.redo()
        self.refresh()

    def _show_history(self) -> None:
        self._history = self.history_menu()
        menus.popup(self._history, self.history_button.mapToGlobal(
            QPoint(0, self.history_button.height())))
