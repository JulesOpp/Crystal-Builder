"""
xtalapp.dialogs.scan
====================
What to scan, over what range, with which engine.

A scan is the one calculation in this application that can take all
night, so the dialog's job is to make three things unmissable before
the Run button is pressed: how many points there are, how long that is
likely to be, and what is going to be held fixed while each one
relaxes.  It says all three in a line that updates as the boxes are
edited.

**An axis is written in the same grammar everywhere.**  The kind
chooser and the atom box build the text that
:func:`xtal.modules.scan.parse_axis` reads, and that text is what goes
into the run log -- so any scan can be re-run, from the command line
or from here, off the line it printed.  A dialog that invented its own
way of saying "the torsion over these four atoms" would be a second
thing to keep in step with the first.

**Only the cell parameters the space group leaves free are offered**,
with the ties spelled out beside them.  Scanning ``b`` in a trigonal
group is not a hexagonal crystal with an odd cell; it is a structure
whose own symmetry operations no longer map it onto itself, and
nothing downstream would report that.

**The engine is read from the Force Field panel, not configured
here.**  One place to set up an engine, the same bargain
:mod:`xtalapp.dialogs.dftb_run` strikes with the Hamiltonian.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from xtal.core import p1
from xtal.core.lattice import PARAMETER_NAMES
from xtal.ff import scan as driver
from xtal.ff.optimize import METHODS
from xtal.ff.registry import ENGINES
from xtal.modules import scan as scan_module
from xtalapp.dialogs.module_form import ParamForm
from xtalapp.docks import scrolling

#: Roughly how long one optimiser step takes, per atom of the P1 cell,
#: in seconds.  Measured under UFF: 0.44 s for the 1152 atoms of
#: Ni2Cl2BTDD and 6.7 ms for the 210 of zinc acetate, which is 0.38
#: and 0.032 milliseconds an atom -- so this is the pessimistic end,
#: and the estimate is offered as an order of magnitude and says so.
SECONDS_PER_ATOM_STEP = 3.8e-4

#: What the kind chooser offers for an internal coordinate, and how
#: many anchors each takes.
INTERNAL = (("distance", "Distance between two", 2),
            ("angle", "Angle across three", 3),
            ("torsion", "Dihedral across four", 4),
            ("plane", "Angle between two planes", 2))


def panel_engine(window) -> str:
    """Which engine the Force Field panel has selected."""
    for name in ("ff_dock", "dftb_dock"):
        dock = getattr(window, name, None)
        chosen = getattr(dock, "engine_name", None)
        if callable(chosen):
            try:
                return str(chosen())
            except Exception:                       # noqa: BLE001
                continue                            # pragma: no cover
    return "uff"


def panel_options(window, engine: str) -> dict:
    """That engine's own options, as the Force Field panel has them.

    Used to *open* this dialog's form on what the user last set up
    rather than on the registry defaults, which is the difference
    between "the scan runs UFF4MOF because that is what I have been
    using" and "the scan runs whatever it felt like".  The form is
    still the dialog's own: an engine chosen here that the panel is
    not on has nothing to inherit, and gets its defaults.
    """
    for name in ("ff_dock", "dftb_dock"):
        dock = getattr(window, name, None)
        if dock is None:
            continue
        chosen = getattr(dock, "engine_name", None)
        if callable(chosen) and str(chosen()) == engine:
            return dict(dock.options())
        forms = getattr(dock, "engine_forms", {}) or {}
        form = forms.get(engine)
        if form is not None:
            return dict(form.values())
    return {}


def selected_atoms(window) -> list[int]:
    """The P1 atoms selected in the tab in front."""
    document = _document(window)
    if document is None:
        return []
    return sorted(int(a) for a in document.selection.atoms)


def _document(window):
    if window is None or not hasattr(window, "current_document"):
        return None
    return window.current_document()


class AxisBox(QGroupBox):
    """One axis: what to scan, and over what.

    The text it builds is the grammar the module reads, so the box and
    the command line cannot drift apart.
    """

    def __init__(self, title, structure, window, optional=False,
                 parent=None):
        super().__init__(title, parent)
        self.structure = structure
        self.window = window
        self.kind = QComboBox()
        if optional:
            self.kind.addItem("None", "")
        constraint = structure.space_group.cell_constraint
        for name in PARAMETER_NAMES:
            if not constraint.is_free(PARAMETER_NAMES.index(name)):
                continue
            followers = [PARAMETER_NAMES[i] for i in range(6)
                         if constraint.follows(i)
                         == PARAMETER_NAMES.index(name)]
            label = f"Lattice {name}"
            if followers:
                # Spelled out, because "scanning a also moves b" is
                # the whole difference between a trigonal crystal and
                # a structure its own operations no longer fit.
                label += f"  ({', '.join(followers)} follows it)"
            self.kind.addItem(label, name)
        self.kind.addItem("Cell volume (shape relaxes)", "volume")
        for name, label, _anchors in INTERNAL:
            self.kind.addItem(label, name)

        self.atoms = QLineEdit()
        self.atoms.setPlaceholderText(
            "atom indices, e.g. 0 1 2 3  (commas join a centroid)")
        self.from_selection = QPushButton("Add the selection")
        self.from_selection.setToolTip(
            "Append the selected atoms as one anchor.  Several atoms "
            "become their centroid, and it follows them.")

        self.start = _number("From")
        self.stop = _number("To")
        self.steps = QSpinBox()
        self.steps.setRange(1, 201)
        self.steps.setValue(7)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: palette(mid);")

        atoms_row = QHBoxLayout()
        atoms_row.addWidget(self.atoms, 1)
        atoms_row.addWidget(self.from_selection)
        range_row = QHBoxLayout()
        range_row.addWidget(self.start, 1)
        range_row.addWidget(QLabel("to"))
        range_row.addWidget(self.stop, 1)
        range_row.addWidget(QLabel("in"))
        range_row.addWidget(self.steps)
        range_row.addWidget(QLabel("points"))

        self.form = QFormLayout(self)
        self.form.addRow("Coordinate", self.kind)
        self.form.addRow("Atoms", atoms_row)
        self.form.addRow("Range", range_row)
        self.form.addRow("", self.status)

        self.kind.currentIndexChanged.connect(self._kind_changed)
        self.atoms.textChanged.connect(self.refresh)
        self.from_selection.clicked.connect(self._add_selection)
        self._kind_changed()

    # -- reading it ----------------------------------------------------

    @property
    def chosen(self) -> str:
        return str(self.kind.currentData() or "")

    @property
    def is_internal(self) -> bool:
        return self.chosen in dict(
            (name, anchors) for name, _label, anchors in INTERNAL)

    def spec(self) -> str:
        if not self.chosen:
            return ""
        if not self.is_internal:
            return self.chosen
        return f"{self.chosen} {self.atoms.text().strip()}".strip()

    def coordinate(self):
        """The coordinate this box describes, or ``None``.

        Failure is a message under the box rather than an exception:
        a half-typed atom list is the ordinary state of a dialog
        being filled in.
        """
        spec = self.spec()
        if not spec:
            return None
        cell = p1.expand(self.structure)
        return scan_module.parse_axis(self.structure, cell, spec)

    def axis(self):
        coordinate = self.coordinate()
        if coordinate is None:
            return None
        return driver.Axis.over(coordinate, self.start.value(),
                                self.stop.value(), self.steps.value())

    # -- keeping it honest ---------------------------------------------

    def _kind_changed(self) -> None:
        internal = self.is_internal
        # Hidden rather than greyed out.  A lattice parameter has no
        # atoms and never will, so the row is not a control that is
        # unavailable, it is a control that does not apply -- and two
        # dead rows per axis is what pushed Direction below the fold.
        self.form.setRowVisible(1, internal)
        self.atoms.setEnabled(internal)
        self.from_selection.setEnabled(internal)
        if not internal and self.chosen:
            self._centre_on_current()
        self.refresh()

    def _add_selection(self) -> None:
        chosen = selected_atoms(self.window)
        if not chosen:
            self.status.setText("nothing is selected")
            return
        joined = ",".join(str(a) for a in chosen)
        text = self.atoms.text().strip()
        self.atoms.setText(f"{text} {joined}".strip())

    def _centre_on_current(self) -> None:
        """Open a cell axis on a range around where the crystal is.

        Somebody scanning a hexagonal cell wants a few percent either
        side of the structure they have, and typing 38.528 twice to
        find that out is a worse first impression than the dialog
        already knowing it.
        """
        try:
            coordinate = self.coordinate()
        except Exception:                           # noqa: BLE001
            return                                  # pragma: no cover
        if coordinate is None:
            return                                  # pragma: no cover
        cell = p1.expand(self.structure)
        matrix = self.structure.lattice.matrix
        value = coordinate.value(cell.frac @ matrix, matrix)
        self.start.setValue(value * 0.94)
        self.stop.setValue(value * 1.06)

    def refresh(self) -> None:
        if not self.chosen:
            self.status.setText("")
            return
        try:
            coordinate = self.coordinate()
        except Exception as error:                  # noqa: BLE001
            self.status.setText(str(error))
            return
        cell = p1.expand(self.structure)
        matrix = self.structure.lattice.matrix
        value = coordinate.value(cell.frac @ matrix, matrix)
        units = f" {coordinate.units}" if coordinate.units else ""
        self.status.setText(
            f"{coordinate.label} is {value:.4f}{units} now")


def _wrapped(layout) -> QWidget:
    """A bare widget around a layout, for the scroll area.

    A tall form goes inside ``docks.scrolling`` rather than setting a
    minimum, which is the rule that keeps a dock column free to
    narrow -- and a dialog this tall on a laptop wants it for the
    same reason.
    """
    box = QWidget()
    box.setLayout(layout)
    return box


def _number(tip: str) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setDecimals(4)
    box.setRange(-100000.0, 1000000.0)
    box.setToolTip(tip)
    return box


class ScanDialog(QDialog):
    """Set up a relaxed scan, and say what it is going to cost."""

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

        self.engine = QComboBox()
        for engine in ENGINES:
            self.engine.addItem(engine.label, engine.name)
        self._select(self.engine, panel_engine(parent))

        # One generated form per engine, built from what the registry
        # says that engine can be asked -- so UFF4MOF, the MACE model,
        # xTB's GFN level and DFTB+'s Hamiltonian are all chosen here
        # rather than only in the panel.  Each opens on whatever the
        # panel has set for it, and only the chosen one is shown.
        self.engine_forms = {}
        self.engine_stack = QStackedWidget()
        self.engine_pages = {}
        for engine in ENGINES:
            form = ParamForm(engine.options) if engine.options else None
            if form is not None:
                form.set_values(panel_options(parent, engine.name))
                self.engine_forms[engine.name] = form
            page = form if form is not None else QWidget()
            self.engine_pages[engine.name] = \
                self.engine_stack.addWidget(page)
        self.engine.currentIndexChanged.connect(self._engine_changed)

        self.availability = QLabel("")
        self.availability.setWordWrap(True)
        self.availability.setStyleSheet("color: palette(mid);")

        self.first = AxisBox("First axis", self.structure, parent)
        self.second = AxisBox("Second axis", self.structure, parent,
                              optional=True)

        self.seed = QComboBox()
        self.seed.addItem("Carry on from the nearest point",
                          "previous")
        self.seed.addItem("Restart from this structure", "input")
        self.seed.setToolTip(
            "Carrying the last relaxed geometry into the next cell "
            "is what makes a scan affordable, and also what makes it "
            "path-dependent: near a transition the optimiser stays "
            "in the basin it arrived in.")
        self.direction = QComboBox()
        self.direction.addItem("Both, and report each", "both")
        self.direction.addItem("Forwards only", "forward")
        self.direction.addItem("Backwards only", "reverse")
        self.direction.setToolTip(
            "Walking the grid both ways and drawing both is how "
            "hysteresis shows up instead of hiding inside one curve.")

        self.method = QComboBox()
        self.method.addItems(sorted(METHODS))
        self._select(self.method, "smart")
        self.method.setToolTip(
            "Smart descends steeply at first and changes rule as the "
            "forces fall.  Every point after the first starts near a "
            "minimum; the first one may not.")
        self.max_steps = QSpinBox()
        self.max_steps.setRange(1, 100000)
        self.max_steps.setValue(500)
        self.max_steps.setToolTip(
            "A ceiling, not a target: a point that stops here is "
            "reported as not converged and drawn apart.")
        self.tolerance = QDoubleSpinBox()
        self.tolerance.setDecimals(4)
        self.tolerance.setRange(1e-4, 100.0)
        self.tolerance.setValue(0.05)
        self.tolerance.setSuffix(" kcal/mol/A")

        self.summary = QLabel("")
        self.summary.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok |
                                   QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Run")
        self.buttons = buttons
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        self._build()
        self._engine_changed()
        for form in self.engine_forms.values():
            form.changed.connect(self._engine_changed)
        for box in (self.first, self.second):
            box.kind.currentIndexChanged.connect(self.refresh)
            box.atoms.textChanged.connect(self.refresh)
            box.steps.valueChanged.connect(self.refresh)
        self.direction.currentIndexChanged.connect(self.refresh)
        self.max_steps.valueChanged.connect(self.refresh)
        self.seed.currentIndexChanged.connect(self.refresh)
        if initial:
            self.set_values(initial)
        self.refresh()

    def _build(self) -> None:
        engine = QFormLayout()
        engine.addRow("Engine", self.engine)
        note = QLabel(
            "For a flexible framework a machine-learned potential is "
            "the better choice: UFF4MOF was never fitted to "
            "reproduce a breathing double well.")
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(mid);")

        how = QFormLayout()
        how.addRow("Starting geometry", self.seed)
        how.addRow("Direction", self.direction)
        how.addRow("Optimiser", self.method)
        how.addRow("Steps per point", self.max_steps)
        how.addRow("Force tolerance", self.tolerance)

        inner = QVBoxLayout()
        inner.addLayout(engine)
        inner.addWidget(self.engine_stack)
        inner.addWidget(self.availability)
        inner.addWidget(note)
        inner.addWidget(self.first)
        inner.addWidget(self.second)
        inner.addLayout(how)
        inner.addStretch(1)
        body = _wrapped(inner)

        layout = QVBoxLayout(self)
        layout.addWidget(scrolling(body))
        layout.addWidget(self.summary)
        layout.addWidget(self.buttons)
        self.resize(560, 660)

    def _engine_changed(self) -> None:
        """Show the chosen engine's form, and whether it can run.

        An engine that is not installed -- MACE without its extra,
        DFTB+ without a binary -- has to say so here rather than
        after a scan has been started and the first point has failed
        a hundred times over.
        """
        name = str(self.engine.currentData())
        self.engine_stack.setCurrentIndex(
            self.engine_pages.get(name, 0))
        entry = ENGINES.get(name)
        ready = entry.availability(**self.engine_values())
        self.availability.setText(
            "" if ready.ok else str(ready.reason or
                                    f"{entry.label} is not available"))
        self.refresh()

    def engine_values(self) -> dict:
        form = self.engine_forms.get(str(self.engine.currentData()))
        return dict(form.values()) if form is not None else {}

    @staticmethod
    def _select(combo, value) -> None:
        index = combo.findData(value)
        if index < 0:
            index = combo.findText(str(value))
        if index >= 0:
            combo.setCurrentIndex(index)

    # -- the line that says what this will cost ------------------------

    def refresh(self) -> None:
        """Say how many points, how long, and what is held.

        All three before the Run button rather than after it: a twelve
        by twelve grid of a real framework is a couple of hours, and
        that is a thing to find out from a dialog.
        """
        ok = self.buttons.button(QDialogButtonBox.Ok)
        if self.structure is None:
            self.summary.setText("no structure is open")
            ok.setEnabled(False)
            return
        try:
            axes = [box.axis() for box in (self.first, self.second)]
            axes = [axis for axis in axes if axis is not None]
            if not axes:
                raise ValueError("choose a coordinate to scan")
            plan = driver.plan(
                self.structure, axes,
                seed=str(self.seed.currentData()),
                direction=str(self.direction.currentData()))
        except Exception as error:                  # noqa: BLE001
            self.summary.setText(str(error))
            self.summary.setStyleSheet("color: palette(mid);")
            ok.setEnabled(False)
            return
        atoms = p1.expand(self.structure).n_atoms
        seconds = driver.estimate(
            plan, SECONDS_PER_ATOM_STEP * atoms,
            self.max_steps.value())
        self.summary.setText(
            f"{plan.n_points} points, up to about {_spell(seconds)}.  "
            f"{plan.describe()}")
        self.summary.setStyleSheet("")
        ok.setEnabled(True)

    # -- what it hands back --------------------------------------------

    def values(self) -> dict:
        engine = str(self.engine.currentData())
        out = {
            "engine": engine,
            "axis1": self.first.spec(),
            "axis1_start": self.first.start.value(),
            "axis1_stop": self.first.stop.value(),
            "axis1_steps": self.first.steps.value(),
            "axis2": self.second.spec(),
            "axis2_start": self.second.start.value(),
            "axis2_stop": self.second.stop.value(),
            "axis2_steps": self.second.steps.value(),
            "seed": str(self.seed.currentData()),
            "direction": str(self.direction.currentData()),
            "method": self.method.currentText(),
            "max_steps": self.max_steps.value(),
            "tolerance": self.tolerance.value(),
        }
        out["engine_options"] = self.engine_values()
        return out

    def set_values(self, values) -> None:
        values = dict(values or {})
        if "engine" in values:
            self._select(self.engine, values["engine"])
        for number, box in ((1, self.first), (2, self.second)):
            spec = str(values.get(f"axis{number}", "") or "")
            if spec:
                head = spec.split()[0]
                self._select(box.kind, head)
                rest = spec[len(head):].strip()
                if rest:
                    box.atoms.setText(rest)
            for name, widget in (("_start", box.start),
                                 ("_stop", box.stop)):
                if f"axis{number}{name}" in values:
                    widget.setValue(
                        float(values[f"axis{number}{name}"]))
            if f"axis{number}_steps" in values:
                box.steps.setValue(int(values[f"axis{number}_steps"]))

    @classmethod
    def ask(cls, module, action, parent=None, initial=None):
        dialog = cls(module, action, parent, initial)
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.values()


def _spell(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.0f} seconds"
    if seconds < 5400:
        return f"{seconds / 60:.0f} minutes"
    return f"{seconds / 3600:.1f} hours"
