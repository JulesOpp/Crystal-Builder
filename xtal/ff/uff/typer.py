"""
xtal.ff.uff.typer
=================
Bond graph plus geometry in, UFF atom types out.

This is where wrong answers come from.  The energy expressions are
arithmetic and either match the paper or do not; the *typing* is a
judgement about what a set of coordinates means chemically, and a
carbon called ``C_3`` when it should have been ``C_R`` gives a
plausible-looking number that is simply wrong.  So every assignment
here carries the reason it was made and how much it should be trusted,
the Force Field dock shows both, and the user can override any of
them -- an override is stored in ``Site.props["uff_type"]`` and travels
with the structure.

Three things decide a type:

* **coordination**, from the bond graph;
* **geometry**, from the coordinates -- the angle at a two-coordinate
  atom is what tells a nitrile from an ether;
* **aromaticity**, from planar rings of the right size, detected
  through the periodic bond graph so a ring that closes through a cell
  boundary is still a ring.

Elements with no hand-written rule -- most of the periodic table, and
every metal -- fall through to the type table itself: a UFF type name
says what coordination it expects (``Fe6+2`` is octahedral), so
choosing the type whose geometry character matches what the atom
actually has is a general rule and not a special case.  Those come out
marked uncertain when nothing matches, because a metal in an unusual
coordination is exactly the case UFF is worst at and the user needs to
be told rather than reassured.

Missing hydrogens are the other running theme.  An X-ray structure
usually has none, so a benzene carbon has two neighbours rather than
three and a methyl carbon has one.  Rules here are written to survive
that, and to say so in the reason when it is what they assumed.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from xtal.core import bonding, p1
from xtal.core.structure import CHEMISTRY, Change
from xtal.ff.uff import params

# Elements that can sit in an aromatic ring.  Restricting the ring
# search to these is also what keeps it cheap: a metal-oxide framework
# has enormous numbers of short cycles and none of them are aromatic.
AROMATIC_ELEMENTS = frozenset({"B", "C", "N", "O", "P", "S", "Se"})
AROMATIC_RING_SIZES = (5, 6)
# Root-mean-square deviation from the best-fit plane, in Angstrom,
# below which a ring counts as flat.  Loose enough for a real
# refinement, tight enough to reject a cyclohexane chair (~0.25 A).
PLANARITY_TOLERANCE = 0.12

# The type given to each element that has exactly one sensible answer
# regardless of what it is bonded to.
SIMPLE_TYPES = {
    "Li": "Li", "Na": "Na", "K": "K_", "Rb": "Rb", "Cs": "Cs",
    "Fr": "Fr",
    "F": "F_", "Cl": "Cl", "Br": "Br", "I": "I_", "At": "At",
    "Al": "Al3", "Si": "Si3", "Ge": "Ge3", "Sn": "Sn3", "Pb": "Pb3",
    "He": "He4+4", "Ne": "Ne4+4", "Ar": "Ar4+4", "Kr": "Kr4+4",
    "Xe": "Xe4+4", "Rn": "Rn4+4",
}

# Elements whose oxide bridges get UFF's zeolite oxygen.
ZEOLITE_FORMERS = frozenset({"Si", "Al", "P", "Ge", "B"})

CERTAIN = "certain"
LIKELY = "likely"
UNCERTAIN = "uncertain"
CONFIDENCE_ORDER = {CERTAIN: 0, LIKELY: 1, UNCERTAIN: 2}


class TypingError(ValueError):
    """An atom UFF has no parameters for at all."""


@dataclass(frozen=True)
class AtomType:
    """One atom's assignment, and how much to trust it."""

    name: str
    confidence: str = CERTAIN
    reason: str = ""
    overridden: bool = False

    @property
    def params(self) -> params.UFFParams:
        return params.get(self.name)

    @property
    def is_sure(self) -> bool:
        return self.overridden or self.confidence == CERTAIN


