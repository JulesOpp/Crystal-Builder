"""
xtalapp.dialogs.polymer_build
=============================
The amorphous polymer builder's form: a monomer row for A and for B,
then the sequence, the size, the box and the rest.

**A monomer row is the molecule builder's box and canvas, aimed at a
repeat unit.**  A library combo of the ``Monomer`` entries, the text
box :func:`xtal.modules.polymer.monomer_of` reads (a library name, a
block file or a starred SMILES string), and the sketch.  Choosing an
entry writes its *name* into the box -- so the tab and the report say
"Polystyrene" and not a string -- and draws its SMILES; drawing on the
canvas writes the drawn SMILES into the box.  Whatever the box holds is
resolved after a pause, unrelaxed, and the row's footer says the
formula and how many atoms each end stands for, or why it is not a
monomer: the same sentence the run would fail with, said before it.

**Build is enabled only when every monomer the recipe uses resolves
and the recipe passes** :meth:`xtal.polymer.pack.Recipe.check`, whose
refusals -- too many atoms above all -- are written under the form.
B is used only by a copolymer, so its row is disabled for a
homopolymer, as the membrane's thickness and vacuum are for bulk.

The form is long, so it is in :func:`xtalapp.docks.scrolling`.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from xtal.build import BuildError, library
from xtal.modules import polymer as polymer_module
from xtal.polymer.monomer import monomers
from xtalapp.dialogs import sketch
from xtalapp.dialogs.build_molecule import on_change, sketch_for
from xtalapp.dialogs.module_form import ParamForm
from xtalapp.widgets.tone import HINT, WARNING, set_tone

#: The same pause the molecule builder waits after a keystroke.
QUIET_MS = 350
#: The canvas's height.  It is square and as large as it fits, and
#: left to fit it took the whole dialog for an ethylene.
SKETCH_HEIGHT = 240

#: The groups below the monomers, in reading order.
GROUPS = (
    ("Sequence", ("composition", "fraction_a", "block_a", "block_b",
                  "tacticity", "p_meso")),
    ("Size", ("chains", "length", "density", "start_density")),
    ("Box", ("periodic", "thickness", "vacuum")),
    ("Growth", ("relax_steps", "trials", "seed", "max_atoms")),
)

#: Which row each choice enables; every other row of the group is on.
_WHEN = {
    "fraction_a": ("composition", ("random",)),
    "block_a": ("composition", ("block",)),
    "block_b": ("composition", ("block",)),
    "p_meso": ("tacticity", ("atactic",)),
    "thickness": ("periodic", ("membrane",)),
    "vacuum": ("periodic", ("membrane",)),
}


class MonomerRow(QWidget):
    """One monomer: the library, the box, the sketch and a footer."""

    def __init__(self, param, parent=None):
        super().__init__(parent)
        self.param = param
        self.monomer = None
        self.problem = ""
        self.form = ParamForm([param], self)
        self.box = self.form.widgets[param.name]
        self.library = QComboBox(self)
        self.library.addItem("(type it, draw it, or name a file)", None)
        try:
            entries = monomers()
        except library.LibraryError:                # pragma: no cover
            entries = ()
        for entry in entries:
            self.library.addItem(entry.name, entry)
        self.library.currentIndexChanged.connect(self._on_library)
        self.sketch = sketch_for(self, True)
        self.sketch.setMaximumHeight(SKETCH_HEIGHT)
        self.sketch.smilesChanged.connect(self._on_sketch)
        self.footer = QLabel(self)
        self.footer.setWordWrap(True)
        self.footer.setTextFormat(Qt.RichText)

        self._quiet = QTimer(self)
        self._quiet.setSingleShot(True)
        self._quiet.setInterval(QUIET_MS)
        self._quiet.timeout.connect(self.resolve)
        on_change(self.box, self._touched)
        self.changed = None                         # set by the dialog

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.library)
        layout.addWidget(self.form)
        layout.addWidget(self.sketch, 1)
        layout.addWidget(self.footer)

    def text(self) -> str:
        return str(self.form.values().get(self.param.name) or "").strip()

    def set_text(self, text: str) -> None:
        self.form.set_values({self.param.name: text})
        self.resolve()

    def _on_library(self, *_args) -> None:
        entry = self.library.currentData()
        if entry is not None:
            self.set_text(entry.name)

    def _on_sketch(self, text: str) -> None:
        """What was drawn, into the box -- unless the box already names
        that molecule, by its string or by a library entry's name."""
        if sketch.canonical(self._smiles_of(self.text())) != \
                sketch.canonical(text):
            self.form.set_values({self.param.name: text})
            self._touched()

    def _touched(self, *_args) -> None:
        self._quiet.start()

    @staticmethod
    def _smiles_of(text: str) -> str:
        """What the sketch should draw for the box's text: a library
        entry's string for its name, nothing for a file."""
        entry = library.find(text) if text else None
        if entry is not None:
            return entry.smiles
        return "" if text.lower().endswith(".xyz") else text

    def resolve(self) -> None:
        """The box's monomer, unrelaxed, and the footer saying what it
        is or why it is not one."""
        from xtal.polymer.monomer import MonomerError

        self._quiet.stop()
        text = self.text()
        self.sketch.set_smiles(self._smiles_of(text))
        self.monomer, self.problem = None, ""
        if not text:
            self.problem = "no monomer given"
            self._say("", bad=False)
        else:
            try:
                self.monomer = polymer_module.monomer_of(
                    text, optimise=False)
            except (BuildError, MonomerError, OSError,
                    ValueError) as exc:
                self.problem = str(exc)
                self._say(self.problem, bad=True)
            else:
                self._say(_describe(self.monomer), bad=False)
        if self.changed is not None:
            self.changed()

    def _say(self, text: str, bad: bool) -> None:
        self.footer.setText(text)
        set_tone(self.footer, WARNING if bad else HINT)


