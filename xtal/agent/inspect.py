"""
xtal.agent.inspect
==================
One call that says what a structure is and what is wrong with it.

The agent's equivalent of looking at the Info panel, the site table
and the viewport at once, in numbers.  It reads; it never changes the
structure, and it never perceives bonds the structure does not
already have -- the graph it reports is the one the user would see.

Every finding is a :class:`~xtal.agent.diagnostics.Diagnostic` with a
closed code, so an agent can act on it without parsing prose.  Each
kind is capped at :data:`MAX_PER_CODE` with a count of the rest: a
list of 400 close contacts is one problem, not 400.
"""

from __future__ import annotations

from collections import Counter

import numpy as np

from xtal.agent.answers import Inspection
from xtal.agent.diagnostics import Diagnostic
from xtal.core import bonding, p1, properties, symmetry
from xtal.core import elements as el

#: The tolerance the detected group is reported at.  Looser than
#: spglib's own 1e-5, because a group that 1e-5 misses on a file
#: written to four decimals is the group the file means: MFU-4l is
#: Pmmm at 1e-5, P4/mmm at 1e-3 and the Fm-3m it was deposited in
#: from 0.01 up.  The same argument ``p1.SPECIAL_POSITION_TOL`` makes.
DEFAULT_SYMPREC = 1e-2

#: Most findings of one code to list before summarising the rest.
MAX_PER_CODE = 8

#: An unbonded pair closer than this fraction of the sum of covalent
#: radii is a contact no chemistry makes.
CONTACT_FRACTION = 0.8

#: A bond further than this fraction from the sum of covalent radii is
#: worth a second look -- unless a metal is at either end, where long
#: dative bonds are the rule.
BOND_DEVIATION = 0.3

#: The elements whose valence caps their coordination hard enough
#: that exceeding it always means a misplaced atom or loose rules.
MAX_COORDINATION = {"H": 1, "C": 4, "F": 1}

_NONMETALS = frozenset({
    "H", "D", "He", "B", "C", "N", "O", "F", "Ne", "Si", "P", "S",
    "Cl", "Ar", "As", "Se", "Br", "Kr", "Te", "I", "Xe", "At", "Rn",
    "X",
})

# Which prepare finding is which code: the finding's key is the
# operation that addresses it.
_PREPARE_CODES = {
    "disorder": "DISORDER",
    "deuterium": "DEUTERIUM",
    "solvent": "SOLVENT",
    "cap": "OPEN_TRIMERS",
    "hydrogens": "MISSING_HYDROGENS",
    "duplicates": "DUPLICATE_SITES",
    "primitive": "CENTRED_CELL",
}


def inspect(structure, symprec: float = DEFAULT_SYMPREC) -> Inspection:
    """Everything worth knowing about ``structure``, and what is wrong."""
    found: list[Diagnostic] = []
    info = properties.info(structure)
    cell = p1.expand(structure)
    coincident = p1.coincidence_warning(structure)
    if coincident:
        found.append(Diagnostic("COINCIDENT_ATOMS", coincident))
    for warning in structure.meta.get("warnings", []):
        # The reader says the coincidence sentence too; it is one
        # finding, and the code that names its remedy is the one kept.
        if str(warning) != coincident:
            found.append(Diagnostic("READ_WARNING", str(warning)))

    detected = _detected(structure, symprec, found)
    graph = bonding.graph(structure)
    coordination = graph.coordination()

    sites = _sites(structure, cell, graph, coordination)
    fragments = [
        {"kind": f.kind, "n_atoms": len(f),
         "formula": _formula(cell.elements[a] for a in f.atoms)}
        for f in graph.fragments()]

    if not coincident:
        # Everything below reads distances, and a cell with two atoms
        # in one place answers all of it wrongly.  The one diagnostic
        # that matters then is the one already given.
        found.extend(_prepare_findings(structure))
        found.extend(_contacts(structure, cell, graph))
        found.extend(_coordination(structure, cell, coordination))
        found.extend(_bond_lengths(structure, cell, graph))
    markers = sum(1 for e in cell.elements if el.is_dummy(e))
    if markers:
        found.append(Diagnostic(
            "MARKERS_PRESENT",
            f"{markers} dummy atom(s) in the cell"))
    if info.net_charge is not None and abs(info.net_charge) > 1e-3:
        found.append(Diagnostic(
            "CELL_NOT_NEUTRAL",
            f"the site charges sum to {info.net_charge:+.3f} e"))

    a, b, c, alpha, beta, gamma = (float(x) for x in info.parameters)
    return Inspection(
        formula=info.formula, z=info.z, n_sites=info.n_sites,
        n_atoms=info.n_atoms,
        cell={"a": a, "b": b, "c": c, "alpha": alpha, "beta": beta,
              "gamma": gamma},
        volume=float(info.volume), density=float(info.density),
        space_group=info.space_group,
        space_group_number=info.space_group_number,
        detected_space_group=detected, symprec=symprec,
        net_charge=info.net_charge, n_bonds=len(graph.bonds),
        fragments=fragments, sites=sites,
        diagnostics=_capped(found))


def _detected(structure, symprec, found) -> str:
    """The group spglib finds, or the declared one if it cannot say."""
    try:
        detected = symmetry.detect(structure, symprec)
    except ValueError as exc:
        found.append(Diagnostic(
            "SYMMETRY_NOTE", f"no group could be detected at "
                             f"{symprec:g} A: {exc}"))
        return structure.space_group.short_name
    name = detected.space_group.short_name
    if detected.number != structure.space_group.number:
        found.append(Diagnostic(
            "SYMMETRY_NOTE",
            f"the declared group is {structure.space_group.short_name} "
            f"(#{structure.space_group.number}) but the coordinates "
            f"have {name} (#{detected.number}) at {symprec:g} A"))
    return name


