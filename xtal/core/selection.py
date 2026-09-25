"""
xtal.core.selection
===================
What the user has selected, and the ways of arriving at a selection.

Atoms, chemical bonds and net edges are three sets and not one.  A
topology bond can join the same pair of atoms as a chemical bond, so
their keys collide and only the set they are in tells them apart.

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
    """A set of selected atoms and bonds, and the order they arrived
    in."""

    atoms: set = field(default_factory=set)
    bonds: set = field(default_factory=set)     # CellBond.key() tuples
    # Net edges, keyed the same way.  A separate set and not the same
    # one: a topology bond and a chemical bond can join the very same
    # pair of atoms, and their keys would then be indistinguishable.
    topology: set = field(default_factory=set)
    # The same atoms, in the order they were picked.  A set cannot
    # answer what a measurement asks: three atoms picked A-B-C make an
    # angle about B, and B-A-C is a different question over the same
    # three atoms.  Stating the rule ("the order you clicked them")
    # without keeping the order is a lie, so the order is kept.
    order: list = field(default_factory=list)

    # -- state ---------------------------------------------------------

    @property
    def focus(self) -> int | None:
        """The last atom picked, or ``None``."""
        return self.order[-1] if self.order else None

    @property
    def is_empty(self) -> bool:
        return not self.atoms and not self.bonds and not self.topology

    @property
    def count(self) -> int:
        return len(self.atoms) + len(self.bonds) + len(self.topology)

    def __len__(self) -> int:
        return self.count

    def __contains__(self, atom: int) -> bool:
        return atom in self.atoms

    # -- editing -------------------------------------------------------

    def clear(self) -> None:
        self.atoms.clear()
        self.bonds.clear()
        self.topology.clear()
        self.order.clear()

    def set_atoms(self, atoms) -> None:
        """Replace the selected atoms.

        A *sequence* states its own order, which is what a click path
        passes and what a measurement then reads back.  A set has no
        order to state, so it is taken in index order rather than in
        whatever order that particular set happens to iterate in:
        "the middle one of however the set came out" is not an answer
        anybody can predict twice.
        """
        self.order = _ordered(atoms)
        self.atoms = set(self.order)

    def add_atoms(self, atoms) -> None:
        for atom in _ordered(atoms):
            if atom not in self.atoms:
                self.atoms.add(atom)
                self.order.append(atom)

    def remove_atoms(self, atoms) -> None:
        gone = {int(a) for a in atoms}
        self.atoms -= gone
        self.order = [a for a in self.order if a not in gone]

    def toggle_atom(self, atom: int) -> bool:
        """Toggle one atom; returns whether it ended up selected.

        A re-picked atom goes to the *end* of the order, because that
        is when it was picked -- clicking it off and on again is how
        somebody corrects the vertex of an angle.
        """
        atom = int(atom)
        if atom in self.atoms:
            self.atoms.discard(atom)
            self.order.remove(atom)
            return False
        self.atoms.add(atom)
        self.order.append(atom)
        return True

    def toggle_bond(self, key) -> bool:
        if key in self.bonds:
            self.bonds.discard(key)
            return False
        self.bonds.add(key)
        return True

    def toggle_topology(self, key) -> bool:
        if key in self.topology:
            self.topology.discard(key)
            return False
        self.topology.add(key)
        return True

    def invert(self, n_atoms: int) -> None:
        self.set_atoms(set(range(n_atoms)) - self.atoms)

    def copy(self) -> Selection:
        return Selection(set(self.atoms), set(self.bonds),
                         set(self.topology), list(self.order))

    def mask(self, n_atoms: int) -> np.ndarray:
        """Boolean array over the P1 cell -- what the scene builder
        needs to highlight."""
        out = np.zeros(n_atoms, dtype=bool)
        if self.atoms:
            valid = [a for a in self.atoms if 0 <= a < n_atoms]
            out[valid] = True
        return out

    def names_beyond(self, n_atoms: int) -> bool:
        """Does this selection name an atom the cell does not have?

        Asked before pruning, so that a selection which is still
        correct is left alone -- pruning it unconditionally would
        announce a selection change on every step of an optimisation.
        """
        return (any(a >= n_atoms for a in self.atoms)
                or any(b[0] >= n_atoms or b[1] >= n_atoms
                       for b in self.bonds))

    def prune(self, n_atoms: int) -> None:
        """Drop references to atoms that no longer exist (after a
        delete, a supercell, a change of space group)."""
        self.atoms = {a for a in self.atoms if 0 <= a < n_atoms}
        self.order = [a for a in self.order if a in self.atoms]
        self.bonds = {b for b in self.bonds
                      if b[0] < n_atoms and b[1] < n_atoms}


def _ordered(atoms) -> list:
    """The atoms as a list, deduplicated, first occurrence winning.

    Sets and dict keys are sorted on the way past: they have no order
    of their own, and taking one from the iteration order would make
    the same selection mean different things on different runs.
    """
    if isinstance(atoms, set | frozenset | dict):
        atoms = sorted(atoms)
    return list(dict.fromkeys(int(a) for a in atoms))


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


def bonds_between_elements(graph, cell, first: str,
                           second: str | None = None) -> set:
    """Keys of the bonds joining ``first`` to ``second``, either way
    round -- or ``first`` to anything when ``second`` is ``None``.

    Both ends are asked, not the order the bond was stored in: a
    Zn-O bond is stored O-Zn as often as not, and matching one
    direction would find half of them.
    """
    elements = cell.elements
    wanted = {first, second}
    keys = set()
    for bond in graph.bonds:
        pair = {elements[bond.i], elements[bond.j]}
        if second is None:
            if first in pair:
                keys.add(bond.key())
        elif pair == wanted:
            keys.add(bond.key())
    return keys


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
