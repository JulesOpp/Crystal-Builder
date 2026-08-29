"""
xtal.core.bonding
=================
Where bonds come from: distance-based perception, the user's explicit
overrides, and the connectivity graph built from both.

Perception happens in the P1 cell (what is drawn), while the user's
explicit bonds are stored against the asymmetric unit (what is saved).
Mapping between the two is this module's job: an explicitly drawn bond
propagates to every symmetry image of the atoms it joins, exactly as it
does in VESTA -- draw one Fe-O bond and the whole orbit gets it.

Fragment detection is periodicity-aware.  Walking the graph while
accumulating lattice translations tells a molecule (returns to the
start with a zero shift) apart from a framework (returns with a
non-zero shift, so the fragment is infinite).  Anything that asks
"select this molecule" needs that distinction or it will happily try to
select an infinite crystal one atom at a time.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from xtal.core import elements as el
from xtal.core import neighbors, p1
from xtal.core.structure import Bond

# Two atoms bond when d <= (r_i + r_j) * SCALE + DELTA, with covalent
# radii.  1.15 / 0.0 reproduces what VESTA and Mercury draw for common
# inorganic and organic structures.
DEFAULT_SCALE = 1.15
DEFAULT_DELTA = 0.0
MIN_BOND_DISTANCE = 0.4         # below this it is an overlap, not a bond


@dataclass
class BondRules:
    """Criteria for automatic bond perception."""

    scale: float = DEFAULT_SCALE
    delta: float = DEFAULT_DELTA
    min_distance: float = MIN_BOND_DISTANCE
    # (A, B) -> (dmin, dmax); element order does not matter
    pair_ranges: dict = field(default_factory=dict)
    # pairs that never bond, e.g. {("O", "O")}
    forbidden: set = field(default_factory=set)
    allow_metal_metal: bool = False

    def cutoff(self, a: str, b: str) -> tuple[float, float]:
        """(dmin, dmax) for a pair of elements."""
        key = tuple(sorted((a, b)))
        if key in self.pair_ranges:
            lo, hi = self.pair_ranges[key]
            return float(lo), float(hi)
        radii = el.covalent_radius(a) + el.covalent_radius(b)
        return self.min_distance, radii * self.scale + self.delta

    def allows(self, a: str, b: str) -> bool:
        if tuple(sorted((a, b))) in {tuple(sorted(p))
                                     for p in self.forbidden}:
            return False
        if not self.allow_metal_metal:
            if el.element(a).is_metal and el.element(b).is_metal:
                return False
        return True

    def max_cutoff(self, symbols) -> float:
        """Search radius that cannot miss a bond between these
        elements."""
        uniq = sorted(set(symbols))
        if not uniq:
            return 0.0
        widest = max(self.cutoff(a, b)[1]
                     for i, a in enumerate(uniq) for b in uniq[i:])
        for _lo, hi in self.pair_ranges.values():
            widest = max(widest, float(hi))
        return widest

    def to_dict(self) -> dict:
        return {
            "scale": self.scale, "delta": self.delta,
            "min_distance": self.min_distance,
            "pair_ranges": {f"{a}-{b}": list(v)
                            for (a, b), v in self.pair_ranges.items()},
            "forbidden": sorted(f"{a}-{b}" for a, b in self.forbidden),
            "allow_metal_metal": self.allow_metal_metal,
        }

    @classmethod
    def from_dict(cls, d: dict) -> BondRules:
        if not d:
            return cls()
        pairs = {tuple(k.split("-")): tuple(v)
                 for k, v in d.get("pair_ranges", {}).items()}
        forbid = {tuple(s.split("-")) for s in d.get("forbidden", [])}
        return cls(
            scale=d.get("scale", DEFAULT_SCALE),
            delta=d.get("delta", DEFAULT_DELTA),
            min_distance=d.get("min_distance", MIN_BOND_DISTANCE),
            pair_ranges=pairs, forbidden=forbid,
            allow_metal_metal=d.get("allow_metal_metal", False),
        )


@dataclass(frozen=True)
class CellBond:
    """A bond between two atoms of the P1 cell."""

    i: int
    j: int
    image: tuple[int, int, int]
    distance: float
    explicit: bool = False

    def key(self) -> tuple:
        if (self.j, self.image) < (self.i, tuple(-v for v in self.image)):
            return (self.j, self.i, tuple(-v for v in self.image))
        return (self.i, self.j, self.image)


# ======================================================================
#  PERCEPTION
# ======================================================================

def perceive(structure, rules: BondRules | None = None,
             include_explicit: bool = True) -> list[CellBond]:
    """Bonds of the P1 cell: distance-based, plus the user's explicit
    additions, minus the ones they suppressed.

    Memoised on the structure until its next mutation.
    """
    rules = rules or BondRules.from_dict(structure.bond_rules)
    key = f"bonds:{include_explicit}:{id(rules) if rules else 0}"
    return structure.cached(
        key, lambda: _perceive_uncached(structure, rules,
                                        include_explicit))


def _perceive_uncached(structure, rules, include_explicit):
    cell = p1.expand(structure)
    if cell.n_atoms == 0:
        return []

    cutoff = rules.max_cutoff(cell.elements)
    found: dict[tuple, CellBond] = {}
    if cutoff > 0:
        pairs = neighbors.neighbor_pairs(
            cell.frac, structure.lattice, cutoff,
            min_distance=rules.min_distance)
        for k in range(len(pairs)):
            i, j = int(pairs.i[k]), int(pairs.j[k])
            a, b = cell.elements[i], cell.elements[j]
            if not rules.allows(a, b):
                continue
            lo, hi = rules.cutoff(a, b)
            d = float(pairs.distance[k])
            if lo <= d <= hi:
                bond = CellBond(i, j, tuple(int(v) for v in
                                            pairs.image[k]), d)
                found[bond.key()] = bond

    if include_explicit:
        for bond in structure.bonds:
            for mapped in map_explicit_bond(structure, cell, bond):
                if bond.kind == "suppressed":
                    found.pop(mapped.key(), None)
                else:
                    found[mapped.key()] = mapped

    return sorted(found.values(), key=lambda b: (b.i, b.j, b.image))


def map_explicit_bond(structure, cell: p1.P1Cell,
                      bond: Bond) -> list[CellBond]:
    """Expand one asymmetric-unit bond into the P1 cell.

    For every image of site ``i`` produced by operation k, the partner
    is the same operation applied to ``j`` shifted by the bond's stored
    lattice translation -- which is how a hand-drawn bond ends up on
    every symmetry-equivalent pair.
    """
    ops = structure.space_group.operations
    lattice = structure.lattice
    partner_frac = structure.sites[bond.j].frac + np.array(bond.image)
    out = []
    for a in cell.indices_of_site(bond.i):
        op = ops[int(cell.op_idx[a])]
        target = op.apply(partner_frac) + cell.tau[a]
        wrapped = p1._wrap(target)
        shift = np.round(target - wrapped).astype(int)
        b = _find_atom(cell, wrapped, lattice)
        if b is None:
            continue
        out.append(CellBond(
            int(a), int(b), tuple(int(v) for v in -shift),
            neighbors.min_image_distance(cell.frac[a], target, lattice),
            explicit=True))
    return out


def _find_atom(cell, frac, lattice, tol=1e-3):
    d = cell.frac - frac
    d -= np.round(d)
    dist = np.linalg.norm(d @ lattice.matrix, axis=1)
    hit = np.flatnonzero(dist < tol)
    return int(hit[0]) if len(hit) else None


# ======================================================================
#  GRAPH
# ======================================================================

class BondGraph:
    """Adjacency over the P1 cell, with periodic bookkeeping."""

    def __init__(self, n_atoms: int, bonds: list[CellBond]):
        self.n_atoms = n_atoms
        self.bonds = list(bonds)
        self._adj: list[list[tuple[int, np.ndarray, int]]] = [
            [] for _ in range(n_atoms)]
        for k, b in enumerate(self.bonds):
            t = np.array(b.image, dtype=int)
            self._adj[b.i].append((b.j, t, k))
            self._adj[b.j].append((b.i, -t, k))

    def neighbors(self, i: int) -> list[int]:
        return [j for j, _t, _k in self._adj[i]]

    def coordination(self) -> np.ndarray:
        return np.array([len(self._adj[i]) for i in range(self.n_atoms)])

    def bonds_of(self, i: int) -> list[CellBond]:
        return [self.bonds[k] for _j, _t, k in self._adj[i]]

    def fragments(self) -> list[Fragment]:
        """Connected components, each flagged as molecular or
        periodic (a framework, chain or sheet that never closes)."""
        seen = np.zeros(self.n_atoms, dtype=bool)
        out = []
        for start in range(self.n_atoms):
            if seen[start]:
                continue
            members: list[int] = []
            offsets = {start: np.zeros(3, dtype=int)}
            periodic = False
            queue = deque([start])
            seen[start] = True
            while queue:
                a = queue.popleft()
                members.append(a)
                for b, t, _k in self._adj[a]:
                    shifted = offsets[a] + t
                    if b in offsets:
                        if not np.array_equal(offsets[b], shifted):
                            periodic = True     # closes onto an image
                        continue
                    offsets[b] = shifted
                    seen[b] = True
                    queue.append(b)
            out.append(Fragment(tuple(sorted(members)), periodic,
                                {a: tuple(offsets[a]) for a in members}))
        return out

    def fragment_containing(self, atom: int) -> Fragment:
        for frag in self.fragments():
            if atom in frag.atoms:
                return frag
        raise IndexError(f"atom {atom} is not in the graph")

    def shell(self, seeds, depth: int = 1) -> set[int]:
        """Atoms within ``depth`` bonds of any seed (seeds included)."""
        out = set(int(s) for s in seeds)
        frontier = set(out)
        for _ in range(max(0, depth)):
            nxt = {j for a in frontier for j in self.neighbors(a)}
            nxt -= out
            if not nxt:
                break
            out |= nxt
            frontier = nxt
        return out


@dataclass(frozen=True)
class Fragment:
    """A connected component of the bond graph."""

    atoms: tuple[int, ...]
    periodic: bool                      # infinite: a framework, not a
    offsets: dict                       #   molecule
    def __len__(self) -> int:
        return len(self.atoms)

    @property
    def kind(self) -> str:
        return "framework" if self.periodic else "molecule"


def graph(structure, rules: BondRules | None = None) -> BondGraph:
    """Bond graph of the P1 cell, memoised with the structure."""
    cell = p1.expand(structure)
    bonds = perceive(structure, rules)
    return structure.cached(
        "bondgraph", lambda: BondGraph(cell.n_atoms, bonds))
