"""
xtal.polymer.stats
==================
What a packed model is, in the numbers a person judges it by.

**Chain shape** is the mean-square end-to-end distance, the radius of
gyration and the characteristic ratio ``C_n = <R^2(n)> / (n l^2)``
over ``n`` backbone bonds of mean length ``l``.  ``C_n`` is averaged
over every segment of ``n`` bonds inside every chain, at ``n`` half a
chain's backbone: ten end-to-end distances carry a quarter of their
mean as noise, and the same polyethylene came out 3.7 and 6.2 by them
with nothing changed but the seed.  ``C_n`` is set
beside the freely rotating chain's at the same bond angle, which is
what a chain with no preference among its torsions would give: 2.0 at
the tetrahedral angle, against about 7 for a polyethylene melt.  A
ladder's backbone does not run unit to unit through one bond, so it
gets R and Rg and no ``C_n``.

**A ring speared by a bond** is a knot no relaxation undoes: two
chains, or one chain twice, interlocked through a phenyl.  Growth
cannot make one -- a trial that puts a bond through a ring puts its
atoms inside it -- but compression and the push-off can, so it is
counted, and the report says so when there are any.

Everything is read off unwrapped Cartesian positions: a chain as
grown is continuous, whichever periodic image its atoms are in.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from xtal.core import elements as table

AVOGADRO = 0.602214076          # g/cm3 per (g/mol)/A3
#: The largest ring looked through for a spearing bond.
RING = 7


@dataclass(frozen=True)
class Shape:
    """The chains' statistics.  ``c_n`` and ``c_free`` are ``None``
    for a ladder."""

    r2: float                   # <R^2>, A^2
    rg: float                   # root-mean-square Rg, A
    ends: tuple                 # each chain's R, A
    bonds: int                  # the n of c_n, backbone bonds
    c_n: float | None
    c_free: float | None


def density(elements, volume: float) -> float:
    """g/cm3 of ``elements`` in ``volume`` A3."""
    mass = sum(table.element(e).mass for e in elements)
    return mass / (volume * AVOGADRO)


def backbone(chain) -> list[int]:
    """Atom indices, into ``chain.atoms()``, of the chain's backbone
    from end to end -- empty for a ladder."""
    if not chain.units or chain.units[0].monomer.is_ladder:
        return []
    out = []
    start = 0
    for unit in chain.units:
        body = unit.monomer.body
        out.extend(start + body.index(a) for a in unit.monomer.backbone)
        start += len(body)
    return out


def shape(chains, cart_of) -> Shape:
    """Statistics over ``chains``, with ``cart_of(k)`` the positions of
    chain ``k``'s atoms in :meth:`~xtal.polymer.chain.Chain.atoms`
    order."""
    r2, rg2, counts, lengths, cosines, paths = [], [], [], [], [], []
    for k, chain in enumerate(chains):
        cart = cart_of(k)
        centre = cart.mean(axis=0)
        rg2.append(float(np.mean(np.sum((cart - centre) ** 2, axis=1))))
        path = backbone(chain)
        if len(path) < 3:
            first = len(chain.units[0].monomer.body)
            last = len(chain.units[-1].monomer.body)
            stop = sum(len(u.monomer.body) for u in chain.units)
            ends = (cart[:first].mean(axis=0),
                    cart[stop - last:stop].mean(axis=0))
            r2.append(float(np.sum((ends[1] - ends[0]) ** 2)))
            continue
        points = cart[path]
        paths.append(points)
        r2.append(float(np.sum((points[-1] - points[0]) ** 2)))
        steps = np.diff(points, axis=0)
        lengths.extend(np.sum(steps ** 2, axis=1))
        unit = steps / np.linalg.norm(steps, axis=1)[:, None]
        cosines.extend(np.sum(unit[1:] * unit[:-1], axis=1))
        counts.append(len(steps))
    mean_r2 = float(np.mean(r2))
    ends = tuple(float(np.sqrt(v)) for v in r2)
    rg = float(np.sqrt(np.mean(rg2)))
    if not counts:
        return Shape(mean_r2, rg, ends, 0, None, None)
    n = max(1, min(counts) // 2)
    inside = [np.sum((p[n:] - p[:-n]) ** 2, axis=1) for p in paths]
    c_n = float(np.mean(np.concatenate(inside))) / (
        n * float(np.mean(lengths)))
    # The freely rotating chain (Flory): bonds at a fixed angle, every
    # torsion equally likely.  ``c`` is the cosine between successive
    # bond vectors, minus the cosine of the bond angle.
    c = float(np.mean(cosines))
    free = ((1 + c) / (1 - c)
            - 2 * c * (1 - c ** n) / (n * (1 - c) ** 2))
    return Shape(mean_r2, rg, ends, n, c_n, free)


def rings(monomer) -> list[tuple[int, ...]]:
    """The monomer's rings of :data:`RING` atoms or fewer, as indices
    into its body, each once."""
    body = list(monomer.body)
    row = {a: k for k, a in enumerate(body)}
    around: dict[int, list[int]] = {k: [] for k in range(len(body))}
    for i, j, _ in monomer.bonds:
        if i in row and j in row:
            around[row[i]].append(row[j])
            around[row[j]].append(row[i])
    found, seen = [], set()
    for start in range(len(body)):
        stack = [[start]]
        while stack:
            path = stack.pop()
            if len(path) > RING:
                continue
            for nxt in around[path[-1]]:
                if nxt == start and len(path) >= 3:
                    key = frozenset(path)
                    if key not in seen:
                        seen.add(key)
                        found.append(tuple(path))
                elif nxt > start and nxt not in path:
                    stack.append([*path, nxt])
    # Only the smallest set: a naphthalene's ten-ring is no ring a bond
    # could pass through that the two six-rings do not already cover.
    return [r for r in found
            if not any(set(o) < set(r) for o in found)]


def speared(cart, bonds, ring_atoms, box, periodic) -> int:
    """How many (ring, bond) pairs have the bond passing through the
    ring's face.  ``ring_atoms`` are tuples of atom indices."""
    if not ring_atoms or not len(bonds):
        return 0
    cart = np.asarray(cart, dtype=float)
    box = np.asarray(box, dtype=float)
    periodic = np.asarray(periodic, dtype=bool)

    def wrap(d):
        d = np.array(d, dtype=float)
        for axis in np.nonzero(periodic)[0]:
            d[..., axis] -= box[axis] * np.round(d[..., axis] / box[axis])
        return d

    pairs = np.array([(i, j) for i, j, *_ in bonds], dtype=np.int64)
    middles = cart[pairs[:, 0]] + 0.5 * wrap(cart[pairs[:, 1]]
                                             - cart[pairs[:, 0]])
    size = np.where(periodic, box, 1e6)
    tree = cKDTree(np.where(periodic, np.mod(middles, box),
                            middles + 5e5), boxsize=size)
    count = 0
    for ring in ring_atoms:
        ring = list(ring)
        points = cart[ring[0]] + wrap(cart[ring] - cart[ring[0]])
        centre = points.mean(axis=0)
        local = points - centre
        _, _, vt = np.linalg.svd(local)
        normal = vt[2]
        reach = float(np.linalg.norm(local, axis=1).max())
        probe = np.where(periodic, np.mod(centre, box), centre + 5e5)
        members = set(ring)
        for b in tree.query_ball_point(probe, reach + 1.0):
            i, j = pairs[b]
            if i in members or j in members:
                continue
            a = centre + wrap(cart[i] - centre)
            e = a + wrap(cart[j] - cart[i])
            da, de = (a - centre) @ normal, (e - centre) @ normal
            if da * de >= 0.0:
                continue
            hit = a + (e - a) * (da / (da - de)) - centre
            if _inside(hit, local, normal):
                count += 1
    return count


def _inside(point, polygon, normal) -> bool:
    """Whether ``point``, in the ring's plane, is inside the ring
    polygon -- the winding of the polygon about it."""
    u = polygon[0] - (polygon[0] @ normal) * normal
    u = u / np.linalg.norm(u)
    v = np.cross(normal, u)
    xy = np.stack([polygon @ u, polygon @ v], axis=1)
    p = np.array([point @ u, point @ v])
    angles = np.arctan2(xy[:, 1] - p[1], xy[:, 0] - p[0])
    turn = np.diff(np.append(angles, angles[0]))
    turn = (turn + np.pi) % (2 * np.pi) - np.pi
    return abs(turn.sum()) > np.pi
