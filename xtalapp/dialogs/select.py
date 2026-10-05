"""
xtalapp.dialogs.select
======================
Select > Advanced Selection...: one rule, and how it meets what is held.

The menu has a handful of fixed ways of arriving at a selection; this
is the rest of them, as one form -- by label, by coordination, by
what an atom is bonded to, a functional group, inside a box, near a
point, bonds by length or order -- with a *combine* choice so that
two rules make one selection ("the four-coordinate Zn, then intersect
with the box").

It stays open.  Apply selects and leaves the form as it was, because
the second rule is usually a small change to the first; the count
beside the button is :meth:`Document.pick` of what the form says now,
and Apply is :meth:`Document.select_by` of the same thing, so the
number shown is the number selected.  The rules themselves are
:func:`xtal.core.selection.pick`, which is what an agent's
``Session.select`` asks too.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from xtal.core import groups
from xtalapp import manual
from xtalapp.widgets.tone import HINT, set_tone

ANY = "Any element"

#: (rule, what the chooser says), in the order it lists them.
RULES = (
    ("element", "Element"),
    ("label", "Label"),
    ("site", "Site (every image)"),
    ("coordination", "Coordination"),
    ("bonded_to", "Bonded to an element"),
    ("neighbours", "Neighbours of the selection only"),
    ("shell", "Within n bonds of the selection"),
    ("radius", "Within a distance of the selection"),
    ("point", "Within a distance of a point"),
    ("box", "Inside a box"),
    ("group", "Functional group"),
    ("bonds", "Bonds"),
    ("net", "Net edges"),
)

#: (how, what the chooser says).
COMBINE = (
    ("replace", "Replace the selection"),
    ("add", "Add to the selection"),
    ("remove", "Remove from the selection"),
    ("intersect", "Intersect with the selection"),
)

#: What each rule does, said under the chooser.  The form's fields
#: name their numbers but not what the rule does with them, and "Within
#: a distance of the selection" keeps the selection while "Neighbours"
#: lets it go -- nothing on the form said which.
RULE_HELP = {
    "element": "Every atom of the ticked elements.",
    "label": "Every atom whose site label matches: * is any run of "
             "characters, ? any one, and the case counts (O1* is O1, "
             "O1A and O12).",
    "site": "Every symmetry copy of one site of the asymmetric unit.",
    "coordination": "Atoms of an element with exactly, at least or at "
                    "most this many bonded neighbours -- counted off "
                    "the bonds as they are drawn now, not distances.",
    "bonded_to": "Every atom bonded to at least one atom of this "
                 "element; the element's own atoms only where two of "
                 "them are bonded.",
    "neighbours": "The atoms one bond from the selection, without the "
                  "selection itself -- select something first.",
    "shell": "The selection and every atom up to this many bonds from "
             "it, with the bonds among them -- select something "
             "first.",
    "radius": "Every atom within this distance of any selected atom, "
              "the selection included, with the bonds among them -- "
              "select something first.",
    "point": "Every atom within this distance of a point, with the "
             "bonds among them.  The point is in fractions of the "
             "cell: 0.5, 0.5, 0.5 is its middle.",
    "box": "Every atom inside a box, faces included, with the bonds "
           "among them.  In fractions of the cell, 0 to 1 on each "
           "axis: 0, 0, 0.5 to 1, 1, 1 is the upper half.",
    "group": "The atoms of a functional group, found from the bonds; "
             "the number beside each is how many the structure has.  "
             "Take the whole group, or only the atom of each that "
             "Replace with group would swap.",
    "bonds": "Bonds, not atoms: between two elements, of an order, a "
             "length, or drawn by hand.  A field left at Any or no bound "
             "lets every bond through.",
    "net": "The edges of the drawn net, by length; no bound lets "
           "every edge through.",
}

INTRO = ("Choose a rule, fill in its fields, then choose how it "
         "combines with what is already selected and press Apply.  "
         "The window stays open, so rules can be applied one after "
         "another to build up a selection.")

#: The manual's page on this dialog, with a worked two-rule example.
MANUAL_PAGE = "essentials/select"

#: Wide enough that the longest rule's help line wraps to three lines
#: rather than six, and the functional groups' names with their
#: counts fit the chooser.
MINIMUM_WIDTH = 460

#: The bond orders a person names, and what they are called.
ORDERS = (("Any order", None), ("Single", 1.0), ("Aromatic", 1.5),
          ("Double", 2.0), ("Triple", 3.0))

#: A length bound at zero is no bound, so the spin boxes need no
#: separate "off" switch.
NO_BOUND = 0.0


def _fraction() -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(-1.0, 2.0)
    spin.setDecimals(3)
    spin.setSingleStep(0.05)
    return spin


def _distance(value: float = 0.0) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(0.0, 100.0)
    spin.setDecimals(2)
    spin.setSingleStep(0.1)
    spin.setSuffix(" Å")
    spin.setValue(value)
    return spin


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    set_tone(label, HINT)
    return label


class _Pages(QStackedWidget):
    """A stack as tall as the page in front.

    A stack is as tall as its tallest page, so a box's two rows sat
    over the Bonds page's five rows of blank space."""

    def sizeHint(self):
        page = self.currentWidget()
        return page.sizeHint() if page else super().sizeHint()

    def minimumSizeHint(self):
        page = self.currentWidget()
        return (page.minimumSizeHint() if page
                else super().minimumSizeHint())


