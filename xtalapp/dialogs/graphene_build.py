"""
xtalapp.dialogs.graphene_build
==============================
The graphene builder's form: the generated one, and the commensurate
twists near the one typed.

**The list of twists is the reason this is not the generated form.**
Only some angles close into a cell, and how many atoms that cell
holds jumps between neighbours -- 1.08 degrees is 11 164 atoms a
bilayer, 1.10 is 43 204 -- so the angles nearest the typed one, each
with its count, are listed under the box, only those under the size
limit at the repeat and layers asked.  Choosing one writes it into
the box as :func:`xtal.graphene.twist.spelled` spells it, which reads
back to that cell.  The readout under the list says what will be
built, or why nothing can be.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialogButtonBox,
    QFormLayout,
)

from xtal.core import limits
from xtal.graphene import build as sheet
from xtal.graphene import twist
from xtalapp import manual
from xtalapp.dialogs.module_form import ModuleDialog
from xtalapp.widgets.tone import HINT, WARNING, set_tone

#: How many commensurate angles the list offers.
LISTED = 8


class GrapheneBuildDialog(ModuleDialog):
    """The sheets' form, with the commensurate twists near the one
    typed and what will be built said beneath."""

    def __init__(self, module, action, parent=None, initial=None):
        super().__init__(module, action, parent, initial)
        self.buttons.button(QDialogButtonBox.Ok).setText("Build")
        manual.add_help_button(self.buttons, "frameworks/graphene")
        self.twists = QComboBox(self)
        self.twists.setToolTip(
            "The commensurate angles nearest the Twist, each with the "
            "atoms its cell holds at this repeat and these layers; "
            "only those under the size limit are listed.")
        row = QFormLayout()
        row.addRow("Commensurate", self.twists)
        layout = self.layout()
        layout.insertLayout(layout.indexOf(self.form) + 1, row)
        self.twists.activated.connect(self._on_chosen)
        self._show_size()

    def _show_size(self) -> None:
        """What will be built, or why nothing can be; and, for a
        twisted stack, the angles near the one typed."""
        if not hasattr(self, "twists"):
            # The base class's constructor calls this before the list
            # exists; it is called again once it does.
            return
        values = self.values()
        twisted = values["stacking"] == sheet.TWISTED
        self.form.widgets["twist"].setEnabled(twisted)
        self.twists.setEnabled(twisted)
        ok = self.buttons.button(QDialogButtonBox.Ok)
        try:
            recipe = sheet.checked(sheet.Recipe(**values))
        except sheet.GrapheneError as exc:
            self._fill(values, None)
            self._say(f"{str(exc)[:1].upper()}{str(exc)[1:]}.", WARNING)
            ok.setEnabled(False)
            return
        self._fill(values, recipe)
        verdict = limits.check_graphene(recipe)
        ok.setEnabled(not verdict.refused)
        if verdict.warned:
            self._say(f"{verdict.sentence[:1].upper()}"
                      f"{verdict.sentence[1:]}.", WARNING)
            return
        self._say(f"{recipe.title[:1].upper()}{recipe.title[1:]}: "
                  f"{limits.count(verdict.estimate)} atoms.", HINT)

    def _fill(self, values, recipe) -> None:
        """The angles nearest the typed one, largest first, the typed
        one's own cell chosen when it is among them."""
        self.twists.clear()
        if values["stacking"] != sheet.TWISTED:
            return
        try:
            angle = float(str(values["twist"]).strip().rstrip("°"))
        except ValueError:
            return
        layers = max(int(values["layers"]), 1)
        # Atoms a build has per atom of one bilayer cell.
        per = sheet.atoms_per_layer(sheet.Recipe(
            cells_a=values["cells_a"], cells_b=values["cells_b"],
            rectangular=values["rectangular"])) * layers / 4
        hard = limits.bounds("graphene")[1] or twist.MAX_ATOMS * per
        near = twist.nearest(angle, LISTED,
                             max_atoms=min(int(hard / per),
                                           twist.MAX_ATOMS))
        chosen = recipe.moire if recipe is not None else None
        for each in sorted(near, key=lambda t: -t.angle):
            self.twists.addItem(
                f"{twist.spelled(each)}°, (m, r) = ({each.m}, {each.r}): "
                f"{limits.count(each.atoms * per)} atoms",
                twist.spelled(each))
            if each == chosen:
                self.twists.setCurrentIndex(self.twists.count() - 1)
        if chosen not in near:
            self.twists.setCurrentIndex(-1)

    def _on_chosen(self, index: int) -> None:
        self.form.widgets["twist"].setText(self.twists.itemData(index))

    def _say(self, text: str, tone) -> None:
        self.size.setText(text)
        set_tone(self.size, tone)
        self.size.show()
