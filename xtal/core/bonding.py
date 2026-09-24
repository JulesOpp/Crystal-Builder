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

A **topology bond** is a third kind, and it is not chemistry at all:
it is the edge of a net -- pcu, fcu, soc -- which is what is left after
a chemist decides which parts of a framework are nodes and which are
linkers.  It is stored like any other explicit bond and is filtered out
of everything chemical; :func:`topology_graph` hands the net back on
its own.  See :func:`coordination_sequence` and :func:`point_symbol`,
which are what the net is *for*.

Bond *order* is inferred here as well, and not in the force field
that used to own it: counting pi bonds is chemistry, and the viewport
should not have to import a calculator to decide how many tubes to
draw.  See :func:`orders`.

Fragment detection is periodicity-aware.  Walking the graph while
accumulating lattice translations tells a molecule (returns to the
start with a zero shift) apart from a framework (returns with a
non-zero shift, so the fragment is infinite).  Anything that asks
"select this molecule" needs that distinction or it will happily try to
select an infinite crystal one atom at a time.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, replace

import numpy as np

from xtal.core import elements as el
from xtal.core import neighbors, p1, transforms
from xtal.core import structure as structure_module
from xtal.core.structure import CHEMISTRY, Bond, CellBond

# Two atoms bond when d <= (r_i + r_j) * SCALE + DELTA, with covalent
# radii.  1.15 / 0.0 reproduces what VESTA and Mercury draw for common
# inorganic and organic structures.
DEFAULT_SCALE = 1.15
DEFAULT_DELTA = 0.0
MIN_BOND_DISTANCE = 0.4         # below this it is an overlap, not a bond

#: Re-exported from :mod:`xtal.core.elements`, where the fact belongs:
#: which symbols name a position rather than an element.  Perception
#: never bonds one -- the centre of a ring would get a bond to every
#: carbon in it, and a coordination number nobody asked for.  A bond
#: to a dummy that the user *draws* is a different matter and is
#: stored like any other; so is a net edge, which is mostly what they
#: are for.
DUMMY_ELEMENTS = el.DUMMY_ELEMENTS

#: Re-exported from :mod:`xtal.core.structure`, where the identity
#: rules for a stored bond have to know about it too.  A topology bond
#: is drawn, expands over the symmetry orbit and is saved -- and is
#: invisible to perception, to the force field and to every
#: coordination count.
TOPOLOGY = structure_module.TOPOLOGY


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
        if a in DUMMY_ELEMENTS or b in DUMMY_ELEMENTS:
            return False                # see DUMMY_ELEMENTS
        if tuple(sorted((a, b))) in {tuple(sorted(p))
                                     for p in self.forbidden}:
            return False
        if not self.allow_metal_metal:
            if el.element(a).is_metal and el.element(b).is_metal:
                return False
        return True

    def pairs_within(self, positions, symbols) -> list[tuple[int, int]]:
        """The pairs of a molecule these rules would bond.

        No cell and no images: for something that is not a crystal
        yet, such as a building block in a picker, which has to be
        drawn with the bonds the application would give it rather
        than with a rule of its own -- the MOF preview once drew
        Zn-Zn and Cu-Cu bonds perception refuses outright.
        """
        from scipy.spatial import cKDTree

        positions = np.asarray(positions, dtype=float).reshape(-1, 3)
        cutoff = self.max_cutoff(symbols)
        if len(positions) < 2 or cutoff <= 0:
            return []
        found = []
        for i, j in sorted(cKDTree(positions).query_pairs(cutoff)):
            a, b = symbols[i], symbols[j]
            if not self.allows(a, b):
                continue
            lo, hi = self.cutoff(a, b)
            if lo <= float(np.linalg.norm(positions[i] - positions[j])) \
                    <= hi:
                found.append((int(i), int(j)))
        return found

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

def bond_distance(a: str, b: str) -> float:
    """How far apart to place a new atom and the one it bonds to.

    The sum of the two covalent radii, which is what perception
    already uses to decide that two atoms *are* bonded -- so an atom
    placed here is one the distance criteria would have found anyway,
    and the bond drawn with it does not contradict the rules that
    would have drawn it.  Every element carries one, a dummy atom
    included, so there is no pair this has no answer for.
    """
    return el.covalent_radius(a) + el.covalent_radius(b)


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
            if bond.kind == TOPOLOGY:
                # Not a bond in any chemical sense.  Left in, it would
                # land in the force field's topology, in every
                # coordination number and in every valence check, and
                # be wrong in all three.
                continue
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