@dataclass(frozen=True)
class Typing:
    """The typing of a whole P1 cell."""

    types: tuple[AtomType, ...]
    bond_orders: np.ndarray             # one per bond of the graph
    rings: tuple[tuple[int, ...], ...]  # aromatic rings, by atom index

    def __len__(self) -> int:
        return len(self.types)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(t.name for t in self.types)

    def unsure(self) -> list[int]:
        """Atoms the user should look at before believing the energy.

        Only the genuinely uncertain ones.  A "likely" assignment
        carries its reasoning and is usually right -- rutile's
        titanium has six neighbours and UFF has an octahedral titanium
        -- and warning about those as well would put a warning on
        almost every crystal and leave nothing to notice.  What is
        listed here is the case where nothing fitted: a coordination
        the element has no type for, an atom with no neighbours to
        judge by.
        """
        return [i for i, t in enumerate(self.types)
                if t.confidence == UNCERTAIN and not t.overridden]

    def summary(self) -> str:
        unsure = self.unsure()
        counts: dict[str, int] = {}
        for t in self.types:
            counts[t.name] = counts.get(t.name, 0) + 1
        listed = ", ".join(f"{n}x{c}" for n, c in sorted(counts.items()))
        if not unsure:
            return f"{len(self.types)} atoms typed: {listed}"
        return (f"{len(self.types)} atoms typed: {listed} "
                f"-- {len(unsure)} uncertain")


# ======================================================================
#  ENTRY POINT
# ======================================================================

def assign(structure, rules: bonding.BondRules | None = None) -> Typing:
    """Type every atom of ``structure``'s P1 cell.

    Memoised with the structure, so the panel that draws the table and
    the calculator that consumes it do the work once between edits.
    """
    key = f"uff-typing:{rules.signature() if rules else ''}"
    # Chemistry, plus METADATA: a hand-set type is stored in
    # ``Site.props`` and setting one is a metadata change, so the memo
    # has to notice it.  Atoms moving is what it deliberately ignores.
    return structure.cached(key, lambda: _assign(structure, rules),
                            invalidated_by=CHEMISTRY | Change.METADATA)


def _assign(structure, rules) -> Typing:
    cell = p1.expand(structure)
    graph = bonding.graph(structure, rules)
    if cell.n_atoms == 0:
        return Typing((), np.zeros(0), ())

    _refuse_unknown_elements(cell)
    geometry = _Geometry(cell, graph)
    rings = _aromatic_rings(cell, graph, geometry)
    aromatic = {i for ring in rings for i in ring}

    overrides = _overrides(structure, cell)
    types = []
    for i in range(cell.n_atoms):
        override = overrides.get(i)
        if override is not None:
            types.append(AtomType(override, CERTAIN,
                                  "set by hand", overridden=True))
        else:
            types.append(_type_of(i, cell, graph, geometry,
                                  i in aromatic))
    _refine_terminal(types, cell, geometry)
    orders = _bond_orders(graph, [t.name for t in types], aromatic)
    return Typing(tuple(types), orders,
                  tuple(tuple(r) for r in rings))


def _refuse_unknown_elements(cell) -> None:
    unknown = sorted({e for e in cell.elements
                      if not params.has_element(e)})
    if unknown:
        raise TypingError(
            "UFF has no parameters for "
            + ", ".join(unknown)
            + "; the force field covers hydrogen to lawrencium and "
              "nothing beyond it")


def _overrides(structure, cell) -> dict[int, str]:
    """Hand-set types, mapped from sites onto the atoms they generate.

    An override is stored on the *site*, so it applies to the whole
    symmetry orbit -- which is the only consistent thing it could do:
    two atoms related by symmetry are the same atom seen twice, and
    typing them differently would make the energy depend on which copy
    the user happened to click.
    """
    out: dict[int, str] = {}
    for index, site in enumerate(structure.sites):
        name = site.props.get("uff_type")
        if not name:
            continue
        if name not in params.PARAMS:
            structure.meta.setdefault("warnings", []).append(
                f"ignored unknown UFF type {name!r} on "
                f"{site.label or site.element}")
            continue
        for atom in cell.indices_of_site(index):
            out[int(atom)] = name
    return out


