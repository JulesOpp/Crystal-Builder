"""
xtalapp.dialogs.rod_build
=========================
Modules ▸ MOF builder ▸ Build a rod framework: a rod, the pattern the
rods stand on, and the linker between them.

The generated form asked for the linker by typing its name, and left
the rhombus angle as an empty box that meant "whatever fits best".
Here the linker is picked from a list -- the rod's own first, then
every two-ended block there is -- or drawn with the same sketcher a
MOF builder's slot row draws with.  The angle's empty box shows, in
grey, the angle a build would use: the placement is worked out on a
thread whenever the rod, the linker or the pattern changes, which is
0.5 to 3.6 s, and its cell is said under the form.

The rod and the linker are drawn beside their rows with the MOF
builder's own :class:`~xtalapp.dialogs.mof_preview.BlockPreview`, the
connection points as open rings; the rod as two repeats, so it reads
as the chain it is.

Everything handed back is the generated form's ``values``, so
:func:`xtal.modules.mof.build_rod_framework` never learns which
asked.  There is no interpenetration: rods joined on every side fill
the plane across them.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from xtal.mof import rod as rods
from xtal.mof.rodnet import PATTERNS
from xtalapp.dialogs.answered import answered
from xtalapp.dialogs.mof_preview import BlockPreview
from xtalapp.widgets.tone import HINT, WARNING, set_tone

#: Shown in the angle box while the placement is being worked out.
FITTING = "fitting..."

#: The patterns, as a person reads them.
PATTERN_LABELS = {"sql": "sql -- square or rhombic",
                  "hcb": "hcb -- honeycomb",
                  "hxl": "hxl -- triangular",
                  "kgm": "kgm -- kagome"}

#: The hands, as a person reads them.
HAND_LABELS = (("auto", "As in the crystal"), ("same", "All one hand"),
               ("alternating", "Alternating"))


#: How large a block's picture is, as a MOF builder slot row's; a rod's
#: is wider, being two repeats of a chain.
PREVIEW = (190, 140)
ROD_PREVIEW = (300, 140)

#: How many repeats of a rod are drawn: two, so a bond to the next
#: repeat is drawn as a bond and not left hanging.
REPEATS = 2


@dataclass
class _Drawn:
    """What :class:`BlockPreview` draws: a rod or a linker, as a
    catalogue block would give it."""

    name: str
    symbols: list
    positions: np.ndarray
    connections: tuple
    pairs: list
    #: How many copies of the block are drawn: a rod's formula is one
    #: repeat's.
    copies: int = 1

    @property
    def formula(self) -> str:
        counts = Counter(s for s in self.symbols[:len(self.symbols)
                                                 // self.copies]
                         if s != "X")
        return "".join(f"{s}{n if n > 1 else ''}"
                       for s, n in sorted(counts.items()))

    def bond_pairs(self) -> list:
        return self.pairs


def drawn_rod(rod, name: str = "") -> _Drawn:
    """``rod`` as :data:`REPEATS` repeats up its axis, bonded across
    the cut where both ends are drawn."""
    n = len(rod.symbols)
    symbols, positions = [], []
    for k in range(REPEATS):
        symbols += list(rod.symbols)
        positions.append(rod.positions + [0.0, 0.0, k * rod.repeat])
    pairs = []
    for i, j, _letter, shift in rod.bonds:
        for k in range(REPEATS):
            if 0 <= k + shift < REPEATS:
                pairs.append((k * n + i, (k + shift) * n + j))
    connections = tuple(k * n + x for k in range(REPEATS)
                        for x in rod.connections)
    return _Drawn(name or rod.name, symbols, np.vstack(positions),
                  connections, pairs, REPEATS)


def drawn_linker(block, name: str) -> _Drawn:
    """A linker as :func:`xtal.mof.rodbuild.load_linker` reads it."""
    return _Drawn(name, list(block.symbols),
                  np.asarray(block.positions, float),
                  tuple(block.connections),
                  [(min(i, j), max(i, j)) for i, j, *_ in block.bonds])


class _Fit(QObject):
    """One placement, off the GUI thread: what an empty angle box
    means, and the cell a build would have."""

    finished = Signal(object)
    failed = Signal(object)

    def __init__(self, key, folders):
        super().__init__()
        self.key = key
        self.folders = folders

    def run(self) -> None:
        try:
            self.finished.emit((self.key, fit(self.key, self.folders)))
        except Exception as exc:                    # noqa: BLE001
            self.failed.emit((self.key, str(exc)))


def fit(key, folders=()):
    """The placement for ``(rod, linker, pattern, hands)`` with the
    angle left free -- what a build of those would do."""
    from xtal.mof.rodbuild import RodRequest, load_linker, load_rod
    from xtal.mof.rodnet import placement, rod_net

    name, linker, pattern, hands = key
    request = RodRequest(name, pattern, linker, hands).resolved(folders)
    rod = load_rod(request.rod, folders)
    net = rod_net(pattern, rod, hands)
    return placement(net, rod, load_linker(request.linker_name, folders))


class RodBuildDialog(QDialog):
    """A rod, a pattern, a linker and the hands; the angle as a build
    would take it, shown before it is built."""

    def __init__(self, module, action, parent=None, initial=None):
        super().__init__(parent)
        self.module = module
        self.action = action
        self.setWindowTitle(f"{module.label}: {action.label.rstrip('.')}")
        workspace = getattr(parent, "workspace", None)
        self.blocks = getattr(workspace, "blocks", None)
        self.folders = (self.blocks,) if self.blocks else ()
        #: Placements worked out, by ``(rod, linker, pattern, hands)``.
        self._fits: dict = {}
        #: Placements being worked out, so one asked twice runs once.
        self._running: set = set()
        self._asked = None
        given = dict(action.coerce(initial or {}))

        self.rod = QComboBox(self)
        rod_param = next(p for p in action.params if p.name == "rod")
        for value, text in rod_param.values_and_labels():
            self.rod.addItem(text, value)
        self.rod.setToolTip(rod_param.help)
        self.pattern = QComboBox(self)
        for name in PATTERNS:
            self.pattern.addItem(PATTERN_LABELS.get(name, name), name)
        self.pattern.setToolTip(
            "Where the rods cross a plane across them.  MIL-53 and "
            "MOF-303 sit on sql, MOF-74 and Ni2Cl2BTDD on hcb.")

        self.linker_search = QLineEdit(self)
        self.linker_search.setPlaceholderText(
            "Search linkers by name or composition -- E14, 8C")
        self.linker = QComboBox(self)
        self.linker.setToolTip(
            "What joins one rod to the next.  The rod's own is the one "
            "cut from its crystal beside it, which meets it at the "
            "crystal's lengths; any two-ended block will do.")
        self.draw = QPushButton("Draw...", self)
        self.draw.setToolTip("Draw a two-ended linker; it is saved in "
                             "this workspace's blocks and chosen here")
        self.draw.clicked.connect(self._draw)
        self.rod_preview = BlockPreview(self, minimum=ROD_PREVIEW)
        self.rod_preview.setFixedSize(*ROD_PREVIEW)
        self.rod_preview.empty_text = "no rod"
        self.linker_preview = BlockPreview(self, minimum=PREVIEW)
        self.linker_preview.setFixedSize(*PREVIEW)
        self.linker_preview.empty_text = "no linker"

        rod_row = _beside(self, [self.rod], self.rod_preview)
        choice = QWidget(self)
        row = QHBoxLayout(choice)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.linker, 1)
        row.addWidget(self.draw)
        linker_row = _beside(self, [self.linker_search, choice],
                             self.linker_preview)

        self.hands = QComboBox(self)
        for value, text in HAND_LABELS:
            self.hands.addItem(text, value)
        self.angle = QLineEdit(self)
        self.angle.setToolTip(
            "sql's angle, in degrees -- the coordinate MIL-53 breathes "
            "along.  Left empty, the angle the rods' points of "
            "extension fit best, shown here in grey.")
        self.repeat = QLineEdit(self)
        self.repeat.setPlaceholderText("1x1x1")
        self.repeat.setToolTip("How many cells, '1x1x2' for two along "
                               "the rods")

        self.summary = QLabel(self)
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.RichText)

        form = QFormLayout()
        form.addRow("Rod", rod_row)
        form.addRow("Rod pattern", self.pattern)
        form.addRow("Linker", linker_row)
        form.addRow("Hands", self.hands)
        form.addRow("Rhombus angle", self.angle)
        form.addRow("Repeat", self.repeat)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                   | QDialogButtonBox.Cancel)
        self.build_button = buttons.button(QDialogButtonBox.Ok)
        self.build_button.setText("Build")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.summary)
        layout.addWidget(buttons)
        self.resize(760, 560)

        self._restore(given)
        self.rod.currentIndexChanged.connect(self._rod_changed)
        self.linker_search.textChanged.connect(self._fill_linkers)
        for box in (self.pattern, self.linker, self.hands):
            box.currentIndexChanged.connect(self._changed)
        self._rod_changed()

    # -- the lists -------------------------------------------------------

    def rod_name(self) -> str:
        return str(self.rod.currentData() or "")

    def linker_name(self) -> str:
        return str(self.linker.currentData() or "")

    def _own_linker(self) -> str:
        from xtal.mof.rodbuild import RodBuildError, RodRequest

        try:
            return RodRequest(self.rod_name(), "sql").resolved(
                self.folders).linker_name
        except (RodBuildError, rods.RodError, OSError):
            return ""

    def _linkers(self) -> list[tuple[str, str]]:
        """``(value, label)`` for every linker there is: the rod's own,
        the rod library's, then every two-ended block."""
        from xtal.mof import Catalog
        from xtal.mof.catalog import matches_search

        query = self.linker_search.text().strip()
        own = self._own_linker()
        out = [("", f"The rod's own ({own})" if own
                else "The rod's own (none: pick one)")]
        for name in rods.shipped_linkers():
            if not query or query.lower() in name.lower():
                out.append((name, f"{name} (cut from its crystal)"))
        catalog = Catalog.default(also_blocks=self.folders)
        for block in catalog.building_blocks():
            if block.n_connections != 2:
                continue
            if query and not matches_search(block, query):
                continue
            mine = (self.blocks is not None
                    and block.path.parent == self.blocks)
            out.append((block.name, f"{block.name} (this workspace)"
                        if mine else block.name))
        return out

    def _fill_linkers(self, *_args, keep: str | None = None) -> None:
        keep = self.linker_name() if keep is None else keep
        self.linker.blockSignals(True)
        self.linker.clear()
        for value, text in self._linkers():
            self.linker.addItem(text, value)
        at = self.linker.findData(keep)
        self.linker.setCurrentIndex(max(at, 0))
        self.linker.blockSignals(False)
        self._changed()

    def _draw(self) -> None:
        from xtalapp.dialogs.draw_block import DrawBlockDialog

        if self.blocks is None:
            self.summary.setText("No workspace open, so a drawn linker "
                                 "has nowhere to go.")
            set_tone(self.summary, WARNING)
            return
        slot = SimpleNamespace(label="Linker", coordination=2)
        written = DrawBlockDialog.ask(slot, str(self.blocks), self)
        if written is not None:
            self.linker_search.blockSignals(True)
            self.linker_search.clear()
            self.linker_search.blockSignals(False)
            self._fill_linkers(keep=written.stem)

    # -- what follows from what ----------------------------------------

    def _rod_changed(self, *_args) -> None:
        from xtal.mof.rodbuild import load_rod

        try:
            rod = load_rod(self.rod_name(), self.folders)
            self.rod_preview.set_block(drawn_rod(
                rod, self.rod.currentText()))
        except Exception:                           # noqa: BLE001
            self.rod_preview.set_block(None)
        self._fill_linkers(keep=self.linker_name())

    def _show_linker(self) -> None:
        from xtal.mof.rodbuild import load_linker

        name = self.linker_name() or self._own_linker()
        try:
            block = load_linker(name, self.folders)
        except Exception:                           # noqa: BLE001
            self.linker_preview.set_block(None)
            return
        self.linker_preview.set_block(drawn_linker(block, name))

    def _changed(self, *_args) -> None:
        """Grey what does not apply, then ask for the placement."""
        self._show_linker()
        pattern = str(self.pattern.currentData())
        self.angle.setEnabled(pattern == "sql")
        if pattern != "sql":
            self.angle.clear()
        try:
            from xtal.mof.rodbuild import load_rod

            chiral = load_rod(self.rod_name(), self.folders).hand \
                is not None
        except Exception:                           # noqa: BLE001
            chiral = True
        self.hands.setEnabled(chiral)
        self.hands.setToolTip(
            "Which hand each helical rod is.  It decides the net: "
            "three-fold helices are etb when neighbours alternate and "
            "eta when all are one hand." if chiral else
            "This rod has no hand -- an improper operation maps it "
            "onto itself -- so there is none to choose.")
        alternating = self.hands.model().item(2)
        odd = pattern in ("hxl", "kgm")
        alternating.setEnabled(not odd)
        alternating.setToolTip(
            f"{pattern} has triangles, so neighbouring rods cannot "
            f"alternate" if odd else "")
        if odd and self.hands.currentData() == "alternating":
            self.hands.setCurrentIndex(0)
        self._ask_fit()

    def key(self):
        hands = str(self.hands.currentData()) if self.hands.isEnabled() \
            else "auto"
        return (self.rod_name(), self.linker_name(),
                str(self.pattern.currentData()), hands)

    def _ask_fit(self) -> None:
        key = self.key()
        self._asked = key
        if key in self._fits:
            self._show(key, self._fits[key])
            return
        self.angle.setPlaceholderText(FITTING
                                      if self.angle.isEnabled() else "")
        self.summary.setText("Working out where the rods go...")
        set_tone(self.summary, HINT)
        if key in self._running:
            return
        self._running.add(key)
        from xtalapp.workers import start_in_thread

        worker = _Fit(key, self.folders)
        worker.finished.connect(self._fitted)
        worker.failed.connect(self._fitted)
        start_in_thread(worker)

    def _fitted(self, answer) -> None:
        key, placed = answer
        self._running.discard(key)
        self._fits[key] = placed
        if key == self._asked:
            self._show(key, placed)

    def _show(self, key, placed) -> None:
        self.build_button.setEnabled(not isinstance(placed, str))
        if isinstance(placed, str):
            self.angle.setPlaceholderText("")
            self.summary.setText(f"This cannot be built: {placed}")
            set_tone(self.summary, WARNING)
            return
        if self.angle.isEnabled():
            self.angle.setPlaceholderText(f"{placed.gamma:.1f} -- best "
                                          f"fit")
        a, b, c, alpha, beta, gamma = placed.cell
        self.summary.setText(
            f"Predicted cell: a {a:.2f}, b {b:.2f}, c {c:.2f} A; "
            f"{alpha:.1f}, {beta:.1f}, {gamma:.1f} degrees.  Rods "
            f"{placed.spacing:.2f} A apart, worst joint "
            f"{placed.worst:.2f} A off.")
        set_tone(self.summary, HINT)

    # -- values ----------------------------------------------------------

    def _restore(self, given: dict) -> None:
        for box, name in ((self.rod, "rod"), (self.pattern, "pattern"),
                          (self.hands, "hands")):
            at = box.findData(given.get(name))
            if at >= 0:
                box.setCurrentIndex(at)
        self.angle.setText(str(given.get("angle") or ""))
        repeat = str(given.get("repeat") or "")
        self.repeat.setText("" if repeat == "1x1x1" else repeat)
        self._fill_linkers(keep=str(given.get("linker") or ""))

    def values(self) -> dict:
        return self.action.coerce({
            "rod": self.rod_name(),
            "pattern": str(self.pattern.currentData()),
            "linker": self.linker_name(),
            "hands": str(self.hands.currentData())
            if self.hands.isEnabled() else "auto",
            "angle": self.angle.text().strip()
            if self.angle.isEnabled() else "",
            "repeat": self.repeat.text().strip() or "1x1x1",
        })

    @classmethod
    def ask(cls, module, action, parent=None, initial=None):
        """The values to run with, or ``None`` if it was cancelled."""
        with answered(cls(module, action, parent, initial)) as dialog:
            if dialog.exec() != QDialog.Accepted:
                return None
            return dialog.values()


def _beside(parent, widgets, preview) -> QWidget:
    """``widgets`` stacked, with ``preview`` to their right: a MOF
    builder slot row's shape."""
    row = QWidget(parent)
    grid = QHBoxLayout(row)
    grid.setContentsMargins(0, 0, 0, 0)
    column = QVBoxLayout()
    column.setContentsMargins(0, 0, 0, 0)
    for widget in widgets:
        column.addWidget(widget)
    column.addStretch(1)
    grid.addLayout(column, 1)
    grid.addWidget(preview, 0, Qt.AlignTop)
    return row