def _describe(unit) -> str:
    ends = len(unit.head_members)
    what = ("a ladder: each end stands for "
            f"{ends} atoms, and a joint is a flip, not a torsion"
            if unit.is_ladder else "head and tail one atom each")
    hand = "" if unit.handed else "; no stereocentre, so no tacticity"
    return (f"<b>{unit.formula}</b>, {len(unit.body)} atoms a unit, "
            f"{unit.mass:.1f} g/mol -- {what}{hand}")


class PolymerBuildDialog(QDialog):
    """A recipe for an amorphous polymer, with its monomers checked as
    they are typed and the recipe as it is set."""

    def __init__(self, module, action, parent=None, initial=None):
        from xtalapp.docks import scrolling

        super().__init__(parent)
        self.module = module
        self.action = action
        self.setWindowTitle(f"{module.label}: "
                            f"{action.label.rstrip('.')}")
        by_name = {p.name: p for p in action.params}
        given = action.coerce(initial or {})

        # Tabs and not side by side: each row carries a canvas and its
        # toolbar, and two of them abreast scrolled the form sideways.
        self.rows = {}
        self.tabs = QTabWidget(self)
        for name, title in (("monomer", "Monomer A"),
                            ("monomer_b", "Monomer B")):
            row = MonomerRow(by_name[name], self.tabs)
            row.form.set_values({name: given.get(name, "")})
            self.rows[name] = row
            self.tabs.addTab(row, title)
        self.forms = {}
        grid = QGridLayout()
        for k, (title, names) in enumerate(GROUPS):
            box = QGroupBox(title, self)
            column = QVBoxLayout(box)
            form = ParamForm([by_name[n] for n in names], box)
            form.set_values({n: given[n] for n in names if n in given})
            column.addWidget(form)
            column.addStretch(1)
            self.forms[title] = form
            grid.addWidget(box, k // 2, k % 2)

        intro = QLabel(module.description, self)
        intro.setWordWrap(True)
        set_tone(intro, HINT)
        self.readout = QLabel(self)
        self.readout.setWordWrap(True)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                        | QDialogButtonBox.Cancel)
        self.build_button = self.buttons.button(QDialogButtonBox.Ok)
        self.build_button.setText("Build")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        inner = QWidget(self)
        body = QVBoxLayout(inner)
        body.addWidget(intro)
        body.addWidget(self.tabs)
        body.addLayout(grid)
        area = scrolling(inner)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout = QVBoxLayout(self)
        layout.addWidget(area, 1)
        layout.addWidget(self.readout)
        layout.addWidget(self.buttons)
        # As wide as the canvas's toolbar needs, since the form does not
        # scroll sideways: narrower clipped its Undo button.
        width = inner.minimumSizeHint().width()
        self.resize(width + area.verticalScrollBar().sizeHint().width()
                    + 2 * layout.contentsMargins().left(), 780)

        # Connected once everything holds what it starts with, so the
        # first readout is written once and against the whole form.
        for form in self.forms.values():
            form.changed.connect(self._update)
        for row in self.rows.values():
            row.changed = self._update
            row.resolve()
        self._update()

    def widget(self, name: str):
        """The widget for one parameter, wherever it is in the form."""
        for form in (*self.forms.values(),
                     *(r.form for r in self.rows.values())):
            if name in form.widgets:
                return form.widgets[name]
        raise KeyError(name)

    def _copolymer(self) -> bool:
        return self.values(coerce=False).get(
            "composition", "homopolymer") != "homopolymer"

    def _update(self, *_args) -> None:
        """Rows enabled by the choices that use them, and the recipe's
        verdict under the form."""
        values = self.values(coerce=False)
        for name, (choice, on) in _WHEN.items():
            self.widget(name).setEnabled(values.get(choice) in on)
        self.tabs.setTabEnabled(1, self._copolymer())
        self.rows["monomer_b"].setEnabled(self._copolymer())
        problem = self._problem()
        if problem:
            self.readout.setText(problem)
            set_tone(self.readout, WARNING)
        else:
            self.readout.setText(self._estimate())
            set_tone(self.readout, HINT)
        self.build_button.setEnabled(not problem)

    def _used(self) -> list[MonomerRow]:
        rows = [self.rows["monomer"]]
        if self._copolymer():
            rows.append(self.rows["monomer_b"])
        return rows

    def _recipe(self):
        """The recipe the form describes, over the monomers the rows
        resolved -- never embedding anything again."""
        units = [r.monomer for r in self._used()]
        return polymer_module.recipe_of(_Values(self.values()),
                                        monomers=units)

    def _problem(self) -> str:
        from xtal.polymer.pack import PackError
        from xtal.polymer.sequence import SequenceError

        for row in self._used():
            if row.monomer is None:
                title = ("Monomer A" if row is self.rows["monomer"]
                         else "Monomer B")
                return f"{title}: {row.problem or 'not resolved yet'}"
        try:
            self._recipe().check()
        except (PackError, SequenceError, ValueError) as exc:
            return str(exc)
        return ""

    def _estimate(self) -> str:
        recipe = self._recipe()
        a = recipe.box(recipe.density)
        return (f"About {recipe.n_atoms()} atoms in a "
                f"{' x '.join(f'{v:.1f}' for v in a)} A box.  Ten "
                f"chains of a hundred polyethylene units, 6000 atoms, "
                f"take about twenty seconds.")

    def values(self, coerce: bool = True) -> dict:
        given = {}
        for form in (*self.forms.values(),
                     *(r.form for r in self.rows.values())):
            given.update(form.values())
        return self.action.coerce(given) if coerce else given

    @classmethod
    def ask(cls, module, action, parent=None, initial=None):
        """The values to run with, or ``None`` if it was cancelled --
        the contract ``Action.dialog`` promises."""
        dialog = cls(module, action, parent, initial)
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.values()


class _Values:
    """Parameter values with the ``param`` a job answers to."""

    def __init__(self, values: dict):
        self._values = values

    def param(self, name, default=None):
        return self._values.get(name, default)
