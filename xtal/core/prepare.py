"""
xtal.core.prepare
=================
From a deposited CIF to a cell a calculation can use.

A crystal structure as refined is a statement about the *average* over
every unit cell of a sample, and several things that are true of an
average are not true of any one cell:

* **Disorder.**  A site with an occupancy of 0.5 is an atom that is
  there in half the cells.  An engine given it computes a whole atom --
  and where two half-atoms are alternatives 0.4 A apart, a pair nobody
  has ever seen.
* **Solvent.**  The pores of an as-made framework hold whatever it was
  crystallised from, often with no hydrogens found.
* **Deuterium**, from a neutron experiment.
* **Missing hydrogens**, never located by X-rays.
* **Open metal sites** a refinement left bare -- the terminal ligand of
  an M3O trimer, disordered over F, OH and water and often not modelled.
* **The conventional cell**, four times the primitive one when the
  group is F-centred: MIL-101 is 16 000 atoms, and 4 000 in primitive.

Each is a separate function here returning ``(structure, message)``
and never mutating its argument, so the dialog can show what each would
do before it is done and each lands as its own undo step.  None of them
is a guess dressed up as a fact: every message says what was chosen.

**How disorder is ordered.**  Partial atoms are grouped into *units* --
the atoms that move together, by bonds among them and by the CIF's own
``_atom_site_disorder_group`` where it gives one.  Two units that would
put atoms too close to coexist are *alternatives*.  Then, per cluster of
alternatives, as many units are kept as the occupancies add up to
(rounded), the most occupied first; and a unit with no alternative is
kept as many times as its occupancy says it is present in the cell.  So
each place gets its most probable occupant -- including nothing -- and
the cell keeps the composition the refinement found: a counter-ion
spread over six positions at 1/6 is one ion, not none.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from xtal.core import bonding, p1
from xtal.core import elements as el
from xtal.core.neighbors import neighbor_pairs
from xtal.core.structure import Structure

#: An occupancy this close to 1 is 1: refinements write 0.999.
FULL = 0.999

#: Below this, two hydrogens are alternatives rather than neighbours.
#: The closest real pair is a water's own, 1.53 A; a methyl's are 1.78.
#: The alternative positions of a disordered methyl are 0.5-1.3 A
#: apart -- pbz-MOF-1 has them at 1.27.
H_CLASH = 1.4

#: Below this fraction of the covalent bond length, two heavy atoms are
#: alternatives.  A real bond is never shorter than about 85 % of it;
#: the alternatives in the shipped COD files are 0.44-1.12 A apart.
HEAVY_CLASH = 0.8

#: Occupancies further apart than this are not one disorder component.
#: Refinements tie a component's atoms to one free variable, so they
#: agree to the digits written; 0.02 allows for rounding.
SAME_COMPONENT = 0.02

#: Metals an M3O(RCO2)6 trimer is made of in the frameworks that have
#: one, and are trivalent in it -- which is what makes one anion and
#: two waters per trimer the neutral count.
TRIVALENT_TRIMER_METALS = frozenset({
    "Al", "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Ga", "In"})

#: Metal-ligand distance for a terminal ligand put on an open site, A.
TERMINAL_DISTANCE = {"F": 1.95, "O": 2.05}

#: Heavy-atom formulas of the solvents a framework is crystallised
#: from.  Heavy atoms only, because an X-ray structure seldom has the
#: solvent's hydrogens.  A lone O is water.
SOLVENTS = {
    "O": "water", "C1O1": "methanol", "C2O1": "ethanol",
    "C3N1O1": "DMF", "C5N1O1": "DEF", "C2O1S1": "DMSO",
    "C3O1": "acetone", "C4O1": "THF", "C2N1": "acetonitrile",
    "C4O2": "dioxane", "C1Cl2": "dichloromethane",
    "C1Cl3": "chloroform", "C5N1": "pyridine", "C6": "benzene",
    "C7": "toluene", "C5N1O1_": "NMP",
}


#: Below this, two oxygens are alternatives: nothing in a framework
#: puts two closer than a hydrogen bond allows, about 2.4 A (peroxide
#: aside).  MOF-808's disordered waters sit 1.45 A apart, which a bond
#: perceiver takes for an O-O bond.
O_CLASH = 2.0


def _clash(a: str, b: str, distance: float) -> bool:
    """Whether two atoms are too close to both be there."""
    if a in ("H", "D") and b in ("H", "D"):
        return distance < H_CLASH
    if a == "O" and b == "O":
        return distance < O_CLASH
    return distance < HEAVY_CLASH * (el.covalent_radius(a)
                                     + el.covalent_radius(b))


# ======================================================================
#  WHAT IS WRONG
# ======================================================================

@dataclass(frozen=True)
class Finding:
    """One thing between this structure and a calculation."""

    key: str            # the operation that addresses it
    text: str


@dataclass
class Diagnosis:
    findings: list[Finding] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.findings)

    def keys(self) -> list[str]:
        return [f.key for f in self.findings]

    def text(self) -> str:
        if not self.findings:
            return "nothing to prepare: no disorder, solvent, " \
                   "deuterium or missing hydrogens were found"
        return "\n".join(f"- {f.text}" for f in self.findings)


def diagnose(structure: Structure) -> Diagnosis:
    """What :func:`prepare` would change, and why, without changing it."""
    found = Diagnosis()
    partial = [s for s in structure.sites if s.occupancy < FULL]
    if partial:
        occupancies = sorted({round(s.occupancy, 3) for s in partial})
        shown = ", ".join(f"{o:g}" for o in occupancies[:5])
        found.findings.append(Finding(
            "disorder",
            f"{len(partial)} of {len(structure.sites)} sites are "
            f"partially occupied ({shown}"
            f"{', ...' if len(occupancies) > 5 else ''}): an engine "
            f"would count each as a whole atom"))
    deuterium = sum(1 for s in structure.sites if s.element == "D")
    if deuterium:
        found.findings.append(Finding(
            "deuterium", f"{deuterium} deuterium site(s), from a "
                         f"neutron experiment"))
    if not partial:
        molecules = _solvent_molecules(structure)
        if molecules:
            found.findings.append(Finding(
                "solvent", f"{len(molecules)} solvent molecule(s) in "
                           f"the pores ({_named(molecules)})"))
        open_sites = _open_trimer_sites(structure)
        if open_sites:
            found.findings.append(Finding(
                "cap", f"{len(open_sites)} M3O trimer(s) without the "
                       f"terminal ligands their charge asks for"))
    elements = {s.element for s in structure.sites}
    if "H" not in elements and "D" not in elements and "C" in elements:
        found.findings.append(Finding(
            "hydrogens", "no hydrogen at all: the X-ray structure "
                         "never located them"))
    letter = structure.space_group.hm.strip()[:1].upper()
    if letter in _CENTRINGS and not (
            letter == "R" and ":R" in structure.space_group.hm):
        factor = int(round(1 / abs(np.linalg.det(
            np.array(_CENTRINGS[letter])))))
        atoms = p1.expand(structure).n_atoms
        found.findings.append(Finding(
            "primitive", f"the cell is {letter}-centred, {factor} times "
                         f"the primitive one ({atoms} atoms against "
                         f"{atoms // factor})"))
    return found


# ======================================================================
#  THE OPERATIONS
# ======================================================================

def to_hydrogen(structure: Structure) -> tuple[Structure, str]:
    """Deuterium written as hydrogen, for a file anything can read.

    The engines already compute D as H (the energy surface is the
    same); this is for the structure itself.  The mass is what changes,
    and it matters only to vibration.
    """
    out = structure.copy()
    n = 0
    for site in out.sites:
        if site.element == "D":
            site.element = "H"
            n += 1
    out.touch()
    return out, (f"{n} deuterium site(s) written as hydrogen" if n
                 else "no deuterium")


#: A centred lattice's primitive vectors, as rows in the conventional
#: basis -- the International Tables' choices.  R is the hexagonal
#: setting; a rhombohedral-axes cell is primitive already.
_CENTRINGS = {
    "I": ((-0.5, 0.5, 0.5), (0.5, -0.5, 0.5), (0.5, 0.5, -0.5)),
    "F": ((0.0, 0.5, 0.5), (0.5, 0.0, 0.5), (0.5, 0.5, 0.0)),
    "C": ((0.5, 0.5, 0.0), (-0.5, 0.5, 0.0), (0.0, 0.0, 1.0)),
    "A": ((1.0, 0.0, 0.0), (0.0, 0.5, 0.5), (0.0, -0.5, 0.5)),
    "B": ((0.5, 0.0, 0.5), (0.0, 1.0, 0.0), (-0.5, 0.0, 0.5)),
    "R": ((2 / 3, 1 / 3, 1 / 3), (-1 / 3, 1 / 3, 1 / 3),
          (-1 / 3, -2 / 3, 1 / 3)),
}


def primitive(structure: Structure) -> tuple[Structure, str]:
    """The primitive cell of the group the file declares, every site
    keeping its label and its disorder group.

    From the declared centring and not by detecting symmetry again: a
    powder structure's coordinates are seldom good enough for a
    detection to find the F-centring of an 89 A cell, and the file has
    already said what the lattice is.  Done before ordering the
    disorder, because ordering breaks the centring.  In P1.
    """
    from xtal.core.lattice import Lattice
    from xtal.core.spacegroup import SpaceGroup

    symbol = structure.space_group.hm.strip()
    letter = symbol[:1].upper()
    if letter not in _CENTRINGS or (letter == "R" and ":R" in symbol):
        return structure, "the cell is already primitive"
    basis = np.array(_CENTRINGS[letter])
    factor = int(round(1 / abs(np.linalg.det(basis))))
    cell = p1.expand(structure)
    matrix = basis @ structure.lattice.matrix
    lattice = Lattice(matrix)
    cart = cell.frac @ structure.lattice.matrix
    frac = np.mod(cart @ np.linalg.inv(matrix), 1.0)
    pairs = neighbor_pairs(frac, lattice, 0.1, min_distance=0.0)
    first = list(range(cell.n_atoms))

    def root(a):
        while first[a] != a:
            first[a] = first[first[a]]
            a = first[a]
        return a

    for i, j in zip(pairs.i, pairs.j, strict=True):
        ri, rj = root(int(i)), root(int(j))
        if ri != rj:
            first[max(ri, rj)] = min(ri, rj)
    kept = [a for a in range(cell.n_atoms) if root(a) == a]
    if len(kept) * factor != cell.n_atoms:
        raise ValueError(
            f"the {letter}-centred cell did not reduce by {factor}: "
            f"{cell.n_atoms} atoms became {len(kept)}, so the atoms "
            f"are not where the centring puts them -- Find symmetry "
            f"first")
    sites = []
    for a in kept:
        site = structure.sites[int(cell.site_idx[a])].copy()
        site.frac = frac[a]
        sites.append(site)
    out = Structure(lattice=lattice, sites=sites,
                    space_group=SpaceGroup.p1(),
                    meta=dict(structure.meta),
                    bond_rules=dict(structure.bond_rules))
    return out, (f"primitive cell of the {letter}-centred lattice: "
                 f"{len(sites)} atoms, from {cell.n_atoms}")


@dataclass
class _Unit:
    atoms: list
    occupancy: float
    kind: tuple
    blocked: bool = False


def order_disorder(structure: Structure) -> tuple[Structure, str]:
    """Every partially occupied site resolved into whole atoms.

    See the module docstring for the rule.  The result is in P1 unless
    every orbit came out kept whole or dropped whole, in which case the
    group survives.
    """
    sites = structure.sites
    if all(s.occupancy >= FULL for s in sites):
        return structure, "nothing is disordered"
    cell = p1.expand(structure)
    lattice = structure.lattice
    n = cell.n_atoms
    occupancy = np.array([sites[int(k)].occupancy
                          for k in cell.site_idx])
    group = [str(sites[int(k)].props.get("disorder_group", "")).strip()
             for k in cell.site_idx]
    partial = occupancy < FULL
    elements = cell.elements
    rules = bonding.BondRules.from_dict(structure.bond_rules)

    pairs = neighbor_pairs(cell.frac, lattice, 2.6, min_distance=0.0)
    clashes = []
    bonds = []
    blocked = np.zeros(n, dtype=bool)
    for i, j, d in zip(pairs.i, pairs.j, pairs.distance, strict=True):
        i, j, d = int(i), int(j), float(d)
        if i == j:
            continue                 # an atom and its own next-cell copy
        a, b = elements[i], elements[j]
        if _clash(a, b, d):
            if partial[i] and partial[j]:
                clashes.append((i, j))
            elif partial[i]:
                blocked[i] = True
            elif partial[j]:
                blocked[j] = True
            continue
        if not (partial[i] and partial[j]):
            continue
        if _labelled(group[i]) and _labelled(group[j]):
            if group[i] != group[j]:
                continue
        elif abs(occupancy[i] - occupancy[j]) > SAME_COMPONENT:
            # One disorder component is refined with one occupancy (a
            # shared free variable), so atoms that differ are not one
            # component whatever bonds them: Mn-BTT's extra-framework
            # Mn at 0.06 and the DMF oxygen at 0.42 beside it.
            continue
        lo, hi = rules.cutoff(a, b)
        if lo <= d <= hi and rules.allows(a, b):
            bonds.append((d, i, j))

    members = _units(n, partial, bonds, clashes)
    units = [
        _Unit(atoms, float(occupancy[atoms].mean()),
              tuple(sorted({int(cell.site_idx[a]) for a in atoms})),
              bool(blocked[atoms].any()))
        for atoms in members.values()]
    unit_of = {a: u for u, unit in enumerate(units) for a in unit.atoms}

    conflicts = [set() for _ in units]
    inside = 0
    for i, j in clashes:
        u, v = unit_of[i], unit_of[j]
        if u == v:
            inside += 1
            continue
        conflicts[u].add(v)
        conflicts[v].add(u)

    keep = _choose(units, conflicts, cell, lattice)
    kept_atoms = sorted(a for u in keep for a in units[u].atoms)
    drop = sorted(set(np.flatnonzero(partial).tolist())
                  - set(kept_atoms))

    out = _without_atoms(structure, cell, drop)
    removed = _count(elements, drop)
    message = (f"ordered {int(partial.sum())} partial atoms: kept "
               f"{len(kept_atoms)}, removed {len(drop)}"
               f"{' (' + removed + ')' if removed else ''}")
    if inside:                                    # pragma: no cover
        message += (f"; {inside} pair(s) of alternatives ended up in "
                    f"one group -- look at them")
    differs = _against_formula(structure, out)
    if differs:
        message += "; " + differs
    if out.space_group.number == 1 and structure.space_group.number != 1:
        message += "; the result is in P1"
    return out, message


def _units(n, partial, bonds, clashes) -> dict:
    """The atoms that move together: partial atoms joined by bonds,
    shortest bond first, **never joining two atoms that clash**.

    Without that last rule a chain of bonds carries one alternative
    into the other -- ring atom to ring atom, across the 1.4 A that
    separates two orientations of a disordered ring -- and the two
    come out as one group that has to be kept or dropped together.
    """
    parent = list(range(n))
    against: dict[int, set] = {}
    for i, j in clashes:
        against.setdefault(i, set()).add(j)
        against.setdefault(j, set()).add(i)
    inside = {a: {a} for a in range(n) if partial[a]}
    avoid = {a: set(against.get(a, ())) for a in inside}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for _d, i, j in sorted(bonds):
        ri, rj = find(i), find(j)
        if ri == rj or avoid[ri] & inside[rj]:
            continue
        if len(inside[ri]) < len(inside[rj]):
            ri, rj = rj, ri
        parent[rj] = ri
        inside[ri] |= inside.pop(rj)
        avoid[ri] |= avoid.pop(rj)
    members: dict[int, list] = {}
    for a in np.flatnonzero(partial):
        members.setdefault(find(int(a)), []).append(int(a))
    return members


def _labelled(group: str) -> bool:
    """A disorder group that names an alternative: 1, 2, A, B.  ``-1``
    and friends mean "generated by symmetry", which says nothing about
    which atoms go together."""
    return bool(group) and group not in (".", "?") \
        and not group.startswith("-")


def _choose(units, conflicts, cell, lattice) -> set:
    """Which units to keep: see the module docstring."""
    keep: set = set()
    seen: set = set()
    order = sorted(range(len(units)),
                   key=lambda u: (-units[u].occupancy, units[u].kind,
                                  min(units[u].atoms)))
    lonely: dict[tuple, list] = {}
    for start in order:
        if start in seen:
            continue
        cluster, stack = [], [start]
        seen.add(start)
        while stack:
            u = stack.pop()
            cluster.append(u)
            for v in conflicts[u]:
                if v not in seen:
                    seen.add(v)
                    stack.append(v)
        if len(cluster) == 1 and not conflicts[start]:
            # Pooled by what the unit is, not which site it came from:
            # a chloride at 1/6 on six sites that clash with nothing is
            # one chloride, and per site each rounds to none.
            formula = tuple(sorted(cell.elements[a]
                                   for a in units[start].atoms))
            lonely.setdefault(formula, []).append(start)
            continue
        target = int(round(sum(units[u].occupancy for u in cluster)))
        for u in sorted(cluster, key=order.index):
            if len([k for k in keep if k in cluster]) >= target:
                break
            if units[u].blocked or conflicts[u] & keep:
                continue
            keep.add(u)
    for members in lonely.values():
        free = [u for u in members if not units[u].blocked]
        target = int(round(sum(units[u].occupancy for u in members)))
        keep.update(_spread(free, target, units, cell, lattice))
    return keep


def _spread(candidates, target, units, cell, lattice) -> list:
    """``target`` of ``candidates``, as far apart as they will go: the
    first, then repeatedly the one furthest from those already kept.
    Deterministic, so the same file gives the same cell."""
    if target <= 0 or not candidates:
        return []
    if target >= len(candidates):
        return list(candidates)
    centres = np.array([cell.frac[units[u].atoms].mean(axis=0)
                        for u in candidates])
    chosen = [0]
    nearest = _distances(centres, centres[0], lattice)
    while len(chosen) < target:
        k = int(np.argmax(nearest))
        chosen.append(k)
        nearest = np.minimum(nearest,
                             _distances(centres, centres[k], lattice))
    return [candidates[k] for k in chosen]


def _distances(points, point, lattice) -> np.ndarray:
    delta = points - point
    delta -= np.rint(delta)
    return np.linalg.norm(delta @ lattice.matrix, axis=1)


def _without_atoms(structure, cell, drop) -> Structure:
    """``structure`` less the P1 atoms in ``drop``, every survivor at
    full occupancy -- kept symmetric when whole orbits went."""
    drop = set(drop)
    by_site: dict[int, list] = {}
    for a in range(cell.n_atoms):
        by_site.setdefault(int(cell.site_idx[a]), []).append(a)
    whole = all(not (set(atoms) & drop) or set(atoms) <= drop
                for atoms in by_site.values())
    if whole:
        out = structure.copy()
        gone = [k for k, atoms in by_site.items() if set(atoms) <= drop]
        out.remove_sites(gone)
    else:
        from xtal.core import symmetry
        out = symmetry.reduce_to_p1(structure)
        if len(out.sites) != cell.n_atoms:        # pragma: no cover
            raise ValueError("the P1 cell does not match its expansion")
        out.remove_sites(sorted(drop))
    for site in out.sites:
        site.occupancy = 1.0
        site.props.pop("disorder_group", None)
    out.touch()
    return out


def _is_metal(symbol: str) -> bool:
    return symbol not in _NONMETALS and symbol not in _NOBLE_GASES


def _per_metal(counts: dict) -> dict:
    metals = [e for e in counts if _is_metal(e)]
    total = sum(counts[m] for m in metals)
    if not total:
        return {}
    return {e: counts[e] / total for e in counts}


_NONMETALS = frozenset({"H", "D", "B", "C", "N", "O", "F", "Si", "P",
                        "S", "Cl", "Se", "Br", "I", "As", "Te", "X"})
_NOBLE_GASES = frozenset({"He", "Ne", "Ar", "Kr", "Xe", "Rn"})


def _against_formula(before: Structure, after: Structure) -> str:
    """How the ordered cell's composition differs from the formula the
    CIF declares, per metal atom, where it differs by more than a
    tenth -- or ``""``.  A refinement's formula is its composition,
    so this is the one independent check an ordering has."""
    import re

    declared = str(before.meta.get("chemical_formula", ""))
    wanted: dict[str, float] = {}
    for symbol, number in re.findall(r"([A-Z][a-z]?)\s*([0-9.]*)",
                                     declared):
        wanted[symbol] = wanted.get(symbol, 0.0) + float(number or 1)
    got: dict[str, float] = {}
    for e in p1.expand(after).elements:
        got[e] = got.get(e, 0) + 1
    wanted, got = _per_metal(wanted), _per_metal(got)
    if not wanted or not got:
        return ""
    off = [(e, got.get(e, 0.0), wanted.get(e, 0.0))
           for e in sorted(set(wanted) | set(got))
           if abs(got.get(e, 0.0) - wanted.get(e, 0.0)) > 0.1]
    if not off:
        return ""
    shown = ", ".join(f"{e} {g:.2f} (CIF {w:.2f})" for e, g, w in off)
    return (f"per metal atom this cell differs from the CIF's formula: "
            f"{shown} -- missing hydrogens, defects the refinement "
            f"averaged over, or a formula that was never complete")


def _count(elements, atoms) -> str:
    counts: dict[str, int] = {}
    for a in atoms:
        counts[elements[a]] = counts.get(elements[a], 0) + 1
    return ", ".join(f"{n} {e}" for e, n in sorted(counts.items()))


# ---------------------------------------------------------- solvent

def _solvent_molecules(structure) -> list:
    """``(atoms, name)`` of every molecule that is a known solvent."""
    graph = bonding.graph(structure)
    cell = p1.expand(structure)
    out = []
    for fragment in graph.fragments():
        if fragment.periodic:
            continue
        heavy = [cell.elements[a] for a in fragment.atoms
                 if cell.elements[a] not in ("H", "D")]
        name = SOLVENTS.get(_heavy_formula(heavy))
        if name is not None:
            out.append((fragment.atoms, name))
    return out


def _heavy_formula(elements) -> str:
    counts: dict[str, int] = {}
    for e in elements:
        counts[e] = counts.get(e, 0) + 1
    if counts == {"O": 1}:
        return "O"
    return "".join(f"{e}{counts[e]}" for e in sorted(counts))


def _named(molecules) -> str:
    counts: dict[str, int] = {}
    for _atoms, name in molecules:
        counts[name] = counts.get(name, 0) + 1
    return ", ".join(f"{n} {name}" for name, n in sorted(counts.items()))


def remove_solvent(structure: Structure) -> tuple[Structure, str]:
    """Every molecule in the pores that is a known solvent, removed.

    Known by its heavy atoms, because X-ray solvent seldom has its
    hydrogens: a lone oxygen is water, C3NO is DMF.  Anything else
    that is not bonded into the framework is *left*, and named: an
    isolated chloride is a counter-ion, not solvent, and taking it out
    would leave the framework charged.  Solvent bound to a metal is
    part of the framework and stays.
    """
    molecules = _solvent_molecules(structure)
    if not molecules:
        return structure, "no solvent molecules"
    cell = p1.expand(structure)
    drop = sorted(a for atoms, _name in molecules for a in atoms)
    out = _without_atoms(structure, cell, drop)
    left = [f for f in bonding.graph(out).fragments() if not f.periodic]
    message = f"removed {len(molecules)} solvent molecule(s) " \
              f"({_named(molecules)})"
    if left:
        message += (f"; {len(left)} other molecule(s) left in place -- "
                    f"counter-ions or guests, which only you can tell")
    return out, message


# ---------------------------------------------------------- trimers

def _trimers(structure):
    """Every M(III)3O trimer as ``(mu3-O, [(metal, ligand or None)])``,
    in the P1 cell of ``structure``.

    A mu3-oxide is an oxygen bonded to exactly three of
    :data:`TRIVALENT_TRIMER_METALS`.  A metal's terminal ligand is the
    neighbour opposite that oxide -- within 30 degrees of straight
    through the metal -- that is bonded to nothing else heavy: an F, or
    an O with nothing but hydrogens besides the metal.  ``None`` where
    the octahedron's sixth corner is empty.
    """
    cell = p1.expand(structure)
    graph = bonding.graph(structure)
    elements = cell.elements
    matrix = structure.lattice.matrix
    out = []
    for o in range(cell.n_atoms):
        if elements[o] != "O":
            continue
        around = graph.neighbors_with_images(o)
        metals = [(j, t) for j, t in around
                  if elements[j] in TRIVALENT_TRIMER_METALS]
        if len(metals) != 3 or len(around) != 3:
            continue
        members = []
        for m, t in metals:
            axis = (cell.frac[m] + t - cell.frac[o]) @ matrix
            axis /= np.linalg.norm(axis)
            ligand = None
            for j, u in graph.neighbors_with_images(m):
                if elements[j] not in ("O", "F") or j == o:
                    continue
                bond = (cell.frac[j] + u - cell.frac[m]) @ matrix
                if bond @ axis / np.linalg.norm(bond) < 0.866:
                    continue
                heavy = [k for k in graph.neighbors(j)
                         if elements[k] not in ("H", "D") and k != m]
                if not heavy:
                    ligand = j
            members.append((m, ligand))
        out.append((o, members))
    return out


def _free_anions(structure) -> int:
    """Halide ions in the pores: single F, Cl, Br or I atoms bonded to
    nothing.  Each is a trimer's anion that is not on the trimer."""
    graph = bonding.graph(structure)
    elements = p1.expand(structure).elements
    return sum(1 for a in range(len(elements))
               if elements[a] in ("F", "Cl", "Br", "I")
               and not graph.neighbors(a))


