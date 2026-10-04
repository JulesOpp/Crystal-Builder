"""
xtal.build.sketch
=================
A molecule as it is drawn: atoms at points on a page, bonds between
them, and nothing worked out yet.

The sketcher's canvas (:mod:`xtalapp.widgets.sketcher`) draws one of
these and every gesture is an edit of it, so what a drawing *is* can be
tested with no display.  It holds no RDKit: turning it into a string or
a molecule is :mod:`xtal.build.chem`'s, the one file that imports it.

Three things are written down rather than worked out:

**Hydrogens are counted, not drawn, unless somebody draws them.**  An
atom's ``hydrogens`` is ``None`` for "whatever its valence leaves",
which is RDKit's to say, or a number somebody set with H+/H-.  A metal
is never given hydrogens it was not given.

**A bond to a metal is an ordinary bond unless it is drawn dative.**
RDKit then turns one into a dative bond only where the donor would
otherwise be over-full -- pyridine's nitrogen -- so ``N`` on platinum is
an amido NH2 and an ammine is a dative bond or an H count of three.
Guessing which ligands are neutral would be wrong for half of them;
saying what was drawn is wrong for none.

**A metal's shape is the drawing's only 3D opinion.**  ``shape`` is
empty for "work it out from the coordination number"
(:func:`xtal.build.coordination.default_shape`) or one of
:data:`xtal.build.coordination.SHAPES`, chosen by right-clicking the
metal.  It rides in the CXSMILES as an atom property, so a plain SMILES
is still a drawing and every saved string still reads.

A connection point is the element ``X`` -- ``*`` in a SMILES string --
and ``map_number`` is its ``[*:n]``: a polymer's head (1) and tail (2),
or the order a MOF slot is filled in.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from xtal.core import elements as el

#: What a bond can be drawn as, in the order the tools offer them.
ORDERS = ("single", "double", "triple", "aromatic", "dative")

#: What a connection point is called on the page and in a structure.
CONNECTION = "X"

#: A bond's length on the page.  The canvas scales; nothing else
#: needs a unit.
BOND = 1.0


@dataclass
class SketchAtom:
    element: str = "C"
    x: float = 0.0
    y: float = 0.0
    charge: int = 0
    hydrogens: int | None = None        # None: what the valence leaves
    map_number: int = 0
    shape: str = ""                     # a metal's geometry; "" = auto


@dataclass
class SketchBond:
    a: int
    b: int
    order: str = "single"

    def other(self, atom: int) -> int:
        return self.b if atom == self.a else self.a


@dataclass
class Sketch:
    """Atoms and bonds by index.  Deleting renumbers; the canvas keeps
    no index across an edit, which is what keeps undo a copy."""

    atoms: list = field(default_factory=list)
    bonds: list = field(default_factory=list)

    # -- reading -------------------------------------------------------

    def copy(self) -> Sketch:
        return Sketch([replace(a) for a in self.atoms],
                      [replace(b) for b in self.bonds])

    def __len__(self) -> int:
        return len(self.atoms)

    def bond_between(self, a: int, b: int) -> int | None:
        for k, bond in enumerate(self.bonds):
            if {bond.a, bond.b} == {a, b}:
                return k
        return None

    def neighbours(self, atom: int) -> list[int]:
        return [bond.other(atom) for bond in self.bonds
                if atom in (bond.a, bond.b)]

    def bonds_of(self, atom: int) -> list[int]:
        return [k for k, bond in enumerate(self.bonds)
                if atom in (bond.a, bond.b)]

    def is_metal(self, atom: int) -> bool:
        return is_metal(self.atoms[atom].element)

    def connection_points(self) -> list[int]:
        return [k for k, atom in enumerate(self.atoms)
                if atom.element == CONNECTION]

    def point(self, atom: int) -> tuple[float, float]:
        a = self.atoms[atom]
        return a.x, a.y

    # -- editing -------------------------------------------------------

    def add_atom(self, element: str = "C", x: float = 0.0,
                 y: float = 0.0) -> int:
        self.atoms.append(SketchAtom(symbol(element), float(x),
                                     float(y)))
        return len(self.atoms) - 1

    def connect(self, a: int, b: int, order: str = "single") -> int:
        """A bond from ``a`` to ``b``, or the one there already set to
        ``order``.  A dative bond points from ``a``, the donor."""
        if a == b:
            raise ValueError("an atom cannot be bonded to itself")
        _check_order(order)
        k = self.bond_between(a, b)
        if k is None:
            self.bonds.append(SketchBond(a, b, order))
            return len(self.bonds) - 1
        self.bonds[k] = SketchBond(a, b, order) if order == "dative" \
            else replace(self.bonds[k], order=order)
        return k

    def grow(self, atom: int, element: str = "C",
             order: str = "single") -> int:
        """A new atom bonded to ``atom``, a bond's length away in the
        widest gap its other bonds leave -- 120 degrees on from a
        chain, so a run of clicks draws the zigzag."""
        x, y = self.point(atom)
        angle = self.free_direction(atom)
        new = self.add_atom(element, x + BOND * math.cos(angle),
                            y + BOND * math.sin(angle))
        self.connect(atom, new, order)
        return new

    def free_direction(self, atom: int) -> float:
        """The angle, in radians, of the middle of the widest gap
        between ``atom``'s bonds."""
        x, y = self.point(atom)
        angles = sorted(math.atan2(self.atoms[n].y - y,
                                   self.atoms[n].x - x)
                        for n in self.neighbours(atom))
        if not angles:
            return math.radians(30.0)
        if len(angles) == 1:
            # Zigzag: turn the way the bond before this one did not.
            before = self.neighbours(atom)[0]
            further = [n for n in self.neighbours(before) if n != atom]
            turn = math.radians(120.0)
            if further:
                bx, by = self.point(before)
                fx, fy = self.point(further[0])
                cross = ((x - bx) * (fy - by) - (y - by) * (fx - bx))
                turn = turn if cross > 0 else -turn
            return angles[0] + turn
        gaps = [(angles[(k + 1) % len(angles)] - angles[k])
                % (2 * math.pi) or 2 * math.pi
                for k in range(len(angles))]
        k = max(range(len(gaps)), key=gaps.__getitem__)
        return angles[k] + gaps[k] / 2.0

    def set_element(self, atoms, element: str) -> None:
        """Every atom given to ``element`` in one edit.  A connection
        point carries no charge, no hydrogens and no shape."""
        element = symbol(element)
        for k in atoms:
            atom = self.atoms[k]
            atom.element = element
            atom.shape = atom.shape if is_metal(element) else ""
            if element == CONNECTION:
                atom.charge, atom.hydrogens = 0, None
            else:
                atom.map_number = 0

    def set_order(self, bonds, order: str) -> None:
        """Every bond given set to ``order`` in one edit -- Select All
        then Double makes every bond double."""
        _check_order(order)
        for k in bonds:
            self.bonds[k].order = order

    def set_charge(self, atoms, delta: int) -> None:
        for k in atoms:
            if self.atoms[k].element != CONNECTION:
                self.atoms[k].charge += int(delta)

    def set_hydrogens(self, atoms, count: int | None) -> None:
        for k in atoms:
            if self.atoms[k].element != CONNECTION:
                self.atoms[k].hydrogens = (None if count is None
                                           else max(0, int(count)))

    def set_shape(self, atoms, shape: str) -> None:
        for k in atoms:
            if self.is_metal(k):
                self.atoms[k].shape = shape

    def set_map_number(self, atom: int, number: int) -> None:
        """Name a connection point ``[*:number]``, taking the number
        off any other point that had it -- a monomer has one head."""
        for k in self.connection_points():
            if self.atoms[k].map_number == number:
                self.atoms[k].map_number = 0
        self.atoms[atom].map_number = int(number)

    def delete(self, atoms=(), bonds=()) -> None:
        """Atoms, the bonds to them and the bonds given, renumbering
        what is left."""
        gone = set(atoms)
        gone_bonds = set(bonds) | {k for k, b in enumerate(self.bonds)
                                   if b.a in gone or b.b in gone}
        new_index, kept = {}, []
        for k, atom in enumerate(self.atoms):
            if k not in gone:
                new_index[k] = len(kept)
                kept.append(atom)
        self.bonds = [SketchBond(new_index[b.a], new_index[b.b], b.order)
                      for k, b in enumerate(self.bonds)
                      if k not in gone_bonds]
        self.atoms = kept

    def add_ring(self, size: int, aromatic: bool = False, *,
                 bond: int | None = None, atom: int | None = None,
                 at=(0.0, 0.0)) -> list[int]:
        """A regular ``size``-ring fused onto a bond, on an atom, or
        free at a point; its atoms, in order round it.  On a lone atom
        the atom is one of its corners; on an atom with bonds the ring
        hangs off it by a new bond, which is what a phenyl on a
        nitrogen is drawn as.

        Fused or hung, the ring goes on the side away from what is
        there already, which is where a chemist draws it.
        """
        if size < 3:
            raise ValueError("a ring has at least three atoms")
        radius = BOND / (2.0 * math.sin(math.pi / size))
        step = 2.0 * math.pi / size
        if bond is not None:
            a, b = self.bonds[bond].a, self.bonds[bond].b
            ax, ay = self.point(a)
            bx, by = self.point(b)
            mx, my = (ax + bx) / 2, (ay + by) / 2
            # Left of a->b is the normal's side; the ring goes on the
            # side away from what is bonded there already.
            nx, ny = -(by - ay), bx - ax
            side = 1.0 if self._crowd_side(a, b, mx, my, nx, ny) <= 0 \
                else -1.0
            ring = [a, b]
            px, py, qx, qy = ax, ay, bx, by
            turn = side * step
            for _ in range(2, size):
                dx, dy = qx - px, qy - py
                ex = dx * math.cos(turn) - dy * math.sin(turn)
                ey = dx * math.sin(turn) + dy * math.cos(turn)
                px, py, qx, qy = qx, qy, qx + ex, qy + ey
                ring.append(self.add_atom("C", qx, qy))
        elif atom is not None:
            if self.neighbours(atom):
                # An atom with bonds gets the ring as a substituent --
                # a phenyl on a nitrogen -- through a bond of its own.
                atom = self.grow(atom, "C")
            x, y = self.point(atom)
            out = self.free_direction(atom)
            cx, cy = x + radius * math.cos(out), y + radius * math.sin(out)
            start = out + math.pi
            ring = [atom] + [self.add_atom(
                "C", cx + radius * math.cos(start + step * k),
                cy + radius * math.sin(start + step * k))
                for k in range(1, size)]
        else:
            cx, cy = at
            ring = [self.add_atom(
                "C", cx + radius * math.cos(math.pi / 2 + step * k),
                cy + radius * math.sin(math.pi / 2 + step * k))
                for k in range(size)]
        for k in range(size):
            i, j = ring[k], ring[(k + 1) % size]
            if self.bond_between(i, j) is None:
                self.connect(i, j, "single")
        if aromatic:
            # Drawn the way a chemist draws benzene: alternating, which
            # RDKit then perceives as aromatic.  A ring of odd size
            # keeps one single bond more.
            for k in range(0, size - 1, 2):
                self.bonds[self.bond_between(
                    ring[k], ring[k + 1])].order = "double"
        return ring

    def _crowd_side(self, a, b, mx, my, nx, ny) -> float:
        """Which side of bond a-b its other neighbours are on, along
        the normal: positive is the normal's side."""
        total = 0.0
        for end in (a, b):
            for n in self.neighbours(end):
                if n in (a, b):
                    continue
                x, y = self.point(n)
                total += (x - mx) * nx + (y - my) * ny
        return total


def _turn(p, q, r) -> float:
    return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])


def _check_order(order: str) -> None:
    if order not in ORDERS:
        raise ValueError(f"{order!r} is not a bond order: "
                         f"{', '.join(ORDERS)}")


def symbol(text: str) -> str:
    """An element's symbol as it is written, or ``X``; ``*`` is a
    connection point.  Raises ``ValueError`` for anything else,
    deuterium included -- a drawing names elements."""
    text = str(text).strip()
    if text in ("*", CONNECTION):
        return CONNECTION
    canonical = el.canonical_symbol(text)
    if canonical is None or canonical == "D":
        raise ValueError(f"{text!r} is not an element")
    return canonical


def is_element(text: str) -> bool:
    try:
        symbol(text)
    except ValueError:
        return False
    return True


def is_metal(element: str) -> bool:
    if element == CONNECTION:
        return False
    try:
        return bool(el.element(element).is_metal)
    except (KeyError, ValueError):
        return False
