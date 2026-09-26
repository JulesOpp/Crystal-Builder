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

**Rietveld is watched, and lands as one undo step.**  Its frames move
the atoms through ``Document.preview_positions`` -- no history, no
modified flag -- and redraw the calculated curve in place.  A finished
fit puts the atoms back where they started and then commits the
refined structure through the Document, so Ctrl+Z undoes the whole
run; Stop or a failure puts them back and commits nothing.  The
document is the one this window was opened over, never the tab in
front.
"""

from __future__ import annotations

import dataclasses
import datetime
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from xtal import powder
from xtal.core.structure import Change
from xtal.modules import MODULES
from xtal.modules import powder as steps
from xtal.modules import record as module_record
from xtal.modules.job import Job
from xtal.powder.data import PowderData, PowderError
from xtalapp.dialogs.module_form import ParamForm
from xtalapp.docks import scrolling
from xtalapp.refine.bravais import BravaisBox
from xtalapp.refine.cell import CellBox
from xtalapp.refine.plot import RefinementPlot
from xtalapp.widgets.tone import HINT, WARNING, set_tone
from xtalapp.workers import ModuleWorker, start_in_thread

__all__ = ["RefinementWorkbench"]

#: ``(action name, list label)``, in the order a refinement goes.
STEPS = (("peaks", "Peaks"), ("index", "Index"), ("pawley", "Pawley"),
         ("rietveld", "Rietveld"), ("auto", "Automatic"))

#: What the Run button says on each step.
RUN_LABELS = {"peaks": "Find peaks", "index": "Index",
              "pawley": "Fit Pawley", "rietveld": "Refine",
              "auto": "Run all"}

#: Parameters a step declares for ``xtal run`` that the workbench asks
#: through a widget of its own rather than the form: the cell box
#: writes ``cell`` and ``hold``.
_NOT_IN_FORM = {"index": ("bravais",), "pawley": ("cell", "hold"),
                "rietveld": ("cell", "hold")}

HISTORY_HEADERS = ("#", "Time", "Rwp (%)", "Rp (%)", "GoF", "Plan",
                   "Moved (Å)", "Status")

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
        self.pawley = None                  # xtal.powder.pawley.PawleyFit
        self.rietveld = None            # xtal.powder.rietveld.RietveldFit
        self.auto = None                    # xtal.powder.auto.AutoResult
        #: where the atoms were when a Rietveld run started: what Stop
        #: puts back, and what the one undo step undoes to
        self._before = None
        #: every Rietveld configuration reached against this pattern,
        #: the structure before the first run at the top -- SHELXLE's
        #: list of .res files, which a person walks back along
        self.history: list[HistoryEntry] = []
        self._history_at: int | None = None
        #: what the running step last said, and when it started: a
        #: stage that runs for minutes says so by the second rather
        #: than looking stalled
        self._said, self._started = "", 0.0
        self._ticker = QTimer(self)
        self._ticker.setInterval(1000)
        self._ticker.timeout.connect(self._tick)
        self._run_values: dict = {}
        self._framed = False
        self._running = ""
        self._cell_rows: list = []
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
        self.table = _table(PEAK_HEADERS)
        self.table.itemChanged.connect(self._on_use_changed)
        self.cell_table = _table(steps.INDEX_COLUMNS, rows=True)
        self.cell_table.itemSelectionChanged.connect(self._on_cell_chosen)
        self.reflection_table = _table(steps.REFLECTION_COLUMNS)
        self.reflection_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers)
        self.refined_table = _table(("Parameter", "Value", "esd"))
        self.refined_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers)
        self.tables = QStackedWidget()
        self.tables.addWidget(self.table)
        self.tables.addWidget(self.cell_table)
        self.tables.addWidget(self.reflection_table)
        self.rietveld_tabs = QTabWidget()
        self.rietveld_tabs.addTab(self.refined_table, "Refined")
        self.rietveld_tabs.addTab(self._history_page(), "History")
        self.tables.addWidget(self.rietveld_tabs)
        self.auto_table = _table(steps.AUTO_COLUMNS, rows=True)
        self.auto_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.auto_table.setToolTip(
            "Every Pawley fit the run made, best first.  Choose a row "
            "to draw its fit; it becomes the Pawley step's answer, so "
            "Apply cell and New structure work from it.")
        self.auto_table.itemSelectionChanged.connect(self._on_auto_chosen)
        self.tables.addWidget(self.auto_table)
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
        splitter.setSizes([120, 1150, 450])
        self.setCentralWidget(splitter)
        self.steps.currentRowChanged.connect(self.forms.setCurrentIndex)
        self.steps.currentRowChanged.connect(self.tables.setCurrentIndex)
        self.steps.currentRowChanged.connect(self._redraw)
        self.steps.setCurrentRow(0)
        self.resize(*_default_size())
        self._fill_from_structure()
        self._show_pawley_result()
        self._show_rietveld_result()
        self._on_radiation()
        self._show_plan_note()
        self._fill_history()
        self._show_auto_result()
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
        self.cell_box = CellBox("Cell")
        self.cell_box.setToolTip(
            "The numbers the space group leaves free; the rest follow "
            "from them.  Untick Refine to hold one at the value given.")
        self.rietveld_cell = CellBox("Cell of the structure",
                                     editable=False)
        self.rietveld_cell.setToolTip(
            "The structure's own cell, refined number by number: "
            "untick Refine to hold one")
        for name, label in STEPS:
            params = [p for p in steps.STEP_PARAMS[name]
                      if p.name not in _NOT_IN_FORM.get(name, ())]
            box = QGroupBox(label)
            box_layout = QVBoxLayout(box)
            if name == "index":
                box_layout.addWidget(self.bravais)
            refines = name in ("pawley", "rietveld")
            form = ParamForm(params, notes=refines)
            self.step_forms[name] = form
            box_layout.addWidget(form)
            if name == "peaks":
                box_layout.addWidget(self._peaks_box())
            if name == "index":
                box_layout.addLayout(self._index_box())
            if name == "pawley":
                # the group decides which numbers the cell has, so the
                # cell sits under it
                form.layout().insertRow(1, self.cell_box)
                form.widgets["space_group"].textChanged.connect(
                    self.cell_box.set_space_group)
                box_layout.addWidget(self._pawley_box())
            if name == "auto":
                box_layout.addWidget(self._auto_box())
            if name == "rietveld":
                # what the plan chosen above it does, stage by stage
                self.plan_note = _Paragraph("")
                set_tone(self.plan_note, HINT)
                form.layout().insertRow(1, self.plan_note)
                form.changed.connect(self._show_plan_note)
                form.layout().insertRow(
                    form.layout().rowCount(), self.rietveld_cell)
                box_layout.addWidget(self._rietveld_box())
            # the stack is as tall as its tallest step; a shorter one
            # sits at the top rather than spread down the column
            box_layout.addStretch(1)
            self.forms.addWidget(box)
        layout.addWidget(self.forms)
        layout.addStretch(1)
        # A stack is as tall as its tallest page, which is Rietveld's;
        # sized that way, Peaks and Index scrolled a screen of nothing
        # and put Run below the bottom of the window.
        self.forms.currentChanged.connect(self._fit_form)
        self._fit_form(0)
        area = scrolling(side)
        area.setWidget(side)
        # As wide as the form asks: this is a window of its own and
        # not a dock, so nothing else's column is held open by it, and
        # a narrower one clipped the radiation box and Stop.
        area.setMinimumWidth(max(
            self.forms.widget(k).sizeHint().width()
            for k in range(self.forms.count()))
            + 2 * layout.contentsMargins().left()
            + area.verticalScrollBar().sizeHint().width())

        # Run, Stop and what they said stay in sight below the form,
        # however long it is.
        column = QWidget()
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.addWidget(area, 1)
        bottom = QVBoxLayout()
        bottom.setContentsMargins(9, 0, 9, 9)
        buttons = QHBoxLayout()
        self.run_button = QPushButton(RUN_LABELS["peaks"])
        self.run_button.clicked.connect(lambda: self.run_step())
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop)
        buttons.addWidget(self.run_button)
        buttons.addWidget(self.stop_button)
        bottom.addLayout(buttons)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        set_tone(self.status, HINT)
        bottom.addWidget(self.status)
        column_layout.addLayout(bottom)
        return column

    def _fit_form(self, index: int) -> None:
        """The stack as tall as the page shown, not the tallest one."""
        for k in range(self.forms.count()):
            policy = QSizePolicy.Preferred if k == index \
                else QSizePolicy.Ignored
            self.forms.widget(k).setSizePolicy(policy, policy)
        # the stack caches its hint; a policy changed under it is not
        # news to it until it is told
        self.forms.layout().invalidate()
        self.forms.updateGeometry()

    def _peaks_box(self) -> QWidget:
        """Lines placed by hand, Refine, and the single-line overlay."""
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.addWidget(QLabel("Add peaks at"))
        self.add_edit = QLineEdit()
        self.add_edit.setPlaceholderText("2θ, separated by commas")
        self.add_edit.setToolTip(
            "Place lines by hand where Find peaks missed one -- a "
            "shoulder, a weak line.  They are fitted by Refine.")
        self.add_edit.returnPressed.connect(self.add_peaks)
        row.addWidget(self.add_edit, 1)
        self.add_button = QPushButton("Add")
        self.add_button.clicked.connect(self.add_peaks)
        row.addWidget(self.add_button)
        layout.addLayout(row)
        self.refine_button = QPushButton("Refine peaks")
        self.refine_button.setToolTip(
            "Fit the lines in use together over the whole range, on a "
            "Chebyshev background of the terms above: position, area "
            "and width of each.  Lines out of use are removed.")
        self.refine_button.clicked.connect(
            lambda: self.run_step("refine_peaks"))
        layout.addWidget(self.refine_button)
        self.components_box = QCheckBox("Show individual peaks")
        self.components_box.setChecked(True)
        self.components_box.setToolTip(
            "Draw each line in use on its own over the background")
        self.components_box.toggled.connect(self.plot.show_components)
        layout.addWidget(self.components_box)
        return box

    def _index_box(self) -> QVBoxLayout:
        """How the cell table is ordered, and where a row goes."""
        layout = QVBoxLayout()
        row = QHBoxLayout()
        row.addWidget(QLabel("Sort cells by"))
        self.sort_box = QComboBox()
        for key, label in steps.INDEX_SORTS:
            self.sort_box.addItem(label, key)
        self.sort_box.setToolTip(
            "GoF ranks by how well the line positions are explained; "
            "GoF / (unindexed + 1) makes a cell pay for each line it "
            "leaves unexplained, as TOPAS's second ordering does.  "
            "RietX's rank weighs its whole figure-of-merit panel and "
            "whether its engines agree.")
        self.sort_box.currentIndexChanged.connect(
            lambda _i: self._fill_cells())
        row.addWidget(self.sort_box, 1)
        layout.addLayout(row)
        hint = QLabel("The highlighted cell and its space group are "
                      "copied into the Pawley step.")
        hint.setWordWrap(True)
        set_tone(hint, HINT)
        layout.addWidget(hint)
        return layout

    def _pawley_box(self) -> QGroupBox:
        """The fit's figures, and the two things a cell is for."""
        box = QGroupBox("Result")
        layout = QVBoxLayout(box)
        self.pawley_label = QLabel("")
        self.pawley_label.setWordWrap(True)
        self.pawley_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse)
        layout.addWidget(self.pawley_label)
        self.apply_button = QPushButton("Apply cell to the structure")
        self.apply_button.clicked.connect(self.apply_cell)
        self.new_button = QPushButton("New structure from this cell")
        self.new_button.setToolTip(
            "An empty structure with this cell and space group, filed "
            "in the workspace like File > New")
        self.new_button.clicked.connect(self.new_structure)
        layout.addWidget(self.apply_button)
        layout.addWidget(self.new_button)
        explain = QLabel(
            "A Pawley fit has no atoms: it refines a cell, and each "
            "reflection's intensity is a free number.  <b>Apply cell to "
            "the structure</b> puts the refined a, b, c, α, β, γ on the "
            "structure this window was opened over, its atoms kept at "
            "the same fractional coordinates -- one undo step.  "
            "<b>New structure from this cell</b> opens an empty "
            "structure in a new tab, with this cell and space group "
            "and no atoms, to build or solve a structure in.")
        explain.setWordWrap(True)
        set_tone(explain, HINT)
        layout.addWidget(explain)
        return box

    def _rietveld_box(self) -> QGroupBox:
        """The fit's figures, and what finishing did to the document."""
        box = QGroupBox("Result")
        layout = QVBoxLayout(box)
        self.rietveld_label = QLabel("")
        self.rietveld_label.setWordWrap(True)
        self.rietveld_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse)
        layout.addWidget(self.rietveld_label)
        explain = QLabel(
            "Refines the atoms of the structure this window was opened "
            "over.  The atoms move in the viewer as it runs; a finished "
            "fit is one undo step, and Stop puts them back.  Atoms are "
            "never added, removed or bonded.")
        explain.setWordWrap(True)
        set_tone(explain, HINT)
        layout.addWidget(explain)
        return box

    def _auto_box(self) -> QGroupBox:
        """What the run reads from the other steps, and what it found."""
        box = QGroupBox("Result")
        layout = QVBoxLayout(box)
        self.auto_label = QLabel("")
        self.auto_label.setWordWrap(True)
        self.auto_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.auto_label)
        explain = QLabel(
            "Fits the peaks, indexes them, and Pawley fits the leading "
            "cells in their leading space-group classes, ranked by "
            "Rwp.  Each stage asks what its own step's form says: the "
            "lattices and budget on Index, the range and broadening on "
            "Pawley, the plan and boxes on Rietveld.  It stops at the "
            "table unless Continue to Rietveld is ticked, and then "
            "refines the structure only if its cell is a row's.")
        explain.setWordWrap(True)
        set_tone(explain, HINT)
        layout.addWidget(explain)
        return box

    def _history_page(self) -> QWidget:
        """Every fit reached, with its figures, and the way back."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self.history_table = _table(HISTORY_HEADERS, rows=True)
        self.history_table.setToolTip(
            "Every Rietveld fit against this pattern, and the "
            "structure before the first.  Double-click a row, or "
            "choose it and Restore, to go back to it.")
        self.history_table.cellDoubleClicked.connect(
            lambda row, _column: self.restore_history(row))
        layout.addWidget(self.history_table, 1)
        row = QHBoxLayout()
        self.restore_button = QPushButton("Restore this configuration")
        self.restore_button.setToolTip(
            "Put the atoms, the cell and the boxes back as they were "
            "at this point: one undo step.  The next fit starts from "
            "there, and the later rows stay.")
        self.restore_button.clicked.connect(lambda: self.restore_history(
            self.history_table.currentRow()))
        row.addWidget(self.restore_button)
        row.addStretch(1)
        layout.addLayout(row)
        return page

    def _show_plan_note(self) -> None:
        """What the chosen plan does, and the boxes it overrides greyed:
        RietX's plans never read them, and a live box beside one
        claimed a say it did not have."""
        values = self.values("rietveld")
        self.plan_note.setText(steps.rietveld_plan_note(values))
        planned = bool(values.get("plan"))
        form = self.step_forms["rietveld"]
        for name in steps.PLAN_DECIDES:
            widget = form.widgets.get(name)
            if widget is not None:
                widget.setEnabled(not planned)
        self.rietveld_cell.setEnabled(not planned)
        # the note is a paragraph for a plan and one line for the
        # boxes; the page was measured with the old one, and clipped
        # its bottom rows once the note grew
        self._fit_form(self.forms.currentIndex())

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
        # A native file dialog hands activation back to the main
        # window when it closes, which then stands in front of this one
        # as though it had closed.
        self.raise_()
        self.activateWindow()
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
        self.pawley = self.rietveld = self.auto = None
        # a history is of fits to one pattern
        self.history, self._history_at = [], None
        self._fill_history()
        self._folder = None
        self.pattern_label.setText(
            f"{data.name}: {len(data)} points, "
            f"{data.range[0]:g}-{data.range[1]:g}°"
            + (", with errors" if data.sigma is not None else ""))
        self.plot.show_observed(data.two_theta, data.intensity,
                                label=data.name)
        self._fill_table()
        self._fill_cells()
        self._fill_reflections()
        self._fill_auto()
        self._show_pawley_result()
        self._show_rietveld_result()
        # the range a fit runs over starts as the whole measurement
        lo, hi = data.range
        for step in ("peaks", "pawley", "rietveld"):
            self.step_forms[step].set_values({"start": lo, "finish": hi})
        self.say(f"loaded {Path(path).name}")
        self._refresh()
        return True

    # -- running a step ------------------------------------------------

    @property
    def current_step(self) -> str:
        return STEPS[max(self.steps.currentRow(), 0)][0]

    def _form_of(self, action: str) -> str:
        """The step whose form an action reads: Refine peaks is the
        Peaks step's second button."""
        return "peaks" if action == "refine_peaks" else action

    def values(self, step: str | None = None) -> dict:
        """Everything the step's ``run`` is handed.

        Indexing is handed the peak form's values too: with no peaks
        fitted yet it fits them itself, as the Peaks step would.
        """
        step = self._form_of(step or self.current_step)
        values = {"xy": str(self.data.path) if self.data is not None
                  and self.data.path is not None else ""}
        values.update(self.data_form.values())
        if step == "auto":
            return self._auto_values(values)
        if step == "index":
            values.update(self.step_forms["peaks"].values())
            values["bravais"] = self.bravais.value()
        values.update(self.step_forms[step].values())
        if step == "pawley":
            values["cell"] = self.cell_box.value()
            values["hold"] = self.cell_box.hold()
        if step == "rietveld":
            settings = getattr(self.window_, "settings", None)
            if settings is not None:
                values["frame_interval"] = \
                    settings.preview_interval / 1000.0
            held = self.rietveld_cell.hold()
            values["hold"] = held
            values["cell"] = len([n for n in held.split(",")
                                  if n.strip()]) \
                < len(self.rietveld_cell.free())
        return values

    def _auto_values(self, values: dict) -> dict:
        """The automatic run asks every step's own form: peaks and index
        as they are, Pawley and Rietveld under their prefixes."""
        peaks = self.step_forms["peaks"].values()
        values.update({k: v for k, v in peaks.items()
                       if k != "background_terms"})
        values.update(self.step_forms["index"].values())
        values["bravais"] = self.bravais.value()
        values.update(self.step_forms["auto"].values())
        for step in ("pawley", "rietveld"):
            own = self.values(step)
            for name in ("xy", *self.data_form.values()):
                own.pop(name, None)
            if step == "pawley":
                for name in ("cell", "space_group", "hold"):
                    own.pop(name, None)
            interval = own.pop("frame_interval", None)
            if interval is not None:
                values["frame_interval"] = interval
            values.update({f"{step}_{k}": v for k, v in own.items()})
        return values

    def run_step(self, name: str | None = None) -> None:
        """Run a step's action -- the current step's, or ``name``."""
        if self.worker is not None or self.data is None:
            return
        name = name or self.current_step
        if name == "refine_peaks" and self.peaks is None:
            self.say("Find peaks (or add some) before refining them",
                     warn=True)
            return
        refused = self._rietveld_refused() if name == "rietveld" else ""
        if refused:
            self.say(refused, warn=True)
            return
        action = self.module.action(name)
        available = action.availability()
        if not available:
            self.say(available.reason, warn=True)
            return
        values = self.values(name)
        folder = self._open_folder(action, values)
        structure = None
        if name == "auto" and values.get("continue_rietveld") \
                and not self._rietveld_refused():
            structure = self._start_rietveld(self.values("rietveld"))
        if name == "rietveld":
            structure = self._start_rietveld(values)
        job = Job(structure=structure, params=values, folder=folder,
                  label=f"pxrd.{name}", given=self._given(name))
        worker = ModuleWorker(self.module, action, job)
        worker.progressed.connect(self._progress)
        worker.updated.connect(self._on_frame)
        worker.finished.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        self.worker, self._folder, self._running = worker, folder, name
        self._started = time.monotonic()
        self._progress(f"running {action.label.lower()}...")
        self._ticker.start()
        self._refresh()
        start_in_thread(worker, self)

    def _start_rietveld(self, values: dict):
        """The structure a Rietveld run is handed, and what Stop and the
        history need to know about where it started."""
        structure = self.document.structure.copy()
        self._before = (structure.frac.copy(),
                        structure.lattice.matrix.copy())
        self._framed = False
        self._run_values = dict(values)
        if not self.history:
            self.history.append(HistoryEntry(
                structure=structure.copy(), values=dict(values),
                fit=None, when=datetime.datetime.now()))
        return structure

    def _given(self, name: str):
        """What the step before hands this one: for indexing, the
        peaks as they are ticked now.  A copy of the ticks, so an
        untick made while the search runs is the next run's."""
        if name not in ("index", "refine_peaks") or self.peaks is None:
            return None
        return dataclasses.replace(
            self.peaks,
            peaks=[dataclasses.replace(p) for p in self.peaks.peaks])

    def _progress(self, text: str) -> None:
        self._said = text
        self._tick()

    def _tick(self) -> None:
        if self.worker is None:
            self._ticker.stop()
            return
        elapsed = int(time.monotonic() - self._started)
        self.say(f"{self._said} ({elapsed // 60}:{elapsed % 60:02d})")

    def stop(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            self._progress("stopping...")

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
        self._ticker.stop()
        step, self._running = self._running, ""
        answer = result.answer if result.ok else None
        if step in ("peaks", "refine_peaks") and answer \
                and not result.cancelled:
            self.peaks, self.cells = answer, None
            self._show_peaks()
            self._fill_cells()
        elif step == "index" and answer is not None:
            # Stop keeps what the search reached; that is the point
            # of stopping a search that already looks right.
            self.cells = answer
            self._fill_cells()
        elif step == "pawley" and answer and not result.cancelled:
            self.pawley = answer
            self._draw_pawley()
            self._fill_reflections()
            self._show_pawley_result()
        if step == "auto" and answer is not None:
            self._take_auto(answer)
        if step == "rietveld":
            self._finish_rietveld(answer if not result.cancelled
                                  else None)
        if step == "auto" and self._before is not None:
            self._finish_rietveld(
                answer.rietveld if answer is not None
                and not result.cancelled else None)
            if answer is not None and answer.rietveld is None:
                self._draw_auto_row()
        self.say(result.summary(), warn=not result.ok)
        self._refresh()
        self.stepFinished.emit(result)

    def _on_failed(self, message: str) -> None:
        module_record.close_run(self._folder, error=message)
        step, self.worker, self._running = self._running, None, ""
        self._ticker.stop()
        if step == "rietveld" or self._before is not None:
            self._finish_rietveld(None)
        self.say(message, warn=True)
        self._refresh()

    # -- Rietveld --------------------------------------------------------

    def _rietveld_refused(self) -> str:
        if self.document is None or not self.document.structure.sites:
            return ("Rietveld refines a structure's atoms: open the "
                    "structure, and open this window from it")
        if self.document.is_playing:
            return "Leave playback before refining"
        return ""

    def _on_frame(self, frame) -> None:
        """One moment of a running fit: the curve redrawn in place and
        the atoms moved, neither of them an edit."""
        if self._running not in ("rietveld", "auto") \
                or self.document is None:
            return
        if not self._framed:
            # the first frame lays the plot out on the fit's own grid;
            # every later one only moves the calculated line
            self.plot.show_fit(frame.two_theta, frame.y_obs, frame.y_calc)
            self._framed = True
        else:
            self.plot.show_calculated(frame.y_calc)
        self.document.preview_positions(frame.frac, frame.matrix)
        self._progress(f"Rietveld: {frame.stage}...")

    def _finish_rietveld(self, fit) -> None:
        """Put the atoms back where the run started, and then -- for a
        fit that finished -- commit it as one undo step."""
        before, self._before = self._before, None
        if self.document is None:
            return
        if before is not None and len(before[0]) != len(
                self.document.structure.sites):
            # edited under the run: neither the start nor the fit
            # describes these atoms any more
            self.say("the structure was edited while it was being "
                     "refined; the fit was not applied", warn=True)
            return
        if before is not None:
            self.document.preview_positions(*before)
        if fit is None:
            if self.rietveld is not None:
                self._draw_rietveld()
            return
        self.rietveld = fit
        self.document.replace_structure(
            fit.structure.copy(), "Rietveld refinement",
            Change.POSITIONS | Change.CELL | Change.METADATA)
        self.history.append(HistoryEntry(
            structure=fit.structure.copy(), values=self._run_values,
            fit=fit, when=datetime.datetime.now(), folder=self._folder))
        self._history_at = len(self.history) - 1
        self._fill_history()
        self._draw_rietveld()
        self._fill_rietveld_cell()
        self._show_rietveld_result()

    def _draw_rietveld(self) -> None:
        fit = self.rietveld
        if fit is None:
            if self.data is not None:
                self.plot.show_observed(self.data.two_theta,
                                        self.data.intensity,
                                        label=self.data.name)
            return
        self.plot.show_fit(fit.two_theta, fit.y_obs, fit.y_calc,
                           fit.y_background, fit.ticks)

    # -- the history -----------------------------------------------------

    def _fill_history(self) -> None:
        table = self.history_table
        table.setRowCount(len(self.history))
        plans = dict(next(p for p in steps.RIETVELD_PARAMS
                          if p.name == "plan").values_and_labels())
        for r, entry in enumerate(self.history):
            fit = entry.fit
            status = "start" if fit is None else fit.status
            plan = plans.get(entry.values.get("plan", ""), "")
            texts = (str(r), entry.when.strftime("%H:%M:%S"),
                     _percent(fit and fit.rwp), _percent(fit and fit.rp),
                     f"{fit.gof:.3f}" if fit is not None else "--",
                     "" if fit is None else plan,
                     f"{fit.moved:.3f}" if fit is not None else "--",
                     status)
            for column, text in enumerate(texts):
                item = QTableWidgetItem(text)
                if column in (0, 2, 3, 4, 6):
                    item.setTextAlignment(Qt.AlignRight
                                          | Qt.AlignVCenter)
                font = item.font()
                font.setBold(r == self._history_at)
                item.setFont(font)
                if entry.folder is not None:
                    item.setToolTip(str(entry.folder))
                table.setItem(r, column, item)
        self.restore_button.setEnabled(bool(self.history)
                                       and self.worker is None)

    def restore_history(self, row: int) -> bool:
        """Back to the configuration of history row ``row``: its atoms
        and cell on the document as one undo step, its boxes in the
        form, and its fit on the plot.  Nothing is taken off the
        list; the next fit is appended, as SHELXLE appends."""
        if not 0 <= row < len(self.history) or self.worker is not None \
                or self.document is None:
            return False
        entry = self.history[row]
        if len(entry.structure.sites) != len(
                self.document.structure.sites):
            self.say("the structure has gained or lost atoms since this "
                     "fit, so it cannot be put back", warn=True)
            return False
        label = "the start" if entry.fit is None else f"fit {row}"
        self.document.replace_structure(
            entry.structure.copy(), f"Restore Rietveld {label}",
            Change.POSITIONS | Change.CELL | Change.METADATA)
        self.step_forms["rietveld"].set_values(entry.values)
        self.rietveld_cell.set_hold(entry.values.get("hold", ""))
        self.rietveld = entry.fit
        self._history_at = row
        self._fill_rietveld_cell()
        self._draw_rietveld()
        self._show_rietveld_result()
        self._fill_history()
        self.say(f"restored {label}"
                 + (f": Rwp {100 * entry.fit.rwp:.2f} %"
                    if entry.fit is not None else ""))
        return True

    def _show_rietveld_result(self) -> None:
        fit = self.rietveld
        self.rietveld_label.setText(
            steps.rietveld_summary(fit) if fit is not None
            else "Run a Rietveld fit to refine the structure.")
        set_tone(self.rietveld_label,
                 HINT if fit is None or fit.converged else WARNING)
        notes = steps.refined_notes(fit) if fit is not None else {}
        self.step_forms["rietveld"].set_notes(notes)
        self.rietveld_cell.set_refined(notes)
        rows = list(fit.refined.items()) if fit is not None else []
        self.refined_table.setRowCount(len(rows))
        for r, (path, (value, esd)) in enumerate(rows):
            for column, text in enumerate(
                    (path, f"{value:.6g}", f"{esd:.2g}" if esd else "")):
                item = QTableWidgetItem(text)
                if column:
                    item.setTextAlignment(Qt.AlignRight
                                          | Qt.AlignVCenter)
                self.refined_table.setItem(r, column, item)

    def _fill_rietveld_cell(self) -> None:
        """The structure's cell, as Rietveld will start from it."""
        structure = self.document.structure \
            if self.document is not None else None
        if structure is None:
            return
        self.rietveld_cell.set_space_group(structure.space_group.hm)
        self.rietveld_cell.set_value(
            tuple(float(v) for v in structure.lattice.parameters))

    # -- the answer ----------------------------------------------------

    def _show_peaks(self) -> None:
        fit = self.peaks
        self.plot.show_fit(fit.two_theta, fit.y_obs, fit.y_calc,
                           fit.y_background, self._used_positions())
        self.plot.set_components(fit.y_background, fit.curves())
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
        self.plot.set_components(self.peaks.y_background,
                                 self.peaks.curves())
        self.say(f"{self.peaks.n_used} of {len(self.peaks.peaks)} "
                 f"lines in use for indexing")

    def _fill_cells(self) -> None:
        rows = [] if self.cells is None else steps.sorted_rows(
            self.cells, self.sort_box.currentData() or "rank")
        self._cell_rows = rows
        gof = self.cell_table.horizontalHeaderItem(
            steps.INDEX_COLUMNS.index("GoF"))
        name = steps.gof_name(self.cells) if self.cells is not None \
            else "--"
        gof.setToolTip(
            f"{name}: how well the cell explains the line positions, "
            f"higher better -- the figure TOPAS calls GOF.  M20 when "
            f"20 or more lines are in use, RietX's M_sym below that.")
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

        row = self._cell_rows[chosen[0].row()]
        self.plot.set_reflections(lines_of(
            row, self.cells.wavelength, self.cells.two_theta_range))
        self.step_forms["pawley"].set_values(
            {"space_group": row.fit_group})
        self.cell_box.set_value(row.cell)

    def add_peaks(self) -> None:
        """Lines placed by hand at the typed 2θ, in use and unfitted."""
        if self.data is None:
            return
        try:
            positions = steps._positions(self.add_edit.text())
            if not positions:
                return
            if self.peaks is None:
                from xtal.powder.peaks import empty_fit

                self.peaks = empty_fit(self.data,
                                       steps.radiation_of(self.values()),
                                       *self._peak_range())
            added = self.peaks.add(positions, self.data)
        except PowderError as exc:
            self.say(str(exc), warn=True)
            return
        self.add_edit.clear()
        self._show_peaks()
        self.say(f"added {len(added)} line(s) -- Refine peaks fits them")
        self._refresh()

    def _peak_range(self) -> tuple[float, float]:
        values = self.step_forms["peaks"].values()
        lo, hi = self.data.range
        return (max(float(values.get("start") or lo), lo),
                min(float(values.get("finish") or hi), hi))

    # -- Pawley --------------------------------------------------------

    def _fill_from_structure(self) -> None:
        """The open structure's cell and group, as the Pawley step's
        starting point: refining a known phase's cell against a new
        measurement needs no indexing."""
        structure = self.document.structure \
            if self.document is not None else None
        if structure is None or not structure.sites:
            return
        self.step_forms["pawley"].set_values(
            {"space_group": structure.space_group.hm})
        self.cell_box.set_value(
            tuple(float(v) for v in structure.lattice.parameters))
        self._fill_rietveld_cell()

    def _draw_pawley(self) -> None:
        fit = self.pawley
        self.plot.show_fit(fit.two_theta, fit.y_obs, fit.y_calc,
                           fit.y_background, fit.ticks)

    def _fill_reflections(self) -> None:
        rows = self.pawley.reflections if self.pawley is not None \
            else []
        self.reflection_table.setRowCount(len(rows))
        for r, reflection in enumerate(rows):
            h, k, m = reflection.hkl
            cells = (str(h), str(k), str(m), f"{reflection.d:.5f}",
                     f"{reflection.two_theta:.4f}",
                     str(reflection.multiplicity),
                     f"{reflection.intensity:.2f}")
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.reflection_table.setItem(r, column, item)

    def _show_pawley_result(self) -> None:
        fit = self.pawley
        notes = steps.refined_notes(fit) if fit is not None else {}
        self.step_forms["pawley"].set_notes(notes)
        self.cell_box.set_refined(notes)
        self.pawley_label.setText(
            steps.pawley_summary(fit) if fit is not None
            else "Run a Pawley fit to refine a cell.")
        set_tone(self.pawley_label,
                 HINT if fit is None or fit.converged else WARNING)
        reason = self._apply_refused()
        self.apply_button.setEnabled(not reason)
        self.apply_button.setToolTip(
            reason or "Put this cell on the open structure, fractional "
                      "coordinates kept: one undo step")
        self.new_button.setEnabled(fit is not None)

    def _apply_refused(self) -> str:
        from xtal.powder.pawley import cell_fits_structure

        if self.pawley is None:
            return "Run a Pawley fit first"
        if self.document is None or not self.document.structure.sites:
            return "No structure is open to put the cell on"
        reason = cell_fits_structure(self.pawley, self.document.structure)
        return f"Not this structure's cell: {reason}" if reason else ""

    def apply_cell(self) -> None:
        """The refined cell onto the structure the workbench is for."""
        reason = self._apply_refused()
        if reason:
            self.say(reason, warn=True)
            return
        from xtal.core.lattice import Lattice

        text = self.document.set_lattice(
            Lattice.from_parameters(*self.pawley.cell),
            keep="fractional", label="Apply Pawley cell")
        self.say(f"applied the Pawley {text}")

    def new_structure(self):
        """An empty structure in the fitted cell and group, filed in
        the workspace the way File > New files one."""
        if self.pawley is None:
            return None
        from xtal.core.lattice import Lattice
        from xtal.core.structure import Structure

        structure = Structure.from_arrays(
            Lattice.from_parameters(*self.pawley.cell), [], [],
            space_group=self.pawley.space_group)
        name = f"{self.data.name}-pawley" if self.data is not None \
            else "pawley"
        document = self.window_.document_set.new_document(structure,
                                                          name=name)
        self.say(f"new structure {document.title.rstrip('*')} in "
                 f"{self.pawley.space_group}")
        return document

    def _redraw(self, row: int) -> None:
        """Show the chosen step's own last answer, if it has one."""
        step = STEPS[max(row, 0)][0]
        if step == "rietveld" and self.worker is None:
            self._fill_rietveld_cell()
        if step == "rietveld" and self.rietveld is not None:
            self._draw_rietveld()
        elif step == "pawley" and self.pawley is not None:
            self._draw_pawley()
        elif step == "auto" and self.auto is not None:
            self._draw_auto_row()
        elif step in ("peaks", "index") and self.peaks is not None:
            self._show_peaks()
            if step == "index":
                self._on_cell_chosen()
        self._refresh()

    # -- automatic -----------------------------------------------------

    def _take_auto(self, result) -> None:
        """Every stage's answer where its own step shows it -- the peaks
        on Peaks, the cells on Index -- and the ranked table here."""
        self.auto = result
        if result.peaks is not None:
            self.peaks = result.peaks
            self._fill_table()
        self.cells = result.cells
        self._fill_cells()
        self._fill_auto()

    def _fill_auto(self) -> None:
        rows = self.auto.rows if self.auto is not None else []
        table = self.auto_table
        table.blockSignals(True)
        table.clearSelection()
        table.setRowCount(len(rows))
        text_columns = (2, 3, 4)
        for r, row in enumerate(rows):
            for column, text in enumerate(steps.auto_cells(row)):
                item = QTableWidgetItem(text)
                if column not in text_columns:
                    item.setTextAlignment(Qt.AlignRight
                                          | Qt.AlignVCenter)
                if column == 4 and row.groups:
                    item.setToolTip(", ".join(row.groups))
                if row.error:
                    item.setToolTip(row.error)
                table.setItem(r, column, item)
        table.blockSignals(False)
        self._show_auto_result()
        if rows and rows[0].fit is not None:
            table.selectRow(0)

    def _show_auto_result(self) -> None:
        result = self.auto
        if result is None:
            self.auto_label.setText("Run all to rank the cells.")
            set_tone(self.auto_label, HINT)
            return
        best = result.best
        lines = []
        if best is not None:
            lines.append(f"Best: row 1, {best.bravais} in "
                         f"{best.fit.space_group}\n"
                         + steps.pawley_summary(best.fit))
        if result.rietveld is not None:
            lines.append(f"Rietveld, in the cell of row "
                         f"{result.rietveld_row.rank}: Rwp "
                         f"{100 * result.rietveld.rwp:.2f} %, GoF "
                         f"{result.rietveld.gof:.3f}")
        if result.rietveld_refused:
            lines.append(result.rietveld_refused)
        self.auto_label.setText("\n\n".join(lines)
                                or "No cell was Pawley fitted.")
        set_tone(self.auto_label,
                 WARNING if result.rietveld_refused or best is None
                 else HINT)

    def _chosen_auto_row(self):
        if self.auto is None:
            return None
        chosen = self.auto_table.selectionModel().selectedRows()
        if not chosen:
            return None
        return self.auto.rows[chosen[0].row()]

    def _on_auto_chosen(self) -> None:
        """A row's own fit on the plot, and in the Pawley step as its
        answer: the cell to apply is the one being looked at."""
        row = self._chosen_auto_row()
        if row is None or row.fit is None:
            return
        self.pawley = row.fit
        self._fill_reflections()
        self._show_pawley_result()
        self.step_forms["pawley"].set_values(
            {"space_group": row.fit.space_group})
        self.cell_box.set_value(row.fit.cell)
        if self.current_step == "auto" and self.worker is None:
            self._draw_pawley()

    def _draw_auto_row(self) -> None:
        row = self._chosen_auto_row()
        if row is not None and row.fit is not None:
            self.pawley = row.fit
            self._draw_pawley()

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
        self.run_button.setText(RUN_LABELS[self.current_step])
        self.refine_button.setEnabled(can_run and not running
                                      and self.peaks is not None)
        self.restore_button.setEnabled(bool(self.history)
                                       and not running)
        self.add_button.setEnabled(self.data is not None and not running)
        refused = self._rietveld_refused() \
            if self.current_step == "rietveld" else ""
        if refused:
            self.run_button.setEnabled(False)
        if not powder.available():
            self.run_button.setToolTip(powder.missing())
        elif self.data is None:
            self.run_button.setToolTip("Load a pattern first")
        else:
            self.run_button.setToolTip(refused or "Run this step")

    def closeEvent(self, event) -> None:
        # A step left running when its window goes would have nowhere
        # to report; stop it.  MainWindow.closeEvent's workers.stop_all
        # waits for it if the whole application is going.
        self.stop()
        super().closeEvent(event)


class _Paragraph(QLabel):
    """A wrapped label as tall as its text needs at its own width.

    A form row asks a label its ``sizeHint``, which is the text on as
    few lines as the widest word allows -- not what it wraps to in the
    column it is given -- so a plan's four-sentence note was drawn a
    line or two short and cut off.
    """

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setWordWrap(True)

    def setText(self, text: str) -> None:                # noqa: N802
        super().setText(text)
        self._fit()

    def resizeEvent(self, event) -> None:                # noqa: N802
        super().resizeEvent(event)
        self._fit()

    def _fit(self) -> None:
        height = self.heightForWidth(self.width())
        if height > 0 and height != self.minimumHeight():
            self.setMinimumHeight(height)


@dataclasses.dataclass
class HistoryEntry:
    """One configuration a Rietveld run reached, or the start.

    ``structure`` is the atoms and cell as they were, ``values`` the
    form that made them (the start's are the first run's), ``fit`` the
    :class:`~xtal.powder.rietveld.RietveldFit`, ``None`` for the start.
    """

    structure: object
    values: dict
    fit: object
    when: datetime.datetime
    folder: Path | None = None


def _percent(value) -> str:
    return "--" if value is None else f"{100 * value:.2f}"


def _table(headers, rows: bool = False) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.horizontalHeader().setSectionResizeMode(
        QHeaderView.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True)
    table.verticalHeader().setVisible(False)
    if rows:
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    return table


def _default_size() -> tuple[int, int]:
    """Wide enough for every column of the cell table beside the form,
    and never larger than the screen it opens on."""
    width, height = 1720, 1000
    screen = QApplication.primaryScreen()
    if screen is not None:
        available = screen.availableGeometry()
        width = min(width, int(0.95 * available.width()))
        height = min(height, int(0.92 * available.height()))
    return width, height
