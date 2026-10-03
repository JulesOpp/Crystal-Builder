"""
xtal.core.rings
===============
The rings of a structure -- the faces a carbon framework is made of.

:func:`bonding.find_rings` returns every simple cycle up to a size,
and in a fused sheet most of those are not rings anybody would draw:
two hexagons sharing an edge are also a ten-membered cycle round the
outside of both.  On graphene that is 1728 ten-cycles for 576
hexagons, and on a zeolite-templated carbon of 2268 carbons 497 of
them where 37 survive.  So what this module hands out is the
**primitive** (shortest-path) rings of Franzblau: a cycle is kept only
if no two of its atoms are closer through the graph than they are
round the ring.  A composite has a shortcut -- the bond the two
hexagons share -- and a real ring does not.

Rings are read off the stored bond graph, never perceived, and a
dummy atom is never in one: a marker is not chemistry.
"""

from __future__ import annotations

from collections import Counter, deque

import numpy as np

from xtal.core import bonding, elements, p1
from xtal.core.structure import CHEMISTRY

#: The largest ring looked for unless asked otherwise.  Five-, six-,
#: seven- and eight-membered rings are what a curved carbon sheet is
#: made of, and the search is 0.08 s on 3188 atoms at eight against
#: 0.29 s at ten.
DEFAULT_MAX_SIZE = 8

#: Above this the search is a walk over every path of that length,
#: which on a dense framework is minutes rather than seconds.
LARGEST = 12


def primitive(cell, graph, max_size: int = DEFAULT_MAX_SIZE) -> list:
    """Shortest-path rings of at most ``max_size`` atoms.

    Each comes back as ``(atom, lattice shift)`` pairs in ring order,
    as :func:`bonding.find_rings` gives them, so a ring closing
    through a cell face can still be laid out in space.
    """
    max_size = max(3, min(int(max_size), LARGEST))
    candidates = {i for i in range(cell.n_atoms)
                  if not elements.is_dummy(cell.elements[i])}
    adjacency = {
        i: [(int(j), tuple(t.tolist()))
            for j, t, _k in graph._adj[i] if j in candidates]
        for i in candidates}
    reach: dict[int, dict] = {}
    depth = max_size // 2
    return [ring for ring in _cycles(adjacency, max_size)
            if _is_primitive(ring, adjacency, reach, depth)]


def _cycles(adjacency, max_size) -> list:
    """Every simple cycle of at most ``max_size`` atoms that closes
    with no net translation, once.

    :func:`bonding.find_rings`, except that a walk may pass through
    another copy of the atom it started from.  In a cell smaller than
    the ring that is the only way round it -- graphene's two-atom cell
    has one hexagon holding three copies of each atom -- and
    ``find_rings`` refusing it is why that cell had no rings.  The
    price is that one ring is then found from each copy of its lowest
    atom, so the copies are told apart by moving each ring home
    (:func:`_translated_home`).
    """
    rings: list = []
    seen: set = set()
    for start in sorted(adjacency):
        origin = (start, (0, 0, 0))
        stack = [[origin]]
        while stack:
            path = stack.pop()
            node, (a, b, c) = path[-1]
            if len(path) > max_size:
                continue
            for j, (x, y, z) in adjacency[node]:
                if j < start:
                    continue
                nxt = (j, (a + x, b + y, c + z))
                if nxt == origin:
                    if len(path) >= 3:
                        key = _translated_home(path)
                        if key not in seen:
                            seen.add(key)
                            rings.append(list(path))
                    continue
                if nxt in path:
                    continue
                stack.append([*path, nxt])
    return rings


def _translated_home(ring) -> frozenset:
    """``ring`` moved so its least ``(atom, shift)`` is in the home
    cell -- the same for every translate of one ring."""
    _atom, (a, b, c) = min(ring)
    return frozenset((atom, (x - a, y - b, z - c))
                     for atom, (x, y, z) in ring)


