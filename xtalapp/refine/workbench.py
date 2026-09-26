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
    QFormLayout,
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
from xtal.powder.pawley import METHODS
from xtalapp.dialogs.module_form import ParamForm
from xtalapp.docks import scrolling
from xtalapp.refine.bravais import BravaisBox
from xtalapp.refine.cell import CellBox
from xtalapp.refine.pareto_plot import ParetoPlots
from xtalapp.refine.plot import RefinementPlot
from xtalapp.refine.sections import SectionedForm, fold
from xtalapp.widgets.tone import HINT, WARNING, set_tone
from xtalapp.workers import ModuleWorker, start_in_thread

__all__ = ["RefinementWorkbench"]

#: ``(action name, list label)``, in the order a refinement goes.
STEPS = (("peaks", "Peaks"), ("index", "Index"),
         ("pawley", "Pawley / Le Bail"),
         ("rietveld", "Rietveld"), ("energy", "With energy"),
         ("pareto", "Pareto"), ("auto", "Automatic"))

#: What the Run button says on each step.
RUN_LABELS = {"peaks": "Find peaks", "index": "Index",
              "pawley": "Fit Pawley", "rietveld": "Refine",
              "energy": "Refine", "pareto": "Sweep",
              "auto": "Run all"}

#: How each step's form is folded in the right-hand column:
#: ``(section title, parameter names)``.  Rietveld's cell and the
#: Pawley cell are boxes of their own, placed in their sections by the
#: page that builds them.
GROUPS = {
    "peaks": (("Range", ("start", "finish")),
              ("Finding peaks", ("shoulders", "flag_ghosts")),
              ("Refining peaks", ("background_terms",))),
    "index": (("Search", ("space_groups", "zero_error", "max_volume",
                          "longest_axis", "budget")),
              ("Space groups", ("rank_groups",))),
    "pawley": (("Method", ("method",)),
               ("Cell and space group", ("space_group",)),
               ("Range and background", ("start", "finish",
                                         "background_terms")),
               ("Refined", ("zero", "displacement", "size", "strain"))),
    "rietveld": (("Plan", ("plan",)),
                 ("Range and background", ("start", "finish",
                                           "background_terms")),
                 ("Refined: instrument and peak shape",
                  ("background", "zero", "displacement", "profile",
                   "size", "strain")),
                 ("Refined: atoms", ("positions", "biso", "occupancy",
                                     "preferred_axis"))),
    "energy": (("Range", ("start", "finish")),
               ("Energy", ("weight", "energy_cell", "max_steps"))),
    "pareto": (("Range", ("start", "finish")),
               ("Sweep", ("weights", "energy_cell", "max_steps"))),
    "auto": (("Automatic", ("cells", "classes", "continue_rietveld")),),
}

#: The steps that fit over a 2θ range of their own, which starts as
#: the Peaks step's and follows it until it is changed.
_RANGED = ("pawley", "rietveld", "energy", "pareto")

#: Parameters a step declares for ``xtal run`` that the workbench asks
#: through a widget of its own rather than the form: the cell box
#: writes ``cell`` and ``hold``.
_NOT_IN_FORM = {"index": ("bravais",), "pawley": ("cell", "hold"),
                "rietveld": ("cell", "hold"), "energy": ("engine",),
                "pareto": ("engine",)}

#: The steps that move the document's atoms as they run, and land as
#: one undo step.
_MOVES_ATOMS = ("rietveld", "energy")

#: The steps that refine the document's atoms: a Pareto sweep moves
#: them as it runs and puts them back, since it returns no structure
#: -- the points are files, and the weight chosen is With energy's.
_REFINES_ATOMS = (*_MOVES_ATOMS, "pareto")

#: Measured 2026-09-26 on a 14 x 17 Å hexagonal cell (Cu Kα, a 0.3 %
#: wrong start): 4-30° is 35 reflections and 1.3 s, 4-45° 97 and 19 s,
#: 4-60° 199 and 144 s -- and the widest put a 0.04 Å further from the
#: truth.  A Pawley intensity is a free number per reflection, so the
#: cost grows faster than the count.
PAWLEY_RANGE_NOTE = (
    "<b>A wider 2θ range is not a better cell.</b>  Every reflection "
    "is one more free intensity, and a framework's reflections crowd "
    "together with angle: on a 14 × 17 Å cell, 4-30° was 35 of them "
    "and a second; 4-60° was 199 and more than two minutes, and its "
    "cell came out further off.  Fit the low-angle range where the "
    "lines are resolved, and widen it only if there are too few.")