def _trimer_plan(structure) -> list:
    """``(mu3-O, members, anions wanted)`` for every trimer whose
    terminal ligands are not already what charge balance asks.

    Each M(III)3O(RCO2)6 trimer is +1 and needs one anion.  A halide in
    the pores is one -- Al-soc-MOF-1 is [Al3O(abtc)1.5(H2O)3]+ Cl- --
    so that many trimers keep three waters, and the rest carry their
    anion themselves: one F or OH and two waters.
    """
    cell = p1.expand(structure)
    graph = bonding.graph(structure)
    trimers = sorted(_trimers(structure), key=lambda t: t[0])
    bound = len(trimers) - _free_anions(structure)
    plan = []
    for rank, (o, members) in enumerate(trimers):
        wanted = 1 if rank < bound else 0
        if _roles(cell, graph, members) != (wanted, 3 - wanted):
            plan.append((o, members, wanted))
    return plan


def _open_trimer_sites(structure) -> list:
    """The trimers :func:`complete_trimers` would change."""
    return _trimer_plan(structure)


def _roles(cell, graph, members):
    """``(anions, waters)`` among the three terminal ligands, or
    ``None`` if a site is empty or a ligand is neither."""
    anions = waters = 0
    for _m, ligand in members:
        if ligand is None:
            return None
        if cell.elements[ligand] == "F":
            anions += 1
            continue
        hydrogens = sum(1 for k in graph.neighbors(ligand)
                        if cell.elements[k] in ("H", "D"))
        if hydrogens == 1:
            anions += 1
        elif hydrogens == 2:
            waters += 1
        else:
            return None
    return anions, waters