def hold_perception(structure, rules: BondRules | None = None) -> bool:
    """Carry the stored perception onto atoms that were just appended,
    giving them no bonds of their own.  Says whether it could.

    Perception *grows* onto appended atoms by default -- see
    :func:`_by_distance` -- and that is right for the edits that mean
    "work out what these are bonded to": Add hydrogens puts a hydrogen
    at a bond length from its parent and expects the graph to find it.

    An atom the **user placed** is the other case entirely.  They said
    where it goes, and if it bonds to anything they said that too, so
    a distance criterion offering a second opinion is exactly what
    "bonds change when you ask them to" exists to prevent -- see
    :data:`xtal.core.structure.CHEMISTRY`.  Such a command calls this
    afterwards, and the atom arrives with the bonds it was given and
    no others.

    :func:`prepare_hold` is the other half and runs *before* the edit:
    a structure that has never been perceived has nothing to carry
    forward, and would perceive the whole cell -- new atom included --
    on the next read.
    """
    stored = structure.perceived
    if stored is None:
        return False
    rules = rules or BondRules.from_dict(structure.bond_rules)
    if stored.signature != rules.signature():
        return False
    cell = p1.expand(structure)
    if not _appended_to(stored.elements, cell.elements):
        return False
    kept = rebase(stored.bonds, stored.tau, cell.tau[:stored.n_atoms])
    structure.set_perceived(kept, stored.signature, cell)
    return True


def prepare_hold(structure, rules: BondRules | None = None) -> None:
    """Make sure there is a stored perception to hold, before an edit
    that appends atoms the user placed.  See :func:`hold_perception`."""
    if structure.perceived is None:
        perceive(structure, rules)