# ======================================================================
#  GEOMETRY
# ======================================================================

class _Geometry:
    """Cartesian neighbour vectors, with the periodic images resolved.

    Every rule below needs "where are this atom's neighbours, really",
    and in a crystal half of them are usually in the next cell along.
    Resolving that once here is what keeps the rules readable.
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


def _plane_deviation(points: np.ndarray) -> float:
    """RMS distance of ``points`` from their best-fit plane."""
    if len(points) < 4:
        return 0.0
    centred = points - points.mean(axis=0)
    normal = np.linalg.svd(centred)[2][-1]
    return float(np.sqrt(np.mean((centred @ normal) ** 2)))


# ======================================================================
#  RINGS AND AROMATICITY
# ======================================================================

def _aromatic_rings(cell, graph, geometry) -> list[tuple[int, ...]]:
    """Planar five- and six-membered rings of sp2-capable atoms.

    Aromaticity here is decided by the coordinates rather than by a
    Kekule structure, which is the right way round for this
    application: what it has is a refined geometry, and a flat ring of
    three-coordinate carbons *is* an aromatic ring however the bonds
    were drawn.
    """
    candidates = {
        i for i in range(cell.n_atoms)
        if cell.elements[i] in AROMATIC_ELEMENTS
        and 2 <= geometry.coordination(i) <= 3
    }
    out = []
    for ring in _find_rings(graph, candidates, max(AROMATIC_RING_SIZES)):
        if len(ring) not in AROMATIC_RING_SIZES:
            continue
        points = np.array([geometry.cart[i] + np.asarray(shift) @
                           geometry.matrix for i, shift in ring])
        if _plane_deviation(points) <= PLANARITY_TOLERANCE:
            out.append(tuple(i for i, _shift in ring))
    return out


def _find_rings(graph, candidates: set, max_size: int) -> list[list]:
    """Simple cycles of at most ``max_size`` atoms, within
    ``candidates``, that close with no net lattice translation.

    The translation test is what makes this periodic-safe.  Walking a
    chain of Si-O-Si along a cell axis returns to the atom it started
    from after a few steps, but a cell further along; that is the
    lattice repeating, not a ring, and treating it as one would call
    every framework aromatic.

    Each ring is found once, from its lowest-numbered atom.
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
#  THE RULES
# ======================================================================

def _type_of(i: int, cell, graph, geo, aromatic: bool) -> AtomType:
    element = cell.elements[i]
    rule = _RULES.get(element)
    if rule is not None:
        return rule(i, cell, geo, aromatic)
    if element in SIMPLE_TYPES:
        return AtomType(SIMPLE_TYPES[element], CERTAIN,
                        "the only type UFF gives this element")
    return _by_coordination(i, cell, geo)


def _hydrogen(i, cell, geo, _aromatic) -> AtomType:
    n = geo.coordination(i)
    if n == 2 and all(cell.elements[j] == "B" for j in geo.partners(i)):
        return AtomType("H_b", CERTAIN, "bridging two borons")
    if n > 1:
        return AtomType("H_", UNCERTAIN,
                        f"{n} neighbours; hydrogen should have one, "
                        f"so the bond criteria may be too generous")
    return AtomType("H_", CERTAIN, "")


def _boron(i, _cell, geo, _aromatic) -> AtomType:
    if geo.coordination(i) >= 4:
        return AtomType("B_3", CERTAIN, "four neighbours")
    return AtomType("B_2", LIKELY,
                    f"{geo.coordination(i)} neighbours, taken as "
                    f"trigonal")


