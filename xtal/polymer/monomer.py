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
    def is_ladder(self) -> bool:
        """Whether its ends stand for more than one atom each."""
        return len(self.head_members) > 1

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
    if len(members[head]) > 1 and set(members[head]) & set(members[tail]):
        raise MonomerError(f"the head and tail of {what} share an "
                           f"atom, and a ladder cannot close on itself")
    body = [i for i in range(len(elements)) if i not in (head, tail)]
    cart = cart - cart[body].mean(axis=0)
    return Monomer(name=name, elements=elements, cart=cart, bonds=bonds,
                   head=head, tail=tail, smiles=smiles)


def from_smiles(smiles: str, name: str = "") -> Monomer:
    """Embed a starred SMILES string and read its head and tail.

    Raises :class:`xtal.build.BuildError` for a string that is not a
    molecule and :class:`MonomerError` for one that is not a monomer.
    """
    from xtal.build import from_smiles as embed

    molecule = embed(smiles, name=name)
    return from_parts(molecule.elements, molecule.cart, molecule.bonds,
                      molecule.connections, name=name,
                      smiles=str(smiles).strip())


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
