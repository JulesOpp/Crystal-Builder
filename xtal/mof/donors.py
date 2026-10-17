"""A rod linker drawn whole: its donors found and made its points.

A rod carries the donor groups it was cut with -- MOF-74's carboxylates
and phenolates are the rod's -- so a linker meets it as a core with an
``X`` where each donor joined it.  Drawn that way, nothing says which
``X`` was the carboxylate: a biphenyl with ``X`` on C3 and C4 is dobpdc
and pc-dobpdc both.  Drawn whole, with its carboxylates and phenols, the
drawing says it, and :func:`as_linker` turns it into that core with each
``X`` named by the donor it stands for (``Block.kinds``), which a build
pairs only with a rod point of the same kind.

**An L-type donor is drawn bare too.**  A pyridyl meets its metal
through the nitrogen's lone pair, and the point is a fourth bond on
the nitrogen (``*[n+]``) that nobody draws by instinct.  Asked for
(``pyridyls``, the MOF builder's slots and its partitioners, never a
rod), a drawing with no carboxylate and no hydroxyl makes a point of
each ring nitrogen with its lone pair free -- no hydrogen, and both
ring neighbours bearing nothing but hydrogen -- with its ``X`` on the
lone-pair line.  So tpt's three pyridyls are its points and its
triazine nitrogens, each between two substituted carbons, are not;
tripp's central pyridine and tppm's pyrimidine likewise.

Read off the drawing's bonds and never its lengths, as a functional
group is.  :mod:`xtal.core.groups` is not used: it reads a drawn
``[O-]`` on a ring carbon as a ketone, and a phenolate drawn as the
anion or the acid is one donor.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace

import numpy as np

from xtal.mof.block import BOND_LETTERS, CONNECTION_DISTANCE

CARBOXYLATE = "carboxylate"
PHENOLATE = "phenolate"
PYRIDYL = "pyridyl"

#: What each kind is called in a sentence, many of them.
PLURALS = {CARBOXYLATE: "carboxylates", PHENOLATE: "phenolates",
           PYRIDYL: "pyridyl nitrogens"}

#: A bond letter's order, for a nitrogen's valence.
_ORDER = {"S": 1.0, "D": 2.0, "T": 3.0, "A": 1.5}

_HYDROGENS = ("H", "D")


class DonorError(ValueError):
    """A linker drawn whole whose donors cannot be made its points,
    said in a sentence."""


@dataclass(frozen=True)
class Donor:
    """One donor group of a linker drawn whole."""

    kind: str
    #: Every atom of the group, hydrogens included: what is dropped.
    #: Empty for a pyridyl, whose nitrogen stays and carries the point.
    atoms: tuple[int, ...]
    #: The group's atom bonded to the linker -- the carboxylate's
    #: carbon, the phenolate's oxygen -- where the rod's ``X`` hangs;
    #: a pyridyl's nitrogen.
    attach: int
    #: The linker atom it is bonded to; for a pyridyl, the nitrogen's
    #: two ring neighbours, whose middle the lone pair points away
    #: from.
    partner: int | tuple[int, int]


def _neighbours(block) -> dict[int, list[int]]:
    near = defaultdict(list)
    for i, j, _letter in block.bonds:
        near[i].append(j)
        near[j].append(i)
    return near


def find(block, pyridyls: bool = False) -> list[Donor]:
    """The carboxylates (acid or anion) and phenolates (phenol or
    anion: an oxygen on one sp2 carbon) of ``block``, in atom order;
    with ``pyridyls``, and none of those, its free pyridyl nitrogens
    (:func:`_pyridyls`)."""
    symbols = block.symbols
    near = _neighbours(block)

    def hydrogens(a):
        return [n for n in near[a] if symbols[n] in _HYDROGENS]

    def heavy(a):
        return [n for n in near[a] if symbols[n] not in _HYDROGENS]

    found, claimed = [], set()
    for c, symbol in enumerate(symbols):
        if symbol != "C":
            continue
        oxygens = [n for n in near[c] if symbols[n] == "O"
                   and heavy(n) == [c] and len(hydrogens(n)) <= 1]
        others = [n for n in heavy(c) if n not in oxygens]
        if len(oxygens) == 2 and len(others) == 1 and not hydrogens(c):
            atoms = (c, *oxygens, *(h for o in oxygens
                                     for h in hydrogens(o)))
            found.append(Donor(CARBOXYLATE, tuple(sorted(atoms)), c,
                               others[0]))
            claimed.update(atoms)
    for o, symbol in enumerate(symbols):
        if symbol != "O" or o in claimed:
            continue
        carbons = heavy(o)
        if (len(carbons) == 1 and symbols[carbons[0]] == "C"
                and len(hydrogens(o)) <= 1
                and len(near[carbons[0]]) == 3):
            atoms = (o, *hydrogens(o))
            found.append(Donor(PHENOLATE, tuple(sorted(atoms)), o,
                               carbons[0]))
    if pyridyls and not found:
        found = _pyridyls(block, near, heavy, hydrogens)
    return sorted(found, key=lambda d: d.attach)


def _pyridyls(block, near, heavy, hydrogens) -> list[Donor]:
    """Each ring nitrogen whose lone pair is free: no hydrogen, two
    neighbours by a single and a double or two aromatic bonds, each
    bearing only hydrogen beside the ring -- so a triazine's nitrogen
    between two arms is not one, and a pyrazine has two."""
    symbols = block.symbols
    order = defaultdict(float)
    for i, j, letter in block.bonds:
        order[i] += _ORDER.get(letter, 1.0)
        order[j] += _ORDER.get(letter, 1.0)
    found = []
    for n, symbol in enumerate(symbols):
        flanks = heavy(n)
        if (symbol != "N" or hydrogens(n) or len(near[n]) != 2
                or len(flanks) != 2 or order[n] != 3.0):
            continue
        a, b = flanks
        if (len(heavy(a)) != 2 or len(heavy(b)) != 2
                or not _ring_through(near, n, a, b)):
            continue
        found.append(Donor(PYRIDYL, (), n, (a, b)))
    return found


def _ring_through(near, n, a, b, limit: int = 7) -> bool:
    """Whether ``a`` and ``b`` are joined other than through ``n``,
    within a ring of ``limit`` atoms."""
    seen, frontier = {n, a}, [a]
    for _ in range(limit - 2):
        frontier = [m for f in frontier for m in near[f]
                    if m not in seen and not seen.add(m)]
        if b in frontier:
            return True
    return False


def as_linker(block, pyridyls: bool = False):
    """``block``, drawn whole, as the core a rod meets: each donor
    dropped and an ``X`` put :data:`CONNECTION_DISTANCE` from its
    attaching atom toward the linker -- where
    :func:`xtal.mof.rod.linker_from_structure` puts one, so a drawn
    linker and a cut one agree -- named by its kind in ``kinds``.
    A pyridyl nitrogen is kept and its ``X`` put on its lone-pair
    line, as ``*[n+]`` embeds one.

    A block that already has ``X`` atoms is handed back as it is.
    """
    if block.connections:
        return block
    donors = find(block, pyridyls)
    if not donors:
        what = ("carboxylate, phenol or pyridyl" if pyridyls
                else "carboxylate or phenol")
        raise DonorError(f"this linker has no connection points and no "
                         f"{what} to make them from")
    drop = {a for d in donors for a in d.atoms}
    keep = [a for a in range(len(block.symbols)) if a not in drop]
    new = {a: k for k, a in enumerate(keep)}
    xyz = np.asarray(block.positions, float)
    symbols = [block.symbols[a] for a in keep]
    positions = [xyz[a] for a in keep]
    bonds = [(new[i], new[j], letter) for i, j, letter in block.bonds
             if i in new and j in new]
    connections, kinds = [], []
    for d in donors:
        if d.kind == PYRIDYL:
            at = d.attach
            step = xyz[at] - xyz[list(d.partner)].mean(axis=0)
        else:
            at = d.partner
            step = xyz[d.partner] - xyz[d.attach]
        x = len(symbols)
        symbols.append("X")
        positions.append(xyz[d.attach] + CONNECTION_DISTANCE * step
                         / np.linalg.norm(step))
        bonds.append((new[at], x, "S"))
        connections.append(x)
        kinds.append(d.kind)
    return replace(block, symbols=symbols,
                   positions=np.array(positions), bonds=bonds,
                   connections=connections, kinds=tuple(kinds))


def described(kinds) -> str:
    """``kinds`` in words: "a carboxylate and a phenolate".  A kind no
    drawn donor is called (a triazolate's ``"CC"``) is a point with no
    name."""
    counts = defaultdict(int)
    for k in kinds:
        counts[k if k in PLURALS else ""] += 1
    parts = []
    for k, n in counts.items():
        if not k:
            parts.append(f"{n} unnamed points" if n > 1
                         else "an unnamed point")
        else:
            parts.append(f"{n} {PLURALS[k]}" if n > 1 else f"a {k}")
    return " and ".join(parts)


def whole(molecule):
    """A built molecule (:class:`xtal.build.molecule.Molecule`) as a
    block with no ``X``: a rod linker drawn whole, as it is saved and
    as :func:`as_linker` reads it.  Its stars, if it was drawn with
    any, become ``X`` as they always did."""
    from xtal.mof.trimer import Block

    symbols = ["X" if i in set(molecule.connections) else e
               for i, e in enumerate(molecule.elements)]
    bonds = [(int(i), int(j), BOND_LETTERS.get(float(order), "S"))
             for i, j, order, *_rest in molecule.bonds]
    return Block(symbols, np.asarray(molecule.cart, float), bonds,
                 [i for i, s in enumerate(symbols) if s == "X"])


def points(block, pyridyls: bool = False
           ) -> tuple[int, tuple[str, ...]]:
    """How many connection points ``block`` makes and what each is:
    its ``X`` atoms, bare, or else one per donor it was drawn with."""
    if block.connections:
        return len(block.connections), ()
    found = find(block, pyridyls)
    return len(found), tuple(d.kind for d in found)
