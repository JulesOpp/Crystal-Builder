"""
xtalapp.docks.move
==================
Moving the selection: translate, rotate, mirror, flatten.

Rotation and mirroring are done in cartesian space, because that is the
only space in which they are rigid -- rotating fractional coordinates
in a non-orthogonal cell shears the fragment rather than turning it.
Translation is offered in both, since "shift by half a cell" and "shift
by 1.5 A" are both things people mean.

Every button here runs a command, so everything undoes; repeated nudges
merge into one undo step while the gesture continues.

The arrows are the point of the dock rather than a decoration on it.
Typing a number and pressing Apply is how the tool is *specified*;
holding an arrow and watching the fragment slide is how it is used, and
a burst of forty nudges has to come back on one Ctrl+Z or the undo
stack is useless afterwards.  ``MoveSites`` and ``TransformSites``
merge while the button is down, and the merge window is closed when it
comes up -- see :meth:`MoveDock._end_gesture`.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# A held arrow repeats at this rate, after this delay.  Slow enough
# that one press is one step, fast enough that holding it reads as a
# slide rather than a stutter.
REPEAT_DELAY_MS = 350
REPEAT_INTERVAL_MS = 60

AXES = {
    "a": None, "b": None, "c": None,          # lattice vectors
    "x": (1.0, 0.0, 0.0),
    "y": (0.0, 1.0, 0.0),
    "z": (0.0, 0.0, 1.0),
}


class MoveDock(QDockWidget):
    """Numeric transformations of the current selection."""

    #: What an edit did, for the status bar.  Make planar in
    #: particular has to say how far it moved things -- "moved by up to
    #: 0.08 A" is a fix and "0.8 A" is a silent corruption, and the
    #: picture afterwards looks the same either way.
    statusMessage = Signal(str)

    def __init__(self, parent=None):
        super().__init__("Move", parent)
        self.setObjectName("MoveDock")
        self.document = None

        self.summary = QLabel("Nothing selected")
        self.summary.setWordWrap(True)

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(self.summary)
        layout.addWidget(self._build_translate())
        layout.addWidget(self._build_rotate())
        layout.addWidget(self._build_mirror())
        layout.addStretch(1)

        container = QWidget()
        container.setLayout(layout)
        self.setWidget(container)
        self.set_document(None)

    # -- construction --------------------------------------------------

    def _build_translate(self) -> QGroupBox:
        box = QGroupBox("Translate")
        self.units = QComboBox()
        self.units.addItems(["fractional", "cartesian (A)"])

        self.steps = []
        self.nudges = []
        grid = QGridLayout()
        grid.addWidget(self.units, 0, 0, 1, 3)
        for column, axis in enumerate("xyz"):
            spin = QDoubleSpinBox()
            spin.setRange(-99.0, 99.0)
            spin.setDecimals(4)
            spin.setSingleStep(0.05)
            spin.setValue(0.0)
            spin.setPrefix(f"{axis} ")
            grid.addWidget(spin, 1, column)
            self.steps.append(spin)
            # One step per click, repeating while held.  The step is
            # the spinbox above, so the arrows add no new quantity to
            # keep track of -- they are pure acceleration.
            arrows = QHBoxLayout()
            for glyph, sign in (("\u2212", -1.0), ("+", 1.0)):
                button = self._arrow(
                    glyph,
                    lambda a=column, s=sign: self.nudge(a, s),
                    f"Move by the {axis} step, and keep moving while "
                    f"held")
                arrows.addWidget(button)
                self.nudges.append(button)
            grid.addLayout(arrows, 2, column)

        # Both buttons go through a lambda: QPushButton.clicked carries
        # a `checked` flag, and connecting `translate` to it directly
        # hands that False in as the sign -- so every translation is
        # multiplied by zero and Apply silently does nothing.
        apply_button = QPushButton("Apply")
        apply_button.clicked.connect(
            lambda: self.translate(sign=1.0))
        back_button = QPushButton("Apply -")
        back_button.setToolTip("Translate by the negative of the step")
        back_button.clicked.connect(
            lambda: self.translate(sign=-1.0))
        buttons = QHBoxLayout()
        buttons.addWidget(apply_button)
        buttons.addWidget(back_button)

        inner = QVBoxLayout(box)
        inner.addLayout(grid)
        inner.addLayout(buttons)
        return box

    def _build_rotate(self) -> QGroupBox:
        box = QGroupBox("Rotate")
        self.rotation_axis = QComboBox()
        self.rotation_axis.addItems(list(AXES))
        self.angle = QDoubleSpinBox()
        self.angle.setRange(-360.0, 360.0)
        self.angle.setDecimals(2)
        self.angle.setValue(90.0)
        self.angle.setSuffix(" deg")
        self.rotation_centre = QComboBox()
        self.rotation_centre.addItems(["selection centre",
                                       "cell origin"])
        apply_button = QPushButton("Apply")
        apply_button.clicked.connect(lambda: self.rotate())

        spin_arrows = QHBoxLayout()
        for glyph, sign in (("\u21ba", -1.0), ("\u21bb", 1.0)):
            button = self._arrow(
                glyph, lambda s=sign: self.nudge_rotation(s),
                "Turn by the angle above, and keep turning while held")
            spin_arrows.addWidget(button)
            self.nudges.append(button)

        grid = QGridLayout(box)
        grid.addWidget(QLabel("axis"), 0, 0)
        grid.addWidget(self.rotation_axis, 0, 1)
        grid.addWidget(QLabel("angle"), 1, 0)
        grid.addWidget(self.angle, 1, 1)
        grid.addLayout(spin_arrows, 2, 1)
        grid.addWidget(QLabel("about"), 3, 0)
        grid.addWidget(self.rotation_centre, 3, 1)
        grid.addWidget(apply_button, 4, 0, 1, 2)
        return box

    def _build_mirror(self) -> QGroupBox:
        box = QGroupBox("Reflect and flatten")
        self.mirror_axis = QComboBox()
        self.mirror_axis.addItems(list(AXES))
        apply_button = QPushButton("Mirror")
        apply_button.clicked.connect(lambda: self.mirror())
        row = QHBoxLayout()
        row.addWidget(QLabel("normal"))
        row.addWidget(self.mirror_axis, 1)
        row.addWidget(apply_button)

        self.planar_button = QPushButton("Make planar")
        self.planar_button.setToolTip(
            "Flatten the selection onto its best-fit plane -- for a "
            "ring that came out of a builder slightly puckered")
        self.planar_button.clicked.connect(lambda: self.planarize())

        inner = QVBoxLayout(box)
        inner.addLayout(row)
        inner.addWidget(self.planar_button)
        return box

    def _arrow(self, glyph: str, slot, tip: str) -> QToolButton:
        """A button that fires once on click and repeats while held.

        The release is wired as well as the press: it is what closes
        the merge window, so a burst of nudges is one undo step and the
        *next* burst is a different one.
        """
        button = QToolButton()
        button.setText(glyph)
        button.setToolTip(tip)
        button.setAutoRepeat(True)
        button.setAutoRepeatDelay(REPEAT_DELAY_MS)
        button.setAutoRepeatInterval(REPEAT_INTERVAL_MS)
        button.clicked.connect(lambda _checked=False: self._nudged(slot))
        button.released.connect(self._end_gesture)
        return button

    def _nudged(self, slot) -> str:
        message = slot()
        if message:
            self.statusMessage.emit(message)
        return message

    def _end_gesture(self) -> None:
        """The arrow came up: stop merging into that undo step."""
        if self.document is not None:
            self.document.break_merge()

    # -- binding -------------------------------------------------------

    def set_document(self, document) -> None:
        self.document = document
        self.refresh()

    def refresh(self) -> None:
        document = self.document
        enabled = (document is not None
                   and bool(document.selection.atoms))
        self.widget().setEnabled(document is not None)
        if not enabled:
            self.summary.setText("Nothing selected")
            return
        text = document.selection_orbit_report()
        if not document.selection_is_orbit_complete():
            text += " — the whole orbit moves"
        self.summary.setText(text)

    # -- actions -------------------------------------------------------

    def _axis_vector(self, name: str) -> np.ndarray:
        fixed = AXES[name]
        if fixed is not None:
            return np.array(fixed, dtype=float)
        index = "abc".index(name)
        return np.array(self.document.structure.lattice.matrix[index])

    def translate(self, sign: float = 1.0) -> str:
        if self.document is None or not self.document.selection.atoms:
            return ""
        delta = np.array([spin.value() for spin in self.steps]) * sign
        if not np.any(delta):
            return ""
        cartesian = self.units.currentIndex() == 1
        return self.document.move_selection(delta, cartesian=cartesian)

    def rotate(self) -> str:
        if self.document is None or not self.document.selection.atoms:
            return ""
        axis = self._axis_vector(self.rotation_axis.currentText())
        centre = (None if self.rotation_centre.currentIndex() == 0
                  else np.zeros(3))
        return self.document.rotate_selection(axis, self.angle.value(),
                                              centre)

    def mirror(self) -> str:
        if self.document is None or not self.document.selection.atoms:
            return ""
        normal = self._axis_vector(self.mirror_axis.currentText())
        return self.document.mirror_selection(normal)

    def planarize(self) -> str:
        if self.document is None or not self.document.selection.atoms:
            return ""
        message = self.document.planarize_selection()
        if message:
            self.statusMessage.emit(message)
        return message

    def nudge(self, axis: int, sign: float = 1.0) -> str:
        """One step along one axis, from that axis's spinbox."""
        if self.document is None or not self.document.selection.atoms:
            return ""
        step = self.steps[axis].value()
        if not step:
            return ""
        delta = np.zeros(3)
        delta[axis] = step * sign
        cartesian = self.units.currentIndex() == 1
        return self.document.move_selection(delta, cartesian=cartesian)

    def nudge_rotation(self, sign: float = 1.0) -> str:
        """One step of rotation about the chosen axis."""
        if self.document is None or not self.document.selection.atoms:
            return ""
        angle = self.angle.value() * sign
        if not angle:
            return ""
        axis = self._axis_vector(self.rotation_axis.currentText())
        centre = (None if self.rotation_centre.currentIndex() == 0
                  else np.zeros(3))
        return self.document.rotate_selection(axis, angle, centre)