def hold_through_removal(structure, before, removed) -> bool:
    """Carry the stored perception onto a cell that has just had sites
    taken out of it.  Says whether it could.

    The removal half of :func:`hold_perception`, and there for a
    sharper reason.  Atoms *appended* to a cell leave the stored graph
    a prefix of it, which :func:`_by_distance` grows; atoms *removed*
    leave it describing a cell that no longer exists, which that
    function can only throw away -- so deleting one atom re-perceived
    every bond in the crystal, at whatever geometry the rest of it had
    drifted to.  A user who had recalculated their bonds, or optimised
    and kept them, lost that answer to a single Delete; and undoing
    the Delete threw it away a second time rather than putting it
    back.  Bonds change when the user asks -- see
    :data:`xtal.core.structure.CHEMISTRY`.

    ``before`` is the P1 cell as it was *before* the sites went, which
    the caller has to capture: it is the only thing that says which
    atoms the stored bonds were about.  Dropping the atoms of the
    removed sites and renumbering the survivors is then arithmetic,
    because the expansion is site-major -- the same property
    :class:`xtal.commands.atoms.AddBondedSite` relies on.
    """
    stored = structure.perceived
    if stored is None:
        return False
    if stored.elements != tuple(before.elements):
        return False
    dropped = {int(i) for i in removed}
    keep = np.array([int(site) not in dropped
                     for site in before.site_idx], dtype=bool)
    cell = p1.expand(structure)
    if int(keep.sum()) != cell.n_atoms:
        # The removal did not simply take whole orbits out: a site on
        # a special position can merge or split its neighbours' images
        # as it goes.  The graph cannot be renumbered onto a cell it
        # does not match, and a wrong renumbering draws bonds between
        # atoms that were never near each other.
        return False
    index = np.cumsum(keep) - 1
    kept = [CellBond(int(index[bond.i]), int(index[bond.j]),
                     bond.image, bond.distance, bond.explicit,
                     bond.order, bond.stated)
            for bond in stored.bonds if keep[bond.i] and keep[bond.j]]
    structure.set_perceived(rebase(kept, stored.tau[keep], cell.tau),
                            stored.signature, cell)
    return True


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
    # dataclasses.replace rather than the constructor: a field listed
    # by hand is a field that can be left out, and ``stated`` was --
    # a bond order the user set went back to Automatic whenever an
    # atom crossed a face.
    return [
        replace(b, image=tuple(int(v) for v in
                               (np.asarray(b.image)
                                + shift[b.j] - shift[b.i])))
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
    group = structure.space_group
    ops = group.operations
    rotations, translations = group.stacked
    lattice = structure.lattice
    near = structure.sites[bond.i].frac
    far = (ops[bond.op].apply(structure.sites[bond.j].frac)
           + np.array(bond.image, dtype=float))

    # Every operation at once: one lookup for all 2 x order ends rather
    # than a scan of the cell per end.
    here = rotations @ near + translations
    wrapped_here = p1._wrap(here)
    tau = wrapped_here - here                   # into the cell
    there_all = rotations @ far + translations + tau
    wrapped_all = p1._wrap(there_all)
    found = _find_atoms(cell, np.vstack([wrapped_here, wrapped_all]),
                        lattice)
    n_ops = len(ops)
    ends = found[:n_ops]
    lengths = _min_image_distances(cell.frac[np.maximum(ends, 0)],
                                   there_all, lattice)
    # The image joins the two *atoms found*, not the two wrapped
    # points: an atom stored at 0 is found for a point wrapped to
    # 0.99999, and taking the image from the point then hangs the
    # bond on the copy a cell away -- Ni2Cl2BTDD drew six of the
    # eighteen edges of one chain net 5.9-39 A across the cell.
    fars = found[n_ops:]
    images = np.round(
        (there_all - cell.frac[np.maximum(fars, 0)])
        - (wrapped_here - cell.frac[np.maximum(ends, 0)])).astype(int)

    out: dict[tuple, CellBond] = {}
    for k in range(n_ops):
        a, b = found[k], found[n_ops + k]
        if a < 0 or b < 0:                      # pragma: no cover
            continue
        # ``there`` is where the partner really is; the atom found for
        # it lives inside the cell, so the bond carries the translation
        # between the two.  Getting this sign wrong draws the bond to
        # the copy on the opposite side -- or, more often, to a partner
        # that is not in the picture at all, so the bond vanishes.
        cell_bond = CellBond(
            int(a), int(b), tuple(int(v) for v in images[k]),
            float(lengths[k]),
            explicit=True, order=bond.order, stated=bond.stated)
        out[cell_bond.key()] = cell_bond
    return list(out.values())


def records_drawing(structure, cell: p1.P1Cell, key,
                    kind: str = TOPOLOGY) -> list[Bond]:
    """Every stored bond whose expansion draws this P1 edge.

    :func:`bond_between` answers a *different* question -- what to
    store for a pair of drawn atoms -- and it is not the inverse of
    this one, because a bond has more than one name.  A record says
    "site i, joined to op(site j) + image", and the same pair of
    points can be written with a different operation whenever either
    site sits on a special position: composing with anything that
    fixes site i moves the pair and re-anchors it, and composing with
    anything that fixes site j renames the operation without moving
    anything at all.

    That is not a curiosity.  In Fm-3m MOF-5 one drawn net edge stores
    one record and draws ninety-six edges, and clicking those edges
    yields *two* spellings of that one record; in halite, eight.  A
    removal that matched the record it was handed therefore deleted
    the net when the user clicked the edge they had drawn and did
    nothing at all when they clicked any of the others.

    So the question is asked the way the user asks it -- "which record
    puts this edge on the screen?" -- and answered by expanding, which
    is what drew it in the first place.  Empty when nothing stored
    draws it.

    **All of them, not the first.**  Two records that spell the same
    bond differently both draw it, and the same ambiguity is what let
    them both be stored: ``add_bond`` refuses a duplicate by comparing
    the very numbers that are not unique.  Removing one of a pair
    would leave the net on screen and look exactly like the failure
    this function exists to fix.
    """
    out = []
    for bond in structure.bonds:
        if bond.kind != kind:
            continue
        for mapped in map_explicit_bond(structure, cell, bond):
            if mapped.key() == key:
                out.append(bond)
                break
    return out


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

    # Every operation's image of site j at once; the first whose
    # difference from q is a lattice vector names the bond.  The test
    # is np.allclose's own, written out so it can be asked of all of
    # them in one go.
    rotations, translations = structure.space_group.stacked
    shift = q - (rotations @ structure.sites[site_j].frac + translations)
    whole = np.round(shift)
    close = np.all(np.abs(shift - whole) <= 1e-6 + 1e-5 * np.abs(whole),
                   axis=1)
    hits = np.flatnonzero(close)
    if len(hits):
        k = int(hits[0])
        return Bond(site_i, site_j,
                    tuple(int(v) for v in whole[k]), op=k)
    raise ValueError(                           # pragma: no cover
        "these two atoms are not in orbits of the same space group; "
        "reduce the structure to P1 to bond them")


def _find_atoms(cell, fracs, lattice, tol=1e-3) -> np.ndarray:
    """The lowest-numbered atom of the cell within ``tol`` A of each
    point, or -1.

    A scan of the whole cell per point was 4.7 million distances to
    map 19 bonds through Fm-3m; :func:`p1.within` asks a KD-tree, and
    the answer is still the first index, exactly as the scan chose.
    """
    fracs = np.asarray(fracs, dtype=float).reshape(-1, 3)
    point, atom, _distance = p1.within(cell, fracs, lattice, tol)
    out = np.full(len(fracs), -1, dtype=int)
    if not len(point):
        return out
    lowest = np.full(len(fracs), np.iinfo(int).max)
    np.minimum.at(lowest, point, atom)
    found = lowest != np.iinfo(int).max
    out[found] = lowest[found]
    return out


def _min_image_distances(frac_a, frac_b, lattice) -> np.ndarray:
    """:func:`neighbors.min_image_distance` for many pairs at once."""
    d = np.asarray(frac_b, dtype=float) - np.asarray(frac_a, dtype=float)
    d -= np.round(d)
    candidates = (d[:, None, :] + _IMAGES[None]) @ lattice.matrix
    return np.linalg.norm(candidates, axis=2).min(axis=1)


_IMAGES = np.array([(a, b, c) for a in (-1, 0, 1) for b in (-1, 0, 1)
                    for c in (-1, 0, 1)], dtype=float)


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

    def unwrap(self, atoms) -> dict[int, np.ndarray]:
        """A lattice translation for each of ``atoms`` that puts it
        beside the atoms of the set it is bonded to.

        The cell wraps every atom into it, so a molecule lying across a
        face is two pieces a cell apart, and anything that lifts it out
        -- a copy, a guest for filling a pore -- carries a methyl group
        to the far side of the crystal unless the translations are put
        back.  Walked over bonds *within* the set only: a bond out of it
        says nothing about where the copy should be, and following one
        would unwrap onto whatever the selection happened to be bonded
        to.  Each disconnected piece keeps its own atom's wrap.

        A periodic set has no consistent answer -- it closes onto its
        own image -- and gets a spanning tree's; the bonds that close
        it are the ones :meth:`consistent` refuses.
        """
        members = {int(a) for a in atoms}
        offsets: dict[int, np.ndarray] = {}
        for start in sorted(members):
            if start in offsets:
                continue
            offsets[start] = np.zeros(3, dtype=int)
            queue = deque([start])
            while queue:
                a = queue.popleft()
                for b, t, _k in self._adj[a]:
                    if b in members and b not in offsets:
                        offsets[b] = offsets[a] + t
                        queue.append(b)
        return offsets

    @staticmethod
    def consistent(bond, offsets) -> bool:
        """Whether ``bond`` joins its atoms as :meth:`unwrap` put them.

        The one that does not is the bond closing a ring through the
        periodic boundary, and written between the unwrapped atoms it
        would stretch the whole way across the cell.
        """
        return bool(np.array_equal(offsets[bond.j] - offsets[bond.i],
                                   np.asarray(bond.image, dtype=int)))

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


# ======================================================================
#  LOCAL GEOMETRY
# ======================================================================

class Geometry:
    """The shape of each atom's coordination, cached.

    A bond graph says *what* an atom is joined to; this says *where*
    those neighbours are -- which is what tells a nitrile from an
    ether, a flat ring from a chair, and a double bond from a single
    one.  The periodic bookkeeping is the whole difficulty and is done
    once here: a neighbour four cells away is at
    ``cart[j] + shift @ matrix``, and taking the copy inside the cell
    instead gives an angle that belongs to nothing.

    Public, and used from three places -- the UFF typer, the hydrogen
    builder and the bond-order inference below.  A second geometry pass
    over the same graph would be a second place for that bookkeeping to
    be got wrong.
    """

    def __init__(self, cell, graph):
        self.cell = cell
        self.graph = graph
        self.cart = cell.cart
        self.matrix = cell.lattice.matrix
        self._vectors: dict[int, np.ndarray] = {}
        self._partners: dict[int, list[int]] = {}

    def partners(self, i: int) -> list[int]:
        if i not in self._partners:
            self._resolve(i)
        return self._partners[i]

    def vectors(self, i: int) -> np.ndarray:
        """(n, 3) vectors from atom ``i`` to each bonded neighbour."""
        if i not in self._vectors:
            self._resolve(i)
        return self._vectors[i]

    def _resolve(self, i: int) -> None:
        partners, vectors = [], []
        for j, shift in self.graph.neighbors_with_images(i):
            partners.append(j)
            vectors.append(self.cart[j] + shift @ self.matrix
                           - self.cart[i])
        self._partners[i] = partners
        self._vectors[i] = (np.array(vectors, dtype=float)
                            if vectors else np.zeros((0, 3)))

    def coordination(self, i: int) -> int:
        return len(self.partners(i))

    def distances(self, i: int) -> np.ndarray:
        return np.linalg.norm(self.vectors(i), axis=1)

    def angles(self, i: int) -> np.ndarray:
        """Every neighbour-i-neighbour angle, in degrees."""
        v = self.vectors(i)
        if len(v) < 2:
            return np.zeros(0)
        unit = v / np.linalg.norm(v, axis=1)[:, None]
        out = []
        for a in range(len(unit)):
            for b in range(a + 1, len(unit)):
                out.append(np.degrees(np.arccos(
                    np.clip(float(unit[a] @ unit[b]), -1.0, 1.0))))
        return np.array(out)

    def max_angle(self, i: int) -> float:
        angles = self.angles(i)
        return float(angles.max()) if len(angles) else 0.0

    def angle_sum(self, i: int) -> float:
        """The three angles at a three-coordinate atom: 360 degrees
        when it is planar, about 328 when it is pyramidal."""
        return float(self.angles(i).sum())


def geometry(structure, rules: BondRules | None = None) -> Geometry:
    """The coordination geometry of ``structure``'s P1 cell, memoised.

    Positions are deliberately *not* part of the memo key -- the graph
    it is built over is not either.  Anything watching a relaxation
    wants the topology to hold still while the atoms move; what it must
    not do is ask this for angles mid-run and believe them.
    """
    key = f"geometry:{rules.signature() if rules else ''}"

    def build():
        return Geometry(p1.expand(structure), graph(structure, rules))

    cell = p1.expand(structure)
    geo = structure.cached(key, build, invalidated_by=CHEMISTRY)
    if geo.cell.n_atoms != cell.n_atoms:
        # The graph underneath was re-perceived because a
        # positions-only edit changed how many atoms the cell holds --
        # see :func:`_drawn`.  Holding still is one thing; indexing a
        # cell that no longer exists is another.
        structure.drop_cache(key)
        geo = structure.cached(key, build, invalidated_by=CHEMISTRY)
    return geo


# ======================================================================
#  RINGS AND AROMATICITY
# ======================================================================

# Elements that can sit in an aromatic ring.  Restricting the ring
# search to these is also what keeps it cheap: a metal-oxide framework
# has enormous numbers of short cycles and none of them are aromatic.
AROMATIC_ELEMENTS = frozenset({"B", "C", "N", "O", "P", "S", "Se"})
AROMATIC_RING_SIZES = (5, 6)
# Root-mean-square deviation from the best-fit plane, in Angstrom,
# below which a ring counts as flat.  Loose enough for a real
# refinement, tight enough to reject a cyclohexane chair (~0.25 A).
PLANARITY_TOLERANCE = 0.12


def aromatic_rings(cell, graph, geo=None) -> list[tuple[int, ...]]:
    """Planar five- and six-membered rings of sp2-capable atoms.

    Aromaticity here is decided by the coordinates rather than by a
    Kekule structure, which is the right way round for this
    application: what it has is a refined geometry, and a flat ring of
    three-coordinate carbons *is* an aromatic ring however the bonds
    were drawn.
    """
    geo = geo or Geometry(cell, graph)
    candidates = {
        i for i in range(cell.n_atoms)
        if cell.elements[i] in AROMATIC_ELEMENTS
        and 2 <= geo.coordination(i) <= 3
    }
    out = []
    for ring in find_rings(graph, candidates, max(AROMATIC_RING_SIZES)):
        if len(ring) not in AROMATIC_RING_SIZES:
            continue
        points = np.array([geo.cart[i] + np.asarray(shift) @ geo.matrix
                           for i, shift in ring])
        if transforms.plane_deviation(points) <= PLANARITY_TOLERANCE:
            out.append(tuple(i for i, _shift in ring))
    return out


def find_rings(graph, candidates: set, max_size: int) -> list[list]:
    """Simple cycles of at most ``max_size`` atoms, within
    ``candidates``, that close with no net lattice translation.

    The translation test is what makes this periodic-safe.  Walking a
    chain of Si-O-Si along a cell axis returns to the atom it started
    from after a few steps, but a cell further along; that is the
    lattice repeating, not a ring, and treating it as one would call
    every framework aromatic.

    Each ring is found once, from its lowest-numbered atom, and comes
    back as ``(atom, lattice shift)`` pairs -- the shift is what lets
    the caller lay the ring out in space when it closes through a cell
    face.
    """
    rings: list[list] = []
    seen: set[frozenset] = set()

    for start in sorted(candidates):
        origin = (start, (0, 0, 0))
        stack = [[origin]]
        while stack:
            path = stack.pop()
            node = path[-1]
            if len(path) > max_size:
                continue
            for j, shift in graph.neighbors_with_images(node[0]):
                if j not in candidates or j < start:
                    continue
                nxt = (j, tuple(int(v) for v in
                                np.asarray(node[1]) + shift))
                if nxt == origin:
                    if len(path) >= 3:
                        key = frozenset(path)
                        if key not in seen:
                            seen.add(key)
                            rings.append(list(path))
                    continue
                if nxt in path or j == start:
                    continue
                stack.append([*path, nxt])
    return rings


# ======================================================================
#  BOND ORDER
# ======================================================================
#
# A crystal structure carries no bond orders -- a CIF has nowhere to
# put them -- so they have to be inferred, and until now that was done
# inside the UFF typer against UFF's own type names.  Counting pi bonds
# is chemistry rather than one force field's business, and the viewport
# should not have to import a force field to decide how many tubes to
# draw, so it lives here and the typer reads it.

#: Below this the number is "not stated": an explicit bond left at the
#: default order is inferred like any other, and one the user actually
#: set overrides the inference.  A bond the user set to *single* says so
#: with :attr:`Bond.stated` instead, because 1.0 is also what an
#: undecided bond carries.
STATED_ORDER_TOLERANCE = 1e-9

AROMATIC_ORDER = 1.5

# How many pi bonds an atom of this element has to place, once its
# geometry has said what shape it is in.  The thresholds are the same
# ones the UFF typer reads to tell sp from sp2 from sp3, because they
# are answering the same question about the same coordinates.
LINEAR_ANGLE = 155.0        # above this, two neighbours means sp
SP2_ANGLE = 114.0           # above this, sp2 rather than sp3
PLANAR_ANGLE_SUM = 345.0    # three angles summing to this is flat

# An atom with one bond has no angles, so nothing above can judge it,
# and in a structure refined without hydrogens -- which is most of
# them -- the terminal carbon of an alkene, the carbon of a methyl
# group and the carbon of a nitrile look identical.  What separates
# them is the length, measured against the single bond the two
# covalent radii predict: a double bond runs about 0.9 of it and a
# triple about 0.8.  Butadiene without its hydrogens is the case this
# exists for -- its terminal carbons sit 1.34 A from their partners,
# which is a double bond and nothing else, and calling them saturated
# puts the double bond in the middle of the molecule where the single
# bond belongs.
DOUBLE_BOND_RATIO = 0.96
TRIPLE_BOND_RATIO = 0.86

#: The most pi bonds each element ever places, whatever the length
#: says.  Oxygen is the one that matters: a short terminal C-O is a
#: carbonyl, not a carbon monoxide ligand, and letting the ratio alone
#: decide would make carbon dioxide O#C-O.
MAX_PI = {"C": 2, "N": 2, "O": 1, "S": 1, "B": 1}


def _pi_capacity(i: int, cell, geo) -> int:
    """How many pi bonds atom ``i`` has to give away.

    Two neighbours at 180 degrees is an sp centre with two of them; a
    flat three-coordinate atom is sp2 with one; everything saturated,
    every metal and every halogen has none.  A terminal atom is judged
    by its bond length, because it has nothing else.

    Written to survive missing hydrogens, which is the normal state of
    an X-ray structure: a benzene carbon has two neighbours there, not
    three, and a rule that demanded three would find no pi bonds in
    any real refinement.
    """
    element = cell.elements[i]
    cap = MAX_PI.get(element, 0)
    n = geo.coordination(i)
    if not cap or n == 0:
        return 0

    if n == 1:
        return _terminal_capacity(i, cell, geo, cap)
    if element == "B":
        return 0 if n >= 4 else 1
    if element in ("O", "S"):
        return 0                        # bridging, an ether, a thioether
    if n >= 4:
        return 0
    if n == 3:
        return 1 if geo.angle_sum(i) >= PLANAR_ANGLE_SUM else 0
    angle = geo.max_angle(i)            # n == 2
    if angle > LINEAR_ANGLE:
        return 2
    if element == "N":
        return 1                        # bent: sp2, and no other option
    return 1 if angle >= SP2_ANGLE else 0


def _terminal_capacity(i: int, cell, geo, cap: int) -> int:
    """The pi count of an atom with exactly one bond, from its
    length relative to the single bond its two radii predict."""
    partner = cell.elements[geo.partners(i)[0]]
    single = (el.covalent_radius(cell.elements[i])
              + el.covalent_radius(partner))
    if single <= 0:                                 # pragma: no cover
        return 0
    ratio = float(geo.distances(i)[0]) / single
    if ratio <= TRIPLE_BOND_RATIO:
        return min(2, cap)
    if ratio <= DOUBLE_BOND_RATIO:
        return min(1, cap)
    return 0


def orders(structure, rules: BondRules | None = None) -> np.ndarray:
    """A bond order for every bond of the graph, in the graph's order.

    Two rules do the work.  A bond between two aromatic atoms is 1.5.
    Otherwise every unsaturated atom starts with a number of pi bonds
    to place -- one for an sp2 atom, two for an sp one -- and bonds
    take as many as both ends can still spare, shortest bond first.

    Shortest-first is what gets butadiene right.  Its four carbons are
    all sp2, and pairing them off by length makes the two short bonds
    double and the long middle one single, which is the answer;
    calling every sp2-sp2 bond double would stiffen the middle bond by
    a third.  Counting rather than pairing is what gets carbon dioxide
    right: its carbon has two pi bonds to give away, not one.

    An explicit bond whose order the user actually *set* is not
    inferred at all -- perception decides whether two atoms are bonded,
    not what the bond is.

    Memoised against everything but a geometry change, like the
    perception it is read over: bonds do not become double because two
    atoms drifted together.
    """
    key = f"bond-orders:{rules.signature() if rules else ''}"
    bonds = graph(structure, rules).bonds
    out = structure.cached(key, lambda: _infer_orders(structure, rules),
                           invalidated_by=CHEMISTRY)
    if len(out) != len(bonds):
        # One order per bond of the graph, *this* graph.  A
        # positions-only edit that moves an atom off a special position
        # splits its orbit, which re-perceives the graph underneath
        # this array -- see :func:`_drawn` -- and an array that is one
        # bond per bond of the graph before that is not merely stale,
        # it is the wrong length, and the code that draws bond orders
        # indexes off the end of it.
        structure.drop_cache(key)
        out = structure.cached(key, lambda: _infer_orders(structure, rules),
                               invalidated_by=CHEMISTRY)
    return out


def stated_pi(graph) -> dict[int, float]:
    """The pi count *stated* at each atom, where every bond says one.

    A bond order the user set is a statement about the bonding, and how
    many pi bonds an atom carries is what decides its hybridisation --
    so a carbon with two bonds the user called single is sp3 whatever
    angle the two neighbours happen to be drawn at.  The typer reads
    this and believes it over the geometry.

    Only atoms whose bonds are *all* stated appear here.  One stated
    bond among three inferred ones says nothing about the total, and
    concluding a hybridisation from it would let a single click retype
    an atom the user was not talking about.
    """
    total: dict[int, float] = {}
    for bond in graph.bonds:
        for atom in (bond.i, bond.j):
            if not bond.stated:
                total[atom] = float("nan")
            elif total.get(atom) == total.get(atom):    # not already nan
                total[atom] = total.get(atom, 0.0) + bond.order - 1.0
    return {atom: pi for atom, pi in total.items() if pi == pi}


def stated_resonant(graph) -> set[int]:
    """The atoms the user called aromatic.

    Read separately from :func:`stated_pi` because the pi count cannot
    carry it: two aromatic bonds at a ring carbon sum to exactly one pi
    bond, which is indistinguishable from one plain double bond, and
    the two mean different types to a force field.
    """
    return {atom for bond in graph.bonds
            if bond.stated
            and abs(bond.order - AROMATIC_ORDER) < STATED_ORDER_TOLERANCE
            for atom in (bond.i, bond.j)}


def _carboxylates(cell, geo, bonds, free, aromatic) -> list:
    """``(bond, bond)`` -- the two C-O bonds -- for every carboxylate
    carbon.

    A carboxylate's two C-O bonds are one bond and a half each: the
    charge and the pi bond are shared between the oxygens, and the
    lengths say so -- 1.26 A twice, not a 1.21 and a 1.34.  Counting pi
    bonds cannot see it.  An oxygen held by a metal has two neighbours
    and is given no pi bond to place, so MOF-5's carboxylates came out
    single at both ends and the carbon's own pi bond went nowhere;
    and a free one would be split double-and-single by whichever bond
    happened to be shorter.  PORMAKE's 867 blocks settle what the
    answer is: a metal-bound carboxylate is aromatic at both ends in
    1579 of them and single at both in none.

    The carbon is flat with three neighbours, two of them oxygens, and
    each oxygen has nothing else but metals -- or nothing else at all.
    An oxygen with a hydrogen or a carbon on it is an acid or an
    ester, whose bonds really are one double and one single, and it is
    left to the counting below.
    """
    by_pair: dict[tuple[int, int], list[int]] = {}
    for k in free:
        bond = bonds[k]
        by_pair.setdefault((min(bond.i, bond.j), max(bond.i, bond.j)),
                           []).append(k)
    out = []
    for carbon in range(cell.n_atoms):
        if (cell.elements[carbon] != "C" or carbon in aromatic
                or geo.coordination(carbon) != 3
                or geo.angle_sum(carbon) < PLANAR_ANGLE_SUM):
            continue
        # Two *distinct* oxygens: in a small cell one oxygen can be a
        # partner twice, through two images, and that is not this.
        oxygens = [j for j in geo.partners(carbon)
                   if cell.elements[j] == "O"]
        if len(oxygens) != 2 or len(set(oxygens)) != 2:
            continue
        if not all(_carboxylate_oxygen(o, carbon, cell, geo)
                   for o in oxygens):
            continue
        pair = [by_pair.get((min(carbon, o), max(carbon, o)), [])
                for o in oxygens]
        if all(len(ks) == 1 for ks in pair):
            out.append((pair[0][0], pair[1][0]))
    return out


def _carboxylate_oxygen(oxygen, carbon, cell, geo) -> bool:
    others = [j for j in geo.partners(oxygen) if j != carbon]
    return all(el.element(cell.elements[j]).is_metal for j in others)


def _infer_orders(structure, rules) -> np.ndarray:
    cell = p1.expand(structure)
    bonds = graph(structure, rules).bonds
    if not bonds:
        return np.zeros(0)
    geo = Geometry(cell, graph(structure, rules))
    aromatic = {i for ring in aromatic_rings(cell, graph(structure, rules),
                                             geo)
                for i in ring}

    out = np.ones(len(bonds))
    spare = {i: _pi_capacity(i, cell, geo) for i in range(cell.n_atoms)}

    # Stated first, and taken out of the counting entirely: a bond the
    # user called double has already spent the pi electrons at both
    # ends, and letting the inference spend them again would double up
    # somewhere else in the same ring.
    stated = [k for k, b in enumerate(bonds)
              if b.explicit
              and (b.stated
                   or abs(b.order - 1.0) > STATED_ORDER_TOLERANCE)]
    for k in stated:
        out[k] = float(bonds[k].order)
        used = max(0, int(round(bonds[k].order)) - 1)
        spare[bonds[k].i] = max(0, spare[bonds[k].i] - used)
        spare[bonds[k].j] = max(0, spare[bonds[k].j] - used)

    free = set(range(len(bonds))) - set(stated)
    for k in free:
        bond = bonds[k]
        if bond.i in aromatic and bond.j in aromatic:
            out[k] = AROMATIC_ORDER
            spare[bond.i] = spare[bond.j] = 0

    for pair in _carboxylates(cell, geo, bonds, free, aromatic):
        for k in pair:
            out[k] = AROMATIC_ORDER
            spare[bonds[k].i] = spare[bonds[k].j] = 0

    candidates = sorted((bonds[k].distance, k) for k in free
                        if out[k] == 1.0)
    for _distance, k in candidates:
        bond = bonds[k]
        shared = min(spare[bond.i], spare[bond.j])
        if shared <= 0:
            continue
        out[k] = 1.0 + shared
        spare[bond.i] -= shared
        spare[bond.j] -= shared
    return out


# ======================================================================
#  TOPOLOGY
# ======================================================================

def topology_graph(structure) -> BondGraph:
    """The net the user drew, as its own graph over the P1 cell.

    Only the bonds marked :data:`TOPOLOGY`, and none of the perceived
    ones: a net is a statement about which parts of a framework are
    nodes and which are linkers, and a distance criterion is not
    qualified to make it.

    Memoised and wrap-corrected like :func:`graph`, so an atom drifting
    across a cell face does not leave a net edge drawn all the way back
    across the crystal.
    """
    cell = p1.expand(structure)

    def build() -> _Drawn:
        found: dict[tuple, CellBond] = {}
        for bond in structure.bonds:
            if bond.kind != TOPOLOGY:
                continue
            for mapped in map_explicit_bond(structure, cell, bond):
                found[mapped.key()] = mapped
        bonds = sorted(found.values(),
                       key=lambda b: (b.i, b.j, b.image))
        return _Drawn(bonds, cell.tau, cell.n_atoms)

    drawn = structure.cached("topology", build, invalidated_by=CHEMISTRY)
    if drawn.n_atoms != cell.n_atoms:
        structure.drop_cache("topology")
        drawn = structure.cached("topology", build,
                                 invalidated_by=CHEMISTRY)
    return drawn.at(cell.tau).graph


def coordination_sequence(graph: BondGraph, atom: int,
                          depth: int = 10) -> list[int]:
    """How many vertices lie exactly ``k`` edges from ``atom``, for
    ``k`` from 1 to ``depth``.

    The first invariant RCSR names a net by: **pcu** is
    6, 18, 38, 66, ... and nothing else is.

    The walk is over ``(atom, lattice offset)`` pairs and not over
    atoms, which is the whole of the difficulty.  A net is infinite,
    and the six neighbours of a vertex in **pcu** are six *different*
    vertices even though the cell holds one atom -- counting atoms
    instead gives 1, 0, 0, ... for every net there is.
    """
    origin = (int(atom), (0, 0, 0))
    seen = {origin}
    frontier = {origin}
    out: list[int] = []
    for _ in range(max(0, int(depth))):
        nxt = set()
        for node, offset in frontier:
            for j, shift in graph.neighbors_with_images(node):
                step = (int(j), tuple(int(v) for v in
                                      np.asarray(offset) + shift))
                if step not in seen:
                    nxt.add(step)
        seen |= nxt
        out.append(len(nxt))
        if not nxt:
            break
        frontier = nxt
    return out


def point_symbol(graph: BondGraph, atom: int,
                 max_ring: int = 12) -> str:
    """The Schlafli point symbol at ``atom`` -- ``4^12.6^3`` for
    **pcu**.

    For every pair of edges meeting at the vertex, the size of the
    smallest ring that contains that angle; the symbol collects those
    sizes with their multiplicities.  A vertex of degree *n* has
    *n(n-1)/2* angles, and an angle with no ring inside ``max_ring``
    is written as ``*``, which is what RCSR does and is honest about
    the search having a bound.
    """
    partners = [(int(j), tuple(int(v) for v in shift))
                for j, shift in graph.neighbors_with_images(int(atom))]
    origin = (int(atom), (0, 0, 0))
    counts: dict = {}
    for a in range(len(partners)):
        for b in range(a + 1, len(partners)):
            size = _smallest_ring(graph, origin, partners[a],
                                  partners[b], max_ring)
            key = size if size else "*"
            counts[key] = counts.get(key, 0) + 1
    if not counts:
        return ""
    ordered = sorted(counts, key=lambda k: (k == "*", k))
    return ".".join(
        f"{k}^{counts[k]}" if counts[k] > 1 else f"{k}"
        for k in ordered)


def _smallest_ring(graph, origin, first, second, max_ring):
    """The shortest cycle through ``origin`` containing both edges.

    A breadth-first walk from one neighbour to the other that is not
    allowed through the vertex itself; the ring is that path plus the
    two edges back to it.
    """
    if first == second:                         # pragma: no cover
        return 0
    seen = {origin, first}
    frontier = [first]
    # The path already holds two edges (origin-first, second-origin),
    # so a path of `steps` edges from first to second closes a ring of
    # `steps + 2`.
    for steps in range(1, max_ring - 1):
        nxt = []
        for node, offset in frontier:
            for j, shift in graph.neighbors_with_images(node):
                step = (int(j), tuple(int(v) for v in
                                      np.asarray(offset) + shift))
                if step == second:
                    return steps + 2
                if step in seen or step == origin:
                    continue
                seen.add(step)
                nxt.append(step)
        if not nxt:
            break
        frontier = nxt
    return 0
