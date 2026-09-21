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


#: Below this, two atoms are not a pair: the vector between them has
#: no direction and 1/r has no value, so the pair is dropped rather
#: than allowed to divide by zero.  Dropping is right for the sum and
#: wrong for the answer, because the terms go missing in silence -- so
#: :func:`xtal.ff.registry._refuse_coincident` refuses a structure at
#: this same distance rather than let a force field report a finite
#: energy for a cell holding two atoms in one place.  The two must not
#: drift apart, which is why this is a name and not a literal.
MIN_SEPARATION = 1e-6


def neighbor_pairs(frac, lattice: Lattice, cutoff: float,
                   min_distance: float = MIN_SEPARATION,
                   subset=None) -> PairList:
    """Every pair of atoms closer than ``cutoff``, listed once.

    A pair appears once per periodic image that satisfies the cutoff.
    Self-pairs through a lattice translation (an atom and its own copy
    in the next cell) are included -- for a small cell they are real
    contacts.

    ``subset`` restricts the *search*, not the answer: every pair that
    comes back has at least one end in it, and the other end may be any
    atom at all.  That is what "perceive the bonds of the atom I just
    added" needs, and it costs a query per new atom rather than one per
    atom in the crystal -- which on a framework is the difference
    between adding a hydrogen and re-deriving the whole graph.
    """
    frac = np.asarray(frac, dtype=float).reshape(-1, 3)
    n = len(frac)
    if n == 0:
        return _empty_pairs()
    if subset is None:
        source = np.arange(n)
    else:
        source = np.unique(np.asarray(list(subset), dtype=int))
        if not len(source):
            return _empty_pairs()
        if source[0] < 0 or source[-1] >= n:
            raise IndexError(
                f"subset names an atom outside 0..{n - 1}")

    na, nb, nc = image_range(lattice, cutoff)
    shifts = np.array(list(itertools.product(
        range(-na, na + 1), range(-nb, nb + 1), range(-nc, nc + 1))))

    cart = lattice.to_cart(frac)
    ghost = (cart[None, :, :]
             + lattice.to_cart(shifts)[:, None, :]).reshape(-1, 3)
    ghost_atom = np.tile(np.arange(n), len(shifts))
    ghost_shift = np.repeat(shifts, n, axis=0)

    tree = cKDTree(cart[source])
    ghost_tree = cKDTree(ghost)
    # ``sparse_distance_matrix`` hands the hits back as arrays.  The
    # obvious alternative, ``query_ball_tree``, returns a list of lists
    # and the loop that unpacks it costs a second for a five-thousand
    # atom cell -- more than everything the force field does with the
    # answer.
    hits = tree.sparse_distance_matrix(ghost_tree, cutoff,
                                       output_type="ndarray")
    if not len(hits):
        return _empty_pairs()

    i_arr = source[hits["i"].astype(int)]
    ghosts = hits["j"].astype(int)
    j_arr = ghost_atom[ghosts]
    t_arr = ghost_shift[ghosts].reshape(-1, 3)

    # Keep each physical pair once: i<j, or the same atom through a
    # lexicographically positive translation.  A pair with only one end
    # in ``subset`` is found only once to begin with, so the tie-break
    # would throw half of those away rather than deduplicate them.
    tie_break = (j_arr > i_arr) | ((j_arr == i_arr)
                                   & lexicographically_positive(t_arr))
    if subset is None:
        keep_once = tie_break
    else:
        searched = np.zeros(n, dtype=bool)
        searched[source] = True
        keep_once = np.where(searched[j_arr], tie_break, True)
    i_arr, j_arr, t_arr = (i_arr[keep_once], j_arr[keep_once],
                           t_arr[keep_once])
    if not len(i_arr):
        return _empty_pairs()

    vec = (cart[j_arr] + lattice.to_cart(t_arr)) - cart[i_arr]
    dist = np.linalg.norm(vec, axis=1)
    keep = dist >= min_distance
    return PairList(i_arr[keep], j_arr[keep], t_arr[keep], dist[keep],
                    vec[keep])


def lexicographically_positive(shifts) -> np.ndarray:
    """Is each ``(a, b, c)`` greater than ``(0, 0, 0)``, read left to
    right?

    The tie-break that names a self-pair once.  An atom and its own
    image in the next cell are one contact described two ways -- by
    ``+t`` from one end and ``-t`` from the other -- so exactly one of
    the pair is kept, and this is the rule that picks it.
    """
    s = np.asarray(shifts, dtype=int).reshape(-1, 3)
    return ((s[:, 0] > 0)
            | ((s[:, 0] == 0) & (s[:, 1] > 0))
            | ((s[:, 0] == 0) & (s[:, 1] == 0) & (s[:, 2] > 0)))


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
