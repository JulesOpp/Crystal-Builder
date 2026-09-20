"""Shared helpers for the polydentate probes."""
from collections import deque
import numpy as np
from xtal.io import FORMATS
from xtal.core import bonding, p1


def load(path):
    s = FORMATS.read(path)
    cell = p1.expand(s)
    g = bonding.graph(s)
    el = [str(e) for e in cell.elements]
    return s, cell, g, el


def env(g, el, i):
    """The sorted element multiset atom i is bonded to."""
    return tuple(sorted(el[j] for j, _ in g.neighbors_with_images(i)))


def unwrap(g, cell, seed, keep):
    """Cartesian positions of the piece reachable from ``seed``.

    ``keep(i)`` says whether an atom belongs; the walk stops at atoms
    it refuses.  Returns {atom index: unwrapped cartesian position},
    which is what makes a fragment that straddles a cell boundary one
    rigid object again.
    """
    M = cell.lattice.matrix
    out = {seed: np.asarray(cell.cart[seed], dtype=float)}
    queue = deque([seed])
    while queue:
        i = queue.popleft()
        for j, im in g.neighbors_with_images(i):
            if j in out or not keep(j):
                continue
            shift = np.asarray(im, dtype=float) @ M
            out[j] = np.asarray(cell.cart[j], dtype=float) + shift
            queue.append(j)
    return out


def outward(members, partners):
    """Unit vector from the members' centroid toward what was cut away."""
    d = partners.mean(axis=0) - members.mean(axis=0)
    return d / np.linalg.norm(d)


def laterals(members, point, axis):
    """Each member's offset from ``point``, perpendicular to ``axis``."""
    d = members - point
    return d - np.outer(d @ axis, axis)


def pair_cost(a, b):
    """Mean squared lateral difference under the better of two pairings.

    Both sets are in the framework frame, in the plane perpendicular to
    the shared axis, so a good joint is one where they coincide.
    """
    straight = np.mean(np.sum((a - b) ** 2, axis=1))
    crossed = np.mean(np.sum((a - b[::-1]) ** 2, axis=1))
    return min(straight, crossed)


def direction_cost(a, b):
    """Lateral mismatch of two member sets, as directions only.

    The absolute laterals cannot coincide when the two ends have
    different spans -- MFU-4l's node members are 1.4 A apart and the
    linker's are 2.8 -- so comparing them leaves a floor that has
    nothing to do with orientation.  Normalising first measures the
    twist alone, which is what the tie-break is about.
    """
    import numpy as np
    ua = a / np.linalg.norm(a, axis=1)[:, None]
    ub = b / np.linalg.norm(b, axis=1)[:, None]
    straight = np.mean(np.sum((ua - ub) ** 2, axis=1))
    crossed = np.mean(np.sum((ua - ub[::-1]) ** 2, axis=1))
    return min(straight, crossed)