def _carbon(i, _cell, geo, aromatic) -> AtomType:
    n = geo.coordination(i)
    if n >= 4:
        return AtomType("C_3", CERTAIN, "four neighbours")
    if aromatic:
        return AtomType("C_R", CERTAIN, "in a flat aromatic ring")
    if n == 3:
        total = geo.angle_sum(i)
        if total >= 345.0:
            return AtomType("C_2", CERTAIN,
                            f"planar, angles sum to {total:.0f}")
        return AtomType("C_3", LIKELY,
                        f"pyramidal, angles sum to {total:.0f}; "
                        f"a hydrogen is probably missing")
    if n == 2:
        angle = geo.max_angle(i)
        if angle > 155.0:
            return AtomType("C_1", CERTAIN, f"linear, {angle:.0f}")
        if angle >= 114.0:
            return AtomType("C_2", LIKELY,
                            f"{angle:.0f} between its two neighbours")
        return AtomType("C_3", LIKELY,
                        f"{angle:.0f} between its two neighbours; "
                        f"hydrogens are probably missing")
    return AtomType("C_3", UNCERTAIN,
                    f"only {n} neighbour(s); nothing in the geometry "
                    f"says what this carbon is")


def _nitrogen(i, cell, geo, aromatic) -> AtomType:
    n = geo.coordination(i)
    if n >= 4:
        return AtomType("N_3", CERTAIN, "four neighbours")
    if aromatic:
        return AtomType("N_R", CERTAIN, "in a flat aromatic ring")
    if n == 3:
        total = geo.angle_sum(i)
        if total >= 345.0:
            return AtomType("N_2", CERTAIN,
                            f"planar, angles sum to {total:.0f}")
        return AtomType("N_3", CERTAIN,
                        f"pyramidal, angles sum to {total:.0f}")
    if n == 2:
        angle = geo.max_angle(i)
        if angle > 155.0:
            return AtomType("N_1", CERTAIN, f"linear, {angle:.0f}")
        return AtomType("N_2", LIKELY,
                        f"bent at {angle:.0f}, taken as sp2")
    if n == 1:
        d = float(geo.distances(i)[0])
        if d < 1.20:
            return AtomType("N_1", LIKELY,
                            f"one neighbour at {d:.2f} A -- a triple "
                            f"bond")
        return AtomType("N_2", LIKELY,
                        f"one neighbour at {d:.2f} A")
    return AtomType("N_3", UNCERTAIN, "no neighbours")


def _oxygen(i, cell, geo, aromatic) -> AtomType:
    n = geo.coordination(i)
    if aromatic:
        return AtomType("O_R", CERTAIN, "in a flat aromatic ring")
    if n >= 3:
        return AtomType("O_3", LIKELY,
                        f"{n} neighbours; bridging or over-bonded")
    if n == 2:
        neighbours = [cell.elements[j] for j in geo.partners(i)]
        angle = geo.max_angle(i)
        if (all(e in ZEOLITE_FORMERS for e in neighbours)
                and angle >= 130.0):
            return AtomType(
                "O_3_z", CERTAIN,
                f"bridges {neighbours[0]} and {neighbours[1]} at "
                f"{angle:.0f} -- a framework oxygen")
        return AtomType("O_3", CERTAIN, f"two neighbours at "
                                        f"{angle:.0f}")
    if n == 1:
        d = float(geo.distances(i)[0])
        partner = cell.elements[geo.partners(i)[0]]
        if d < 1.30:
            return AtomType("O_2", CERTAIN,
                            f"one short bond to {partner} at "
                            f"{d:.2f} A -- a double bond")
        return AtomType("O_3", LIKELY,
                        f"one bond to {partner} at {d:.2f} A, too "
                        f"long to be a double bond")
    return AtomType("O_3", UNCERTAIN, "no neighbours")


def _phosphorus(i, _cell, geo, _aromatic) -> AtomType:
    n = geo.coordination(i)
    if n >= 4:
        return AtomType("P_3+5", CERTAIN, f"{n} neighbours")
    return AtomType("P_3+3", LIKELY, f"{n} neighbours")


