"""
xtalapp.docks.ff_panel
======================
The Force Field panel: set it up, look at what it decided, run it.

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
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from xtal.ff import ENGINES
from xtal.ff.optimize import (
    DEFAULT_FORCE_TOLERANCE,
    DEFAULT_MAX_STEPS,
    METHODS,
)
from xtal.ff.uff import params
from xtalapp.plot import TracePlot
from xtalapp.workers import OptimizationWorker, start_in_thread

COLUMNS = ["Site", "Type", "Sure?", "Why"]
CHARGE_SOURCES = [
    ("From the sites", "site"),
    ("Equilibrate (QEq)", "qeq"),
    ("All zero", "zero"),
]
METHOD_LABELS = {"lbfgs": "L-BFGS (fast near a minimum)",
                 "fire": "FIRE (robust far from one)"}


class ForceFieldDock(QDockWidget):
    """Atom types, a single point, and a geometry optimisation."""

    statusMessage = Signal(str)

    def __init__(self, parent=None):
        super().__init__("Force Field", parent)
        self.setObjectName("ForceFieldDock")
        self.document = None
        self.worker: OptimizationWorker | None = None
        self._thread = None
        self._before: np.ndarray | None = None

        self.engine = QComboBox()
        for engine in ENGINES:
            self.engine.addItem(engine.label, engine.name)
            self.engine.setItemData(self.engine.count() - 1,
                                    engine.description, Qt.ToolTipRole)

        self.coulomb = QCheckBox("Include electrostatics")
        self.coulomb.setToolTip(
            "Off by default, as in UFF itself: the published "
            "parameters were fitted without a Coulomb term")
        self.coulomb.toggled.connect(self._on_coulomb)
        self.charges = QComboBox()
        for label, value in CHARGE_SOURCES:
            self.charges.addItem(label, value)
        self.charges.setEnabled(False)

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

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.Stretch)

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
        self.notes.setStyleSheet("color: palette(mid);")

        self.setWidget(self._build())
        self.set_document(None)

    def _build(self) -> QWidget:
        setup = QFormLayout()
        setup.setContentsMargins(0, 0, 0, 0)
        setup.addRow("Force field", self.engine)
        setup.addRow(self.coulomb)
        setup.addRow("Charges", self.charges)
        setup_box = QGroupBox("Model")
        setup_box.setLayout(setup)

        run = QFormLayout()
        run.setContentsMargins(0, 0, 0, 0)
        run.addRow("Optimiser", self.method)
        run.addRow("Max steps", self.max_steps)
        run.addRow("Converge below", self.tolerance)
        run.addRow(self.freeze)
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
        top.addWidget(QLabel("Atom types (double-click to override)"))
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
        self.table.cellDoubleClicked.connect(self._edit_type)
        return splitter

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

    def refresh(self) -> None:
        """Redraw the type table for the current structure.

        Typing is memoised on the structure, so this is cheap between
        edits and correct after one.
        """
        enabled = self.document is not None and bool(ENGINES)
        self.widget().setEnabled(enabled)
        if not enabled or self.document.structure.n_sites == 0:
            self.table.setRowCount(0)
            self._say("")
            return
        try:
            rows = self.document.site_types()
        except Exception as exc:                    # noqa: BLE001
            self.table.setRowCount(0)
            self._say(str(exc))
            return

        self.table.setRowCount(len(rows))
        structure = self.document.structure
        for row, (index, atom, multiplicity) in enumerate(rows):
            site = structure.sites[index]
            name = site.label or f"{site.element}{index}"
            if multiplicity > 1:
                name += f"  (x{multiplicity})"
            sure = "set" if atom.overridden else atom.confidence
            for column, text in enumerate(
                    (name, atom.name, sure, atom.reason)):
                item = QTableWidgetItem(text)
                item.setData(Qt.UserRole, index)
                if column == 2 and sure == "uncertain":
                    item.setForeground(Qt.red)
                if atom.overridden:
                    font = item.font()
                    font.setItalic(True)
                    item.setFont(font)
                self.table.setItem(row, column, item)
        self._say(self._warnings_text(rows))

    def _warnings_text(self, rows) -> str:
        unsure = [r for r in rows
                  if r[1].confidence == "uncertain"
                  and not r[1].overridden]
        if not unsure:
            return ""
        names = ", ".join(r[1].name for r in unsure[:4])
        more = "" if len(unsure) <= 4 else f" and {len(unsure) - 4} more"
        return (f"{len(unsure)} site(s) have a type the typer is not "
                f"sure of ({names}{more}). Check them before trusting "
                f"the energy -- a wrong type gives a plausible number, "
                f"not an obvious error.")

    def _say(self, text: str) -> None:
        self.notes.setText(text)
        self.notes.setVisible(bool(text))

    # ==================================================================
    #  OPTIONS
    # ==================================================================

    def _on_coulomb(self, on: bool) -> None:
        self.charges.setEnabled(on)

    def options(self) -> dict:
        return {"coulomb": self.coulomb.isChecked(),
                "charges": self.charges.currentData()}

    def engine_name(self) -> str:
        return self.engine.currentData()

    # ==================================================================
    #  OVERRIDING A TYPE
    # ==================================================================

    def _edit_type(self, row: int, _column: int) -> None:
        """Offer the types UFF has for that element, and nothing else.

        Restricting the list to the element's own types is what makes
        the override safe: there is no way to ask for a carbon
        parameter on an oxygen, which would not be a bold modelling
        choice but a silent nonsense.
        """
        if self.document is None or self.is_running:
            return
        item = self.table.item(row, 0)
        if item is None:                            # pragma: no cover
            return
        index = int(item.data(Qt.UserRole))
        site = self.document.structure.sites[index]
        choices = params.types_for(site.element)
        if not choices:                             # pragma: no cover
            return
        current = self.table.item(row, 1).text()
        options = ["(let the force field decide)", *choices]
        from PySide6.QtWidgets import QInputDialog

        start = options.index(current) if current in options else 0
        chosen, ok = QInputDialog.getItem(
            self, "Atom type",
            f"UFF type for {site.label or site.element} "
            f"(and its whole symmetry orbit):",
            options, start, False)
        if not ok:
            return
        name = None if chosen == options[0] else chosen
        self.statusMessage.emit(
            self.document.set_atom_type([index], name))

    # ==================================================================
    #  RUNNING
    # ==================================================================

    @property
    def is_running(self) -> bool:
        return self.worker is not None and self.worker.is_running

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
        frozen = document.frozen_sites() if self.freeze.isChecked() \
            else ()
        if self.freeze.isChecked() and \
                len(frozen) >= document.structure.n_sites:
            self._say("Every site is selected, so freezing the "
                      "selection would leave nothing to relax.")
            return

        self.plot.clear()
        self.report.setPlainText(
            f"{calculator.summary()}\n\nrunning...")
        self.worker = OptimizationWorker(
            calculator, working, method=self.method.currentData(),
            frozen=frozen, max_steps=self.max_steps.value(),
            force_tolerance=self.tolerance.value())
        self.worker.stepped.connect(self._on_step)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self._thread = start_in_thread(self.worker)
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
        for widget in (self.energy_button, self.engine, self.coulomb,
                       self.charges, self.method, self.max_steps,
                       self.tolerance, self.freeze, self.table):
            widget.setEnabled(not running)
        if not running:
            self.charges.setEnabled(self.coulomb.isChecked())

    # -- signals from the worker ---------------------------------------

    def _on_step(self, step) -> None:
        self.plot.append(step.iteration, step.energy, step.max_force)
        if self.document is not None:
            self.document.preview_positions(step.frac)
        self.statusMessage.emit(step.line())

    def _on_finished(self, result) -> None:
        self._set_running(False)
        document = self.document
        if document is None:                        # pragma: no cover
            return
        if self._before is not None:
            # Undo the preview before committing, so the one command
            # that lands carries the whole run as its undo data.
            document.preview_positions(self._before)
        message = document.apply_optimization(result,
                                              before=self._before)
        self.plot.set_history(result.history)
        self.report.setPlainText(
            f"{result.summary()}\n\n"
            + "\n".join(f"{k:<16s}{v:12.4f}"
                        for k, v in sorted(result.terms.items(),
                                           key=lambda kv: -abs(kv[1]))))
        self.statusMessage.emit(message)
        self.worker = None
        # Refresh first, then have the last word: refreshing rewrites
        # the note from the typing, and doing it afterwards would wipe
        # the one thing the user most needs to see.
        self.refresh()
        if not result.converged:
            self._say(
                "The optimiser stopped before converging, so this "
                "geometry is where it got to and not a minimum. Run "
                "it again to carry on. " + self.notes.text())

    def _on_failed(self, message: str) -> None:
        self._set_running(False)
        if self.document is not None and self._before is not None:
            self.document.preview_positions(self._before)
        self.report.setPlainText(f"the optimisation failed: {message}")
        self.statusMessage.emit(f"optimisation failed: {message}")
        self.worker = None

    def closeEvent(self, event):                    # pragma: no cover
        self.stop()
        super().closeEvent(event)
