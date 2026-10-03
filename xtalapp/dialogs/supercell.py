"""
xtalapp.dialogs.supercell
=========================
Building a bigger cell -- or a differently shaped one.

Two tabs, because these are two different operations that happen to
share a result type.  **Multiples** is the everyday one: 2x2x2, more
atoms, same shape.  **Transformation** takes a general integer matrix
P, which is the only way to express the cells crystallographers
actually want and cannot write as three multiples -- a primitive cell
out of a centred one (|det P| = 1), a root-2 by root-2 surface cell,
the C-centred setting of a monoclinic structure.

Both land in P1: which sites are independent is a question about a
particular cell, and it stops meaning anything the moment the cell
changes.  The count under each tab says what will come out before it
comes out, because "2x2x2 of a 648-atom framework" is a number worth
seeing first.

**The count is arithmetic, and the real preview runs only below the
soft size limit** (:mod:`xtal.core.limits`).  It used to build the
cell on every spin step, so typing 20 on MFU-4l built 2x2x2, then
20x20x20 -- 5.2 M atoms and 2.8 GB -- before anyone pressed OK.  The
spins do not track the keyboard, the count is ``n x |det P|``, and
above the hard limit OK is disabled unless the profile is Warn only.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from xtal.commands import cell as cell_commands
from xtal.core import limits
from xtalapp.dialogs.answered import answered
from xtalapp.widgets.tone import WARNING, set_tone

MAX_MULTIPLE = 20
# A general P is allowed to be this large in any one entry; beyond it
# the cell is almost certainly a typo rather than a plan.
MAX_ENTRY = 12


class SupercellDialog(QDialog):
    """na x nb x nc, or a general integer transformation."""

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Supercell")
        self.document = document
        self._command = None

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_multiples(), "Multiples")
        self.tabs.addTab(self._build_matrix(), "Transformation")
        self.tabs.currentChanged.connect(self._preview)

        self.preview = QLabel()
        self.preview.setWordWrap(True)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                        | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addWidget(self.preview)
        layout.addWidget(self.buttons)
        self._preview()

    # -- construction --------------------------------------------------

    def _build_multiples(self) -> QWidget:
        page = QWidget()
        grid = QGridLayout(page)
        self.counts = []
        for column, axis in enumerate("abc"):
            spin = QSpinBox()
            spin.setRange(1, MAX_MULTIPLE)
            spin.setValue(1)
            spin.setPrefix(f"{axis} x ")
            spin.setKeyboardTracking(False)
            spin.valueChanged.connect(self._preview)
            grid.addWidget(spin, 0, column)
            self.counts.append(spin)
        return page

    def _build_matrix(self) -> QWidget:
        page = QWidget()
        grid = QGridLayout(page)
        grid.addWidget(QLabel(
            "New a, b, c as integer combinations of the old ones"),
            0, 0, 1, 3)
        self.matrix = []
        for row in range(3):
            entries = []
            for column in range(3):
                spin = QSpinBox()
                spin.setRange(-MAX_ENTRY, MAX_ENTRY)
                spin.setValue(1 if row == column else 0)
                spin.setKeyboardTracking(False)
                spin.valueChanged.connect(self._preview)
                grid.addWidget(spin, row + 1, column)
                entries.append(spin)
            self.matrix.append(entries)
        return page

    # -- values --------------------------------------------------------

    def multiples(self) -> tuple[int, int, int]:
        return tuple(spin.value() for spin in self.counts)

    def p_matrix(self) -> np.ndarray:
        return np.array([[spin.value() for spin in row]
                         for row in self.matrix], dtype=float)

    def command(self):
        """The command for what is shown -- the one the preview ran,
        while it still is, so OK does not build the cell twice."""
        key = self._key()
        if self._command is None or self._command[0] != key:
            if self.tabs.currentIndex() == 0:
                command = cell_commands.Supercell(*self.multiples())
            else:
                command = cell_commands.TransformCell(self.p_matrix())
            self._command = (key, command)
        return self._command[1]

    def _key(self) -> tuple:
        if self.tabs.currentIndex() == 0:
            return (0, self.multiples())
        return (1, tuple(self.p_matrix().ravel()))

    def _p(self):
        if self.tabs.currentIndex() == 0:
            return self.multiples()
        return self.p_matrix()

    # -- preview -------------------------------------------------------

    def _preview(self, *_args) -> None:
        ok_button = self.buttons.button(QDialogButtonBox.Ok)
        n = self.document.cell.n_atoms
        verdict = limits.check_supercell(n, self._p())
        if verdict.warned:
            # Counted, not built: building it is what this is for.
            self.preview.setText(f"{verdict.sentence[0].upper()}"
                                 f"{verdict.sentence[1:]}.")
            set_tone(self.preview, WARNING)
            ok_button.setEnabled(not verdict.refused)
            return
        try:
            _new, report = self.command().preview(
                self.document.structure)
        except (ValueError, np.linalg.LinAlgError) as exc:
            self.preview.setText(str(exc))
            set_tone(self.preview, WARNING)
            ok_button.setEnabled(False)
            return
        self.preview.setText(report.message)
        set_tone(self.preview, None)
        ok_button.setEnabled(True)

    # -- running -------------------------------------------------------

    @classmethod
    def ask(cls, document, parent=None):
        with answered(cls(document, parent)) as dialog:
            if dialog.exec() != QDialog.Accepted:
                return None
            return document.operate(dialog.command())
