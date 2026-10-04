"""
xtalapp.widgets.sketcher.canvas
===============================
The page: a :class:`~xtal.build.sketch.Sketch` painted, and every click
and key turned into one edit of it.

**One gesture is one undo step.**  The canvas keeps its own history of
whole sketches -- a drawn molecule is a few dozen atoms, so a copy per
step costs nothing and undo can never be subtly wrong -- and pushes
one before each edit.  A second letter typed fast enough to make a
two-letter element (C then l is chlorine) *replaces* the step the
first letter made, so Ctrl+Z after "Cl" goes back to what was there
before the C, not to a carbon nobody meant.

**A selection is atoms and bonds**, and an edit chosen while there is
one applies to all of it: Ctrl+A then Double makes every bond double,
Ctrl+A then N makes every atom nitrogen.  With nothing selected a key
applies to what the pointer is over -- hover an atom and press O.

**Painted, not a scene graph.**  A drawing is small and redrawn whole;
hit-testing is a distance to a point or a segment, in model units, and
keeping it in this file is what keeps hover, keys and clicks agreeing
about what is under the pointer.
"""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import QMenu, QWidget

from xtal.build import chem, coordination
from xtal.build.sketch import (
    BOND,
    CONNECTION,
    TEMPLATES,
    Sketch,
    is_element,
    symbol,
)
from xtal.core import elements as el
from xtalapp.widgets import tone

#: How long a second letter may wait and still make a two-letter
#: element with the first (seconds).
TYPE_AHEAD = 0.7

#: Pixels per bond length before anything is fitted.
SCALE = 56.0

#: The one-letter symbols a key gives at once.
_ONE_LETTER = frozenset(s for s in el.all_symbols() if len(s) == 1)

_CYCLE = {"single": "double", "double": "triple", "triple": "single"}