def complete_trimers(structure: Structure) -> tuple[Structure, str]:
    """Each M(III)3O(RCO2)6 trimer given the terminal ligands its
    charge asks for.

    Three M(III) are +9, the mu3-oxide -2 and six carboxylates -6,
    which leaves +1 and one anion.  A halide in the pores is that anion
    for one trimer, which then keeps three waters; every other trimer
    carries it itself -- an F already there, else one terminal oxygen
    made hydroxide, or fluoride on an empty site (the MIL materials
    are made with HF and their formulas carry it) -- with two waters.
    A new ligand goes on the line from the mu3-O through the metal,
    where the octahedron's sixth corner is, and the hydrogens of the
    waters and the hydroxide are placed here, because only the trimer
    knows which is which: a planner reading valences alone makes all
    three hydroxide, and the trimer -2.
    """
    if not _trimers(structure):
        return structure, "no M3O trimers"
    if not _trimer_plan(structure):
        return structure, "every M3O trimer already has the ligands " \
                          "its charge asks for"
    from xtal.core import symmetry
    from xtal.core.site import Site

    out = symmetry.reduce_to_p1(structure) \
        if structure.space_group.number != 1 else structure.copy()
    plan = _trimer_plan(out)
    free = _free_anions(out)
    cell = p1.expand(out)
    graph = bonding.graph(out)
    matrix = out.lattice.matrix
    inverse = np.linalg.inv(matrix)
    fixed = {"F": 0, "OH": 0, "water": 0}
    for o, members, wanted in plan:
        # Existing hydrogens on the ligands are the refinement's; a
        # trimer being completed gets its own.
        for _m, lig in members:
            if lig is None:
                continue
            for k in graph.neighbors(lig):
                if cell.elements[k] in ("H", "D"):
                    out.sites[k].props["prepare_drop"] = True
        anions = sum(1 for _m, lig in members
                     if lig is not None and cell.elements[lig] == "F")
        for m, ligand in sorted(members, key=lambda p: (
                p[1] is None, p[0])):
            if ligand is not None and cell.elements[ligand] == "F":
                continue
            axis = cell.frac[m] - cell.frac[o]
            axis -= np.rint(axis)
            axis = axis @ matrix
            axis /= np.linalg.norm(axis)
            metal = cell.frac[m] @ matrix
            anion = anions < wanted
            if ligand is None:
                kind = "F" if anion else "O"
                where = metal + TERMINAL_DISTANCE[kind] * axis
                out.sites.append(Site(kind, np.mod(where @ inverse, 1.0),
                                      label=f"{kind}cap{len(out.sites)}"))
                if kind == "F":
                    anions += 1
                    fixed["F"] += 1
                    continue
                oxygen = where
            else:
                shift = cell.frac[ligand] - cell.frac[m]
                shift -= np.rint(shift)
                oxygen = metal + shift @ matrix
            if anion:
                anions += 1
                fixed["OH"] += 1
            else:
                fixed["water"] += 1
            for h in _hydrogens_on(oxygen, oxygen - metal,
                                   1 if anion else 2):
                out.sites.append(Site("H", np.mod(h @ inverse, 1.0),
                                      label=f"Hcap{len(out.sites)}"))
    stale = [k for k, site in enumerate(out.sites)
             if site.props.pop("prepare_drop", False)]
    out.remove_sites(stale)
    out.touch()
    said = (f"completed {len(plan)} M3O trimer(s): {fixed['F']} F "
            f"added, {fixed['OH']} OH and {fixed['water']} water")
    if free:
        said += (f"; {free} halide ion(s) in the pores are the anions "
                 f"of as many trimers, which keep three waters")
    return out, said


