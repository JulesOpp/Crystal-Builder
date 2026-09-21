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


#: The individual flags, in order.  ``Change.ALL`` is a combination and
#: iterating an IntFlag's members would include it.
CHANGE_FLAGS = (Change.POSITIONS, Change.TOPOLOGY, Change.CELL,
                Change.SYMMETRY, Change.METADATA)

#: What invalidates chemistry: the bond graph, the atom typing, and
#: everything derived from them.  **Not** ``POSITIONS`` -- perception
#: is re-run when the user asks for it (``Recalculate bonds``, which
#: is a ``TOPOLOGY`` touch) and not because an atom moved.  Bonds
#: appearing and disappearing under an optimisation, or under a hand
#: that is dragging one atom, is the behaviour this excludes.
CHEMISTRY = Change.TOPOLOGY | Change.CELL | Change.SYMMETRY

#: ``Bond.kind`` for an edge of the underlying net -- pcu, fcu, soc --
#: rather than a chemical bond.  Named here, next to :class:`Bond`, so
#: that the identity rules below can tell one from the other without
#: importing the module that draws them.
TOPOLOGY = "topology"


# ======================================================================
#  BOND
# ======================================================================

@dataclass(frozen=True)
class Bond:
    """An explicit bond between two asymmetric-unit sites.

    The bond joins site ``i``, where it sits, to the point

        op[``op``](site ``j``) + ``image``

    -- a symmetry image of site ``j``, displaced by a lattice
    translation.  Both halves of that are needed and neither is
    optional:

    ``image`` is what makes a bond that crosses a periodic boundary
    survive supercells and display-range changes.  Storing only (i, j)
    is the classic bug.

    ``op`` is what lets *any* two atoms of the cell be joined.  Without
    it a stored bond can only relate two sites through the same
    operation, and a click on the wrong one of four symmetry-equivalent
    neighbours has to be refused -- which, in a group like Fm-3m, is
    almost every click.  ``op = 0`` is the identity and is the common
    case; drawing a bond on one pair still puts it on every
    symmetry-equivalent pair, because it is the *pair* that gets
    expanded.

    ``kind`` is ``"explicit"`` for a bond the user drew,
    ``"suppressed"`` for one they deleted that automatic perception
    would otherwise keep re-creating, or :data:`TOPOLOGY` for an edge
    of the underlying net -- which is not a chemical bond at all and is
    filtered out of everything that treats one as such.

    ``stated`` says the ``order`` is the user's answer and not a
    default.  It exists for the one order the number cannot express on
    its own: a bond the user deliberately called *single* carries
    ``order = 1.0``, which is exactly what an undecided bond carries,
    and without this flag the inference would go on making it double
    because both its ends look sp2.  Set Bond Type sets it; drawing a
    bond does not.
    """

    i: int
    j: int
    image: tuple[int, int, int] = (0, 0, 0)
    order: float = 1.0
    kind: str = "explicit"
    op: int = 0
    stated: bool = False

    def __post_init__(self):
        object.__setattr__(self, "i", int(self.i))
        object.__setattr__(self, "stated", bool(self.stated))
        object.__setattr__(self, "j", int(self.j))
        object.__setattr__(self, "op", int(self.op))
        object.__setattr__(self, "image",
                           tuple(int(v) for v in self.image))
        if len(self.image) != 3:
            raise ValueError("bond image must have 3 components")
        if self.op < 0:
            raise ValueError("bond operation index must be >= 0")
        if (self.i == self.j and self.op == 0
                and self.image == (0, 0, 0)):
            raise ValueError("a site cannot bond to itself in the same "
                             "periodic image")

    def reverse(self, space_group) -> Bond:
        """The same physical bond, named from the other end.

        Reading it backwards means undoing the operation that placed
        the far end, which is why this needs the group: operations
        compose only modulo a lattice translation, and that translation
        lands in the image.
        """
        m, closing = space_group.inverse_of(self.op)
        rot = space_group.operations[m].rot
        image = -(closing + rot @ np.asarray(self.image, dtype=float))
        return Bond(self.j, self.i,
                    tuple(int(round(v)) for v in image),
                    self.order, self.kind, m, self.stated)

    def canonical(self, space_group=None) -> Bond:
        """Direction-independent form, so a bond and the same bond
        written from its other end compare and hash equal.

        Without a group only the identity case can be turned around,
        which is the one every caller that has no group in hand is
        asking about.
        """
        if space_group is None:
            if self.op != 0:
                return self
            other = Bond(self.j, self.i,
                         tuple(-v for v in self.image),
                         self.order, self.kind, 0, self.stated)
        else:
            other = self.reverse(space_group)
        mine = (self.i, self.j, self.op, self.image)
        theirs = (other.i, other.j, other.op, other.image)
        return other if theirs < mine else self

    def key(self, space_group=None) -> tuple:
        c = self.canonical(space_group)
        return (c.i, c.j, c.op, c.image)

    def involves(self, index: int) -> bool:
        return self.i == index or self.j == index

    def to_dict(self) -> dict:
        out = {"i": self.i, "j": self.j, "image": list(self.image),
               "order": self.order, "kind": self.kind, "op": self.op}
        if self.stated:
            out["stated"] = True
        return out

    @classmethod
    def from_dict(cls, d: dict) -> Bond:
        return cls(d["i"], d["j"], tuple(d.get("image", (0, 0, 0))),
                   d.get("order", 1.0), d.get("kind", "explicit"),
                   d.get("op", 0), d.get("stated", False))