class SketchCanvas(QWidget):
    """A molecule that is drawn on with the mouse and the keyboard."""

    #: Emitted after every edit, undo and redo -- not after a hover.
    edited = Signal()

    def __init__(self, parent=None, connection_points: bool = True,
                 head_tail: bool = False):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(160, 120)
        self.connection_points = connection_points
        self.head_tail = head_tail
        self.sketch = Sketch()
        self.selected_atoms: set[int] = set()
        self.selected_bonds: set[int] = set()
        self.hover: tuple[str, int] | None = None
        self.tool = "draw"
        self.element = "C"
        self.order = "single"
        self.ring: tuple[int, bool, str] = (6, True, "")
        self.scale = SCALE
        self.offset = QPointF(0.0, 0.0)
        # Refit on every resize until somebody draws: a drawing set
        # before the dialog is laid out was fitted to a page of 160
        # pixels, and stayed in its corner.
        self._auto_fit = True
        self._history: list[Sketch] = []
        self._future: list[Sketch] = []
        self._typed: tuple | None = None
        self._press: QPointF | None = None
        self._press_hit = None
        self._dragging = False
        self._moving: tuple | None = None
        self._marquee: QRectF | None = None
        self.hydrogens: dict[int, int] = {}
        self.problem = ""
        self.smiles = ""
        self._chemistry()

    # ==================================================================
    #  STATE
    # ==================================================================

    def set_sketch(self, sketch: Sketch, record: bool = True) -> None:
        """Replace the drawing, as one undo step, and fit it."""
        if record:
            self._remember()
        self.sketch = sketch
        self.selected_atoms.clear()
        self.selected_bonds.clear()
        self.hover = None
        self._auto_fit = True
        self.fit()
        self._changed()

    def _remember(self) -> None:
        self._history.append(self.sketch.copy())
        self._future.clear()
        del self._history[:-200]

    def edit(self, change) -> None:
        """Run ``change(sketch)`` as one undo step."""
        self._auto_fit = False
        self._remember()
        change(self.sketch)
        self._changed()

    def undo(self) -> bool:
        if not self._history:
            return False
        self._future.append(self.sketch)
        self.sketch = self._history.pop()
        self._clean_selection()
        self._changed()
        return True

    def redo(self) -> bool:
        if not self._future:
            return False
        self._history.append(self.sketch)
        self.sketch = self._future.pop()
        self._clean_selection()
        self._changed()
        return True

    def _clean_selection(self) -> None:
        self.selected_atoms = {k for k in self.selected_atoms
                               if k < len(self.sketch.atoms)}
        self.selected_bonds = {k for k in self.selected_bonds
                               if k < len(self.sketch.bonds)}
        self.hover = None

    def _changed(self) -> None:
        self._chemistry()
        self.update()
        self.edited.emit()

    def _chemistry(self) -> None:
        """The string, the hydrogens each atom is drawn with, and what
        is wrong with the drawing -- all from RDKit, once per edit."""
        self.hydrogens = {}
        self.problem = ""
        if not self.sketch.atoms:
            self.smiles = ""
            return
        try:
            mol = chem.sketch_mol(self.sketch)
            self.smiles = chem.sketch_smiles(self.sketch)
        except chem.BuildError as exc:
            self.problem = str(exc)
            return
        for atom in mol.GetAtoms():
            self.hydrogens[atom.GetIdx()] = atom.GetTotalNumHs()

    # ==================================================================
    #  SELECTION AND TOOLS
    # ==================================================================

    def select_all(self) -> None:
        self.selected_atoms = set(range(len(self.sketch.atoms)))
        self.selected_bonds = set(range(len(self.sketch.bonds)))
        self.update()

    def clear_selection(self) -> None:
        self.selected_atoms.clear()
        self.selected_bonds.clear()
        self.update()

    def choose(self, tool: str) -> None:
        """What a click does from now on; and, with something
        selected, done to all of it at once where that means anything
        -- which is how a bond type reaches every selected bond."""
        kind, _, arg = tool.partition(":")
        if kind == "element":
            self.tool, self.element = "draw", symbol(arg)
            if self.selected_atoms:
                self.set_element(self.selected_atoms, self.element)
            return
        if kind == "bond":
            self.tool, self.order = "bond", arg
            if self.selected_bonds:
                self.set_order(self.selected_bonds, arg)
            return
        if kind == "ring":
            self.tool, self.ring = "ring", (
                TEMPLATES[arg] if arg in TEMPLATES else
                (int(arg), False, ""))
            return
        if kind in ("charge", "hydrogen"):
            self.tool = tool
            if self.selected_atoms:
                self._step_atoms(kind, int(arg), self.selected_atoms)
            return
        self.tool = kind                    # select, erase

    def set_element(self, atoms, element: str) -> None:
        atoms = sorted(atoms)
        if element == CONNECTION and not self.connection_points:
            return
        if atoms:
            self.edit(lambda s: s.set_element(atoms, element))

    def set_order(self, bonds, order: str) -> None:
        bonds = sorted(bonds)
        if bonds:
            self.edit(lambda s: _set_orders(s, bonds, order))

    def _step_atoms(self, kind: str, delta: int, atoms) -> None:
        atoms = sorted(atoms)

        def change(s):
            for k in atoms:
                if kind == "charge":
                    s.set_charge([k], delta)
                else:
                    current = s.atoms[k].hydrogens
                    if current is None:
                        current = self.hydrogens.get(k, 0)
                    s.set_hydrogens([k], current + delta)
        self.edit(change)

    def delete_selection(self) -> bool:
        atoms, bonds = sorted(self.selected_atoms), \
            sorted(self.selected_bonds)
        if not atoms and not bonds and self.hover is not None:
            kind, k = self.hover
            atoms, bonds = ([k], []) if kind == "atom" else ([], [k])
        if not atoms and not bonds:
            return False
        self.selected_atoms.clear()
        self.selected_bonds.clear()
        self.hover = None
        self.edit(lambda s: s.delete(atoms, bonds))
        return True

    def clean(self) -> None:
        """Lay the drawing out again, as RDKit draws it."""
        if not self.smiles:
            return
        try:
            fresh = chem.sketch_from_smiles(self.smiles)
        except chem.BuildError:
            return
        self.set_sketch(fresh)

    # ==================================================================
    #  KEYS
    # ==================================================================

    def type_key(self, text: str) -> bool:
        """One typed character, aimed at what the pointer is over or,
        with nothing under it, at the selection.  Whether it did
        anything."""
        if not text:
            return False
        if text.isalpha():
            return self._letter(text)
        atoms = self._target_atoms()
        if text in "123":
            bonds = self._target_bonds()
            order = {"1": "single", "2": "double", "3": "triple"}[text]
            if bonds:
                self.set_order(bonds, order)
                return True
            return False
        if text in "+-" and atoms:
            self._step_atoms("charge", 1 if text == "+" else -1, atoms)
            return True
        if text == "*" and atoms and self.connection_points:
            self.set_element(atoms, CONNECTION)
            return True
        return False

    def _target_atoms(self) -> list[int]:
        if self.hover is not None and self.hover[0] == "atom":
            return [self.hover[1]]
        return sorted(self.selected_atoms)

    def _target_bonds(self) -> list[int]:
        if self.hover is not None and self.hover[0] == "bond":
            return [self.hover[1]]
        return sorted(self.selected_bonds)

    def _letter(self, letter: str) -> bool:
        """The type-ahead: the first letter is its one-letter element
        at once, and a second within :data:`TYPE_AHEAD` that makes a
        symbol with it replaces that, in the same undo step."""
        atoms = tuple(self._target_atoms())
        if not atoms:
            self._typed = None
            return False
        now = time.monotonic()
        pending = self._typed
        if pending is not None and pending[1] == atoms and \
                now - pending[2] <= TYPE_AHEAD:
            two = pending[0] + letter.lower()
            if is_element(two) and two != "D":
                if pending[3]:
                    # Undo the one-letter element, so the two-letter
                    # one is the same step and not a second.
                    self.sketch = self._history.pop()
                self._typed = None
                self.set_element(atoms, two)
                return True
        first = letter.upper()
        applies = (first in _ONE_LETTER
                   or (first == CONNECTION and self.connection_points))
        if applies:
            self.set_element(atoms, first)
        self._typed = (first, atoms, now, applies)
        return applies

    def keyPressEvent(self, event) -> None:
        key = event.key()
        modifiers = event.modifiers()
        command = modifiers & (Qt.ControlModifier | Qt.MetaModifier)
        if command and key == Qt.Key_A:
            self.select_all()
        elif command and key == Qt.Key_Z:
            if modifiers & Qt.ShiftModifier:
                self.redo()
            else:
                self.undo()
        elif command and key == Qt.Key_Y:
            self.redo()
        elif key in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selection()
        elif key == Qt.Key_Escape and (self.selected_atoms
                                       or self.selected_bonds):
            self.clear_selection()
        elif command or not self.type_key(event.text()):
            super().keyPressEvent(event)
            return
        event.accept()

    # ==================================================================
    #  GEOMETRY
    # ==================================================================

    def to_screen(self, x: float, y: float) -> QPointF:
        return QPointF(self.offset.x() + x * self.scale,
                       self.offset.y() - y * self.scale)

    def to_model(self, point: QPointF) -> tuple[float, float]:
        return ((point.x() - self.offset.x()) / self.scale,
                (self.offset.y() - point.y()) / self.scale)

    def fit(self) -> None:
        """The whole drawing in the middle of the page, no larger than
        a bond of :data:`SCALE` pixels."""
        width, height = max(self.width(), 1), max(self.height(), 1)
        if not self.sketch.atoms:
            self.scale = SCALE
            self.offset = QPointF(width / 2, height / 2)
            return
        xs = [a.x for a in self.sketch.atoms]
        ys = [a.y for a in self.sketch.atoms]
        span_x, span_y = max(xs) - min(xs) + 2, max(ys) - min(ys) + 2
        self.scale = min(SCALE, width / span_x, height / span_y)
        cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        self.offset = QPointF(width / 2 - cx * self.scale,
                              height / 2 + cy * self.scale)
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._auto_fit:
            self.fit()

    def hit(self, point: QPointF):
        """``("atom", k)``, ``("bond", k)`` or ``None`` under a point:
        an atom wins anywhere near its centre, a bond along its
        middle."""
        x, y = self.to_model(point)
        reach = max(0.28, 9.0 / self.scale)
        best, best_d = None, reach
        for k, atom in enumerate(self.sketch.atoms):
            d = math.hypot(atom.x - x, atom.y - y)
            if d < best_d:
                best, best_d = ("atom", k), d
        if best is not None:
            return best
        reach = max(0.15, 6.0 / self.scale)
        for k, bond in enumerate(self.sketch.bonds):
            ax, ay = self.sketch.point(bond.a)
            bx, by = self.sketch.point(bond.b)
            d = _segment_distance(x, y, ax, ay, bx, by)
            if d < reach and d < best_d:
                best, best_d = ("bond", k), d
        return best

    def hover_at(self, point: QPointF) -> None:
        found = self.hit(point)
        if found != self.hover:
            self.hover = found
            self.update()

    # ==================================================================
    #  MOUSE
    # ==================================================================

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        self.setFocus(Qt.MouseFocusReason)
        point = event.position()
        self._press, self._dragging = point, False
        self._press_hit = self.hit(point)
        shift = bool(event.modifiers() & Qt.ShiftModifier)
        if self.tool == "select":
            hit = self._press_hit
            if hit is None:
                if not shift:
                    self.clear_selection()
                self._marquee = QRectF(point, point)
            else:
                chosen = (self.selected_atoms if hit[0] == "atom"
                          else self.selected_bonds)
                if shift:
                    chosen ^= {hit[1]}
                elif hit[1] not in chosen:
                    self.clear_selection()
                    chosen.add(hit[1])
                self._moving = (self.sketch.copy(), point)
            self.update()

    def mouseMoveEvent(self, event) -> None:
        point = event.position()
        if self._press is None:
            self.hover_at(point)
            return
        if (point - self._press).manhattanLength() > 4:
            self._dragging = True
        if self.tool == "select":
            if self._marquee is not None:
                self._marquee = QRectF(self._press, point).normalized()
            elif self._moving is not None and self._dragging:
                self._move_selection(point)
            self.update()
        else:
            self.hover_at(point)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or self._press is None:
            super().mouseReleaseEvent(event)
            return
        point = event.position()
        start, hit = self._press, self._press_hit
        self._press = None
        if self.tool == "select":
            self._finish_select(point)
            return
        end = self.hit(point)
        if self._dragging:
            self._drag(start, hit, point, end)
        elif hit is None:
            self.click_empty(self.to_model(point))
        elif hit[0] == "atom":
            self.click_atom(hit[1])
        else:
            self.click_bond(hit[1])
        self.hover_at(point)

    def contextMenuEvent(self, event) -> None:
        hit = self.hit(QPointF(event.pos()))
        if hit is None or hit[0] != "atom":
            return
        menu = self.menu_for(hit[1])
        if menu is not None:
            from xtalapp import menus
            menus.popup(menu, event.globalPos())

    def menu_for(self, atom: int) -> QMenu | None:
        """The right-click menu of an atom: a metal's shape, or a
        connection point's head or tail.  ``None`` for anything else."""
        drawn = self.sketch.atoms[atom]
        if self.sketch.is_metal(atom):
            menu = QMenu(self)
            group = menu.addMenu("Geometry")
            group.setObjectName("geometry")
            n = len(self.sketch.neighbours(atom))
            auto = group.addAction("Automatic")
            auto.setCheckable(True)
            auto.setChecked(not drawn.shape)
            auto.triggered.connect(
                lambda: self.edit(lambda s: s.set_shape([atom], "")))
            for name in coordination.shapes_for(n):
                action = group.addAction(coordination.SHAPES[name][0])
                action.setCheckable(True)
                action.setChecked(drawn.shape == name)
                action.triggered.connect(
                    lambda _=False, name=name: self.edit(
                        lambda s: s.set_shape([atom], name)))
            if not coordination.shapes_for(n):
                none = group.addAction(f"No shape has {n} corners")
                none.setEnabled(False)
            return menu
        if drawn.element == CONNECTION and self.head_tail:
            menu = QMenu(self)
            for number, label in ((1, "Head [*:1]"), (2, "Tail [*:2]"),
                                  (0, "No number")):
                action = menu.addAction(label)
                action.setCheckable(True)
                action.setChecked(drawn.map_number == number)
                action.triggered.connect(
                    lambda _=False, number=number: self.edit(
                        lambda s: s.set_map_number(atom, number)))
            return menu
        return None

    def leaveEvent(self, event) -> None:
        self.hover = None
        self.update()
        super().leaveEvent(event)

    # -- what a click does ---------------------------------------------

    def click_empty(self, at) -> None:
        x, y = at
        if self.tool == "draw":
            if self.element == CONNECTION and not self.connection_points:
                return
            self.edit(lambda s: s.add_atom(self.element, x, y))
        elif self.tool == "bond":
            def change(s):
                k = s.add_atom("C", x, y)
                s.grow(k, "C", _plain(self.order))
            self.edit(change)
        elif self.tool == "ring":
            size, aromatic, hetero = self.ring
            self.edit(lambda s: s.add_ring(size, aromatic, at=(x, y),
                                           hetero=hetero))
        else:
            self.clear_selection()

    def click_atom(self, atom: int) -> None:
        tool = self.tool
        if tool == "draw":
            if self.element == CONNECTION and not self.connection_points:
                return
            if self.sketch.atoms[atom].element != self.element:
                self.set_element([atom], self.element)
            else:
                self.edit(lambda s: s.grow(atom, self.element))
        elif tool == "bond":
            self.edit(lambda s: _grow_bond(s, atom, self.order))
        elif tool == "ring":
            size, aromatic, hetero = self.ring
            self.edit(lambda s: s.add_ring(size, aromatic, atom=atom,
                                           hetero=hetero))
        elif tool == "erase":
            self.edit(lambda s: s.delete([atom]))
        elif tool.startswith(("charge:", "hydrogen:")):
            kind, _, delta = tool.partition(":")
            self._step_atoms(kind, int(delta), [atom])

    def click_bond(self, bond: int) -> None:
        tool = self.tool
        if tool == "bond":
            if bond in self.selected_bonds:
                self.set_order(self.selected_bonds, self.order)
            elif self.sketch.bonds[bond].order == self.order and \
                    self.order in _CYCLE:
                self.set_order([bond], _CYCLE[self.order])
            else:
                self.set_order([bond], self.order)
        elif tool == "draw":
            current = self.sketch.bonds[bond].order
            self.set_order([bond], _CYCLE.get(current, "single"))
        elif tool == "ring":
            size, aromatic, hetero = self.ring
            self.edit(lambda s: s.add_ring(size, aromatic, bond=bond,
                                           hetero=hetero))
        elif tool == "erase":
            self.edit(lambda s: s.delete(bonds=[bond]))

    def _drag(self, start, hit, point, end) -> None:
        """A drag draws a bond: from an atom to another, or out of an
        atom (or empty page) a bond's length towards the pointer."""
        element = self.element if self.tool == "draw" else "C"
        if element == CONNECTION and not self.connection_points:
            return
        order = _plain(self.order) if self.tool == "bond" else "single"
        x0, y0 = self.to_model(start)
        x1, y1 = self.to_model(point)
        angle = math.atan2(y1 - y0, x1 - x0)
        if hit is not None and hit[0] == "atom":
            a = hit[1]
            if end is not None and end[0] == "atom" and end[1] != a:
                b = end[1]
                self.edit(lambda s: s.connect(a, b, order))
                return
            ax, ay = self.sketch.point(a)
            self.edit(lambda s: s.connect(a, s.add_atom(
                element, ax + BOND * math.cos(angle),
                ay + BOND * math.sin(angle)), order))
        elif hit is None:
            def change(s):
                a = s.add_atom(element, x0, y0)
                s.connect(a, s.add_atom(
                    element, x0 + BOND * math.cos(angle),
                    y0 + BOND * math.sin(angle)), order)
            self.edit(change)

    def _move_selection(self, point) -> None:
        before, start = self._moving
        dx = (point.x() - start.x()) / self.scale
        dy = -(point.y() - start.y()) / self.scale
        moving = set(self.selected_atoms)
        for k in self.selected_bonds:
            moving |= {self.sketch.bonds[k].a, self.sketch.bonds[k].b}
        for k in moving:
            self.sketch.atoms[k].x = before.atoms[k].x + dx
            self.sketch.atoms[k].y = before.atoms[k].y + dy

    def _finish_select(self, point) -> None:
        if self._marquee is not None:
            box = self._marquee.normalized()
            inside = {k for k, a in enumerate(self.sketch.atoms)
                      if box.contains(self.to_screen(a.x, a.y))}
            self.selected_atoms |= inside
            self.selected_bonds |= {
                k for k, b in enumerate(self.sketch.bonds)
                if b.a in inside and b.b in inside}
            self._marquee = None
        elif self._moving is not None and self._dragging:
            before, _start = self._moving
            moved = self.sketch
            self.sketch = before
            self._remember()
            self.sketch = moved
            self._changed()
        self._moving = None
        self.update()

    # ==================================================================
    #  PAINTING
    # ==================================================================

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.color(QPalette.Base))
        ink = palette.color(QPalette.Text)
        highlight = QColor(palette.color(QPalette.Highlight))
        if not self.sketch.atoms:
            self._hint(painter, ink)
        font = QFont(self.font())
        font.setPixelSize(int(max(9, min(22, 0.42 * self.scale))))
        painter.setFont(font)
        labels = {k: self._label(k) for k in range(len(self.sketch.atoms))}
        self._paint_marks(painter, highlight)
        for bond in self.sketch.bonds:
            self._paint_bond(painter, bond, labels, ink)
        for k in range(len(self.sketch.atoms)):
            self._paint_atom(painter, k, labels[k], ink, palette)
        if self._marquee is not None:
            pen = QPen(highlight, 1, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self._marquee)
        if self.problem:
            painter.setPen(QColor(tone._AMBER[tone.is_dark(palette)]))
            small = QFont(self.font())
            painter.setFont(small)
            painter.drawText(self.rect().adjusted(6, 0, -6, -4),
                             Qt.AlignBottom | Qt.AlignLeft
                             | Qt.TextWordWrap, self.problem)
        painter.end()

    def _hint(self, painter, ink) -> None:
        faded = QColor(ink)
        faded.setAlphaF(0.45)
        painter.setPen(faded)
        painter.drawText(
            self.rect().adjusted(12, 12, -12, -12),
            Qt.AlignCenter | Qt.TextWordWrap,
            "Click to place an atom, drag to draw a bond.  Hover an "
            "atom and type a symbol to change it (C then l is Cl); "
            "Ctrl+A selects everything.")

    def _paint_marks(self, painter, highlight) -> None:
        """Selection and hover, under everything else."""
        halo = QColor(highlight)
        halo.setAlphaF(0.35)
        faint = QColor(highlight)
        faint.setAlphaF(0.18)
        painter.setPen(Qt.NoPen)
        radius = 0.3 * self.scale
        for k, bond in enumerate(self.sketch.bonds):
            chosen = k in self.selected_bonds
            hovered = self.hover == ("bond", k)
            if chosen or hovered:
                pen = QPen(halo if chosen else faint, 0.35 * self.scale,
                           Qt.SolidLine, Qt.RoundCap)
                painter.setPen(pen)
                painter.drawLine(self.to_screen(*self.sketch.point(bond.a)),
                                 self.to_screen(*self.sketch.point(bond.b)))
        painter.setPen(Qt.NoPen)
        for k, atom in enumerate(self.sketch.atoms):
            chosen = k in self.selected_atoms
            hovered = self.hover == ("atom", k)
            if chosen or hovered:
                painter.setBrush(halo if chosen else faint)
                painter.drawEllipse(self.to_screen(atom.x, atom.y),
                                    radius, radius)

    def _label(self, k: int) -> str:
        """What an atom is written as: nothing for a plain carbon, the
        symbol with its hydrogens, charge and number otherwise."""
        atom = self.sketch.atoms[k]
        if atom.element == CONNECTION:
            return "X" + (f":{atom.map_number}" if atom.map_number
                          else "")
        h = self.hydrogens.get(k, 0)
        plain_carbon = (atom.element == "C" and not atom.charge
                        and atom.hydrogens is None
                        and self.sketch.neighbours(k))
        if plain_carbon:
            return ""
        text = atom.element
        if h:
            text += "H" + (str(h) if h > 1 else "")
        if atom.charge:
            size = abs(atom.charge)
            text += (str(size) if size > 1 else "") + \
                ("+" if atom.charge > 0 else "−")
        return text

    def _label_radius(self, label: str) -> float:
        if not label:
            return 0.0
        metrics = QFontMetricsF(self.font())
        return max(0.3 * self.scale,
                   min(metrics.horizontalAdvance(label) * 0.5 + 3,
                       0.45 * self.scale))

    def _paint_bond(self, painter, bond, labels, ink) -> None:
        p = self.to_screen(*self.sketch.point(bond.a))
        q = self.to_screen(*self.sketch.point(bond.b))
        length = math.hypot(q.x() - p.x(), q.y() - p.y())
        if length < 1e-6:
            return
        ux, uy = (q.x() - p.x()) / length, (q.y() - p.y()) / length
        cut_a = self._label_radius(labels[bond.a]) * 0.8
        cut_b = self._label_radius(labels[bond.b]) * 0.8
        p = QPointF(p.x() + ux * cut_a, p.y() + uy * cut_a)
        q = QPointF(q.x() - ux * cut_b, q.y() - uy * cut_b)
        nx, ny = -uy, ux
        gap = 0.1 * self.scale
        pen = QPen(ink, max(1.2, self.scale / 28), Qt.SolidLine,
                   Qt.RoundCap)
        painter.setPen(pen)

        def line(offset, style=Qt.SolidLine):
            pen.setStyle(style)
            painter.setPen(pen)
            painter.drawLine(
                QPointF(p.x() + nx * offset, p.y() + ny * offset),
                QPointF(q.x() + nx * offset, q.y() + ny * offset))

        if bond.order == "double":
            line(gap / 2)
            line(-gap / 2)
        elif bond.order == "triple":
            line(0.0)
            line(gap)
            line(-gap)
        elif bond.order == "aromatic":
            line(-gap / 2)
            line(gap / 2, Qt.DashLine)
        elif bond.order == "dative":
            line(0.0)
            head = 0.18 * self.scale
            tip = q
            arrow = QPolygonF([
                tip,
                QPointF(tip.x() - ux * head + nx * head * 0.45,
                        tip.y() - uy * head + ny * head * 0.45),
                QPointF(tip.x() - ux * head - nx * head * 0.45,
                        tip.y() - uy * head - ny * head * 0.45)])
            painter.setBrush(ink)
            painter.drawPolygon(arrow)
            painter.setBrush(Qt.NoBrush)
        else:
            line(0.0)

    def _paint_atom(self, painter, k, label, ink, palette) -> None:
        if not label:
            return
        atom = self.sketch.atoms[k]
        centre = self.to_screen(atom.x, atom.y)
        colour = _ink_for(atom.element, ink, palette)
        metrics = QFontMetricsF(painter.font())
        width = metrics.horizontalAdvance(label)
        height = metrics.height()
        box = QRectF(centre.x() - width / 2 - 2, centre.y() - height / 2,
                     width + 4, height)
        path = QPainterPath()
        path.addRoundedRect(box, 3, 3)
        painter.fillPath(path, palette.color(QPalette.Base))
        painter.setPen(colour)
        painter.drawText(box, Qt.AlignCenter, label)