def _hydrogens_on(oxygen, outward, count: int) -> list:
    """Hydrogen positions on a terminal O: 0.97 A, pointing away from
    the metal, H-O-H 104.5 degrees for a water."""
    outward = outward / np.linalg.norm(outward)
    side = np.cross(outward, [1.0, 0.0, 0.0])
    if np.linalg.norm(side) < 0.1:
        side = np.cross(outward, [0.0, 1.0, 0.0])
    side /= np.linalg.norm(side)
    if count == 1:
        # M-O-H of about 120 degrees.
        direction = np.cos(np.radians(60)) * outward + \
            np.sin(np.radians(60)) * side
        return [oxygen + 0.97 * direction]
    half = np.radians(104.5 / 2)
    return [oxygen + 0.97 * (np.cos(half) * outward + sign
                             * np.sin(half) * side)
            for sign in (1.0, -1.0)]


# ---------------------------------------------------------- the lot

#: The order the steps run in, and why: deuterium first so everything
#: after sees hydrogen; the primitive cell before the disorder is
#: ordered, because ordering breaks the centring; solvent after, since
#: a disordered solvent is only a molecule once it is ordered; the
#: trimers' ligands before the hydrogens, which then complete the
#: waters as well as the linkers.
STEPS = ("deuterium", "primitive", "disorder", "solvent", "cap",
         "hydrogens")

