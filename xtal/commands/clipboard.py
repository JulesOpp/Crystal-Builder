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
        """
        chosen = sorted(int(a) for a in atoms)
        if not chosen:
            return cls()
        cart = structure.lattice.to_cart(cell.frac[chosen])
        cart = cart - cart.mean(axis=0)
        position = {atom: i for i, atom in enumerate(chosen)}
        bonds = []
        if graph is not None:
            for bond in graph.bonds:
                if bond.i in position and bond.j in position:
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
        )

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

    def describe(self, structure) -> str:
        """What the paste will actually do, symmetry included."""
        n = self.fragment.n_atoms
        group = structure.space_group
        if group.is_p1:
            return f"paste {n} atom(s)"
        return (f"paste {n} atom(s) into {group.short_name}: the group "
                f"will multiply them by up to {group.order}")

    def do(self, host) -> None:
        structure = host.structure
        sites = self.fragment.to_sites(structure.lattice, self.offset)
        for site in sites:
            site.label = structure.suggest_label(site.element)
        self.indices = structure.add_sites(sites)
        self._bonds = []
        for i, j, order in self.fragment.bonds:
            bond = Bond(self.indices[i], self.indices[j], (0, 0, 0),
                        order)
            if structure.add_bond(bond):
                self._bonds.append(bond)

    def undo(self, host) -> None:
        for bond in self._bonds:
            host.structure.remove_bond(bond)
        host.structure.remove_sites(self.indices)
