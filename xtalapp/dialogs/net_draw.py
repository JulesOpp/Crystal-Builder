"""
xtalapp.dialogs.net_draw
========================
Find a net among 2726 of them, see it, and draw it.

The generated form for :data:`xtal.modules.net.PARAMS` is a text box
you have to already know the answer to type into.  There are 2726
drawable nets and their names are three letters of no mnemonic value
-- **tbo**, **rht**, **soc** -- so a box is only usable by somebody who
did not need it.

**The same search the MOF builder has**, and deliberately the same
shape: a filter over a list, a picture beside it, and the numbers
underneath.  The two are looking at the same 2929 nets from different
ends, and a user who has learned one has learned the other.

**What it filters on is what somebody knows.**  Rarely the name --
more often "the 4-coordinate ones", or a space group, or the number of
vertices.  So every row carries its name, its group, its coordination
figures and its counts in one lowered string, matched as a substring,
which finds ``pcu`` from ``pc``, every cubic net from ``m-3m`` and
every 6-coordinate one from ``6-c``.

**The picture comes from the same place the MOF builder's does.**
:class:`~xtalapp.dialogs.mof_preview.NetPreview` wants an object with
``placement()`` and ``lattice()`` on it, PORMAKE's ``Topology`` has
those, and :func:`xtal.analysis.rcsr.placement` returns exactly the
pair it asks for -- so :class:`_Placed` is nine lines and there is no
second net renderer.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from xtal.analysis import rcsr
from xtal.core.lattice import Lattice
from xtalapp.dialogs.mof_preview import NetPreview

#: The parameter the list answers, and so the one the form must not
#: also ask about.  Everything else in ``PARAMS`` is a number and goes
#: in the form unchanged.
CHOSEN = "net"


class _Placed:
    """An RCSR entry wearing the two methods :class:`NetPreview` wants.

    PORMAKE's ``Topology`` is what that widget was written against and
    a ``CgdEntry`` is not one, but the only two things asked of it are
    a placement and a cell -- and both are a call away.  An adapter is
    cheaper than a second renderer and keeps the two pictures the same
    picture.
    """

    def __init__(self, entry):
        self.entry = entry
        self.name = entry.name

    def placement(self):
        return rcsr.placement(self.entry)

    def lattice(self) -> Lattice:
        a, b, c, alpha, beta, gamma = self.entry.cell
        return Lattice.from_parameters(a, b, c, alpha, beta, gamma)


class NetDrawDialog(QDialog):
    """The net to draw, chosen by looking rather than by typing."""

    def __init__(self, module, action, parent=None, initial=None):
        super().__init__(parent)
        self.module = module
        self.action = action
        self.setWindowTitle(f"{module.label}: "
                            f"{action.label.rstrip('.')}")
        self._entry = None
        self._build_ui()
        self._fill()
        given = action.coerce(initial or {})
        self.form.set_values({k: v for k, v in given.items()
                              if k != CHOSEN})
        if not self._select(str(given.get(CHOSEN, ""))):
            self._select("pcu")

    # -- construction --------------------------------------------------

    def _build_ui(self) -> None:
        from xtalapp.dialogs.module_form import ParamForm

        self.filter = QLineEdit(self)
        self.filter.setPlaceholderText(
            "Filter by name, coordination or space group -- pcu, 4-c, "
            "Fm-3m")
        self.filter.textChanged.connect(self._apply_filter)

        self.nets = QListWidget(self)
        self.nets.currentItemChanged.connect(self._on_net_changed)

        self.preview = NetPreview(self, minimum=(260, 210))
        self.details = QLabel(self)
        self.details.setWordWrap(True)
        self.details.setTextFormat(Qt.RichText)
        self.details.setAlignment(Qt.AlignTop)

        self.form = ParamForm(
            [p for p in self.action.params if p.name != CHOSEN], self)

        left = QWidget(self)
        column = QVBoxLayout(left)
        column.setContentsMargins(0, 0, 0, 0)
        column.addWidget(self.filter)
        column.addWidget(self.nets, 1)

        right = QWidget(self)
        column = QVBoxLayout(right)
        column.setContentsMargins(0, 0, 0, 0)
        column.addWidget(self.preview, 1)
        column.addWidget(self.details)

        split = QSplitter(Qt.Horizontal, self)
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                        | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Draw")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(split, 1)
        layout.addWidget(self.form)
        layout.addWidget(self.buttons)
        self.resize(720, 520)

    def _fill(self) -> None:
        """Every drawable net, with what it can be searched by.

        The catalogue is what carries the coordination and the counts;
        the ``.cgd`` is what carries the cell, and a net without one
        cannot be drawn -- so the two are joined here and only the
        entries in both are offered.
        """
        described = {entry.name: entry
                     for entry in rcsr.catalogue().entries}
        for entry in rcsr.nets():
            if entry.dimension != 3 or not entry.cell:
                continue
            known = described.get(entry.name)
            summary = _summary(entry, known)
            item = QListWidgetItem(f"{entry.name}    {summary}")
            item.setData(Qt.UserRole, entry.name)
            # Lowered once here rather than on every keystroke of a
            # 2726-row list, which is the same reason the MOF
            # builder's does it.
            item.setData(Qt.UserRole + 1,
                         f"{entry.name} {summary}".lower())
            self.nets.addItem(item)

    # -- behaviour -----------------------------------------------------

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for index in range(self.nets.count()):
            item = self.nets.item(index)
            item.setHidden(bool(needle) and needle not in
                           str(item.data(Qt.UserRole + 1)))

    def _select(self, name: str) -> bool:
        for index in range(self.nets.count()):
            item = self.nets.item(index)
            if item.data(Qt.UserRole) == name:
                self.nets.setCurrentItem(item)
                self.nets.scrollToItem(item)
                return True
        return False

    def _on_net_changed(self, current, _previous=None) -> None:
        if current is None:
            return
        name = str(current.data(Qt.UserRole))
        try:
            self._entry = rcsr.nets()[name]
        except KeyError:                            # pragma: no cover
            self._entry = None
            return
        self.preview.set_topology(_Placed(self._entry))
        self.details.setText(self._describe(self._entry))

    def _describe(self, entry) -> str:
        known = rcsr.catalogue()
        try:
            listed = known[entry.name]
        except KeyError:
            listed = None
        rows = [f"<b>{entry.name}</b>", f"Space group {entry.group}"]
        if listed is not None:
            rows.append("Coordination "
                        + ", ".join(str(c)
                                    for c in listed.coordination()))
            rows.append(f"{listed.vertices} vertices and "
                        f"{listed.edges} edges per cell")
        # Said as "asymmetric unit" rather than "in the file" because
        # the two counts above are the whole cell and these are what
        # the group is applied to -- sod is 1 and 12, and a reader
        # given both without that word reads them as disagreeing.
        rows.append(f"{len(entry.nodes)} vertex site(s) and "
                    f"{len(entry.edges)} edge(s) in the "
                    "asymmetric unit")
        return "<br>".join(rows)

    # -- the contract --------------------------------------------------

    def values(self) -> dict:
        given = dict(self.form.values())
        given[CHOSEN] = self._entry.name if self._entry else ""
        return self.action.coerce(given)

    @classmethod
    def ask(cls, module, action, parent=None, initial=None):
        """The values to run with, or ``None`` if it was cancelled.

        The same contract as
        :meth:`xtalapp.dialogs.module_form.ModuleDialog.ask`, which is
        the whole of what ``Action.dialog`` promises.
        """
        dialog = cls(module, action, parent, initial)
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.values()


def _summary(entry, listed) -> str:
    """One line per row: what somebody would search by.

    The coordination is written ``4-c`` the way the RCSR writes it, so
    that typing what is on the page finds the net it names.
    """
    parts = [entry.group]
    if listed is not None:
        parts.append("".join(f"{c}-c " for c in listed.coordination())
                     .strip())
        parts.append(f"{listed.vertices}v {listed.edges}e")
    return "  ".join(p for p in parts if p)
