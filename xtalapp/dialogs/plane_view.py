"""
xtalapp.dialogs.plane_view
==========================
View ▸ Along (hkl)...: look straight onto a lattice plane.

The camera goes along the plane's normal, ``h a* + k b* + l c*``
(:meth:`xtal.core.lattice.Lattice.plane_normal`), which outside an
orthogonal cell is not the direction [hkl]: (100) of quartz is thirty
degrees off a.  The dialog stays open and keeps its index, because
the use is stepping through (100), (110), (111) and comparing; Look
acts on whichever tab is in front when it is pressed, never the one
the dialog was opened over.  Nothing here touches the document -- a
camera is not an edit.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from xtalapp.widgets.tone import WARNING, set_tone

#: The largest Miller index offered, as for a slab: past it the
#: planes are closer together than anything in the picture shows.
MAX_INDEX = 12


class PlaneViewDialog(QDialog):
    """Three indices and a Look button that leaves the dialog open."""

    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle("View along (hkl)")
        self.setModal(False)
        self._window = window

        row = QHBoxLayout()
        self.indices = []
        for name, value in zip("hkl", (0, 0, 1), strict=True):
            spin = QSpinBox()
            spin.setRange(-MAX_INDEX, MAX_INDEX)
            spin.setValue(value)
            spin.setPrefix(f"{name} ")
            spin.valueChanged.connect(self._check)
            row.addWidget(spin)
            self.indices.append(spin)
        form = QFormLayout()
        form.addRow("Plane (hkl)", row)

        self.hint = QLabel("(0 0 0) is not a plane.")
        set_tone(self.hint, WARNING)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.close)
        # Close can never be the default: in the real window the box
        # handed it Return, so typing an index and pressing Return
        # shut the dialog instead of turning the view.
        buttons.button(QDialogButtonBox.Close).setAutoDefault(False)
        # An action role, not accept: accepting would close the dialog,
        # and Return is meant to look and stay.
        self.look_button = QPushButton("Look")
        self.look_button.setToolTip(
            "Turn the view in front onto these planes, along their "
            "normal")
        self.look_button.clicked.connect(self.look)
        buttons.addButton(self.look_button, QDialogButtonBox.ActionRole)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.hint)
        layout.addWidget(buttons)
        self._check()

    def showEvent(self, event) -> None:
        # Set here and not in the constructor: a default is honoured
        # only for a button already inside its dialog, and showing
        # reassigns it.
        super().showEvent(event)
        self.look_button.setDefault(True)

    def hkl(self) -> tuple[int, int, int]:
        return tuple(spin.value() for spin in self.indices)

    def look(self) -> None:
        if any(self.hkl()):
            self._window.look_along_plane(self.hkl())

    def _check(self, *_args) -> None:
        ok = any(self.hkl())
        self.look_button.setEnabled(ok)
        self.hint.setHidden(ok)
