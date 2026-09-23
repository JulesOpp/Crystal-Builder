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
    QSizePolicy,
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
from xtalapp.widgets.atom_types import HEADING as TYPES_HEADING
from xtalapp.widgets.atom_types import AtomTypeTable, warnings_text
from xtalapp.widgets.tone import HINT, set_tone

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
    """The P1 atoms selected in the tab in front, in the order they
    were picked -- which is the order of a torsion's four atoms."""
    document = _document(window)
    if document is None:
        return []
    selection = document.selection
    order = [int(a) for a in getattr(selection, "order", ())]
    if sorted(order) == sorted(int(a) for a in selection.atoms):
        return order
    return sorted(int(a) for a in selection.atoms)


def _document(window):
    if window is None or not hasattr(window, "current_document"):
        return None
    return window.current_document()


def cell_choices(structure) -> list[tuple[str, str]]:
    """``(label, parameter)`` for every cell parameter a scan may set.

    What the list holds is the crystal system's: a cubic cell offers
    *a* alone, a hexagonal one *a* and *c*, a monoclinic one the three
    lengths and beta.  What moves with each is spelled out, and all of
    it -- a cubic *c* is tied to *b*, which is tied to *a*, and
    "b follows it" alone read as though *c* stayed where it was.
    """
    constraint = structure.space_group.cell_constraint
    out = []
    for index, name in enumerate(PARAMETER_NAMES):
        if not constraint.is_free(index):
            continue
        # Spelled out, because "scanning a also moves b" is the whole
        # difference between a trigonal crystal and a structure its
        # own operations no longer fit.
        followers = [PARAMETER_NAMES[i]
                     for i in constraint.followers(index)]
        label = (f"Lattice {name}" if index < 3
                 else f"Cell angle {name}")
        if len(followers) == 1:
            label += f"  ({followers[0]} follows)"
        elif followers:
            label += (f"  ({', '.join(followers[:-1])} and "
                      f"{followers[-1]} follow)")
        out.append((label, name))
    return out


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
        for label, name in cell_choices(structure):
            self.kind.addItem(label, name)
        constraint = structure.space_group.cell_constraint
        self.kind.setToolTip(
            f"A {constraint.system} cell: "
            f"{constraint.describe()}.  Only the parameters it "
            f"leaves free can be scanned.")
        self.kind.addItem("Cell volume (shape relaxes)", "volume")
        for name, label, _anchors in INTERNAL:
            self.kind.addItem(label, name)

        self.atoms = QLineEdit()
        self.atoms.setPlaceholderText(
            "atom indices, e.g. 0, 1, 2, 3  (+ joins a centroid)")
        self.from_selection = QPushButton("Add the selection")
        self.from_selection.setToolTip(
            "Append the selected atoms, in the order they were "
            "picked.  More atoms than the coordinate still needs -- "
            "or any selection, for a plane -- become one centroid, "
            "written 4+5+6, and it follows them.")

        self.start = _number("From")
        self.stop = _number("To")
        self.steps = QSpinBox()
        self.steps.setRange(1, 201)
        self.steps.setValue(7)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        set_tone(self.status, HINT)

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
        text = self.atoms.text().strip().rstrip(",").strip()
        try:
            have = len(scan_module.read_anchors(text, text))
        except Exception:                           # noqa: BLE001
            have = 0
        wanted = dict((name, anchors) for name, _label, anchors
                      in INTERNAL).get(self.chosen, 0)
        # Separate atoms when they fit what the coordinate still
        # needs -- two chlorides picked for a distance are its two
        # ends -- and one centroid when they do not, which is how "the
        # middle of that ring" is said.  A plane is always a group:
        # one atom is not a plane.
        if self.chosen != "plane" and len(chosen) <= wanted - have:
            groups = [[a] for a in chosen]
        else:
            groups = [chosen]
        added = scan_module.spell_anchors(groups)
        self.atoms.setText(f"{text}, {added}" if text else added)

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
        self.engine_forms, self.engine_stack, self.engine_pages = \
            _engine_forms(parent)
        self.engine.currentIndexChanged.connect(self._engine_changed)

        self.availability = QLabel("")
        self.availability.setWordWrap(True)
        set_tone(self.availability, HINT)

        # The same table the Force Field panel shows, over the same
        # document: a scan runs the engine for hours on these types,
        # which makes this the place a wrong one costs most.
        self.types_heading = QLabel(TYPES_HEADING)
        self.types = AtomTypeTable()
        self.types.statusMessage.connect(self._type_overridden)
        self.types_note = QLabel("")
        self.types_note.setWordWrap(True)
        set_tone(self.types_note, HINT)

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

        # A second, cheaper engine run first at every point.  Its own
        # forms, because "UFF4MOF ahead of MACE" needs UFF's parameter
        # set chosen here even while the panel is set up for MACE.
        self.pre_engine = QComboBox()
        self.pre_engine.addItem("Nothing", "")
        for engine in ENGINES:
            self.pre_engine.addItem(engine.label, engine.name)
        self.pre_engine.setToolTip(
            "A cheaper engine run at every point before the one the "
            "landscape is of.  A volume step moves every atom with "
            "the cell, and this spends the long walk back at the "
            "cheap price.  Only the main engine's energy is "
            "reported.")
        self.pre_forms, self.pre_stack, self.pre_pages = \
            _engine_forms(parent)
        self.pre_availability = QLabel("")
        self.pre_availability.setWordWrap(True)
        set_tone(self.pre_availability, HINT)
        self.pre_max_steps = QSpinBox()
        self.pre_max_steps.setRange(1, 100000)
        self.pre_max_steps.setValue(500)
        self.pre_tolerance = QDoubleSpinBox()
        self.pre_tolerance.setDecimals(4)
        self.pre_tolerance.setRange(1e-4, 100.0)
        self.pre_tolerance.setValue(0.5)
        self.pre_tolerance.setSuffix(" kcal/mol/A")
        self.pre_tolerance.setToolTip(
            "Loose on purpose: the cheap engine's minimum is not the "
            "one wanted, so converging to it tightly buys nothing.")
        self.pre_engine.currentIndexChanged.connect(self._pre_changed)

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
        self._pre_changed()
        for form in self.engine_forms.values():
            form.changed.connect(self._engine_changed)
        for form in self.pre_forms.values():
            form.changed.connect(self._pre_changed)
        self.pre_max_steps.valueChanged.connect(self.refresh)
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
        set_tone(note, HINT)

        how = QFormLayout()
        how.addRow("Starting geometry", self.seed)
        how.addRow("Direction", self.direction)
        how.addRow("Optimiser", self.method)
        how.addRow("Steps per point", self.max_steps)
        how.addRow("Force tolerance", self.tolerance)

        # Not a group box: its frame's margins pushed the wider engine
        # forms past the dialog's width and grew a sideways scroll.
        self.pre_box = QWidget()
        pre = QVBoxLayout(self.pre_box)
        pre.setContentsMargins(0, 0, 0, 0)
        heading = QLabel("Pre-relaxation")
        heading.setStyleSheet("font-weight: bold;")
        pre.addWidget(heading)
        chooser = QFormLayout()
        chooser.addRow("Pre-relax with", self.pre_engine)
        pre.addLayout(chooser)
        pre.addWidget(self.pre_stack)
        pre.addWidget(self.pre_availability)
        self.pre_limits = QWidget()
        limits = QFormLayout(self.pre_limits)
        limits.setContentsMargins(0, 0, 0, 0)
        limits.addRow("Steps per point", self.pre_max_steps)
        limits.addRow("Force tolerance", self.pre_tolerance)
        pre.addWidget(self.pre_limits)

        inner = QVBoxLayout()
        inner.addLayout(engine)
        inner.addWidget(self.engine_stack)
        inner.addWidget(self.availability)
        inner.addWidget(self.types_heading)
        inner.addWidget(self.types)
        inner.addWidget(self.types_note)
        inner.addWidget(note)
        inner.addWidget(self.first)
        inner.addWidget(self.second)
        inner.addLayout(how)
        inner.addWidget(self.pre_box)
        inner.addStretch(1)
        body = _wrapped(inner)

        layout = QVBoxLayout(self)
        layout.addWidget(scrolling(body))
        layout.addWidget(self.summary)
        layout.addWidget(self.buttons)
        self.resize(560, 660)

    def _engine_changed(self) -> None:
        """Show the chosen engine's form, and whether it can run."""
        name = str(self.engine.currentData())
        _show_page(self.engine_stack, self.engine_pages.get(name, 0))
        self.availability.setText(
            _unavailable(name, self.engine_values()))
        self.refresh_types()
        self.refresh()

    def _pre_changed(self) -> None:
        """Show the pre-relaxation engine's form, or nothing at all.

        Its forms and limits are hidden while it is off, so that the
        dialog of somebody who never wants one is no longer for it.
        """
        name = str(self.pre_engine.currentData() or "")
        self.pre_stack.setVisible(bool(name))
        self.pre_limits.setVisible(bool(name))
        if name:
            _show_page(self.pre_stack, self.pre_pages.get(name, 0))
        self.pre_availability.setText(
            _unavailable(name, self.pre_values()) if name else "")
        self.pre_availability.setVisible(
            bool(self.pre_availability.text()))
        self.refresh()

    def refresh_types(self) -> None:
        """Type the structure as the chosen engine will, and show it.

        Only for an engine that has atom types.  DFTB+, xTB and MACE
        have none -- a tight-binding Hamiltonian or a learned
        potential sees elements -- and an empty table under the
        heading would read as a failure to type them.  The parameter
        set is the one chosen *here*: UFF4MOF types a paddlewheel
        copper differently, and the table has to show what the scan
        will run.
        """
        entry = ENGINES.get(str(self.engine.currentData()))
        shown = "types" in entry.provides
        for widget in (self.types_heading, self.types):
            widget.setVisible(shown)
        if not shown:
            self.types_note.setText("")
            self.types_note.setVisible(False)
            return
        try:
            rows = self.types.fill(
                _document(self.window),
                self.engine_values().get("parameter_set"))
            said = warnings_text(rows)
        except Exception as error:                  # noqa: BLE001
            said = str(error)
        self.types.fit_rows()
        self.types_note.setText(said)
        self.types_note.setVisible(bool(said))

    def _type_overridden(self, message: str) -> None:
        if hasattr(self.window, "show_message"):
            self.window.show_message(message)
        self.refresh_types()

    def engine_values(self) -> dict:
        form = self.engine_forms.get(str(self.engine.currentData()))
        return dict(form.values()) if form is not None else {}

    def pre_values(self) -> dict:
        form = self.pre_forms.get(str(self.pre_engine.currentData()))
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
            set_tone(self.summary, HINT)
            ok.setEnabled(False)
            return
        atoms = p1.expand(self.structure).n_atoms
        pre_steps = (self.pre_max_steps.value()
                     if self.pre_engine.currentData() else 0)
        seconds = driver.estimate(
            plan, SECONDS_PER_ATOM_STEP * atoms,
            self.max_steps.value(), pre_steps)
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
        out["pre_engine"] = str(self.pre_engine.currentData() or "")
        out["pre_engine_options"] = self.pre_values()
        out["pre_max_steps"] = self.pre_max_steps.value()
        out["pre_tolerance"] = self.pre_tolerance.value()
        return out

    def set_values(self, values) -> None:
        values = dict(values or {})
        if "engine" in values:
            self._select(self.engine, values["engine"])
        if "pre_engine" in values:
            self._select(self.pre_engine, values["pre_engine"] or "")
        form = self.pre_forms.get(str(self.pre_engine.currentData()))
        if form is not None and values.get("pre_engine_options"):
            form.set_values(values["pre_engine_options"])
        if "pre_max_steps" in values:
            self.pre_max_steps.setValue(int(values["pre_max_steps"]))
        if "pre_tolerance" in values:
            self.pre_tolerance.setValue(float(values["pre_tolerance"]))
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


