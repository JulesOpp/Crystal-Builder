"""
xtalapp.dialogs.supertetrahedra_box
===================================
The MOF builder's *Supertetrahedra* section.

Live for a 4-connected net -- every zeolite the RCSR holds -- because
a supertetrahedron stands on a 4-c vertex.  Ticked, the net the build
is on becomes its decoration (``sod`` -> ``sod-st``: a trimer on every
edge, a tritopic face on each of a vertex's four edge triples), and
the rows above are asked again for a trimer and a face.  The windows
-- the parent's rings -- are listed by size, and a ticked one gets a
filler (``sod-st-f4``) and a row of its own.

The arithmetic is :mod:`xtal.mof.decorate` and nothing here repeats
it.  Every fill is tried once the net is decorated, one an event-loop
turn so a click on fau is not three seconds of fills, and one that
cannot be written is greyed in the list with its reason as the
tooltip, as a refused partitioner is; two allowed alone can still be refused
together, which is said and the tick put back.  *Suggest fillers* is
a button and not a reaction to every change, because what a window
asks is read off one trial pass of PORMAKE on the blocks chosen --
a second or two -- and a click on a suggestion fills that window.

Greyed rather than hidden, as the partition section is.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from xtal.mof import decorate, linkers
from xtal.mof.catalog import CatalogError, installed
from xtalapp.busy import busy
from xtalapp.widgets.tone import HINT, WARNING, set_tone

#: How many fillers each window lists.
SUGGESTIONS = 4

#: The zeolites offered as links while a net that is not 4-c is
#: picked: the two the cSDA and MIL-100 papers build on, and the
#: commonest others.  Any of the 63 can be typed into the search.
OFFERED = ("sod", "mtn", "lta", "rho", "cha", "fau")


class SupertetrahedraBox(QWidget):
    """Supertetrahedra on the 4-c net chosen above, and its windows."""

    #: The net to build on changed: a decorated net's name, or ``""``
    #: for the net picked in the list.
    net_changed = Signal(str)                        # noqa: N815
    #: The person clicked a filler for one slot: ``(slot key, name)``.
    use_block = Signal(int, str)                     # noqa: N815
    #: The person clicked a zeolite in the note.
    use_net = Signal(str)                            # noqa: N815

    def __init__(self, parent=None):
        super().__init__(parent)
        self.decorate = QCheckBox("Supertetrahedra on every vertex",
                                  self)
        self.decorate.setToolTip(
            "Four M3O trimers at the corners of a tetrahedron, a "
            "tritopic linker on each face: MIL-100 on mtn, the "
            "sod-ZMOFs on sod.  A trimer goes on every edge of the "
            "net and a face on each triple of a vertex's edges.")
        self.decorate.toggled.connect(self._on_decorate)
        self.same = QCheckBox("Same trimer and face in every slot",
                              self)
        self.same.setToolTip(
            "A net with several kinds of edge has a trimer slot for "
            "each, and the frameworks put the same cluster in all of "
            "them")
        self.same.setChecked(True)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.RichText)
        self.status.linkActivated.connect(self.use_net)
        set_tone(self.status, HINT)

        self.windows = QWidget(self)
        self.grid = QGridLayout(self.windows)
        self.grid.setContentsMargins(0, 0, 0, 0)

        self.suggest = QPushButton("Suggest fillers", self)
        self.suggest.setToolTip(
            "What each window asks of a pyridyl filler on the trimer "
            "and face chosen above -- a donor on every site it takes "
            "-- and the nearest molecules, catalogue and generated.  "
            "Worked out on one trial build.")
        self.suggest.clicked.connect(self._suggest)
        self.suggestions = QLabel(self)
        self.suggestions.setWordWrap(True)
        self.suggestions.setTextFormat(Qt.RichText)
        self.suggestions.linkActivated.connect(self._clicked)
        set_tone(self.suggestions, HINT)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.decorate)
        row.addWidget(self.same)
        row.addStretch(1)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addWidget(self.suggest)
        buttons.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(row)
        layout.addWidget(self.status)
        layout.addWidget(self.windows)
        layout.addLayout(buttons)
        layout.addWidget(self.suggestions)

        self._catalog = None
        self._parent = None
        self._decorated = None
        #: The fills the net is built with, ``(size, every)``.
        self._spec: list[tuple[int, int]] = []
        #: size -> (tick, every combo).
        self._rows: dict[int, tuple[QCheckBox, QComboBox]] = {}
        #: size -> (its note, what the note says before a size).
        self._notes: dict[int, tuple[QLabel, str]] = {}
        self._topology = None
        self._chosen: dict[int, str] = {}
        #: The fills still to be tried, ``(size, every)``, one a turn.
        self._untried: list[tuple[int, int]] = []
        self._trying = QTimer(self)
        self._trying.setSingleShot(True)
        self._trying.setInterval(0)
        self._trying.timeout.connect(self._try_next)
        self.set_net(None, None)

    # -- what it is told -----------------------------------------------

    def set_net(self, catalog, topology) -> None:
        """The net picked in the list.  Starts undecorated: the
        decoration of a net is a second's work on fau, and browsing
        the list with it ticked would pay that on every click."""
        self._catalog = catalog
        self._parent = topology
        self._decorated = None
        self._spec = []
        self._topology = None
        self._clear_rows()
        self.suggestions.clear()
        self.decorate.blockSignals(True)
        self.decorate.setChecked(False)
        self.decorate.blockSignals(False)
        four = (topology is not None
                and set(topology.coordinations) == {4})
        self.decorate.setEnabled(four)
        self._say()

    def set_blocks(self, topology, chosen: dict) -> None:
        """The net being built on and its node rows (``{slot key:
        name}``), so that *Suggest fillers* knows the trimer and the
        face."""
        self._topology = topology
        self._chosen = {k: v for k, v in chosen.items() if v}
        live = self._decorated is not None and installed()
        self.suggest.setEnabled(live and bool(self._pair()))
        if self._decorated is not None and not installed():
            self.suggest.setToolTip("Needs PORMAKE's 'ase' extra")
        self._say_sizes()

    def _say_sizes(self) -> None:
        """Each window's rough size on the trimer and face chosen:
        how far its trimers sit from its middle and what a filler
        must span, on the blocks' instant scale.  Instant, so it
        follows every pick; 5-9 % out, so it says it is rough and
        *Suggest fillers* gives the measured one."""
        sizes = {}
        pair = self._pair() if self._decorated is not None else ()
        if pair and self._catalog is not None:
            every = {size: int(combo.currentData() or 1)
                     for size, (_tick, combo) in self._rows.items()}
            try:
                sizes = decorate.rough(self._decorated, self._catalog,
                                       *pair, every)
            except Exception:                       # noqa: BLE001
                # A face or trimer this cannot measure: no size, and
                # the build says why.
                sizes = {}
        for size, (note, said) in self._notes.items():
            if size not in sizes:
                note.setText(said)
                continue
            radius, wanted = sizes[size]
            text = f"{said}; trimers ~{radius:.0f} A from its middle"
            if wanted is not None:
                text += (f", so a {wanted.topicity}-topic filler of "
                         f"~{wanted.value:.1f} A {wanted.measure}")
            note.setText(text + " (rough)")

    # -- what it hands back --------------------------------------------

    def name(self) -> str:
        """The decorated net to build on, or ``""``."""
        if self._decorated is None or self._parent is None:
            return ""
        return decorate.spelled(self._parent.name, self._spec)

    def roles(self) -> dict[int, str]:
        """Node slot -> trimer, face or the window it fills, for the
        net being built on."""
        if self._topology is None:
            return {}
        return decorate.roles(self._topology)

    def same_blocks(self) -> bool:
        return self.same.isChecked() and self._decorated is not None

    def set_value(self, name: str) -> bool:
        """A decorated net picked last time, on the parent already
        picked: ticked, its windows filled again."""
        spelled = decorate.parse(str(name or ""))
        if (spelled is None or self._parent is None
                or spelled[0] != self._parent.name
                or not self.decorate.isEnabled()):
            return False
        self.decorate.setChecked(True)
        if self._decorated is None:
            return False
        self.settle()
        for size, every in spelled[1]:
            if size not in self._rows:
                continue
            tick, combo = self._rows[size]
            for widget in (tick, combo):
                widget.blockSignals(True)
            tick.setChecked(True)
            at = combo.findData(every)
            if at >= 0:
                combo.setCurrentIndex(at)
            for widget in (tick, combo):
                widget.blockSignals(False)
        self._apply()
        return self.name() == name

    # -- inside ----------------------------------------------------------

    def _say(self, warning: str = "") -> None:
        if warning:
            self.status.setText(warning)
            set_tone(self.status, WARNING)
            return
        set_tone(self.status, HINT)
        if self._parent is None:
            self.status.clear()
        elif not self.decorate.isEnabled():
            links = ", ".join(f"<a href='{n}'>{n}</a>" for n in OFFERED)
            self.status.setText(
                f"Supertetrahedra stand on a 4-connected net: a "
                f"zeolite -- {links}, or any of the 63 by IZA code.")
        elif self._decorated is None:
            self.status.setText(
                f"Tick to build {self._parent.name} of supertetrahedra "
                f"({self._parent.name}{decorate.SUFFIX}).")
        else:
            d = self._decorated
            filled = (f", {len(self._spec)} kind(s) of window filled"
                      if self._spec else "")
            made = decorate.made_from(self._catalog.topology(
                self.name()))
            lowered = ""
            if isinstance(made, decorate.Filled) and made.lowered:
                lowered = (f"  Written in {made.group}, where the sites "
                           f"a filler takes stay apart from those it "
                           f"leaves; in {d.group} it would take all.")
            self.status.setText(
                f"Built on <b>{self.name()}</b>: "
                f"{len(d.trimers)} trimers and {len(d.faces)} faces "
                f"a cell{filled}.{lowered}  Pick a 6-connected M3O "
                f"trimer and a tritopic face above.")

    def _on_decorate(self, checked: bool) -> None:
        self._clear_rows()
        self.suggestions.clear()
        self._spec = []
        self._decorated = None
        if checked:
            try:
                with busy():
                    made = self._catalog.topology(
                        self._parent.name + decorate.SUFFIX)
                    self._decorated = decorate.made_from(made)
                    offered = decorate.offered(self._decorated)
            except (CatalogError, decorate.DecorationError) as exc:
                self.decorate.blockSignals(True)
                self.decorate.setChecked(False)
                self.decorate.blockSignals(False)
                self._say(f"{self._parent.name} cannot be built of "
                          f"supertetrahedra: {exc}.")
                return
            self._fill_rows(offered)
        self._say()
        self.net_changed.emit(self.name())

    def settle(self) -> None:
        """Try every fill not yet tried, now: for a caller about to
        read the rows (a restore, a test)."""
        self._trying.stop()
        while self._untried:
            self._try_one()

    def _try_next(self) -> None:
        if self._untried:
            self._try_one()
        if self._untried:
            self._trying.start()

    def _try_one(self) -> None:
        size, every = self._untried.pop(0)
        if self._decorated is None or size not in self._rows:
            return
        why = decorate.choice(self._decorated, size, every)
        tick, combo = self._rows[size]
        at = combo.findData(every)
        if why and at >= 0:
            combo.setItemData(at, why, Qt.ToolTipRole)
            model = combo.model()
            if isinstance(model, QStandardItemModel):
                model.item(at).setEnabled(False)
        if any(s == size for s, _ in self._untried):
            return
        # The row's last one: point it at a fill that can be made.
        allowed = [combo.itemData(i) for i in range(combo.count())
                   if not combo.itemData(i, Qt.ToolTipRole)]
        if not allowed:
            tick.setEnabled(False)
            combo.setEnabled(False)
            tick.setToolTip(str(combo.itemData(0, Qt.ToolTipRole)))
        elif (combo.currentData() not in allowed
              and not tick.isChecked()):
            combo.blockSignals(True)
            combo.setCurrentIndex(combo.findData(allowed[0]))
            combo.blockSignals(False)

    def _clear_rows(self) -> None:
        self._trying.stop()
        self._untried = []
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # Hidden, never unparented, as the dialog's slot rows
                # are (MofBuildDialog._rebuild_slots says why).
                widget.hide()
                widget.deleteLater()
        self._rows = {}
        self._notes = {}

    def _fill_rows(self, offered: dict) -> None:
        """A row per window size, every fill listed; each is tried
        afterwards (:meth:`_try_next`) and greyed if refused."""
        kinds = decorate.windows(self._decorated)
        for line, (size, everies) in enumerate(offered.items()):
            same = [k for k in kinds if k.size == size]
            tick = QCheckBox(f"Fill the {size}-rings", self.windows)
            combo = QComboBox(self.windows)
            for every in everies:
                combo.addItem("every site" if every == 1 else
                              f"every {_ordinal(every)} site "
                              f"({size // every} taken)", every)
                self._untried.append((size, every))
            count = sum(k.count for k in same)
            facing = min(k.inward for k in same)
            said = (f"{count} a cell"
                    + (f", {len(same)} kinds" if len(same) > 1 else "")
                    + ("" if facing == size else
                       f", {facing} of {size} sites face in"))
            note = QLabel(said, self.windows)
            note.setWordWrap(True)
            set_tone(note, HINT)
            self._notes[size] = (note, said)
            tick.toggled.connect(self._apply)
            combo.currentIndexChanged.connect(self._on_every)
            self.grid.addWidget(tick, line, 0)
            self.grid.addWidget(combo, line, 1)
            self.grid.addWidget(note, line, 2)
            self._rows[size] = (tick, combo)
        self.grid.setColumnStretch(2, 1)
        self._say_sizes()
        if self._untried:
            self._trying.start()

    def _wanted(self) -> list[tuple[int, int]]:
        return [(size, int(combo.currentData()))
                for size, (tick, combo) in self._rows.items()
                if tick.isChecked()]

    def _on_every(self, *_args) -> None:
        self._say_sizes()
        if self._wanted() != self._spec:
            self._apply()

    def _apply(self, *_args, keep: bool = False) -> None:
        """Make the net the ticks spell, or put the ticks back.
        ``keep`` leaves the suggestions up: a click on one is what
        filled the window."""
        wanted = self._wanted()
        name = decorate.spelled(self._parent.name, wanted)
        try:
            with busy():
                self._catalog.topology(name)
        except CatalogError as exc:
            self._show_spec(self._spec)
            self._say(f"Not filled: {exc}.")
            return
        self._spec = wanted
        if not keep:
            self.suggestions.clear()
        self._say()
        self.net_changed.emit(self.name())

    def _show_spec(self, spec) -> None:
        held = dict(spec)
        for size, (tick, combo) in self._rows.items():
            for widget in (tick, combo):
                widget.blockSignals(True)
            tick.setChecked(size in held)
            if size in held:
                combo.setCurrentIndex(combo.findData(held[size]))
            for widget in (tick, combo):
                widget.blockSignals(False)

    def _pair(self) -> tuple[str, str] | tuple:
        """The trimer and face chosen above, or nothing."""
        roles = self.roles()
        trimer = next((self._chosen[k] for k, r in sorted(roles.items())
                       if r == "trimer" and k in self._chosen), "")
        face = next((self._chosen[k] for k, r in sorted(roles.items())
                     if r == "face" and k in self._chosen), "")
        return (trimer, face) if trimer and face else ()

    def _suggest(self) -> None:
        trimer, face = self._pair()
        every = {size: int(combo.currentData())
                 for size, (_tick, combo) in self._rows.items()}
        try:
            with busy():
                placed, rows = decorate.asked(
                    self._decorated, self._catalog, trimer, face, every)
        except Exception as exc:                    # noqa: BLE001
            # A face that is not tritopic, a trimer with no open site,
            # or a pass PORMAKE could not make: each says its reason.
            self.suggestions.setText(f"No trial on {trimer} and {face}: "
                                     f"{exc}.")
            set_tone(self.suggestions, WARNING)
            return
        set_tone(self.suggestions, HINT)
        a, b, c = (float(v) for v in
                   (placed.lattice ** 2).sum(axis=1) ** 0.5)
        tot = placed.tot(self._decorated)
        cell = (f"a {a:.1f} A" if max(a, b, c) - min(a, b, c) < 0.05
                else f"a {a:.1f}, b {b:.1f}, c {c:.1f} A")
        lines = [f"On {trimer} and {face}, unfilled: {cell}, T-O-T "
                 f"{tot.min():.0f}-{tot.max():.0f} degrees."]
        marked = []
        for row in rows:
            found = linkers.suggest(row.requirement, self._catalog,
                                    n=SUGGESTIONS, invent=True)
            marked.extend(found)
            if not found:
                lines.append(f"{row.sentence}.  Nothing in the "
                             f"catalogue or the series.")
                continue
            items = ", ".join(
                f"<a href='{row.kind.size}:{row.every}:{row.index}:"
                f"{s.candidate.name}'>{s.candidate.name}</a>"
                f"{linkers.mark(s)} ({s.miss:+.2f})" for s in found)
            lines.append(f"{row.sentence}.  Closest: {items}.")
        said = linkers.legend(marked)
        lines.append(f"Click one to fill its window"
                     f"{'; ' + said if said else ''}.")
        self.suggestions.setText("<br>".join(lines))

    def _clicked(self, href: str) -> None:
        """Fill the window, then put the filler in its row."""
        size, every, index, name = href.split(":", 3)
        size, every, index = int(size), int(every), int(index)
        if (size, every) not in self._spec:
            tick, combo = self._rows[size]
            for widget in (tick, combo):
                widget.blockSignals(True)
            tick.setChecked(True)
            combo.setCurrentIndex(combo.findData(every))
            for widget in (tick, combo):
                widget.blockSignals(False)
            self._apply(keep=True)
            if (size, every) not in self._spec:
                return
        label = f"{size}-ring"
        slots = [k for k, r in sorted(self.roles().items())
                 if r == label]
        if index < len(slots):
            self.use_block.emit(slots[index], name)


def _ordinal(n: int) -> str:
    return {2: "2nd", 3: "3rd"}.get(n, f"{n}th")
