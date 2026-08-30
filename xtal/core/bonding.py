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
from xtal.core.structure import CHEMISTRY, Bond

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

    def signature(self) -> str:
        """A stable string identifying these criteria.

        Two BondRules that would perceive the same bonds share a
        signature, which is what lets perception be memoised across
        callers that each build their own rules object.
        """
        pairs = sorted((tuple(sorted(k)), tuple(v))
                       for k, v in self.pair_ranges.items())
        forbidden = sorted(tuple(sorted(p)) for p in self.forbidden)
        return (f"{self.scale!r}|{self.delta!r}|{self.min_distance!r}|"
                f"{pairs!r}|{forbidden!r}|{self.allow_metal_metal!r}")

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
    # The cache key describes the *rules*, not the object holding them:
    # the caller usually builds a fresh BondRules every call, so keying
    # on identity would miss every time and grow the cache without
    # bound.
    key = f"bonds:{include_explicit}:{rules.signature()}"
    return structure.cached(
        key, lambda: _perceive_uncached(structure, rules,
                                        include_explicit),
        invalidated_by=CHEMISTRY)


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

    A stored bond is a *pair of points* -- site ``i``, and the image of
    site ``j`` that ``op`` and ``image`` name.  What gets expanded is
    that pair: every operation of the group is applied to both ends at
    once, which is how a bond drawn on one Fe-O ends up on all six.

    Every operation is tried, not every distinct atom.  A site on a
    special position is reached by several operations, and each of them
    carries the partner somewhere different -- iterating over atoms
    instead would draw one bond per central atom where the symmetry
    demands several.
    """
    ops = structure.space_group.operations
    lattice = structure.lattice
    near = structure.sites[bond.i].frac
    far = (ops[bond.op].apply(structure.sites[bond.j].frac)
           + np.array(bond.image, dtype=float))

    out: dict[tuple, CellBond] = {}
    for op in ops:
        here = op.apply(near)
        wrapped_here = p1._wrap(here)
        tau = wrapped_here - here               # into the cell
        a = _find_atom(cell, wrapped_here, lattice)
        if a is None:                           # pragma: no cover
            continue
        there = op.apply(far) + tau
        wrapped_there = p1._wrap(there)
        b = _find_atom(cell, wrapped_there, lattice)
        if b is None:                           # pragma: no cover
            continue
        # ``there`` is where the partner really is; the atom found for
        # it lives inside the cell, so the bond carries the translation
        # between the two.  Getting this sign wrong draws the bond to
        # the copy on the opposite side -- or, more often, to a partner
        # that is not in the picture at all, so the bond vanishes.
        image = np.round(there - wrapped_there).astype(int)
        cell_bond = CellBond(
            int(a), int(b), tuple(int(v) for v in image),
            neighbors.min_image_distance(cell.frac[a], there, lattice),
            explicit=True)
        out[cell_bond.key()] = cell_bond
    return list(out.values())


def bond_between(structure, cell, atom_a: int, atom_b: int,
                 image_a=(0, 0, 0), image_b=(0, 0, 0)) -> Bond:
    """The asymmetric-unit bond whose expansion joins these two drawn
    atoms -- the inverse of :func:`map_explicit_bond`.

    Atom ``a`` is some image of site ``i``: ``a = op_a(site_i) + tau``.
    Undoing that operation carries atom ``b`` to a point ``q`` in site
    ``i``'s own frame, and the bond to store is the pair (site i, q).
    Because ``b`` is an image of site ``j``, ``q`` is one too, so there
    is always an operation and a lattice translation that name it --
    which is what makes *any* two atoms in the cell bondable.

    Requiring the identity there instead, as if the two ends had to be
    related by the same operation, refuses most of the bonds a
    crystallographer would draw: in Fm-3m it refuses all of them.

    ``image_a`` and ``image_b`` are the lattice translations the two
    atoms were *drawn* at.  A viewer showing more than one cell draws
    the same P1 atom many times, and bonding the copy at (1, 0, 0) is
    not the same bond as bonding the one at the origin -- passing the
    translations in is what stops a click landing on the wrong pair.
    """
    ops = structure.space_group.operations
    site_i = int(cell.site_idx[atom_a])
    site_j = int(cell.site_idx[atom_b])
    op_a = ops[int(cell.op_idx[atom_a])]
    tau_a = cell.tau[atom_a] + np.asarray(image_a, dtype=float)
    target = cell.frac[atom_b] + np.asarray(image_b, dtype=float)

    # Atom b, seen from site i's own frame: undo op_a.
    q = np.linalg.inv(op_a.rot) @ (target - tau_a - op_a.trans)

    frac_j = structure.sites[site_j].frac
    for k, op in enumerate(ops):
        shift = q - op.apply(frac_j)
        if np.allclose(shift, np.round(shift), atol=1e-6):
            return Bond(site_i, site_j,
                        tuple(int(v) for v in np.round(shift)), op=k)
    raise ValueError(                           # pragma: no cover
        "these two atoms are not in orbits of the same space group; "
        "reduce the structure to P1 to bond them")


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

    def neighbors_with_images(self, i: int) -> list[tuple]:
        """``(j, translation)`` for every neighbour of atom ``i``.

        The translation is what makes a coordination sphere drawable:
        four of an octahedron's six vertices are usually in the next
        cell along, and the neighbour index alone points at the copy
        inside the cell, which is somewhere else entirely.
        """
        return [(int(j), np.asarray(t, dtype=int))
                for j, t, _k in self._adj[i]]

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
        "bondgraph", lambda: BondGraph(cell.n_atoms, bonds),
        invalidated_by=CHEMISTRY)
