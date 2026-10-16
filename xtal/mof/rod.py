"""
xtal.mof.rod
============
A rod: a 1-periodic secondary building unit, as MOF-74, MIL-53,
MOF-303 and Ni2Cl2BTDD are built from.

**A rod is one block, not a chain of finite nodes.**  Cut into
PORMAKE nodes, a rod would put metals on the edges of its net -- MOF-74's
net, msf, has carboxylate carbons for vertices, not zinc -- and the
joints would cut M-O bonds through the shared oxygens.  So a rod is its
own block: the atoms of one repeat along *z*, the bonds within it and to
the next repeat up, and an ``X`` for each point a linker meets it.

**The points of extension are the net, and their shape is stated.**
A rod has no centre to stand for it.  Its net (Schoedel *et al.*, Chem.
Rev. 2016, 116, 12466) has a vertex for each point of extension (PoE) --
here one per donor group, a carboxylate, a phenolate, a triazolate --
and the PoEs of one rod joined into a shape along it.  Which pairs are
joined was chosen per rod in that review and no proximity rule recovers
all four (measured, E0): the relative-neighbourhood graph gives MIL-53's
sra and Ni2Cl2BTDD's etb but not MOF-74's msf, which leaves out the
phenolate-phenolate pairs at 4.01 A while joining every pair nearer.  So
the shape is decided once, when the rod is cut (:func:`from_structure`,
``shape=``), and written into the file as edges between ``X`` atoms --
stated as a block's bonds are, and never derived again.

**Where a rod is cut.**  The rod side keeps the metals, every atom
bonded to metals alone (a mu-OH, a mu-Cl, a water), and each donor group
whole: the donors a linker binds with, the atom a carboxylate's two
oxygens share, and an azolate's whole five-ring -- MFU-4l's shipped
nodes keep the triazole, fused carbons and all, and the BTDD linker
meets them through one ``X`` bonded to two carbons.  A point is
:data:`~xtal.mof.block.CONNECTION_DISTANCE` from the atoms it hangs
off, as every block's is.

**A hand is found, not given.**  :meth:`Rod.screw` finds the rod's own
screw by matching it onto itself; :attr:`Rod.hand` is ``None`` for a rod
an improper operation maps onto itself (MOF-303 has inversion centres on
its axis, MIL-53 is straight), which is why a hand per rod is a question
only for a chiral rod.

The file is an ``.xyz`` with the rod on its second line::

    54
    rod repeat=6.7960 axis=z
    Zn 1.2345 ...
    ...
    0 7 S 0         bond: i, j, order, how many repeats up j is
    edge 40 41 1    PoE shape: two X atoms and the repeats between them

Numpy and the structure layer only: no Qt, no PORMAKE.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

from xtal.core import elements as el
from xtal.mof.block import BOND_LETTERS, CONNECTION_DISTANCE

#: Within this of each other, A, two atoms are one atom when a rod is
#: matched onto itself or onto its mirror image.  A refinement's
#: symmetry is exact to its rounding; 0.2 A is still far below any
#: bond.
MATCH = 0.2

#: How many shells a PoE shape is looked for in, either way along the
#: rod.  Shapes reach two repeats at most in the four shipped rods.
_REACH = 3


class RodError(ValueError):
    """A structure or file that does not give a rod, said in a sentence."""


@dataclass
class Rod:
    """One repeat of a rod along *z*, its axis through the origin.

    ``bonds`` are ``(i, j, letter, shift)``: ``j`` is ``shift`` repeats
    up from where its position says.  ``edges`` are the PoE shape,
    ``(a, b, shift)`` between ``X`` atoms in the same sense.
    """

    symbols: list[str]
    positions: np.ndarray
    repeat: float
    bonds: list[tuple[int, int, str, int]]
    edges: list[tuple[int, int, int]] = field(default_factory=list)
    name: str = ""
    notes: tuple[str, ...] = ()

    # ------------------------------------------------------- reading

    @property
    def connections(self) -> list[int]:
        """The ``X`` atoms: one per point of extension."""
        return [i for i, s in enumerate(self.symbols) if s == "X"]

    @property
    def metals(self) -> list[int]:
        return [i for i, s in enumerate(self.symbols)
                if s != "X" and el.element(s).is_metal]

    def members(self, point: int) -> list[tuple[int, int]]:
        """The atoms ``point`` hangs off, each with its shift."""
        found = []
        for i, j, _letter, shift in self.bonds:
            if i == point:
                found.append((j, shift))
            elif j == point:
                found.append((i, -shift))
        return found

    def neighbours(self, atom: int) -> list[tuple[int, int]]:
        return self.members(atom)

    # ------------------------------------------------------ symmetry

    def screw(self) -> tuple[int, float]:
        """``(n, turn)``: the rod is its own image after a turn of
        ``turn`` degrees and a rise of ``repeat / n``, the shortest rise
        that maps it.  ``(1, 0.0)`` for a rod with no screw."""
        motions = _motions(self.symbols, self.positions, self.repeat,
                           self.positions)
        rises = [(t, phi) for phi, t in motions
                 if MATCH < t < self.repeat - MATCH]
        if not rises:
            return 1, 0.0
        t, phi = min(rises, key=lambda r: (round(r[0], 2), abs(r[1])))
        return int(round(self.repeat / t)), phi

    def is_chiral(self) -> bool:
        """Whether no rotation and rise maps the rod onto its mirror
        image -- that is, whether it has no mirror, inversion or
        improper axis of its own.

        Two mirror images are tried: through a plane holding the axis,
        which with a turn and a rise gives every vertical mirror and
        glide, and through a plane across it, which gives inversion
        (MOF-303's Al on its axis), a horizontal mirror and the
        rotoinversions -- the operations that turn the rod over."""
        across = self.positions * np.array([1.0, 1.0, -1.0])
        return not any(
            _motions(self.symbols, image, self.repeat, self.positions,
                     first=True)
            for image in (self.mirror().positions, across))

    @property
    def hand(self) -> str | None:
        """``"right"`` or ``"left"`` for a chiral rod, by its screw: a
        right-handed screw turns anticlockwise, seen from above, as it
        rises (3_1 is right-handed).  ``None`` for an achiral rod, and
        ``"chiral"`` for one whose screw is a half turn or none."""
        if not self.is_chiral():
            return None
        _n, turn = self.screw()
        if abs(turn) < 1.0 or abs(abs(turn) - 180.0) < 1.0:
            return "chiral"
        return "right" if turn > 0 else "left"

    def mirror(self) -> Rod:
        """The enantiomer: reflected through the plane *x* = 0, which
        holds the axis, so bonds, shifts and the shape are unchanged."""
        flipped = self.positions.copy()
        flipped[:, 0] *= -1
        return replace(self, positions=flipped)

    def turned_over(self) -> Rod:
        """The rod upside down: a half turn about *x*, across the axis.
        The same hand -- a proper rotation -- with every shift along the
        rod reversed, since what was up is down."""
        turned = self.positions * np.array([1.0, -1.0, -1.0])
        return replace(self, positions=turned,
                       bonds=[(i, j, letter, -k)
                              for i, j, letter, k in self.bonds],
                       edges=[(a, b, -k) for a, b, k in self.edges])

    def with_metal(self, symbol: str) -> Rod:
        """The same rod with every metal made ``symbol``, geometry as it
        was -- and a note saying so, since nothing has been relaxed."""
        was = sorted({self.symbols[i] for i in self.metals})
        symbols = [symbol if i in set(self.metals) else s
                   for i, s in enumerate(self.symbols)]
        note = (f"metal {'/'.join(was)} replaced by {symbol}; geometry "
                f"not relaxed")
        return replace(self, symbols=symbols,
                       notes=(*self.notes, note))

    # ----------------------------------------------------------- file

    def text(self) -> str:
        head = [f"rod repeat={self.repeat:.4f} axis=z"]
        if self.name:
            head.append(f"name={self.name}")
        lines = [str(len(self.symbols)), " ".join(head)]
        for s, (x, y, z) in zip(self.symbols, self.positions,
                                strict=True):
            lines.append(f"{s:<4s} {x:.4f} {y:.4f} {z:.4f}")
        for i, j, letter, shift in self.bonds:
            lines.append(f"{i:4d} {j:4d} {letter} {shift}")
        for a, b, shift in self.edges:
            lines.append(f"edge {a} {b} {shift}")
        for note in self.notes:
            lines.append(f"# {note}")
        return "\n".join(lines) + "\n"

    @classmethod
    def parse(cls, text: str) -> Rod:
        lines = text.splitlines()
        try:
            n = int(lines[0].split()[0])
        except (IndexError, ValueError) as exc:
            raise RodError("a rod file starts with its atom count") \
                from exc
        found = dict(re.findall(r"(\w+)=(\S+)", lines[1]))
        if not lines[1].startswith("rod") or "repeat" not in found:
            raise RodError("a rod file's second line is "
                           "'rod repeat=... axis=z'")
        symbols, positions = [], []
        for line in lines[2:2 + n]:
            parts = line.split()
            symbols.append(parts[0])
            positions.append([float(v) for v in parts[1:4]])
        bonds, edges, notes = [], [], []
        for line in lines[2 + n:]:
            if line.startswith("#"):
                notes.append(line[1:].strip())
                continue
            parts = line.split()
            if not parts:
                continue
            if parts[0] == "edge":
                edges.append((int(parts[1]), int(parts[2]),
                              int(parts[3])))
            else:
                bonds.append((int(parts[0]), int(parts[1]), parts[2],
                              int(parts[3]) if len(parts) > 3 else 0))
        return cls(symbols, np.array(positions, dtype=float),
                   float(found["repeat"]), bonds, edges,
                   found.get("name", ""), tuple(notes))

    @classmethod
    def read(cls, path) -> Rod:
        rod = cls.parse(Path(path).read_text(encoding="utf-8"))
        return rod if rod.name else replace(rod, name=Path(path).stem)

    def write(self, path) -> Path:
        from xtal.io.atomic import write_text

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_text(path, self.text())
        return path


# ================================================================ cutting


def from_structure(structure, seed: int, *, shape="rng", rules=None,
                   name: str = "") -> Rod:
    """Cut the rod holding atom ``seed`` (a metal, in the P1 cell's
    numbering) out of ``structure``.

    ``shape`` decides the PoE shape, once: ``"rng"`` the
    relative-neighbourhood graph of the PoEs, an ``int`` *n* the first
    *n* shells of PoE-PoE distance (rounded to 0.01 A), a ``float`` every
    pair within that many A.  The PoE's position for this is the middle
    of its donors.  ``rules`` are bond rules for perceiving the crystal
    when its own would miss a bond (MOF-74's fifth Zn-O at 2.17 A).
    """
    from xtal.core import bonding, p1

    cell = p1.expand(structure)
    graph = bonding.graph(structure, rules)
    orders = bonding.orders(structure, rules)
    symbols = cell.elements
    n = len(symbols)
    if not 0 <= seed < n or not el.element(symbols[seed]).is_metal:
        raise RodError(f"atom {seed} is not a metal, so no rod starts "
                       f"there")

    nbr = defaultdict(list)
    order_of = {}
    for b, order in zip(graph.bonds, orders, strict=True):
        image = np.array(b.image, int)
        nbr[b.i].append((b.j, image))
        nbr[b.j].append((b.i, -image))
        order_of[(b.i, b.j)] = order_of[(b.j, b.i)] = float(order)

    metal = [el.element(s).is_metal and not el.is_dummy(s)
             for s in symbols]
    heavy = [s not in ("H", "D", "X") for s in symbols]
    bridge = [heavy[i] and not metal[i] and bool(nbr[i])
              and all(metal[j] for j, _ in nbr[i] if heavy[j])
              for i in range(n)]
    linker = {i for i in range(n)
              if heavy[i] and not metal[i] and not bridge[i]}
    donor = {i for i in linker if any(metal[j] for j, _ in nbr[i])}

    groups = _donor_groups(donor, linker, nbr)
    group_of = {a: k for k, g in enumerate(groups) for a in g}

    def allowed(i, j):
        if metal[i] or metal[j]:
            return True
        if i in group_of and group_of.get(j) == group_of[i]:
            return True
        return (not heavy[i] and (bridge[j] or j in group_of)) or \
               (not heavy[j] and (bridge[i] or i in group_of))

    side = {i for i in range(n)
            if metal[i] or bridge[i] or i in group_of}
    side |= {i for i in range(n) if symbols[i] in ("H", "D")
             and any(j in side for j, _ in nbr[i])}
    offset, translations = _walk(seed, side, nbr, allowed)
    t = _primitive(translations)
    if t is None:
        raise RodError("the atoms round this metal do not repeat in "
                       "one direction only, so they are not a rod")

    to_cart = cell.lattice.to_cart
    tc = np.asarray(to_cart(np.array(t, float)), float)
    length = float(np.linalg.norm(tc))
    axis = tc / length
    where = {a: np.asarray(to_cart(cell.frac[a] + offset[a]), float)
             for a in offset}
    metals = [a for a in offset if metal[a]]
    centre = np.mean([where[a] for a in metals], axis=0)

    # One repeat: each atom taken up or down by whole repeats, a donor
    # group and a hydrogen with what they belong to, so that no group
    # straddles the cut.
    anchor = {}
    for a in offset:
        if a in group_of:
            anchor[a] = min(g for g in groups[group_of[a]] if g in offset)
        elif not heavy[a]:
            anchor[a] = next((j for j, _ in nbr[a] if j in offset), a)
        else:
            anchor[a] = a
    # The walk reaches a group's atoms through different metals, so
    # their offsets can be a repeat apart: put each group back together
    # from its anchor, and each hydrogen beside its parent.
    for a in sorted(offset):
        if a in group_of and anchor[a] == a:
            queue = deque([a])
            placed = {a}
            while queue:
                i = queue.popleft()
                for j, image in nbr[i]:
                    if (j in offset and j not in placed
                            and group_of.get(j) == group_of[a]):
                        offset[j] = offset[i] + image
                        placed.add(j)
                        queue.append(j)
    for a in offset:
        if not heavy[a]:
            for j, image in nbr[a]:
                if j == anchor[a]:
                    offset[a] = offset[j] - image
                    break
    where = {a: np.asarray(to_cart(cell.frac[a] + offset[a]), float)
             for a in offset}
    ups = {a: math.floor(float((where[anchor[a]] - centre) @ axis)
                         / length) for a in offset}
    for a, k in ups.items():
        offset[a] = offset[a] - k * np.array(t)
        where[a] = where[a] - k * tc

    first = next((where[a] - centre for a in sorted(metals)
                  if _off_axis(where[a] - centre, axis) > 0.1),
                 next(where[a] - centre for a in sorted(offset)
                      if _off_axis(where[a] - centre, axis) > 0.1))
    e1 = first - (first @ axis) * axis
    e1 /= np.linalg.norm(e1)
    frame = np.array([e1, np.cross(axis, e1), axis])

    atoms = sorted(offset)
    place = {a: k for k, a in enumerate(atoms)}
    positions = [frame @ (where[a] - centre) for a in atoms]
    out_symbols = [symbols[a] for a in atoms]

    def shift(i, j, image):
        gap = np.asarray(to_cart(np.array(offset[i] + image - offset[j],
                                          float)), float)
        return int(round(float(gap @ tc) / length ** 2))

    bonds = []
    cuts = defaultdict(list)
    for i in atoms:
        for j, image in nbr[i]:
            if j in offset and allowed(i, j):
                if place[i] < place[j]:
                    letter = BOND_LETTERS.get(order_of[(i, j)], "S")
                    bonds.append((place[i], place[j], letter,
                                  shift(i, j, image)))
            elif i in group_of and j in linker and heavy[j]:
                partner = np.asarray(to_cart(cell.frac[j] + offset[i]
                                             + image), float)
                cuts[group_of[i]].append((i, frame @ (partner - centre)))

    points = {}
    for k in sorted(cuts):
        hung = cuts[k]
        members = sorted({place[i] for i, _ in hung})
        middle = np.mean([positions[m] for m in members], axis=0)
        outward = np.mean([p for _, p in hung], axis=0) - middle
        outward /= np.linalg.norm(outward)
        x = len(out_symbols)
        out_symbols.append("X")
        positions.append(middle + CONNECTION_DISTANCE * outward)
        bonds.extend((m, x, "S", 0) for m in members)
        donors = [place[a] for a in groups[k] if a in donor]
        points[x] = np.mean([positions[d] for d in donors], axis=0)
    if not points:
        raise RodError("no linker meets this rod")

    positions = np.array(positions)
    edges = _shape(points, length, shape)
    rod = Rod(out_symbols, positions, length, sorted(bonds), edges,
              name, ())
    return rod


def _donor_groups(donor, linker, nbr) -> list[set[int]]:
    """The linker's donors in groups, each with what it brings to the
    rod side: donors within two bonds of each other (a carboxylate's
    two oxygens, an azolate's nitrogens), an atom bonded to two of them
    (the carboxylate carbon), and an azolate's whole five-ring."""
    parent = {d: d for d in donor}

    def root(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for d in donor:
        reach = {d: 0}
        queue = deque([d])
        while queue:
            a = queue.popleft()
            if reach[a] == 2:
                continue
            for j, _ in nbr[a]:
                if j in linker and j not in reach:
                    reach[j] = reach[a] + 1
                    queue.append(j)
                    if j in donor:
                        parent[root(j)] = root(d)
    groups = defaultdict(set)
    for d in donor:
        groups[root(d)].add(d)
    found = []
    for members in groups.values():
        whole = set(members)
        for a in linker - members:
            if sum(1 for j, _ in nbr[a] if j in members) >= 2:
                whole.add(a)
        if len(members) >= 2:
            whole |= _five_ring(members, linker, nbr)
        found.append(whole)
    return sorted(found, key=min)


def _five_ring(members, linker, nbr) -> set[int]:
    """The five-ring through two of ``members``, if there is one."""
    start = min(members)
    paths = [[(start, (0, 0, 0))]]
    for _ in range(5):
        grown = []
        for path in paths:
            a, at = path[-1]
            for j, image in nbr[a]:
                if j not in linker:
                    continue
                to = tuple(int(v) for v in np.add(at, image))
                if len(path) == 5:
                    if (j, to) == (start, (0, 0, 0)):
                        ring = {p for p, _ in path}
                        if len(ring & members) >= 2:
                            return ring
                elif (j, to) not in path:
                    grown.append([*path, (j, to)])
        paths = grown
    return set()


def _walk(seed, side, nbr, allowed):
    """Offsets of everything reachable from ``seed``, and the
    translations the walk closed onto."""
    offset = {seed: np.zeros(3, int)}
    translations = []
    queue = deque([seed])
    while queue:
        i = queue.popleft()
        for j, image in nbr[i]:
            if j not in side or not allowed(i, j):
                continue
            here = offset[i] + image
            if j in offset:
                gap = here - offset[j]
                if gap.any():
                    translations.append(gap)
            else:
                offset[j] = here
                queue.append(j)
    return offset, translations


def _primitive(translations):
    """The one lattice vector the translations are all multiples of, or
    ``None`` unless they span exactly one direction."""
    if not translations:
        return None
    rows = np.array(translations)
    if np.linalg.matrix_rank(rows) != 1:
        return None
    first = next(r for r in rows if r.any())
    step = first // np.gcd.reduce(np.abs(first[first != 0]))
    return tuple(int(v) for v in step)


def _off_axis(vector, axis) -> float:
    return float(np.linalg.norm(vector - (vector @ axis) * axis))


def _shape(points, length, shape) -> list[tuple[int, int, int]]:
    """The PoE shape, by ``shape`` (see :func:`from_structure`)."""
    xs = sorted(points)
    rise = np.array([0.0, 0.0, length])
    pairs = {}
    for a in xs:
        for b in xs:
            for k in range(-_REACH, _REACH + 1):
                if a == b and k == 0:
                    continue
                key = min((a, b, k), (b, a, -k))
                if key not in pairs:
                    gap = float(np.linalg.norm(points[b] + k * rise
                                               - points[a]))
                    pairs[key] = (gap, a, b, k)
    pairs = sorted(pairs.values())
    if shape == "rng":
        chosen = [p for p in pairs if _neighbourly(p, points, rise)]
    elif isinstance(shape, int):
        shells = sorted({round(p[0], 2) for p in pairs})
        if not 0 < shape <= len(shells):
            raise RodError(f"a shape of {shape} shells needs 1 to "
                           f"{len(shells)}")
        cut = shells[shape - 1]
        chosen = [p for p in pairs if round(p[0], 2) <= cut]
    else:
        chosen = [p for p in pairs if p[0] <= float(shape)]
    edges = set()
    for _gap, a, b, k in chosen:
        edges.add(min((a, b, k), (b, a, -k)))
    return sorted(edges)


def _neighbourly(pair, points, rise) -> bool:
    """Whether no third PoE is nearer both ends than they are to each
    other -- the relative-neighbourhood test."""
    gap, a, b, k = pair
    here, there = points[a], points[b] + k * rise
    for at in points.values():
        for m in range(-_REACH - 1, _REACH + 2):
            p = at + m * rise
            near = max(np.linalg.norm(p - here), np.linalg.norm(p - there))
            if near < gap - 1e-6:
                return False
    return True


def _motions(symbols, moving, repeat, target, first=False):
    """Every ``(turn, rise)`` -- degrees about *z*, A along it, the rise
    in ``[0, repeat)`` -- taking ``moving`` onto ``target`` atom for
    atom, element for element, the rod's period allowed for."""
    symbols = list(symbols)
    radius = np.linalg.norm(target[:, :2], axis=1)
    kinds = defaultdict(list)
    for i, s in enumerate(symbols):
        kinds[s].append(i)
    pivot = min((i for i in range(len(symbols)) if radius[i] > 0.3),
                key=lambda i: (len(kinds[symbols[i]]), i))
    found = []
    seen = set()
    p = moving[pivot]
    for q in kinds[symbols[pivot]]:
        r = target[q]
        if abs(np.linalg.norm(r[:2]) - np.linalg.norm(p[:2])) > MATCH:
            continue
        turn = math.degrees(math.atan2(r[1], r[0])
                            - math.atan2(p[1], p[0]))
        turn = (turn + 180.0) % 360.0 - 180.0
        rise = (r[2] - p[2]) % repeat
        key = (round(turn), round(rise, 1))
        if key in seen:
            continue
        seen.add(key)
        if _maps(symbols, moving, repeat, target, kinds, turn, rise):
            found.append((turn, rise))
            if first:
                return found
    return found


def _maps(symbols, moving, repeat, target, kinds, turn, rise) -> bool:
    c, s = math.cos(math.radians(turn)), math.sin(math.radians(turn))
    turned = moving @ np.array([[c, s, 0.0], [-s, c, 0.0],
                                [0.0, 0.0, 1.0]])
    turned[:, 2] += rise
    for i, at in enumerate(turned):
        others = target[kinds[symbols[i]]]
        gap = others - at
        gap[:, 2] -= repeat * np.round(gap[:, 2] / repeat)
        if np.min(np.linalg.norm(gap, axis=1)) > MATCH:
            return False
    return True


# =============================================================== library

#: Where the shipped rods are.
LIBRARY = Path(__file__).parent / "library" / "rods"


def shipped() -> dict[str, Path]:
    """Every rod in the library, by name."""
    return {p.stem: p for p in sorted(LIBRARY.glob("*.xyz"))}


__all__ = ["LIBRARY", "MATCH", "Rod", "RodError", "from_structure",
           "shipped"]