def _sites(structure, cell, graph, coordination) -> list[dict]:
    """One row per asymmetric site, read off its first atom."""
    rows = []
    for k, site in enumerate(structure.sites):
        atoms = cell.indices_of_site(k)
        if not len(atoms):
            continue
        first = int(atoms[0])
        neighbours = sorted(
            ((cell.elements[j], round(float(bond.distance), 3))
             for j, bond in zip(graph.neighbors(first),
                                graph.bonds_of(first), strict=True)),
            key=lambda pair: pair[1])
        rows.append({
            "index": k,
            "label": site.label or site.element,
            "element": site.element,
            "frac": [round(float(x), 5) for x in site.frac],
            "occupancy": float(site.occupancy),
            "multiplicity": len(atoms),
            "first_atom": first,
            "coordination": int(coordination[first]),
            "neighbours": neighbours,
        })
    return rows


def _formula(symbols) -> str:
    counts = Counter(symbols)
    order = sorted(counts, key=lambda e: (e != "C", e != "H", e))
    return "".join(f"{e}{counts[e] if counts[e] > 1 else ''}"
                   for e in order)


def _name(structure, cell, atom) -> str:
    site = structure.sites[int(cell.site_idx[atom])]
    return f"{site.label or site.element} (atom {atom})"


def _prepare_findings(structure) -> list[Diagnostic]:
    from xtal.core import prepare

    return [Diagnostic(_PREPARE_CODES.get(f.key, "SYMMETRY_NOTE"),
                       f.text)
            for f in prepare.diagnose(structure).findings]


def _contacts(structure, cell, graph) -> list[Diagnostic]:
    from xtal.core.neighbors import neighbor_pairs

    if not cell.n_atoms:
        return []
    radii = np.array([el.covalent_radius(e) for e in cell.elements])
    cutoff = CONTACT_FRACTION * 2 * float(radii.max())
    pairs = neighbor_pairs(cell.frac, structure.lattice, cutoff=cutoff,
                           min_distance=1e-3)
    bonded = {(min(b.i, b.j), max(b.i, b.j)) for b in graph.bonds}
    out = []
    seen = set()
    for i, j, d in zip(pairs.i, pairs.j, pairs.distance, strict=True):
        i, j = int(i), int(j)
        a, b = cell.elements[i], cell.elements[j]
        if el.is_dummy(a) or el.is_dummy(b):
            continue
        if d >= CONTACT_FRACTION * (radii[i] + radii[j]):
            continue
        if (min(i, j), max(i, j)) in bonded:
            continue
        # One report per pair of *sites*: the rest of the orbit is the
        # same contact seen through the group.
        key = tuple(sorted((int(cell.site_idx[i]),
                            int(cell.site_idx[j]))))
        if key in seen:
            continue
        seen.add(key)
        out.append(Diagnostic(
            "CLOSE_CONTACT",
            f"{_name(structure, cell, i)} and "
            f"{_name(structure, cell, j)} are {d:.3f} A apart and not "
            f"bonded",
            where=f"atoms {i}, {j}"))
    return out


def _coordination(structure, cell, coordination) -> list[Diagnostic]:
    out = []
    seen_unbonded = set()
    seen_over = set()
    for atom, element in enumerate(cell.elements):
        if el.is_dummy(element):
            continue
        site = int(cell.site_idx[atom])
        n = int(coordination[atom])
        if n == 0 and site not in seen_unbonded:
            seen_unbonded.add(site)
            out.append(Diagnostic(
                "UNBONDED_ATOM",
                f"{_name(structure, cell, atom)} has no bonds",
                where=f"site {site}"))
        limit = MAX_COORDINATION.get(element)
        if limit is not None and n > limit and site not in seen_over:
            seen_over.add(site)
            out.append(Diagnostic(
                "OVERCOORDINATED",
                f"{_name(structure, cell, atom)} has {n} bonds; "
                f"{element} makes at most {limit}",
                where=f"site {site}"))
    return out


def _bond_lengths(structure, cell, graph) -> list[Diagnostic]:
    out = []
    seen = set()
    for bond in graph.bonds:
        a, b = cell.elements[bond.i], cell.elements[bond.j]
        if a not in _NONMETALS or b not in _NONMETALS:
            continue
        if el.is_dummy(a) or el.is_dummy(b):
            continue
        reference = bonding.bond_distance(a, b)
        if abs(bond.distance - reference) <= BOND_DEVIATION * reference:
            continue
        key = tuple(sorted((int(cell.site_idx[bond.i]),
                            int(cell.site_idx[bond.j]))))
        if key in seen:
            continue
        seen.add(key)
        out.append(Diagnostic(
            "BOND_LENGTH_UNUSUAL",
            f"{_name(structure, cell, bond.i)}-"
            f"{_name(structure, cell, bond.j)} is "
            f"{bond.distance:.3f} A against {reference:.2f} A for "
            f"{a}-{b}",
            where=f"atoms {bond.i}, {bond.j}"))
    return out


def _capped(found) -> list[Diagnostic]:
    """At most :data:`MAX_PER_CODE` of each code, and a line saying how
    many more there were."""
    out, counts = [], Counter()
    for d in found:
        counts[d.code] += 1
        if counts[d.code] <= MAX_PER_CODE:
            out.append(d)
    for code, n in counts.items():
        if n > MAX_PER_CODE:
            out.append(Diagnostic(
                code, f"... and {n - MAX_PER_CODE} more like the above "
                      f"({n} in all)"))
    return out