# ======================================================================
#  CELL BOND
# ======================================================================

@dataclass(frozen=True)
class CellBond:
    """A bond between two atoms of the P1 cell.

    The sibling of :class:`Bond`, one level down: a ``Bond`` joins two
    *sites* through a symmetry operation, and this joins two of the
    atoms that operation produced.  Perception works here, because
    distances are between atoms; the user's own bonds are stored as
    ``Bond`` records, because those are what a save and a change of
    space group have to survive.

    ``image`` is the lattice translation applied to ``j``, and it is
    read against the cell as it is currently *wrapped* -- see
    :class:`PerceivedBonds`, which is what keeps that true when an atom
    drifts across a cell face.
    """

    i: int
    j: int
    image: tuple[int, int, int]
    distance: float
    explicit: bool = False
    #: How many electron pairs join the two atoms: 1, 1.5 for an
    #: aromatic bond, 2, 3.  Perception leaves this at 1 and
    #: :func:`xtal.core.bonding.orders` infers the rest, so the number
    #: here is only ever *stated* -- carried down from the ``order`` of
    #: an explicit :class:`Bond` the user drew.
    order: float = 1.0
    #: Whether that order is the user's answer rather than a default --
    #: see :class:`Bond`.  Perception never states an order.
    stated: bool = False

    def key(self) -> tuple:
        if (self.j, self.image) < (self.i, tuple(-v for v in self.image)):
            return (self.j, self.i, tuple(-v for v in self.image))
        return (self.i, self.j, self.image)

    def to_list(self) -> list:
        """Compact form for the project file.

        A list rather than a dict: a framework has hundreds of these
        and the key names would be most of the file.
        """
        return [self.i, self.j, *self.image, round(self.distance, 6)]

    @classmethod
    def from_list(cls, row) -> CellBond:
        i, j, u, v, w, distance = row
        return cls(int(i), int(j), (int(u), int(v), int(w)),
                   float(distance))


