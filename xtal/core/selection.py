"""
xtal.core.selection
===================
What the user has selected, and the ways of arriving at a selection.

Selections live in **P1 cell index space** -- they refer to the atoms
that are drawn, not to the asymmetric unit -- because that is what a
person clicks on.  Turning a set of drawn atoms back into the sites an
edit must touch is :func:`sites_for`, and whether that mapping is safe
is :func:`covers_whole_orbits`: deleting one symmetry image means
deleting its whole orbit, and the caller has to know that before it
happens rather than after.

Everything here is a plain function over a cell and a bond graph, so
the selection logic is testable without a window and reusable from the
CLI and the Python console.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Selection:
    """A set of selected atoms and bonds, plus the focused atom."""

    atoms: set = field(default_factory=set)
    bonds: set = field(default_factory=set)     # CellBond.key() tuples
    focus: int | None = None                    # last atom picked

    # -- state ---------------------------------------------------------

    @property
    def is_empty(self) -> bool:
        return not self.atoms and not self.bonds

    @property
    def count(self) -> int:
        return len(self.atoms) + len(self.bonds)

    def __len__(self) -> int:
        return self.count

    def __contains__(self, atom: int) -> bool:
        return atom in self.atoms

    # -- editing -------------------------------------------------------

    def clear(self) -> None:
        self.atoms.clear()
        self.bonds.clear()
        self.focus = None

    def set_atoms(self, atoms) -> None:
        self.atoms = {int(a) for a in atoms}
        self.focus = max(self.atoms) if self.atoms else None

    def add_atoms(self, atoms) -> None:
        self.atoms |= {int(a) for a in atoms}

    def remove_atoms(self, atoms) -> None:
        self.atoms -= {int(a) for a in atoms}
        if self.focus is not None and self.focus not in self.atoms:
            self.focus = None

    def toggle_atom(self, atom: int) -> bool:
        """Toggle one atom; returns whether it ended up selected."""
        atom = int(atom)
        if atom in self.atoms:
            self.atoms.discard(atom)
            if self.focus == atom:
                self.focus = None
            return False
        self.atoms.add(atom)
        self.focus = atom
        return True

    def toggle_bond(self, key) -> bool:
        if key in self.bonds:
            self.bonds.discard(key)
            return False
        self.bonds.add(key)
        return True

    def invert(self, n_atoms: int) -> None:
        self.atoms = set(range(n_atoms)) - self.atoms
        self.focus = None

    def copy(self) -> Selection:
        return Selection(set(self.atoms), set(self.bonds), self.focus)

    def mask(self, n_atoms: int) -> np.ndarray:
        """Boolean array over the P1 cell -- what the scene builder
        needs to highlight."""
        out = np.zeros(n_atoms, dtype=bool)
        if self.atoms:
            valid = [a for a in self.atoms if 0 <= a < n_atoms]
            out[valid] = True
        return out

    def prune(self, n_atoms: int) -> None:
        """Drop references to atoms that no longer exist (after a
        delete, a supercell, a change of space group)."""
        self.atoms = {a for a in self.atoms if 0 <= a < n_atoms}
        self.bonds = {b for b in self.bonds
                      if b[0] < n_atoms and b[1] < n_atoms}
        if self.focus is not None and self.focus >= n_atoms:
            self.focus = None


# ======================================================================
#  WAYS OF SELECTING
# ======================================================================

def by_element(cell, *symbols) -> set:
    """Every atom of the given element(s)."""
    wanted = set(symbols)
    return {k for k in range(cell.n_atoms)
            if cell.elements[k] in wanted}


def by_site(cell, site_index: int) -> set:
    """Every image of one asymmetric-unit site."""
    return set(int(k) for k in cell.indices_of_site(site_index))


def symmetry_orbit(cell, atoms) -> set:
    """Grow a selection to the full orbit of every atom in it -- the
    atoms that must move or vanish together."""
    out = set()
    for atom in atoms:
        out |= set(int(k) for k in cell.orbit_of(int(atom)))
    return out


def expand_shell(graph, atoms, depth: int = 1) -> set:
    """Atoms within ``depth`` bonds of the selection."""
    return graph.shell(atoms, depth)


def expand_fragment(graph, atoms) -> set:
    """The whole connected fragment -- a molecule, or the framework."""
    out = set()
    for atom in atoms:
        out |= set(graph.fragment_containing(int(atom)).atoms)
    return out


def within_radius(cell, lattice, atoms, radius: float) -> set:
    """Everything within ``radius`` Angstrom of the selection,
    minimum-image aware."""
    if not atoms or cell.n_atoms == 0:
        return set(atoms)
    out = set(int(a) for a in atoms)
    seeds = cell.frac[sorted(out)]
    for seed in seeds:
        d = cell.frac - seed
        d -= np.round(d)
        dist = np.linalg.norm(d @ lattice.matrix, axis=1)
        out |= {int(k) for k in np.flatnonzero(dist <= radius)}
    return out


def bonds_within(graph, atoms) -> set:
    """Keys of the bonds with both ends inside the selection."""
    inside = set(int(a) for a in atoms)
    return {b.key() for b in graph.bonds
            if b.i in inside and b.j in inside}


# ======================================================================
#  MAPPING BACK TO THE ASYMMETRIC UNIT
# ======================================================================

def sites_for(cell, atoms) -> set:
    """The asymmetric-unit sites behind a set of drawn atoms."""
    return {int(cell.site_idx[int(a)]) for a in atoms}


def covers_whole_orbits(cell, atoms) -> bool:
    """True when the selection contains every image of every site it
    touches.

    An edit to a partial orbit cannot be expressed in the asymmetric
    unit: deleting three of four symmetry-equivalent atoms is not a
    thing a space group can describe.  The caller must either extend
    the selection to the orbit or drop the structure to P1.
    """
    selected = set(int(a) for a in atoms)
    for site in sites_for(cell, selected):
        if not set(int(k) for k in cell.indices_of_site(site)) \
                <= selected:
            return False
    return True


def orbit_report(cell, atoms) -> str:
    """One line describing what an edit would really touch."""
    selected = set(int(a) for a in atoms)
    sites = sites_for(cell, selected)
    total = sum(cell.multiplicity(s) for s in sites)
    if total == len(selected):
        return (f"{len(selected)} atom(s) from {len(sites)} "
                f"site(s)")
    return (f"{len(selected)} atom(s) selected, but they belong to "
            f"{len(sites)} site(s) totalling {total} atoms -- "
            f"symmetry ties them together")


def describe(structure, cell, selection: Selection) -> str:
    """Human summary of a selection, for the status bar."""
    if selection.is_empty:
        return "nothing selected"
    parts = []
    if selection.atoms:
        counts: dict[str, int] = {}
        for atom in selection.atoms:
            element = cell.elements[atom]
            counts[element] = counts.get(element, 0) + 1
        formula = " ".join(f"{el}{n}" if n > 1 else el
                           for el, n in sorted(counts.items()))
        parts.append(f"{len(selection.atoms)} atoms ({formula})")
    if selection.bonds:
        parts.append(f"{len(selection.bonds)} bonds")
    return ", ".join(parts)


def substructure(structure, cell, atoms):
    """A P1 structure holding just the selected atoms of the cell.

    "Export this molecule" is the second thing anybody wants after
    "export this", and it has to mean *where those atoms are*: the
    cell is kept, the coordinates are kept, and only the atoms outside
    the selection are dropped.  The space group cannot be: an
    asymmetric unit whose orbit is half missing is not a crystal, so
    the answer is in P1 and says so.
    """
    from xtal.core.site import Site
    from xtal.core.spacegroup import SpaceGroup
    from xtal.core.structure import Structure

    chosen = sorted(int(a) for a in atoms if 0 <= int(a) < cell.n_atoms)
    out = Structure(
        lattice=structure.lattice,
        sites=[Site(cell.elements[a], cell.frac[a],
                    occupancy=float(cell.occupancy[a]),
                    label=cell.labels[a]) for a in chosen],
        space_group=SpaceGroup.p1())
    title = structure.meta.get("title")
    if title:
        out.meta["title"] = f"{title} (selection)"
    out.ensure_labels()
    return out