def _set_orders(sketch: Sketch, bonds, order: str) -> None:
    """A batch of bond orders; a dative bond is pointed at its metal,
    which is the end that receives."""
    sketch.set_order(bonds, order)
    if order != "dative":
        return
    for k in bonds:
        bond = sketch.bonds[k]
        if sketch.is_metal(bond.a) and not sketch.is_metal(bond.b):
            bond.a, bond.b = bond.b, bond.a


def _plain(order: str) -> str:
    """A bond drawn out of nothing with the dative tool has no metal
    to point at, so it starts single."""
    return "single" if order == "dative" else order


def _grow_bond(sketch: Sketch, atom: int, order: str) -> None:
    new = sketch.grow(atom, "C", _plain(order))
    if order == "dative":
        # From the new donor to the atom clicked, if that is a metal.
        k = sketch.bond_between(atom, new)
        _set_orders(sketch, [k], "dative")


def _segment_distance(x, y, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 < 1e-12:
        return math.hypot(x - ax, y - ay)
    t = max(0.15, min(0.85, ((x - ax) * dx + (y - ay) * dy) / length2))
    return math.hypot(x - (ax + t * dx), y - (ay + t * dy))


def _ink_for(element: str, ink, palette) -> QColor:
    """An element's colour, unless it would vanish on the page: carbon
    and hydrogen are written in the text colour, and any colour too
    near the background is darkened or lightened until it reads."""
    if element in ("C", "H", CONNECTION):
        return QColor(ink)
    colour = QColor(*el.color(element))
    light_page = palette.color(QPalette.Base).lightnessF() > 0.5
    # Luminance, not lightness: chlorine's green and sulfur's yellow
    # are "half light" and still vanish on white.
    for _ in range(4):
        y = _luminance(colour)
        if light_page and y > 0.4:
            colour = colour.darker(140)
        elif not light_page and y < 0.35:
            colour = colour.lighter(150)
        else:
            break
    return colour


def _luminance(colour: QColor) -> float:
    return (0.2126 * colour.redF() + 0.7152 * colour.greenF()
            + 0.0722 * colour.blueF())