def _sulfur(i, _cell, geo, aromatic) -> AtomType:
    n = geo.coordination(i)
    if aromatic:
        return AtomType("S_R", CERTAIN, "in a flat aromatic ring")
    if n >= 4:
        return AtomType("S_3+6", CERTAIN, f"{n} neighbours")
    if n == 3:
        return AtomType("S_3+4", CERTAIN, "three neighbours")
    if n == 2:
        return AtomType("S_3+2", CERTAIN, "two neighbours")
    if n == 1:
        d = float(geo.distances(i)[0])
        if d < 1.70:
            return AtomType("S_2", CERTAIN,
                            f"one short bond at {d:.2f} A")
        return AtomType("S_3+2", LIKELY, f"one bond at {d:.2f} A")
    return AtomType("S_3+2", UNCERTAIN, "no neighbours")


_RULES = {
    "H": _hydrogen,
    "B": _boron,
    "C": _carbon,
    "N": _nitrogen,
    "O": _oxygen,
    "P": _phosphorus,
    "S": _sulfur,
}


def _by_coordination(i: int, cell, geo) -> AtomType:
    """The general rule: let the type table decide.

    A UFF type name states the coordination it was fitted for, so
    picking the type whose geometry character matches what the atom
    actually has needs no per-element code -- and gets Fe6+2 for
    octahedral iron and Fe3+2 for tetrahedral iron without either being
    written down anywhere.

    When nothing matches, the first type in the table is used and the
    assignment is marked uncertain.  That is the case UFF is least
    reliable for, and a metal in an unexpected coordination is
    precisely what a user needs to be told about rather than handed a
    confident-looking number for.
    """
    element = cell.elements[i]
    candidates = params.BY_ELEMENT[element]
    n = geo.coordination(i)

    if len(candidates) == 1:
        only = candidates[0]
        if only.coordination in (None, n) or n == 0:
            return AtomType(only.name, CERTAIN,
                            "the only type UFF gives this element")
        # One type, and it does not fit.  Zinc is the case to have in
        # mind: UFF fits it tetrahedral, and the octahedral zinc at
        # the centre of a Kuratowski node will happily take those
        # parameters and return a confident-looking number.
        return AtomType(
            only.name, UNCERTAIN,
            f"the only type UFF gives this element, fitted for "
            f"{only.coordination}-coordinate and this one has {n}")

    exact = [p for p in candidates if p.coordination == n]
    if exact:
        best = exact[0]
        note = ("" if len(exact) == 1 else
                f"; {len(exact)} {element} types share that "
                f"coordination and {best.name} is the first")
        return AtomType(best.name, LIKELY,
                        f"{n} neighbours{note}")

    best = min(candidates,
               key=lambda p: abs((p.coordination or 0) - n))
    return AtomType(
        best.name, UNCERTAIN,
        f"{n} neighbours, which no {element} type in UFF was fitted "
        f"for; {best.name} ({best.coordination}-coordinate) is the "
        f"closest")


# ======================================================================
#  TERMINAL ATOMS: LET THE BOND LENGTH DECIDE
# ======================================================================

# The hybridisations each element can be refined between.  Only
# elements whose types differ by hybridisation are here; there is no
# choice to make for a halogen or a metal.
REFINABLE = {
    "C": ("C_3", "C_2", "C_1"),
    "N": ("N_3", "N_2", "N_1"),
    "O": ("O_3", "O_2"),
    "S": ("S_3+2", "S_2"),
}


