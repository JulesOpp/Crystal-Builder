"""
xtal.fullerene.geometry
=======================
Where a cage's atoms go, from its graph alone.

**Topological coordinates** (Manolopoulos and Fowler 1992): the three
eigenvectors of the adjacency matrix just below its largest each have
one nodal plane, so read as x, y and z they put the atoms on a closed
surface in the order the graph has them.  C20 and C60 come out as
spheres with every bond within a few percent; a less symmetric cage
comes out lumpier, with its bonds from 0.9 to 1.15 of their length.

**Springs** then even it out: each bond held at its length, each pair
of bonds meeting at an atom held at a hexagon's 120 degrees by its
1-3 distance, and every other pair pushed apart where it comes inside
1.8 bonds.  That is a shape, not a structure anybody relaxed: the
pentagons' 108 degrees strain against the 1-3 springs, which is the
curvature.  :mod:`xtal.fullerene.build` relaxes it with UFF after.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize
from scipy.spatial import cKDTree

__all__ = ["topological", "springs", "positions"]

#: Unbonded pairs beyond the 1-3 ones are pushed apart inside this
#: many bonds: a hexagon's opposite atoms are two apart, a
#: pentagon's 1-3 pairs 1.62.
APART = 1.8


def topological(n: int, bonds) -> np.ndarray:
    """The three eigenvectors below the largest, scaled to a mean
    bond of one."""
    adjacency = np.zeros((n, n))
    for a, b in bonds:
        adjacency[a, b] = adjacency[b, a] = 1.0
    _values, vectors = np.linalg.eigh(adjacency)
    xyz = vectors[:, -4:-1].copy()
    xyz -= xyz.mean(axis=0)
    bonds = np.asarray(bonds)
    lengths = np.linalg.norm(xyz[bonds[:, 0]] - xyz[bonds[:, 1]], axis=1)
    return xyz / lengths.mean()


def _second_neighbours(n, bonds):
    neighbours = [set() for _ in range(n)]
    for a, b in bonds:
        neighbours[a].add(b)
        neighbours[b].add(a)
    pairs = {(min(i, k), max(i, k)) for j in range(n)
             for i in neighbours[j] for k in neighbours[j] if i != k}
    return np.array(sorted(pairs))


def _keys(pairs, n: int) -> np.ndarray:
    """Each pair of atoms as one integer, whichever way round."""
    pairs = np.sort(np.asarray(pairs, dtype=np.int64).reshape(-1, 2),
                    axis=1)
    return pairs[:, 0] * n + pairs[:, 1]


def springs(xyz, bonds, bond: float = 1.0) -> np.ndarray:
    """``xyz`` relaxed under the springs, in units where ``bond`` is
    the bond's length."""
    n = len(xyz)
    bonds = np.asarray(bonds)
    second = _second_neighbours(n, bonds)
    # Pairs as i * n + j, i < j, so the pairs the springs already hold
    # are dropped from the KD-tree's in one step, not by a Python loop
    # over every pair on every iteration.
    near = np.unique(np.concatenate([_keys(bonds, n), _keys(second, n)]))
    targets = ((bonds, bond), (second, bond * np.sqrt(3.0)))

    def energy(flat):
        x = flat.reshape(n, 3)
        grad = np.zeros_like(x)
        total = 0.0
        for pairs, length in targets:
            d = x[pairs[:, 0]] - x[pairs[:, 1]]
            r = np.linalg.norm(d, axis=1)
            stretch = r - length
            total += float(stretch @ stretch)
            f = (2.0 * stretch / np.maximum(r, 1e-12))[:, None] * d
            np.add.at(grad, pairs[:, 0], f)
            np.add.at(grad, pairs[:, 1], -f)
        reach = APART * bond
        close = cKDTree(x).query_pairs(reach, output_type="ndarray")
        close = close[~np.isin(_keys(close, n), near)]
        if len(close):
            d = x[close[:, 0]] - x[close[:, 1]]
            r = np.linalg.norm(d, axis=1)
            short = reach - r
            total += float(short @ short)
            f = (-2.0 * short / np.maximum(r, 1e-12))[:, None] * d
            np.add.at(grad, close[:, 0], f)
            np.add.at(grad, close[:, 1], -f)
        return total, grad.ravel()

    found = minimize(energy, np.asarray(xyz, float).ravel(), jac=True,
                     method="L-BFGS-B", options={"maxiter": 5000})
    out = found.x.reshape(n, 3)
    return out - out.mean(axis=0)


def positions(n: int, bonds, bond: float) -> np.ndarray:
    """The cage's Cartesian positions, centred on the origin, with its
    mean bond ``bond``.  Scaled after the springs: the pentagons pull
    against the hexagon's 1-3 springs and leave every bond about 2 %
    long, which a cage left unrelaxed would keep."""
    xyz = springs(topological(n, bonds) * bond, bonds, bond)
    pairs = np.asarray(bonds)
    lengths = np.linalg.norm(xyz[pairs[:, 0]] - xyz[pairs[:, 1]], axis=1)
    return xyz * (bond / lengths.mean())
