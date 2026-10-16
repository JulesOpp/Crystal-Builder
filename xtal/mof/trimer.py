"""
xtal.mof.trimer
===============
An M3O(RCO2)6 trimer with its open sites as connection points.

A trimer's six carboxylates are what a MIL-88 or MIL-100 framework is
built from, and the 6-connected blocks PORMAKE ships say exactly that.
Each metal also has an open sixth corner, opposite the mu3-oxide,
which a pore-space-partitioned framework (pacs) fills with a pyridyl
and a centring structure-directing agent fills with its donors.  For
those the trimer is **9-connected**: three more points, one on each
open-site line, so that a net like ``nia-d`` has somewhere for the
partitioner to go.

The nine-connected block is derived here from the six-connected one,
rather than drawn by hand, so every shipped trimer has a twin and the
twin is the same cluster to the bit.  The new points sit at the dative
distance less the pyridyl's 0.75 A (:func:`xtal.mof.attach.dative_point`),
which is why this module writes its own ``.xyz`` text:
:func:`xtal.mof.block.block_string` pulls every point in to 0.75 A,
which would give a 1.5 A metal-nitrogen bond.

Numpy and text only: a block file in, a block file out.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from xtal.mof.attach import DATIVE_MN, dative_point

#: Cosine of 30 degrees: a neighbour this close to straight through the
#: metal from the oxide is already on the open site, as
#: ``prepare._trimers`` judges it.
_ON_AXIS = 0.866

#: How many atoms a trimer metal with one open site is bonded to: the
#: mu3-oxide and four carboxylate oxygens, an octahedron less its
#: sixth corner.  A terminal ligand makes six, which is "filled".
OPEN_OCTAHEDRON = 5

#: An oxygen within this of a metal is bonded to it, A.  Used only to
#: judge whether a site is filled when a block's bond list has no word
#: for it; a trimer's own M-O are 1.9-2.2.
_BONDED = 2.5


class TrimerError(ValueError):
    """A block that is not an open M3O trimer, said in a sentence."""


@dataclass
class Block:
    """A PORMAKE building block as plain arrays.

    ``bonds`` are ``(i, j, letter)``.  ``connections`` lists the
    ``X`` atoms in the order the index line names them.
    """

    symbols: list[str]
    positions: np.ndarray
    bonds: list[tuple[int, int, str]]
    connections: list[int]

    @classmethod
    def read(cls, path) -> Block:
        return cls.parse(Path(path).read_text(encoding="utf-8"))

    @classmethod
    def parse(cls, text: str) -> Block:
        lines = text.splitlines()
        n = int(lines[0].split()[0])
        symbols, positions = [], []
        for line in lines[2:2 + n]:
            parts = line.split()
            symbols.append(parts[0])
            positions.append([float(v) for v in parts[1:4]])
        bonds = []
        for line in lines[2 + n:]:
            parts = line.split()
            if len(parts) < 2:
                continue
            letter = parts[2] if len(parts) > 2 else "S"
            bonds.append((int(parts[0]), int(parts[1]), letter))
        try:
            listed = [int(t) for t in lines[1].split()]
        except (IndexError, ValueError):
            listed = []
        marked = [i for i, s in enumerate(symbols) if s == "X"]
        connections = listed if sorted(listed) == marked else marked
        return cls(symbols, np.array(positions, dtype=float), bonds,
                   connections)

    def text(self) -> str:
        lines = [str(len(self.symbols)),
                 "".join(f"{i:5d}" for i in self.connections)]
        for s, (x, y, z) in zip(self.symbols, self.positions,
                                strict=True):
            lines.append(f"{s:<4s} {x:.4f} {y:.4f} {z:.4f}")
        for i, j, letter in self.bonds:
            lines.append(f"{i:4d} {j:4d} {letter}")
        return "\n".join(lines) + "\n"

    def neighbours(self, atom: int) -> list[int]:
        return [j if i == atom else i for i, j, _ in self.bonds
                if atom in (i, j)]


@dataclass(frozen=True)
class Trimer:
    """One mu3-oxide and its three metals, in a block's numbering."""

    oxide: int
    metals: tuple[int, int, int]


def trimers(block: Block) -> list[Trimer]:
    """Every M3O core in ``block``.

    A mu3-oxide is an oxygen bonded to exactly three atoms of
    :data:`~xtal.mof.attach.DATIVE_MN`'s metals and nothing else.  The
    bond list is read rather than distances, because a block's bonds
    are what it says it is.
    """
    out = []
    for o, symbol in enumerate(block.symbols):
        if symbol != "O":
            continue
        around = block.neighbours(o)
        metals = [m for m in around if block.symbols[m] in DATIVE_MN]
        if len(metals) == 3 and len(around) == 3:
            out.append(Trimer(o, tuple(sorted(metals))))
    return out


def open_site(block: Block, trimer: Trimer, metal: int) -> np.ndarray:
    """The unit direction of a metal's open sixth corner."""
    axis = block.positions[metal] - block.positions[trimer.oxide]
    return axis / np.linalg.norm(axis)


def filled_by(block: Block, trimer: Trimer, metal: int) -> int | None:
    """The atom already on a metal's open site, or ``None``.

    Any non-``X`` neighbour within 30 degrees of the open-site line --
    a terminal water, a fluoride -- whether the bond list names it or it
    merely sits there.
    """
    axis = open_site(block, trimer, metal)
    here = block.positions[metal]
    near = set(block.neighbours(metal))
    for j, symbol in enumerate(block.symbols):
        if j in (metal, trimer.oxide) or symbol == "X":
            continue
        bond = block.positions[j] - here
        length = float(np.linalg.norm(bond))
        if j not in near and length > _BONDED:
            continue
        if bond @ axis / length >= _ON_AXIS:
            return j
    return None


