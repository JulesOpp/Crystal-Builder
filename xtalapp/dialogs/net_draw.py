"""
xtalapp.dialogs.net_draw
========================
Find a net among 2926 of them, see it, and draw it.

The generated form for :data:`xtal.modules.net.PARAMS` is a text box
you have to already know the answer to type into.  There are 2926
drawable nets -- 2726 of them 3-periodic and 200 layers -- and their
names are three letters of no mnemonic value
-- **tbo**, **rht**, **soc** -- so a box is only usable by somebody who
did not need it.

**The same search the MOF builder has** -- the same widget,
:class:`~xtalapp.widgets.net_search.NetSearch` -- and deliberately
the same shape: a search over a list, a picture beside it, and the
numbers underneath.  The two are looking at the same nets from
different ends, and a user who has learned one has learned the other.

**What it searches on is what somebody knows.**  Rarely the name --
more often "the 4-coordinate ones", a space group number, or how many
kinds of vertex and edge: MOF+'s four fields, read by
:mod:`xtal.analysis.netsearch`.

**A layer is drawn in 3-D**, flat at z = 0 in its plane group's
layer group (:func:`xtal.analysis.rcsr.as_layer`), which is the cell
the MOF builder builds it in.

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
    QListWidget,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from xtal.analysis import rcsr
from xtal.analysis.netsearch import facts_of_entry
from xtal.core.lattice import Lattice
from xtal.references import RCSR, rcsr_net
from xtalapp.dialogs.mof_preview import NetPreview, reset_view_row
from xtalapp.widgets.links import SourceLinks
from xtalapp.widgets.net_search import NetSearch, add_row

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
        self.entry = rcsr.as_layer(entry)
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

        self.search = NetSearch(self)
        self.search.changed.connect(self._apply_filter)
        self.filter = self.search.name
        self.three_d = self.search.three_d
        self.two_d = self.search.two_d

        self.nets = QListWidget(self)
        self.nets.currentItemChanged.connect(self._on_net_changed)

        self.preview = NetPreview(self, minimum=(260, 210))
        self.details = QLabel(self)
        self.details.setWordWrap(True)
        self.details.setTextFormat(Qt.RichText)
        self.details.setAlignment(Qt.AlignTop)
        # The chosen net's own page in the RCSR, which every net here
        # comes from, and the database's paper.
        self.links = SourceLinks(RCSR, self)

        self.form = ParamForm(
            [p for p in self.action.params if p.name != CHOSEN], self)

        left = QWidget(self)
        column = QVBoxLayout(left)
        column.setContentsMargins(0, 0, 0, 0)
        column.addWidget(self.search)
        column.addWidget(self.nets, 1)

        right = QWidget(self)
        column = QVBoxLayout(right)
        column.setContentsMargins(0, 0, 0, 0)
        column.addWidget(self.preview, 1)
        column.addLayout(reset_view_row(self.preview))
        column.addWidget(self.details)
        column.addWidget(self.links)

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

        Read off the ``.cgd`` alone -- the header counts are p and q
        (:func:`~xtal.analysis.netsearch.facts_of_entry`) -- so the
        2926 rows cost no expansion.  The four with no cell cannot be
        drawn and are not offered.
        """
        for entry in rcsr.nets():
            if not entry.cell:
                continue
            facts = facts_of_entry(entry)
            add_row(self.nets, f"{entry.name}    {facts.summary()}",
                    facts, entry.dimension == 2)
        self.search.count(self.nets)

    # -- behaviour -----------------------------------------------------

    def _apply_filter(self) -> None:
        self.search.narrow(self.nets)

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
        self.links.set_references(
            (rcsr_net(self._entry.name, self._entry.dimension),) + RCSR)

    def _describe(self, entry) -> str:
        known = rcsr.catalogue()
        try:
            listed = known[entry.name]
        except KeyError:
            listed = None
        if entry.dimension == 2:
            rows = [f"<b>{entry.name}</b>",
                    f"Plane group {entry.group}, drawn as a layer in "
                    f"{rcsr.as_layer(entry).group}"]
        else:
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