@dataclass
class PerceivedBonds:
    """The distance-perceived bond graph of the P1 cell, stored.

    Perception is expensive, it is not re-run when atoms merely move
    (see :data:`CHEMISTRY`), and the answer is one a user can change
    deliberately -- so it is a field on the structure and it is written
    into the project file, rather than being recomputed from the
    geometry every time a document is opened.

    Three things travel with the bonds, and each of them exists to stop
    a stored graph being silently wrong later:

    ``signature`` is the :class:`~xtal.core.bonding.BondRules`
    signature it came from, so changing the rules re-perceives instead
    of being ignored.

    ``elements`` is the cell it describes.  Identical means the graph
    still applies; a *prefix* means atoms were appended and only their
    bonds need perceiving; anything else means the cell is a different
    cell and the graph is thrown away.

    ``tau`` is the wrap each atom was drawn at.  ``CellBond.image``
    counts lattice translations between *wrapped* positions, so an atom
    that drifts across a cell face and reappears on the other side
    changes the image of every bond it is in.  Keeping the wrap the
    graph was built against is what lets those images be moved onto the
    current one instead of pointing at the copy on the far side of the
    crystal.
    """

    bonds: list                     # list[CellBond]
    signature: str
    elements: tuple[str, ...]
    tau: np.ndarray                 # (n_atoms, 3) int

    @property
    def n_atoms(self) -> int:
        return len(self.elements)

    def to_dict(self) -> dict:
        return {
            "signature": self.signature,
            "elements": list(self.elements),
            "tau": np.asarray(self.tau, dtype=int).tolist(),
            "bonds": [b.to_list() for b in self.bonds],
        }

    @classmethod
    def from_dict(cls, d: dict) -> PerceivedBonds:
        elements = tuple(str(e) for e in d["elements"])
        tau = np.array(d.get("tau") or [], dtype=int).reshape(-1, 3)
        if len(tau) != len(elements):
            raise ValueError(
                f"the stored bond graph has {len(elements)} elements "
                f"but {len(tau)} wrap translations")
        return cls([CellBond.from_list(row) for row in d["bonds"]],
                   str(d["signature"]), elements, tau)


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
    # The distance-perceived bond graph of the P1 cell, once something
    # has asked for it.  ``None`` means "nobody has perceived yet"; it
    # is filled in on the first read and from then on it is the answer,
    # which is what makes a recalculated graph survive a save.
    perceived: PerceivedBonds | None = field(default=None, repr=False,
                                             compare=False)

    revision: int = field(default=0, repr=False)
    last_change: Change = field(default=Change.NONE, repr=False)
    _cache: dict = field(default_factory=dict, repr=False, compare=False)
    # flag -> the revision at which that kind of change last happened
    _changed_at: dict = field(default_factory=dict, repr=False,
                              compare=False)

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
        """Record a mutation: bump the revision, drop what it invalidated.

        Only what it invalidated.  A structure whose atoms moved has a
        stale P1 expansion and a perfectly good bond graph, atom typing
        and formula, and clearing the lot was costing an optimisation
        more time per step than the optimisation itself.
        """
        self.revision += 1
        self.last_change = change
        for flag in CHANGE_FLAGS:
            if change & flag:
                self._changed_at[flag] = self.revision
        if change & Change.SYMMETRY:
            # A new group makes the cell a different set of atoms, and
            # a graph over the old one cannot be reconciled with it --
            # only recognised as stale, which is cheaper to do here
            # than to work out later.
            #
            # A new lattice on its own is not this.  ``Change.CELL``
            # used to be checked here too, which meant nudging *c* by
            # a hundredth of an Angstrom to match a refinement silently
            # rebuilt a bond graph the user had drawn by hand -- the
            # fractional coordinates and the topology are unchanged by
            # a metric edit, so the stored graph still describes the
            # same atoms.  Every operation that *does* change which
            # atoms there are (a supercell, a basis transform, a Niggli
            # reduction) sets ``Change.SYMMETRY`` alongside
            # ``Change.CELL`` -- see ``xtal.commands.cell`` -- and is
            # still caught here.  ``Structure ▸ Recalculate bonds`` is
            # the only thing that should recalculate bonds; see
            # ``xtal.commands.bonds.RecomputeBonds``.
            self.perceived = None
        self._cache = {
            key: entry for key, entry in self._cache.items()
            if entry[0] == self._stamp(entry[2])}

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
                 b.image, b.order, b.kind, b.op, b.stated)
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

    def _bond_identity(self, bond: Bond) -> tuple:
        """What makes two stored bonds the same bond.

        The pair of points, plus whether it is a net edge.  A topology
        bond and a chemical bond can join exactly the same two atoms
        and mean entirely different things -- in a net whose vertices
        are directly bonded metals they always do -- so they must not
        collide, or drawing the net would refuse and deleting it would
        take the chemistry with it.

        ``explicit`` and ``suppressed`` deliberately *do* collide,
        because they are two answers to the same question about the
        same pair.
        """
        return (bond.kind == TOPOLOGY, bond.key(self.space_group))

    def _bond_identities(self) -> set:
        """Every bond's identity, as a set, memoised.

        The lookup this replaces was a scan of the whole list with a
        matrix multiply inside the comparison -- :meth:`Bond.reverse`
        composes symmetry operations to name a bond from its other
        end.  Adding n bonds one at a time therefore cost n**2 of
        them: opening a 21 KB MFU-4l project made 360 824 calls and
        took 2.1 seconds, and the six loops that build a graph a bond
        at a time (Reduce to P1, a project load, a MOF build, SMILES,
        a paste, connection points) all paid it.
        """
        return self.cached(
            "bond_identities",
            lambda: {self._bond_identity(b) for b in self.bonds},
            invalidated_by=CHEMISTRY)

    def add_bond(self, bond: Bond) -> bool:
        """Add a bond if it is not already there.  Returns whether it
        was added."""
        self._check_bond(bond)
        identity = self._bond_identity(bond)
        known = self._bond_identities()
        if identity in known:
            return False
        self.bonds.append(bond)
        self.touch(Change.TOPOLOGY)
        # Carry the set across the touch rather than let the next call
        # rebuild it: without this the memo is re-made on every add and
        # the loop is quadratic again, just with a cheaper constant.
        # Any *other* mutation bumps the stamp past this one and the
        # entry is discarded, which is what keeps it honest -- the bond
        # list is replaced wholesale in seven places.
        known.add(identity)
        self._cache["bond_identities"] = (self._stamp(CHEMISTRY),
                                          known, CHEMISTRY)
        return True

    def remove_bond(self, bond: Bond) -> bool:
        identity = self._bond_identity(bond)
        keep = [b for b in self.bonds
                if self._bond_identity(b) != identity]
        if len(keep) == len(self.bonds):
            return False
        self.bonds = keep
        self.touch(Change.TOPOLOGY)
        return True

    def set_bonds(self, bonds) -> None:
        """Replace the whole bond list, in one change.

        The bulk form of :meth:`add_bond` and :meth:`remove_bond`, and
        the only honest way to make a hundred bond edits at once: each
        of those touches, and a touch drops the P1 expansion, so a loop
        over them re-expands the cell once per bond.  On a framework
        with two hundred symmetry operations that is the difference
        between an edit and a stall.

        The caller owns the deduplication -- this is a replacement, not
        a merge -- but every bond is still checked against the sites
        and the group, because a bond list that names a site which is
        not there is not a saveable structure.
        """
        fresh = list(bonds)
        for bond in fresh:
            self._check_bond(bond)
        self.bonds = fresh
        self.touch(Change.TOPOLOGY)

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

    def suggest_label(self, element: str, taken=()) -> str:
        """An unused CIF-style label for a new atom of this element.

        Unlike :meth:`ensure_labels` this touches nothing that already
        exists -- adding an atom must not silently relabel the atoms
        that were already there, or undoing the addition would leave
        the structure changed.

        ``taken`` is for a batch being added together, none of which
        is in the structure yet: without it, twelve hydrogens added at
        once would every one of them be told that ``H1`` was free.
        """
        used = {site.label for site in self.sites if site.label}
        used.update(t for t in taken if t)
        n = 1
        while f"{element}{n}" in used:
            n += 1
        return f"{element}{n}"

    def _check_bond(self, bond: Bond) -> None:
        if bond.op >= self.space_group.order:
            raise ValueError(
                f"bond operation {bond.op} is outside "
                f"{self.space_group.short_name}, which has "
                f"{self.space_group.order} operations")
        n = len(self.sites)
        if not (0 <= bond.i < n and 0 <= bond.j < n):
            raise IndexError(
                f"bond ({bond.i}, {bond.j}) refers to a site outside "
                f"0..{n - 1}")

    # -- derived-data cache --------------------------------------------

    def _stamp(self, mask: Change) -> int:
        """The revision at which anything in ``mask`` last happened."""
        return max((self._changed_at.get(flag, 0)
                    for flag in CHANGE_FLAGS if mask & flag),
                   default=0)

    def cached(self, key: str, factory,
               invalidated_by: Change = Change.ALL):
        """Memoise ``factory()`` under ``key``.

        ``invalidated_by`` says which kinds of change make the answer
        wrong; the default is every kind, which is always safe and
        never wrong.  Narrowing it is what lets a positions-only edit
        keep the bond graph and the atom typing it did not affect --
        see :data:`CHEMISTRY`.

        Used by the P1 expansion, bond perception, the atom typing and
        the scene builder, so each is computed once per edit that
        matters to it rather than once per frame.
        """
        stamp = self._stamp(invalidated_by)
        entry = self._cache.get(key)
        if entry is not None and entry[0] == stamp:
            return entry[1]
        value = factory()
        self._cache[key] = (stamp, value, invalidated_by)
        return value

    # -- the stored bond graph -----------------------------------------

    def set_perceived(self, bonds, signature: str, cell) -> None:
        """Record the distance-perceived bonds of ``cell``.

        Deliberately not a mutation: nothing about the crystal changed,
        the answer to an expensive question was merely written down.
        Bumping the revision here would invalidate the very cache the
        caller is in the middle of filling.
        """
        self.perceived = PerceivedBonds(
            list(bonds), signature, tuple(cell.elements),
            np.array(cell.tau, dtype=int).reshape(-1, 3))

    def clear_perceived(self) -> None:
        """Forget the stored graph, so the next read perceives again.

        What ``Recalculate bonds`` does, and the only thing that makes
        perception follow a geometry that has moved.
        """
        self.perceived = None

    def drop_cache(self, prefix: str = "") -> None:
        """Forget memoised data whose key starts with ``prefix``.

        The escape hatch for the case where the inputs to a memo have
        not changed but the answer is wanted again anyway.
        """
        for key in [k for k in self._cache if k.startswith(prefix)]:
            del self._cache[key]

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
            # Frozen dataclasses in a fresh list: the copy perceives
            # the same bonds without perceiving them again, which is
            # what makes handing a copy to a worker thread cheap.
            perceived=(None if self.perceived is None else
                       PerceivedBonds(list(self.perceived.bonds),
                                      self.perceived.signature,
                                      self.perceived.elements,
                                      self.perceived.tau.copy())),
        )

    def to_dict(self) -> dict:
        return {
            "lattice": self.lattice.to_dict(),
            "space_group": self.space_group.to_dict(),
            "sites": [s.to_dict() for s in self.sites],
            "bonds": [b.to_dict() for b in self.bonds],
            "bond_rules": dict(self.bond_rules),
            "meta": dict(self.meta),
            "perceived": (None if self.perceived is None
                          else self.perceived.to_dict()),
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
            perceived=(PerceivedBonds.from_dict(d["perceived"])
                       if d.get("perceived") else None),
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
            and ({b.key(self.space_group) for b in self.bonds}
                 == {b.key(other.space_group) for b in other.bonds})
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