def with_axial_points(block: Block, *, strip: bool = False) -> Block:
    """``block`` with a connection point on each open metal site.

    Refused when ``block`` holds no M3O core, or when a site is already
    taken -- a terminal water is part of what the block says the
    cluster is, and dropping it silently would build the framework with
    a ligand the user chose taken away.  ``strip=True`` is how to ask
    for it to go: the terminal atom and anything bonded only through it
    (its hydrogens) are removed first.
    """
    found = trimers(block)
    if not found:
        raise TrimerError("this block has no M3O trimer: no oxygen is "
                          "bonded to three metals and nothing else")
    if len(found) > 1:
        raise TrimerError(f"this block has {len(found)} M3O cores; a "
                          f"trimer node has one")
    trimer = found[0]
    short = {m: n for m in trimer.metals
             if (n := _coordination(block, m)) < OPEN_OCTAHEDRON}
    if short:
        # N422, N554 and N590 are Zn3O cores with tetrahedral zinc:
        # nothing is opposite the oxide because there is no octahedron
        # to have a sixth corner, and a pyridyl there would make the
        # zinc five-coordinate rather than fill a site.
        names = ", ".join(f"{block.symbols[m]}{m} is {n}-coordinate"
                          for m, n in short.items())
        raise TrimerError(f"no open octahedral site: {names}, where an "
                          f"open site needs {OPEN_OCTAHEDRON} (the "
                          f"oxide and four carboxylate oxygens)")
    taken = {m: filled_by(block, trimer, m) for m in trimer.metals}
    framework = {m: a for m, a in taken.items()
                 if a is not None and not _terminal(block, a, m)}
    if framework:
        # N86 and N179 are Co3O cores whose own carboxylates lean onto
        # the line opposite the oxide: there is no open site to give,
        # and stripping would cut the cluster.
        names = ", ".join(f"{block.symbols[m]}{m} by "
                          f"{block.symbols[a]}{a}"
                          for m, a in framework.items())
        raise TrimerError(f"no open site: the cluster's own atoms sit "
                          f"opposite the oxide ({names})")
    if any(v is not None for v in taken.values()):
        if not strip:
            names = ", ".join(
                f"{block.symbols[m]}{m} by {block.symbols[a]}{a}"
                for m, a in taken.items() if a is not None)
            raise TrimerError(f"open sites already filled ({names}); "
                              f"strip them to make the points")
        block = _without(block, {a for a in taken.values()
                                 if a is not None})
        trimer = trimers(block)[0]

    symbols = list(block.symbols)
    positions = [p for p in block.positions]
    bonds = list(block.bonds)
    connections = list(block.connections)
    for m in trimer.metals:
        point = dative_point(symbols[m], block.positions[m],
                             open_site(block, trimer, m))
        symbols.append("X")
        positions.append(point)
        bonds.append((m, len(symbols) - 1, "S"))
        connections.append(len(symbols) - 1)
    return Block(symbols, np.array(positions), bonds, connections)


def _coordination(block: Block, metal: int) -> int:
    """How many atoms coordinate ``metal``: bonded in the block, or an
    O or N within :data:`_BONDED` of it.  Either, because PORMAKE's
    bond lists are not complete -- N268's lists three of a cobalt's
    four carboxylate oxygens."""
    near = {j for j in block.neighbours(metal)
            if block.symbols[j] != "X"}
    here = block.positions[metal]
    near |= {j for j, symbol in enumerate(block.symbols)
             if symbol in ("O", "N") and j != metal
             and np.linalg.norm(block.positions[j] - here) < _BONDED}
    return len(near)


def _terminal(block: Block, atom: int, metal: int) -> bool:
    """Whether ``atom`` is a terminal ligand on ``metal``: bonded to
    nothing heavy besides it, as ``prepare._trimers`` judges a water
    or a fluoride."""
    return not [j for j in block.neighbours(atom)
                if j != metal and block.symbols[j] not in ("H", "D")]


def _without(block: Block, atoms: set[int]) -> Block:
    """``block`` less ``atoms`` and the hydrogens on them."""
    drop = set(atoms)
    for a in atoms:
        drop |= {j for j in block.neighbours(a)
                 if block.symbols[j] in ("H", "D")}
    keep = [i for i in range(len(block.symbols)) if i not in drop]
    place = {old: new for new, old in enumerate(keep)}
    return Block(
        [block.symbols[i] for i in keep],
        block.positions[keep],
        [(place[i], place[j], t) for i, j, t in block.bonds
         if i in place and j in place],
        [place[i] for i in block.connections if i in place])


def twin_name(name: str) -> str:
    """A trimer's nine-connected twin's name: ``N536`` -> ``N536-9c``."""
    return f"{name}-9c"


def write_twin(source, folder, *, strip: bool = False) -> Path:
    """Write the nine-connected twin of the block at ``source`` into
    ``folder``, named by :func:`twin_name`, and return its path."""
    source = Path(source)
    twin = with_axial_points(Block.read(source), strip=strip)
    out = Path(folder) / f"{twin_name(source.stem)}.xyz"
    out.parent.mkdir(parents=True, exist_ok=True)
    from xtal.io.atomic import write_text

    write_text(out, twin.text())
    return out
