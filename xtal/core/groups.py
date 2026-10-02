"""
xtal.core.groups
================
Functional groups: every hydroxyl, every carboxylic acid, every C-F
on a sheet's edge -- found so they can be selected, shown alone and
changed together.

A **closed catalogue** of patterns over the stored bond graph
(:data:`CATALOGUE`), each an element with the neighbours it has.
RDKit is not used: it cannot take a periodic graph, and a group that
closes through a cell face (an epoxide on a sheet that crosses one)
is still a group.

**Chemistry is decided by connectivity, never by a bond's length.**
A refinement's C=O and C-OH are often within a few hundredths of an
angstrom of each other, so which oxygen of an acid is the hydroxyl is
the one with the hydrogen on it, and a carbonyl is an oxygen with one
neighbour.  A bond to a metal is dative and does not count against
an oxygen: a carboxylate on a zinc is still a carboxylate.

Each atom is claimed once, by the most specific pattern that covers
it -- an acid is one group, not a hydroxyl and a carbonyl, and an
ester's oxygen is not also an ether.  A dummy atom never matches: a
marker is not chemistry.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from xtal.core import bonding, elements, p1
from xtal.core.structure import CHEMISTRY

#: The largest ring an oxygen is looked for in, to call it a ring
#: ether or a lactone.  A pyran is six; a sheet's edge is not a ring.
RING_SEARCH = 8

#: Elements a bond to which is chemistry rather than coordination.
_NONMETALS = frozenset({"H", "D", "B", "C", "N", "O", "F", "Si", "P",
                        "S", "Cl", "Se", "Br", "I", "As", "Te"})
_HYDROGENS = frozenset({"H", "D"})


@dataclass(frozen=True)
class Kind:
    """One pattern of the catalogue."""

    name: str                           # key, as a script names it
    label: str                          # as a person reads it
    #: What the handle is -- the atom a person changes the group by.
    handle: str


#: Every group found, in the order a list of them is shown: the
#: oxygen groups a carbon's edge carries first, as a ZTC's are.
CATALOGUE = (
    Kind("phenol", "Hydroxyl (phenol)", "the hydrogen"),
    Kind("alcohol", "Hydroxyl (alcohol)", "the hydrogen"),
    Kind("carboxylic_acid", "Carboxylic acid", "the hydrogen"),
    Kind("carboxylate", "Carboxylate", "the two oxygens"),
    Kind("ketone", "Carbonyl (ketone, quinone)", "the oxygen"),
    Kind("aldehyde", "Aldehyde", "the hydrogen"),
    Kind("ether", "Ether", "the oxygen"),
    Kind("ring_ether", "Ring ether", "the oxygen"),
    Kind("epoxide", "Epoxide", "the oxygen"),
    Kind("ester", "Ester", "the ether oxygen"),
    Kind("lactone", "Lactone", "the ring oxygen"),
    Kind("anhydride", "Anhydride", "the bridging oxygen"),
    Kind("amide", "Amide", "the hydrogens on nitrogen"),
    Kind("amine", "Amine (primary, secondary)",
         "the hydrogens on nitrogen"),
    Kind("fluoride", "C-F", "the fluorine"),
)

KINDS = {kind.name: kind for kind in CATALOGUE}

#: The parts of a group a selection can take.
PARTS = ("whole", "handle")


@dataclass(frozen=True)
class Match:
    """One group: every atom of it, and the ones it is changed by.

    Atoms are P1 atoms.  The group's carbon -- the one an acid hangs
    off, not the one a ketone *is* -- is not in ``atoms`` unless the
    group is centred on it.
    """

    name: str
    atoms: tuple[int, ...]
    handle: tuple[int, ...]


def detect(cell, graph) -> dict[str, list[Match]]:
    """Every group of the catalogue in a P1 cell and its graph, by
    name, each list in atom order.  Names nothing found are absent."""
    return _Finder(cell, graph).run()


def matches(structure, rules=None) -> dict[str, list[Match]]:
    """:func:`detect` over ``structure``'s P1 cell and stored graph,
    memoised until the chemistry changes."""
    key = f"groups:{rules.signature() if rules else ''}"

    def build():
        cell = p1.expand(structure)
        return cell.n_atoms, detect(cell, bonding.graph(structure,
                                                        rules))

    n_atoms, found = structure.cached(key, build,
                                      invalidated_by=CHEMISTRY)
    if n_atoms != p1.expand(structure).n_atoms:
        # See :func:`xtal.core.rings.rings_of`.
        structure.drop_cache(key)
        _n, found = structure.cached(key, build,
                                     invalidated_by=CHEMISTRY)
    return found


def find(structure, name: str, rules=None) -> list[Match]:
    """Every group called ``name`` (a key of :data:`KINDS`)."""
    if name not in KINDS:
        raise ValueError(f"unknown group {name!r}; one of "
                         f"{', '.join(KINDS)}")
    return list(matches(structure, rules).get(name, ()))


def census(structure, rules=None) -> dict[str, int]:
    """How many of each group, in catalogue order, the absent left
    out."""
    found = matches(structure, rules)
    return {kind.name: len(found[kind.name]) for kind in CATALOGUE
            if found.get(kind.name)}


def atoms_of(found, name: str, part: str = "whole") -> set[int]:
    """The atoms a selection of ``part`` of every ``name`` takes."""
    if part not in PARTS:
        raise ValueError(f"unknown part {part!r}; one of "
                         f"{', '.join(PARTS)}")
    out: set[int] = set()
    for match in found.get(name, ()):
        out.update(match.atoms if part == "whole" else match.handle)
    return out


class _Finder:
    """One pass of the catalogue over a cell."""

    def __init__(self, cell, graph):
        self.symbols = list(cell.elements)
        real = [not elements.is_dummy(s) for s in self.symbols]
        # Bonds to metals left out: they are coordination, and an
        # oxygen on a zinc is still a carbonyl's oxygen to count.
        self.adjacency = [
            [(int(j), tuple(int(v) for v in t))
             for j, t in graph.neighbors_with_images(i)
             if real[j] and self.symbols[j] in _NONMETALS]
            if real[i] else []
            for i in range(cell.n_atoms)]
        self.claimed: set[int] = set()
        self.found: dict[str, list[Match]] = {}

    def element(self, i) -> str:
        return "H" if self.symbols[i] in _HYDROGENS else self.symbols[i]

    def partners(self, i) -> list[int]:
        return [j for j, _t in self.adjacency[i]]

    def of(self, i, symbol) -> list[int]:
        return [j for j in self.partners(i)
                if self.element(j) == symbol]

    def terminal_oxygen(self, o) -> bool:
        """An oxygen on one carbon and nothing else: a C=O."""
        return (self.element(o) == "O" and len(self.adjacency[o]) == 1
                and self.element(self.adjacency[o][0][0]) == "C")

    def hydroxy_oxygen(self, o) -> bool:
        partners = sorted(self.element(j) for j in self.partners(o))
        return self.element(o) == "O" and partners == ["C", "H"]

    def bridging_oxygen(self, o) -> bool:
        partners = [self.element(j) for j in self.partners(o)]
        return self.element(o) == "O" and partners == ["C", "C"]

    def carbonyl(self, c) -> list[int]:
        """The C=O oxygens on carbon ``c``."""
        if self.element(c) != "C":
            return []
        return [o for o in self.partners(c) if self.terminal_oxygen(o)]

    def add(self, name, atoms, handle) -> None:
        atoms = tuple(sorted(set(atoms)))
        self.found.setdefault(name, []).append(
            Match(name, atoms, tuple(sorted(set(handle)))))
        self.claimed.update(atoms)

    def run(self) -> dict[str, list[Match]]:
        n = len(self.symbols)
        for c in range(n):
            self.carbonyl_group(c)
        for o in range(n):
            self.oxygen_group(o)
        for x in range(n):
            self.nitrogen_group(x)
            self.fluorine(x)
        return {name: sorted(found, key=lambda m: m.atoms)
                for name, found in self.found.items()}

    # -- the patterns --------------------------------------------------

    def carbonyl_group(self, c) -> None:
        """Every group with a C=O in it, centred on its carbon."""
        terminal = self.carbonyl(c)
        if not terminal or c in self.claimed:
            return
        if len(terminal) >= 2:
            self.add("carboxylate", [c, *terminal[:2]], terminal[:2])
            return
        double = terminal[0]
        hydroxy = [o for o in self.of(c, "O") if self.hydroxy_oxygen(o)]
        if hydroxy:
            o = hydroxy[0]
            h = self.of(o, "H")
            self.add("carboxylic_acid", [c, double, o, *h], h)
            return
        for o in self.of(c, "O"):
            if not self.bridging_oxygen(o) or o in self.claimed:
                continue
            other = next(j for j in self.partners(o) if j != c)
            far = self.carbonyl(other)
            if far and other not in self.claimed:
                self.add("anhydride", [c, double, o, other, far[0]],
                         [o])
            else:
                self.add("lactone" if self.in_ring(o) else "ester",
                         [c, double, o], [o])
            return
        nitrogens = self.of(c, "N")
        if nitrogens:
            n = nitrogens[0]
            h = self.of(n, "H")
            self.add("amide", [c, double, n, *h], h or [n])
            return
        hydrogens = self.of(c, "H")
        if hydrogens:
            self.add("aldehyde", [c, double, hydrogens[0]],
                     [hydrogens[0]])
            return
        if len(self.of(c, "C")) == 2:
            self.add("ketone", [c, double], [double])

    def oxygen_group(self, o) -> None:
        if o in self.claimed:
            return
        if self.hydroxy_oxygen(o):
            c = self.of(o, "C")[0]
            h = self.of(o, "H")
            name = "phenol" if len(self.adjacency[c]) == 3 else "alcohol"
            self.add(name, [o, *h], h)
            return
        if not self.bridging_oxygen(o):
            return
        (a, ta), (b, tb) = self.adjacency[o]
        if self.carbonyl(a) or self.carbonyl(b):
            return
        step = tuple(y - x for x, y in zip(ta, tb, strict=True))
        if (b, step) in self.adjacency[a]:
            self.add("epoxide", [o, a, b], [o])
        elif self.in_ring(o):
            self.add("ring_ether", [o], [o])
        else:
            self.add("ether", [o], [o])

    def nitrogen_group(self, x) -> None:
        if self.element(x) != "N" or x in self.claimed:
            return
        partners = self.partners(x)
        if len(partners) != 3:
            return
        if any(self.element(j) not in ("C", "H") for j in partners):
            return
        if any(self.carbonyl(j) for j in partners):
            return
        h = self.of(x, "H")
        if h and len(h) < 3:
            self.add("amine", [x, *h], h)

    def fluorine(self, f) -> None:
        if self.element(f) != "F" or len(self.adjacency[f]) != 1:
            return
        c = self.adjacency[f][0][0]
        if self.element(c) == "C":
            self.add("fluoride", [f], [f])

    def in_ring(self, o) -> bool:
        """Whether bridging oxygen ``o`` closes a ring of at most
        :data:`RING_SEARCH` atoms -- a path between its two partners
        that does not go through it and arrives with no net
        translation, so the ring may close through a cell face."""
        (a, ta), (b, tb) = self.adjacency[o]
        start, goal = (a, ta), (b, tb)
        seen = {start: 0}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            depth = seen[node]
            if depth >= RING_SEARCH - 2:
                continue
            atom, shift = node
            for j, t in self.adjacency[atom]:
                if j == o:
                    continue
                nxt = (j, tuple(x + y for x, y in zip(shift, t,
                                                       strict=True)))
                if nxt == goal:
                    return True
                if nxt not in seen:
                    seen[nxt] = depth + 1
                    queue.append(nxt)
        return False