def _refine_terminal(types: list, cell, geo) -> None:
    """Re-decide the atoms that have only one neighbour.

    An atom with one bond has no angles, so the coordination rules
    above have almost nothing to work with -- and in a structure
    refined without hydrogens, which is most of them, the terminal
    carbon of an alkene, the carbon of a methyl group and the carbon of
    a nitrile all look identical: one neighbour, nothing else.

    What separates them is the bond length, and the force field
    already knows what length each hybridisation implies.  So the type
    is chosen by asking which one predicts the distance that was
    actually measured.  Butadiene without its hydrogens is the case
    this exists for: its terminal carbons are 1.34 A from their
    partners, which is a double bond and nothing else, and calling
    them sp3 puts the double bond in the middle of the molecule where
    the single bond belongs.

    Every candidate is scored against the types from the first pass,
    not against each other's refinements, so the result does not
    depend on the order the atoms happen to be in.
    """
    seeds = [t.name for t in types]
    for i in range(len(types)):
        if types[i].overridden or geo.coordination(i) != 1:
            continue
        candidates = REFINABLE.get(cell.elements[i])
        if not candidates:
            continue
        partner = seeds[geo.partners(i)[0]]
        distance = float(geo.distances(i)[0])
        scored = sorted(
            (abs(distance - _implied_length(c, partner)), c)
            for c in candidates)
        best, runner_up = scored[0], scored[1]
        types[i] = AtomType(
            best[1], LIKELY,
            f"one bond to {partner} at {distance:.2f} A, which suits "
            f"{best[1]} ({_implied_length(best[1], partner):.2f} A) "
            f"better than {runner_up[1]} "
            f"({_implied_length(runner_up[1], partner):.2f} A)")


def _implied_length(candidate: str, partner: str) -> float:
    """The bond length UFF predicts if this atom were that type.

    The bond order comes from the same pi-counting rule the order
    assignment uses, so the length asked about here is the length the
    calculation would actually go on to use.
    """
    from xtal.ff.uff import terms

    order = 1.0 + min(PI_CAPACITY.get(candidate, 0),
                      PI_CAPACITY.get(partner, 0))
    return terms.natural_bond_length(candidate, partner, order)


# ======================================================================
#  BOND ORDERS
# ======================================================================

# How many pi bonds each unsaturated type has to place.  An sp2 atom
# has one; an sp carbon has two, which is what makes CO2 O=C=O and
# acetylene a triple bond rather than each of them one bond short.
PI_CAPACITY = {
    "C_2": 1, "N_2": 1, "O_2": 1, "S_2": 1, "B_2": 1,
    "C_1": 2, "N_1": 2, "O_1": 1,
}
RESONANT_TYPES = frozenset({"C_R", "N_R", "O_R", "S_R"})

AMIDE_ORDER = 1.41          # UFF's bond order for the amide C-N bond


def _bond_orders(graph, names, aromatic: set) -> np.ndarray:
    """A bond order for every bond, inferred from the types.

    A crystal structure carries no bond orders -- a CIF has nowhere to
    put them -- so they have to come from somewhere, and UFF needs them
    for every bond length and every torsion barrier.

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
    """
    orders = np.ones(len(graph.bonds))
    spare = {i: PI_CAPACITY.get(names[i], 0)
             for i in range(graph.n_atoms)}

    for k, bond in enumerate(graph.bonds):
        if bond.i in aromatic and bond.j in aromatic:
            orders[k] = 1.5
            spare[bond.i] = spare[bond.j] = 0

    candidates = sorted((bond.distance, k)
                        for k, bond in enumerate(graph.bonds)
                        if orders[k] == 1.0)
    for _distance, k in candidates:
        bond = graph.bonds[k]
        shared = min(spare[bond.i], spare[bond.j])
        if shared <= 0:
            continue
        orders[k] = 1.0 + shared
        spare[bond.i] -= shared
        spare[bond.j] -= shared

    _amide_bonds(graph, names, orders)
    return orders


def _amide_bonds(graph, names, orders) -> None:
    """The C-N bond of an amide is 1.41 in UFF, not 1.

    Worth the special case: peptide and MOF-linker amides are common,
    and a single bond there is 0.06 A too long and noticeably too soft.
    """
    carbonyl = {
        bond.i if names[bond.i] == "C_2" else bond.j
        for k, bond in enumerate(graph.bonds)
        if orders[k] == 2.0
        and {names[bond.i], names[bond.j]} == {"C_2", "O_2"}
    }
    for k, bond in enumerate(graph.bonds):
        pair = {names[bond.i], names[bond.j]}
        if orders[k] != 1.0 or "C_2" not in pair:
            continue
        if not pair & {"N_2", "N_3", "N_R"}:
            continue
        if bond.i in carbonyl or bond.j in carbonyl:
            orders[k] = AMIDE_ORDER