def _triple(make) -> tuple[QWidget, list]:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    spins = [make() for _ in range(3)]
    for spin in spins:
        layout.addWidget(spin)
    return row, spins


class SelectDialog(QDialog):
    """A rule chooser, the rule's own fields, and a combine chooser."""

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Advanced selection")
        self.document = document
        elements = sorted(set(document.cell.elements))

        self.rule = QComboBox()
        for rule, text in RULES:
            self.rule.addItem(text, rule)
        self.how = QComboBox()
        for how, text in COMBINE:
            self.how.addItem(text, how)

        self.pages = _Pages()
        self._read = {}
        for rule, _text in RULES:
            page, read = getattr(self, f"_page_{rule}")(elements)
            self.pages.addWidget(page)
            self._read[rule] = read

        self.found = QLabel()
        set_tone(self.found, HINT)
        self.found.setWordWrap(True)
        self.found.setToolTip("What Apply would leave selected, with "
                              "the rule and the combine choice as "
                              "they are now")

        self.intro = _hint(INTRO)
        self.rule_help = _hint("")

        top = QFormLayout()
        top.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        top.addRow("Select", self.rule)
        top.addRow(self.rule_help)

        bottom = QFormLayout()
        bottom.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        bottom.addRow("and", self.how)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.apply_button = QPushButton("&Apply")
        self.buttons.addButton(self.apply_button,
                               QDialogButtonBox.ApplyRole)
        # After adding, not before: the box makes its own Close the
        # default, and Return in a spin box should apply the rule.
        self.buttons.button(QDialogButtonBox.Close).setAutoDefault(False)
        self.apply_button.setDefault(True)
        self.apply_button.clicked.connect(self.apply)
        self.buttons.rejected.connect(self.reject)
        manual.add_help_button(self.buttons, MANUAL_PAGE)

        layout = QVBoxLayout(self)
        layout.addWidget(self.intro)
        layout.addLayout(top)
        layout.addWidget(self.pages)
        layout.addLayout(bottom)
        layout.addWidget(self.found)
        layout.addWidget(self.buttons)
        self.setMinimumWidth(MINIMUM_WIDTH)

        self.rule.currentIndexChanged.connect(self._turn_to)
        self.rule.currentIndexChanged.connect(self.recount)
        self.how.currentIndexChanged.connect(self.recount)
        for signal in (document.selectionChanged,
                       document.structureChanged):
            signal.connect(self.recount)
        self._turn_to(self.rule.currentIndex())
        self.recount()

    def _turn_to(self, index: int) -> None:
        # The help line first: sized before its text changed, the
        # dialog kept the last rule's one line and cut Functional
        # group's three off.
        self.rule_help.setText(RULE_HELP[self.rule.itemData(index)])
        self.pages.setCurrentIndex(index)
        self.pages.updateGeometry()
        if self.isVisible():
            self.layout().activate()
            self.adjustSize()

    # -- what the form says ---------------------------------------------

    def values(self) -> tuple[str, str, dict]:
        """``(rule, how, arguments)`` -- what Apply would ask for."""
        rule = self.rule.currentData()
        return rule, self.how.currentData(), self._read[rule]()

    def preview(self):
        """The selection Apply would leave."""
        rule, how, args = self.values()
        return self.document.pick(rule, how, **args)

    def recount(self, *_args) -> None:
        chosen = self.preview()
        parts = []
        if chosen.atoms:
            parts.append(f"{len(chosen.atoms)} atoms")
        if chosen.bonds:
            parts.append(f"{len(chosen.bonds)} bonds")
        if chosen.topology:
            parts.append(f"{len(chosen.topology)} net edges")
        self.found.setText(", ".join(parts) if parts
                           else "Nothing would be selected")

    def apply(self) -> str:
        rule, how, args = self.values()
        message = self.document.select_by(rule, how, **args)
        window = self.parent()
        if hasattr(window, "show_status"):
            window.show_status(message)
        return message

    # -- one page per rule ------------------------------------------------

    def _form(self):
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        return page, form

    def _watch(self, *widgets) -> None:
        for widget in widgets:
            for name in ("valueChanged", "currentIndexChanged",
                         "textChanged", "itemChanged"):
                signal = getattr(widget, name, None)
                if signal is not None:
                    signal.connect(self.recount)
                    break

    def _element_box(self, elements, any_: bool = False) -> QComboBox:
        box = QComboBox()
        if any_:
            box.addItem(ANY, None)
        for symbol in elements:
            box.addItem(symbol, symbol)
        self._watch(box)
        return box

    def _page_element(self, elements):
        page, form = self._form()
        chosen = QListWidget()
        for symbol in elements:
            item = QListWidgetItem(symbol)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            chosen.addItem(item)
        if chosen.count():
            chosen.item(0).setCheckState(Qt.Checked)
        chosen.setMaximumHeight(120)
        self.element_list = chosen
        self._watch(chosen)
        form.addRow("Elements", chosen)

        def read():
            return {"symbols": [
                chosen.item(k).text() for k in range(chosen.count())
                if chosen.item(k).checkState() == Qt.Checked]}
        return page, read

    def _page_label(self, _elements):
        page, form = self._form()
        pattern = QLineEdit()
        pattern.setPlaceholderText("O1*")
        pattern.setToolTip("* is any run of characters, ? any one; "
                           "the case counts")
        self.label_pattern = pattern
        self._watch(pattern)
        form.addRow("Label", pattern)
        return page, lambda: {"pattern": pattern.text().strip()}

    def _page_site(self, _elements):
        page, form = self._form()
        site = QComboBox()
        for k, entry in enumerate(self.document.structure.sites):
            site.addItem(f"{k}  {entry.label or entry.element}", k)
        self._watch(site)
        form.addRow("Site", site)
        return page, lambda: {"site": site.currentData() or 0}

    def _page_coordination(self, elements):
        page, form = self._form()
        element = self._element_box(elements, any_=True)
        op = QComboBox()
        for text, value in (("exactly", "="), ("at least", ">="),
                            ("at most", "<=")):
            op.addItem(text, value)
        n = QSpinBox()
        n.setRange(0, 24)
        n.setValue(4)
        self.coordination = (element, op, n)
        self._watch(op, n)
        form.addRow("Element", element)
        row = QWidget()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.addWidget(op)
        line.addWidget(n)
        form.addRow("With", row)
        form.addRow(QLabel("bonded neighbours"))
        return page, lambda: {"element": element.currentData(),
                              "op": op.currentData(),
                              "n": n.value()}

    def _page_bonded_to(self, elements):
        page, form = self._form()
        element = self._element_box(elements)
        form.addRow("Bonded to", element)
        return page, lambda: {"element": element.currentData()}

    def _page_neighbours(self, _elements):
        # Nothing to fill in: the help line above says what it does.
        return QWidget(), lambda: {}

    def _page_shell(self, _elements):
        page, form = self._form()
        depth = QSpinBox()
        depth.setRange(1, 20)
        self._watch(depth)
        form.addRow("Bonds", depth)
        return page, lambda: {"depth": depth.value()}

    def _page_radius(self, _elements):
        page, form = self._form()
        radius = _distance(3.0)
        self._watch(radius)
        form.addRow("Within", radius)
        return page, lambda: {"radius": radius.value()}

    def _page_point(self, _elements):
        page, form = self._form()
        row, point = _triple(_fraction)
        for spin in point:
            spin.setValue(0.5)
        radius = _distance(3.0)
        self._watch(*point, radius)
        form.addRow("Point (a, b, c)", row)
        form.addRow("Within", radius)
        return page, lambda: {"point": [s.value() for s in point],
                              "radius": radius.value()}

    def _page_box(self, _elements):
        page, form = self._form()
        low_row, lower = _triple(_fraction)
        high_row, upper = _triple(_fraction)
        for spin in upper:
            spin.setValue(1.0)
        self.box = (lower, upper)
        self._watch(*lower, *upper)
        form.addRow("From (a, b, c)", low_row)
        form.addRow("To (a, b, c)", high_row)
        return page, lambda: {"lower": [s.value() for s in lower],
                              "upper": [s.value() for s in upper]}

    def _lengths(self, form):
        shortest = _distance()
        longest = _distance()
        for spin in (shortest, longest):
            spin.setSpecialValueText("no bound")
        self._watch(shortest, longest)
        form.addRow("At least", shortest)
        form.addRow("At most", longest)

        def read():
            return {"shortest": shortest.value() or None,
                    "longest": longest.value() or None}
        return (shortest, longest), read

    def _page_bonds(self, elements):
        page, form = self._form()
        first = self._element_box(elements, any_=True)
        second = self._element_box(elements, any_=True)
        order = QComboBox()
        for text, value in ORDERS:
            order.addItem(text, value)
        kind = QComboBox()
        for text, value in (("Any", "any"), ("Drawn by hand", "explicit"),
                            ("Found by the bond rules", "perceived")):
            kind.addItem(text, value)
        self._watch(order, kind)
        form.addRow("Between", first)
        form.addRow("and", second)
        form.addRow("Order", order)
        self.bond_lengths, lengths = self._lengths(form)
        form.addRow("Where from", kind)

        def read():
            return {"first": first.currentData(),
                    "second": second.currentData(),
                    "order": order.currentData(),
                    "kind": kind.currentData(), **lengths()}
        return page, read

    def _page_group(self, _elements):
        page, form = self._form()
        kind = QComboBox()
        for entry in groups.CATALOGUE:
            kind.addItem(entry.label, entry.name)
        part = QComboBox()
        part.addItem("The whole group", "whole")
        part.addItem("", "handle")
        self.group_kind, self.group_part = kind, part
        # Counted before it is watched: the count can move the
        # choice, and the form it would recount is not built yet.
        self._count_groups()
        self._name_the_handle()
        self._watch(kind, part)
        kind.currentIndexChanged.connect(self._name_the_handle)
        self.document.structureChanged.connect(self._count_groups)
        form.addRow("Group", kind)
        form.addRow("Take", part)
        return page, lambda: {"name": kind.currentData(),
                              "part": part.currentData()}

    def _count_groups(self, *_args) -> None:
        """Each group's row says how many there are, so the one that
        is there is found without trying them all."""
        counts = groups.census(self.document.structure)
        for k, entry in enumerate(groups.CATALOGUE):
            self.group_kind.setItemText(
                k, f"{entry.label} — {counts.get(entry.name, 0)}")
        found = [k for k, entry in enumerate(groups.CATALOGUE)
                 if counts.get(entry.name)]
        if found and not counts.get(self.group_kind.currentData()):
            self.group_kind.setCurrentIndex(found[0])

    def _name_the_handle(self, *_args) -> None:
        handle = groups.KINDS[self.group_kind.currentData()].handle
        self.group_part.setItemText(1, f"Only {handle}")

    def _page_net(self, _elements):
        page, form = self._form()
        _spins, lengths = self._lengths(form)
        return page, lengths

    @classmethod
    def open_for(cls, document, parent=None) -> SelectDialog:
        """Show one, modeless, over ``document``."""
        dialog = cls(document, parent)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.show()
        return dialog