LABELS = {
    "deuterium": "Write deuterium as hydrogen",
    "primitive": "Reduce to the primitive cell",
    "disorder": "Order the disorder",
    "solvent": "Remove solvent from the pores",
    "cap": "Complete M3O trimers' terminal ligands",
    "hydrogens": "Add missing hydrogens",
}


#: Metals whose M6O8 clusters are Zr6O4(OH)4-like: UiO-66, MOF-808,
#: NU-1000, PCN-222 and the rest of the zirconium family.
HEXANUCLEAR_METALS = frozenset({"Zr", "Hf", "Ce", "Th", "U"})


def _arene_hydrogens(structure) -> list:
    """Cartesian positions for the hydrogens of every six-membered
    carbon ring, by ring membership and not by bond length.

    A powder structure's bonds cannot be trusted to say what a carbon
    is: MIL-100's btc rings have C-C bonds of 1.51 A, a single bond's
    length, and a planner reading them gives a ring CH two hydrogens.
    A carbon in a benzene ring with two ring neighbours has one, in the
    ring's plane along the outward bisector, 1.08 A out.
    """
    cell = p1.expand(structure)
    graph = bonding.graph(structure)
    matrix = structure.lattice.matrix
    elements = cell.elements
    rings = _six_rings(graph, elements, cell.frac)
    out, done = [], set()
    for ring in rings:
        for k, (atom, position) in enumerate(ring):
            if atom in done:
                continue
            if len(graph.neighbors(atom)) != 2:
                continue
            before = ring[k - 1][1]
            after = ring[(k + 1) % 6][1]
            here = position @ matrix
            bisector = (here - before @ matrix) + (here - after @ matrix)
            norm = np.linalg.norm(bisector)
            if norm < 1e-6:
                continue
            out.append(here + 1.08 * bisector / norm)
            done.add(atom)
    return out


