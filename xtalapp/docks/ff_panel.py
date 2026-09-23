"""
xtalapp.docks.ff_panel
======================
One dock class, opened twice: the Forcefield panel and the DFTB+
panel.

They used to be one window with an engine chooser at the top, and
splitting them was Phase I's answer to the DFTB+ half growing taller
than a laptop screen -- its generated form (Hamiltonian, parameter
directory, dispersion, charge, temperature, k-point spacing, SCC
tolerance, angular momentum overrides) stacked on top of the shared
Optimisation controls, the plot and the report, in one non-scrolling
column.  ``ForceFieldDock`` now takes the *engines* it should offer:
``["uff"]`` for one dock and ``["dftb"]`` for the other, each built by
:class:`~xtalapp.mainwindow.MainWindow` and each its own
``QDockWidget`` with its own place in the Window menu -- so a user who
has never touched DFTB+ never opens a form for it.  Offered more than
one engine (nothing does today, but nothing stops a third one sharing
a chooser later) the combo box that used to be the only way in is
still there.  And the whole thing sits in a scroll area rather than a
bare splitter, so a tall form makes the panel scroll instead of making
it refuse to fit the screen it opened on.

Three parts stacked in the order they are used.

**The atom types come first, and they are editable.**  UFF's answer is
only as good as its typing, and the typing is a guess made from
coordination and geometry -- so the table shows every site's type, how
sure the typer was and the sentence explaining why, and any of them can
be overridden from a drop-down.  Putting it above the Run button is
deliberate: it is the thing to look at before believing a number, not
after.

**Running is asynchronous and reversible.**  An optimisation goes to a
worker thread, the geometry is drawn as it moves, and Pause and Stop
work at every step.  Nothing reaches the undo stack until the run
finishes, and then exactly one command does -- so Ctrl+Z afterwards
gives back the structure the user started with, not the last iteration.
Cancelling puts the atoms back where they were and leaves no trace.

**The result is a breakdown, not a number.**  A total energy on its own
says nothing; per-term energies say which part of the model is unhappy,
and a bond term carrying most of a large energy usually means a
mistyped atom rather than a strained crystal.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from xtal.ff import ENGINES
from xtal.ff.optimize import (
    DEFAULT_FORCE_TOLERANCE,
    DEFAULT_MAX_STEPS,
    DEFAULT_STRESS_TOLERANCE,
    METHODS,
    unconverged,
)
from xtal.ff.uff import calculator as uff_calculator
from xtal.ff.uff import params
from xtalapp.dialogs.module_form import ParamForm
from xtalapp.plot import TracePlot
from xtalapp.widgets.atom_types import (
    COLUMNS,  # noqa: F401
    AtomTypeTable,
    warnings_text,
)
from xtalapp.widgets.atom_types import HEADING as TYPES_HEADING
from xtalapp.widgets.tone import HINT, set_tone
from xtalapp.workers import OptimizationWorker, start_in_thread

CHARGE_SOURCES = [
    ("From the sites", "site"),
    ("Equilibrate (QEq)", "qeq"),
    ("All zero", "zero"),
]
METHOD_LABELS = {
    "lbfgs": "L-BFGS (fast near a minimum)",
    "fire": "FIRE (robust far from one)",
    "smart": "Smart (descent, then ABNR, then quasi-Newton)",
    "steepest_descent": "Steepest descent",
    "conjugate_gradient": "Conjugate gradient",
    "quasi_newton": "Quasi-Newton (BFGS)",
    "abnr": "ABNR (adopted-basis Newton-Raphson)",
}

#: Said whenever the cell is a variable, before and after.  A lattice
#: constant is the number people most want out of this and the one UFF
#: is least entitled to be believed about.
CELL_WARNING = (
    "A cell relaxed under UFF is a UFF cell: for a framework it is "
    "routinely a few percent out. Use it as a starting geometry, not "
    "as a measured lattice constant.")


#: Label -> preview redraw interval in milliseconds.  0 draws every
#: step, -1 draws none of them.
REDRAW_RATES = (
    ("Every step", 0),
    ("20 times a second", 50),
    ("5 times a second", 200),
    ("Not while it runs", -1),
)


class ForceFieldDock(QDockWidget):
    """Atom types, a single point, and a geometry optimisation.

    ``engines`` restricts the chooser to the names given -- one engine
    is the normal case now, and the combo box hides itself when that
    is all there is to choose between.  Left as ``None`` it offers
    every registered engine, which is what a test that does not care
    about the split wants and is also how this behaved before there
    were two docks.
    """

    statusMessage = Signal(str)
    previewIntervalChanged = Signal(int)    # ms; 0 every step, -1 never
    runStarted = Signal(str)                # the run folder's path
    runFinished = Signal(str)               # the run folder's path

    def __init__(self, parent=None, *, title="Force Field",
                object_name="ForceFieldDock", engines=None):
        super().__init__(title, parent)
        self.setObjectName(object_name)
        self.document = None
        self.worker: OptimizationWorker | None = None
        self._thread = None
        self._before: np.ndarray | None = None
        self._before_matrix: np.ndarray | None = None
        self._recorder = None

        self.engines = (list(ENGINES) if engines is None
                        else [ENGINES.get(name) for name in engines])

        self.engine = QComboBox()
        for engine in self.engines:
            self.engine.addItem(engine.label, engine.name)
            self.engine.setItemData(self.engine.count() - 1,
                                    engine.description, Qt.ToolTipRole)
        self.engine.currentIndexChanged.connect(self._on_engine)

        # An engine that declares its options gets a generated form,
        # one per engine, built once and shown when it is chosen.
        #
        # UFF is the exception and is named rather than detected.  It
        # declares its options too now, so that a dialog elsewhere can
        # offer "UFF or UFF4MOF" without reaching in here -- but the
        # controls below stay, because two of them drive each other
        # (ticking electrostatics is what enables the charge chooser)
        # and a generated form has no way to say that.  Same asymmetry
        # as ``Action.shell``, and the same honesty about it.
        self.engine_forms = {
            engine.name: ParamForm(engine.options)
            for engine in self.engines
            if engine.options and engine.name != "uff"}
        for form in self.engine_forms.values():
            # An engine whose availability depends on what the form
            # says -- xTB's does, per method -- has to be re-asked
            # when the form changes, or the Run button stays enabled
            # for a method this machine has no binary for.
            form.changed.connect(self._show_engine)
        self.engine_note = QLabel("")
        self.engine_note.setWordWrap(True)
        set_tone(self.engine_note, HINT)

        # UFF4MOF was always on and nothing said so.  Offered so a
        # number can be checked against the field it extends, and so
        # the table's "framework-fitted" is visibly a choice.
        self.parameter_set = QComboBox()
        for value, label in params.PARAMETER_SETS:
            self.parameter_set.addItem(label, value)
        self.parameter_set.setToolTip(
            "UFF4MOF adds rows fitted to metal nodes in frameworks and "
            "types everything else exactly as UFF does.  Plain UFF "
            "never uses them, which is how to see what they change")
        self.parameter_set.currentIndexChanged.connect(
            lambda _index: self.refresh())
        self.coulomb = QCheckBox("Include electrostatics")
        self.coulomb.setToolTip(
            "Off by default, as in UFF itself: the published "
            "parameters were fitted without a Coulomb term")
        self.coulomb.toggled.connect(self._on_coulomb)
        self.charges = QComboBox()
        for label, value in CHARGE_SOURCES:
            self.charges.addItem(label, value)
        self.charges.setEnabled(False)

        # The van der Waals pair list is array work now -- 4.0 s down
        # to 0.49 s for a 5184-atom cell -- and what is left to control
        # is how big the job is in the first place.  Both are named for
        # what they cost, not left for somebody to discover by reading
        # the source.
        self.vdw_cutoff = QDoubleSpinBox()
        self.vdw_cutoff.setDecimals(1)
        self.vdw_cutoff.setRange(4.0, 30.0)
        self.vdw_cutoff.setSingleStep(1.0)
        self.vdw_cutoff.setValue(uff_calculator.DEFAULT_VDW_CUTOFF)
        self.vdw_cutoff.setSuffix(" A")
        self.vdw_cutoff.setToolTip(
            "How far the van der Waals sum reaches.  The pair count "
            "goes as the cube of this: 10 A is 42% fewer pairs than "
            "12 A, for an LJ tail worth about a thousandth of a "
            "kcal/mol per pair.")
        self.skin = QDoubleSpinBox()
        self.skin.setDecimals(1)
        self.skin.setRange(0.0, 10.0)
        self.skin.setSingleStep(0.5)
        self.skin.setValue(uff_calculator.DEFAULT_SKIN)
        self.skin.setSuffix(" A")
        self.skin.setToolTip(
            "How far an atom can move before the pair list is rebuilt. "
            "Rebuilt whenever any atom has moved half of this -- a "
            "larger skin trades memory for fewer rebuilds, which is "
            "the cheapest knob there is early in a relaxation from a "
            "hand-built geometry.")

        self.method = QComboBox()
        for name in METHODS:
            self.method.addItem(METHOD_LABELS.get(name, name), name)
        self.max_steps = QSpinBox()
        self.max_steps.setRange(1, 100000)
        self.max_steps.setValue(DEFAULT_MAX_STEPS)
        self.tolerance = QDoubleSpinBox()
        self.tolerance.setDecimals(4)
        self.tolerance.setRange(0.0001, 100.0)
        self.tolerance.setSingleStep(0.01)
        self.tolerance.setValue(DEFAULT_FORCE_TOLERANCE)
        self.tolerance.setSuffix(" kcal/mol/A")
        self.freeze = QCheckBox("Freeze the selected atoms")
        self.freeze.setToolTip(
            "Hold the selected sites still and relax everything else")

        # The cell as a variable.  Off by default, and it says what it
        # costs: twelve extra energy evaluations a step for an engine
        # with no analytic stress, which UFF is.
        self.relax_cell = QCheckBox("Relax the cell as well")
        self.relax_cell.setToolTip(
            "Relax the lattice under a symmetry-adapted strain, so a "
            "cubic cell stays cubic and a hexagonal one hexagonal. "
            "Costs twelve extra energy evaluations a step, because "
            "UFF has no analytic stress.")
        self.relax_cell.toggled.connect(self._on_relax_cell)
        # Its own tolerance, in the units a cell is talked about in.
        # The per-atom strain gradient that was the whole of the cell's
        # criterion let a framework call itself relaxed under a fifth
        # of a GPa.
        self.stress_tolerance = QDoubleSpinBox()
        self.stress_tolerance.setDecimals(3)
        self.stress_tolerance.setRange(0.001, 10.0)
        self.stress_tolerance.setSingleStep(0.01)
        self.stress_tolerance.setValue(DEFAULT_STRESS_TOLERANCE)
        self.stress_tolerance.setSuffix(" GPa")
        self.stress_tolerance.setEnabled(False)
        self.stress_tolerance.setToolTip(
            "With the cell relaxing, the run is converged only when "
            "the stress the cell can still relax is below this as well")
        self.pressure = QDoubleSpinBox()
        self.pressure.setDecimals(3)
        self.pressure.setRange(-100.0, 1000.0)
        self.pressure.setSingleStep(0.5)
        self.pressure.setValue(0.0)
        self.pressure.setSuffix(" GPa")
        self.pressure.setEnabled(False)
        self.pressure.setToolTip(
            "External pressure, as a P V term.  Only has an effect "
            "when the cell is free to respond to it.")

        # How often the viewport redraws while a run is going.  Every
        # step is announced whatever this says -- the plot and the
        # status line show all of them; this is only how often the
        # picture is repainted, which on a large cell is the most
        # expensive thing happening.
        self.redraw = QComboBox()
        for label, value in REDRAW_RATES:
            self.redraw.addItem(label, value)
        self.redraw.setCurrentIndex(1)
        self.redraw.setToolTip(
            "How often to redraw the structure while it relaxes. "
            "Every step is the smoothest and the slowest; a long run "
            "on a large cell is often best watched as the plot alone.")
        self.redraw.currentIndexChanged.connect(
            lambda _i: self.previewIntervalChanged.emit(
                int(self.redraw.currentData())))

        self.table = AtomTypeTable()
        self.table.statusMessage.connect(self.statusMessage)

        self.energy_button = QPushButton("Single point")
        self.energy_button.clicked.connect(self.single_point)
        self.run_button = QPushButton("Optimise")
        self.run_button.clicked.connect(self.toggle_run)
        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.toggle_pause)
        self.pause_button.setEnabled(False)

        self.plot = TracePlot()
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setMinimumHeight(90)
        self.notes = QLabel("")
        self.notes.setWordWrap(True)
        set_tone(self.notes, HINT)

        self.setWidget(self._build())
        self.set_document(None)

    def _build(self) -> QWidget:
        setup = QFormLayout()
        setup.setContentsMargins(0, 0, 0, 0)
        setup.addRow("Force field", self.engine)
        setup.addRow("Parameters", self.parameter_set)
        setup.addRow(self.coulomb)
        setup.addRow("Charges", self.charges)
        setup.addRow("van der Waals cutoff", self.vdw_cutoff)
        setup.addRow("Pair list skin", self.skin)
        self.uff_rows = (self.parameter_set, self.coulomb, self.charges,
                         self.vdw_cutoff, self.skin)
        if len(self.engines) <= 1:
            # Nothing to choose between, so the row that would do the
            # choosing is one more thing standing between opening the
            # panel and seeing what it is for.
            self.engine.setVisible(False)
            chooser_label = setup.labelForField(self.engine)
            if chooser_label is not None:
                chooser_label.setVisible(False)

        model = QVBoxLayout()
        model.setContentsMargins(0, 0, 0, 0)
        model.setSpacing(4)
        model.addLayout(setup)
        for form in self.engine_forms.values():
            model.addWidget(form)
        model.addWidget(self.engine_note)
        setup_box = QGroupBox("Model")
        setup_box.setLayout(model)
        self.setup_form = setup

        run = QFormLayout()
        run.setContentsMargins(0, 0, 0, 0)
        run.addRow("Optimiser", self.method)
        run.addRow("Max steps", self.max_steps)
        run.addRow("Converge below", self.tolerance)
        run.addRow(self.freeze)
        run.addRow(self.relax_cell)
        run.addRow("Stress below", self.stress_tolerance)
        run.addRow("Pressure", self.pressure)
        run.addRow("Redraw", self.redraw)
        run_box = QGroupBox("Optimisation")
        run_box.setLayout(run)

        buttons = QHBoxLayout()
        buttons.addWidget(self.energy_button)
        buttons.addWidget(self.run_button)
        buttons.addWidget(self.pause_button)

        top = QVBoxLayout()
        top.setContentsMargins(8, 8, 8, 4)
        top.setSpacing(6)
        top.addWidget(setup_box)
        self.table_heading = QLabel(TYPES_HEADING)
        top.addWidget(self.table_heading)
        top.addWidget(self.table, 1)
        top_widget = QWidget()
        top_widget.setLayout(top)

        bottom = QVBoxLayout()
        bottom.setContentsMargins(8, 4, 8, 8)
        bottom.setSpacing(6)
        bottom.addWidget(run_box)
        bottom.addLayout(buttons)
        bottom.addWidget(self.plot, 1)
        bottom.addWidget(self.report)
        bottom.addWidget(self.notes)
        bottom_widget = QWidget()
        bottom_widget.setLayout(bottom)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(top_widget)
        splitter.addWidget(bottom_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        # A QSplitter's own minimum size is the sum of what its
        # children need, so DFTB+'s generated form -- eight fields on
        # top of the Optimisation controls, the plot and the report --
        # was demanding a taller window than some screens have.  A
        # scroll area's minimum size is not its content's, so the
        # panel now shrinks to fit and scrolls for the rest instead of
        # refusing to.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(splitter)
        return scroll

    # ==================================================================
    #  BINDING
    # ==================================================================

    def set_document(self, document) -> None:
        if self.is_running:
            self.stop()
        self.document = document
        self.plot.clear()
        self.report.setPlainText("")
        self.refresh()

    def set_parameter_directory(self, path: str) -> None:
        """Preferences' Slater-Koster folder, as this form's default.

        **Into an empty field only.**  A directory typed for this run
        belongs to this run, and a preference that overwrote it would
        undo what somebody had just typed -- the field is still the
        thing that decides, and this only saves it being filled in on
        every run.  Which is also why the preference is not read at
        run time: :func:`xtal.ff.dftb.hsd.slater_koster_directory`
        takes what the form says, and it stays the one answer.
        """
        form = self.engine_forms.get("dftb")
        if form is None or not str(path or "").strip():
            return
        current = str(form.values().get("parameter_directory", ""))
        if not current.strip():
            form.set_values({"parameter_directory": str(path)})

    def refresh(self) -> None:
        """Redraw the type table for the current structure.

        Typing is memoised on the structure, so this is cheap between
        edits and correct after one.
        """
        enabled = self.document is not None and bool(ENGINES)
        self.widget().setEnabled(enabled)
        self._show_engine()
        if not self._engine_provides("types"):
            # The table is UFF's answer to a question DFTB+ does not
            # ask: there are no atom types in a tight-binding
            # Hamiltonian, only elements and a parameter set.  Showing
            # an empty table under its heading would look like a
            # failure to type them.
            self.table.setRowCount(0)
            self.table.setVisible(False)
            self.table_heading.setVisible(False)
            return
        self.table.setVisible(True)
        self.table_heading.setVisible(True)
        if not enabled:
            self.table.setRowCount(0)
            self._say("")
            return
        try:
            rows = self.table.fill(self.document,
                                   self.parameter_set.currentData())
        except Exception as exc:                    # noqa: BLE001
            self._say(str(exc))
            return
        self._say(warnings_text(rows))

    def _say(self, text: str) -> None:
        self.notes.setText(text)
        self.notes.setVisible(bool(text))

    # ==================================================================
    #  OPTIONS
    # ==================================================================

    def _on_engine(self, _index: int = 0) -> None:
        """A different engine asks for different things."""
        self._show_engine()
        self.refresh()

    def _show_engine(self) -> None:
        """Show the controls the chosen engine actually has, and say
        so when it cannot run at all.

        An external engine whose binary is missing is the state it
        will usually be in, and the answer belongs here -- beside the
        chooser, before the button -- rather than in the failure after
        pressing Optimise.
        """
        name = self.engine_name()
        if name is None:                            # pragma: no cover
            return
        engine = ENGINES.get(name)
        for form_name, form in self.engine_forms.items():
            form.setVisible(form_name == name)
        # Whether a generated form takes over, and not merely
        # whether the engine declares options: UFF declares them so
        # the scan dialog can offer UFF4MOF without reaching in here,
        # and keeps its hand-built controls all the same.  Asking
        # ``engine.options`` hid all five of them the day UFF gained
        # them, with no form built to put in their place.
        generated = name in self.engine_forms
        for widget in self.uff_rows:
            widget.setVisible(not generated)
            label = self.setup_form.labelForField(widget)
            if label is not None:
                label.setVisible(not generated)
        # With the options, because half of what an external engine
        # needs to be available is in them -- DFTB+ without a
        # parameter directory cannot run, and the box that names one
        # is in the form directly above this note.
        available = engine.availability(**self.options())
        self.engine_note.setText("" if available else available.reason)
        self.engine_note.setVisible(not available)
        if self.is_running:
            # Mid-run the run button is Stop, and _set_running owns
            # the rest.  Re-enabling either from here would offer a
            # second single point on top of the optimisation.
            return
        for button in (self.energy_button, self.run_button):
            button.setEnabled(bool(available))

    def _engine_provides(self, what: str) -> bool:
        name = self.engine_name()
        if name is None:                            # pragma: no cover
            return False
        return what in ENGINES.get(name).provides

    def _on_coulomb(self, on: bool) -> None:
        self.charges.setEnabled(on)

    def _on_relax_cell(self, on: bool) -> None:
        self.pressure.setEnabled(on)
        self.stress_tolerance.setEnabled(on)
        if on:
            self._say(CELL_WARNING)
        else:
            self.refresh()

    def set_preview_interval(self, milliseconds: int) -> None:
        """Show a stored redraw rate without announcing it back."""
        index = self.redraw.findData(int(milliseconds))
        if index >= 0:
            self.redraw.blockSignals(True)
            self.redraw.setCurrentIndex(index)
            self.redraw.blockSignals(False)

    def options(self) -> dict:
        """What to build the calculator with.

        The declared form when the engine has one, and UFF's four
        hand-built controls when it has not.  Never both: an engine
        handed a keyword it has never heard of is a ``TypeError`` at
        the moment the user presses Optimise.
        """
        form = self.engine_forms.get(self.engine_name())
        if form is not None:
            return form.values()
        return {"parameter_set": self.parameter_set.currentData(),
                "coulomb": self.coulomb.isChecked(),
                "charges": self.charges.currentData(),
                "vdw_cutoff": self.vdw_cutoff.value(),
                "skin": self.skin.value()}

    def engine_name(self) -> str:
        return self.engine.currentData()

    # ==================================================================
    #  OVERRIDING A TYPE
    # ==================================================================

    def _edit_type(self, row: int, _column: int = 0) -> None:
        """Override one row's type.

        See :meth:`xtalapp.widgets.atom_types.AtomTypeTable.
        override_type`.
        """
        if self.document is None or self.is_running:
            return
        self.table.override_type(row)

    # ==================================================================
    #  RUNNING
    # ==================================================================

    @property
    def is_running(self) -> bool:
        return self.worker is not None and self.worker.is_running

    def _open_run(self, kind: str, calculator):
        """A run folder in the workspace, when the document has one.

        A document with no workspace entry still runs; it just leaves
        nothing behind, which is exactly what this application did
        before there was anywhere to leave it.  The panel says so once
        rather than silently doing less than the user expects.
        """
        document = self.document
        entry = getattr(document, "entry", None)
        if entry is None:
            return None
        from xtal.ff.record import RunRecorder
        try:
            folder = entry.next_run(self.engine_name(), kind)
            recorder = RunRecorder(
                folder, document.structure, calculator,
                engine=self.engine_name(), options=self.options(),
                record_trajectory=(kind == "optimise"))
            recorder.header(kind.replace("-", " "))
            if self._engine_provides("types"):
                # UFF's typing table.  Writing it for an engine that
                # has no atom types would put a page of somebody
                # else's answer in the middle of this one's log.
                recorder.typing()
            recorder.topology()
        except OSError as exc:
            self.statusMessage.emit(
                f"could not write into the workspace: {exc}")
            return None
        return recorder

    def single_point(self) -> None:
        if self.document is None:
            return
        try:
            result, calculator = self.document.single_point(
                self.engine_name(), **self.options())
        except Exception as exc:                    # noqa: BLE001
            self.report.setPlainText(f"could not compute: {exc}")
            self.statusMessage.emit(str(exc))
            return
        recorder = self._open_run("single-point", calculator)
        if recorder is not None:
            recorder.energies(result, "Energy")
            recorder.log.write(f"max force      {result.max_force:.5f} "
                               f"kcal/mol/A")
            recorder.log.write(f"rms force      {result.rms_force:.5f} "
                               f"kcal/mol/A")
            recorder.close()
            self.runFinished.emit(str(recorder.folder.path))
        self.report.setPlainText(
            f"{calculator.summary()}\n\n{result.breakdown()}\n\n"
            f"max force  {result.max_force:.5f} kcal/mol/A\n"
            f"rms force  {result.rms_force:.5f} kcal/mol/A")
        # The typing warning is already the table's whole third
        # column, so only what the table cannot show is repeated here,
        # after the panel's own note.
        extra = [w for w in calculator.warnings
                 if "not sure of" not in w]
        if extra:
            self._say(" ".join([*extra, self.notes.text()]).strip())
        self.statusMessage.emit(
            f"{result.energy:.4f} kcal/mol, "
            f"max force {result.max_force:.4f} kcal/mol/A")

    def toggle_run(self) -> None:
        if self.is_running:
            self.stop()
        else:
            self.start()

    def start(self) -> None:
        if self.document is None or self.is_running:
            return
        document = self.document
        # The worker gets a copy: it reads the structure on every step
        # and caches on it, and the window keeps redrawing the one the
        # user can see.
        working = document.structure.copy()
        try:
            calculator = ENGINES.build(self.engine_name(), working,
                                       **self.options())
        except Exception as exc:                    # noqa: BLE001
            self.report.setPlainText(f"could not start: {exc}")
            self.statusMessage.emit(str(exc))
            return

        self._before = document.structure.frac.copy()
        self._before_matrix = document.structure.lattice.matrix.copy()
        frozen = document.frozen_sites() if self.freeze.isChecked() \
            else ()
        if self.freeze.isChecked() and \
                len(frozen) >= document.structure.n_sites:
            self._say("Every site is selected, so freezing the "
                      "selection would leave nothing to relax.")
            return

        self.plot.clear()
        self.plot.set_marker(None)
        self.report.setPlainText(
            f"{calculator.summary()}\n\nrunning...")
        self._recorder = self._open_run("optimise", calculator)
        if self._recorder is not None:
            self._recorder.log.write(
                f"optimiser      {self.method.currentData()}, "
                f"max {self.max_steps.value()} steps, converge below "
                f"{self.tolerance.value()} kcal/mol/A")
            self._recorder.log.write(
                f"               "
                f"{METHOD_LABELS.get(self.method.currentData(), '')}")
            if self.relax_cell.isChecked():
                self._recorder.log.write(
                    f"cell           relaxed under a "
                    f"symmetry-adapted strain at "
                    f"{self.pressure.value():g} GPa, converged below "
                    f"{self.stress_tolerance.value():g} GPa")
            if frozen:
                self._recorder.log.write(
                    f"frozen         {len(frozen)} site(s)")
            self._recorder.log.blank()
            self.runStarted.emit(str(self._recorder.folder.path))
        self.worker = OptimizationWorker(
            calculator, working, method=self.method.currentData(),
            frozen=frozen, max_steps=self.max_steps.value(),
            force_tolerance=self.tolerance.value(),
            stress_tolerance=self.stress_tolerance.value(),
            relax_cell=self.relax_cell.isChecked(),
            pressure=self.pressure.value(),
            recorder=self._recorder)
        self.worker.stepped.connect(self._on_step)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self._thread = start_in_thread(self.worker, self)
        self._set_running(True)

    def stop(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            self.statusMessage.emit("stopping the optimisation...")

    def toggle_pause(self) -> None:
        if self.worker is None:
            return
        if self.worker.is_paused:
            self.worker.resume()
            self.pause_button.setText("Pause")
        else:
            self.worker.pause()
            self.pause_button.setText("Resume")

    def _set_running(self, running: bool) -> None:
        self.run_button.setText("Stop" if running else "Optimise")
        self.pause_button.setEnabled(running)
        self.pause_button.setText("Pause")
        for widget in (self.energy_button, self.engine,
                       self.parameter_set, self.coulomb,
                       self.charges, self.vdw_cutoff, self.skin,
                       self.method, self.max_steps,
                       self.tolerance, self.freeze, self.relax_cell,
                       self.pressure, self.table):
            widget.setEnabled(not running)
        for form in self.engine_forms.values():
            form.setEnabled(not running)
        # Not the redraw rate: turning the picture off is something
        # you want to do *because* a run is going slowly.
        self.redraw.setEnabled(True)
        if not running:
            self.charges.setEnabled(self.coulomb.isChecked())
            self.pressure.setEnabled(self.relax_cell.isChecked())
            self.stress_tolerance.setEnabled(
                self.relax_cell.isChecked())
            # And an engine that cannot run stays unable to, which
            # _set_running would otherwise have just undone.
            self._show_engine()

    # -- signals from the worker ---------------------------------------

    def _on_step(self, step) -> None:
        self.plot.append(step.iteration, step.energy, step.max_force)
        if self.document is not None:
            self.document.preview_positions(step.frac, step.matrix)
        self.statusMessage.emit(step.line())

    def _on_finished(self, result) -> None:
        self._set_running(False)
        document = self.document
        if document is None:                        # pragma: no cover
            return
        if self._before is not None:
            # Undo the preview before committing, so the one command
            # that lands carries the whole run as its undo data.
            document.preview_positions(self._before,
                                       self._before_matrix)
        message = document.apply_optimization(result,
                                              before=self._before)
        self.plot.set_history(result.history)
        self.report.setPlainText(
            f"{result.summary()}\n\n"
            + "\n".join(f"{k:<16s}{v:12.4f}"
                        for k, v in sorted(result.terms.items(),
                                           key=lambda kv: -abs(kv[1]))))
        self.statusMessage.emit(message)
        self._close_run(result, document.structure)
        self.worker = None
        # Refresh first, then have the last word: refreshing rewrites
        # the note from the typing, and doing it afterwards would wipe
        # the one thing the user most needs to see.
        self.refresh()
        if getattr(result, "matrix", None) is not None:
            self._say(CELL_WARNING + " " + self.notes.text())
        if not result.converged:
            short = unconverged(result, self.tolerance.value(),
                                self.stress_tolerance.value())
            # A run that ended for a reason of its own -- a line search
            # with nowhere downhill to go -- says so; one that ran out
            # of steps or was stopped has nothing to add.
            why = (f"It ended because {result.message}. "
                   if result.message.startswith("the line search")
                   else "")
            self._say(
                "The optimiser stopped before converging"
                + (f" -- {short} still above the tolerance" if short
                   else "")
                + ", so this geometry is where it got to and not a "
                "minimum. " + why + "Run it again to carry on. "
                + self.notes.text())

    def _close_run(self, result, final) -> None:
        """Finish the log and say where it went.

        The final structure is written from the document rather than
        from the worker's copy: it is the geometry the user is looking
        at, and the one the command that just landed put there.
        """
        recorder = self._recorder
        if recorder is None:
            return
        if self.worker is not None and self.worker.recording_failed:
            self.statusMessage.emit(
                f"the run was not fully recorded: "
                f"{self.worker.recording_failed}")
            recorder.warn(f"recording stopped: "
                          f"{self.worker.recording_failed}")
        try:
            if result is None:
                recorder.failed("the optimisation failed")
            else:
                recorder.result(result, final=final)
        except OSError as exc:                      # pragma: no cover
            self.statusMessage.emit(f"could not finish the log: {exc}")
        recorder.close()
        self._recorder = None
        self.runFinished.emit(str(recorder.folder.path))

    def _on_failed(self, message: str) -> None:
        self._set_running(False)
        if self.document is not None and self._before is not None:
            self.document.preview_positions(self._before,
                                            self._before_matrix)
        self.report.setPlainText(f"the optimisation failed: {message}")
        self.statusMessage.emit(f"optimisation failed: {message}")
        if self._recorder is not None:
            self._recorder.failed(message)
            self._recorder.close()
            path = str(self._recorder.folder.path)
            self._recorder = None
            self.runFinished.emit(path)
        self.worker = None

    def closeEvent(self, event):                    # pragma: no cover
        self.stop()
        super().closeEvent(event)
