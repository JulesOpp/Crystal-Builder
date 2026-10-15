"""
xtal.core.molecule
==================
A molecule in a box, as a molecule: whole, and how symmetric.

A periodic code runs a gas-phase molecule as one molecule alone in a
big cell, and the cell then wraps it -- methane centred on a corner
has its hydrogens on four faces.  Everything that treats it as a
rigid body (its moments of inertia, the rotations a Hessian projects
out, the ideal gas's rotational entropy) needs it whole, so
:func:`whole` puts its atoms back beside each other over the stored
bond graph, as filling a pore does.

:func:`is_isolated` only *proposes* that a structure is a molecule --
the thermochemistry dialog preselects *Molecule* when it says so and
the user can always say otherwise -- so it asks for what is visible:
no bonded net that closes on its own image, and vacuum all round.

Markers are not atoms here, as everywhere chemistry is reasoned about.
"""

from __future__ import annotations

import numpy as np

from xtal.core import bonding, p1
from xtal.core import elements as el

#: Vacuum, A, that a molecule needs between it and its next image
#: along every axis before it is offered as a molecule.
VACUUM = 5.0

#: How far, A, a rotated atom may land from the atom it maps onto.
SYMMETRY_TOL = 0.1


def _graph(structure):
    """The stored graph, perceived on a copy if there is none, so
    asking whether a structure is a molecule never writes a graph
    onto the user's."""
    return bonding.graph(structure.copy())


def whole(structure):
    """``(elements, cart)`` of the P1 cell's real atoms, each bonded
    piece unwrapped so its atoms sit beside each other."""
    cell = p1.expand(structure)
    graph = _graph(structure)
    real = [i for i in range(cell.n_atoms)
            if not el.is_dummy(cell.elements[i])]
    offsets = graph.unwrap(real)
    frac = np.array([cell.frac[i] + offsets.get(i, 0) for i in real],
                    dtype=float).reshape(-1, 3)
    cart = frac @ structure.lattice.matrix
    return [cell.elements[i] for i in real], cart


def is_isolated(structure, vacuum: float = VACUUM) -> bool:
    """Whether ``structure`` looks like molecules alone in a box: no
    fragment of its bond graph periodic, and ``vacuum`` A clear across
    every face once its pieces are made whole."""
    cell = p1.expand(structure)
    real = [i for i in range(cell.n_atoms)
            if not el.is_dummy(cell.elements[i])]
    if not real:
        return False
    graph = _graph(structure)
    if any(fragment.periodic for fragment in graph.fragments()
           if fragment.atoms[0] in real):
        return False
    _elements, cart = whole(structure)
    lattice = structure.lattice
    frac = cart @ np.linalg.inv(lattice.matrix)
    widths = _perpendicular_widths(lattice.matrix)
    for axis in range(3):
        extent = frac[:, axis].max() - frac[:, axis].min()
        if (1.0 - extent) * widths[axis] < vacuum:
            return False
    return True


def _perpendicular_widths(matrix) -> np.ndarray:
    """The distance between opposite faces of the cell, per axis."""
    volume = abs(np.linalg.det(matrix))
    a, b, c = matrix
    return volume / np.array([np.linalg.norm(np.cross(b, c)),
                              np.linalg.norm(np.cross(c, a)),
                              np.linalg.norm(np.cross(a, b))])


def rotational_symmetry_number(elements, cart,
                               tol: float = SYMMETRY_TOL) -> int:
    """How many proper rotations about the centre of mass map the
    molecule onto itself, like atom onto like: water 2, ammonia 3,
    methane and benzene 12, CO2 2.

    Found by enumeration, not by naming a point group: every rotation
    of the molecule is fixed by where it sends two atoms whose
    directions from the centre are not parallel, so each candidate
    image of that pair is tried and kept if it maps everything."""
    from scipy.spatial import cKDTree

    elements = list(elements)
    masses = np.array([el.mass(e) for e in elements])
    r = np.asarray(cart, dtype=float)
    r = r - (masses[:, None] * r).sum(axis=0) / masses.sum()
    if len(r) == 1:
        return 1
    radii = np.linalg.norm(r, axis=1)
    off = np.flatnonzero(radii > tol)
    if not len(off):
        return 1
    axis = r[off[0]] / radii[off[0]]
    across = np.linalg.norm(np.cross(r, axis), axis=1)
    if np.all(across < tol):
        # Linear: the only rotation besides the identity is the C2
        # that swaps the ends, and only a centrosymmetric chain has it.
        return 2 if _maps(-r, r, elements, tol) else 1
    a = off[0]
    b = int(np.flatnonzero(across > tol)[np.argmax(
        across[across > tol])])
    frame = _frame(r[a], r[b])
    trees = {}
    for e in set(elements):
        idx = [i for i, x in enumerate(elements) if x == e]
        trees[e] = (cKDTree(r[idx]), idx)
    found = []
    for a2 in range(len(r)):
        if elements[a2] != elements[a] or abs(radii[a2] - radii[a]) > tol:
            continue
        for b2 in range(len(r)):
            if b2 == a2 or elements[b2] != elements[b]:
                continue
            if abs(radii[b2] - radii[b]) > tol:
                continue
            if abs(np.linalg.norm(r[a2] - r[b2])
                   - np.linalg.norm(r[a] - r[b])) > tol:
                continue
            rotation = _frame(r[a2], r[b2]) @ frame.T
            if any(np.allclose(rotation, seen, atol=1e-3)
                   for seen in found):
                continue
            if _maps(r @ rotation.T, r, elements, tol, trees):
                found.append(rotation)
    return max(len(found), 1)


def _frame(u, v) -> np.ndarray:
    """An orthonormal frame, as columns, fixed by two directions."""
    e1 = u / np.linalg.norm(u)
    e2 = v - np.dot(v, e1) * e1
    e2 = e2 / np.linalg.norm(e2)
    return np.column_stack([e1, e2, np.cross(e1, e2)])


def _maps(moved, r, elements, tol, trees=None) -> bool:
    """Whether every moved atom lands on an atom of its element."""
    from scipy.spatial import cKDTree

    if trees is None:
        trees = {}
        for e in set(elements):
            idx = [i for i, x in enumerate(elements) if x == e]
            trees[e] = (cKDTree(r[idx]), idx)
    for i, point in enumerate(moved):
        tree, _idx = trees[elements[i]]
        distance, _j = tree.query(point)
        if distance > tol:
            return False
    return True
