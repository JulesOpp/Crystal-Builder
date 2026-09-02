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

#: Coordination geometry, and the ring perception over it, both live
#: in the core now: a bond graph plus coordinates is not a force
#: field's private business, and the viewport reads the same answers.
#: Re-exported because :mod:`xtal.ff.hydrogens` builds one directly.
Geometry = bonding.Geometry

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
    geometry = Geometry(cell, graph)
    rings = bonding.aromatic_rings(cell, graph, geometry)
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
    _apply_stated_orders(types, cell, graph, geometry)
    # The orders are the core's -- counting pi bonds is chemistry, and
    # the viewport reads the same numbers.  What is added here is the
    # one place UFF disagrees with a plain bond order, and it is UFF's
    # own convention rather than a fact about the molecule.
    orders = np.array(bonding.orders(structure, rules), dtype=float)
    _amide_bonds(graph, [t.name for t in types], orders)
    return Typing(tuple(types), orders,
                  tuple(tuple(r) for r in rings))


def _refuse_unknown_elements(cell) -> None:
    """Refuse before typing rather than during it, and say which.

    A dummy atom is called out separately because it is the one that
    arrives by an ordinary gesture -- Add centroid puts one in -- and
    "no parameters, the field stops at lawrencium" is the wrong
    explanation for a marker that was never chemistry to begin with.
    """
    unknown = sorted({e for e in cell.elements
                      if not params.has_element(e)})
    if not unknown:
        return
    dummies = [e for e in unknown if e in bonding.DUMMY_ELEMENTS]
    if dummies:
        raise TypingError(
            "a force field has nothing to say about a dummy atom ("
            + ", ".join(dummies)
            + "); delete it, or change its element, before running "
              "one")
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
#  STATED ORDERS: LET THE USER DECIDE
# ======================================================================

#: The type an atom takes when the pi count at it is *stated*, indexed
#: by that count: none, one, two.  Only the elements whose UFF types
#: are a choice of hybridisation are here.  Sulfur and phosphorus are
#: deliberately absent: their type names encode an oxidation state
#: rather than a hybridisation -- ``S_3+6`` is a sulfate sulfur, not an
#: sp3 one -- and their coordination already decides between them.
BY_STATED_PI = {
    "C": ("C_3", "C_2", "C_1"),
    "N": ("N_3", "N_2", "N_1"),
    "O": ("O_3", "O_2"),
    "B": ("B_3", "B_2"),
}

#: The resonant type for an element, for an atom the user called
#: aromatic.
BY_STATED_RESONANCE = {"C": "C_R", "N": "N_R", "O": "O_R", "S": "S_R"}


def _apply_stated_orders(types, cell, graph, geo) -> None:
    """Retype the atoms whose bond orders the user has stated.

    The geometry rules above read angles, which is the only evidence
    there is until somebody says otherwise.  Set Bond Type is somebody
    saying otherwise, and a stated order settles the hybridisation:
    two single bonds on a carbon is sp3 whether the model has them
    drawn at 109 degrees or at 180.  This is what makes *Add
    hydrogens* put two hydrogens on that carbon rather than one -- the
    valence was never the part that was wrong.

    A statement that contradicts the coordination is not applied: four
    neighbours and a stated double bond describes no carbon, and the
    angles are better evidence than an order that cannot be right.
    """
    resonant = bonding.stated_resonant(graph)
    for atom, pi in bonding.stated_pi(graph).items():
        if types[atom].overridden:
            continue                    # a hand-set type outranks it
        element = cell.elements[atom]
        neighbours = geo.coordination(atom)
        if atom in resonant:
            name = BY_STATED_RESONANCE.get(element)
            room = 3                    # resonant types are trigonal
        else:
            candidates = BY_STATED_PI.get(element)
            if candidates is None:
                continue
            pi = int(round(pi))
            name = candidates[min(pi, len(candidates) - 1)]
            # sp3 has four directions to share out, sp2 three, sp two.
            room = 4 - min(pi, 2)
        if name is None or neighbours > room:
            continue
        types[atom] = AtomType(
            name, CERTAIN,
            "every bond at it is stated, and the user called it "
            "aromatic" if atom in resonant else
            f"every bond at it is stated, and they carry "
            f"{pi:g} pi bond(s)")


# ======================================================================
#  BOND ORDERS
# ======================================================================

# How many pi bonds each unsaturated type has to place.  The orders
# themselves come from :func:`xtal.core.bonding.orders`; this table is
# what is left of the old inference, and it survives because
# ``_implied_length`` has to ask what length a *candidate* type would
# imply -- a question about a type that no atom has yet been given, so
# there is nothing in the graph to look it up from.
PI_CAPACITY = {
    "C_2": 1, "N_2": 1, "O_2": 1, "S_2": 1, "B_2": 1,
    "C_1": 2, "N_1": 2, "O_1": 1,
}
RESONANT_TYPES = frozenset({"C_R", "N_R", "O_R", "S_R"})

AMIDE_ORDER = 1.41          # UFF's bond order for the amide C-N bond


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