CELL_TO_STRUCTURE_NOTE = (
    "<b>From a cell to a structure.</b>  The idea here is that Pawley "
    "(or Automatic) finds a cell and space group that match; then the "
    "nets consistent with them -- the MOF builder's search by "
    "coordination and space group number -- are built into models "
    "with your linker and the SBU you expect (Modules > MOF builder), "
    "and each model is tested against this pattern: refined here with "
    "Rietveld or With energy, or its simulated pattern laid over this "
    "one as a phase match (Modules > PXRD > Simulate a pattern).  "
    "Solving a structure from the pattern alone, by charge flipping, "
    "is not part of this application.")

HISTORY_HEADERS = ("#", "Time", "Rwp (%)", "Rp (%)", "GoF", "Plan",
                   "Moved (Å)", "Status")

PEAK_HEADERS = ("Use", "2θ (°)", "esd", "d (Å)", "Area", "FWHM (°)",
                "Flags")

#: The peak table's columns a person may type into, and the
#: :meth:`~xtal.powder.peaks.PeakFit.edit` keyword each one sets.
PEAK_EDITS = {1: "two_theta", 4: "area", 5: "fwhm"}


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
        self.energy = None                  # xtal.powder.energy.EnergyFit
        self.pareto = None               # xtal.powder.pareto.ParetoResult
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
        #: the 2θ range last handed from Peaks to the steps after it: a
        #: step still showing it follows Peaks, one changed by hand
        #: keeps its own
        self._range_given: tuple[float, float] | None = None
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
        for column, _key in PEAK_EDITS.items():
            self.table.horizontalHeaderItem(column).setToolTip(
                "Double-click a number to set it by hand, as a start "
                "for Refine peaks")
        self.cell_table = _table(steps.INDEX_COLUMNS, rows=True)
        # A row's classes are a long list; stretched to what was left of
        # the width, the last column cut them off.  Sized to its text,
        # the table scrolls sideways instead.
        self.cell_table.horizontalHeader().setStretchLastSection(False)
        self.cell_table.setTextElideMode(Qt.ElideNone)
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
        self.ends_table = _table(steps.ENERGY_COLUMNS)
        self.ends_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ends_table.setToolTip(
            "Where the run started, the atoms under the energy alone "
            "(w = 1), and this fit: the two ends a weight is between")
        self.tables.addWidget(self.ends_table)
        self.pareto_table = _table(steps.PARETO_COLUMNS, rows=True)
        self.pareto_table.setToolTip(
            "One row a weight.  Choose one to draw its fit; "
            "double-click to open its structure.  Front is a point no "
            "other beats on both Rwp and energy.")
        self.pareto_table.itemSelectionChanged.connect(
            self._draw_pareto_row)
        self.pareto_table.cellDoubleClicked.connect(
            lambda row, _column: self.open_pareto_point(row))
        self.pareto_plots = ParetoPlots()
        self.pareto_plots.pointPicked.connect(self.pareto_table.selectRow)
        pareto = QSplitter(Qt.Horizontal)
        pareto.addWidget(self.pareto_table)
        pareto.addWidget(self.pareto_plots)
        pareto.setSizes([400, 600])
        self.tables.addWidget(pareto)
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
        # half and half: the table under a fit is read as much as the
        # fit is looked at
        middle.setStretchFactor(0, 1)
        middle.setStretchFactor(1, 1)
        middle.setSizes([500, 500])
        self.middle = middle

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
        self._show_energy_result()
        self._show_pareto_result()
        self._on_radiation()
        self._show_plan_note()
        self._show_refines_note()
        self._fill_history()
        self._show_auto_result()
        self._refresh()

    def _side(self) -> QWidget:
        """The pattern, the step's sections, and Run / Stop."""
        side = QWidget()
        layout = QVBoxLayout(side)
        layout.setSpacing(4)

        self.missing = QLabel(powder.missing())
        self.missing.setWordWrap(True)
        set_tone(self.missing, WARNING)
        self.missing.setVisible(bool(powder.missing()))
        layout.addWidget(self.missing)

        row = QHBoxLayout()
        self.load_button = QPushButton("Load .xy...")
        self.load_button.setToolTip("Read the measured pattern to "
                                    "refine against")
        self.load_button.clicked.connect(self.choose_pattern)
        row.addWidget(self.load_button)
        self.pattern_label = QLabel("no pattern loaded")
        self.pattern_label.setWordWrap(True)
        set_tone(self.pattern_label, HINT)
        row.addWidget(self.pattern_label, 1)
        self.data_form = ParamForm(steps.DATA_PARAMS[1:])
        self.data_form.changed.connect(self._on_radiation)
        self.data_form.layout().setLabelAlignment(Qt.AlignLeft
                                                  | Qt.AlignVCenter)
        self.data_form.layout().setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.pattern_fold = self._fold("Pattern", row, self.data_form)
        layout.addWidget(self.pattern_fold)

        self.forms = _PageStack()
        self.step_forms: dict[str, SectionedForm] = {}
        self.engine_boxes: dict[str, QComboBox] = {}
        self.refines_notes: dict[str, _Paragraph] = {}
        self.bravais = BravaisBox()
        self.bravais.setTitle("")
        self.bravais.setFlat(True)
        self.cell_box = CellBox("")
        self.cell_box.setFlat(True)
        self.cell_box.setToolTip(
            "The numbers the space group leaves free; the rest follow "
            "from them.  Untick Refine to hold one at the value given.")
        self.rietveld_cell = CellBox("", editable=False)
        self.rietveld_cell.setFlat(True)
        self.rietveld_cell.setToolTip(
            "The structure's own cell, refined number by number: "
            "untick Refine to hold one")
        for name, _label in STEPS:
            params = [p for p in steps.STEP_PARAMS[name]
                      if p.name not in _NOT_IN_FORM.get(name, ())]
            form = SectionedForm(params, GROUPS[name],
                                 notes=name in ("pawley", "rietveld"),
                                 parent=self)
            self.step_forms[name] = form
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)
            page_layout.setSpacing(2)
            for section in getattr(self, f"_{name}_sections")(form):
                page_layout.addWidget(section)
            # the stack is as tall as its tallest step; a shorter one
            # sits at the top rather than spread down the column
            page_layout.addStretch(1)
            self.forms.addWidget(page)
        self.step_forms["peaks"].changed.connect(self._on_peaks_changed)
        for name in ("energy", "pareto"):
            self.step_forms[name].changed.connect(self._show_refines_note)
        self.step_forms["rietveld"].changed.connect(
            self._show_refines_note)
        self.step_forms["pawley"].changed.connect(self._refresh)
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
        self.run_button.setDefault(True)
        self.run_button.clicked.connect(lambda: self.run_step())
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop)
        buttons.addWidget(self.run_button, 1)
        buttons.addWidget(self.stop_button)
        bottom.addLayout(buttons)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        set_tone(self.status, HINT)
        bottom.addWidget(self.status)
        column_layout.addLayout(bottom)
        return column

    def _fold(self, title: str, *widgets, open_: bool = True):
        """A section of the column that folds, and re-measures the page
        when it does."""
        return fold(title, *widgets, open_=open_,
                    on_toggle=lambda: self._fit_form(
                        self.forms.currentIndex()))

    def _fit_form(self, index: int) -> None:
        """The stack as tall as the page shown, not the tallest one."""
        forms = getattr(self, "forms", None)
        if forms is None or index < 0:
            return
        for k in range(forms.count()):
            policy = QSizePolicy.Preferred if k == index \
                else QSizePolicy.Ignored
            forms.widget(k).setSizePolicy(policy, policy)
        # the stack caches its hint; a policy changed under it is not
        # news to it until it is told
        forms.layout().invalidate()
        forms.updateGeometry()

    # -- each step's sections ------------------------------------------

    def _peaks_sections(self, form):
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
        self.refine_button = QPushButton("Refine peaks")
        self.refine_button.setToolTip(
            "Fit the lines in use together over the whole range, on a "
            "Chebyshev background of the terms above: position, area "
            "and width of each.  Lines out of use are removed.")
        self.refine_button.clicked.connect(
            lambda: self.run_step("refine_peaks"))
        self.components_box = QCheckBox("Show individual peaks")
        self.components_box.setChecked(True)
        self.components_box.setToolTip(
            "Draw each line in use on its own over the background")
        self.components_box.toggled.connect(self.plot.show_components)
        hint = _hint("A line's 2θ, area and width can be typed into "
                     "the table (double-click the number), to give "
                     "Refine peaks a better start than the one found.")
        return (self._fold("Range", form.part("Range")),
                self._fold("Finding peaks", form.part("Finding peaks")),
                self._fold("Refining peaks", form.part("Refining peaks"),
                           row, self.refine_button, self.components_box,
                           hint))

    def _index_sections(self, form):
        search = form.part("Search")
        self._add_budget_switch(search)
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
        hint = _hint("The highlighted cell and its space group are "
                     "copied into the Pawley step.")
        return (self._fold("Bravais lattices", self.bravais),
                self._fold("Search", search),
                self._fold("Space groups", form.part("Space groups")),
                self._fold("Cell table", row, hint))

    def _add_budget_switch(self, search) -> None:
        """A box beside the time budget that turns it off, off to start
        with: a budget is a way to stop a search, and Stop is another.
        The spin box shows "no limit" at 0, which is what an unticked
        box sends."""
        spin = search.widgets["budget"]
        spin.setSpecialValueText("no limit")
        self.budget_box = QCheckBox("Time budget")
        self.budget_box.setToolTip(
            "Stop the search after this long, reporting what it "
            "reached.  Unticked, it runs until it is done or Stop is "
            "pressed.")
        layout = search.layout()
        row, _role = layout.getWidgetPosition(spin)
        old = layout.itemAt(row, QFormLayout.LabelRole).widget()
        layout.removeWidget(old)
        old.deleteLater()
        layout.setWidget(row, QFormLayout.LabelRole, self.budget_box)
        self._budget_seconds = 60.0

        def switched(on: bool) -> None:
            if on and spin.value() == 0:
                spin.setValue(self._budget_seconds)
            elif not on and spin.value() > 0:
                self._budget_seconds = spin.value()
                spin.setValue(0.0)
            spin.setEnabled(on)

        def edited(value: float) -> None:
            # a number set from outside (a saved form, a test) turns
            # the budget on; 0 typed into the box turns it off
            self.budget_box.blockSignals(True)
            self.budget_box.setChecked(value > 0)
            self.budget_box.blockSignals(False)
            spin.setEnabled(value > 0)

        self.budget_box.toggled.connect(switched)
        spin.valueChanged.connect(edited)
        edited(spin.value())

    def _pawley_sections(self, form):
        group = form.part("Cell and space group")
        # the group decides which numbers the cell has, so the cell
        # sits under it
        group.layout().addRow(self.cell_box)
        form.widgets["space_group"].textChanged.connect(
            self.cell_box.set_space_group)
        self.pawley_label = _result_label()
        self.apply_button = QPushButton("Apply cell to the structure")
        self.apply_button.clicked.connect(self.apply_cell)
        self.new_button = QPushButton("New structure from this cell")
        self.new_button.setToolTip(
            "An empty structure with this cell and space group, filed "
            "in the workspace like File > New")
        self.new_button.clicked.connect(self.new_structure)
        buttons = QHBoxLayout()
        buttons.addWidget(self.apply_button)
        buttons.addWidget(self.new_button)
        explain = _hint(
            "A Pawley or Le Bail fit has no atoms: it refines a cell, "
            "and each reflection's intensity is found from the pattern "
            "-- a free number in Pawley, shared out from the observed "
            "counts in Le Bail.  <b>Apply cell to the structure</b> "
            "puts the refined a, b, c, α, β, γ on the structure this "
            "window was opened over, its atoms kept at the same "
            "fractional coordinates -- one undo step.  <b>New "
            "structure from this cell</b> opens an empty structure in "
            "a new tab, with this cell and space group and no atoms, "
            "to build or solve a structure in.")
        # Two things a person asked to be told, and would otherwise
        # learn by waiting: that a wider range is not a better cell,
        # and what a cell is for here.
        return (self._fold("Method", form.part("Method")),
                self._fold("Cell and space group", group),
                self._fold("Range and background",
                           form.part("Range and background")),
                self._fold("Refined", form.part("Refined")),
                self._fold("Result", self.pawley_label, buttons),
                self._fold("About", explain, _hint(PAWLEY_RANGE_NOTE),
                           _hint(CELL_TO_STRUCTURE_NOTE), open_=False))

    def _rietveld_sections(self, form):
        plan = form.part("Plan")
        # what the plan chosen above it does, stage by stage
        self.plan_note = _Paragraph("")
        set_tone(self.plan_note, HINT)
        plan.layout().addRow(self.plan_note)
        form.changed.connect(self._show_plan_note)
        self.rietveld_label = _result_label()
        explain = _hint(
            "Refines the atoms of the structure this window was opened "
            "over.  The atoms move in the viewer as it runs; a finished "
            "fit is one undo step, and Stop puts them back.  Atoms are "
            "never added, removed or bonded.")
        return (self._fold("Plan", plan),
                self._fold("Range and background",
                           form.part("Range and background")),
                self._fold("Refined: instrument and peak shape",
                           form.part("Refined: instrument and peak "
                                     "shape")),
                self._fold("Refined: cell", self.rietveld_cell),
                self._fold("Refined: atoms", form.part("Refined: atoms")),
                self._fold("Result", self.rietveld_label),
                self._fold("About", explain, open_=False))

    def _engine_section(self, step: str):
        """The energy engine, chosen here -- and in the same choice as
        the Force Field panel's, whose model the box shares, so the
        two windows can never name different engines.  The engine's
        own options stay in that panel, one button away."""
        box = QComboBox()
        box.setToolTip("The engine the energy term is computed with.  "
                       "Choosing one here chooses it in the Force Field "
                       "panel too.")
        dock = getattr(self.window_, "ff_dock", None)
        chooser = getattr(dock, "engine", None)
        if chooser is not None:
            box.setModel(chooser.model())
            box.setCurrentIndex(chooser.currentIndex())
            chooser.currentIndexChanged.connect(box.setCurrentIndex)
            box.activated.connect(chooser.setCurrentIndex)
            chooser.currentIndexChanged.connect(
                lambda _i: self._show_refines_note())
        else:
            from xtal.ff.registry import ENGINES

            for engine in ENGINES:
                box.addItem(engine.label, engine.name)
        self.engine_boxes[step] = box
        options = QPushButton("Options...")
        options.setToolTip("Show the Force Field panel, where the "
                           "engine's parameter set, model and charges "
                           "are set")
        options.clicked.connect(self._show_engine_options)
        options.setEnabled(hasattr(self.window_, "show_force_field"))
        row = QHBoxLayout()
        row.addWidget(box, 1)
        row.addWidget(options)
        hint = _hint("Shared with the Force Field panel: its options "
                     "(parameter set, model, charges) are set there.")
        return self._fold("Energy engine", row, hint)

    def _refines_section(self, step: str):
        note = _Paragraph("")
        set_tone(note, HINT)
        self.refines_notes[step] = note
        return self._fold("What is refined", note)

    def _energy_sections(self, form):
        self.energy_label = _result_label()
        explain = _hint(
            "Minimises (1 − w) χ²/χ²₀ + w (E − E₀)/ΔE, where ΔE is how "
            "far the energy falls with the atoms answering to it alone. "
            " An atom on a special position stays on it.  A finished "
            "fit is one undo step, and Stop puts the atoms back.")
        return (self._engine_section("energy"),
                self._fold("Range", form.part("Range")),
                self._fold("Energy", form.part("Energy")),
                self._refines_section("energy"),
                self._fold("Result", self.energy_label),
                self._fold("About", explain, open_=False))

    def _pareto_sections(self, form):
        self.pareto_label = _result_label()
        self.use_knee_button = QPushButton("Use this weight")
        self.use_knee_button.setToolTip(
            "Put the suggested weight in the With energy step, to "
            "refine the structure at it")
        self.use_knee_button.clicked.connect(self.use_knee)
        self.front_button = QPushButton("Show in Results")
        self.front_button.setToolTip(
            "Rwp against energy in the main window's Results panel as "
            "well, where a point opens its structure")
        self.front_button.clicked.connect(self.show_front)
        buttons = QHBoxLayout()
        buttons.addWidget(self.use_knee_button)
        buttons.addWidget(self.front_button)
        buttons.addStretch(1)
        explain = _hint(
            "Refines with energy at every weight listed, each from the "
            "one below it, with the scale, background and peak shape "
            "fitted once for all of them.  The front is the weights no "
            "other beats on both Rwp and energy; the suggested weight "
            "is where it bends most.  Every point is written as it "
            "finishes, so Stop keeps them.  The structure is put back "
            "afterwards: refine at the weight you choose with With "
            "energy.")
        return (self._engine_section("pareto"),
                self._fold("Range", form.part("Range")),
                self._fold("Sweep", form.part("Sweep")),
                self._refines_section("pareto"),
                self._fold("Result", self.pareto_label, buttons),
                self._fold("About", explain, open_=False))

    def _auto_sections(self, form):
        self.auto_label = _result_label()
        explain = _hint(
            "Fits the peaks, indexes them, and fits the leading cells "
            "in their leading space-group classes by the Pawley step's "
            "method, ranked by Rwp.  Each stage asks what its own "
            "step's form says: the lattices and budget on Index, the "
            "range and broadening on Pawley, the plan and boxes on "
            "Rietveld.  It stops at the table unless Continue to "
            "Rietveld is ticked, and then refines the structure only "
            "if its cell is a row's.")
        return (self._fold("Automatic", form.part("Automatic")),
                self._fold("Result", self.auto_label),
                self._fold("About", explain, open_=False))

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
        self._range_given = None
        for step in ("peaks", *_RANGED):
            self.step_forms[step].set_values({"start": lo, "finish": hi})
        # as the boxes hold it, rounded to their decimals
        given = self.step_forms["peaks"].values()
        self._range_given = (float(given["start"]), float(given["finish"]))
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
        if step in ("energy", "pareto"):
            return self._energy_values(values, step)
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

    def _energy_values(self, values: dict, step: str = "energy") -> dict:
        """The step's own form, the engine it names (which is the Force
        Field panel's), and the Rietveld step's boxes under
        ``rietveld_`` for the fit of everything but the atoms that
        comes first -- for With energy and for a Pareto sweep of it
        alike.  The range is the step's own, not Rietveld's."""
        from xtalapp.docks.ff_panel import panel_options

        own_form = self.step_forms[step].values()
        span = {k: own_form.pop(k) for k in ("start", "finish")
                if k in own_form}
        values.update(own_form)
        engine = self.engine_name()
        values["engine"] = engine
        values["engine_options"] = panel_options(self.window_, engine)
        own = self.values("rietveld")
        for name in ("xy", *self.data_form.values()):
            own.pop(name, None)
        interval = own.pop("frame_interval", None)
        if interval is not None:
            values["frame_interval"] = interval
        values.update({f"rietveld_{k}": v for k, v in own.items()})
        values.update({f"rietveld_{k}": v for k, v in span.items()})
        return values

    def engine_name(self) -> str:
        """The energy engine: the Force Field panel's, which the boxes
        here share; the box's own choice only with no panel."""
        from xtalapp.docks.ff_panel import panel_engine

        if getattr(self.window_, "ff_dock", None) is not None:
            return panel_engine(self.window_)
        box = self.engine_boxes.get("energy")
        return str(box.currentData()) if box is not None and \
            box.currentData() else "uff"

    def _show_engine_options(self) -> None:
        show = getattr(self.window_, "show_force_field", None)
        if show is not None:
            show()

    def _show_refines_note(self) -> None:
        """What a run with energy fits first and what it moves after:
        the first stage is the Rietveld step's boxes, on another page."""
        notes = getattr(self, "refines_notes", {})
        for step, note in notes.items():
            try:
                note.setText(steps.energy_refines_note(self.values(step)))
            except PowderError as exc:
                note.setText(str(exc))
        if notes:
            self._fit_form(self.forms.currentIndex())

    def _on_peaks_changed(self) -> None:
        """The Peaks step's range, handed on to every step that fits
        over one and still shows the range it was last handed -- a
        range set on Pawley by hand is Pawley's."""
        if self._range_given is None:
            return
        values = self.step_forms["peaks"].values()
        new = (float(values["start"]), float(values["finish"]))
        if new == self._range_given:
            return
        old, self._range_given = self._range_given, None
        for step in _RANGED:
            form = self.step_forms[step]
            own = form.values()
            if (float(own["start"]), float(own["finish"])) == old:
                form.set_values({"start": new[0], "finish": new[1]})
        self._range_given = new

    def run_step(self, name: str | None = None) -> None:
        """Run a step's action -- the current step's, or ``name``."""
        if self.worker is not None or self.data is None:
            return
        name = name or self.current_step
        if name == "refine_peaks" and self.peaks is None:
            self.say("Find peaks (or add some) before refining them",
                     warn=True)
            return
        refused = self._rietveld_refused() if name in _REFINES_ATOMS \
            else ""
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
        if name == "energy":
            # the history's boxes are the Rietveld step's, which is the
            # form a restored row puts back
            structure = self._start_rietveld(
                {**self.values("rietveld"),
                 "energy_weight": values.get("weight", 0.0)})
        if name == "pareto":
            structure = self.document.structure.copy()
            self._before = (structure.frac.copy(),
                            structure.lattice.matrix.copy())
            self._framed = False
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
        if step == "pareto":
            self._put_back()
            if answer is not None:
                # Stop keeps the points reached: each is an answer
                self.pareto = answer
                self._fill_pareto()
        if step in _MOVES_ATOMS:
            self._finish_rietveld(answer if not result.cancelled
                                  else None, step)
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
        if step == "pareto":
            self._put_back()
        elif step in _MOVES_ATOMS or self._before is not None:
            self._finish_rietveld(None, step)
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
        if self._running not in (*_REFINES_ATOMS, "auto") \
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
        what = {"energy": "With energy", "pareto": "Pareto"}.get(
            self._running, "Rietveld")
        self._progress(f"{what}: {frame.stage}...")

    def _finish_rietveld(self, fit, step: str = "rietveld") -> None:
        """Put the atoms back where the run started, and then -- for a
        fit that finished -- commit it as one undo step.  ``step`` is
        which step's answer it is: Rietveld's, or with energy."""
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
        energy = step == "energy"
        if fit is None:
            if energy and self.energy is not None:
                self._draw_energy()
            elif not energy and self.rietveld is not None:
                self._draw_rietveld()
            return
        if energy:
            self.energy = fit
        else:
            self.rietveld = fit
        self.document.replace_structure(
            fit.structure.copy(),
            "Rietveld with energy" if energy else "Rietveld refinement",
            Change.POSITIONS | Change.CELL | Change.METADATA)
        self.history.append(HistoryEntry(
            structure=fit.structure.copy(), values=self._run_values,
            fit=fit, when=datetime.datetime.now(), folder=self._folder))
        self._history_at = len(self.history) - 1
        self._fill_history()
        self._fill_rietveld_cell()
        if energy:
            self._draw_energy()
            self._show_energy_result()
            return
        self._draw_rietveld()
        self._show_rietveld_result()

    def _draw_energy(self) -> None:
        fit = self.energy
        if fit is None:
            self._draw_rietveld()
            return
        self.plot.show_fit(fit.two_theta, fit.y_obs, fit.y_calc,
                           fit.y_background, fit.ticks)

    def _show_energy_result(self) -> None:
        fit = self.energy
        self.energy_label.setText(
            steps.energy_summary(fit) if fit is not None
            else "Run to refine the structure against the pattern and "
                 "the energy.")
        set_tone(self.energy_label,
                 HINT if fit is None or fit.converged else WARNING)
        rows = steps.energy_ends(fit) if fit is not None else []
        self.ends_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for column, text in enumerate(row):
                item = QTableWidgetItem(text)
                if column:
                    item.setTextAlignment(Qt.AlignRight
                                          | Qt.AlignVCenter)
                self.ends_table.setItem(r, column, item)

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
            if "energy_weight" in entry.values:
                plan = f"with energy, w {entry.values['energy_weight']:g}"
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
            cells = (f"{peak.two_theta:.4f}", _number(peak.two_theta_esd,
                                                      ".4f"),
                     f"{peak.d:.5f}", f"{peak.area:.1f}",
                     f"{peak.fwhm:.4f}", ", ".join(peak.flags))
            for column, text in enumerate(cells, start=1):
                item = QTableWidgetItem(text)
                flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
                if column in PEAK_EDITS:
                    flags |= Qt.ItemIsEditable
                item.setFlags(flags)
                if column < len(cells):
                    item.setTextAlignment(Qt.AlignRight
                                          | Qt.AlignVCenter)
                self.table.setItem(row, column, item)
        self.table.blockSignals(False)

    def _on_use_changed(self, item) -> None:
        if self.peaks is None:
            return
        if item.column() in PEAK_EDITS:
            self._on_peak_edited(item)
            return
        if item.column() != 0:
            return
        self.peaks.peaks[item.row()].use = \
            item.checkState() == Qt.Checked
        self.plot.set_ticks(self._used_positions())
        self.plot.set_components(self.peaks.y_background,
                                 self.peaks.curves())
        self.say(f"{self.peaks.n_used} of {len(self.peaks.peaks)} "
                 f"lines in use for indexing")

    def _on_peak_edited(self, item) -> None:
        """A number typed into the peak table: the line moved or resized
        there, drawn where it now is, and refined from there next."""
        key = PEAK_EDITS[item.column()]
        try:
            value = float(item.text().strip())
            self.peaks.edit(item.row(), **{key: value})
        except ValueError:
            self.say(f"{item.text()!r} is not a number", warn=True)
        except PowderError as exc:
            self.say(str(exc), warn=True)
        else:
            self.say("line set by hand -- Refine peaks starts from it")
        # after the editor has closed: the table is rebuilt, and an
        # edit to 2θ may have put the line somewhere else in the order
        QTimer.singleShot(0, self._redraw_lines)

    def _redraw_lines(self) -> None:
        """The table, the comb and the single lines, the zoom kept."""
        if self.peaks is None:
            return
        self._fill_table()
        self.plot.set_ticks(self._used_positions())
        self.plot.set_components(self.peaks.y_background,
                                 self.peaks.curves())

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
        elif step == "energy":
            self._show_energy_result()
            if self.energy is not None:
                self._draw_energy()
        elif step == "pareto":
            self._show_pareto_result()
            self._draw_pareto_row()
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

    # -- Pareto --------------------------------------------------------

    def _put_back(self) -> None:
        """The atoms where the sweep started: it returns no structure."""
        before, self._before = self._before, None
        if before is None or self.document is None:
            return
        if len(before[0]) != len(self.document.structure.sites):
            self.say("the structure was edited while the sweep ran",
                     warn=True)
            return
        self.document.preview_positions(*before)

    def _fill_pareto(self) -> None:
        result = self.pareto
        rows = steps.pareto_rows(result) if result is not None else []
        table = self.pareto_table
        table.blockSignals(True)
        table.clearSelection()
        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for column, text in enumerate(row):
                item = QTableWidgetItem(text)
                if column < 3 or column == 4:
                    item.setTextAlignment(Qt.AlignRight
                                          | Qt.AlignVCenter)
                table.setItem(r, column, item)
        table.blockSignals(False)
        self.pareto_plots.show_result(result)
        self._show_pareto_result()
        if result is not None and result.points:
            bend = result.knee
            table.selectRow(bend if bend is not None else 0)

    def _show_pareto_result(self) -> None:
        result = self.pareto
        if result is None:
            self.pareto_label.setText(
                "Sweep to refine at every weight and find the one "
                "where the fit and the energy trade best.")
            set_tone(self.pareto_label, HINT)
        else:
            self.pareto_label.setText(steps.pareto_summary(result))
            set_tone(self.pareto_label,
                     HINT if result.knee is not None else WARNING)
        self.use_knee_button.setEnabled(
            result is not None and result.knee is not None)
        self.front_button.setEnabled(
            result is not None and bool(result.points))

    def _chosen_pareto_point(self):
        if self.pareto is None:
            return None
        chosen = self.pareto_table.selectionModel().selectedRows()
        if not chosen:
            return None
        return self.pareto.points[chosen[0].row()]

    def _draw_pareto_row(self) -> None:
        chosen = self.pareto_table.selectionModel().selectedRows()
        self.pareto_plots.mark(chosen[0].row() if chosen else None)
        point = self._chosen_pareto_point()
        if point is None or point.fit is None or self.worker is not None:
            return
        fit = point.fit
        self.plot.show_fit(fit.two_theta, fit.y_obs, fit.y_calc,
                           fit.y_background, fit.ticks)

    def open_pareto_point(self, row: int):
        """Open the structure refined at row ``row``'s weight as a tab
        of the main window -- the answer's geometry, not a preview."""
        if self.pareto is None or not 0 <= row < len(self.pareto.points):
            return None
        path = self.pareto.points[row].path
        if not path or not Path(path).exists():
            self.say("that weight left no structure behind: the sweep "
                     "ran with no workspace to write into", warn=True)
            return None
        return self.window_.open_path(path)

    def use_knee(self) -> None:
        """The suggested weight into With energy, and that step shown:
        refining the structure at it is one more click."""
        result = self.pareto
        if result is None or result.knee is None:
            return
        weight = result.points[result.knee].weight
        self.step_forms["energy"].set_values({"weight": weight})
        self.steps.setCurrentRow([s for s, _l in STEPS].index("energy"))

    def show_front(self) -> None:
        """The front in the Results panel, where a point opens its
        structure as a scan's profile does."""
        dock = getattr(self.window_, "results_dock", None)
        if self.pareto is None or dock is None:
            return
        name = self.data.name if self.data is not None else ""
        dock.show_report(steps.pareto_report(self.pareto, name),
                         "Pareto")
        dock.show()
        dock.raise_()

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
        label = RUN_LABELS[self.current_step]
        if self.current_step == "pawley":
            method = self.step_forms["pawley"].values().get("method")
            label = f"Fit {METHODS.get(method, 'Pawley')}"
        self.run_button.setText(label)
        self.refine_button.setEnabled(can_run and not running
                                      and self.peaks is not None)
        self.restore_button.setEnabled(bool(self.history)
                                       and not running)
        self.add_button.setEnabled(self.data is not None and not running)
        refused = self._rietveld_refused() \
            if self.current_step in _REFINES_ATOMS else ""
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


