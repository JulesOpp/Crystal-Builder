"""
xtal.core.symmetry
==================
The symmetry workflow: detect it, set it, impose it, or throw it away.

Four operations, and each one is a menu item in the application:

* :func:`detect`        -- what symmetry do these coordinates have, at
                           this tolerance?  (spglib)
* :func:`set_space_group` -- adopt a group, either *reinterpreting* the
                           current sites as an asymmetric unit or
                           *imposing* the group on a full cell.
* :func:`asymmetrize`   -- keep the detected symmetry and reduce the
                           cell to its asymmetric unit.
* :func:`reduce_to_p1`  -- expand every orbit and drop the group.  The
                           escape hatch; always safe, always available.

Two details that decide whether the results are right:

**Partial occupancy.**  spglib only knows integer species.  Two sites
of the same element with different occupancies are *not* symmetry
equivalent, so species ids here are keyed on ``(element, occupancy)``
-- otherwise a disordered structure detects a symmetry it does not
have.

**Verification.**  Anything that claims to preserve the structure is
checked by re-expanding the result and comparing it with the cell we
started from.  If the round trip does not match, the operation reports
failure instead of returning a plausible-looking wrong answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import spglib

from xtal.core import p1
from xtal.core.lattice import Lattice
from xtal.core.site import Site
from xtal.core.spacegroup import SpaceGroup
from xtal.core.structure import Bond, Structure

DEFAULT_SYMPREC = 1e-5          # Angstrom-ish; spglib's own default
DEFAULT_ANGLE_TOLERANCE = -1.0  # negative = derive from symprec
MATCH_TOL = 1e-3                # Angstrom, for matching two atoms


# ======================================================================
#  RESULT TYPES
# ======================================================================

@dataclass
class SymmetryReport:
    """What an operation did, in terms a dialog can show."""

    ok: bool = True
    message: str = ""
    warnings: list[str] = field(default_factory=list)
    n_before: int = 0
    n_after: int = 0
    merged: int = 0
    unmatched: list[int] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


@dataclass(frozen=True)
class SymmetryInfo:
    """Everything spglib found, in our vocabulary."""

    space_group: SpaceGroup
    number: int
    international: str
    hall: str
    choice: str
    pointgroup: str
    n_operations: int
    wyckoffs: tuple[str, ...]           # per atom of the P1 cell
    site_symmetry: tuple[str, ...]
    equivalent_atoms: np.ndarray
    n_orbits: int
    symprec: float
    angle_tolerance: float
    transformation_matrix: np.ndarray
    origin_shift: np.ndarray
    std_lattice: np.ndarray
    std_positions: np.ndarray
    std_species: tuple

    @property
    def is_standard_setting(self) -> bool:
        """True when the cell as given already is the standard setting,
        so the group can be adopted without moving anything."""
        return (np.allclose(self.transformation_matrix, np.eye(3),
                            atol=1e-5)
                and np.allclose(self.origin_shift, 0.0, atol=1e-5))

    def summary(self) -> str:
        return (f"{self.international} (#{self.number}), "
                f"{self.n_operations} operations, "
                f"{self.n_orbits} independent sites "
                f"[symprec={self.symprec:g}]")


# ======================================================================
#  SPGLIB PLUMBING
# ======================================================================

def _species_ids(elements, occupancies):
    """Map (element, occupancy) pairs to the integer species ids
    spglib wants, plus the reverse map."""
    ids, back, numbers = {}, {}, []
    for el, occ in zip(elements, occupancies, strict=True):
        key = (el, round(float(occ), 6))
        if key not in ids:
            ids[key] = len(ids) + 1
            back[ids[key]] = key
        numbers.append(ids[key])
    return np.array(numbers, dtype=int), back


def _spglib_cell(structure: Structure):
    """(lattice, positions, numbers) for the FULL cell -- spglib needs
    every atom, not the asymmetric unit."""
    cell = p1.expand(structure)
    if cell.n_atoms == 0:
        raise ValueError("cannot analyse the symmetry of an empty cell")
    numbers, back = _species_ids(cell.elements, cell.occupancy)
    return (structure.lattice.matrix, cell.frac, numbers), back, cell


# ======================================================================
#  DETECTION
# ======================================================================

def detect(structure: Structure, symprec: float = DEFAULT_SYMPREC,
           angle_tolerance: float = DEFAULT_ANGLE_TOLERANCE
           ) -> SymmetryInfo:
    """Find the space group of ``structure`` at a given tolerance.

    Raises ValueError if spglib cannot make sense of the cell (which is
    itself useful information -- usually overlapping atoms).
    """
    cell, back, _ = _spglib_cell(structure)
    try:
        ds = spglib.get_symmetry_dataset(
            cell, symprec=symprec, angle_tolerance=angle_tolerance)
    except Exception as exc:                    # spglib raises its own
        raise ValueError(f"symmetry detection failed: {exc}") from exc
    if ds is None:
        raise ValueError(
            f"no symmetry could be determined at symprec={symprec:g}")

    hall = spglib.get_spacegroup_type(ds.hall_number).hall_symbol
    try:
        sg = SpaceGroup.from_hall(hall)
    except ValueError:                          # pragma: no cover
        sg = SpaceGroup.from_name(ds.international)

    return SymmetryInfo(
        space_group=sg,
        number=int(ds.number),
        international=str(ds.international),
        hall=str(hall),
        choice=str(ds.choice),
        pointgroup=str(ds.pointgroup),
        n_operations=len(ds.rotations),
        wyckoffs=tuple(ds.wyckoffs),
        site_symmetry=tuple(ds.site_symmetry_symbols),
        equivalent_atoms=np.asarray(ds.equivalent_atoms),
        n_orbits=len(set(ds.equivalent_atoms)),
        symprec=symprec,
        angle_tolerance=angle_tolerance,
        transformation_matrix=np.asarray(ds.transformation_matrix),
        origin_shift=np.asarray(ds.origin_shift),
        std_lattice=np.asarray(ds.std_lattice),
        std_positions=np.asarray(ds.std_positions),
        std_species=tuple(back[int(t)] for t in ds.std_types),
    )


def assign_wyckoff(structure: Structure,
                   symprec: float = DEFAULT_SYMPREC) -> Structure:
    """Copy of ``structure`` with Wyckoff letters filled in on every
    site.  Purely informational -- no coordinate changes."""
    info = detect(structure, symprec)
    cell = p1.expand(structure)
    out = structure.copy()
    for i in range(out.n_sites):
        members = cell.indices_of_site(i)
        if len(members):
            k = int(members[0])
            mult = int(np.count_nonzero(
                info.equivalent_atoms == info.equivalent_atoms[k]))
            out.sites[i].wyckoff = f"{mult}{info.wyckoffs[k]}"
    out.touch()
    return out


# ======================================================================
#  P1
# ======================================================================

def reduce_to_p1(structure: Structure) -> Structure:
    """Expand every orbit into explicit sites and drop the group.

    **The bonding comes too.**  Every stored bond -- drawn, suppressed,
    a net edge, a type the user set -- is expanded the way it is drawn
    and written down again between the new sites, and the perceived
    graph is carried over rather than perceived afresh.  Dropping them,
    which is what this did, re-perceived the whole crystal from the
    geometry: a framework somebody had recalculated, typed and drawn a
    net over came back from Reduce to P1 -- or from filling its pores,
    which reduces first -- with none of it.  Bonds change when the
    user asks.
    """
    from xtal.core import bonding
    cell = p1.expand(structure)
    sites = []
    for k in range(cell.n_atoms):
        parent = structure.sites[int(cell.site_idx[k])]
        s = parent.copy()
        s.frac = cell.frac[k].copy()
        s.wyckoff = None
        s.label = ""
        sites.append(s)
    out = Structure(
        lattice=structure.lattice,
        sites=sites,
        space_group=SpaceGroup.p1(),
        meta=dict(structure.meta),
        bond_rules=dict(structure.bond_rules),
    )
    out.ensure_labels()
    # The new sites are the cell's atoms in the cell's order, already
    # wrapped, so a P1 bond between atoms a and b is a bond between
    # sites a and b with the same image.
    for bond in structure.bonds:
        for mapped in bonding.map_explicit_bond(structure, cell, bond):
            out.add_bond(Bond(mapped.i, mapped.j, mapped.image,
                              bond.order, bond.kind, 0, bond.stated))
    stored = structure.perceived
    if stored is not None and stored.elements == tuple(cell.elements):
        # Read against the original's wrap as it is now, which is where
        # the new sites are; their own wrap is then zero.
        flat = p1.expand(out)
        out.set_perceived(bonding.rebase(stored.bonds, stored.tau,
                                         cell.tau),
                          stored.signature, flat)
    return out


# ======================================================================
#  ADOPTING A GROUP
# ======================================================================

def set_space_group(structure: Structure, sg, mode: str = "reinterpret",
                    tol: float = MATCH_TOL
                    ) -> tuple[Structure, SymmetryReport]:
    """Change the space group of a structure.

    ``mode="reinterpret"``
        Treat the existing sites as the asymmetric unit and let the new
        group generate the rest.  The atom count usually grows.  This is
        what you want when building a structure by hand.

    ``mode="impose"``
        Treat the existing sites as a full cell and find an asymmetric
        unit for the new group inside it.  The atom count usually
        shrinks.  Atoms the group cannot explain are reported, not
        silently dropped.
    """
    group = SpaceGroup.from_any(sg)
    if mode == "reinterpret":
        return _reinterpret(structure, group, tol)
    if mode == "impose":
        return _impose(structure, group, tol)
    raise ValueError(f"unknown mode {mode!r}: "
                     "expected 'reinterpret' or 'impose'")


def _reinterpret(structure, group, tol):
    before = p1.expand(structure).n_atoms
    out = structure.copy()
    out.set_space_group(group)
    out.bonds = []
    cell = p1.expand(out)
    report = SymmetryReport(
        n_before=before, n_after=cell.n_atoms,
        message=(f"{structure.n_sites} sites generate {cell.n_atoms} "
                 f"atoms in {group.short_name}"),
    )
    clashes = _find_clashes(cell, structure.lattice, tol)
    if clashes:
        report.warnings.append(
            f"{len(clashes)} pairs of atoms from different sites now "
            f"overlap within {tol} A -- merge them, or the group or "
            f"the coordinates are wrong")
    return out, report


def _impose(structure, group, tol):
    cell = p1.expand(structure)
    lattice = structure.lattice
    covered = np.zeros(cell.n_atoms, dtype=bool)
    reps: list[int] = []
    missing: list[np.ndarray] = []

    for k in range(cell.n_atoms):
        if covered[k]:
            continue
        reps.append(k)
        covered[k] = True
        for op in group.operations:
            target = p1._wrap(op.apply(cell.frac[k]))
            hit = _match_atom(cell, target, cell.elements[k],
                              cell.occupancy[k], lattice, tol)
            if hit is None:
                missing.append(target)
            else:
                covered[hit] = True

    sites = []
    for k in reps:
        parent = structure.sites[int(cell.site_idx[k])]
        s = parent.copy()
        s.frac = cell.frac[k].copy()
        s.wyckoff = None
        sites.append(s)
    out = Structure(lattice=lattice, sites=sites, space_group=group,
                    meta=dict(structure.meta),
                    bond_rules=dict(structure.bond_rules))
    out.ensure_labels()

    report = SymmetryReport(
        n_before=cell.n_atoms, n_after=p1.expand(out).n_atoms,
        message=(f"{cell.n_atoms} atoms reduced to {len(reps)} "
                 f"independent sites in {group.short_name}"),
    )
    if missing:
        report.ok = False
        report.warnings.append(
            f"{len(missing)} atoms required by {group.short_name} are "
            f"not present -- the structure does not have this symmetry "
            f"at a {tol} A tolerance")
    return out, report


def _match_atom(cell, target, element, occupancy, lattice, tol):
    """Index of the atom of ``cell`` sitting at ``target`` with the same
    species, or None."""
    found = _nearest_atom(cell, target, element, occupancy, lattice,
                          tol)
    return None if found is None else found[0]


def _nearest_atom(cell, target, element, occupancy, lattice, tol):
    """(index, distance) of the closest atom of ``cell`` within ``tol``
    of ``target`` and of the same species, or None.

    The distance matters as well as the hit: it is how far a symmetry
    operation had to move an atom to be believed, and at a loose
    tolerance that is the number the user has to see.
    """
    d = cell.frac - target
    d -= np.round(d)
    dist = np.linalg.norm(d @ lattice.matrix, axis=1)
    best = None
    for k in np.flatnonzero(dist < tol):
        if (cell.elements[k] == element
                and abs(cell.occupancy[k] - occupancy) < 1e-6
                and (best is None or dist[k] < best[1])):
            best = (int(k), float(dist[k]))
    return best


def _find_clashes(cell, lattice, tol):
    """Pairs of atoms from *different* parent sites that overlap."""
    out = []
    for i in range(cell.n_atoms):
        d = cell.frac[i + 1:] - cell.frac[i]
        if not len(d):
            continue
        d -= np.round(d)
        dist = np.linalg.norm(d @ lattice.matrix, axis=1)
        for off in np.flatnonzero(dist < tol):
            j = i + 1 + int(off)
            if cell.site_idx[i] != cell.site_idx[j]:
                out.append((i, j))
    return out


# ======================================================================
#  STANDARDISING / ASYMMETRISING
# ======================================================================

def standardize(structure: Structure,
                symprec: float = DEFAULT_SYMPREC,
                to_primitive: bool = False,
                idealize: bool = True) -> tuple[Structure, SymmetryReport]:
    """Rebuild the cell in the conventional (or primitive) setting of
    its detected group.  The result is in P1 -- call
    :func:`asymmetrize` after it to also reduce the sites."""
    cell, back, _ = _spglib_cell(structure)
    try:
        std = spglib.standardize_cell(
            cell, to_primitive=to_primitive, no_idealize=not idealize,
            symprec=symprec)
    except Exception as exc:
        raise ValueError(f"cell standardisation failed: {exc}") from exc
    if std is None:
        raise ValueError("cell standardisation failed")

    lattice_rows, positions, numbers = std
    sites = []
    for pos, num in zip(positions, numbers, strict=True):
        element, occ = back[int(num)]
        sites.append(Site(element, p1._wrap(pos), occupancy=occ))
    out = Structure(lattice=Lattice(lattice_rows), sites=sites,
                    space_group=SpaceGroup.p1(),
                    meta=dict(structure.meta))
    out.ensure_labels()
    kind = "primitive" if to_primitive else "conventional"
    return out, SymmetryReport(
        n_before=len(cell[1]), n_after=len(sites),
        message=(f"standardised to the {kind} cell: {len(sites)} atoms, "
                 f"V = {out.lattice.volume:.2f} A^3"),
    )


def asymmetrize(structure: Structure,
                symprec: float = DEFAULT_SYMPREC,
                standardize_cell: bool = False
                ) -> tuple[Structure, SymmetryReport]:
    """Detect the symmetry and reduce the cell to its asymmetric unit.

    With ``standardize_cell=False`` (the default) the cell is left
    exactly as it is, which is only possible when it is already in the
    standard setting of the detected group; when it is not, the caller
    is told to pass ``standardize_cell=True`` rather than being handed
    a structure in the wrong setting.

    The result is verified by re-expansion: if the asymmetric unit does
    not regenerate the cell we started from, the original structure is
    returned with ``ok=False``.
    """
    info = detect(structure, symprec)
    work = structure
    notes: list[str] = []

    if not info.is_standard_setting:
        if not standardize_cell:
            return structure, SymmetryReport(
                ok=False,
                message=(f"the cell is not in the standard setting of "
                         f"{info.international}; standardise it first"),
                warnings=["pass standardize_cell=True to rebuild the "
                          "cell in the standard setting"],
            )
        work, std_report = standardize(structure, symprec)
        notes.append(std_report.message)
        info = detect(work, symprec)

    cell = p1.expand(work)
    reps: list[int] = []
    seen: set[int] = set()
    for k in range(cell.n_atoms):
        cls = int(info.equivalent_atoms[k])
        if cls not in seen:
            seen.add(cls)
            reps.append(k)

    sites = []
    for k in reps:
        parent = work.sites[int(cell.site_idx[k])]
        s = parent.copy()
        s.frac = cell.frac[k].copy()
        mult = int(np.count_nonzero(
            info.equivalent_atoms == info.equivalent_atoms[k]))
        s.wyckoff = f"{mult}{info.wyckoffs[k]}"
        sites.append(s)

    out = Structure(lattice=work.lattice, sites=sites,
                    space_group=info.space_group,
                    meta=dict(work.meta))
    out.ensure_labels()

    # Verified at the tolerance the group was *found* at.  Checking a
    # symprec of 0.05 against a fixed 1e-3 would reject every loose
    # answer, which would make the tolerance control pointless: the
    # whole premise of a loose search is that atoms are that far from
    # their idealised positions.
    ok, why, worst = _regenerates(out, cell, max(MATCH_TOL, symprec))
    if not ok:
        return structure, SymmetryReport(
            ok=False,
            message=f"could not reduce to an asymmetric unit: {why}",
            warnings=["the structure is unchanged; reduce the tolerance "
                      "or work in P1"],
        )
    if worst > MATCH_TOL:
        notes.append(
            f"imposing the group idealised the coordinates: atoms move "
            f"by up to {worst:.4f} A")
    report = SymmetryReport(
        n_before=cell.n_atoms, n_after=len(sites),
        message=(f"{info.international} (#{info.number}): "
                 f"{cell.n_atoms} atoms -> {len(sites)} independent "
                 f"sites"),
        warnings=notes,
    )
    return out, report


def _regenerates(candidate: Structure, original: p1.P1Cell, tol: float):
    """Does expanding ``candidate`` reproduce ``original``?

    Returns (ok, why, worst displacement in Angstrom).
    """
    new = p1.expand(candidate)
    if new.n_atoms != original.n_atoms:
        return False, (f"expansion gives {new.n_atoms} atoms, "
                       f"expected {original.n_atoms}"), 0.0
    lattice = candidate.lattice
    worst = 0.0
    for k in range(new.n_atoms):
        hit = _nearest_atom(original, new.frac[k], new.elements[k],
                            new.occupancy[k], lattice, tol)
        if hit is None:
            return (False,
                    "expanded atoms do not line up with the cell", 0.0)
        worst = max(worst, hit[1])
    return True, "", worst


# ======================================================================
#  CHANGE OF HAND
# ======================================================================
#
#  P4_1 and P4_3 are the same crystal in the two hands.  Getting from
#  one to the other is a change of hand on the *coordinates* and the
#  matching change of *space group*, and doing only the first is the
#  bug: negating the coordinates while leaving P4_1 in place gives a
#  structure whose atoms no longer obey their own symmetry, and the
#  next P1 expansion of it is nonsense.


def change_of_hand_op(group: SpaceGroup):
    """``(rot, tran)`` of the operation that inverts this group's
    coordinates and lands back in its standard setting.

    Usually a bare ``-x,-y,-z``, but not always: I4_1 needs
    ``-x+1/2,-y,-z`` and F4_132 needs ``-x+1/4,-y+1/4,-z+1/4``, and
    using a bare inversion for those puts 14 groups into a
    non-standard setting without saying so.
    """
    import gemmi
    op = group._sg.change_of_hand_op()
    rot = np.array(op.rot, dtype=float) / float(gemmi.Op.DEN)
    tran = np.array(op.tran, dtype=float) / float(gemmi.Op.DEN)
    return rot, tran


def enantiomorph(group: SpaceGroup) -> SpaceGroup:
    """The group of the inverted structure.

    Falls out of the operations rather than a table: conjugating by the
    inversion leaves the rotations alone and negates the translations,
    which names the partner for all eleven enantiomorphic pairs and
    returns the group unchanged for the other 219.
    """
    import gemmi
    ops = group._sg.operations()
    ops.change_basis_forward(group._sg.change_of_hand_op())
    partner = gemmi.find_spacegroup_by_ops(ops)
    if partner is None:                             # pragma: no cover
        return group
    return SpaceGroup(partner.hall)


def hand_description(group: SpaceGroup) -> str:
    """One line saying which hand this group is, for a panel that is
    always on screen.

    The read-out is the thing that makes anyone think to invert a
    structure at all: "chiral, P4_1 (enantiomorph P4_3)" is a standing
    invitation to check the other hand against the data.
    """
    if group.is_centrosymmetric:
        return "centrosymmetric (achiral)"
    if not group.is_chiral:
        return "achiral (improper operations, no inversion centre)"
    partner = enantiomorph(group)
    if partner != group:
        return f"chiral, enantiomorph {partner.short_name}"
    return "chiral, its own enantiomorph"


def invert(structure: Structure) -> tuple[Structure, SymmetryReport]:
    """The same crystal in the other hand.

    Transforms every site by the change-of-hand operation and sets the
    group to the partner.  The lattice is left alone: the cell
    parameters do not change and a right-handed cell stays right-handed
    -- the hand that changes is the structure's, not the axes'.
    """
    group = structure.space_group
    rot, tran = change_of_hand_op(group)
    partner = enantiomorph(group)

    out = structure.copy()
    for site in out.sites:
        site.frac = p1._wrap(rot @ site.frac + tran)
    out.set_space_group(partner)
    # Bond operation indices are numbered within a group; the group has
    # just changed, so they no longer point where they did.
    out.bonds = []
    out.ensure_labels()
    out.touch()

    if group.is_centrosymmetric:
        message = (f"{group.short_name} is centrosymmetric: inversion "
                   f"is already one of its operations and the "
                   f"structure is unchanged")
    elif partner != group:
        message = (f"inverted: {group.short_name} -> "
                   f"{partner.short_name}")
    elif not group.is_chiral:
        message = (f"inverted the coordinates; {group.short_name} has "
                   f"improper operations, so this is the same crystal "
                   f"described the other way round")
    else:
        message = (f"inverted: {group.short_name} is its own "
                   f"enantiomorph, so the symbol is unchanged and the "
                   f"structure is not")
    report = SymmetryReport(
        n_before=structure.n_sites, n_after=out.n_sites,
        message=message)
    if group.is_centrosymmetric:
        report.warnings.append(
            "nothing to undo: the inverted structure is the one you "
            "already have")
    return out, report


# ======================================================================
#  DUPLICATE MERGING
# ======================================================================
# ======================================================================

DEFAULT_MERGE_TOL = 0.05        # Angstrom; loose, for sloppy files


@dataclass(frozen=True)
class MergePreview:
    """What merging at one tolerance would do, without doing it.

    The atom counts are the reason the dialog exists.  A file that
    repeats an orbit is not slightly wrong: ``Ni2Cl2BTDD.cif`` puts
    1188 atoms in the cell where there are 396, and the formula, the
    density and every energy computed from it are out by that factor
    with nothing on screen saying so.  "27 sites merge" does not carry
    that; "1188 atoms become 396" does.
    """

    tol: float
    merged: int                 # sites that would be removed
    sites_before: int
    sites_after: int
    atoms_before: int           # atoms in the unit cell
    atoms_after: int
    demoted: int                # groups keeping a later, more special site

    def __bool__(self) -> bool:
        return self.merged > 0

    def message(self) -> str:
        if not self.merged:
            return f"no duplicates within {self.tol:g} A"
        return (f"{self.merged} of {self.sites_before} sites merge -- "
                f"{self.atoms_before} atoms in the cell become "
                f"{self.atoms_after}")


def duplicate_groups(structure: Structure,
                     tol: float = DEFAULT_MERGE_TOL) -> list[list[int]]:
    """Sites of the same element that are the same atom, grouped.

    Each group is the site indices of one atom written more than once,
    in the order the sites are; an atom written once does not appear.

    The comparison is against the **orbit**, not against the parent
    coordinates, and that is the whole of it.  A CIF written with a
    full cell's worth of coordinates under a group -- which is how
    ``Ni2Cl2BTDD.cif`` and anything else exported from a P1 refinement
    arrives -- repeats an atom at whichever image the exporter happened
    to pick, so the two parent coordinates are as far apart as any two
    atoms in the cell.  ``C1`` and ``C1X`` there are 7.2 A apart as
    written and 2e-5 A apart once one of them is put through the
    operations of ``H-3m``.  Comparing parents finds nothing at any
    tolerance; comparing one parent against the other's images finds
    all 27 of them.
    """
    cell = p1.expand(structure)
    matrix = structure.lattice.matrix
    species: dict[str, int] = {}

    # The pool is every image of every group's first site, which is at
    # most the whole cell -- so it is allocated once and filled rather
    # than regrown per site.  A P1 structure with a few thousand sites
    # comes through here, and the regrowth, not the arithmetic, would
    # be what it cost.
    pool = np.zeros((cell.n_atoms, 3))
    pool_group = np.zeros(cell.n_atoms, dtype=int)
    pool_species = np.zeros(cell.n_atoms, dtype=int)
    filled = 0

    groups: list[list[int]] = []
    for i, site in enumerate(structure.sites):
        kind = species.setdefault(site.element, len(species))
        found = -1
        if filled:
            d = pool[:filled] - site.frac
            d -= np.round(d)
            dist = np.linalg.norm(d @ matrix, axis=1)
            near = np.nonzero((pool_species[:filled] == kind)
                              & (dist < tol))[0]
            if len(near):
                found = int(pool_group[near[np.argmin(dist[near])]])
        if found >= 0:
            groups[found].append(i)
            continue

        members = cell.indices_of_site(i)
        n = len(members)
        pool[filled:filled + n] = cell.frac[members]
        pool_group[filled:filled + n] = len(groups)
        pool_species[filled:filled + n] = kind
        filled += n
        groups.append([i])

    return [g for g in groups if len(g) > 1]


def _keeper(cell, group: list[int]) -> int:
    """Which site of a duplicate group survives.

    The one on the more special Wyckoff position -- the one generating
    the fewest atoms.  Keeping the site written first is right when
    both are general and wrong when one of them sits on an axis: an
    atom written 0.01 A off a three-fold generates twice as many atoms
    as the same atom written on it, so keeping the general one doubles
    that element in the formula while the screen shows two atoms where
    there is one.  Equally special sites tie, and the tie goes to the
    site written first -- which is what merging has always done.
    """
    return min(group, key=lambda i: (cell.multiplicity(i), i))


def _site_name(structure: Structure, index: int) -> str:
    """What to call a site in a report.  A structure built from arrays
    has no labels at all, and "site 3" beats an empty string."""
    return structure.sites[index].label or f"site {index + 1}"


def preview_merge(structure: Structure,
                  tol: float = DEFAULT_MERGE_TOL) -> MergePreview:
    """What :func:`merge_duplicates` would do at ``tol``.

    Cheap enough to run on every keystroke of a spinbox: the expansion
    it needs is memoised on the structure, so only the first tolerance
    pays for it, and the atom count afterwards is read off the
    multiplicities already computed rather than by expanding again.
    """
    cell = p1.expand(structure)
    groups = duplicate_groups(structure, tol)
    dropped = {i for g in groups for i in g if i != _keeper(cell, g)}
    demoted = sum(1 for g in groups if _keeper(cell, g) != g[0])
    kept = [i for i in range(structure.n_sites) if i not in dropped]
    return MergePreview(
        tol=float(tol),
        merged=len(dropped),
        sites_before=structure.n_sites,
        sites_after=len(kept),
        atoms_before=cell.n_atoms,
        atoms_after=sum(cell.multiplicity(i) for i in kept),
        demoted=demoted,
    )


def merge_duplicates(structure: Structure,
                     tol: float = DEFAULT_MERGE_TOL
                     ) -> tuple[Structure, SymmetryReport]:
    """Merge asymmetric-unit sites of the same element that are the
    same atom to within ``tol`` Angstrom, symmetry images included.

    Every symmetry-changing operation should offer this: generating a
    group over coordinates that were already the full cell is the
    standard way to end up with near-duplicate atoms.
    """
    cell = p1.expand(structure)
    groups = duplicate_groups(structure, tol)

    dropped: list[int] = []
    demoted: list[str] = []
    partial = False
    for group in groups:
        keeper = _keeper(cell, group)
        dropped.extend(i for i in group if i != keeper)
        partial = partial or any(structure.sites[i].occupancy < 1.0
                                 for i in group)
        if keeper != group[0]:
            demoted.append(
                f"{_site_name(structure, keeper)} "
                f"(multiplicity {cell.multiplicity(keeper)}) over "
                f"{_site_name(structure, group[0])} "
                f"({cell.multiplicity(group[0])})")

    out = structure.copy()
    if dropped:
        out.remove_sites(sorted(dropped))
    report = SymmetryReport(
        n_before=structure.n_sites, n_after=out.n_sites,
        merged=len(dropped),
        message=(f"merged {len(dropped)} duplicate site(s) within "
                 f"{tol:g} A" if dropped else "no duplicates found"),
    )
    if demoted:
        report.warnings.append(
            "kept the site on the more special Wyckoff position, so "
            "the multiplicity is unchanged: " + _first_few(demoted))
    if partial:
        report.warnings.append(
            "some of the merged sites are partially occupied -- check "
            "the occupancies of what is left against the formula")
    return out, report


def _first_few(items: list[str], limit: int = 3) -> str:
    """A warning naming twenty sites is a warning nobody reads."""
    if len(items) <= limit:
        return "; ".join(items)
    return (f"{'; '.join(items[:limit])}; and {len(items) - limit} "
            f"more")
