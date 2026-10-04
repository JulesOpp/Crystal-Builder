"""
xtalapp.dialogs.orca_input
==========================
Modules > ORCA > Input file...: the choices, and the file they make.

Everything the input is decided from is on the left, in groups, and
the input itself on the right, rewritten as anything changes -- the
file is short, and seeing it is how a person who knows ORCA checks
what a box means.  Under it, the electron count and multiplicity, and
anything :func:`xtal.orca.input.problems` has to say: a refusal in
warning tone with Write greyed, a caution as a hint.  The dialog
decides none of that itself, so ``xtal run orca.input`` refuses
exactly what it does.

What the values are restored from is the runner's memory of the last
run of this entry in this window; the atoms and the name are not
restored but read from the tab in front each time, because they are
the structure's and not the method's.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from xtal.orca import catalogue
from xtal.orca import input as orca
from xtalapp.dialogs.answered import answered
from xtalapp.docks import scrolling
from xtalapp.widgets.catalog_picker import CatalogPicker
from xtalapp.widgets.tone import HINT, WARNING, set_tone


def _document(parent):
    current = getattr(parent, "current_document", None)
    return current() if callable(current) else None


def _choice(pairs) -> QComboBox:
    box = QComboBox()
    for value, label in pairs:
        box.addItem(label, value)
    return box


def _spin(low, high, value=0, special="", suffix="") -> QSpinBox:
    box = QSpinBox()
    box.setRange(low, high)
    box.setValue(value)
    if special:
        box.setSpecialValueText(special)
    if suffix:
        box.setSuffix(suffix)
    return box


def _set_choice(box: QComboBox, value) -> None:
    index = box.findData(value)
    if index >= 0:
        box.setCurrentIndex(index)


class OrcaInputDialog(QDialog):
    """The ORCA input's choices, the input, and what is wrong with it."""

    def __init__(self, module, action, parent=None, initial=None):
        super().__init__(parent)
        self.module = module
        self.action = action
        self.setWindowTitle("ORCA: Input file")
        document = _document(parent)
        self._structure = getattr(document, "structure", None)
        selection = getattr(document, "selection", None)
        self._selected = sorted(int(a) for a in
                                getattr(selection, "atoms", ()) or ())
        path = getattr(document, "path", None)
        self._name = (path.stem if path is not None else
                      str(getattr(self._structure, "meta", {})
                          .get("title") or "structure"))
        self._clusters = {}

        # -- method ----------------------------------------------------
        self.functional = CatalogPicker(
            catalogue.FUNCTIONALS, placeholder="Search functionals")
        self.dispersion = _choice(catalogue.DISPERSIONS)
        self.basis = CatalogPicker(catalogue.bases(),
                                   placeholder="Search basis sets")
        self.ri = _choice(catalogue.RI_CHOICES)
        method = QFormLayout()
        method.addRow("Functional", self.functional)
        method.addRow("Dispersion", self.dispersion)
        method.addRow("Basis set", self.basis)
        method.addRow("RI", self.ri)

        # -- job -------------------------------------------------------
        self.run = _choice(catalogue.RUNS)
        self.opt_level = _choice(catalogue.OPT_LEVELS)
        self.cartesian = QCheckBox("Cartesian coordinates (COpt)")
        self.calc_hess = QCheckBox("Exact Hessian first (Calc_Hess)")
        self.max_iter = _spin(0, 100000, special="Default")
        self.freq = QCheckBox("Frequencies (Freq)")
        job = QFormLayout()
        job.addRow("Job", self.run)
        job.addRow("Convergence", self.opt_level)
        job.addRow("", self.cartesian)
        job.addRow("", self.calc_hess)
        job.addRow("MaxIter (%geom)", self.max_iter)
        job.addRow("", self.freq)

        # -- scf -------------------------------------------------------
        self.scf_threshold = _choice(catalogue.SCF_THRESHOLDS)
        self.scf_solver = _choice(catalogue.SCF_SOLVERS)
        self.scf_max_iter = _spin(0, 100000, special="Default")
        self.scf_guess = _choice(catalogue.SCF_GUESSES)
        scf = QFormLayout()
        scf.addRow("Convergence", self.scf_threshold)
        scf.addRow("Solver", self.scf_solver)
        scf.addRow("MaxIter (%scf)", self.scf_max_iter)
        scf.addRow("Guess (%scf)", self.scf_guess)

        # -- excited states --------------------------------------------
        self.tddft = QGroupBox("UV-Vis by TD-DFT (%tddft)")
        self.tddft.setCheckable(True)
        self.tddft.setChecked(False)
        self.nroots = _spin(1, 10000, 10)
        self.triplets = QCheckBox("Triplets too")
        excited = QFormLayout(self.tddft)
        excited.addRow("Roots (nroots)", self.nroots)
        excited.addRow("", self.triplets)

        # -- environment -----------------------------------------------
        self.solvation = _choice(catalogue.SOLVATIONS)
        self.solvent = QComboBox()
        self.solvent.setEditable(True)
        for solvent in catalogue.solvents():
            self.solvent.addItem(" / ".join(solvent.names), solvent.name)
        self.solvent.completer().setFilterMode(Qt.MatchContains)
        self.solvent.completer().setCompletionMode(
            QCompleter.PopupCompletion)
        _set_choice(self.solvent, "water")
        environment = QFormLayout()
        environment.addRow("Model", self.solvation)
        environment.addRow("Solvent", self.solvent)

        # -- system ----------------------------------------------------
        self.charge = _spin(-1000, 1000, 0)
        self.multiplicity = _spin(1, 1000, 1)
        self.selected_only = QCheckBox(
            f"Selected atoms only ({len(self._selected)})"
            if self._selected else "Selected atoms only")
        self.selected_only.setEnabled(bool(self._selected))
        self.selected_only.setToolTip(
            "Write the selected atoms, each molecule made whole"
            if self._selected else "Nothing is selected")
        system = QFormLayout()
        system.addRow("Charge", self.charge)
        system.addRow("Multiplicity (2S+1)", self.multiplicity)
        system.addRow("", self.selected_only)

        # -- resources -------------------------------------------------
        self.nprocs = _spin(1, 4096, 1)
        self.maxcore = _spin(0, 10_000_000, 0, special="Default",
                             suffix=" MB")
        resources = QFormLayout()
        resources.addRow("Processes (%pal)", self.nprocs)
        resources.addRow("Memory per process", self.maxcore)

        # -- more ------------------------------------------------------
        self.extra_keywords = QLineEdit()
        self.extra_keywords.setPlaceholderText("e.g. NMR KDIIS")
        self.extra_blocks = QPlainTextEdit()
        self.extra_blocks.setPlaceholderText("%output\n  ...\nend")
        self.extra_blocks.setFixedHeight(
            5 * self.extra_blocks.fontMetrics().lineSpacing())
        more = QFormLayout()
        more.addRow("Keywords", self.extra_keywords)
        more.addRow("Blocks", self.extra_blocks)

        form = QWidget()
        column = QVBoxLayout(form)
        for title, layout in (("Method", method), ("Job", job),
                              ("SCF", scf)):
            column.addWidget(self._group(title, layout))
        column.addWidget(self.tddft)
        for title, layout in (("Solvation", environment),
                              ("System", system),
                              ("Resources", resources),
                              ("More", more)):
            column.addWidget(self._group(title, layout))
        column.addStretch(1)

        # -- the file --------------------------------------------------
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFont(QFontDatabase.systemFont(
            QFontDatabase.FixedFont))
        self.preview.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.electrons = QLabel()
        self.problems = QLabel()
        self.problems.setWordWrap(True)
        self.problems.setTextFormat(Qt.PlainText)
        right = QWidget()
        side = QVBoxLayout(right)
        side.setContentsMargins(0, 0, 0, 0)
        side.addWidget(QLabel("The input"))
        side.addWidget(self.preview, 1)
        side.addWidget(self.electrons)
        side.addWidget(self.problems)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(scrolling(form))
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                        | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Write")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        note = QLabel(action.tip)
        note.setWordWrap(True)
        set_tone(note, HINT)
        layout.addWidget(note)
        layout.addWidget(split, 1)
        layout.addWidget(self.buttons)

        self.functional.set_key(catalogue.DEFAULT_FUNCTIONAL)
        self.basis.set_key(catalogue.DEFAULT_BASIS)
        self.set_values(initial or {})
        for signal in (self.functional.changed, self.basis.changed,
                       self.dispersion.currentIndexChanged,
                       self.ri.currentIndexChanged,
                       self.run.currentIndexChanged,
                       self.opt_level.currentIndexChanged,
                       self.cartesian.toggled, self.calc_hess.toggled,
                       self.max_iter.valueChanged, self.freq.toggled,
                       self.scf_threshold.currentIndexChanged,
                       self.scf_solver.currentIndexChanged,
                       self.scf_max_iter.valueChanged,
                       self.scf_guess.currentIndexChanged,
                       self.tddft.toggled, self.nroots.valueChanged,
                       self.triplets.toggled,
                       self.solvation.currentIndexChanged,
                       self.solvent.currentTextChanged,
                       self.charge.valueChanged,
                       self.multiplicity.valueChanged,
                       self.selected_only.toggled,
                       self.nprocs.valueChanged,
                       self.maxcore.valueChanged,
                       self.extra_keywords.textChanged,
                       self.extra_blocks.textChanged):
            signal.connect(self.refresh)
        self.refresh()
        self.resize(980, 700)

    @staticmethod
    def _group(title, layout) -> QGroupBox:
        box = QGroupBox(title)
        box.setLayout(layout)
        return box

    # -- values --------------------------------------------------------

    def _solvent_name(self) -> str:
        text = self.solvent.currentText().strip()
        index = self.solvent.findText(text)
        if index >= 0:
            return self.solvent.itemData(index)
        found = catalogue.solvent(text.split(" / ")[0])
        return found.name if found is not None else text

    def values(self) -> dict:
        """What the module is run with: its own parameter names."""
        atoms = (" ".join(str(a) for a in self._selected)
                 if self.selected_only.isChecked() else "")
        return {
            "functional": self.functional.key(),
            "basis": self.basis.key(),
            "dispersion": self.dispersion.currentData(),
            "ri": self.ri.currentData(),
            "run": self.run.currentData(),
            "opt_level": self.opt_level.currentData(),
            "cartesian": self.cartesian.isChecked(),
            "freq": self.freq.isChecked(),
            "max_iter": self.max_iter.value(),
            "calc_hess": self.calc_hess.isChecked(),
            "scf_threshold": self.scf_threshold.currentData(),
            "scf_solver": self.scf_solver.currentData(),
            "scf_max_iter": self.scf_max_iter.value(),
            "scf_guess": self.scf_guess.currentData(),
            "tddft_nroots": (self.nroots.value()
                             if self.tddft.isChecked() else 0),
            "tddft_triplets": self.triplets.isChecked(),
            "solvation": self.solvation.currentData(),
            "solvent": self._solvent_name(),
            "nprocs": self.nprocs.value(),
            "maxcore_mb": self.maxcore.value(),
            "charge": self.charge.value(),
            "multiplicity": self.multiplicity.value(),
            "extra_keywords": self.extra_keywords.text(),
            "extra_blocks": self.extra_blocks.toPlainText(),
            "atoms": atoms,
            "name": self._name,
        }

    def set_values(self, values: dict) -> None:
        """The last run's choices; never its atoms or its name."""
        if not values:
            return
        if values.get("functional"):
            self.functional.set_key(values["functional"])
        if values.get("basis"):
            self.basis.set_key(values["basis"])
        for name, box in (("dispersion", self.dispersion),
                          ("ri", self.ri), ("run", self.run),
                          ("opt_level", self.opt_level),
                          ("scf_threshold", self.scf_threshold),
                          ("scf_solver", self.scf_solver),
                          ("scf_guess", self.scf_guess),
                          ("solvation", self.solvation)):
            if name in values:
                _set_choice(box, values[name])
        for name, box in (("cartesian", self.cartesian),
                          ("freq", self.freq),
                          ("calc_hess", self.calc_hess),
                          ("tddft_triplets", self.triplets)):
            if name in values:
                box.setChecked(bool(values[name]))
        for name, box in (("max_iter", self.max_iter),
                          ("scf_max_iter", self.scf_max_iter),
                          ("charge", self.charge),
                          ("multiplicity", self.multiplicity),
                          ("nprocs", self.nprocs),
                          ("maxcore_mb", self.maxcore)):
            if name in values:
                box.setValue(int(values[name] or 0))
        roots = int(values.get("tddft_nroots") or 0)
        self.tddft.setChecked(roots > 0)
        if roots:
            self.nroots.setValue(roots)
        if values.get("solvent"):
            _set_choice(self.solvent, values["solvent"])
        self.extra_keywords.setText(values.get("extra_keywords", ""))
        self.extra_blocks.setPlainText(values.get("extra_blocks", ""))

    # -- what it makes -------------------------------------------------

    def cluster(self):
        """The atoms that would be written, worked out once a choice of
        atoms -- the cell is expanded and its fragments walked, which
        on MFU-4l is not free and does not change with the method."""
        if self._structure is None:
            return orca.Cluster([], np.zeros((0, 3)))
        chosen = self.selected_only.isChecked()
        if chosen not in self._clusters:
            self._clusters[chosen] = orca.cluster(
                self._structure, self._selected if chosen else None)
        return self._clusters[chosen]

    def refresh(self, *_args) -> None:
        from xtal.modules.orca import orca_input

        values = self.values()
        inp = orca_input(values)
        found = self.cluster()
        functional = catalogue.functional(inp.functional)
        own_basis = functional is not None and functional.own_basis
        self.basis.setEnabled(not own_basis)
        self.dispersion.setEnabled(
            functional is None or not functional.carries_dispersion)
        optimising = inp.run != "sp"
        for widget in (self.opt_level, self.cartesian, self.max_iter,
                       self.calc_hess):
            widget.setEnabled(optimising)
        self.opt_level.setEnabled(inp.run == "opt")
        self.solvent.setEnabled(bool(inp.solvation))

        refused, cautions = orca.problems(inp, found)
        stem = orca.safe_name(self._name)
        self.preview.setPlainText(orca.render(
            inp, f"{stem}.xyz", title=f"{self._name}, from Crystal "
                                      f"Builder"))
        n = orca.electrons(found.elements, inp.charge)
        self.electrons.setText(
            f"{found.n_atoms} atoms: "
            f"{orca.describe(n, inp.multiplicity)}")
        said = refused or cautions
        self.problems.setText("\n".join(said))
        set_tone(self.problems, WARNING if refused else HINT)
        self.problems.setVisible(bool(said))
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(not refused)

    @classmethod
    def ask(cls, module, action, parent=None, initial=None):
        with answered(cls(module, action, parent, initial)) as dialog:
            if dialog.exec() != QDialog.Accepted:
                return None
            return dialog.values()


__all__ = ["OrcaInputDialog"]
