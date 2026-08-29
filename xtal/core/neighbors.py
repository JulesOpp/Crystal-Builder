"""
xtal.core.neighbors
===================
Periodic neighbour search: which atoms are within r Angstrom of which,
and through which lattice translation.

Everything that needs distances -- bond perception, coordination
numbers, clash detection, the force field's pair terms -- goes through
here, so the periodic-image bookkeeping is written once.

The lattice translation is part of the answer, not an implementation
detail: a pair (i, j, t) means "atom i and the copy of atom j shifted
by t lattice vectors".  Two atoms can be neighbours through several
different t at once (a short cell axis), and each of those is a
separate, real contact.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from xtal.core.lattice import Lattice


@dataclass(frozen=True)
class PairList:
    """Neighbour pairs, each listed once.

    ``i``, ``j`` index atoms of the cell; ``image`` is the translation
    applied to ``j``; ``distance`` is in Angstrom; ``vector`` is the
    cartesian j-minus-i separation.
    """

    i: np.ndarray
    j: np.ndarray
    image: np.ndarray               # (M,3) int
    distance: np.ndarray            # (M,)
    vector: np.ndarray              # (M,3) cartesian

    def __len__(self) -> int:
        return len(self.i)

    def filter(self, mask) -> PairList:
        mask = np.asarray(mask, dtype=bool)
        return PairList(self.i[mask], self.j[mask], self.image[mask],
                        self.distance[mask], self.vector[mask])

    def sorted_by_distance(self) -> PairList:
        order = np.argsort(self.distance)
        return PairList(self.i[order], self.j[order], self.image[order],
                        self.distance[order], self.vector[order])


def perpendicular_widths(lattice: Lattice) -> np.ndarray:
    """Distance between opposite faces of the cell, per axis.  This is
    what decides how many periodic images a cutoff needs -- cell edge
    lengths are not enough for a skewed cell."""
    m = lattice.matrix
    widths = []
    for k in range(3):
        i, j = [x for x in range(3) if x != k]
        area = np.linalg.norm(np.cross(m[i], m[j]))
        widths.append(lattice.volume / area)
    return np.array(widths)


def image_range(lattice: Lattice, cutoff: float) -> tuple[int, int, int]:
    """How many cells to replicate along each axis to cover ``cutoff``.
    """
    if cutoff <= 0:
        raise ValueError("cutoff must be positive")
    n = np.ceil(cutoff / perpendicular_widths(lattice)).astype(int)
    return tuple(int(max(1, v)) for v in n)


def neighbor_pairs(frac, lattice: Lattice, cutoff: float,
                   min_distance: float = 1e-6) -> PairList:
    """Every pair of atoms closer than ``cutoff``, listed once.

    A pair appears once per periodic image that satisfies the cutoff.
    Self-pairs through a lattice translation (an atom and its own copy
    in the next cell) are included -- for a small cell they are real
    contacts.
    """
    frac = np.asarray(frac, dtype=float).reshape(-1, 3)
    n = len(frac)
    if n == 0:
        return _empty_pairs()

    na, nb, nc = image_range(lattice, cutoff)
    shifts = np.array(list(itertools.product(
        range(-na, na + 1), range(-nb, nb + 1), range(-nc, nc + 1))))

    cart = lattice.to_cart(frac)
    ghost = (cart[None, :, :]
             + lattice.to_cart(shifts)[:, None, :]).reshape(-1, 3)
    ghost_atom = np.tile(np.arange(n), len(shifts))
    ghost_shift = np.repeat(shifts, n, axis=0)

    tree = cKDTree(cart)
    ghost_tree = cKDTree(ghost)
    hits = tree.query_ball_tree(ghost_tree, r=cutoff)

    ii, jj, tt = [], [], []
    for i, matches in enumerate(hits):
        for g in matches:
            j = int(ghost_atom[g])
            t = ghost_shift[g]
            # Keep each physical pair once: i<j, or the same atom
            # through a lexicographically positive translation.
            if j < i:
                continue
            if j == i and tuple(t) <= (0, 0, 0):
                continue
            ii.append(i)
            jj.append(j)
            tt.append(t)

    if not ii:
        return _empty_pairs()

    i_arr = np.array(ii, dtype=int)
    j_arr = np.array(jj, dtype=int)
    t_arr = np.array(tt, dtype=int).reshape(-1, 3)
    vec = (cart[j_arr] + lattice.to_cart(t_arr)) - cart[i_arr]
    dist = np.linalg.norm(vec, axis=1)
    keep = dist >= min_distance
    return PairList(i_arr[keep], j_arr[keep], t_arr[keep], dist[keep],
                    vec[keep])


def _empty_pairs() -> PairList:
    return PairList(np.zeros(0, int), np.zeros(0, int),
                    np.zeros((0, 3), int), np.zeros(0),
                    np.zeros((0, 3)))


def min_image_vector(frac_a, frac_b, lattice: Lattice) -> np.ndarray:
    """Shortest cartesian vector from a to b under periodicity.

    Uses the 27 nearest images, which is exact for any cell that is
    not pathologically skewed (and every reduced cell).  For a
    guaranteed answer in a badly skewed cell, reduce it first.
    """
    d = np.asarray(frac_b, dtype=float) - np.asarray(frac_a, dtype=float)
    d -= np.round(d)
    shifts = np.array(list(itertools.product((-1, 0, 1), repeat=3)))
    candidates = lattice.to_cart(d + shifts)
    return candidates[np.argmin(np.linalg.norm(candidates, axis=1))]


def min_image_distance(frac_a, frac_b, lattice: Lattice) -> float:
    return float(np.linalg.norm(
        min_image_vector(frac_a, frac_b, lattice)))
