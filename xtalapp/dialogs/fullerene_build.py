"""
xtalapp.dialogs.fullerene_build
===============================
The fullerene builder's form: a size, and the isomers that size has.

**The isomer list is the reason this is not the generated form.**
Which isomers there are depends on the size -- one for C60 among the
IPR cages, forty for C40, 450 for C100 -- so the list is filled from
:mod:`xtal.fullerene.catalogue` whenever the size changes, each named
by its number and its point group or the order of its group.  A size
the table does not hold offers only a typed spiral, and a typed spiral
greys the list, since it is the cage then.  The readout under the
groups says what will be built, or why nothing can be.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QVBoxLayout,
)

from xtal.fullerene import build as cage
from xtal.fullerene import catalogue, spiral
from xtalapp import manual
from xtalapp.dialogs.answered import answered
from xtalapp.widgets.tone import HINT, WARNING, set_tone

#: The groups, in reading order; the isomer list sits in the first.
GROUPS = (
    ("Cage", ("n", "spiral")),
    ("Atoms", ("element", "bond", "hydrogenate")),
    ("Relaxation", ("relax", "relax_steps", "vacuum")),
)


class FullereneBuildDialog(QDialog):
    """A cage by size and isomer, or by its spiral, with what it is
    said beneath."""

    def __init__(self, module, action, parent=None, initial=None):
        from xtalapp.dialogs.module_form import ParamForm

        super().__init__(parent)
        self.module = module
        self.action = action
        self.setWindowTitle(f"{module.label}: "
                            f"{action.label.rstrip('.')}")
        by_name = {p.name: p for p in action.params}
        self.forms = {}
        grid = QGridLayout()
        for k, (title, names) in enumerate(GROUPS):
            box = QGroupBox(title, self)
            column = QVBoxLayout(box)
            if title == "Cage":
                # The list sits under the size it follows, and the
                # spiral that replaces it comes last: two forms either
                # side of a row of our own.
                size, typed = names
                self.forms[title] = ParamForm([by_name[size]], box)
                column.addWidget(self.forms[title])
                self.isomer = QComboBox(box)
                self.isomer.setToolTip(by_name["isomer"].help)
                row = QFormLayout()
                row.addRow(by_name["isomer"].title, self.isomer)
                column.addLayout(row)
                self.forms["Spiral"] = ParamForm([by_name[typed]], box)
                self.forms["Spiral"].widgets[typed].setPlaceholderText(
                    "12 pentagon places")
                column.addWidget(self.forms["Spiral"])
            else:
                self.forms[title] = ParamForm(
                    [by_name[n] for n in names], box)
                column.addWidget(self.forms[title])
            column.addStretch(1)
            grid.addWidget(box, 0 if k == 0 else 1, 0 if k < 2 else 1)
        given = action.coerce(initial or {})
        for form in self.forms.values():
            form.set_values({p.name: given[p.name] for p in form.params
                             if p.name in given})
        self._fill_isomers(given["n"], given["isomer"])

        intro = QLabel(module.description, self)
        intro.setWordWrap(True)
        set_tone(intro, HINT)
        self.readout = QLabel(self)
        self.readout.setWordWrap(True)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                        | QDialogButtonBox.Cancel)
        manual.add_help_button(self.buttons, "frameworks/fullerene")
        self.buttons.button(QDialogButtonBox.Ok).setText("Build")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(grid)
        layout.addWidget(self.readout)
        layout.addWidget(self.buttons)
        # Connected once the forms hold what they start with: filling
        # them fires ``changed`` before there is a readout to write.
        self._size = given["n"]
        for form in self.forms.values():
            form.changed.connect(self._on_changed)
        self.isomer.currentIndexChanged.connect(self._update_readout)
        self._update_readout()

    def _fill_isomers(self, n: int, chosen: int = 0) -> None:
        """The size's isomers, its default first; one row saying a
        spiral is needed where the table has none."""
        self.isomer.blockSignals(True)
        self.isomer.clear()
        try:
            rows = catalogue.isomers(n)
        except spiral.FullereneError:
            rows = ()
        if rows:
            default = catalogue.default(n)
            self.isomer.addItem(f"Default: {default.name}", 0)
            for row in rows:
                self.isomer.addItem(row.label, row.number)
        else:
            self.isomer.addItem("Not in the table: type its spiral", 0)
        index = self.isomer.findData(chosen)
        self.isomer.setCurrentIndex(max(index, 0))
        self.isomer.blockSignals(False)

    def _on_changed(self) -> None:
        n = self.values(coerce=False).get("n")
        if n != self._size:
            self._size = n
            self._fill_isomers(n)
        self._update_readout()

    def _update_readout(self) -> None:
        """What will be built, or why nothing can be."""
        values = self.values()
        typed = bool(str(values["spiral"]).strip())
        self.isomer.setEnabled(not typed)
        ok = self.buttons.button(QDialogButtonBox.Ok)
        try:
            recipe = cage.checked(cage.Recipe(**values))
            if typed:
                spiral.wind(recipe.n, cage.parse_spiral(recipe.spiral))
                row = None
            else:
                row = catalogue.isomer(recipe.n, recipe.isomer
                                       or catalogue.default(
                                           recipe.n).number)
        except spiral.FullereneError as exc:
            self.readout.setText(f"{str(exc)[:1].upper()}{str(exc)[1:]}.")
            set_tone(self.readout, WARNING)
            ok.setEnabled(False)
            return
        ok.setEnabled(True)
        set_tone(self.readout, HINT)
        if row is None:
            self.readout.setText(
                f"A typed spiral: {cage.title_of(recipe, None)}, named "
                f"after the table's isomer if it is one.")
            return
        isolated = ("its pentagons isolated" if row.ipr
                    else "some pentagons sharing a bond")
        self.readout.setText(
            f"{cage.title_of(recipe, row)}: {row.label}, {isolated}.  "
            f"Spiral {' '.join(str(p) for p in row.spiral)}.")

    def values(self, coerce: bool = True) -> dict:
        given = {}
        for form in self.forms.values():
            given.update(form.values())
        given["isomer"] = self.isomer.currentData() or 0
        return self.action.coerce(given) if coerce else given

    @classmethod
    def ask(cls, module, action, parent=None, initial=None):
        """The values to run with, or ``None`` if it was cancelled --
        the contract ``Action.dialog`` promises."""
        with answered(cls(module, action, parent, initial)) as dialog:
            if dialog.exec() != QDialog.Accepted:
                return None
            return dialog.values()