def _engine_forms(window):
    """One generated form per engine, each opened on what the panel
    has set for it; ``(forms, stack, pages)``."""
    forms = {}
    stack = QStackedWidget()
    pages = {}
    for engine in ENGINES:
        form = ParamForm(engine.options) if engine.options else None
        if form is not None:
            form.set_values(panel_options(window, engine.name))
            forms[engine.name] = form
        page = form if form is not None else QWidget()
        pages[engine.name] = stack.addWidget(page)
    return forms, stack, pages


def _show_page(stack, current: int) -> None:
    # A stack is as tall as its tallest page, so UFF's four rows sat
    # above DFTB+'s ten rows of empty space.  Only the page on show
    # gets a say in the height.
    for page in range(stack.count()):
        stack.widget(page).setSizePolicy(
            QSizePolicy.Preferred,
            QSizePolicy.Preferred if page == current
            else QSizePolicy.Ignored)
    stack.setCurrentIndex(current)
    stack.adjustSize()


def _unavailable(name: str, values: dict) -> str:
    """Why this engine cannot run, or ``""`` when it can.

    An engine that is not installed -- MACE without its extra, DFTB+
    without a binary -- has to say so in the dialog rather than after
    a scan has started and the first point has failed a hundred
    times over.
    """
    entry = ENGINES.get(name)
    ready = entry.availability(**values)
    return "" if ready.ok else str(
        ready.reason or f"{entry.label} is not available")


def _spell(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.0f} seconds"
    if seconds < 5400:
        return f"{seconds / 60:.0f} minutes"
    return f"{seconds / 3600:.1f} hours"
