"""
xtal.polymer.monomer
====================
One repeat unit, and which ends of it join.

A monomer is a molecule with two connection points: the **head**,
where it is bonded to the unit before it, and the **tail**, where the
next one is bonded to it.  ``[*:1]`` is the head and ``[*:2]`` the
tail; an unnumbered string goes by the order the stars were written,
which is all the sketch canvas can say.  ``[*:1]CC([*:2])C`` is
polypropylene with its methyl on the tail carbon -- head to tail is
then what a chain of them is, without anything having to say so.

A connection point is the ``X`` of :mod:`xtal.mof.attach`, so a
**ladder** monomer's point stands for two atoms: PIM-1's head is bonded
to both oxygens of a catechol and its tail to the two ring carbons the
next unit's oxygens meet.  Nothing here treats a ladder specially
beyond reading how many members each end has; joining one is
:mod:`xtal.polymer.chain`'s business.

**A third connection point is refused, by name.**  Branching is a
different generator (bonding reactive sites while packing, not a
walk), and when it comes ``[*:3]`` is its branch point.  Refusing now
rather than ignoring the third star means the format does not change
when it does.

**The other hand is a reflection.**  A monomer embedded once has
whatever chirality the embedding gave its stereocentre;
:meth:`Monomer.mirrored` is its enantiomer, which is how isotactic,
syndiotactic and atactic chains are made from one string.

Nothing here imports RDKit: a string is embedded through
:func:`xtal.build.from_smiles`, which does.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

from xtal.mof.attach import Attachment, members_of

#: What a connection point is spelled.
CONNECTION = "X"

#: A block file's bond letter -> the order stored here.  The inverse of
#: :data:`xtal.mof.block.BOND_LETTERS`.
_ORDERS = {"S": 1.0, "D": 2.0, "T": 3.0, "A": 1.5}


class MonomerError(ValueError):
    """Something that is not a repeat unit, said in a sentence."""


@dataclass(frozen=True)
class Monomer:
    """A repeat unit: atoms, bonds, a head and a tail.

    ``cart`` is centred on the body's centroid.  ``bonds`` are ``(i, j,
    order)`` and include the ones onto the two ``X`` atoms, which are
    what says which atoms each end stands for.
    """

    name: str
    elements: tuple[str, ...]
    cart: np.ndarray = field(repr=False)
    bonds: tuple[tuple[int, int, float], ...] = field(repr=False)
    head: int = 0
    tail: int = 1
    smiles: str = ""
    #: Whether this is the reflection of the unit as embedded.
    mirror: bool = False
    #: Whether its reflection is another unit: false for polyethylene,
    #: whose mirror image is itself turned over, so that a chain of it
    #: has no tacticity to report.  A unit read from atoms rather than
    #: a string is taken to have a hand, since nothing here can tell.
    handed: bool = True

    @property
    def n_atoms(self) -> int:
        return len(self.elements)

    @property
    def body(self) -> tuple[int, ...]:
        """Every atom but the two connection points, in order."""
        return tuple(i for i in range(self.n_atoms)
                     if i not in (self.head, self.tail))

    @property
    def body_elements(self) -> tuple[str, ...]:
        return tuple(self.elements[i] for i in self.body)

    @property
    def formula(self) -> str:
        counts: dict[str, int] = {}
        for element in self.body_elements:
            counts[element] = counts.get(element, 0) + 1
        return "".join(f"{s}{n if n > 1 else ''}"
                       for s, n in sorted(counts.items()))

    @property
    def mass(self) -> float:
        """g/mol of the body, which is what one unit adds to a chain."""
        from xtal.core import elements

        return float(sum(elements.element(e).mass
                         for e in self.body_elements))

    @property
    def head_members(self) -> tuple[int, ...]:
        return members_of((self.head, self.tail), self.bonds)[self.head]

    @property
    def tail_members(self) -> tuple[int, ...]:
        return members_of((self.head, self.tail), self.bonds)[self.tail]

    @property
    def backbone(self) -> tuple[int, ...]:
        """The shortest path of bonds from the first head member to the
        first tail member, both included -- what a torsion about a
        joint is measured along.  One atom when they are the same."""
        points = {self.head, self.tail}
        around: dict[int, list[int]] = {}
        for i, j, _ in self.bonds:
            if i not in points and j not in points:
                around.setdefault(i, []).append(j)
                around.setdefault(j, []).append(i)
        start, goal = self.head_members[0], self.tail_members[0]
        before = {start: start}
        queue = [start]
        while queue and goal not in before:
            atom = queue.pop(0)
            for other in sorted(around.get(atom, ())):
                if other not in before:
                    before[other] = atom
                    queue.append(other)
        if goal not in before:
            return (start,)
        path = [goal]
        while path[-1] != start:
            path.append(before[path[-1]])
        return tuple(reversed(path))

    @property
    def is_ladder(self) -> bool:
        """Whether its ends stand for more than one atom each."""
        return len(self.head_members) > 1

    def free_direction(self, member: int,
                       outward: bool = False) -> np.ndarray:
        """Unit vector along which ``member``'s joint bond leaves it.

        For a one-atom end it is the ``X`` direction, which came from
        the embedding's own capping hydrogen.  A ladder's ``X`` stands
        for two atoms and points between them, so each member's bond
        is worked out from its own neighbours: straight out of three,
        the in-plane bisector of two when the atom is sp2 and the
        tetrahedral direction nearest the ``X`` when it is not, and of
        one, the cone at 117 degrees (on an aromatic neighbour, an
        aryl ether's angle) or 109.5 nearest the ``X`` -- or, with
        ``outward``, farthest from it, which is where a hydrogen
        capping an open end goes: two catechol hydrogens turned toward
        the ``X`` between them were 1.17 A apart.
        """
        point = (self.head if member in self.head_members
                 else self.tail)
        here = self.cart[member]
        toward = self.cart[point] - here
        toward = toward / np.linalg.norm(toward)
        inner = [(j if i == member else i, o) for i, j, o in self.bonds
                 if member in (i, j) and point not in (i, j)]
        if len(self.head_members) < 2 or not inner:
            return toward
        vectors = np.array([self.cart[n] - here for n, _ in inner])
        vectors /= np.linalg.norm(vectors, axis=1)[:, None]
        if len(inner) >= 3:
            return _unit(-vectors.sum(axis=0))
        if len(inner) == 2:
            bisector = _unit(-vectors.sum(axis=0))
            if any(o > 1.0 for _, o in inner):
                return bisector
            normal = _unit(np.cross(vectors[0], vectors[1]))
            half = np.radians(54.75)
            options = [np.cos(half) * bisector + s * np.sin(half) * normal
                       for s in (1.0, -1.0)]
            return max(options, key=lambda d: d @ toward)
        v = vectors[0]
        neighbour = inner[0][0]
        aromatic = any(o > 1.0 for i, j, o in self.bonds
                       if neighbour in (i, j))
        theta = np.radians(117.0 if aromatic else 109.47)
        across = toward - (toward @ v) * v
        if np.linalg.norm(across) < 1e-9:
            across = np.cross(v, [1.0, 0.0, 0.0])
        across = -_unit(across) if outward else _unit(across)
        return _unit(np.cos(theta) * v + np.sin(theta) * across)

    def attachment(self, end: str) -> Attachment:
        """``"head"`` or ``"tail"``, as :mod:`xtal.mof.attach` reads
        a connection point."""
        point = self.head if end == "head" else self.tail
        members = (self.head_members if end == "head"
                   else self.tail_members)
        offsets = self.cart[list(members)] - self.cart[point]
        return Attachment(point, tuple(members), offsets)

    def mirrored(self) -> Monomer:
        """The other hand: every position reflected through a plane.

        Which plane is immaterial -- a chain re-orients each unit as
        it is joined -- so it is the simplest one, x to -x.
        """
        cart = np.array(self.cart, dtype=float) * np.array([-1, 1, 1])
        return replace(self, cart=cart, mirror=not self.mirror)


def _unit(vector) -> np.ndarray:
    return vector / np.linalg.norm(vector)


def from_parts(elements, cart, bonds, connections, name: str = "",
               smiles: str = "") -> Monomer:
    """A monomer from atoms, bonds and its connection points, head
    first -- checked, and centred on its body."""
    elements = tuple(str(e) for e in elements)
    cart = np.array(cart, dtype=float).reshape(-1, 3)
    bonds = tuple((int(i), int(j), float(o)) for i, j, o in bonds)
    connections = tuple(int(c) for c in connections)
    what = name or smiles or "this monomer"
    if len(connections) < 2:
        raise MonomerError(
            f"a monomer needs a head and a tail -- [*:1] where the unit "
            f"before it joins and [*:2] where the next one does -- and "
            f"{what} has {len(connections)} connection point"
            f"{'' if len(connections) == 1 else 's'}")
    if len(connections) > 2:
        raise MonomerError(
            f"branching is not built yet: {what} has "
            f"{len(connections)} connection points, and a chain takes "
            f"two, a head and a tail")
    head, tail = connections
    members = members_of(connections, bonds)
    if any({head, tail} == {i, j} for i, j, _ in bonds):
        raise MonomerError(f"the head and tail of {what} are bonded "
                           f"to each other")
    for point, end in ((head, "head"), (tail, "tail")):
        if not members[point]:
            raise MonomerError(f"the {end} of {what} is bonded to "
                               f"nothing, so it joins nothing")
    if len(members[head]) != len(members[tail]):
        raise MonomerError(
            f"the head of {what} stands for {len(members[head])} "
            f"atom(s) and its tail for {len(members[tail])}, so one "
            f"unit cannot join the next -- a ladder is two at each end")
    if len(members[head]) > 2:
        raise MonomerError(
            f"each end of {what} stands for {len(members[head])} atoms; "
            f"a chain joins through one, and a ladder through two")
    if len(members[head]) > 1 and set(members[head]) & set(members[tail]):
        raise MonomerError(f"the head and tail of {what} share an "
                           f"atom, and a ladder cannot close on itself")
    body = [i for i in range(len(elements)) if i not in (head, tail)]
    cart = cart - cart[body].mean(axis=0)
    return Monomer(name=name, elements=elements, cart=cart, bonds=bonds,
                   head=head, tail=tail, smiles=smiles)


def from_smiles(smiles: str, name: str = "",
                optimise: bool = True) -> Monomer:
    """Embed a starred SMILES string and read its head and tail.

    Raises :class:`xtal.build.BuildError` for a string that is not a
    molecule and :class:`MonomerError` for one that is not a monomer.
    ``optimise=False`` skips the force-field polish, for a dialog
    asking only whether the string is a monomer at all.
    """
    from xtal.build import from_smiles as embed
    from xtal.build.chem import stereocentres

    molecule = embed(smiles, name=name, optimise=optimise)
    unit = from_parts(molecule.elements, molecule.cart, molecule.bonds,
                      molecule.connections, name=name,
                      smiles=str(smiles).strip())
    return replace(unit, handed=stereocentres(smiles) > 0)


def from_library(name: str) -> Monomer:
    """A ``Monomer`` entry of the fragment library, by name."""
    from xtal.build import library

    entry = library.find(name)
    if entry is None or entry.category != library.MONOMER:
        known = ", ".join(e.name for e in monomers())
        raise MonomerError(f"no monomer called {name!r} in the "
                           f"library; it has {known}")
    return from_smiles(entry.smiles, name=entry.name)


def monomers():
    """The library's monomers, in file order."""
    from xtal.build import library

    return tuple(e for e in library.entries()
                 if e.category == library.MONOMER)


def from_block_file(path) -> Monomer:
    """A block file (PORMAKE's ``.xyz``) with two connection points,
    the first the head -- the order *Save as Monomer* writes them in."""
    from xtal.mof.catalog import read_building_block

    path = Path(path)
    block = read_building_block(path)
    bonds = tuple((int(i), int(j), _ORDERS.get(str(letter), 1.0))
                  for i, j, letter in block.bonds)
    return from_parts(block.symbols, block.positions, bonds,
                      block.connections, name=path.stem)


def connection_points(structure) -> tuple[int, ...]:
    """The structure's connection points, by index in its P1 cell --
    what *Save as Monomer* offers as the head."""
    from xtal.core import p1

    cell = p1.expand(structure)
    return tuple(i for i, symbol in enumerate(cell.elements)
                 if symbol == CONNECTION)


def point_name(structure, point: int) -> str:
    """A connection point as a person picks it: its label and the
    atoms it stands for, ``X1 on C3`` or ``X2 on O4 + O5``."""
    from xtal.core import bonding, p1

    cell = p1.expand(structure)

    def label(atom):
        given = cell.labels[atom] if len(cell.labels) > atom else ""
        return str(given) or f"{cell.elements[atom]}{atom + 1}"

    graph = bonding.graph(structure)
    members = dict.fromkeys(
        j for j, _image in graph.neighbors_with_images(point)
        if cell.elements[j] != CONNECTION)
    on = " + ".join(label(j) for j in members) or "nothing"
    return f"{label(point)} on {on}"


def from_structure(structure, head: int | None = None,
                   name: str = "") -> Monomer:
    """The monomer *Save as Monomer* would write, read back through
    the block file itself, so the check is the reader's and not a
    second opinion of it."""
    import tempfile

    from xtal.mof.block import BlockError, write_building_block

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / f"{name or 'monomer'}.xyz"
        try:
            write_building_block(structure, path, head=head)
        except BlockError as exc:
            raise MonomerError(str(exc)) from None
        return from_block_file(path)


def save(structure, path, head: int | None = None) -> Path:
    """Write ``structure`` as a monomer block file, ``head`` first.

    Checked before anything is written, so a refusal leaves no file
    for the polymer builder to list and then fail on.
    """
    from xtal.mof.block import write_building_block

    path = Path(path)
    from_structure(structure, head=head, name=path.stem)
    return write_building_block(structure, path, head=head)


def saved(folder) -> tuple[Path, ...]:
    """The monomer files in ``folder``, by name; none if it is not
    there yet."""
    folder = Path(folder)
    if not folder.is_dir():
        return ()
    return tuple(sorted(folder.glob("*.xyz"),
                        key=lambda p: p.stem.lower()))
