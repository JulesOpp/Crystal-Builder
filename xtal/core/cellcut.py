"""
xtal.core.cellcut
=================
One unit cell as a finite object: every atom in it, and its bonds.

A crystal has no edges, and everything that makes a *thing* out of
one -- a printed model, a PDB for a program with no idea what a
lattice is -- has to decide where the edges go.  The answer here is
the one the viewport draws by default: the cell, faces and corners
included, so a cubic cell with an atom at the origin has eight of it.
That is what a person holding the model expects to see, and it is
what makes the printed cell look like the picture.

**The bonds are the document's, not a second opinion.**  They come
from :func:`xtal.core.bonding.graph` of the structure as it is, so a
bond the user suppressed stays gone and one they drew is there.  A
bond is kept between two images that are both in the cut; one that
leaves the cell is dropped, unless ``bonded_partners`` asks for the
atom at its far end to be brought in -- which is what keeps a linker
from printing as a row of loose carbons along a face.  Only one layer
is brought in: a partner's own partners outside the cell would be the
next cell, and the one after that.

A net edge is not a bond and a marker is not an atom, and neither is
cut.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np

from xtal.core import bonding, p1
from xtal.core import elements as el

#: How close to a face, in fractional units, counts as on it.  The same
#: tolerance the viewport draws with, so the model has the atoms the
#: picture has.
FACE_TOL = 1e-6


@dataclass(frozen=True)
class CellCut:
    """Atoms at cartesian positions, and bonds ``(i, j, order)``
    between them."""

    elements: tuple = ()
    cart: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))
    bonds: tuple = ()

    @property
    def n_atoms(self) -> int:
        return len(self.elements)


def cut_cell(structure, bonded_partners: bool = False,
             tol: float = FACE_TOL) -> CellCut:
    """Every atom image in ``[0, 1]`` along each axis, and the bonds
    between them.  See the module docstring."""
    cell = p1.expand(structure)
    graph = bonding.graph(structure)
    orders = bonding.orders(structure)
    solid = [k for k in range(cell.n_atoms)
             if not el.is_dummy(cell.elements[k])]

    images: dict[tuple, int] = {}
    for k in solid:
        frac = cell.frac[k]
        choices = [[0] + ([1] if f < tol else []) + ([-1] if f > 1 - tol
                                                     else [])
                   for f in frac]
        for shift in itertools.product(*choices):
            images.setdefault((k, shift), len(images))

    chemical = [(number, bond) for number, bond in enumerate(graph.bonds)
                if not (el.is_dummy(cell.elements[bond.i])
                        or el.is_dummy(cell.elements[bond.j]))]
    if bonded_partners:
        shifts_of = _by_atom(images)
        for _number, bond in chemical:
            t = np.asarray(bond.image, dtype=int)
            for shift in shifts_of.get(bond.i, ()):
                images.setdefault((bond.j, _add(shift, t)), len(images))
            for shift in shifts_of.get(bond.j, ()):
                images.setdefault((bond.i, _add(shift, -t)), len(images))

    keys = sorted(images, key=images.get)
    shifts_of = _by_atom(images)
    frac = np.array([cell.frac[k] + np.array(shift)
                     for k, shift in keys]).reshape(-1, 3)
    bonds = {}
    for number, bond in chemical:
        t = np.asarray(bond.image, dtype=int)
        for shift in shifts_of.get(bond.i, ()):
            i = images[(bond.i, shift)]
            j = images.get((bond.j, _add(shift, t)))
            if j is not None and j != i:
                bonds[(min(i, j), max(i, j))] = float(orders[number])
    return CellCut(
        elements=tuple(cell.elements[k] for k, _shift in keys),
        cart=structure.lattice.to_cart(frac) if len(keys)
        else np.zeros((0, 3)),
        bonds=tuple((i, j, order)
                    for (i, j), order in sorted(bonds.items())))


def _by_atom(images) -> dict:
    out: dict[int, list] = {}
    for k, shift in images:
        out.setdefault(k, []).append(shift)
    return out


def _add(shift, t) -> tuple:
    return tuple(int(v) for v in np.add(shift, t))
