"""
xtal.analysis.interpenetrate
============================
Interpenetration, generated -- and checked by the detector that was
already here.

**There is no topological test for which nets self-interpenetrate.**
The clean part of the theory is the balance surfaces: ``pcu``, ``dia``
and ``srs`` are the labyrinth nets of the P, D and G minimal surfaces,
which is why those three interpenetrate two-fold so readily and why
the second copy sits at a coset representative rather than anywhere.
Beyond that it is Blatov's classification -- **Class Ia**, copies
related by a translation of the array, so that one net's lattice is an
index-*n* sublattice of the array's; **Class II**, copies related by a
symmetry operation that is not a translation -- and whether a given
placement is *realisable* is geometric: the voids have to be large
enough.  So this module does not theorise.  It **enumerates**
candidates, measures each one, and says which of them leave room.

* :func:`candidates` -- every Class Ia placement that the structure's
  own lattice admits at a given fold, one per orbit of the structure's
  point group, and for an acentric structure the Class II inversions
  through the quarter-cell points.
  Each is scored by its shortest contact between copies.
* :func:`build` -- the array, with **the bonds each copy had**.  Nothing
  is perceived: the copies carry the explicit bonds, the stored
  perceived graph and the drawn net of the original, moved with them.
* :func:`copies` -- how many independent periodic copies a structure
  holds, read off its bonds by :meth:`~xtal.analysis.topology.Net.
  multiplicity`.  **This is the verification**: the array is refused
  unless it counts ``n`` times what the original counted, so the
  generator is checked by code that was written to *find*
  interpenetration and knows nothing about how this one was made.

The array stays in the cell it was given.  A Class Ia offset is a
translation of order *n* modulo the structure's lattice, so the
structure's cell already holds every copy whole; the array's own,
smaller, translation lattice is a symmetry it has on top of that, and
Find Symmetry is where it is looked for.  The result is in **P1**,
because the array's group is not one copy's group and a guess at it
here would be a symmetry nobody checked.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, replace
from fractions import Fraction

import numpy as np

#: The largest fold offered.  Real frameworks stop well before it --
#: ten-fold ``dia`` is the record -- and the index-*n* sublattices grow
#: faster than *n*, so this is a bound on the list and not on the
#: chemistry.
MAX_FOLD = 6

#: How far the shortest contact between copies is looked for, in
#: Angstrom.  Beyond this the copies are far enough apart that the
#: number stops meaning anything and the report says "more than".
CONTACT_RANGE = 6.0

#: Below this, two atoms of different copies are on top of each other
#: whatever the bond rules say.  The rules' own criterion is the first
#: test -- a pair Recalculate Bonds would join has fused the copies,
#: and the count of copies is then wrong -- but it lets two hydrogens
#: sit 0.7 A apart.  Every framework in ``resources/samples`` has its
#: closest non-bonded contact between 1.996 and 2.170 A, and a build
#: whose blocks do not fit their net comes out at 1.66
#: (:func:`xtal.mof.build.closest_contact`); 1.5 is below all of it.
MIN_CONTACT = 1.5


class InterpenetrationError(ValueError):
    """A placement that cannot be made, said in a sentence."""


# ======================================================================
#  A PLACEMENT
# ======================================================================

@dataclass(frozen=True)
class Placement:
    """Where the copies go: one operation per copy, the first the
    identity.

    ``operations`` are ``(rotation, translation)`` in the structure's
    fractional coordinates, ``x' = R x + t``.  A Class Ia placement is
    all rotations the identity; a Class II inversion is ``-1`` and a
    translation of twice the centre.
    """

    kind: str                           # "translation" | "inversion"
    operations: tuple
    name: str
    #: Blatov's class: ``"Class Ia"`` when the copies are related by
    #: a translation of the whole array, ``"Class II"`` when by an
    #: operation that is not one.
    relation: str = "Class Ia"
    #: The shortest distance between two atoms of different copies,
    #: once :func:`score` has measured it; ``inf`` when nothing is
    #: within :data:`CONTACT_RANGE`, ``nan`` before it is measured.
    contact: float = float("nan")
    #: Which two atoms that is, by label, for the sentence.
    pair: tuple[str, str] = ("", "")
    #: Why this placement cannot be made, or ``""``.
    collision: str = ""

    @property
    def fold(self) -> int:
        return len(self.operations)

    @property
    def collides(self) -> bool:
        return bool(self.collision)

    def contact_text(self) -> str:
        if np.isnan(self.contact):
            return ""
        if np.isinf(self.contact):
            return f"more than {CONTACT_RANGE:g} A"
        return f"{self.contact:.2f} A"


def translation(n: int, offset) -> Placement:
    """``n`` copies, each ``offset`` further on than the last.

    The spelling a person types: one vector, the copies at
    ``0, t, 2t, ...``.  A Class Ia array exactly when ``n t`` is a
    lattice translation, which the candidates always are; one that is
    not is still an array of copies, and is measured and verified the
    same way.
    """
    n = _fold(n)
    t = np.asarray(offset, dtype=float).reshape(3)
    ops = tuple((_IDENTITY, tuple(float(v) for v in np.mod(k * t, 1.0)))
                for k in range(n))
    return Placement("translation", ops,
                     f"translation by {_spell(t)}")


def parse_offset(text) -> tuple[float, float, float]:
    """``"1/2, 1/2, 1/2"`` or ``"0.5 0.5 0.5"`` as three fractions."""
    parts = [p for p in str(text or "").replace(",", " ").split() if p]
    try:
        values = [float(Fraction(p)) for p in parts]
    except (ValueError, ZeroDivisionError):
        values = []
    if len(values) != 3:
        raise InterpenetrationError(
            f"{text!r} is not an offset -- write three fractions of "
            f"a, b and c, such as 1/2, 1/2, 1/2")
    return (values[0], values[1], values[2])


_IDENTITY = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
_INVERSION = ((-1, 0, 0), (0, -1, 0), (0, 0, -1))


def _fold(n) -> int:
    n = int(n)
    if not 2 <= n <= MAX_FOLD:
        raise InterpenetrationError(
            f"{n}-fold is not offered: interpenetration is two to "
            f"{MAX_FOLD} copies")
    return n


# ======================================================================
#  THE CANDIDATES
# ======================================================================

def candidates(structure, n: int) -> list[Placement]:
    """Every placement worth measuring at ``n``-fold, best first.

    **Class Ia**: the superlattices of index ``n`` of the structure's
    own lattice, each giving ``n`` coset representatives for the copies
    to sit at.  One that contains a translation the structure already
    has -- a centring vector -- is left out, because its copy lands on
    the original.

    **Class II**, at two-fold: the copy is the original inverted
    through a point ``p`` of the eighth-cell grid, and the inversion is
    then a symmetry of the array whatever the structure's own group.
    For a centrosymmetric structure that copy *is* the original
    translated, by ``2p`` less the structure's own centre, and it is
    offered as the translation -- which is how 2-fold MOF-5 is found:
    its second copy is a quarter of the cell along the body diagonal,
    and no half-vector of its F-centred cell reaches it.

    Two placements that a symmetry of the structure carries onto each
    other are the same array turned round, and are one row.  The
    symmetry is **detected** on the P1 cell, not read off the label: a
    framework straight out of the builder is labelled P1 and is cubic.

    Scored, and sorted by the shortest contact between copies,
    largest first; the ones that collide are kept, at the end, with
    the reason -- a list that silently dropped them could not say why
    a dense framework offers nothing.
    """
    n = _fold(n)
    from xtal.analysis.topology import net_of

    one = _flat(structure)
    # The chemistry or a net drawn over it: a net drawn on its own,
    # vertices and nothing else, is a framework waiting for blocks.
    if copies(one) == 0 and _net_copies(net_of(one)) == 0:
        raise InterpenetrationError(
            "nothing here is periodic: the bonds make only molecules, "
            "and a molecular crystal has no framework to thread a "
            "second copy through -- Recalculate Bonds first if the "
            "framework should be bonded")
    ops = _symmetry(one)
    found, seen = [], set()

    def offer(reps, name, relation):
        key = _orbit_key(ops, reps)
        if key not in seen:
            seen.add(key)
            found.append(Placement(
                "translation",
                tuple((_IDENTITY, tuple(float(v) for v in r))
                      for r in reps),
                name, relation))

    for reps in _superlattice_cosets(n):
        if not any(_is_translation(ops, r) for r in reps[1:]):
            offer(reps, _name_cosets(reps), "Class Ia")
    if n == 2:
        centre = _centre(ops)
        for p in itertools.product(np.arange(4) / 8, repeat=3):
            p = np.array(p)
            if centre is None:
                _offer_inversion(found, seen, ops, p)
                continue
            t = np.mod(2 * p - centre, 1.0)
            if np.allclose(np.mod(2 * t + 0.5, 1.0) - 0.5, 0.0,
                           atol=1e-6):
                continue            # a Class Ia row, or the original
            offer([np.zeros(3), t], f"translation by {_spell(t)}",
                  "Class II")
    measure = _Measure(one)
    scored = [measure(placement) for placement in found]
    scored.sort(key=_rank)
    return scored


def _offer_inversion(found, seen, ops, p) -> None:
    """Inversion through ``p``, once per class of centres.

    Conjugating the inversion through ``p`` by a symmetry ``g`` of the
    structure gives the inversion through ``g(p)``, so the centres a
    symmetry relates give the same array; and centres half a lattice
    vector apart give copies a lattice vector apart, which is the same
    copy.
    """
    keys = []
    for rot, trans in ops:
        moved = np.mod(rot @ p + trans, 0.5)
        keys.append(tuple(int(round(v * 16)) % 8 for v in moved))
    key = ("inversion", min(keys))
    if key in seen:
        return
    seen.add(key)
    found.append(Placement(
        "inversion",
        ((_IDENTITY, (0.0, 0.0, 0.0)),
         (_INVERSION, tuple(float(v) for v in np.mod(2 * p, 1.0)))),
        f"inversion through {_spell(p)}", "Class II"))


def best(structure, n: int) -> Placement:
    """The candidate with the most room, or a sentence saying why
    there is none."""
    found = candidates(structure, n)
    viable = [c for c in found if not c.collides]
    if viable:
        return viable[0]
    if not found:
        raise InterpenetrationError(
            f"this lattice offers no {n}-fold placement at all")
    closest = found[0]
    raise InterpenetrationError(
        f"no {n}-fold placement leaves room: the best of "
        f"{len(found)}, {closest.name}, {closest.collision}")


def _rank(placement: Placement):
    contact = placement.contact
    return (placement.collides,
            -round(contact, 3) if np.isfinite(contact) else -np.inf,
            placement.relation, placement.name)


def _superlattice_cosets(n: int):
    """The coset representatives of every lattice containing ``Z^3``
    with index ``n``, identity first.

    Each is the dual of a sublattice of index ``n``, and those are the
    Hermite normal forms of determinant ``n``: upper triangular, each
    entry above a pivot reduced modulo it.  Seven at two-fold, the
    half-vectors; thirteen at three-fold.
    """
    for a, d, f in _factorisations(n):
        for b, c, e in itertools.product(range(d), range(f), range(f)):
            h = np.array([[a, b, c], [0, d, e], [0, 0, f]], dtype=float)
            inverse = np.linalg.inv(h)
            reps = {}
            for m in itertools.product(range(n), repeat=3):
                x = np.mod(inverse @ np.array(m, dtype=float), 1.0)
                grid = tuple(int(round(v * n)) % n for v in x)
                reps.setdefault(grid, np.array(grid, dtype=float) / n)
            yield [reps[g] for g in sorted(reps)]


def _factorisations(n: int):
    for a in range(1, n + 1):
        if n % a:
            continue
        for d in range(1, n // a + 1):
            if (n // a) % d:
                continue
            yield a, d, n // a // d


#: spglib's tolerance for the symmetry the candidates are sorted by,
#: in Angstrom.  A framework out of the builder is exact to the digits
#: it was written at; this only has to see through that rounding.
SYMPREC = 0.01


def _symmetry(one) -> list:
    """``(R, t)`` for every symmetry of the P1 cell, in its own basis.

    Only ever used to *merge* rows, so a symmetry missed costs a
    duplicate row and nothing else.
    """
    import spglib

    from xtal.core import symmetry

    identity = [(np.eye(3, dtype=int), np.zeros(3))]
    try:
        cell, _back, _flat_cell = symmetry._spglib_cell(one)
        found = spglib.get_symmetry(cell, symprec=SYMPREC)
    except Exception:
        return identity
    if not found:
        return identity
    return [(np.asarray(r, dtype=int), np.mod(np.asarray(t), 1.0))
            for r, t in zip(found["rotations"], found["translations"],
                            strict=True)]


def _is_translation(ops, vector) -> bool:
    """Is ``vector`` a translation the structure already has?"""
    for rot, trans in ops:
        if not np.array_equal(rot, np.eye(3, dtype=int)):
            continue
        delta = np.mod(trans - vector + 0.5, 1.0) - 0.5
        if np.allclose(delta, 0.0, atol=1e-4):
            return True
    return False


def _centre(ops):
    """Twice a centre of inversion of the structure, or ``None``."""
    for rot, trans in ops:
        if np.array_equal(rot, -np.eye(3, dtype=int)):
            return trans
    return None


def _orbit_key(ops, reps) -> tuple:
    """One name for a set of copies and every rotation of it the
    structure's own symmetry makes.

    Carrying the array ``{S, S + t}`` by a symmetry ``(R, tau)`` of
    ``S`` gives ``{S, S + R t}``: the same array, turned.  And
    ``{S, S + t}`` is ``{S - t, S}`` moved by ``t``.  So rows that
    differ only by either are one row.
    """
    keys = []
    for rot, _trans in ops:
        for sign in (1, -1):
            moved = sorted(tuple(int(round(v * 48)) % 48
                                 for v in sign * (rot @ r))
                           for r in reps)
            keys.append(tuple(moved))
    return min(keys)


def _name_cosets(reps) -> str:
    rest = [r for r in reps if np.any(r)]
    if len(rest) == 1:
        return f"translation by {_spell(rest[0])}"
    return "translations by " + "; ".join(_spell(r) for r in rest)


def _spell(vector) -> str:
    return ", ".join(str(Fraction(float(v)).limit_denominator(48) % 1)
                     for v in vector)


# ======================================================================
#  MEASURING ONE
# ======================================================================

def score(structure, placement: Placement) -> Placement:
    """``placement`` with its shortest contact between copies, and the
    reason it collides if it does."""
    return _Measure(_flat(structure))(placement)


class _Measure:
    """The shortest contact between copies, for one structure and any
    number of placements.

    Contacts *within* a copy are the original's and are not measured:
    they are the same in every placement and would decide nothing.
    Dummy atoms are held back at the door -- a net vertex or a marker
    sitting in a pore is not chemistry for anything to bump into.

    A class so that the expansion, the labels and the table of limits
    are made once: the candidates at two-fold are seventy placements
    of the same cell.
    """

    def __init__(self, one):
        from xtal.core import bonding, elements, p1

        cell = p1.expand(one)
        self.lattice = one.lattice
        self.frac = np.asarray(cell.frac, dtype=float)
        self.labels = [str(cell.labels[k] or cell.elements[k])
                       for k in range(cell.n_atoms)]
        kinds = sorted({str(e) for e in cell.elements})
        self.kind = np.array([kinds.index(str(e))
                              for e in cell.elements], dtype=int)
        self.dummy = np.array([elements.is_dummy(str(e))
                               for e in cell.elements], dtype=bool)
        rules = bonding.BondRules.from_dict(one.bond_rules)
        #: Where Recalculate Bonds would join two elements.
        shape = (len(kinds), len(kinds))
        self.bonding = np.array([[rules.cutoff(a, b)[1] for b in kinds]
                                 for a in kinds]).reshape(shape)
        #: Whether it would join them at all -- two sodiums are never
        #: bonded, and 2.4 A apart they are still on top of each other.
        self.allowed = np.array([[rules.allows(a, b) for b in kinds]
                                 for a in kinds],
                                dtype=bool).reshape(shape)

    def __call__(self, placement: Placement) -> Placement:
        from xtal.core.neighbors import neighbor_pairs

        count = len(self.frac)
        frac, owner = _positions(self.frac, placement)
        pairs = neighbor_pairs(frac, self.lattice, CONTACT_RANGE,
                               min_distance=0.0)
        i, j = pairs.i % count, pairs.j % count
        keep = ((owner[pairs.i] != owner[pairs.j])
                & ~self.dummy[i] & ~self.dummy[j])
        i, j, distance = i[keep], j[keep], pairs.distance[keep]
        if not len(distance):
            return replace(placement, contact=float("inf"))
        nearest = int(np.argmin(distance))
        pair = (self.labels[i[nearest]], self.labels[j[nearest]])
        joins = self.bonding[self.kind[i], self.kind[j]]
        limits = np.maximum(joins, MIN_CONTACT)
        over = distance < limits
        collision = ""
        if over.any():
            worst = int(np.argmin(np.where(over, distance - limits,
                                           np.inf)))
            near = float(distance[worst])
            if near >= joins[worst]:
                why = f"closer than {MIN_CONTACT:g} A"
            elif self.allowed[self.kind[i[worst]], self.kind[j[worst]]]:
                why = ("close enough for Recalculate Bonds to join the "
                       "two copies")
            else:
                why = "closer than a bond between the two would be"
            collision = (f"puts {self.labels[i[worst]]} of one copy "
                         f"{near:.2f} A from {self.labels[j[worst]]} of "
                         f"another, {why}")
        return replace(placement, contact=float(distance[nearest]),
                       pair=pair, collision=collision)


def _positions(frac, placement: Placement):
    """Every copy's atoms, and which copy each one is."""
    frac = np.asarray(frac, dtype=float)
    out, owner = [], []
    for k, (rot, trans) in enumerate(placement.operations):
        out.append(frac @ np.asarray(rot, dtype=float).T
                   + np.asarray(trans, dtype=float))
        owner.append(np.full(len(frac), k))
    return np.vstack(out), np.concatenate(owner)


