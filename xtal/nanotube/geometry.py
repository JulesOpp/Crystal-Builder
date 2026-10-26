"""
xtal.nanotube.geometry
======================
A single-walled nanotube from its roll-up vector: the (n,m) arithmetic
and one translational period of the sheet rolled onto a cylinder.

The construction is the textbook one (Dresselhaus, Dresselhaus and
Saito, Carbon 33, 883 (1995)).  The honeycomb has two sites a cell, A
and B; the chiral vector Ch = n a1 + m a2 becomes the circumference
and the shortest lattice vector perpendicular to it, T, the period
along the axis.  A site at (u, v) in the basis (Ch, T) goes to the
angle 2 pi u and the height v |T|, so arc length round the tube is the
sheet's own and a bond becomes a slightly shorter chord.

**The bonds come from the sheet, never from distances.**  Each A site
has its three B neighbours at fixed offsets; wrapping a neighbour's
(u, v) back into the period names it, and how far v wrapped is the
period it is in.  Wrapping in u is the seam that closes the tube, so a
bond across it is an ordinary bond, not a cell image.  Perceiving them
instead would be wrong exactly when it matters: a thin tube brings
unbonded atoms within bonding distance, which is what
:func:`bonding_clash` refuses.

Pure numpy and scipy; nothing here knows about elements.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

__all__ = ["Chirality", "Rolled", "roll", "shortest_bond",
           "closest_contact", "bonding_clash"]

#: How close to a period's edge a site still counts as on it.
_EPS = 1e-9

#: B - A for the three neighbours of an A site, in units of (a1, a2):
#: B sits at (a1 + a2) / 3.
_NEIGHBOURS = ((1 / 3, 1 / 3), (1 / 3 - 1, 1 / 3), (1 / 3, 1 / 3 - 1))


@dataclass(frozen=True)
class Chirality:
    """The (n,m) of a tube and the bond length it is rolled from."""

    n: int
    m: int
    bond: float = 1.42

    @property
    def a(self) -> float:
        """The sheet's lattice constant, sqrt(3) bonds."""
        return math.sqrt(3.0) * self.bond

    @property
    def a1(self) -> np.ndarray:
        return self.a * np.array([math.sqrt(3.0) / 2, 0.5])

    @property
    def a2(self) -> np.ndarray:
        return self.a * np.array([math.sqrt(3.0) / 2, -0.5])

    @property
    def ch(self) -> np.ndarray:
        return self.n * self.a1 + self.m * self.a2

    @property
    def circumference(self) -> float:
        return self.a * math.sqrt(self.n ** 2 + self.n * self.m
                                  + self.m ** 2)

    @property
    def diameter(self) -> float:
        return self.circumference / math.pi

    @property
    def theta(self) -> float:
        """Degrees from the zigzag direction: 0 for (n,0), 30 for
        (n,n), over 30 when m > n -- the mirror image of (m,n)."""
        return math.degrees(math.atan2(math.sqrt(3.0) * self.m,
                                       2 * self.n + self.m))

    @property
    def d_r(self) -> int:
        return math.gcd(2 * self.n + self.m, 2 * self.m + self.n)

    @property
    def t_indices(self) -> tuple[int, int]:
        return ((2 * self.m + self.n) // self.d_r,
                -(2 * self.n + self.m) // self.d_r)

    @property
    def t(self) -> np.ndarray:
        t1, t2 = self.t_indices
        return t1 * self.a1 + t2 * self.a2

    @property
    def t_length(self) -> float:
        return math.sqrt(3.0) * self.circumference / self.d_r

    @property
    def atoms_per_period(self) -> int:
        return 4 * (self.n ** 2 + self.n * self.m + self.m ** 2) \
            // self.d_r


@dataclass
class Rolled:
    """One period of a rolled tube, its axis along z from 0 to |T|."""

    cart: np.ndarray        # (N, 3)
    sublattice: np.ndarray  # (N,) 0 for an A site, 1 for a B site
    uv: np.ndarray          # (N, 2) in the basis (Ch, T), in [0, 1)
    bonds: np.ndarray       # (3N/2, 2): an A site, then a B site
    images: np.ndarray      # (3N/2,) the B site's period, relative


def roll(chirality: Chirality) -> Rolled:
    """One translational period of the tube, with its bonds."""
    c = chirality
    basis = np.column_stack([c.ch, c.t])
    inverse = np.linalg.inv(basis)
    sheet = np.vstack([c.a1, c.a2])
    corners = np.array([[0, 0], [1, 0], [0, 1], [1, 1]], float) @ \
        np.array([[c.n, c.m], c.t_indices], float)
    lo = np.floor(corners.min(axis=0)).astype(int) - 1
    hi = np.ceil(corners.max(axis=0)).astype(int) + 1
    i, j = np.meshgrid(np.arange(lo[0], hi[0] + 1),
                       np.arange(lo[1], hi[1] + 1), indexing="ij")
    cells = np.column_stack([i.ravel(), j.ravel()]).astype(float)
    uvs, subs = [], []
    for sub, offset in enumerate(((0.0, 0.0), (1 / 3, 1 / 3))):
        uv = ((cells + offset) @ sheet) @ inverse.T
        inside = np.all((uv > -_EPS) & (uv < 1 - _EPS), axis=1)
        uvs.append(_wrap(uv[inside]))
        subs.append(np.full(int(inside.sum()), sub))
    uv = np.vstack(uvs)
    sublattice = np.concatenate(subs)
    if len(uv) != c.atoms_per_period:           # pragma: no cover
        raise RuntimeError(f"({c.n},{c.m}): {len(uv)} sites a "
                           f"period, not {c.atoms_per_period}")
    grid = 6 * (c.n ** 2 + c.n * c.m + c.m ** 2)
    where = {(int(s),) + _key(p, grid): k
             for k, (s, p) in enumerate(zip(sublattice, uv, strict=True))}
    # A dict overwrites silently, so two sites on one key would leave a
    # site unreachable and its bonds pointing at another.
    if len(where) != len(uv):                   # pragma: no cover
        raise RuntimeError(f"({c.n},{c.m}): {len(uv) - len(where)} "
                           f"sites share a key")
    bonds, images = [], []
    for k in np.flatnonzero(sublattice == 0):
        # For (1,0), Ch = a1, so two offsets reach the same B and give
        # a duplicate bond; harmless, as the build refuses (1,0) on its
        # crushed bonds before it uses them.
        for du, dv in _NEIGHBOURS:
            target = uv[k] + (du * c.a1 + dv * c.a2) @ inverse.T
            images.append(int(math.floor(target[1] + _EPS)))
            bonds.append((int(k),
                          where[(1,) + _key(_wrap(target), grid)]))
    return Rolled(cart=cylinder(c, uv), sublattice=sublattice, uv=uv,
                  bonds=np.array(bonds, int),
                  images=np.array(images, int))


def cylinder(chirality: Chirality, uv: np.ndarray) -> np.ndarray:
    """Sheet positions (u, v) to Cartesian ones on the tube, its axis
    along z through the origin."""
    radius = chirality.diameter / 2
    phi = 2 * math.pi * uv[:, 0]
    return np.column_stack([radius * np.cos(phi), radius * np.sin(phi),
                            uv[:, 1] * chirality.t_length])


def shortest_bond(chirality: Chirality, rolled: Rolled) -> float:
    """The shortest chord a bond became, rolled."""
    return float(_bond_lengths(chirality, rolled).min())


def closest_contact(chirality: Chirality, rolled: Rolled) -> float:
    """The closest two atoms come that are not bonded, the periods
    either side included."""
    # The answer is at most a, a second neighbour that rolling only
    # shortens, so a reach just over a finds it without the 4x pairs
    # that 2a would.
    distance, _i, _j = _unbonded(chirality, rolled,
                                 1.1 * chirality.a)
    return float(distance.min()) if len(distance) else math.inf


def bonding_clash(chirality: Chirality, rolled: Rolled,
                  cutoffs: np.ndarray):
    """The unbonded pair furthest inside its bonding distance, as
    ``(distance, cutoff)``, or None when every pair is outside it.

    ``cutoffs[s, t]`` is the bonding distance between a site of
    sublattice ``s`` and one of ``t``.
    """
    reach = float(np.max(cutoffs))
    distance, i, j = _unbonded(chirality, rolled, reach)
    if not len(distance):
        return None
    limit = cutoffs[rolled.sublattice[i], rolled.sublattice[j]]
    inside = distance < limit
    if not inside.any():
        return None
    worst = int(np.argmin(np.where(inside, distance - limit, np.inf)))
    return float(distance[worst]), float(limit[worst])


def _bond_lengths(chirality: Chirality, rolled: Rolled) -> np.ndarray:
    shift = np.outer(rolled.images, [0.0, 0.0, chirality.t_length])
    vectors = rolled.cart[rolled.bonds[:, 1]] + shift \
        - rolled.cart[rolled.bonds[:, 0]]
    return np.linalg.norm(vectors, axis=1)


def _unbonded(chirality: Chirality, rolled: Rolled, reach: float):
    """Every pair within ``reach`` that is not a bond, one atom in the
    period and the other in it or a period either side: the distances
    and the two atoms' indices in the period."""
    from scipy.spatial import cKDTree

    n = len(rolled.cart)
    period = chirality.t_length
    copies = max(1, math.ceil(reach / period))
    shifts = range(-copies, copies + 1)
    stacked = np.vstack([rolled.cart + [0.0, 0.0, s * period]
                         for s in shifts])
    home = copies * n
    tree = cKDTree(stacked)
    pairs = tree.query_ball_point(rolled.cart, reach)
    bonded = set()
    for (a, b), image in zip(rolled.bonds, rolled.images, strict=True):
        bonded.add((int(a), int(b), int(image)))
        bonded.add((int(b), int(a), -int(image)))
    distances, first, second = [], [], []
    for a, found in enumerate(pairs):
        for index in found:
            b, image = index % n, index // n - copies
            if index == home + a or (a, b, image) in bonded:
                continue
            distances.append(np.linalg.norm(stacked[index]
                                            - rolled.cart[a]))
            first.append(a)
            second.append(b)
    return (np.array(distances), np.array(first, int),
            np.array(second, int))


def _wrap(uv: np.ndarray) -> np.ndarray:
    wrapped = np.mod(uv + _EPS, 1.0) - _EPS
    wrapped[np.abs(wrapped) < _EPS] = 0.0
    return wrapped


def _key(uv, grid: int) -> tuple[int, int]:
    """A site's place in the period on its exact grid, so that two
    routes to the same site agree.

    Every A and B site's u and v is a multiple of 1/``grid``, with
    ``grid`` = 6(n^2 + nm + m^2): u = (i(2n+m) + j(n+2m)) / 2L and v
    = d_R^2 (i(2t1+t2) + j(t1+2t2)) / 6L for L = n^2 + nm + m^2, and
    B's third of a cell adds integers to both numerators.  A decimal
    grid instead puts some sites exactly half-way between two keys,
    (64,0)'s odd multiples of 1/128 among them.
    """
    return tuple(int(round(x * grid)) % grid for x in uv)
