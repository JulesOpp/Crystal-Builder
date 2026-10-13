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
free atom and one more -- or, with phonopy, one per displacement the
symmetry leaves -- and one evaluation of MOF-5 under MACE is nearly a
second, so the line times one single point of the structure in front
and multiplies.  The timing is on a worker thread, started again
(after a pause, so typing is not timed key by key) whenever the
engine or its options change: on the GUI thread a MACE model not yet
downloaded froze the dialog for the download.  A phonopy supercell's
point is the cell's times its repeats, which is close enough to say.

**Without phonopy its rows are greyed**, the choice in *Hessian* too,
and a line says what installing the ``phonons`` extra buys, with
Preferences > Engines one click away; Automatic is then Gamma only.

**Analytic is offered only for an engine that has one** (MACE), and
greyed for the rest.  Its line says memory as well as time, because
memory is what it costs: a row is about 1.25 evaluations, and the
graph it holds about 13 MB an atom
(:data:`xtal.core.limits.HESSIAN_MB_PER_ATOM`).
"""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)

from xtal.core import limits, molecule
from xtal.ff import phonons, vibrations
from xtal.ff.registry import ENGINES
from xtal.modules.thermo import (
    check_analytic,
    choose_method,
    frozen_sites,
    has_analytic_hessian,
)
from xtal.params import ParamError
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
from xtalapp.workers import start_in_thread

#: How long the engine has to stay chosen before it is timed, ms.
RETIME_AFTER = 400


class _Timing(QObject):
    """One single point timed, off the GUI thread: the second call,
    since the first pays for typing the atoms or loading a model."""

    finished = Signal(object, float)        # (engine key, seconds)
    failed = Signal(object, str)

    def __init__(self, key, structure, values):
        super().__init__()
        self.key = key
        self.structure = structure
        self.values = values

    def run(self) -> None:
        from xtal.core import p1
        try:
            calculator = ENGINES.build(self.key[0], self.structure,
                                       **self.values)
            cell = p1.expand(self.structure)
            matrix = self.structure.lattice.matrix
            calculator.compute(cell.cart, matrix)
            start = time.perf_counter()
            calculator.compute(cell.cart, matrix)
            self.finished.emit(self.key, time.perf_counter() - start)
        except Exception as error:                  # noqa: BLE001
            self.failed.emit(self.key, str(error))

#: The rows a crystal never reads.
MOLECULE_ONLY = ("sigma", "multiplicity", "pressure")

#: The rows only a phonopy run reads.
PHONOPY_ONLY = ("supercell", "mesh")

#: A row of an analytic Hessian, in evaluations: MIL-53 under MACE was
#: 1.03 s a row against 0.83 s an evaluation.
ROW_COST = 1.25


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
        self._timing: set = set()
        self._plans: dict = {}
        self._retime = QTimer(self)
        self._retime.setSingleShot(True)
        self._retime.setInterval(RETIME_AFTER)
        self._retime.timeout.connect(self.time_one_evaluation)

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

        self.phonopy_note = QLabel(
            "phonopy is not installed, so every atom is displaced at "
            "Gamma.  The phonons extra adds symmetry-reduced "
            "displacements and a q-mesh -- the command to install it "
            'is on <a href="engines">Preferences &gt; Engines</a>')
        self.phonopy_note.setWordWrap(True)
        self.phonopy_note.setTextFormat(Qt.TextFormat.RichText)
        self.phonopy_note.linkActivated.connect(self._show_engines)
        set_tone(self.phonopy_note, HINT)
        self.phonopy_note.setVisible(not phonons.installed())
        if not phonons.installed():
            self._grey_phonopy()

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
        inner.addWidget(self.phonopy_note)
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
        self._retime.stop()

    # -- what is shown -------------------------------------------------

    def system(self) -> str:
        chosen = str(self.form.values().get("system", "auto"))
        if chosen == "auto":
            return "molecule" if self.isolated else "crystal"
        return chosen

    def _grey_phonopy(self) -> None:
        """The phonopy choice and its rows, disabled where it is not
        installed."""
        method = self.form.widgets.get("method")
        if method is not None:
            index = method.findData("phonopy")
            item = method.model().item(index) if index >= 0 else None
            if item is not None:
                item.setEnabled(False)
            if method.currentData() == "phonopy":
                self._select(method, "auto")
        for name in PHONOPY_ONLY:
            widget = self.form.widgets.get(name)
            if widget is not None:
                widget.setEnabled(False)

    def _show_engines(self, _link="") -> None:
        show = getattr(self.window, "show_preferences", None)
        if show is not None:
            show("engines")

    def method(self, frozen=()) -> str:
        """``phonopy``, ``gamma`` or ``analytic``, as the run will
        decide it."""
        asked = str(self.form.values().get("method", "auto"))
        return choose_method(asked, self.system(), frozen,
                             engine=str(self.engine.currentData()))[0]

    def _grey_analytic(self, name: str) -> None:
        """Analytic offered only where the engine has a Hessian."""
        method = self.form.widgets.get("method")
        if method is None:
            return
        index = method.findData("analytic")
        item = method.model().item(index) if index >= 0 else None
        if item is None:
            return
        offered = has_analytic_hessian(name)
        item.setEnabled(offered)
        item.setToolTip("" if offered else
                        "This engine has no second derivatives of its "
                        "own; MACE does")
        if not offered and method.currentData() == "analytic":
            self._select(method, "auto")

    def _engine_changed(self) -> None:
        name = str(self.engine.currentData())
        self._grey_analytic(name)
        _show_page(self.engine_stack, self.engine_pages.get(name, 0))
        reason = _unavailable(name, self.engine_values())
        self.availability.setText(reason)
        self.availability.setVisible(bool(reason))
        self.refresh()
        if self._engine_key() not in self._seconds:
            self._retime.start()

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
        try:
            method = self.method(frozen)
        except ParamError as error:
            self.estimate.setText(str(error))
            set_tone(self.estimate, HINT)
            ok.setEnabled(False)
            return
        for name in PHONOPY_ONLY:
            widget = self.form.widgets.get(name)
            if widget is not None:
                layout.setRowVisible(widget, method == "phonopy"
                                     or not phonons.installed())
        ok.setEnabled(True)
        self.estimate.setStyleSheet("")
        try:
            self.estimate.setText(self.cost(frozen, method))
        except (ValueError, ParamError) as error:
            self.estimate.setText(str(error))
            set_tone(self.estimate, HINT)
            ok.setEnabled(False)

    def cost(self, frozen=(), method="gamma") -> str:
        """``N evaluations x t s ≈ total (how)``: Gamma only with
        every atom displaced, or phonopy's displacements in its
        supercell.  Raises ``ValueError`` for a supercell refused."""
        from xtal.core import p1

        scale = 1
        memory = ""
        if method == "analytic":
            verdict = check_analytic(self.structure, frozen)
            atoms = verdict.estimate
            count = 3 * atoms
            scale = ROW_COST
            gb = atoms * limits.HESSIAN_MB_PER_ATOM / 1024
            memory = f", about {gb:.1f} GB beside the model"
            what = "analytic, a row per free coordinate"
            if verdict.warned:
                memory += f" -- {verdict.sentence}"
        elif method == "phonopy":
            ahead = self.phonopy_plan()
            if ahead.verdict.refused:
                raise ValueError(phonons.said(ahead.verdict))
            count = ahead.evaluations
            scale = int(ahead.supercell[0] * ahead.supercell[1]
                        * ahead.supercell[2])
            n = "x".join(str(v) for v in ahead.supercell)
            what = f"phonopy, supercell {n}"
        else:
            cell = p1.expand(self.structure)
            atoms = [i for i in range(cell.n_atoms)
                     if int(cell.site_idx[i]) in set(frozen)]
            count = vibrations.evaluations(self.structure, atoms)
            what = "Gamma only, every free atom displaced"
        seconds = self._seconds.get(self._engine_key())
        noun = "rows" if method == "analytic" else "evaluations"
        if seconds is None:
            return (f"{count} {noun} ({what}){memory}"
                    f"{self._flux_said()}; timing one...")
        seconds *= scale
        relax = (" plus the relaxation"
                 if self.form.values().get("relax_first") else "")
        total = count * seconds
        spelled = "under a second" if total < 1.0 else _spell(total)
        return (f"{count} {noun} x {seconds:.2g} s ≈ "
                f"{spelled}{relax} ({what}){memory}{self._flux_said()}")

    def _flux_said(self) -> str:
        """The charge flux's solves, which are not the engine's and
        can be the longer half: an hour of EQeq on MFU-4l."""
        values = self.form.values()
        spectrum = self.action.name == "infrared" or values.get("ir")
        if not spectrum or values.get("ir_charges") != "flux":
            return ""
        free = vibrations.free_atoms(self.structure)
        return f", then {6 * free} EQeq solves for the charge flux"

    def phonopy_plan(self) -> phonons.Plan:
        """phonopy's plan for the supercell and step asked, kept: it
        finds the symmetry, which on MFU-4l is most of a second, and
        the form refreshes on every keystroke."""
        values = self.form.values()
        key = (str(values.get("supercell", "auto")),
               float(values.get("delta", vibrations.DELTA)))
        if key not in self._plans:
            self._plans[key] = phonons.plan(self.structure, key[0],
                                            delta=key[1])
        return self._plans[key]

    def _engine_key(self):
        return (str(self.engine.currentData()),
                tuple(sorted(self.engine_values().items())))

    def time_one_evaluation(self) -> None:
        """Time one single point of the structure in front, on a
        worker thread; the line says so when it lands."""
        key = self._engine_key()
        if self.structure is None or key in self._seconds \
                or key in self._timing or self.availability.text():
            return
        self._timing.add(key)
        worker = _Timing(key, self.structure.copy(),
                         self.engine_values())
        worker.finished.connect(self._timed)
        worker.failed.connect(self._untimed)
        start_in_thread(worker)

    def _timed(self, key, seconds) -> None:
        self._timing.discard(key)
        self._seconds[key] = float(seconds)
        if key == self._engine_key():
            self.refresh()

    def _untimed(self, key, error) -> None:
        self._timing.discard(key)
        if key == self._engine_key():
            self.estimate.setText(f"one evaluation failed: {error}")
            set_tone(self.estimate, HINT)

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
