"""
xtal.commands.cell
==================
Undoable changes to the unit cell.

Editing a cell is ambiguous and the ambiguity is the whole point:
stretching *a* can either drag the atoms along with it (fractional
coordinates fixed, bonds stretch) or leave them where they are in space
(cartesian positions fixed, fractional coordinates rescale).  The
command takes ``keep`` rather than picking one, and the dialog asks.

The rest of this module changes the *basis* rather than the metric: a
supercell, a general integer transformation, a reduction to the
shortest basis, a shift of the origin.  All of them rebuild the
structure and all of them land it in P1, because "which sites are
independent" is a question about a particular cell and stops meaning
anything the moment the cell changes.  Find the symmetry again
afterwards -- that is what :class:`xtal.commands.symmetry.FindSymmetry`
is for.
"""

from __future__ import annotations

import numpy as np

from xtal.commands.base import Command, StructureOperation
from xtal.core import supercell as sc
from xtal.core.lattice import Lattice
from xtal.core.structure import Change


class SetLattice(Command):
    """Replace the cell, keeping either fractional or cartesian
    coordinates."""

    change = Change.CELL

    def __init__(self, lattice: Lattice, keep: str = "fractional",
                 label: str = "Edit unit cell"):
        if keep not in ("fractional", "cartesian"):
            raise ValueError("keep must be 'fractional' or 'cartesian'")
        self.lattice = lattice
        self.keep = keep
        self.label = label
        self._old_lattice: Lattice | None = None
        self._old_frac: list = []

    def do(self, host) -> None:
        structure = host.structure
        self._old_lattice = structure.lattice
        self._old_frac = [site.frac.copy() for site in structure.sites]
        if self.keep == "cartesian":
            cart = [self._old_lattice.to_cart(f) for f in self._old_frac]
            for site, position in zip(structure.sites, cart,
                                      strict=True):
                site.frac = self.lattice.to_frac(position)
        structure.set_lattice(self.lattice)

    def undo(self, host) -> None:
        structure = host.structure
        for site, frac in zip(structure.sites, self._old_frac,
                              strict=True):
            site.frac = frac.copy()
        structure.set_lattice(self._old_lattice)


# ======================================================================
#  CHANGING THE BASIS
# ======================================================================

class Supercell(StructureOperation):
    """Build an na x nb x nc supercell.  The result is in P1."""

    change = Change.CELL | Change.SYMMETRY | Change.TOPOLOGY

    def __init__(self, na: int, nb: int, nc: int):
        super().__init__()
        self.counts = (int(na), int(nb), int(nc))
        self.label = "Supercell {}x{}x{}".format(*self.counts)

    def apply_to(self, structure):
        out = sc.supercell(structure, *self.counts)
        return out, _report(structure, out, self.label.lower())


class TransformCell(StructureOperation):
    """Apply a general integer cell transformation P.

    ``|det P| = 1`` re-expresses the same crystal in a different basis
    -- the way to turn a C-centred monoclinic cell into its primitive
    one, or to pick a different set of axes -- and a larger determinant
    builds a supercell that ``na x nb x nc`` cannot express.
    """

    change = Change.CELL | Change.SYMMETRY | Change.TOPOLOGY
    label = "Transform cell"

    def __init__(self, p_matrix):
        super().__init__()
        self.p_matrix = np.asarray(p_matrix, dtype=float).reshape(3, 3)

    def apply_to(self, structure):
        out = sc.transform_cell(structure, self.p_matrix)
        det = int(round(float(np.linalg.det(self.p_matrix))))
        return out, _report(
            structure, out,
            f"transformed the basis (det P = {det})")


class ReduceCell(StructureOperation):
    """Niggli- or Delaunay-reduce the cell: the same crystal on the
    shortest, most nearly orthogonal basis there is."""

    change = Change.CELL | Change.SYMMETRY | Change.TOPOLOGY

    def __init__(self, kind: str = "niggli", eps: float = 1e-5):
        super().__init__()
        if kind not in ("niggli", "delaunay"):
            raise ValueError("kind must be 'niggli' or 'delaunay'")
        self.kind = kind
        self.eps = float(eps)
        self.label = f"{kind.capitalize()} reduction"

    def apply_to(self, structure):
        reduce = (sc.niggli_reduce if self.kind == "niggli"
                  else sc.delaunay_reduce)
        out = reduce(structure, self.eps)
        return out, _report(structure, out,
                            f"{self.kind}-reduced the cell")


class ShiftOrigin(StructureOperation):
    """Move the origin: every atom moves by ``-shift``.

    The group is kept, which is only meaningful for a shift the group
    allows -- find the symmetry again if in doubt.
    """

    change = Change.POSITIONS
    label = "Shift origin"

    def __init__(self, shift):
        super().__init__()
        self.shift = np.asarray(shift, dtype=float).reshape(3)

    def apply_to(self, structure):
        out = sc.shift_origin(structure, self.shift)
        x, y, z = self.shift
        return out, _report(
            structure, out,
            f"moved the origin to ({x:g}, {y:g}, {z:g})")


class WrapIntoCell(StructureOperation):
    """Fold every site back into [0, 1)."""

    change = Change.POSITIONS
    label = "Wrap into the cell"

    def apply_to(self, structure):
        out = sc.wrap_into_cell(structure)
        return out, _report(structure, out,
                            "folded every site into the cell")


def _report(before, after, message: str):
    """The same shape of report the symmetry operations return, so a
    dialog can show either without caring which it got."""
    from xtal.core import p1
    from xtal.core.symmetry import SymmetryReport

    n_before = p1.expand(before).n_atoms
    n_after = p1.expand(after).n_atoms
    return SymmetryReport(
        n_before=n_before, n_after=n_after,
        message=(f"{message}: {after.n_sites} sites, {n_after} atoms, "
                 f"V = {after.lattice.volume:.2f} A^3"))
