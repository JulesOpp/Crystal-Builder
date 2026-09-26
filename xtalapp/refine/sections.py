"""
xtalapp.refine.sections
=======================
One step's parameters as several folds of the workbench's right-hand
column -- the range in one, what is refined in another -- read and
written as though they were one form.

A step declares its parameters as one flat list, because ``xtal run``
takes them that way; a person reading eighteen rows of Rietveld
boxes wants them grouped, and wants to fold away the groups not being
changed.  :class:`SectionedForm` is a :class:`ParamForm` per group
behind the interface the workbench already used -- ``values``,
``set_values``, ``widgets``, ``notes``, ``changed`` -- so nothing that
reads a step's form had to learn it is now several.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QFormLayout, QVBoxLayout, QWidget

from xtalapp.dialogs.module_form import ParamForm
from xtalapp.docks.columns import Collapsible

__all__ = ["SectionedForm", "fold"]


class SectionedForm(QObject):
    """A step's parameters split into titled :class:`ParamForm` parts.

    ``groups`` is ``((title, names), ...)``.  A parameter no group
    names goes into the first, so a parameter added to a step later is
    shown somewhere rather than silently not asked.
    """

    #: Any widget in any part was touched.
    changed = Signal()

    def __init__(self, params, groups, notes: bool = False, parent=None):
        super().__init__(parent)
        self.params = tuple(params)
        by_name = {p.name: p for p in self.params}
        named = {n for _title, names in groups for n in names}
        stray = [p for p in self.params if p.name not in named]
        self.parts: dict[str, ParamForm] = {}
        for k, (title, names) in enumerate(groups):
            chosen = [by_name[n] for n in names if n in by_name]
            if k == 0:
                chosen += stray
            form = ParamForm(chosen, notes=notes)
            # a list of weights or groups is typed, and macOS keeps a
            # text box at its hint -- a dozen characters of it
            form.layout().setFieldGrowthPolicy(
                QFormLayout.ExpandingFieldsGrow)
            # left, not macOS's right: a box with a note beside it sits
            # in the label column, and right-aligned it drifted off
            # under the fields of the rows around it
            form.layout().setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            form.layout().setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
            form.changed.connect(self.changed.emit)
            self.parts[title] = form
        self.widgets: dict = {}
        self.notes: dict = {}
        for form in self.parts.values():
            self.widgets.update(form.widgets)
            self.notes.update(form.notes)

    def part(self, title: str) -> ParamForm:
        return self.parts[title]

    def values(self) -> dict:
        out = {}
        for form in self.parts.values():
            out.update(form.values())
        # the step's own order, which is what a run folder records
        return {p.name: out[p.name] for p in self.params if p.name in out}

    def set_values(self, values: dict | None) -> None:
        for form in self.parts.values():
            form.set_values(values)

    def set_note(self, name: str, text: str) -> None:
        for form in self.parts.values():
            if name in form.notes:
                form.set_note(name, text)

    def set_notes(self, notes: dict) -> None:
        for form in self.parts.values():
            form.set_notes(notes)


def fold(title: str, *widgets, open_: bool = True,
         on_toggle=None) -> Collapsible:
    """A :class:`Collapsible` holding ``widgets`` one above another.

    ``on_toggle`` is called after it opens or closes: the page it sits
    in has to be measured again, or the column keeps the height it had.
    """
    body = QWidget()
    layout = QVBoxLayout(body)
    layout.setContentsMargins(18, 0, 0, 6)
    for widget in widgets:
        if isinstance(widget, QWidget):
            layout.addWidget(widget)
        else:
            layout.addLayout(widget)
    section = Collapsible(title, body)
    font = section.arrow.font()
    font.setBold(True)
    section.arrow.setFont(font)
    section.set_open(open_)
    if on_toggle is not None:
        section.toggled.connect(lambda _open: on_toggle())
    return section
