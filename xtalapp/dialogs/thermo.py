"""
xtalapp.dialogs.thermo
======================
Set up a frequencies-and-thermochemistry run, and say what it costs.

It reads the engine rather than configuring one, as the scan dialog
does: the chooser opens on the Force Field panel's engine and each
engine's form on what the panel has set for it.  The rest is the
action's own generated form, with the rows that only a molecule reads
(symmetry number, spin, pressure) shown only when the run will treat
the structure as one.

**One line says the cost before Run.**  A Hessian is 6 evaluations a
free atom and one more, and one evaluation of MOF-5 under MACE is
nearly a second, so the line times one single point of the structure
in front and multiplies -- once the dialog is on screen, so a slow
engine's first call does not hold the dialog closed.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)

from xtal.core import molecule
from xtal.ff import vibrations
from xtal.ff.registry import ENGINES
from xtal.modules.thermo import frozen_sites
from xtalapp import manual
from xtalapp.dialogs.answered import answered
from xtalapp.dialogs.module_form import ParamForm
from xtalapp.dialogs.scan import (
    _document,
    _engine_forms,
    _show_page,
    _spell,
    _unavailable,
    _wrapped,
)
from xtalapp.docks import scrolling
from xtalapp.docks.ff_panel import panel_engine
from xtalapp.widgets.tone import HINT, set_tone

#: The rows a crystal never reads.
MOLECULE_ONLY = ("sigma", "multiplicity", "pressure")


class ThermoDialog(QDialog):
    """Ask for a thermochemistry (or IR) run on the panel's engine."""

    def __init__(self, module, action, parent=None, initial=None):
        super().__init__(parent)
        self.module = module
        self.action = action
        self.window = parent
        self.setWindowTitle(f"{module.label}: "
                            f"{action.label.rstrip('.')}")
        document = _document(parent)
        self.structure = (document.structure if document is not None
                          else None)
        self.isolated = (self.structure is not None
                         and molecule.is_isolated(self.structure))
        self._seconds: dict = {}

        self.engine = QComboBox()
        for engine in ENGINES:
            self.engine.addItem(engine.label, engine.name)
        self._select(self.engine, panel_engine(parent))
        self.engine_forms, self.engine_stack, self.engine_pages = \
            _engine_forms(parent)
        self.availability = QLabel("")
        self.availability.setWordWrap(True)
        set_tone(self.availability, HINT)

        own = tuple(p for p in action.params if p.name != "engine")
        self.form = ParamForm(own)
        system = self.form.widgets.get("system")
        if system is not None and self.isolated:
            # Proposed, not imposed: the box can always be changed.
            self._select(system, "molecule")

        self.estimate = QLabel("")
        self.estimate.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok |
                                   QDialogButtonBox.Cancel)
        manual.add_help_button(buttons, "energy/thermochemistry")
        buttons.button(QDialogButtonBox.Ok).setText("Run")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.buttons = buttons

        top = QFormLayout()
        top.addRow("Engine", self.engine)
        inner = QVBoxLayout()
        inner.addLayout(top)
        inner.addWidget(self.engine_stack)
        inner.addWidget(self.availability)
        inner.addWidget(self.form)
        inner.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addWidget(scrolling(_wrapped(inner)))
        layout.addWidget(self.estimate)
        layout.addWidget(buttons)
        self.resize(520, 620)

        self.engine.currentIndexChanged.connect(self._engine_changed)
        for form in self.engine_forms.values():
            form.changed.connect(self._engine_changed)
        self.form.changed.connect(self.refresh)
        if initial:
            self.set_values(initial)
        self._engine_changed()
        QTimer.singleShot(0, self.time_one_evaluation)

    # -- what is shown -------------------------------------------------

    def system(self) -> str:
        chosen = str(self.form.values().get("system", "auto"))
        if chosen == "auto":
            return "molecule" if self.isolated else "crystal"
        return chosen

    def _engine_changed(self) -> None:
        name = str(self.engine.currentData())
        _show_page(self.engine_stack, self.engine_pages.get(name, 0))
        reason = _unavailable(name, self.engine_values())
        self.availability.setText(reason)
        self.availability.setVisible(bool(reason))
        self.refresh()

    def refresh(self) -> None:
        """Show the molecule's rows for a molecule, and the cost."""
        layout = self.form.layout()
        molecular = self.system() == "molecule"
        for name in MOLECULE_ONLY:
            widget = self.form.widgets.get(name)
            if widget is not None:
                layout.setRowVisible(widget, molecular)
        ok = self.buttons.button(QDialogButtonBox.Ok)
        if self.structure is None:
            self.estimate.setText("no structure is open")
            ok.setEnabled(False)
            return
        if self.availability.text():
            ok.setEnabled(False)
            self.estimate.setText("")
            return
        try:
            frozen = frozen_sites(self.form.values().get("freeze", ""),
                                  self.structure.n_sites)
        except Exception as error:                  # noqa: BLE001
            self.estimate.setText(str(error))
            set_tone(self.estimate, HINT)
            ok.setEnabled(False)
            return
        ok.setEnabled(True)
        self.estimate.setStyleSheet("")
        self.estimate.setText(self.cost(frozen))

    def cost(self, frozen=()) -> str:
        """``N evaluations x t s ≈ total (Gamma only, every atom)``."""
        from xtal.core import p1

        cell = p1.expand(self.structure)
        atoms = [i for i in range(cell.n_atoms)
                 if int(cell.site_idx[i]) in set(frozen)]
        count = vibrations.evaluations(self.structure, atoms)
        what = "Gamma only, every free atom displaced"
        seconds = self._seconds.get(self._engine_key())
        if seconds is None:
            return f"{count} evaluations ({what}); timing one..."
        relax = (" plus the relaxation"
                 if self.form.values().get("relax_first") else "")
        total = count * seconds
        spelled = "under a second" if total < 1.0 else _spell(total)
        return (f"{count} evaluations x {seconds:.2g} s ≈ "
                f"{spelled}{relax} ({what})")

    def _engine_key(self):
        return (str(self.engine.currentData()),
                tuple(sorted(self.engine_values().items())))

    def time_one_evaluation(self) -> None:
        """One single point of the structure in front, timed: the
        second call, since the first pays for typing the atoms or
        loading a model."""
        key = self._engine_key()
        if self.structure is None or key in self._seconds \
                or self.availability.text():
            return
        from xtal.core import p1
        try:
            calculator = ENGINES.build(key[0], self.structure,
                                       **self.engine_values())
            cell = p1.expand(self.structure)
            matrix = self.structure.lattice.matrix
            calculator.compute(cell.cart, matrix)
            start = time.perf_counter()
            calculator.compute(cell.cart, matrix)
            self._seconds[key] = time.perf_counter() - start
        except Exception as error:                  # noqa: BLE001
            self.estimate.setText(f"one evaluation failed: {error}")
            set_tone(self.estimate, HINT)
            return
        self.refresh()

    # -- what it hands back --------------------------------------------

    def engine_values(self) -> dict:
        form = self.engine_forms.get(str(self.engine.currentData()))
        return dict(form.values()) if form is not None else {}

    def values(self) -> dict:
        out = dict(self.form.values())
        out["engine"] = str(self.engine.currentData())
        out["engine_options"] = self.engine_values()
        return out

    def set_values(self, values) -> None:
        values = dict(values or {})
        if "engine" in values:
            self._select(self.engine, values["engine"])
        form = self.engine_forms.get(str(self.engine.currentData()))
        if form is not None and values.get("engine_options"):
            form.set_values(values["engine_options"])
        self.form.set_values({k: v for k, v in values.items()
                              if k in self.form.widgets})

    @staticmethod
    def _select(combo, value) -> None:
        index = combo.findData(value)
        if index < 0:
            index = combo.findText(str(value))
        if index >= 0:
            combo.setCurrentIndex(index)

    @classmethod
    def ask(cls, module, action, parent=None, initial=None):
        with answered(cls(module, action, parent, initial)) as dialog:
            if dialog.exec() != QDialog.Accepted:
                return None
            return dialog.values()
