"""
xtal.fullerene.spiral
=====================
A fullerene as its face spiral, after Fowler and Manolopoulos: the
cage's faces peeled off in one continuous spiral, so that the whole
graph is written as the twelve places the pentagons fall in it.
C60-Ih is ``1 7 9 11 13 15 18 20 22 24 26 32`` of its 32 faces.

The spiral is wound up into the **dual** -- one vertex per face, an
edge where two faces share a bond -- which for a fullerene is a
triangulation of the sphere; the cage's atoms are its triangles and
its bonds the edges two triangles share.  The dual is kept as a
rotation system (each face's neighbours in a consistent cyclic order)
because a spiral read back off the cage needs to know which way round
it is going.

**Canonical** is the Atlas's: of every spiral the cage has -- one for
each starting face, second face and sense -- the one whose pentagons
come earliest.  The starts that give that same spiral are the cage's
symmetries, reflections included, so their count is the order of its
point group: 120 for C60-Ih.  Every fullerene below C380 has a spiral
(Manolopoulos and Fowler 1993); a typed one that does not close is
refused, saying at which face it failed.
"""

from __future__ import annotations

from collections import deque

__all__ = ["FullereneError", "faces", "check_size", "wind",
           "spiral_from", "canonical", "cage", "rings",
           "pentagons_of"]


class FullereneError(ValueError):
    """A cage that cannot be built, said in one sentence."""


def faces(n: int) -> int:
    """How many faces a cage of ``n`` atoms has: Euler's formula with
    every atom three-coordinate, twelve of them pentagons."""
    return n // 2 + 2


def check_size(n: int) -> None:
    """Refuse an atom count no fullerene has: odd, under 20, or 22."""
    if n < 20 or n % 2 or n == 22:
        raise FullereneError(
            f"no fullerene has {n} atoms: a cage needs an even number "
            f"of at least 20, and 22 has none")


def pentagons_of(n: int, pentagons) -> list[int]:
    """The face sizes a spiral of ``n`` atoms with its pentagons at
    ``pentagons`` (counted from 1) has, or a refusal naming the
    problem."""
    check_size(n)
    count = faces(n)
    places = sorted(int(p) for p in pentagons)
    if len(places) != 12 or len(set(places)) != 12:
        raise FullereneError(
            f"a spiral names twelve different pentagons; "
            f"{len(set(places))} were given")
    if places[0] < 1 or places[-1] > count:
        raise FullereneError(
            f"C{n} has {count} faces, so a pentagon must be face 1 to "
            f"{count}")
    sizes = [6] * count
    for place in places:
        sizes[place - 1] = 5
    return sizes


def wind(n: int, pentagons) -> list[list[int]]:
    """The dual of the cage the spiral describes, as a rotation
    system: ``rotation[f]`` is face ``f``'s neighbours in cyclic
    order, the same sense round every face."""
    sizes = pentagons_of(n, pentagons)
    return _orient(_wind(sizes))


def _wind(sizes) -> list[set]:
    """Faces joined in spiral order: each new face to the newest and
    the oldest face still open, and on round the open boundary while
    the faces it meets fill up.  The last face closes the hole."""
    count = len(sizes)
    adjacent = [set() for _ in range(count)]
    room = list(sizes)

    def join(i, j, face):
        if j in adjacent[i]:
            raise FullereneError(f"the spiral does not close: face "
                                 f"{face + 1} meets a face twice")
        adjacent[i].add(j)
        adjacent[j].add(i)
        room[i] -= 1
        room[j] -= 1

    join(0, 1, 1)
    boundary = deque([0, 1])
    for face in range(2, count - 1):
        join(face, boundary[-1], face)
        join(face, boundary[0], face)
        while room[boundary[0]] == 0:
            boundary.popleft()
            if not boundary:
                break
            join(face, boundary[0], face)
        while boundary and room[boundary[-1]] == 0:
            boundary.pop()
            if not boundary:
                break
            join(face, boundary[-1], face)
        if room[face] < 0 or not boundary \
                or any(room[f] < 0 for f in boundary):
            raise FullereneError(f"the spiral does not close: face "
                                 f"{face + 1} has more neighbours "
                                 f"than sides")
        boundary.append(face)
    last = count - 1
    if len(boundary) != sizes[last]:
        raise FullereneError("the spiral does not close: the last "
                             "face does not fit the hole left for it")
    for face in boundary:
        join(last, face, last)
    if any(room):
        raise FullereneError("the spiral does not close")
    return adjacent