def _is_primitive(ring, adjacency, reach, depth) -> bool:
    """No two atoms of ``ring`` closer through the graph than round
    it."""
    n = len(ring)
    for k, (atom, (a, b, c)) in enumerate(ring):
        near = reach.get(atom)
        if near is None:
            near = reach[atom] = _distances(atom, adjacency, depth)
        for m in range(k + 2, n):
            around = min(m - k, n - (m - k))
            if around < 2:
                continue
            other, (x, y, z) = ring[m]
            through = near.get((other, (x - a, y - b, z - c)))
            if through is not None and through < around:
                return False
    return True


def _distances(start, adjacency, depth) -> dict:
    """Graph distance from ``start`` (in the home cell) to every
    ``(atom, shift)`` within ``depth`` bonds.

    One search per atom, shared by every ring through it: a carbon in
    a sheet is in three rings, and searching from it three times was
    most of the filter's time.
    """
    origin = (start, (0, 0, 0))
    seen = {origin: 0}
    queue = deque([origin])
    while queue:
        node = queue.popleft()
        d = seen[node]
        if d == depth:
            continue
        atom, (a, b, c) = node
        for j, (x, y, z) in adjacency[atom]:
            nxt = (j, (a + x, b + y, c + z))
            if nxt not in seen:
                seen[nxt] = d + 1
                queue.append(nxt)
    return seen


def rings_of(structure, rules=None,
             max_size: int = DEFAULT_MAX_SIZE) -> list:
    """:func:`primitive` over ``structure``'s P1 cell and stored graph,
    memoised until the chemistry changes.

    A drag moves atoms and keeps every ring, so a positions-only edit
    keeps the answer too -- read against the cell's wrap *now*, as
    :class:`_Found` says.
    """
    key = (f"primitive-rings:{int(max_size)}:"
           f"{rules.signature() if rules else ''}")

    def build():
        cell = p1.expand(structure)
        return _Found(primitive(cell, bonding.graph(structure, rules),
                                max_size), cell.tau)

    cell = p1.expand(structure)
    found = structure.cached(key, build, invalidated_by=CHEMISTRY)
    if len(found.tau) != cell.n_atoms:
        # The graph underneath was perceived over a cell of another
        # size -- see :func:`bonding.rings_of`.
        structure.drop_cache(key)
        found = structure.cached(key, build, invalidated_by=CHEMISTRY)
    return found.at(cell.tau)


class _Found:
    """The rings of one search, and the wrap they were found at.

    A ring's shifts count lattice translations between *wrapped*
    positions, so an atom an optimiser takes across a cell face is
    redrawn on the far side and every shift it appears in changes.
    Left as found, the ring's face was drawn to that atom's copy
    across the crystal and spanned the whole cell -- the fault
    :class:`bonding._Drawn` mends for the bonds, mended the same way.
    """

    def __init__(self, rings, tau):
        self._base = rings
        self._base_tau = np.asarray(tau, dtype=int)
        self.tau = self._base_tau
        self.rings = rings

    def at(self, tau) -> list:
        tau = np.asarray(tau, dtype=int)
        if np.array_equal(self.tau, tau):
            return self.rings
        # frac + shift is what the geometry fixes, so a member's shift
        # moves by what its wrap moved; then the whole ring is put back
        # with its first atom in the home cell, as it was found.
        moved = self._base_tau - tau
        rings = []
        for ring in self._base:
            members = [(atom, tuple(int(v) for v in
                                    np.add(shift, moved[atom])))
                       for atom, shift in ring]
            a, b, c = members[0][1]
            rings.append([(atom, (x - a, y - b, z - c))
                          for atom, (x, y, z) in members])
        self.tau, self.rings = tau, rings
        return rings


def census(structure, rules=None,
           max_size: int = DEFAULT_MAX_SIZE) -> dict[int, int]:
    """How many primitive rings of each size, smallest first."""
    counts = Counter(len(r) for r in rings_of(structure, rules,
                                              max_size))
    return dict(sorted(counts.items()))
