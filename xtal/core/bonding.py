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
from xtal.core.structure import CHEMISTRY, Bond, CellBond

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


# ======================================================================
#  PERCEPTION
# ======================================================================

def perceive(structure, rules: BondRules | None = None,
             include_explicit: bool = True) -> list[CellBond]:
    """Bonds of the P1 cell: distance-based, plus the user's explicit
    additions, minus the ones they suppressed.

    The distance-based half comes from ``structure.perceived`` -- a
    stored graph, not a memo, so it survives a save and only changes
    when something asks it to.  Passing ``rules`` explicitly is a
    *query* ("what would these criteria give?") and neither reads that
    store nor writes to it, which is what lets the bond rules dialog
    show a preview without committing to it.
    """
    return _drawn(structure, rules, include_explicit).bonds


def graph(structure, rules: BondRules | None = None) -> BondGraph:
    """Bond graph of the P1 cell, memoised with the structure."""
    return _drawn(structure, rules, True).graph


class _Drawn:
    """One perception, and the graph over it, as the cell is wrapped
    *now*.

    Perception is memoised against everything but a geometry change, so
    the bonds it holds were worked out at some earlier arrangement of
    the atoms.  That is the intended behaviour and it is nearly always
    harmless -- except for one thing, which is what this class exists
    for.  ``CellBond.image`` counts lattice translations between
    *wrapped* positions, and an atom that drifts across a cell face is
    redrawn on the opposite side, which changes every image it appears
    in.  Left alone, its bonds are drawn stretching the whole way back
    across the crystal.

    So the wrap is carried with the bonds and checked on the way out.
    Nothing has crossed a face, which is the case on almost every
    frame, costs one array comparison; something has, and the images
    are moved onto the new wrap and the graph rebuilt over them.
    """

    def __init__(self, bonds, tau, n_atoms):
        self._base = bonds
        self._base_tau = tau
        self.bonds = bonds
        self.graph = BondGraph(n_atoms, bonds)
        self.n_atoms = n_atoms
        self._tau = tau

    def at(self, tau) -> _Drawn:
        if np.array_equal(self._tau, tau):
            return self
        self.bonds = rebase(self._base, self._base_tau, tau)
        self.graph = BondGraph(self.n_atoms, self.bonds)
        self._tau = tau
        return self


def _drawn(structure, rules, include_explicit) -> _Drawn:
    override = rules is not None
    rules = rules or BondRules.from_dict(structure.bond_rules)
    # The cache key describes the *rules*, not the object holding them:
    # the caller usually builds a fresh BondRules every call, so keying
    # on identity would miss every time and grow the cache without
    # bound.
    key = f"bonds:{include_explicit}:{rules.signature()}"

    def build():
        return _assemble(structure, rules, include_explicit,
                         store=not override)

    cell = p1.expand(structure)
    drawn = structure.cached(key, build, invalidated_by=CHEMISTRY)
    if drawn.n_atoms != cell.n_atoms:
        # A positions-only edit can still change how many atoms the
        # cell holds: moving an atom onto a special position merges its
        # orbit, and moving it off splits it again.  The perception is
        # then over a different set of atoms, and indices that no
        # longer name the same atom are worse than no perception at
        # all.
        structure.drop_cache("bonds:")
        drawn = structure.cached(key, build, invalidated_by=CHEMISTRY)
    return drawn.at(cell.tau)


def _assemble(structure, rules, include_explicit, store) -> _Drawn:
    cell = p1.expand(structure)
    if cell.n_atoms == 0:
        return _Drawn([], cell.tau, 0)

    found = {b.key(): b for b in _by_distance(structure, rules, cell,
                                              store)}
    if include_explicit:
        for bond in structure.bonds:
            for mapped in map_explicit_bond(structure, cell, bond):
                if bond.kind == "suppressed":
                    found.pop(mapped.key(), None)
                else:
                    found[mapped.key()] = mapped

    bonds = sorted(found.values(), key=lambda b: (b.i, b.j, b.image))
    return _Drawn(bonds, cell.tau, cell.n_atoms)


def _by_distance(structure, rules, cell, store: bool) -> list[CellBond]:
    """The distance-perceived half of the graph.

    The stored graph is the answer whenever it still describes this
    cell.  When atoms have been *appended* -- which is what adding one
    looks like, because the expansion is site-major -- only the new
    ones are perceived and everything already there is left exactly as
    it was; that is the whole point of storing it, and it is why adding
    a hydrogen no longer re-derives a framework's eight hundred bonds.
    Anything else about the cell having changed means the graph is
    describing a different crystal, and it goes.
    """
    stored = structure.perceived
    signature = rules.signature()
    if stored is not None and stored.signature == signature:
        if stored.elements == cell.elements:
            return rebase(stored.bonds, stored.tau, cell.tau)
        if _appended_to(stored.elements, cell.elements):
            kept = rebase(stored.bonds, stored.tau,
                          cell.tau[:stored.n_atoms])
            grown = kept + _search(rules, cell, structure.lattice,
                                   subset=range(stored.n_atoms,
                                                cell.n_atoms))
            if store:
                structure.set_perceived(grown, signature, cell)
            return grown

    fresh = _search(rules, cell, structure.lattice)
    if store:
        structure.set_perceived(fresh, signature, cell)
    return fresh


def _appended_to(before, after) -> bool:
    return (len(after) > len(before)
            and after[:len(before)] == tuple(before))


def _search(rules, cell, lattice, subset=None) -> list[CellBond]:
    """Distance perception over the cell, or over part of it."""
    cutoff = rules.max_cutoff(cell.elements)
    if cutoff <= 0:
        return []
    pairs = neighbors.neighbor_pairs(
        cell.frac, lattice, cutoff, min_distance=rules.min_distance,
        subset=subset)

    found: dict[tuple, CellBond] = {}
    for k in range(len(pairs)):
        i, j = int(pairs.i[k]), int(pairs.j[k])
        a, b = cell.elements[i], cell.elements[j]
        if not rules.allows(a, b):
            continue
        lo, hi = rules.cutoff(a, b)
        d = float(pairs.distance[k])
        if lo <= d <= hi:
            bond = CellBond(i, j,
                            tuple(int(v) for v in pairs.image[k]), d)
            found[bond.key()] = bond
    return sorted(found.values(), key=lambda b: (b.i, b.j, b.image))


def rebase(bonds, tau_then, tau_now) -> list[CellBond]:
    """The same bonds, with their images read against a new wrap.

    A bond joins the atom drawn at ``frac[i]`` to the point
    ``frac[j] + image``, and ``frac[k] = raw[k] + tau[k]``.  What the
    geometry actually fixes is the separation between the two, so

        image + tau[j] - tau[i]

    is the quantity that does not change while atoms move -- and the
    image to draw at any later wrap follows from it.  Getting this
    wrong is not subtle: the bond is drawn to the copy of its partner
    on the far side of the crystal.
    """
    tau_then = np.asarray(tau_then, dtype=int)
    tau_now = np.asarray(tau_now, dtype=int)
    if np.array_equal(tau_then, tau_now):
        return list(bonds)
    shift = tau_then - tau_now
    return [
        CellBond(b.i, b.j,
                 tuple(int(v) for v in
                       (np.asarray(b.image) + shift[b.j] - shift[b.i])),
                 b.distance, b.explicit)
        for b in bonds
    ]


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
