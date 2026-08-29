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
from xtal.core.structure import Structure

# spglib >= 2.5 keeps a deprecated global error flag; opting out makes
# it raise on failure instead of warning and returning None.
try:                                            # pragma: no cover
    import spglib.error as _spglib_error
    _spglib_error.OLD_ERROR_HANDLING = False
except (ImportError, AttributeError):           # pragma: no cover
    pass

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

    Bonds are dropped: their site indices refer to the asymmetric unit
    and no longer mean anything.  Bond perception re-runs on the result.
    """
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
    d = cell.frac - target
    d -= np.round(d)
    dist = np.linalg.norm(d @ lattice.matrix, axis=1)
    for k in np.flatnonzero(dist < tol):
        if (cell.elements[k] == element
                and abs(cell.occupancy[k] - occupancy) < 1e-6):
            return int(k)
    return None


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

    ok, why = _regenerates(out, cell, MATCH_TOL)
    if not ok:
        return structure, SymmetryReport(
            ok=False,
            message=f"could not reduce to an asymmetric unit: {why}",
            warnings=["the structure is unchanged; reduce the tolerance "
                      "or work in P1"],
        )
    report = SymmetryReport(
        n_before=cell.n_atoms, n_after=len(sites),
        message=(f"{info.international} (#{info.number}): "
                 f"{cell.n_atoms} atoms -> {len(sites)} independent "
                 f"sites"),
        warnings=notes,
    )
    return out, report


def _regenerates(candidate: Structure, original: p1.P1Cell, tol: float):
    """Does expanding ``candidate`` reproduce ``original``?"""
    new = p1.expand(candidate)
    if new.n_atoms != original.n_atoms:
        return False, (f"expansion gives {new.n_atoms} atoms, "
                       f"expected {original.n_atoms}")
    lattice = candidate.lattice
    for k in range(new.n_atoms):
        hit = _match_atom(original, new.frac[k], new.elements[k],
                          new.occupancy[k], lattice, tol)
        if hit is None:
            return False, "expanded atoms do not line up with the cell"
    return True, ""


# ======================================================================
#  DUPLICATE MERGING
# ======================================================================

def merge_duplicates(structure: Structure, tol: float = 0.05
                     ) -> tuple[Structure, SymmetryReport]:
    """Merge asymmetric-unit sites of the same element that sit within
    ``tol`` Angstrom of each other (periodic images included).

    Every symmetry-changing operation should offer this: generating a
    group over coordinates that were already the full cell is the
    standard way to end up with near-duplicate atoms.
    """
    keep: list[int] = []
    dropped: list[int] = []
    lattice = structure.lattice
    for i, site in enumerate(structure.sites):
        dup = False
        for j in keep:
            other = structure.sites[j]
            if other.element != site.element:
                continue
            d = site.frac - other.frac
            d -= np.round(d)
            if np.linalg.norm(d @ lattice.matrix) < tol:
                dup = True
                break
        (dropped if dup else keep).append(i)

    out = structure.copy()
    if dropped:
        out.remove_sites(dropped)
    return out, SymmetryReport(
        n_before=structure.n_sites, n_after=len(keep),
        merged=len(dropped),
        message=(f"merged {len(dropped)} duplicate site(s) within "
                 f"{tol} A" if dropped else "no duplicates found"),
    )
