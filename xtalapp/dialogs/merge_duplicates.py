"""
xtalapp.dialogs.merge_duplicates
================================
The tolerance duplicate merging works to, made reachable.

``symmetry.merge_duplicates`` has always taken a ``tol`` and the menu
item has always called it with the default 0.05 A, which made the one
setting that decides the answer the one setting nobody could reach.
The right tolerance is a property of the *file*: a CIF that repeats an
orbit exactly needs 1e-4, and a structure refined twice against the
same data has the same atom placed 0.2 A apart in two places and needs
that.  There is no default that is right for both.

**The count travels with the number**, the way the radius factor does
in the bond-rules dialog, and for the same reason: the count is flat
over a wide range and then steps, and a tolerance set without seeing
where the step is is a guess.

**What is shown is the atom count, not the site count.**  "27 of 40
sites merge" understates it; "1188 atoms in the cell become 396" is
the number that says the formula and the density are wrong by three.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
)

from xtal.core import symmetry

# The slider sweeps; the spin box beside it sets.  The range stops at
# half an Angstrom because merging atoms further apart than that is no
# longer tidying up a file, it is editing the structure -- and a range
# wide enough to include what nobody wants leaves the part they do
# want in the first tenth of the travel.
SLIDER_STEPS = 100
TOL_MIN = 0.001
TOL_MAX = 0.5


class MergeDuplicatesDialog(QDialog):
    """Choose the tolerance, with the count of what it would merge."""

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Merge duplicate sites")
        self.document = document

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Sites of the same element that are the same atom -- "
            "including sites written as different symmetry images of "
            "it -- are merged into one.")
        intro.setWordWrap(True)
        # Word wrap alone does not stop a paragraph deciding the width
        # of the window it is in; the cap is what makes it wrap.
        intro.setMinimumWidth(430)
        intro.setMaximumWidth(430)
        layout.addWidget(intro)

        form = QFormLayout()
        self.tol = QDoubleSpinBox()
        self.tol.setDecimals(3)
        self.tol.setSingleStep(0.005)
        self.tol.setRange(TOL_MIN, TOL_MAX)
        self.tol.setSuffix(" A")
        self.tol.setValue(symmetry.DEFAULT_MERGE_TOL)
        self.tol.setToolTip(
            "Two atoms this close, once the symmetry has been applied "
            "to both, are the same atom")
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, SLIDER_STEPS)
        self.slider.setValue(
            self._to_slider(symmetry.DEFAULT_MERGE_TOL))
        self.tol.valueChanged.connect(self._on_tol)
        self.slider.valueChanged.connect(self._on_slider)

        row = QHBoxLayout()
        row.addWidget(self.tol)
        row.addWidget(self.slider, 1)
        form.addRow("Tolerance", row)
        layout.addLayout(form)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        font = self.summary.font()
        font.setBold(True)
        self.summary.setFont(font)
        layout.addWidget(self.summary)

        self.detail = QLabel()
        self.detail.setWordWrap(True)
        layout.addWidget(self.detail)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                        | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Merge")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self._preview()

    # ==================================================================
    #  PREVIEW
    # ==================================================================

    @staticmethod
    def _to_slider(value: float) -> int:
        span = TOL_MAX - TOL_MIN
        return int(round((float(value) - TOL_MIN) / span
                         * SLIDER_STEPS))

    def _on_tol(self, value: float) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(self._to_slider(value))
        self.slider.blockSignals(False)
        self._preview()

    def _on_slider(self, position: int) -> None:
        span = TOL_MAX - TOL_MIN
        self.tol.setValue(TOL_MIN + span * position / SLIDER_STEPS)

    def preview(self) -> symmetry.MergePreview:
        return self.document.preview_merge(self.tol.value())

    def _preview(self) -> None:
        plan = self.preview()
        self.summary.setText(plan.message())
        self.detail.setText(self._detail(plan))
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(bool(plan))

    @staticmethod
    def _detail(plan: symmetry.MergePreview) -> str:
        if not plan:
            return ("Nothing to merge at this tolerance. Widen it if "
                    "the same atom was refined into two places.")
        lines = [f"{plan.sites_after} independent sites remain."]
        if plan.demoted:
            # Silent otherwise, and this is the case where merging
            # changes the formula if it picks wrong.
            lines.append(
                f"{plan.demoted} of them are kept in place of a site "
                f"written earlier, because they sit on the more "
                f"special Wyckoff position.")
        return " ".join(lines)

    # ==================================================================
    #  ENTRY POINT
    # ==================================================================

    @classmethod
    def ask(cls, document, parent=None):
        """The report from the merge, or ``None`` if it was cancelled
        or there was nothing to do."""
        dialog = cls(document, parent)
        if dialog.exec() != QDialog.Accepted:
            return None
        return document.merge_duplicates(dialog.tol.value())
