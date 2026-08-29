"""
xtal.core.structure
===================
``Structure`` -- the document's data model, and the only object the
Command layer ever mutates.

A Structure is **an asymmetric unit plus a space group**, not a list of
atoms in a box.  The full contents of the unit cell are *derived* from
it (``xtal.core.p1``), which is how VESTA and Materials Studio work and
what makes "set space group" and "reduce to P1" ordinary operations
rather than rewrites.  A structure in P1 is just the special case where
the asymmetric unit is the whole cell.

Everything expensive that can be computed from a Structure -- the P1
expansion, neighbour lists, the bond graph, scene arrays -- is computed
by free functions elsewhere and memoised here via :meth:`cached`, keyed
on ``revision``.  Any mutation bumps ``revision``, which invalidates
every cache at once and tells the GUI what kind of redraw it needs.

Structure is picklable and holds no references to Qt, VTK, or files.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import IntFlag

import numpy as np

from xtal.core.lattice import Lattice
from xtal.core.site import Site
from xtal.core.spacegroup import SpaceGroup

# ======================================================================
#  CHANGE HINTS
# ======================================================================

class Change(IntFlag):
    """What a mutation touched.  The viewport uses this to decide
    between "update one numpy array" and "rebuild the scene"."""

    NONE = 0
    POSITIONS = 1        # coordinates moved, nothing else
    TOPOLOGY = 2         # atoms or bonds added / removed / retyped
    CELL = 4             # lattice changed
    SYMMETRY = 8         # space group changed
    METADATA = 16        # labels, title, provenance
    ALL = POSITIONS | TOPOLOGY | CELL | SYMMETRY | METADATA


# ======================================================================
#  BOND
# ======================================================================

@dataclass(frozen=True)
class Bond:
    """An explicit bond between two asymmetric-unit sites.

    ``image`` is the lattice translation applied to site ``j``, so a
    bond that crosses a periodic boundary survives supercells and
    display-range changes.  Storing only (i, j) is the classic bug.

    ``kind`` is ``"explicit"`` for a bond the user drew, or
    ``"suppressed"`` for one they deleted that automatic perception
    would otherwise keep re-creating.
    """

    i: int
    j: int
    image: tuple[int, int, int] = (0, 0, 0)
    order: float = 1.0
    kind: str = "explicit"

    def __post_init__(self):
        object.__setattr__(self, "i", int(self.i))
        object.__setattr__(self, "j", int(self.j))
        object.__setattr__(self, "image",
                           tuple(int(v) for v in self.image))
        if len(self.image) != 3:
            raise ValueError("bond image must have 3 components")
        if self.i == self.j and self.image == (0, 0, 0):
            raise ValueError("a site cannot bond to itself in the same "
                             "periodic image")

    def canonical(self) -> Bond:
        """Direction-independent form, so (i,j,t) and (j,i,-t) -- the
        same physical bond -- compare and hash equal."""
        flip = (self.j, self.i) < (self.i, self.j) or (
            self.i == self.j and self.image < tuple(-v for v in self.image)
        )
        if not flip:
            return self
        return Bond(self.j, self.i, tuple(-v for v in self.image),
                    self.order, self.kind)

    def key(self) -> tuple:
        c = self.canonical()
        return (c.i, c.j, c.image)

    def involves(self, index: int) -> bool:
        return self.i == index or self.j == index

    def to_dict(self) -> dict:
        return {"i": self.i, "j": self.j, "image": list(self.image),
                "order": self.order, "kind": self.kind}

    @classmethod
    def from_dict(cls, d: dict) -> Bond:
        return cls(d["i"], d["j"], tuple(d.get("image", (0, 0, 0))),
                   d.get("order", 1.0), d.get("kind", "explicit"))


# ======================================================================
#  STRUCTURE
# ======================================================================

@dataclass
class Structure:
    """Lattice + asymmetric unit + space group + explicit bonds."""

    lattice: Lattice
    sites: list[Site] = field(default_factory=list)
    space_group: SpaceGroup = field(default_factory=SpaceGroup.p1)
    bonds: list[Bond] = field(default_factory=list)
    # Distance criteria for automatic bond perception.  The schema is
    # owned by xtal.core.bonding (phase 1); an empty dict means
    # "use the global defaults".
    bond_rules: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)

    revision: int = field(default=0, repr=False)
    last_change: Change = field(default=Change.NONE, repr=False)
    _cache: dict = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self):
        if not isinstance(self.lattice, Lattice):
            self.lattice = Lattice(self.lattice)
        self.space_group = SpaceGroup.from_any(self.space_group)
        self.sites = list(self.sites)
        self.bonds = list(self.bonds)
        for b in self.bonds:
            self._check_bond(b)

    # -- convenience constructors --------------------------------------

    @classmethod
    def empty(cls, lattice=None) -> Structure:
        """An empty P1 cell -- the starting point of File > New."""
        return cls(lattice or Lattice.cubic(10.0))

    @classmethod
    def from_arrays(cls, lattice, symbols, frac, space_group=None,
                    occupancies=None, labels=None) -> Structure:
        """Build from parallel arrays -- the shape most readers and
        external libraries hand us."""
        frac = np.asarray(frac, dtype=float).reshape(-1, 3)
        if len(symbols) != len(frac):
            raise ValueError(
                f"got {len(symbols)} symbols but {len(frac)} positions")
        occ = ([1.0] * len(frac) if occupancies is None
               else list(occupancies))
        lab = [""] * len(frac) if labels is None else list(labels)
        sites = [Site(s, f, occupancy=o, label=lb)
                 for s, f, o, lb in zip(symbols, frac, occ, lab, strict=False)]
        return cls(lattice, sites, SpaceGroup.from_any(space_group))

    # -- identity / size -----------------------------------------------

    def __len__(self) -> int:
        return len(self.sites)

    def __iter__(self):
        return iter(self.sites)

    def __getitem__(self, index) -> Site:
        return self.sites[index]

    @property
    def n_sites(self) -> int:
        """Sites in the ASYMMETRIC UNIT (not atoms in the cell)."""
        return len(self.sites)

    @property
    def elements(self) -> list[str]:
        """Distinct elements, in order of first appearance."""
        seen: dict[str, None] = {}
        for s in self.sites:
            seen.setdefault(s.element, None)
        return list(seen)

    @property
    def frac(self) -> np.ndarray:
        """(N,3) fractional coordinates of the asymmetric unit."""
        if not self.sites:
            return np.zeros((0, 3))
        return np.array([s.frac for s in self.sites])

    @property
    def cart(self) -> np.ndarray:
        return self.lattice.to_cart(self.frac)

    def composition(self) -> dict[str, float]:
        """Occupancy-weighted element counts of the asymmetric unit.

        This is NOT the cell contents -- multiplying by site
        multiplicity needs the symmetry expansion, which lives in
        ``xtal.core.properties`` (phase 1)."""
        c: Counter[str] = Counter()
        for s in self.sites:
            c[s.element] += s.occupancy
        return dict(c)

    @property
    def is_p1(self) -> bool:
        return self.space_group.is_p1

    # -- mutation ------------------------------------------------------
    #
    # Everything that changes a Structure funnels through touch(), so
    # caches invalidate and the GUI learns what to redraw.  Commands
    # call these; widgets call Commands.

    def touch(self, change: Change = Change.ALL) -> None:
        """Record a mutation: bump the revision, drop derived data."""
        self.revision += 1
        self.last_change = change
        self._cache.clear()

    def add_site(self, site: Site) -> int:
        """Append a site; returns its index."""
        self.sites.append(site)
        self.touch(Change.TOPOLOGY)
        return len(self.sites) - 1

    def add_sites(self, sites) -> list[int]:
        start = len(self.sites)
        self.sites.extend(sites)
        self.touch(Change.TOPOLOGY)
        return list(range(start, len(self.sites)))

    def remove_sites(self, indices) -> list[Site]:
        """Remove sites by index, dropping every bond that touched
        them and renumbering the survivors.  Returns what was removed,
        in the order given -- that is the undo data."""
        idx = sorted({int(i) for i in indices})
        if not idx:
            return []
        if idx[0] < 0 or idx[-1] >= len(self.sites):
            raise IndexError(f"site index out of range: {idx}")
        removed = [self.sites[i] for i in idx]
        drop = set(idx)
        shift = np.cumsum([1 if i in drop else 0
                           for i in range(len(self.sites))])
        self.sites = [s for i, s in enumerate(self.sites)
                      if i not in drop]
        self.bonds = [
            Bond(b.i - int(shift[b.i]), b.j - int(shift[b.j]),
                 b.image, b.order, b.kind)
            for b in self.bonds
            if b.i not in drop and b.j not in drop
        ]
        self.touch(Change.TOPOLOGY)
        return removed

    def set_frac(self, index: int, frac) -> None:
        self.sites[index].frac = np.asarray(frac, dtype=float).reshape(3)
        self.touch(Change.POSITIONS)

    def set_lattice(self, lattice: Lattice) -> None:
        self.lattice = lattice
        self.touch(Change.CELL)

    def set_space_group(self, sg) -> None:
        """Change the group *label* only.  Generating or reducing atoms
        is ``xtal.core.symmetry``'s job -- and the Command's."""
        self.space_group = SpaceGroup.from_any(sg)
        self.touch(Change.SYMMETRY)

    def add_bond(self, bond: Bond) -> bool:
        """Add a bond if it is not already there.  Returns whether it
        was added."""
        self._check_bond(bond)
        if any(b.key() == bond.key() for b in self.bonds):
            return False
        self.bonds.append(bond)
        self.touch(Change.TOPOLOGY)
        return True

    def remove_bond(self, bond: Bond) -> bool:
        key = bond.key()
        keep = [b for b in self.bonds if b.key() != key]
        if len(keep) == len(self.bonds):
            return False
        self.bonds = keep
        self.touch(Change.TOPOLOGY)
        return True

    def bonds_of(self, index: int) -> list[Bond]:
        return [b for b in self.bonds if b.involves(index)]

    def wrap_sites(self) -> None:
        """Fold every site into [0, 1)."""
        for s in self.sites:
            s.frac = np.mod(s.frac, 1.0)
        self.touch(Change.POSITIONS)

    def ensure_labels(self) -> None:
        """Give every unlabelled site a unique CIF-style label
        (Fe1, Fe2, O1 ...), leaving existing labels alone."""
        used = {s.label for s in self.sites if s.label}
        counters: Counter[str] = Counter()
        for s in self.sites:
            if s.label:
                continue
            while True:
                counters[s.element] += 1
                cand = f"{s.element}{counters[s.element]}"
                if cand not in used:
                    break
            s.label = cand
            used.add(cand)
        self.touch(Change.METADATA)

    def _check_bond(self, bond: Bond) -> None:
        n = len(self.sites)
        if not (0 <= bond.i < n and 0 <= bond.j < n):
            raise IndexError(
                f"bond ({bond.i}, {bond.j}) refers to a site outside "
                f"0..{n - 1}")

    # -- derived-data cache --------------------------------------------

    def cached(self, key: str, factory):
        """Memoise ``factory()`` under ``key`` until the next mutation.

        Used by neighbour lists, the P1 expansion and the scene builder
        so they are computed once per edit, not once per frame."""
        entry = self._cache.get(key)
        if entry is not None and entry[0] == self.revision:
            return entry[1]
        value = factory()
        self._cache[key] = (self.revision, value)
        return value

    # -- copying / serialisation ---------------------------------------

    def copy(self) -> Structure:
        """Deep copy, sharing nothing mutable with the original."""
        return Structure(
            lattice=self.lattice,               # immutable
            sites=[s.copy() for s in self.sites],
            space_group=self.space_group,       # immutable
            bonds=list(self.bonds),             # frozen dataclasses
            bond_rules=dict(self.bond_rules),
            meta=dict(self.meta),
        )

    def to_dict(self) -> dict:
        return {
            "lattice": self.lattice.to_dict(),
            "space_group": self.space_group.to_dict(),
            "sites": [s.to_dict() for s in self.sites],
            "bonds": [b.to_dict() for b in self.bonds],
            "bond_rules": dict(self.bond_rules),
            "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, d: dict) -> Structure:
        return cls(
            lattice=Lattice.from_dict(d["lattice"]),
            sites=[Site.from_dict(s) for s in d.get("sites", [])],
            space_group=SpaceGroup.from_dict(d["space_group"]),
            bonds=[Bond.from_dict(b) for b in d.get("bonds", [])],
            bond_rules=dict(d.get("bond_rules", {})),
            meta=dict(d.get("meta", {})),
        )

    # -- comparison ----------------------------------------------------

    def almost_equal(self, other: Structure, tol: float = 1e-8) -> bool:
        """Deep structural comparison, ignoring revision and caches.
        This is what the undo/redo round-trip tests assert on."""
        return (
            isinstance(other, Structure)
            and self.lattice.almost_equal(other.lattice, tol)
            and self.space_group == other.space_group
            and len(self.sites) == len(other.sites)
            and all(a.almost_equal(b, tol)
                    for a, b in zip(self.sites, other.sites, strict=False))
            and ({b.key() for b in self.bonds}
                 == {b.key() for b in other.bonds})
        )

    def __eq__(self, other) -> bool:
        if not isinstance(other, Structure):
            return NotImplemented
        return self.almost_equal(other)

    def __repr__(self) -> str:
        comp = "".join(
            f"{el}{n:g}" for el, n in sorted(self.composition().items())
        ) or "empty"
        return (f"Structure({comp}, {self.space_group.short_name}, "
                f"{self.n_sites} sites, "
                f"V={self.lattice.volume:.2f} A^3)")
