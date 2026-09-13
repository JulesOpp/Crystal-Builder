"""
xtalapp.docks.net
=================
The net panel: what the net you drew is called.

Drawing a net is a chemist's decision about which parts of a framework
are nodes and which are linkers, and the reason for making it is to
find out what the answer is.  This is where the answer appears --
**pcu**, and the coordination sequence and point symbol RCSR names it
by underneath, because a name with no evidence for it is not worth
much more than no name at all.

**It refreshes on a change to the bonds, and only while it is on
screen.**  Identification walks ten shells of an infinite graph and
searches for the smallest ring at every angle of every vertex.  Two
things keep that off the critical path: a cell edit, a relaxation and
a change of setting all leave the net alone -- which is the whole
point of a net -- so none of them recompute anything; and a panel
nobody has opened does not compute at all, it remembers that it is
stale and catches up when it is shown.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from xtal.core.structure import CHEMISTRY

#: What the panel says before anything has been drawn.  It names the
#: mode rather than the absence, because "nothing here" is a dead end
#: and "Draw net" is the next thing to do.
EMPTY = ("No net has been drawn.\n\n"
         "Pick Draw net in the toolbar and click two atoms to draw an "
         "edge.  It expands over the symmetry orbit, so one edge of a "
         "pcu net draws all six.")


class NetDock(QDockWidget):
    """The identification of the net in the active document."""

    statusMessage = Signal(str)
    #: Export the net for Systre.  The window owns the save dialog and
    #: the workspace refresh, so the panel only asks.
    exportRequested = Signal()

    def __init__(self, parent=None):
        super().__init__("Net", parent)
        self.setObjectName("NetDock")
        self._document = None
        #: Set when the net changed while the panel was closed.  The
        #: panel is not in the default layout, so for most users this
        #: is always true and nothing is ever computed.
        self._stale = True

        self.name = QLabel()
        self.name.setWordWrap(True)
        font = self.name.font()
        font.setPointSize(font.pointSize() + 6)
        font.setBold(True)
        self.name.setFont(font)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        # A coordination sequence is a row of numbers that only reads
        # as one when the digits line up.
        self.text.setLineWrapMode(QPlainTextEdit.NoWrap)
        mono = QFont("Menlo")
        mono.setStyleHint(QFont.Monospace)
        mono.setPointSize(11)
        self.text.setFont(mono)
        self.text.setMinimumWidth(380)

        self.copy = QPushButton("Copy")
        self.copy.setToolTip("Copy the identification to the clipboard")
        self.copy.clicked.connect(self._on_copy)

        # Beside the name it doubts: the reason to write the file is
        # to check this panel's answer against Systre's.
        self.export = QPushButton("Export for Systre...")
        self.export.setToolTip(
            "Save the net as a .cgd file that Systre can name, for a "
            "second opinion that does not come from this panel")
        self.export.clicked.connect(self.exportRequested)

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(self.name)
        layout.addWidget(self.text, 1)
        buttons = QHBoxLayout()
        buttons.addWidget(self.copy)
        buttons.addWidget(self.export)
        layout.addLayout(buttons)

        container = QWidget()
        container.setLayout(layout)
        self.setWidget(container)
        self.show_document(None)

    # ------------------------------------------------------------ wiring

    def set_document(self, document) -> None:
        self._document = document
        self._refresh()

    def on_structure_changed(self, change: int) -> None:
        """Refresh only when the bonds changed.

        ``CHEMISTRY`` is the same flag the bond graph and the net graph
        are cached against, so this asks exactly the question the cache
        asks and no other change reaches the expensive path.
        """
        if change & CHEMISTRY:
            self._refresh()

    def showEvent(self, event) -> None:      # noqa: N802  (Qt's name)
        """Catch up on whatever happened while nobody was looking."""
        super().showEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        if not self.isVisible():
            self._stale = True
            return
        self._stale = False
        self.show_document(self._document)

    def show_document(self, document) -> None:
        self._document = document
        if document is None:
            self.name.setText("")
            self.text.setPlainText("No structure open.")
            self.copy.setEnabled(False)
            self.export.setEnabled(False)
            return
        net = document.net()
        if net.is_empty():
            self.name.setText("")
            self.text.setPlainText(EMPTY)
            self.copy.setEnabled(False)
            self.export.setEnabled(False)
            return
        report = document.net_identification()
        self.name.setText(report.headline())
        self.text.setPlainText("\n".join(
            report.lines()[1:] + ["", _drawn(net)]).strip())
        self.copy.setEnabled(True)
        self.export.setEnabled(True)

    def _on_copy(self) -> None:
        from PySide6.QtWidgets import QApplication

        text = f"{self.name.text()}\n{self.text.toPlainText()}".strip()
        QApplication.clipboard().setText(text)
        self.statusMessage.emit("net identification copied")


def _drawn(net) -> str:
    """How much of the cell the net actually is.

    Worth saying next to the name: a **pcu** found on eight vertices
    and twenty-four edges is the same net RCSR draws with one and
    three, and seeing both numbers is what makes that believable
    rather than surprising.
    """
    vertices = sum(1 for v in range(net.n_vertices) if net.degree(v))
    return (f"{vertices} vertices and {len(net.edges)} edges drawn "
            f"in the cell")