def _six_rings(graph, elements, frac) -> list:
    """Each six-membered all-carbon ring once, as ``(atom, fractional
    position)`` in order, with positions carried across cell faces so
    the ring is whole."""
    rings, seen = [], set()
    carbons = [a for a in range(len(elements)) if elements[a] == "C"]
    for start in carbons:
        stack = [(start, np.zeros(3), [(start, np.zeros(3))])]
        while stack:
            atom, shift, path = stack.pop()
            if len(path) > 6:
                continue
            for j, t in graph.neighbors_with_images(atom):
                if elements[j] != "C":
                    continue
                where = shift + t
                if j == start and len(path) == 6 and \
                        not np.any(where):
                    key = frozenset(a for a, _ in path)
                    if key not in seen:
                        seen.add(key)
                        rings.append([(a, frac[a] + s)
                                      for a, s in path])
                    continue
                if any(a == j for a, _ in path) or len(path) == 6:
                    continue
                stack.append((j, where, path + [(j, where)]))
    return rings


def _hydroxide_hydrogens(structure) -> list:
    """Cartesian positions for the four mu3-OH hydrogens of every
    M6O8 core that has none.

    Zr6O4(OH)4: of the eight oxygens capping an octahedron's faces,
    four are hydroxide, on alternate faces -- the four that pairwise
    share exactly one metal.  Without them each core is -4.  The
    hydrogen points out from the cluster's centre, 0.97 A.
    """
    cell = p1.expand(structure)
    graph = bonding.graph(structure)
    matrix = structure.lattice.matrix
    elements = cell.elements
    capping = {}
    for o in range(cell.n_atoms):
        if elements[o] != "O":
            continue
        around = graph.neighbors_with_images(o)
        metals = [(j, t) for j, t in around
                  if elements[j] in HEXANUCLEAR_METALS]
        if len(metals) != 3:
            continue
        if any(elements[j] in ("H", "D") for j, _t in around):
            capping[o] = None             # protonated already
            continue
        capping[o] = metals
    # One cluster is the metals its capping oxygens join: union-find,
    # so that an oxygen bridging two partial groups joins them.
    parent: dict[int, int] = {}

    def root(m):
        parent.setdefault(m, m)
        while parent[m] != m:
            parent[m] = parent[parent[m]]
            m = parent[m]
        return m

    for metals in capping.values():
        if metals is None:
            continue
        first = root(metals[0][0])
        for j, _t in metals[1:]:
            parent[root(j)] = first
    groups: dict[int, list] = {}
    for o, metals in capping.items():
        if metals is not None:
            groups.setdefault(root(metals[0][0]), []).append(o)
    out = []
    for oxygens in groups.values():
        if len(oxygens) != 8:
            continue
        chosen = []
        for o in oxygens:
            mine = {j for j, _t in capping[o]}
            if all(len(mine & {j for j, _t in capping[c]}) == 1
                   for c in chosen):
                chosen.append(o)
            if len(chosen) == 4:
                break
        if len(chosen) != 4:
            continue
        # Every capping oxygen by its nearest image to the first: the
        # cluster is a few angstroms across and the cell tens, so that
        # puts them all round one centre even across a cell face.
        reference = cell.frac[oxygens[0]]
        offset = {o: (cell.frac[o] - reference)
                  - np.rint(cell.frac[o] - reference) for o in oxygens}
        centre = np.mean([offset[o] for o in oxygens], axis=0) @ matrix
        for o in chosen:
            outward = offset[o] @ matrix - centre
            here = cell.frac[o] @ matrix
            out.append(here + 0.97 * outward / np.linalg.norm(outward))
    return out


