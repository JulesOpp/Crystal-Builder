"""
xtal.build.molecule
===================
What comes out of the builder, and the two things it turns into.

A molecule has no cell, so it is neither a :class:`~xtal.Structure`
nor quite a :class:`~xtal.commands.clipboard.Fragment`.  It is a
``Fragment`` plus the one thing a fragment has no business knowing --
which of its atoms are connection points -- and it converts to either
in a line:

* :meth:`Molecule.to_fragment` for the open cell, where
  :class:`~xtal.commands.clipboard.PasteFragment` already does the
  undo step, the bonds and the selection.
* :meth:`Molecule.to_structure` for a document of its own, in a box
  with enough vacuum that the periodic images do not see each other.

Both keep the bonds the builder gave them and perceive nothing, which
is the rule for any atom the user placed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from xtal.build.chem import CONNECTION, embed
from xtal.core.lattice import Lattice
from xtal.core.structure import Bond, Structure

#: How much empty space to leave around a molecule that gets a cell of
#: its own.  The same 5 A :func:`xtal.io.xyz._padded_box` gives a
#: cell-less XYZ, so a molecule built here and one read from a file
#: land in the same size of box.
PAD = 5.0


@dataclass(frozen=True)
class Molecule:
    """An embedded molecule: atoms, bonds, and which atoms connect."""

    elements: tuple[str, ...] = ()
    cart: np.ndarray = field(
        default_factory=lambda: np.zeros((0, 3)))
    bonds: tuple = ()                   # (i, j, order) within the set
    connections: tuple[int, ...] = ()   # indices of the X atoms
    smiles: str = ""
    name: str = ""

    @property
    def n_atoms(self) -> int:
        return len(self.elements)

    @property
    def n_connections(self) -> int:
        return len(self.connections)

    @property
    def body_elements(self) -> tuple[str, ...]:
        """The real atoms: what is left once the connection points are
        gone.  The same rule
        :attr:`xtal.mof.catalog.BuildingBlock.body_symbols` uses, so a
        molecule and the block written from it report one formula."""
        marked = set(self.connections)
        return tuple(s for i, s in enumerate(self.elements)
                     if i not in marked and s != CONNECTION)

    @property
    def formula(self) -> str:
        counts: dict[str, int] = {}
        for element in self.body_elements:
            counts[element] = counts.get(element, 0) + 1
        return "".join(f"{s}{n if n > 1 else ''}"
                       for s, n in sorted(counts.items()))

    def to_fragment(self):
        """The clipboard's currency, ready to paste."""
        from xtal.commands.clipboard import Fragment
        return Fragment(
            elements=self.elements,
            cart=np.array(self.cart, dtype=float),
            occupancies=(1.0,) * self.n_atoms,
            labels=("",) * self.n_atoms,
            bonds=self.bonds,
            source=self.name or self.smiles)

    def to_structure(self, pad: float = PAD) -> Structure:
        """A P1 cell with the molecule in the middle of it.

        Cubic and generous rather than a tight bounding box: the cell
        exists so the molecule has somewhere to be, and a box the
        shape of the molecule would make every later operation --
        rotating it, adding to it, relaxing it -- run into a face.
        """
        if self.n_atoms == 0:
            return Structure.empty(Lattice.cubic(2.0 * pad))
        span = float(np.ptp(self.cart, axis=0).max())
        lattice = Lattice.cubic(span + 2.0 * pad)
        centre = lattice.to_cart([0.5, 0.5, 0.5])
        structure = Structure.from_arrays(
            lattice, self.elements,
            lattice.to_frac(self.cart + centre), space_group="P1")
        for i, j, order in self.bonds:
            structure.add_bond(Bond(int(i), int(j), (0, 0, 0), order))
        structure.meta["title"] = self.name or self.smiles
        return structure


def from_smiles(text: str, name: str = "", seed: int = 0xf00d,
                optimise: bool = True,
                connection_points: bool = True) -> Molecule:
    """Build one molecule from a SMILES string.

    ``connection_points=False`` refuses a starred string rather than
    quietly dropping the stars.  A user who typed ``*c1ccccc1`` into
    the box that drops a molecule into a cell meant something by it,
    and a benzene with a silent extra hydrogen is a worse answer than
    being told this box does not do connection points.
    """
    elements, cart, bonds, connections = embed(text, seed=seed,
                                               optimise=optimise)
    if connections and not connection_points:
        from xtal.build.chem import BuildError
        raise BuildError(
            f"{text!r} marks {len(connections)} connection point(s), "
            f"which are only used when saving a building block")
    return Molecule(elements=elements, cart=cart, bonds=bonds,
                    connections=connections, smiles=str(text).strip(),
                    name=name)