# ======================================================================
#  BUILDING THE ARRAY
# ======================================================================

def build(structure, placement: Placement):
    """``(array, placement)`` -- the copies, each with the bonds it had.

    Refused, by name, when the placement collides.  Refused too when
    the detector does not count ``n`` times the copies the original
    had: that would be copies that joined, or a placement that put one
    copy exactly on another, and either way not the array that was
    asked for.
    """
    from xtal.analysis.topology import net_of
    from xtal.core import bonding, p1
    from xtal.core.spacegroup import SpaceGroup
    from xtal.core.structure import Bond, CellBond, Structure

    placement = score(structure, placement)
    if placement.collides:
        raise InterpenetrationError(
            f"{placement.name} {placement.collision}")

    one = _flat(structure)
    stored = one.perceived
    n_atoms = one.n_sites
    zero = np.zeros((n_atoms, 3), dtype=int)
    base = bonding.rebase(stored.bonds, stored.tau, zero)

    sites, bonds, perceived = [], [], []
    for k, (rot, trans) in enumerate(placement.operations):
        rot = np.asarray(rot, dtype=int)
        moved = one.frac @ rot.T + np.asarray(trans, dtype=float)
        shift = np.floor(moved + 1e-9).astype(int)
        start = k * n_atoms
        for index, site in enumerate(one.sites):
            copy = site.copy()
            copy.frac = moved[index] - shift[index]
            copy.wyckoff = None
            if k:
                copy.label = ""
            sites.append(copy)

        def image(i, j, old, rot=rot, shift=shift):
            return tuple(int(v) for v in
                         rot @ np.asarray(old, dtype=int)
                         + shift[j] - shift[i])

        for b in one.bonds:
            bonds.append(Bond(b.i + start, b.j + start,
                              image(b.i, b.j, b.image), b.order, b.kind,
                              0, b.stated))
        for b in base:
            perceived.append(CellBond(
                b.i + start, b.j + start, image(b.i, b.j, b.image),
                b.distance, b.explicit, b.order, b.stated))

    out = Structure(lattice=one.lattice, sites=sites,
                    space_group=SpaceGroup.p1(), bonds=bonds,
                    bond_rules=dict(one.bond_rules),
                    meta=dict(one.meta))
    out.ensure_labels()
    cell = p1.expand(out)
    out.set_perceived(
        bonding.rebase(perceived,
                       np.zeros((cell.n_atoms, 3), dtype=int), cell.tau),
        stored.signature, cell)

    n = placement.fold
    for what, before, after in (
            ("framework", copies(one), copies(out)),
            ("net", _net_copies(net_of(one)), _net_copies(net_of(out)))):
        if after != n * before:
            raise InterpenetrationError(
                f"{placement.name} was built and the {what} does not "
                f"come out {n}-fold: the detector counts {after} "
                f"cop{'y' if after == 1 else 'ies'} where there were "
                f"{before}, so copies have landed on one another")
    return out, placement