def _add_hydrogens(structure):
    """Hydrogens, in three passes: the arene rings and the Zr6 cores
    by rule -- see their functions for why rules and not valences --
    then the planner for everything else."""
    from xtal.core.site import Site
    from xtal.ff import hydrogens

    out = structure.copy()
    inverse = np.linalg.inv(out.lattice.matrix)
    by_rule = []
    for kind, finder in (("ring", _arene_hydrogens),
                         ("hydroxide", _hydroxide_hydrogens)):
        positions = finder(out)
        for cart in positions:
            out.sites.append(Site("H", np.mod(cart @ inverse, 1.0),
                                  label=f"H{kind}{len(out.sites)}"))
        where = "arene rings" if kind == "ring" \
            else "M6 cores (mu3-OH)"
        if positions:
            by_rule.append(f"{len(positions)} on {where}")
        out.touch()
    plan = hydrogens.plan(out)
    planar = _on_planar_carbon(out, plan.sites) if plan else []
    added = [site for k, site in enumerate(plan.sites)
             if k not in planar] if plan else []
    if added:
        out.sites.extend(site.copy() for site in added)
        out.touch()
        by_rule.append(f"{len(added)} more by valence")
    if planar:
        by_rule.append(
            f"{len(planar)} the valence rules asked for were not added: "
            f"each was on a carboxylate or a planar three-coordinate "
            f"carbon, sp2 and full -- the refinement bent its angles")
    return out, "; ".join(by_rule) or "no hydrogens to add"


