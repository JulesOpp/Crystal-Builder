"""
xtal.mof.rod
============
A rod: a 1-periodic secondary building unit, as MOF-74, MIL-53,
MOF-303, Ni2Cl2BTDD and Co(BDP) are built from.

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

A rod saved from a crystal (:func:`save_block`) also says
``linker=NAME`` on its second line: the linker cut beside it.  A shipped
chiral rod says ``hands=same`` or ``hands=alternating``: how its
neighbours sat in its crystal, which a rod cannot tell from itself.

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

#: Linker atoms nearer than this, A, are bonded, and two points cut at
#: them meet one end of one linker (:func:`_face_size`).  A C-C bond is
#: 1.54 at most; the next nearest across a ring is 2.4.
FACE_BOND = 1.8

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
    #: The linker cut beside it (:func:`save_block`), by name, for a
    #: build that names none.  The shipped rods leave it empty and are
    #: known by family (``rodbuild.OWN_LINKERS``).
    linker: str = ""
    #: How many points one end of a linker meets: 1 for a carboxylate
    #: or an azolate, 2 for dobdc's carboxylate and phenolate, which
    #: chelate the rod together.  A linker for this rod has twice as
    #: many points as this, half at each end.
    face: int = 1
    #: How a chiral rod's neighbours sat in the crystal it was cut
    #: from -- ``"same"`` hand or ``"alternating"`` -- which is what
    #: ``hands="auto"`` builds (:func:`xtal.mof.rodnet.rod_net`).
    #: Empty where nobody said, as for a rod saved from a structure.
    hands: str = ""

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

    def kind(self, point: int) -> str:
        """The donor ``point`` stands for, by the atoms it hangs off
        and their bonds: ``"carboxylate"`` for one carbon carrying two
        oxygens, ``"phenolate"`` for one oxygen, and otherwise the
        members' symbols (``"CC"``, a triazolate's two carbons), which
        no drawn donor is called."""
        from xtal.mof import donors

        members = sorted({m for m, _ in self.members(point)})
        if len(members) == 1:
            m = members[0]
            if self.symbols[m] == "O":
                return donors.PHENOLATE
            oxygens = {j for j, _ in self.neighbours(m)
                       if self.symbols[j] == "O"}
            if self.symbols[m] == "C" and len(oxygens) == 2:
                return donors.CARBOXYLATE
        return "".join(self.symbols[m] for m in members)

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
        if self.linker:
            head.append(f"linker={self.linker}")
        if self.face != 1:
            head.append(f"face={self.face}")
        if self.hands:
            head.append(f"hands={self.hands}")
        lines = [str(len(self.symbols)), " ".join(head)]
        for s, xyz in zip(self.symbols, self.positions, strict=True):
            # Adding 0.0 drops the sign of a zero: an atom on the axis
            # is -1e-6 on one BLAS and +1e-6 on another, and the file
            # is compared byte for byte with what the script writes.
            x, y, z = (round(float(v), 4) + 0.0 for v in xyz)
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
                   found.get("name", ""), tuple(notes),
                   found.get("linker", ""), int(found.get("face", 1)),
                   found.get("hands", ""))

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
    split = _Split.of(structure, rules)
    cell, symbols, nbr = split.cell, split.symbols, split.nbr
    n, order_of = len(symbols), split.order_of
    metal, heavy, bridge = split.metal, split.heavy, split.bridge
    linker, donor = split.linker, split.donor
    groups, group_of = split.groups, split.group_of
    if not 0 <= seed < n or not el.element(symbols[seed]).is_metal:
        raise RodError(f"atom {seed} is not a metal, so no rod starts "
                       f"there")

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
    # An anchor on the repeat's boundary is a rounding error from
    # either side of it: on OpenBLAS MOF-74's first Zn was at z = 0
    # and on Accelerate at z = repeat, and every bond's shift with it.
    ups = {a: math.floor(float((where[anchor[a]] - centre) @ axis)
                         / length + 1e-6) for a in offset}
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

    points, faced = {}, {}
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
        faced[x] = [p for _, p in hung]
    if not points:
        raise RodError("no linker meets this rod")

    positions = np.array(positions)
    edges = _shape(points, length, shape)
    rod = Rod(out_symbols, positions, length, sorted(bonds), edges,
              name, (), face=_face_size(faced, length))
    return rod


def _face_size(faced, length) -> int:
    """How many points meet one end of one linker: those whose linker
    atoms are one atom or bonded (dobdc's ring carbons under its
    carboxylate and its phenolate), the next repeat counted.

    Read off the crystal and never off the X atoms' spacing, which is
    where the cut put them and says nothing about which linker each
    faces.
    """
    xs = sorted(faced)
    parent = {x: x for x in xs}

    def root(a):
        while parent[a] != a:
            a = parent[a]
        return a

    rise = np.array([0.0, 0.0, length])
    for i, a in enumerate(xs):
        for b in xs[i + 1:]:
            if any(np.linalg.norm(p + k * rise - q) < FACE_BOND
                   for p in faced[a] for q in faced[b]
                   for k in (-1, 0, 1)):
                parent[root(b)] = root(a)
    sizes = {len([x for x in xs if root(x) == r])
             for r in {root(x) for x in xs}}
    if len(sizes) != 1:
        raise RodError(f"the linkers meet this rod by {sorted(sizes)} "
                       f"points at an end, not one number for all")
    return sizes.pop()


def linker_from_structure(structure, seed: int | None = None, *,
                          rules=None, whole: bool = False):
    """The linker holding atom ``seed`` (any atom of it, in the P1
    cell's numbering; the first one when ``None``), cut where
    :func:`from_structure` cuts a rod: a
    :class:`~xtal.mof.trimer.Block`.

    So the two halves meet exactly.  A rod keeps each donor group
    whole and puts an ``X`` :data:`CONNECTION_DISTANCE` out from the
    group's atoms towards the linker; the linker is everything else of
    its molecule, with its ``X`` **where the rod's is** -- worked out
    the same way, from the group's side.  Coinciding ``X`` is the joint
    every build here makes, so the crystal's joint comes back as it
    was.  Measured from the linker's own atoms instead, the two only
    meet across a gap of 1.5 A: BTDD's triazolate carbons are 1.2 A
    from the middle of the benzene carbons they bond to, and its
    joints came out 1.65 A long.  A linker drawn by hand (PORMAKE's
    E14 has 1.54 A ring bonds) reaches 0.3 A further across and puts
    the rods that much further apart; one cut from the crystal has
    the crystal's own lengths.

    ``whole`` keeps the donor groups it meets instead of an ``X`` for
    each -- the linker as a person would draw it, which
    :func:`xtal.mof.donors.as_linker` turns back into these ``X``, each
    named by its donor.  Only for carboxylates and phenolates: a group
    no donor is called (BTDD's triazolate) would come back as nothing.
    """
    from xtal.mof.trimer import Block

    split = _Split.of(structure, rules)
    cell, symbols, nbr = split.cell, split.symbols, split.nbr
    grouped = set(split.group_of)
    body = {i for i in split.linker if i not in grouped}
    body |= {i for i, s in enumerate(symbols) if s in ("H", "D")
             and any(j in body for j, _ in nbr[i])}
    if seed is None:
        seed = min((i for i in body if split.heavy[i]), default=None)
    if seed is None or seed not in body:
        raise RodError("no linker atom there: a linker is what is left "
                       "once the metals, their bridges and the donor "
                       "groups are taken away")
    offset, translations = _walk(seed, body, nbr, lambda i, j: True)
    if translations:
        raise RodError("this linker repeats through the crystal, so it "
                       "is not a molecule to place between rods")
    to_cart = cell.lattice.to_cart
    where = {a: np.asarray(to_cart(cell.frac[a] + offset[a]), float)
             for a in offset}
    atoms = sorted(offset)
    place = {a: k for k, a in enumerate(atoms)}
    out_symbols = [symbols[a] for a in atoms]
    positions = [where[a] for a in atoms]
    bonds = []
    cuts = []                                # (group, member, partner)
    reached = []                             # (group, i, j, j's frac)
    for i in atoms:
        for j, image in nbr[i]:
            if j in offset:
                if place[i] < place[j]:
                    letter = BOND_LETTERS.get(split.order_of[(i, j)],
                                              "S")
                    bonds.append((place[i], place[j], letter))
            elif j in grouped:
                partner = np.asarray(to_cart(cell.frac[j] + offset[i]
                                             + image), float)
                cuts.append((split.group_of[j], place[i], partner))
                reached.append((split.group_of[j], i, j,
                                cell.frac[j] + offset[i] + image))
    # One X per group *met*: a group reached by two of the linker's
    # atoms (a triazolate fused to a benzene) is one point standing for
    # both, and the same group seen through two cells is two points.
    met: list[tuple[int, list[int], list[np.ndarray]]] = []
    for group, member, partner in cuts:
        for k, members, partners in met:
            if k == group and min(np.linalg.norm(partner - p)
                                  for p in partners) < 3.0:
                members.append(member)
                partners.append(partner)
                break
        else:
            met.append((group, [member], [partner]))
    if len(met) < 2:
        raise RodError("this linker meets fewer than two donor groups, "
                       "so it joins nothing")
    if whole:
        return _with_groups(split, reached, place, out_symbols,
                            positions, bonds)
    connections = []
    for _group, members, partners in met:
        distinct = {tuple(np.round(q, 4)): q for q in partners}
        middle = np.mean(list(distinct.values()), axis=0)
        outward = np.mean([positions[m] for m in members], axis=0) \
            - middle
        outward /= np.linalg.norm(outward)
        members = sorted(set(members))
        x = len(out_symbols)
        out_symbols.append("X")
        positions.append(middle + CONNECTION_DISTANCE * outward)
        bonds.extend((m, x, "S") for m in members)
        connections.append(x)
    positions = np.array(positions)
    positions -= positions[connections].mean(axis=0)
    return Block(out_symbols, positions, sorted(bonds), connections)


def _with_groups(split, reached, place, symbols, positions, bonds):
    """The linker with each donor group it meets put back whole, at
    the image it is met at, its hydrogens with it: a block with no
    ``X``."""
    from xtal.mof.trimer import Block

    cell, nbr = split.cell, split.nbr
    to_cart = cell.lattice.to_cart
    symbols, positions, bonds = list(symbols), list(positions), list(bonds)
    added = {}                               # (atom, rounded frac) -> k

    def add(a, frac):
        key = (a, tuple(np.round(frac, 3)))
        if key not in added:
            added[key] = len(symbols)
            symbols.append(split.symbols[a])
            positions.append(np.asarray(to_cart(frac), float))
        return added[key]

    seen: set = set()
    for group, i, j, frac_j in reached:
        k = add(j, frac_j)
        bonds.append((place[i], k, BOND_LETTERS.get(
            split.order_of[(i, j)], "S")))
        queue = deque([(j, np.asarray(frac_j, float))])
        while queue:
            a, frac_a = queue.popleft()
            ka = add(a, frac_a)
            key_a = (a, tuple(np.round(frac_a, 3)))
            if key_a in seen:
                continue
            seen.add(key_a)
            for n, image in nbr[a]:
                in_group = split.group_of.get(n) == group
                hydrogen = (split.symbols[n] in ("H", "D")
                            and split.symbols[a] not in ("H", "D"))
                if not (in_group or hydrogen):
                    continue
                frac_n = frac_a - cell.frac[a] + cell.frac[n] + image
                kn = add(n, frac_n)
                if ka < kn:
                    bonds.append((ka, kn, BOND_LETTERS.get(
                        split.order_of[(a, n)], "S")))
                queue.append((n, frac_n))
    positions = np.array(positions)
    positions -= positions.mean(axis=0)
    return Block(symbols, positions, sorted(set(bonds)), [])


#: Under a workspace's ``blocks`` folder: rods saved from a structure,
#: and beside them, in ``linkers``, the linker each was cut with.  A
#: folder of their own because PORMAKE globs ``blocks/*.xyz`` as its
#: own blocks, and a rod file is not one.
SAVED = "rods"


@dataclass
class Saved:
    """A rod and its linker, written by :func:`save_block`."""

    rod: Rod
    path: Path
    linker_path: Path
    prepared: tuple[str, ...] = ()

    def sentence(self) -> str:
        n = len(self.rod.connections)
        hand = self.rod.hand
        return (f"saved rod {self.rod.name}: {len(self.rod.metals)} "
                f"metal(s) and {n} point(s) of extension a "
                f"{self.rod.repeat:.2f} A repeat, "
                f"{'achiral' if hand is None else hand + '-handed'}, "
                f"with its linker {self.linker_path.stem}")


def save_block(structure, blocks, seed: int | None = None, *,
               name: str = "", shape="rng", rules=None,
               prepared: bool = True) -> Saved:
    """Cut a rod and its linker out of ``structure`` and write both
    under ``blocks`` (a workspace's ``blocks`` folder): the rod as
    ``rods/<name>.xyz``, naming its linker, and the linker as
    ``rods/linkers/<name>.xyz``.

    ``seed`` is a metal in the P1 cell's numbering of ``structure``;
    ``None`` is its first metal.  With ``prepared`` the cut is from a
    copy run through :func:`xtal.core.prepare.run` first -- a ConQuest
    export writes symmetry copies as sites (Ni2Cl2BTDD's 1152 atoms on
    378 places), and a rod walked through those is not one -- and the
    seed is carried to the prepared cell by where it is.  The structure
    itself is not touched.

    The linker is the crystal's first; a rod MOF with one linker, which
    is every rod MOF here, has no other.  Cut beside the rod, it meets
    it at the crystal's own lengths (:func:`linker_from_structure`), so
    the rod rebuilds its own framework.
    """
    from xtal.core import p1
    from xtal.workspace import safe_name

    steps = ()
    cell = p1.expand(structure)
    if seed is None:
        seed = _first_metal(cell.elements)
    if not 0 <= seed < len(cell.elements) \
            or not el.element(cell.elements[seed]).is_metal:
        raise RodError(f"atom {seed} is not a metal, so no rod starts "
                       f"there")
    if prepared:
        from xtal.core import prepare

        at = np.asarray(cell.lattice.to_cart(cell.frac[seed]), float)
        outcome = prepare.run(structure)
        structure, steps = outcome.structure, tuple(outcome.said)
        seed = _nearest(p1.expand(structure), cell.elements[seed], at)
    name = safe_name(name or default_name(structure), "rod")
    if name in shipped():
        raise RodError(f"{name} is a shipped rod's name, and a build "
                       f"naming it would take the shipped one: call "
                       f"this one something else")
    cut = from_structure(structure, seed, shape=shape, rules=rules,
                         name=name)
    linker = linker_from_structure(structure, rules=rules)
    cut = replace(cut, linker=name)
    folder = Path(blocks) / SAVED
    path = cut.write(folder / f"{name}.xyz")
    linker_path = folder / "linkers" / f"{name}.xyz"
    linker_path.parent.mkdir(parents=True, exist_ok=True)
    from xtal.io.atomic import write_text

    write_text(linker_path, linker.text())
    return Saved(cut, path, linker_path, steps)


def default_name(structure) -> str:
    """The file ``structure`` came from, else its title, as a name --
    ``""`` with neither."""
    from xtal.workspace import safe_name

    for key in ("source", "title"):
        text = str(structure.meta.get(key, "") or "")
        if text:
            return safe_name(Path(text).stem, "rod")
    return ""


def saved(blocks) -> dict[str, Path]:
    """Every rod saved under ``blocks``, by name."""
    folder = Path(blocks) / SAVED
    return {p.stem: p for p in sorted(folder.glob("*.xyz"))}


def _nearest(cell, symbol, at) -> int:
    """The atom ``symbol`` of ``cell`` nearest ``at`` (Cartesian), over
    the cell's images: where a seed went when the cell was prepared,
    which renumbers it and may change it (a centred cell's primitive
    one)."""
    frac = np.asarray(cell.lattice.to_frac(at), float)
    best, found = math.inf, None
    for i, s in enumerate(cell.elements):
        if s != symbol:
            continue
        gap = cell.frac[i] - frac
        gap -= np.round(gap)
        d = float(np.linalg.norm(cell.lattice.to_cart(gap)))
        if d < best:
            best, found = d, i
    if found is None:
        raise RodError(f"the prepared cell has no {symbol} left")
    return found


def _first_metal(symbols) -> int:
    for i, s in enumerate(symbols):
        if s != "X" and el.element(s).is_metal:
            return i
    raise RodError("there is no metal here, so no rod")


@dataclass
class _Split:
    """A crystal's atoms told apart: metals, bridges (bonded to metals
    alone), the linkers' atoms, the donors among them and the donor
    groups a rod keeps whole."""

    cell: object
    symbols: list
    nbr: dict
    order_of: dict
    metal: list
    heavy: list
    bridge: list
    linker: set
    donor: set
    groups: list
    group_of: dict

    @classmethod
    def of(cls, structure, rules=None) -> _Split:
        from xtal.core import bonding, p1

        cell = p1.expand(structure)
        graph = bonding.graph(structure, rules)
        orders = bonding.orders(structure, rules)
        symbols = cell.elements
        n = len(symbols)
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
        return cls(cell, symbols, nbr, order_of, metal, heavy, bridge,
                   linker, donor, groups, group_of)


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


#: The linkers cut from the same crystals as the rods, by
#: :func:`linker_from_structure`, so each rod has the linker that meets
#: it at the crystal's own lengths.
LINKERS = LIBRARY / "linkers"


#: What a shipped rod is called where a person reads it, by family, the
#: metal put in for ``{M}``: the rod's own chemistry, which is what
#: tells MIL-53's trans hydroxides from MOF-303's cis ones.  The file
#: names stay the keys, so a command line and a saved form keep working.
LABELS = {
    "MIL-53": "{M}(OH)(O2CR)2-trans",
    "MOF-303": "{M}(OH)(O2CR)2-cis",
    "Ni2Cl2BTDD": "{M}2Cl2(bta)2",
    "MOF-74": "MOF-74 SBU ({M})",
    "MBDP": "{M}(pz)2 -- {M}(BDP)",
}


def label(name: str) -> str:
    """What the rod called ``name`` is shown as: its :data:`LABELS`
    entry with its metal, or the name itself (a saved rod)."""
    family, _, metal = str(name).rpartition("_")
    form = LABELS.get(family)
    return form.format(M=metal) if form and metal else str(name)


def shipped() -> dict[str, Path]:
    """Every rod in the library, by name."""
    return {p.stem: p for p in sorted(LIBRARY.glob("*.xyz"))}


def shipped_linkers() -> dict[str, Path]:
    """Every linker in the rod library, by name."""
    return {p.stem: p for p in sorted(LINKERS.glob("*.xyz"))}


__all__ = ["LIBRARY", "LINKERS", "MATCH", "SAVED", "Rod", "RodError",
           "LABELS", "Saved", "default_name", "from_structure", "label",
           "linker_from_structure", "save_block", "saved", "shipped",
           "shipped_linkers"]
