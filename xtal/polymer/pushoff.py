"""
xtal.polymer.pushoff
====================
The overlaps a packed box was grown with, pushed apart.

**Growing at a melt's density needs a soft core.**  With explicit
hydrogens a chain step has its tail carbon, two hydrogens and the next
head carbon to find room for at once, and at 0.85 g/cm3 a hard core of
even 0.55 of the van der Waals sum leaves none of twelve trials clear
often enough that polyethylene jammed with a quarter of it unplaced.
So :mod:`xtal.polymer.pack` refuses only atoms nearly on top of each
other and weights the rest, and this takes out what is left -- the
*push-off* of Auhl, Everaers, Grest, Kremer and Plimpton (2003), and
what Amorphous Cell does with its scaled radii.

**It moves positions and nothing else.**  Every stated bond and every
angle is held at the length it was built with, as a spring on the 1-2
and 1-3 distances; nothing is perceived, nothing is bonded, the cell is
fixed.  Between atoms three bonds apart or more, a repulsion
``(sigma - d)^2`` acts below ``sigma``, a fraction of the two van der
Waals radii that is raised from where growth left it to
:data:`TARGET` over the first half of the steps, so the chains slide
past each other rather than being kicked.  It is not a force field and
gives no energy anybody should quote: it is there so that the first
force-field step on the model is not an explosion.

**A bond through a ring cannot be pushed out of it.**  A chain grown
through a phenyl ring is a topological knot that no smooth path
undoes; :func:`push_off` reports the closest contact it could not
clear, and the packer says it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from xtal.core import elements as table

#: The fraction of the van der Waals sum the repulsion starts at:
#: 3.23 A for two carbons, 2.28 for two hydrogens.  Contacts come to
#: rest short of it, where the bonded springs push back: polyethylene
#: at 0.85 g/cm3 settles with its closest pair at 0.89 (two hydrogens
#: 2.1 A apart), a melt's contact.  Aimed at 0.85 it settled at 0.72
#: with two thousand pairs sharing the strain, which looked like a
#: jam and was a repulsion too soft for the springs.
TARGET = 0.95
#: Where the ramp starts, near the fraction growth refused below.
START = 0.5
#: Spring constants, in the one arbitrary unit the push-off uses: the
#: bonded springs stiff enough that a bond or angle gives a few
#: hundredths of an A where the repulsion pushes on it.
K_BOND = 50.0
K_ANGLE = 20.0
K_TORSION = 5.0
K_CONTACT = 20.0
#: FIRE's step and the most an atom moves in one, in A.
DT = 0.05
MAX_MOVE = 0.1
#: How far an atom may move before the pair list is rebuilt, A.
SKIN = 1.0
#: How much a compression cycle shrinks the box by, linearly, and how
#: long it relaxes before the next.
SQUEEZE = 0.03
CYCLE_STEPS = 60


@dataclass(frozen=True)
class Result:
    """Where the atoms went, and how close the closest pair is left:
    as a fraction of the van der Waals sum, and in A."""

    cart: np.ndarray
    closest: float
    closest_distance: float
    steps: int


def _topology(n: int, bonds):
    """``(1-2 pairs, 1-3 pairs, 1-4 pairs, keys of every pair within
    three bonds)``, ``i < j``."""
    around: list[set] = [set() for _ in range(n)]
    for i, j, *_ in bonds:
        around[i].add(j)
        around[j].add(i)
    one_two = {(min(i, j), max(i, j)) for i, j, *_ in bonds}
    one_three = set()
    for b in range(n):
        ends = sorted(around[b])
        for x in range(len(ends)):
            for y in range(x + 1, len(ends)):
                one_three.add((ends[x], ends[y]))
    one_three -= one_two
    one_four = set()
    for i, j in one_two:
        for a in around[i]:
            for d in around[j]:
                if a != j and d != i and a != d:
                    one_four.add((min(a, d), max(a, d)))
    one_four -= one_two | one_three
    near = {i * n + j for i, j in one_two | one_three | one_four}
    return (*(np.array(sorted(p), dtype=np.int64).reshape(-1, 2)
              for p in (one_two, one_three, one_four)), near)


class _Space:
    """Minimum-image differences in a box periodic where it says."""

    def __init__(self, box, periodic):
        self.box = np.asarray(box, dtype=float)
        self.periodic = np.asarray(periodic, dtype=bool)

    def delta(self, a, b) -> np.ndarray:
        d = b - a
        for axis in np.nonzero(self.periodic)[0]:
            length = self.box[axis]
            d[:, axis] -= length * np.round(d[:, axis] / length)
        return d

    def tree(self, cart) -> cKDTree:
        # An axis that is not periodic is given a box far wider than
        # anything in it, which cKDTree reads as no wrap at all.
        size = np.where(self.periodic, self.box, 1e6)
        wrapped = np.where(self.periodic, np.mod(cart, self.box),
                           cart + 5e5)
        return cKDTree(wrapped, boxsize=size)


def contacts(elements, cart, bonds, box, periodic=(True, True, True)):
    """``(fraction, distance)`` of the closest pair three bonds apart
    or more: the distance over the two van der Waals radii's sum."""
    cart = np.asarray(cart, dtype=float)
    n = len(cart)
    *_, near = _topology(n, bonds)
    space = _Space(box, periodic)
    radii = np.array([table.vdw_radius(e) for e in elements])
    pairs = _pairs(space, cart, 2.0 * radii.max(), near, n)
    if not len(pairs):
        return 1.0, np.inf
    d = np.linalg.norm(space.delta(cart[pairs[:, 0]], cart[pairs[:, 1]]),
                       axis=1)
    frac = d / (radii[pairs[:, 0]] + radii[pairs[:, 1]])
    k = int(np.argmin(frac))
    return float(frac[k]), float(d[k])


