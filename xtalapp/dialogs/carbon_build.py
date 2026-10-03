"""
xtalapp.dialogs.carbon_build
============================
The disordered-carbon builder's form, in four groups, with what the
net's shape already decides said beside it.

Nineteen parameters in one generated column was a form taller than a
laptop's screen, and the four kinds of thing they set -- the net and
cell, the disorder, the edges, the relaxation -- are four questions a
person answers separately.

**The Gauss-Bonnet readout is the reason this is not the generated
form.**  A closed sheet round a net has six times its Euler
characteristic as the sum of six minus each ring size, whatever the
seed: a dia cell's has 96 more heptagon-equivalents than pentagons.
So a ratio of five-, six- and seven-membered rings is not something a
recipe can set freely, and the form says what is fixed before anybody
asks for what cannot be had.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QVBoxLayout,
)

from xtal.carbon import build as carbon_build
from xtal.carbon.surface import SurfaceError
from xtal.modules.carbon import parse_repeat
from xtalapp.dialogs.answered import answered
from xtalapp.widgets.tone import HINT, WARNING, set_tone

#: The groups, in reading order: two columns of two.
GROUPS = (
    ("Net and cell", ("net", "repeat", "density", "radius_ratio",
                      "coverage", "layers", "interlayer")),
    ("Disorder", ("sigma_vertex", "sigma_edge", "stone_wales", "seed")),
    ("Edges", ("hydrogen", "fluorine", "oxygen", "ether", "hydroxyl",
               "carbonyl")),
    ("Relaxation", ("relax", "relax_steps")),
)


class CarbonBuildDialog(QDialog):
    """A recipe for a disordered carbon, grouped, with the rings its
    net's shape fixes."""

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
            form = ParamForm([by_name[n] for n in names], box)
            column.addWidget(form)
            column.addStretch(1)
            self.forms[title] = form
            grid.addWidget(box, k % 2, k // 2)
        given = action.coerce(initial or {})
        for form in self.forms.values():
            form.set_values({p.name: given[p.name] for p in form.params
                             if p.name in given})

        intro = QLabel(module.description, self)
        intro.setWordWrap(True)
        set_tone(intro, HINT)
        self.readout = QLabel(self)
        self.readout.setWordWrap(True)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                        | QDialogButtonBox.Cancel)
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
        for form in self.forms.values():
            form.changed.connect(self._update_readout)
        self._update_readout()

    def _update_readout(self) -> None:
        """What the net and repeat fix about the rings, or why they
        cannot be built on."""
        values = self.values(coerce=False)
        net = str(values.get("net", "")).strip()
        ok = self.buttons.button(QDialogButtonBox.Ok)
        try:
            repeat = parse_repeat(values.get("repeat", "1"))
            need = carbon_build.gauss_bonnet_need(net, repeat)
        except (SurfaceError, ValueError) as exc:
            self.readout.setText(str(exc))
            set_tone(self.readout, WARNING)
            ok.setEnabled(False)
            return
        ok.setEnabled(True)
        set_tone(self.readout, HINT)
        if need < 0:
            excess = (f"{-need} more heptagon-equivalents than "
                      "pentagons")
        elif need > 0:
            excess = f"{need} more pentagon-equivalents than heptagons"
        else:
            excess = "as many pentagons as heptagons"
        self.readout.setText(
            f"The closed sheet round {net} x "
            + "x".join(str(n) for n in repeat)
            + f" has chi {need // 6} per layer, so by Gauss-Bonnet "
            f"the sum of (6 - ring size) is {need}: {excess}, "
            "whatever the seed.  Stone-Wales pairs are added on top; "
            "the ribbons' edges open some of these rings.")

    def values(self, coerce: bool = True) -> dict:
        given = {}
        for form in self.forms.values():
            given.update(form.values())
        return self.action.coerce(given) if coerce else given

    @classmethod
    def ask(cls, module, action, parent=None, initial=None):
        """The values to run with, or ``None`` if it was cancelled --
        the contract ``Action.dialog`` promises."""
        with answered(cls(module, action, parent, initial)) as dialog:
            if dialog.exec() != QDialog.Accepted:
                return None
            return dialog.values()
