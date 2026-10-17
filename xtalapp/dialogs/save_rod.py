"""
xtalapp.dialogs.save_rod
========================
A rod out of the crystal in front, into the workspace's blocks for the
rod builder.

**The rod is cut from a prepared copy by default.**  A deposited file
is rarely a rod's atoms as they are: a ConQuest export writes symmetry
copies as sites, and a walk through Ni2Cl2BTDD's 1152 atoms on 378
places finds no rod.  The copy is the one Structure > Prepare for
simulation would make, and the tab is not changed; an already prepared
crystal can be cut as it is.

**The shape of the points of extension is asked, because no one rule
gives it** (the rod track's E0): the relative-neighbourhood graph gives
MIL-53's sra and Ni2Cl2BTDD's etb, MOF-74's msf needs its first five
shells.  The footer says what the rod came to -- cut once, into a
scratch folder, by the same :func:`xtal.mof.rod.save_block` the Save
button runs -- so a rod this dialog accepts is one the builder reads.

It goes to ``rods/`` under :attr:`xtal.workspace.Workspace.blocks`,
with its linker beside it, and the rod builder lists it from then on.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from xtal.mof import rod
from xtal.workspace import safe_name
from xtalapp.dialogs.answered import answered
from xtalapp.widgets.tone import HINT, WARNING, set_tone

#: The shapes offered, as :func:`xtal.mof.rod.from_structure` takes
#: them.
SHAPES = (("rng", "Relative neighbourhood (MIL-53, Ni2Cl2BTDD)"),
          ("shells", "The first shells (MOF-74: 5)"),
          ("within", "Every pair within"))


class SaveRodDialog(QDialog):
    """Name the rod, say how its points of extension join, and be told
    what it came to."""

    def __init__(self, structure, folder, seed=None, parent=None):
        super().__init__(parent)
        self.structure = structure
        self.folder = Path(folder)
        self.seed = seed
        self.setWindowTitle("Save rod as a block")

        self.name = QLineEdit(_suggested(structure), self)
        self.name.setPlaceholderText(
            "the file name, which is its name in the rod builder")
        self.name.textChanged.connect(self._named)
        self.prepared = QCheckBox("Cut from a prepared copy", self)
        self.prepared.setChecked(True)
        self.prepared.setToolTip(
            "Merge sites written twice, order the disorder and take "
            "out the solvent on a copy first, as Prepare for "
            "simulation does.  The tab is not changed.")
        self.prepared.toggled.connect(self._refresh)
        self.shape = QComboBox(self)
        for value, label in SHAPES:
            self.shape.addItem(label, value)
        self.shape.setToolTip(
            "Which points of extension along the rod are joined in its "
            "net.  It decides the net a build reads back as, and is "
            "written into the file once.")
        self.shells = QSpinBox(self)
        self.shells.setRange(1, 12)
        self.shells.setValue(5)
        self.within = QDoubleSpinBox(self)
        self.within.setRange(1.0, 12.0)
        self.within.setDecimals(2)
        self.within.setSingleStep(0.1)
        self.within.setValue(4.5)
        self.within.setSuffix(" A")
        for widget in (self.shells, self.within):
            widget.valueChanged.connect(self._refresh)
        self.shape.currentIndexChanged.connect(self._refresh)
        shape_row = QWidget(self)
        row = QHBoxLayout(shape_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.shape, 1)
        row.addWidget(self.shells)
        row.addWidget(self.within)

        self.summary = QLabel(self)
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.RichText)

        form = QFormLayout()
        form.addRow("Name", self.name)
        form.addRow("", self.prepared)
        form.addRow("Points joined", shape_row)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                   | QDialogButtonBox.Cancel)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)
        self.ok_button.setText("Save")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.summary)
        layout.addWidget(buttons)
        self.resize(520, 220)
        self._cut: rod.Saved | None = None
        self._problem = ""
        self._refresh()

    def shape_value(self):
        """What ``shape=`` is: ``"rng"``, a count, or a distance."""
        kind = self.shape.currentData()
        if kind == "shells":
            return int(self.shells.value())
        if kind == "within":
            return float(self.within.value())
        return "rng"

    def values(self) -> dict:
        return {"name": safe_name(self.name.text(), "rod"),
                "shape": self.shape_value(),
                "prepared": self.prepared.isChecked(),
                "seed": self.seed}

    def problem(self) -> str:
        """Why this cannot be saved, or ``""``."""
        if not self.name.text().strip():
            return "it needs a name -- that is what the rod builder " \
                   "will list"
        name = self.values()["name"]
        if name in rod.shipped():
            return f"{name} is a shipped rod's name: call this one " \
                   f"something else"
        return self._problem

    def _refresh(self, *_args) -> None:
        """Cut the rod again: the shape or the copy changed."""
        kind = self.shape.currentData()
        self.shells.setVisible(kind == "shells")
        self.within.setVisible(kind == "within")
        values = self.values()
        with tempfile.TemporaryDirectory() as scratch:
            try:
                self._cut = rod.save_block(
                    self.structure, scratch, values["seed"],
                    name="trial", shape=values["shape"],
                    prepared=values["prepared"])
                self._problem = ""
            except (rod.RodError, ValueError) as exc:
                self._cut, self._problem = None, str(exc)
        self._named()

    def _named(self, *_args) -> None:
        problem = self.problem()
        if problem:
            self.summary.setText(problem)
            set_tone(self.summary, WARNING)
        else:
            cut = self._cut.rod
            hand = cut.hand
            self.summary.setText(
                f"{len(cut.metals)} metal(s) and "
                f"{len(cut.connections)} point(s) of extension a "
                f"{cut.repeat:.2f} A repeat, "
                f"{'achiral' if hand is None else hand + '-handed'}, "
                f"{len(cut.edges)} edge(s) along it.  It will be in the "
                f"rod builder as <b>{self.values()['name']}</b>, with "
                f"its linker, in {self.folder.name}/{rod.SAVED}/ of "
                f"this workspace")
            set_tone(self.summary, HINT)
        self.ok_button.setEnabled(not problem)

    @classmethod
    def ask(cls, structure, folder, seed=None, parent=None):
        """The :func:`xtal.mof.rod.save_block` keywords, or ``None``
        if it was cancelled."""
        with answered(cls(structure, folder, seed, parent)) as dialog:
            if dialog.exec() != QDialog.Accepted:
                return None
            return dialog.values()


def _suggested(structure) -> str:
    """The file the crystal came from, as a name: a CIF's data block is
    a database code more often than not (``CSD_CIF_POSWUS``)."""
    return rod.default_name(structure)
