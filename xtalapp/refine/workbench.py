"""
xtalapp.refine.workbench
========================
The refinement workbench: a measured pattern, the steps that refine
against it, and the plot that shows each one -- TOPAS's run, one
window.

**Steps down the side, the plot in the middle, the step's form on the
right.**  A step is an entry of the PXRD module
(:mod:`xtal.modules.powder`), unlisted in the Modules menu, and runs
on the same worker, into the same kind of run folder, with the same
Stop as any module; what the workbench adds is that a step's answer
stays here, where the next step reads it -- the peaks just fitted and
unticked are what indexing is handed.

**One per document, and the runs go under that document.**  A
workbench opened with no structure open files its runs under an entry
named after the pattern, made the first time it runs -- the same
answer :meth:`xtalapp.module_runner.ModuleRunner._entry_for` gives a
module that builds from nothing.

**No crystallography here.**  The form values go to the module's
``run``, and the :class:`~xtal.powder.peaks.PeakFit` or
:class:`~xtal.powder.index.IndexResult` that comes back is drawn and
tabled; nothing in this file computes a number.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from xtal import powder
from xtal.modules import MODULES
from xtal.modules import powder as steps
from xtal.modules import record as module_record
from xtal.modules.job import Job
from xtal.powder.data import PowderData, PowderError
from xtalapp.dialogs.module_form import ParamForm
from xtalapp.docks import scrolling
from xtalapp.refine.bravais import BravaisBox
from xtalapp.refine.plot import RefinementPlot
from xtalapp.widgets.tone import HINT, WARNING, set_tone
from xtalapp.workers import ModuleWorker, start_in_thread

__all__ = ["RefinementWorkbench"]

#: ``(action name, list label)``, in the order a refinement goes.
STEPS = (("peaks", "Peaks"), ("index", "Index"))

PEAK_HEADERS = ("Use", "2θ (°)", "esd", "d (Å)", "Area", "FWHM (°)",
                "Flags")


class RefinementWorkbench(QMainWindow):
    """A measured pattern and the steps that refine against it."""

    #: A step finished; carries the :class:`JobResult`.  For tests and
    #: for the next step, which reads the answer.
    stepFinished = Signal(object)

    def __init__(self, window, document=None):
        super().__init__(window, Qt.Window)
        self.window_ = window
        self.document = document
        self.data: PowderData | None = None
        self.peaks = None                   # xtal.powder.peaks.PeakFit
        self.cells = None                   # xtal.powder.index.IndexResult
        self._running = ""
        self.worker: ModuleWorker | None = None
        self._folder = None
        self._entry = None
        self.module = MODULES.get("pxrd")
        name = document.title.rstrip("*") if document is not None \
            else ""
        self.setWindowTitle("Refinement" + (f" — {name}" if name
                                             else ""))

        self.steps = QListWidget()
        for _action, label in STEPS:
            self.steps.addItem(label)
        self.steps.setMaximumWidth(140)

        self.plot = RefinementPlot()
        self.table = QTableWidget(0, len(PEAK_HEADERS))
        self.table.setHorizontalHeaderLabels(PEAK_HEADERS)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemChanged.connect(self._on_use_changed)
        self.cell_table = QTableWidget(0, len(steps.INDEX_COLUMNS))
        self.cell_table.setHorizontalHeaderLabels(steps.INDEX_COLUMNS)
        self.cell_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.cell_table.horizontalHeader().setStretchLastSection(True)
        self.cell_table.verticalHeader().setVisible(False)
        self.cell_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.cell_table.setSelectionMode(
            QAbstractItemView.SingleSelection)
        self.cell_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.cell_table.itemSelectionChanged.connect(self._on_cell_chosen)
        self.tables = QStackedWidget()
        self.tables.addWidget(self.table)
        self.tables.addWidget(self.cell_table)
        middle = QSplitter(Qt.Vertical)
        middle.addWidget(self.plot)
        middle.addWidget(self.tables)
        middle.setStretchFactor(0, 3)
        middle.setStretchFactor(1, 1)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.steps)
        splitter.addWidget(middle)
        splitter.addWidget(self._side())
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([120, 660, 420])
        self.setCentralWidget(splitter)
        self.steps.currentRowChanged.connect(self.forms.setCurrentIndex)
        self.steps.currentRowChanged.connect(self.tables.setCurrentIndex)
        self.steps.setCurrentRow(0)
        self.resize(1200, 760)
        self._on_radiation()
        self._refresh()

    def _side(self) -> QWidget:
        """The data group, the step's form, and Run / Stop."""
        side = QWidget()
        layout = QVBoxLayout(side)

        self.missing = QLabel(powder.missing())
        self.missing.setWordWrap(True)
        set_tone(self.missing, WARNING)
        self.missing.setVisible(bool(powder.missing()))
        layout.addWidget(self.missing)

        data_box = QGroupBox("Pattern")
        data_layout = QVBoxLayout(data_box)
        row = QHBoxLayout()
        self.load_button = QPushButton("Load .xy...")
        self.load_button.setToolTip("Read the measured pattern to "
                                    "refine against")
        self.load_button.clicked.connect(self.choose_pattern)
        row.addWidget(self.load_button)
        self.pattern_label = QLabel("no pattern loaded")
        set_tone(self.pattern_label, HINT)
        row.addWidget(self.pattern_label, 1)
        data_layout.addLayout(row)
        self.data_form = ParamForm(steps.DATA_PARAMS[1:])
        self.data_form.changed.connect(self._on_radiation)
        data_layout.addWidget(self.data_form)
        layout.addWidget(data_box)

        self.forms = QStackedWidget()
        self.step_forms: dict[str, ParamForm] = {}
        self.bravais = BravaisBox()
        for name, label in STEPS:
            params = [p for p in steps.STEP_PARAMS[name]
                      if p.name != "bravais"]
            box = QGroupBox(label)
            box_layout = QVBoxLayout(box)
            if name == "index":
                box_layout.addWidget(self.bravais)
            self.step_forms[name] = ParamForm(params)
            box_layout.addWidget(self.step_forms[name])
            self.forms.addWidget(box)
        layout.addWidget(self.forms)

        buttons = QHBoxLayout()
        self.run_button = QPushButton("Run")
        self.run_button.clicked.connect(self.run_step)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop)
        buttons.addWidget(self.run_button)
        buttons.addWidget(self.stop_button)
        layout.addLayout(buttons)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        set_tone(self.status, HINT)
        layout.addWidget(self.status)
        layout.addStretch(1)
        area = scrolling(side)
        area.setWidget(side)
        # As wide as the form asks: this is a window of its own and
        # not a dock, so nothing else's column is held open by it, and
        # a narrower one clipped the radiation box and Stop.
        area.setMinimumWidth(side.sizeHint().width()
                             + area.verticalScrollBar().sizeHint().width())
        return area

    def _on_radiation(self) -> None:
        """A wavelength box only when the radiation is a synchrotron:
        for a tube the wavelengths are the standard ones, and a live
        box showing 0 Å reads as though that were being used."""
        values = self.data_form.values()
        self.data_form.widgets["wavelength"].setEnabled(
            values.get("radiation") == "synchrotron")

    # -- the pattern ---------------------------------------------------

    def choose_pattern(self) -> None:
        start = str(self.data.path.parent) if self.data is not None \
            and self.data.path is not None else ""
        path, _filter = QFileDialog.getOpenFileName(
            self, "Load a measured pattern", start,
            "Powder pattern (*.xy *.xye);;All files (*)")
        if path:
            self.load_pattern(path)

    def load_pattern(self, path) -> bool:
        """Read a ``.xy`` and draw it; ``False`` with the reason shown."""
        try:
            data = PowderData.from_xy(path)
        except (OSError, PowderError) as exc:
            self.say(str(exc), warn=True)
            return False
        self.data, self.peaks, self.cells = data, None, None
        self._folder = None
        self.pattern_label.setText(
            f"{data.name}: {len(data)} points, "
            f"{data.range[0]:g}-{data.range[1]:g}°"
            + (", with errors" if data.sigma is not None else ""))
        self.plot.show_observed(data.two_theta, data.intensity,
                                label=data.name)
        self._fill_table()
        self._fill_cells()
        self.say(f"loaded {Path(path).name}")
        self._refresh()
        return True

    # -- running a step ------------------------------------------------

    @property
    def current_step(self) -> str:
        return STEPS[max(self.steps.currentRow(), 0)][0]

    def values(self, step: str | None = None) -> dict:
        """Everything the step's ``run`` is handed.

        Indexing is handed the peak form's values too: with no peaks
        fitted yet it fits them itself, as the Peaks step would.
        """
        step = step or self.current_step
        values = {"xy": str(self.data.path) if self.data is not None
                  and self.data.path is not None else ""}
        values.update(self.data_form.values())
        if step == "index":
            values.update(self.step_forms["peaks"].values())
            values["bravais"] = self.bravais.value()
        values.update(self.step_forms[step].values())
        return values

    def run_step(self) -> None:
        if self.worker is not None or self.data is None:
            return
        name = self.current_step
        action = self.module.action(name)
        available = action.availability()
        if not available:
            self.say(available.reason, warn=True)
            return
        values = self.values(name)
        folder = self._open_folder(action, values)
        job = Job(structure=None, params=values, folder=folder,
                  label=f"pxrd.{name}", given=self._given(name))
        worker = ModuleWorker(self.module, action, job)
        worker.progressed.connect(self.say)
        worker.finished.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        self.worker, self._folder, self._running = worker, folder, name
        self.say(f"running {action.label.lower()}...")
        self._refresh()
        start_in_thread(worker, self)

    def _given(self, name: str):
        """What the step before hands this one: for indexing, the
        peaks as they are ticked now.  A copy of the ticks, so an
        untick made while the search runs is the next run's."""
        if name != "index" or self.peaks is None:
            return None
        return dataclasses.replace(
            self.peaks,
            peaks=[dataclasses.replace(p) for p in self.peaks.peaks])

    def stop(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            self.say("stopping...")

    def _open_folder(self, action, values):
        entry = self._entry_for()
        if entry is None:
            return None
        try:
            folder = module_record.open_run(entry, self.module, action,
                                            values)
        except OSError as exc:
            self.say(f"could not write into the workspace: {exc}",
                     warn=True)
            return None
        refresh = getattr(self.window_, "refresh_workspace", None)
        if refresh is not None:
            refresh()
        return folder

    def _entry_for(self):
        """The workspace entry this workbench's runs are filed under."""
        if self.document is not None:
            return self.document.entry
        if self._entry is None:
            workspace = getattr(self.window_, "workspace", None)
            if workspace is None or self.data is None:
                return None
            try:
                self._entry = workspace.add_document(self.data.name)
            except OSError as exc:
                self.say(f"could not write into the workspace: {exc}",
                         warn=True)
        return self._entry

    def _on_finished(self, result) -> None:
        module_record.close_run(self._folder, result)
        self.worker = None
        step, self._running = self._running, ""
        answer = result.answer if result.ok else None
        if step == "peaks" and answer and not result.cancelled:
            self.peaks, self.cells = answer, None
            self._show_peaks()
            self._fill_cells()
        elif step == "index" and answer is not None:
            # Stop keeps what the search reached; that is the point
            # of stopping a search that already looks right.
            self.cells = answer
            self._fill_cells()
        self.say(result.summary(), warn=not result.ok)
        self._refresh()
        self.stepFinished.emit(result)

    def _on_failed(self, message: str) -> None:
        module_record.close_run(self._folder, error=message)
        self.worker, self._running = None, ""
        self.say(message, warn=True)
        self._refresh()

    # -- the answer ----------------------------------------------------

    def _show_peaks(self) -> None:
        fit = self.peaks
        self.plot.show_fit(fit.two_theta, fit.y_obs, fit.y_calc,
                           fit.y_background, self._used_positions())
        self._fill_table()

    def _used_positions(self):
        if self.peaks is None:
            return ()
        return [p.two_theta for p in self.peaks.peaks if p.use]

    def _fill_table(self) -> None:
        self.table.blockSignals(True)
        peaks = self.peaks.peaks if self.peaks is not None else []
        self.table.setRowCount(len(peaks))
        for row, peak in enumerate(peaks):
            use = QTableWidgetItem()
            use.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            use.setCheckState(Qt.Checked if peak.use else Qt.Unchecked)
            use.setToolTip("Untick to keep this line out of indexing")
            self.table.setItem(row, 0, use)
            cells = (f"{peak.two_theta:.4f}", f"{peak.two_theta_esd:.4f}",
                     f"{peak.d:.5f}", f"{peak.area:.1f}",
                     f"{peak.fwhm:.4f}", ", ".join(peak.flags))
            for column, text in enumerate(cells, start=1):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                if column < len(cells):
                    item.setTextAlignment(Qt.AlignRight
                                          | Qt.AlignVCenter)
                self.table.setItem(row, column, item)
        self.table.blockSignals(False)

    def _on_use_changed(self, item) -> None:
        if self.peaks is None or item.column() != 0:
            return
        self.peaks.peaks[item.row()].use = \
            item.checkState() == Qt.Checked
        self.plot.set_ticks(self._used_positions())
        self.say(f"{self.peaks.n_used} of {len(self.peaks.peaks)} "
                 f"lines in use for indexing")

    def _fill_cells(self) -> None:
        rows = self.cells.rows if self.cells is not None else []
        self.cell_table.blockSignals(True)
        self.cell_table.clearSelection()
        self.cell_table.setRowCount(len(rows))
        confidence = steps.INDEX_COLUMNS.index("Confidence")
        groups = steps.INDEX_COLUMNS.index("Space groups")
        for r, row in enumerate(rows):
            for column, text in enumerate(steps.index_cells(row)):
                item = QTableWidgetItem(text)
                if column not in (1, 2, confidence, groups):
                    item.setTextAlignment(Qt.AlignRight
                                          | Qt.AlignVCenter)
                if column == confidence and row.caveats:
                    item.setToolTip("Not higher because: "
                                    + ", ".join(row.caveats))
                if column == groups and row.classes:
                    item.setToolTip("\n".join(
                        f"{c.symbol}: {', '.join(c.space_groups)}"
                        + (" (refuted)" if c.refuted else "")
                        for c in row.classes))
                self.cell_table.setItem(r, column, item)
        self.cell_table.blockSignals(False)
        self.plot.set_reflections(())
        if rows:
            self.cell_table.selectRow(0)

    def _on_cell_chosen(self) -> None:
        """Draw the chosen cell's lines under the peaks."""
        if self.cells is None:
            return
        chosen = self.cell_table.selectionModel().selectedRows()
        if not chosen:
            self.plot.set_reflections(())
            return
        from xtal.powder.index import lines_of

        row = self.cells.rows[chosen[0].row()]
        self.plot.set_reflections(lines_of(
            row, self.cells.wavelength, self.cells.two_theta_range))

    # -- the rest ------------------------------------------------------

    def say(self, text: str, warn: bool = False) -> None:
        self.status.setText(text)
        set_tone(self.status, WARNING if warn else HINT)

    def _refresh(self) -> None:
        running = self.worker is not None
        can_run = bool(powder.available()) and self.data is not None
        self.run_button.setEnabled(can_run and not running)
        self.stop_button.setEnabled(running)
        self.load_button.setEnabled(not running)
        if not powder.available():
            self.run_button.setToolTip(powder.missing())
        elif self.data is None:
            self.run_button.setToolTip("Load a pattern first")
        else:
            self.run_button.setToolTip("Run this step")

    def closeEvent(self, event) -> None:
        # A step left running when its window goes would have nowhere
        # to report; stop it.  MainWindow.closeEvent's workers.stop_all
        # waits for it if the whole application is going.
        self.stop()
        super().closeEvent(event)