#: Angles around a three-coordinate atom summing above this are a
#: plane: 360 for sp2, 328 for a tetrahedral centre with one bond
#: missing.  The sum survives a refinement that bends the angles one
#: at a time, which is why it is read and not the bond lengths.
PLANAR_SUM = 350.0


def _carboxylate(cell, graph, carbon, around) -> bool:
    """Two oxygens on the carbon, bonded to nothing else but metals and
    hydrogen: a carboxylate, sp2 and full at three bonds whatever its
    angles say.  MIL-100's powder model bends one to 337 degrees."""
    oxygens = [j for j, _t in around if cell.elements[j] == "O"]
    if len(oxygens) < 2:
        return False
    for o in oxygens:
        for k in graph.neighbors(o):
            other = cell.elements[k]
            if k != carbon and other not in ("H", "D") \
                    and not _is_metal(other):
                return False
    return True


def _on_planar_carbon(structure, planned) -> list:
    """Which of ``planned`` sit on a carbon that already has three
    neighbours in a plane."""
    cell = p1.expand(structure)
    graph = bonding.graph(structure)
    matrix = structure.lattice.matrix
    out = []
    for k, site in enumerate(planned):
        delta = cell.frac - site.frac
        delta -= np.rint(delta)
        distance = np.linalg.norm(delta @ matrix, axis=1)
        parent = int(np.argmin(distance))
        if cell.elements[parent] != "C":
            continue
        around = graph.neighbors_with_images(parent)
        arms = [(cell.frac[j] + t - cell.frac[parent]) @ matrix
                for j, t in around]
        if len(arms) != 3:
            continue
        if _carboxylate(cell, graph, parent, around):
            out.append(k)
            continue
        units = [a / np.linalg.norm(a) for a in arms]
        total = sum(np.degrees(np.arccos(np.clip(units[a] @ units[b],
                                                 -1, 1)))
                    for a, b in ((0, 1), (0, 2), (1, 2)))
        if total > PLANAR_SUM:
            out.append(k)
    return out


OPERATIONS = {
    "deuterium": to_hydrogen,
    "primitive": primitive,
    "disorder": order_disorder,
    "solvent": remove_solvent,
    "cap": complete_trimers,
    "hydrogens": _add_hydrogens,
}


def prepare(structure: Structure, steps=STEPS
            ) -> tuple[Structure, list[str]]:
    """The chosen steps, in :data:`STEPS` order, and what each did."""
    unknown = set(steps) - set(STEPS)
    if unknown:
        raise ValueError(f"no preparation step called "
                         f"{', '.join(sorted(unknown))}; the steps are "
                         f"{', '.join(STEPS)}")
    said = []
    for step in STEPS:
        if step in steps:
            structure, message = OPERATIONS[step](structure)
            said.append(message)
    return structure, said
