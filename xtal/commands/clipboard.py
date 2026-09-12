"""
xtal.commands.clipboard
=======================
Copy and paste, as a self-contained fragment of structure.

A :class:`Fragment` is cartesian and cell-free: atoms, their internal
bonds, and nothing about where they came from.  That is what makes it
paste sensibly into a different cell, and what makes the XYZ text form
a genuine interchange with every other atomistic program.

Pasting into a structure that has symmetry adds the atoms to the
*asymmetric unit*, so the group multiplies them.  That is what a
crystallographer usually wants -- paste a ligand into a framework and
get it everywhere -- but it is emphatically not what an unsuspecting
user expects, so :meth:`PasteFragment.describe` spells it out and the
UI shows it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from xtal.commands.base import Command
from xtal.core import bonding
from xtal.core import elements as el
from xtal.core.site import Site
from xtal.core.structure import Bond, Change


@dataclass(frozen=True)
class Fragment:
    """Atoms and bonds lifted out of a structure, in cartesian space."""

    elements: tuple = ()
    cart: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))
    occupancies: tuple = ()
    labels: tuple = ()
    bonds: tuple = ()                   # (i, j, order) within the set
    source: str = ""
    #: Indices into ``bonds`` whose order the user *set* -- see
    #: :attr:`xtal.core.structure.Bond.stated`.  Apart from ``bonds``
    #: rather than a fourth member of each, because every molecule
    #: builder writes three.
    stated: frozenset = frozenset()

    @property
    def n_atoms(self) -> int:
        return len(self.elements)

    @property
    def is_empty(self) -> bool:
        return self.n_atoms == 0

    @property
    def formula(self) -> str:
        counts: dict[str, int] = {}
        for symbol in self.elements:
            counts[symbol] = counts.get(symbol, 0) + 1
        return "".join(f"{k}{v}" if v > 1 else k
                       for k, v in sorted(counts.items()))

    @property
    def centroid(self) -> np.ndarray:
        if self.is_empty:
            return np.zeros(3)
        return self.cart.mean(axis=0)

    # -- construction --------------------------------------------------

    @classmethod
    def from_selection(cls, structure, cell, atoms, graph=None
                       ) -> Fragment:
        """Copy the selected atoms of the P1 cell.

        Coordinates are recentred on the selection's centroid, so a
        paste lands where it is put rather than where the original
        happened to sit.

        Unwrapped over the bonds first (:meth:`BondGraph.unwrap
        <xtal.core.bonding.BondGraph.unwrap>`).  Taken from the cell as
        it is drawn, a molecule lying across a face came out in two
        pieces a cell apart, and pasted with its bonds stretched the
        whole way between them.
        """
        chosen = sorted(int(a) for a in atoms)
        if not chosen:
            return cls()
        offsets = (graph.unwrap(chosen) if graph is not None
                   else {a: np.zeros(3, dtype=int) for a in chosen})
        frac = cell.frac[chosen] + np.array([offsets[a] for a in chosen])
        cart = structure.lattice.to_cart(frac)
        cart = cart - cart.mean(axis=0)
        position = {atom: i for i, atom in enumerate(chosen)}
        bonds, stated = [], set()
        if graph is not None:
            for bond in graph.bonds:
                if not (bond.i in position and bond.j in position):
                    continue
                if not graph.consistent(bond, offsets):
                    continue
                if bond.stated:
                    stated.add(len(bonds))
                # Perceived bonds carry no bond order -- we do not
                # guess one from geometry -- so they copy as single.
                bonds.append((position[bond.i], position[bond.j],
                              getattr(bond, "order", 1.0)))
        return cls(
            elements=tuple(cell.elements[a] for a in chosen),
            cart=cart,
            occupancies=tuple(float(cell.occupancy[a])
                              for a in chosen),
            labels=tuple(cell.labels[a] for a in chosen),
            bonds=tuple(bonds),
            source=str(structure.meta.get("title", "")),
            stated=frozenset(stated),
        )

    def without_dummies(self) -> Fragment:
        """The same fragment with its markers taken out.

        What goes into a pore is chemistry, and a centroid somebody
        placed on the solvent they drew is not -- see
        :data:`xtal.core.elements.DUMMY_ELEMENTS`.
        """
        keep = [k for k, symbol in enumerate(self.elements)
                if not el.is_dummy(symbol)]
        if len(keep) == self.n_atoms:
            return self
        position = {old: new for new, old in enumerate(keep)}
        bonds, stated = [], set()
        for k, (i, j, order) in enumerate(self.bonds):
            if i in position and j in position:
                if k in self.stated:
                    stated.add(len(bonds))
                bonds.append((position[i], position[j], order))
        cart = self.cart[keep] if keep else np.zeros((0, 3))
        return Fragment(
            elements=tuple(self.elements[k] for k in keep),
            cart=cart - cart.mean(axis=0) if keep else cart,
            occupancies=tuple(self.occupancies[k] for k in keep),
            labels=tuple(self.labels[k] for k in keep),
            bonds=tuple(bonds), source=self.source,
            stated=frozenset(stated))

    def to_sites(self, lattice, offset=None) -> list[Site]:
        """Convert to sites of a cell, centred on ``offset``
        (cartesian, default the cell centre)."""
        if offset is None:
            offset = lattice.to_cart([0.5, 0.5, 0.5])
        offset = np.asarray(offset, dtype=float).reshape(3)
        frac = lattice.to_frac(self.cart + offset)
        return [Site(element, coordinates, occupancy=occupancy)
                for element, coordinates, occupancy
                in zip(self.elements, frac, self.occupancies,
                       strict=True)]

    # -- text interchange ----------------------------------------------

    def to_xyz(self) -> str:
        lines = [str(self.n_atoms),
                 f"copied from Crystal Builder {self.source}".strip()]
        for element, (x, y, z) in zip(self.elements, self.cart,
                                      strict=True):
            lines.append(f"{element:<4s} {x: 12.6f} {y: 12.6f} "
                         f"{z: 12.6f}")
        return "\n".join(lines) + "\n"

    @classmethod
    def from_xyz(cls, text: str) -> Fragment:
        lines = [line for line in text.splitlines() if line.strip()]
        if len(lines) < 2:
            raise ValueError("not an XYZ fragment")
        try:
            count = int(lines[0].split()[0])
        except (ValueError, IndexError):
            raise ValueError("not an XYZ fragment") from None
        elements, cart = [], []
        for line in lines[2:2 + count]:
            parts = line.split()
            if len(parts) < 4:
                raise ValueError(f"malformed XYZ line: {line!r}")
            elements.append(el.parse_symbol(parts[0]))
            cart.append([float(v) for v in parts[1:4]])
        if len(elements) != count:
            raise ValueError("XYZ atom count does not match its lines")
        positions = np.array(cart, dtype=float).reshape(-1, 3)
        return cls(elements=tuple(elements),
                   cart=positions - positions.mean(axis=0),
                   occupancies=(1.0,) * count,
                   labels=("",) * count)


class PasteFragment(Command):
    """Add a fragment's atoms (and its internal bonds) to a
    structure."""

    change = Change.TOPOLOGY

    def __init__(self, fragment: Fragment, offset=None,
                 label: str | None = None):
        self.fragment = fragment
        self.offset = offset
        self.label = label or f"Paste {fragment.formula}"
        self.indices: list[int] = []
        self._bonds: list[Bond] = []
        self._perceived = None          # see AddSites._perceived

    def describe(self, structure) -> str:
        """What the paste will actually do, symmetry included."""
        n = self.fragment.n_atoms
        group = structure.space_group
        if group.is_p1:
            return f"paste {n} atom(s)"
        return (f"paste {n} atom(s) into {group.short_name}: the group "
                f"will multiply them by up to {group.order}")

    def do(self, host) -> None:
        """Place the atoms with the fragment's own bonds and no others.

        A fragment arrives with its bonding already settled -- copied
        out of a structure, read from somebody else's XYZ, or built
        from a SMILES string -- and it lands wherever the user pointed.
        Left to perception it would also pick up a distance-perceived
        bond to whatever it happened to land beside, which is the
        second opinion :data:`xtal.core.structure.CHEMISTRY` exists to
        refuse; a molecule dropped into a framework would arrive
        already bonded into it.  See
        :func:`xtal.core.bonding.hold_perception`.
        """
        structure = host.structure
        self._perceived = structure.perceived
        sites = self.fragment.to_sites(structure.lattice, self.offset)
        self.indices, self._bonds = _add_copies(
            structure, self.fragment, [sites])

    def undo(self, host) -> None:
        _remove_copies(host.structure, self.indices, self._bonds)
        host.structure.perceived = self._perceived


def _add_copies(structure, fragment, copies) -> tuple[list, list]:
    """Append each copy's sites with the fragment's own bonds and no
    others, in one expansion.  ``(site indices, bonds added)``.

    One expansion is the point of taking a list.  Holding perception
    expands the cell, and forty guests added one at a time into a
    framework is forty expansions of a cell that grows each time --
    the atom-by-atom pattern that made Select All -> Set Bond Type
    stall on MFU-4l.
    """
    bonding.prepare_hold(structure)
    fresh = []
    taken: list[str] = []
    for sites in copies:
        for site in sites:
            site.label = structure.suggest_label(site.element,
                                                 taken=taken)
            taken.append(site.label)
            fresh.append(site)
    indices = structure.add_sites(fresh)
    bonding.hold_perception(structure)
    bonds = []
    n = fragment.n_atoms
    for copy in range(len(copies)):
        first = indices[copy * n:(copy + 1) * n]
        for k, (i, j, order) in enumerate(fragment.bonds):
            bond = Bond(first[i], first[j], (0, 0, 0), order,
                        stated=k in fragment.stated)
            if structure.add_bond(bond):
                bonds.append(bond)
    return indices, bonds


def _remove_copies(structure, indices, bonds) -> None:
    # The bonds first: removing the sites renumbers everything after
    # them, and these name the atoms being taken out.
    for bond in bonds:
        structure.remove_bond(bond)
    structure.remove_sites(indices)


class InsertMolecules(Command):
    """Many copies of one molecule, each where it was put, as one edit.

    What filling a pore with solvent commits -- the placing is
    :func:`xtal.build.fill.place`, and this is only the part that can
    be undone.  Each copy arrives with the molecule's own bonds and no
    others: forty solvent molecules a van der Waals contact from a
    framework are forty molecules a bond criterion could be persuaded
    to join to it, and bonds change when the user asks.

    **A host with symmetry is reduced to P1 first, in the same step.**
    A guest added to an asymmetric unit is multiplied by the group,
    and every overlap test that placed it was made against one copy --
    the group's other forty-seven would land on top of the framework
    and of each other.  One Ctrl+Z takes the guests and the reduction
    back together, because a user who undoes the fill did not ask to
    be left holding a P1 cell.
    """

    def __init__(self, fragment: Fragment, positions,
                 label: str | None = None):
        self.fragment = fragment
        self.positions = [np.asarray(p, dtype=float).reshape(-1, 3)
                          for p in positions]
        self.label = label or (f"Fill pores with {len(self.positions)} "
                               f"{fragment.formula}")
        self.indices: list[int] = []
        self._bonds: list[Bond] = []
        self._perceived = None
        self._reduce = None

    @property
    def change(self) -> Change:
        if self._reduce is not None:
            return Change.SYMMETRY | Change.TOPOLOGY
        return Change.TOPOLOGY

    def do(self, host) -> None:
        from xtal.commands.symmetry import ReduceToP1
        self._reduce = None
        if not host.structure.space_group.is_p1:
            self._reduce = ReduceToP1()
            self._reduce.do(host)
        structure = host.structure
        self._perceived = structure.perceived
        lattice = structure.lattice
        copies = [
            [Site(symbol, frac, occupancy=occupancy)
             for symbol, frac, occupancy
             in zip(self.fragment.elements, lattice.to_frac(cart),
                    self.fragment.occupancies, strict=True)]
            for cart in self.positions]
        self.indices, self._bonds = _add_copies(structure,
                                                self.fragment, copies)

    def undo(self, host) -> None:
        _remove_copies(host.structure, self.indices, self._bonds)
        host.structure.perceived = self._perceived
        if self._reduce is not None:
            self._reduce.undo(host)