class _PageStack(QStackedWidget):
    """A stack as tall as the page it shows.

    A stack asks every page for its height at a width once any page
    wraps text, whatever their size policies say, so Peaks was given
    Index's height as soon as Index's hints wrapped.  Only the page
    shown is asked here.
    """

    def _page(self):
        return self.currentWidget()

    def sizeHint(self):                                  # noqa: N802
        page = self._page()
        return page.sizeHint() if page is not None else super().sizeHint()

    def minimumSizeHint(self):                           # noqa: N802
        page = self._page()
        return page.minimumSizeHint() if page is not None \
            else super().minimumSizeHint()

    def hasHeightForWidth(self) -> bool:                 # noqa: N802
        page = self._page()
        return page is not None and page.hasHeightForWidth()

    def heightForWidth(self, width: int) -> int:         # noqa: N802
        page = self._page()
        return page.heightForWidth(width) if page is not None else -1


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


def _hint(text: str) -> QLabel:
    """A paragraph in the hint tone, wrapping to the column."""
    label = QLabel(text)
    label.setWordWrap(True)
    set_tone(label, HINT)
    return label


def _result_label() -> QLabel:
    """Where a step's figures go: selectable, so they can be copied."""
    label = QLabel("")
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return label


def _number(value: float, spec: str) -> str:
    """A number, or blank for the NaN of one nobody has measured."""
    return "" if value != value else format(value, spec)


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