def _flat(structure):
    """The structure in P1 with its perceived graph written down.

    Perceived first, on a copy, and then expanded with the graph
    carried -- :func:`xtal.core.symmetry.reduce_to_p1` carries a stored
    graph and would otherwise leave the array to be perceived from
    scratch, which is exactly how two copies close together would end
    up bonded to each other.
    """
    from xtal.core import bonding, symmetry

    held = structure.copy()
    bonding.graph(held)
    one = held if held.is_p1 else symmetry.reduce_to_p1(held)
    bonding.graph(one)
    return one


# ======================================================================
#  THE DETECTOR
# ======================================================================

def copies(structure) -> int:
    """How many independent periodic frameworks the bonds make.

    The chemical bond graph as a net, split into the components of the
    quotient graph, each counted by its :meth:`~xtal.analysis.topology.
    Net.multiplicity` -- which is how two copies written into one cell
    and one copy written into a doubled cell both count two.  Only
    periodic components: a solvent molecule is not a framework, and
    counting it would make a solvated array look as if it had lost
    copies.
    """
    from xtal.analysis.topology import Edge, Net
    from xtal.core import bonding

    graph = bonding.graph(structure)
    edges = tuple(Edge(b.i, b.j, tuple(int(v) for v in b.image))
                  for b in graph.bonds)
    return _net_copies(Net(graph.n_atoms, edges))


def _net_copies(net) -> int:
    if net.is_empty():
        return 0
    return sum(part.multiplicity() for part in net.components()
               if part.periodicity() > 0)