def _pairs(space: _Space, cart, cutoff: float, near: set,
           n: int) -> np.ndarray:
    pairs = space.tree(cart).query_pairs(cutoff, output_type="ndarray")
    if not len(pairs):
        return pairs.reshape(0, 2)
    pairs = np.sort(pairs, axis=1)
    keys = pairs[:, 0] * n + pairs[:, 1]
    known = np.fromiter(near, dtype=np.int64, count=len(near))
    return pairs[~np.isin(keys, known)]


def _spring(space, cart, pairs, rest, k, force) -> None:
    if not len(pairs):
        return
    d = space.delta(cart[pairs[:, 0]], cart[pairs[:, 1]])
    r = np.linalg.norm(d, axis=1)
    pull = (2.0 * k * (r - rest) / np.maximum(r, 1e-9))[:, None] * d
    _gather(force, pairs, pull)


def _gather(force, pairs, pull) -> None:
    """``pull`` added to the first atom of each pair and taken from
    the second -- ``bincount``, a tenth of what ``np.add.at`` costs."""
    n = len(force)
    for axis in range(3):
        force[:, axis] += (np.bincount(pairs[:, 0], pull[:, axis], n)
                           - np.bincount(pairs[:, 1], pull[:, axis], n))


class _Model:
    """What the push-off holds fixed: the topology, the rest lengths
    of the springs, the radii.  Built once, so a compression's cycles
    do not rebuild it."""

    def __init__(self, elements, cart, bonds, box, periodic, walls):
        cart = np.asarray(cart, dtype=float)
        self.n = len(cart)
        self.space = _Space(box, periodic)
        self.walls = walls
        self.radii = np.array([table.vdw_radius(e) for e in elements])
        (self.one_two, self.one_three, self.one_four,
         self.near) = _topology(self.n, bonds)
        self.rest_two = self._lengths(cart, self.one_two)
        self.rest_three = self._lengths(cart, self.one_three)
        self.rest_four = self._lengths(cart, self.one_four)

    def _lengths(self, cart, pairs) -> np.ndarray:
        return np.linalg.norm(self.space.delta(cart[pairs[:, 0]],
                                               cart[pairs[:, 1]]), axis=1)

    def relax(self, cart, steps: int, start: float, target: float,
              check) -> tuple[np.ndarray, int]:
        """FIRE over the springs and the repulsion, its ``sigma``
        raised from ``start`` to ``target`` over the first half."""
        cart = np.array(cart, dtype=float)
        space, radii = self.space, self.radii
        cutoff = 2.0 * target * radii.max() + SKIN
        pairs = _pairs(space, cart, cutoff, self.near, self.n)
        built_at = cart.copy()
        velocity = np.zeros_like(cart)
        dt, alpha, calm = DT, 0.1, 0
        ramp = max(1, steps // 2)
        done = 0
        for step in range(steps):
            done = step + 1
            if step % 20 == 0:
                check()
            fraction = start + (target - start) * min(1.0, step / ramp)
            if np.abs(space.delta(built_at, cart)).max() > 0.5 * SKIN:
                pairs = _pairs(space, cart, cutoff, self.near, self.n)
                built_at = cart.copy()
            force = np.zeros_like(cart)
            _spring(space, cart, self.one_two, self.rest_two, K_BOND,
                    force)
            _spring(space, cart, self.one_three, self.rest_three,
                    K_ANGLE, force)
            _spring(space, cart, self.one_four, self.rest_four,
                    K_TORSION, force)
            clash = 0.0
            if len(pairs):
                d = space.delta(cart[pairs[:, 0]], cart[pairs[:, 1]])
                r = np.linalg.norm(d, axis=1)
                sigma = fraction * (radii[pairs[:, 0]]
                                    + radii[pairs[:, 1]])
                inside = r < sigma
                if inside.any():
                    p, dd, rr, ss = (pairs[inside], d[inside],
                                     r[inside], sigma[inside])
                    clash = float((ss - rr).max())
                    push = (2.0 * K_CONTACT * (ss - rr) / np.maximum(
                        rr, 1e-9))[:, None] * dd
                    _gather(force, p, -push)
            if self.walls is not None:
                low, high = self.walls
                z = cart[:, 2]
                force[:, 2] += 2.0 * K_CONTACT * (
                    np.clip(low - z, 0, None) - np.clip(z - high, 0, None))
            if step > ramp and clash < 1e-3:
                break
            # FIRE (Bitzek et al. 2006): run downhill, and stop dead
            # whenever the velocity turns against the force.
            power = float(np.sum(force * velocity))
            f_norm = np.linalg.norm(force)
            v_norm = np.linalg.norm(velocity)
            if power > 0.0:
                velocity = ((1.0 - alpha) * velocity + alpha * force
                            * v_norm / max(f_norm, 1e-12))
                calm += 1
                if calm > 5:
                    dt = min(dt * 1.1, 4.0 * DT)
                    alpha *= 0.99
            else:
                velocity[:] = 0.0
                dt, alpha, calm = dt * 0.5, 0.1, 0
            velocity += dt * force
            move = dt * velocity
            longest = np.linalg.norm(move, axis=1).max()
            if longest > MAX_MOVE:
                move *= MAX_MOVE / longest
            cart += move
        return cart, done

    def result(self, elements, bonds, cart, steps) -> Result:
        closest, distance = contacts(elements, cart, bonds,
                                     self.space.box,
                                     self.space.periodic)
        return Result(cart, closest, distance, steps)


def push_off(elements, cart, bonds, box, periodic=(True, True, True),
             walls=None, steps: int = 600, target: float = TARGET,
             check=None) -> Result:
    """Atoms moved until no two three bonds apart or more are closer
    than ``target`` of their van der Waals sum, or ``steps`` run out.

    ``walls`` is ``(low, high)`` along *c* for a membrane: an atom
    outside is pushed back.  ``check`` is called every few steps and
    stops the push-off by raising.
    """
    model = _Model(elements, cart, bonds, box, periodic, walls)
    cart, done = model.relax(cart, steps, START, target,
                             check or (lambda: None))
    return model.result(elements, bonds, cart, done)


def compress(elements, cart, bonds, groups, box, to_box,
             periodic=(True, True, True), walls=None, steps: int = 600,
             check=None, say=None) -> Result:
    """A box grown loose, squeezed to ``to_box`` and pushed off.

    Each cycle shrinks the box by at most :data:`SQUEEZE` along every
    axis that shrinks, carries each group -- a chain's unit, which is
    rigid as built -- with its centroid, and relaxes for
    :data:`CYCLE_STEPS`; only the joints between units stretch, and the
    springs take that back.  Scaling the atoms instead would compress
    every bond in the box by the same few percent each cycle.  Then
    ``steps`` of :func:`push_off` at the final box.
    """
    check = check or (lambda: None)
    say = say or (lambda _text: None)
    cart = np.array(cart, dtype=float)
    groups = np.asarray(groups, dtype=np.int64)
    box = np.asarray(box, dtype=float)
    to_box = np.asarray(to_box, dtype=float)
    model = _Model(elements, cart, bonds, box, periodic, walls)
    count = np.bincount(groups).astype(float)
    total = 0
    cycles = 0
    while np.any(box > to_box * (1.0 + 1e-9)):
        check()
        new = np.maximum(box * (1.0 - SQUEEZE), to_box)
        factor = new / box
        centroid = np.stack([np.bincount(groups, cart[:, axis])
                             for axis in range(3)], axis=1)
        centroid /= count[:, None]
        cart += (centroid * (factor - 1.0))[groups]
        box = new
        model.space = _Space(box, periodic)
        cart, done = model.relax(cart, CYCLE_STEPS, TARGET, TARGET,
                                 check)
        total += done
        cycles += 1
        if cycles % 5 == 0:
            say(f"compressed to {' x '.join(f'{v:.1f}' for v in box)} A")
    cart, done = model.relax(cart, steps, START, TARGET, check)
    return model.result(elements, bonds, cart, total + done)