def _orient(adjacent) -> list[list[int]]:
    """Each face's neighbours as a cycle -- in a fullerene's dual a
    face's neighbours ring it, each meeting the next -- turned so the
    sense agrees across every edge: if ``w`` follows ``v`` round
    ``u``, then ``u`` follows ``w`` round ``v``."""
    count = len(adjacent)
    rotation = [None] * count
    for face, around in enumerate(adjacent):
        ring = [min(around)]
        while len(ring) < len(around):
            step = [g for g in adjacent[ring[-1]] & around
                    if g not in ring]
            if len(ring) > 1:
                step = [g for g in step if g != ring[-2]]
            if not step:
                raise FullereneError(f"face {face + 1} is not ringed "
                                     f"by its neighbours")
            ring.append(min(step))
        if ring[0] not in adjacent[ring[-1]]:
            raise FullereneError(f"face {face + 1} is not ringed by "
                                 f"its neighbours")
        rotation[face] = ring
    done = [False] * count
    done[0] = True
    queue = deque([0])
    while queue:
        u = queue.popleft()
        for v in rotation[u]:
            if done[v]:
                continue
            if _after(rotation, v, _after(rotation, u, v)) != u:
                rotation[v].reverse()
            done[v] = True
            queue.append(v)
    for u in range(count):
        for v in rotation[u]:
            if _after(rotation, v, _after(rotation, u, v)) != u:
                raise FullereneError("the cage is not orientable")
    return rotation


def _after(rotation, face, neighbour, sense=1):
    around = rotation[face]
    return around[(around.index(neighbour) + sense) % len(around)]


def spiral_from(rotation, first, second, sense=1) -> list[int] | None:
    """The faces in spiral order from ``first`` then ``second``, going
    round ``sense`` (1 or -1), or None where no spiral starts there.
    Each next face follows the newest one round the oldest face still
    open."""
    count = len(rotation)
    order = [first, second]
    seen = {first, second}
    oldest = 0
    while len(order) < count:
        while all(f in seen for f in rotation[order[oldest]]):
            oldest += 1
        hub, newest = order[oldest], order[-1]
        if newest not in rotation[hub]:
            return None
        face = _after(rotation, hub, newest, sense)
        if face in seen:
            return None
        order.append(face)
        seen.add(face)
    return order


def canonical(rotation) -> tuple[tuple[int, ...], int]:
    """The cage's canonical spiral -- its pentagons, counted from 1,
    as early as any start puts them -- and how many starts give it,
    which is the order of the cage's point group."""
    best, count = None, 0
    for first, around in enumerate(rotation):
        for second in around:
            for sense in (1, -1):
                order = spiral_from(rotation, first, second, sense)
                if order is None:
                    continue
                key = tuple(i + 1 for i, f in enumerate(order)
                            if len(rotation[f]) == 5)
                if best is None or key < best:
                    best, count = key, 1
                elif key == best:
                    count += 1
    if best is None:
        raise FullereneError("the cage has no spiral")
    return best, count


def cage(rotation):
    """The atoms and bonds: one atom per triangle of the dual, named
    by its three faces, and a bond across each edge of the dual."""
    triangles = {}
    for u, around in enumerate(rotation):
        for i, v in enumerate(around):
            key = tuple(sorted((u, v, around[(i + 1) % len(around)])))
            triangles.setdefault(key, len(triangles))
    atoms = list(triangles)
    bonds = set()
    for u, around in enumerate(rotation):
        for i, v in enumerate(around):
            if v < u:
                continue
            w = around[(i + 1) % len(around)]
            x = around[i - 1]
            a = triangles[tuple(sorted((u, v, w)))]
            b = triangles[tuple(sorted((u, v, x)))]
            bonds.add((min(a, b), max(a, b)))
    return atoms, sorted(bonds)


def rings(rotation, atoms) -> list[list[int]]:
    """Each face's atoms in order round it: the cage's rings, five or
    six atoms each."""
    index = {key: k for k, key in enumerate(atoms)}
    out = []
    for u, around in enumerate(rotation):
        out.append([index[tuple(sorted(
            (u, v, around[(i + 1) % len(around)])))]
            for i, v in enumerate(around)])
    return out
