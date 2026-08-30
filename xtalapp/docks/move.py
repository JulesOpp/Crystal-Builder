"""
xtalapp.docks.move
==================
Moving the selection: translate, rotate, mirror.

Rotation and mirroring are done in cartesian space, because that is the
only space in which they are rigid -- rotating fractional coordinates
in a non-orthogonal cell shears the fragment rather than turning it.
Translation is offered in both, since "shift by half a cell" and "shift
by 1.5 A" are both things people mean.

Every button here runs a command, so everything undoes; repeated nudges
merge into one undo step while the gesture continues.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

AXES = {
    "a": None, "b": None, "c": None,          # lattice vectors
    "x": (1.0, 0.0, 0.0),
    "y": (0.0, 1.0, 0.0),
    "z": (0.0, 0.0, 1.0),
}


class MoveDock(QDockWidget):
    """Numeric transformations of the current selection."""

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

        grid = QGridLayout(box)
        grid.addWidget(QLabel("axis"), 0, 0)
        grid.addWidget(self.rotation_axis, 0, 1)
        grid.addWidget(QLabel("angle"), 1, 0)
        grid.addWidget(self.angle, 1, 1)
        grid.addWidget(QLabel("about"), 2, 0)
        grid.addWidget(self.rotation_centre, 2, 1)
        grid.addWidget(apply_button, 3, 0, 1, 2)
        return box

    def _build_mirror(self) -> QGroupBox:
        box = QGroupBox("Mirror")
        self.mirror_axis = QComboBox()
        self.mirror_axis.addItems(list(AXES))
        apply_button = QPushButton("Apply")
        apply_button.clicked.connect(lambda: self.mirror())
        inner = QHBoxLayout(box)
        inner.addWidget(QLabel("normal"))
        inner.addWidget(self.mirror_axis, 1)
        inner.addWidget(apply_button)
        return box

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
