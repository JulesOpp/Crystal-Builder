"""
xtal.polymer.chain
==================
Monomers joined into a chain, one joint at a time.

**A joint is built from bond lengths, never by making two ``X``
coincide.**  The ``X`` of a connection point is 0.75 A out from its
members (:data:`xtal.mof.block.CONNECTION_DISTANCE`), which is a
convention about direction and says nothing about how long the bond it
stands for is.  So the next unit's head member goes the sum of the two
covalent radii out from the tail member, along the tail's axis, with
the new unit's head axis pointing back down it; both ``X`` are then
dropped and the bond between the members is stated.

What is left free is one number.  At a **single** joint it is the
torsion about the new bond, which is what a chain's conformation is
made of and what :mod:`xtal.polymer.pack` samples.  At a **ladder**
joint there is no torsion -- two bonds hold the two units in one plane
-- and the freedom is which tail member meets which head member: the
two :func:`xtal.mof.attach.pairing` choices, the *flip* that is cis
or trans in PIM-1.

The ends of a finished chain are capped with hydrogen: each member of
the first head and the last tail gets one where its ``X`` pointed.  So
no ``X`` survives into a built model, which is the invariant every
engine's door relies on.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from xtal.core import elements
from xtal.polymer.monomer import Monomer

#: The order a joint bond is stated with.  A ladder's two bonds and a
#: chain's one are single in every library monomer; a conjugated joint
#: is a monomer this does not yet describe.
JOINT_ORDER = 1.0


#: Cordero's carbon by hybridisation, by how many neighbours the atom
#: has with its connection point counted.  The element table holds one
#: radius per element, 0.73 for carbon, and a backbone joint of two
#: sp3 carbons came out 1.46 A against the 1.51 inside each unit.
CARBON = {4: 0.76, 3: 0.73, 2: 0.69}


def radius(monomer: Monomer, atom: int) -> float:
    """The covalent radius of one atom of a monomer, Cordero 2008."""
    symbol = monomer.elements[atom]
    if symbol == "C":
        neighbours = sum(1 for i, j, _ in monomer.bonds if atom in (i, j))
        return CARBON.get(neighbours, elements.covalent_radius("C"))
    return elements.covalent_radius(symbol)


def bond_length(a: Monomer, i: int, b: Monomer, j: int) -> float:
    """The joint bond from atom ``i`` of ``a`` to atom ``j`` of ``b``:
    the sum of their covalent radii."""
    return radius(a, i) + radius(b, j)


def dihedral(a, b, c, d) -> float:
    """The torsion a-b-c-d in degrees, (-180, 180]."""
    b0 = np.asarray(a, float) - np.asarray(b, float)
    b1 = np.asarray(c, float) - np.asarray(b, float)
    b2 = np.asarray(d, float) - np.asarray(c, float)
    b1 = b1 / np.linalg.norm(b1)
    v = b0 - (b0 @ b1) * b1
    w = b2 - (b2 @ b1) * b1
    x = v @ w
    y = np.cross(b1, v) @ w
    return float(np.degrees(np.arctan2(y, x)))


@dataclass(frozen=True)
class Unit:
    """A monomer placed: its atoms, ``X`` included, where they are."""

    monomer: Monomer
    cart: np.ndarray = field(repr=False)

    def members(self, end: str) -> np.ndarray:
        m = self.monomer
        chosen = m.head_members if end == "head" else m.tail_members
        return self.cart[list(chosen)]

    def point(self, end: str) -> np.ndarray:
        m = self.monomer
        return self.cart[m.head if end == "head" else m.tail]

    def axis(self, end: str) -> np.ndarray:
        """Unit vector from the end's members out to its point."""
        out = self.point(end) - self.members(end).mean(axis=0)
        return out / np.linalg.norm(out)


@dataclass(frozen=True)
class Joint:
    """The bonds that join unit ``k`` to unit ``k + 1``: pairs of
    (tail member of ``k``, head member of ``k + 1``), monomer indices."""

    pairs: tuple[tuple[int, int], ...]


def first(monomer: Monomer, rotation=None, origin=None) -> Unit:
    """The first unit of a chain, its body centred on ``origin``."""
    cart = np.array(monomer.cart, dtype=float)
    if rotation is not None:
        cart = cart @ np.asarray(rotation, float).T
    if origin is not None:
        cart = cart + np.asarray(origin, float)
    return Unit(monomer, cart)


def _rotation(source, target) -> np.ndarray:
    """The smallest rotation taking unit vector ``source`` to
    ``target``."""
    v = np.cross(source, target)
    c = float(source @ target)
    if c < -1.0 + 1e-12:
        # Opposite: half a turn about any perpendicular.
        perpendicular = np.cross(source, [1.0, 0.0, 0.0])
        if np.linalg.norm(perpendicular) < 1e-6:
            perpendicular = np.cross(source, [0.0, 1.0, 0.0])
        perpendicular /= np.linalg.norm(perpendicular)
        return 2.0 * np.outer(perpendicular, perpendicular) - np.eye(3)
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + k + k @ k / (1.0 + c)


def _about(axis, angle: float) -> np.ndarray:
    """Rotation by ``angle`` radians about unit ``axis``."""
    x, y, z = axis
    k = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    return np.eye(3) + np.sin(angle) * k + (1 - np.cos(angle)) * k @ k


def _kabsch(source, target):
    """``(rotation, shift)`` taking ``source`` onto ``target`` with the
    least squared error, a proper rotation."""
    a = source.mean(axis=0)
    b = target.mean(axis=0)
    h = (source - a).T @ (target - b)
    u, _, vt = np.linalg.svd(h)
    d = np.sign(np.linalg.det(vt.T @ u.T)) or 1.0
    rotation = vt.T @ np.diag([1.0, 1.0, d]) @ u.T
    return rotation, b - a @ rotation.T


def tail_rotation(unit: Unit) -> np.ndarray:
    """The rotation that took ``unit``'s monomer to where it is: its
    atoms fitted onto their placed positions."""
    rotation, _ = _kabsch(np.asarray(unit.monomer.cart, float),
                          np.asarray(unit.cart, float))
    return rotation


def place(tail: Unit, monomer: Monomer, twist: float = 0.0,
          flip: bool = False) -> tuple[Unit, Joint]:
    """``monomer`` joined to ``tail``'s tail.

    ``twist`` (radians) turns the new unit about the joint bond and
    means something only at a single joint; ``flip`` chooses the other
    pairing at a ladder joint and means nothing at a single one.
    """
    old = tail.monomer
    if not monomer.is_ladder:
        u = tail.axis("tail")
        anchor = tail.members("tail")[0]
        here = monomer.cart[monomer.head_members[0]]
        a = monomer.cart[monomer.head] - here
        a = a / np.linalg.norm(a)
        rotation = _about(u, twist) @ _rotation(a, -u)
        length = bond_length(old, old.tail_members[0], monomer,
                             monomer.head_members[0])
        cart = (monomer.cart - here) @ rotation.T + anchor + length * u
        joint = Joint(((old.tail_members[0], monomer.head_members[0]),))
        return Unit(monomer, cart), joint

    tm, hm = old.tail_members, monomer.head_members
    pairs = (((tm[0], hm[1]), (tm[1], hm[0])) if flip
             else ((tm[0], hm[0]), (tm[1], hm[1])))
    # Four points, fitted rigidly: each head member where its partner's
    # free valence points, and each tail member where the head
    # member's own free valence points from the other side.  Matching
    # flat frames instead could not describe a Troger's base, whose
    # joint is not planar: PIM-EA-TB came out 1.19 and 1.75 A.
    turned = tail_rotation(tail)
    source, target = [], []
    for t, h in pairs:
        length = bond_length(old, t, monomer, h)
        source.append(monomer.cart[h])
        target.append(tail.cart[t] + length * (
            turned @ old.free_direction(t)))
        source.append(monomer.cart[h] + length
                      * monomer.free_direction(h))
        target.append(tail.cart[t])
    rotation, shift = _kabsch(np.array(source), np.array(target))
    cart = monomer.cart @ rotation.T + shift
    return Unit(monomer, cart), Joint(pairs)


def ahead(unit: Unit, monomer: Monomer | None) -> np.ndarray:
    """Where the head members of ``monomer`` will be once it is joined
    to ``unit`` -- or, with no monomer, where the end's capping
    hydrogens go.  Fixed by ``unit`` alone: a torsion at the next
    joint turns everything of the next unit but these."""
    if monomer is None:
        return np.array([cart for _, cart in _caps(unit, "tail")])
    old = unit.monomer
    if not monomer.is_ladder:
        length = bond_length(old, old.tail_members[0], monomer,
                             monomer.head_members[0])
        return (unit.members("tail")[0]
                + length * unit.axis("tail"))[None, :]
    turned = tail_rotation(unit)
    return np.array([
        unit.cart[t] + bond_length(old, t, monomer, h)
        * (turned @ old.free_direction(t))
        for t, h in zip(old.tail_members, monomer.head_members,
                        strict=True)])


#: The staggered torsions a free backbone bond inside a unit is set
#: to: trans and the two gauche.
STAGGERED = (180.0, 60.0, -60.0)


def free_bonds(monomer: Monomer) -> list[int]:
    """Positions ``k`` along :attr:`Monomer.backbone` whose bond
    ``backbone[k] - backbone[k + 1]`` turns freely: single, in no
    ring, and between two atoms with no multiple bond, so an amide's or
    an ester's C(=O)-X stays planar where the embedding put it."""
    path = monomer.backbone
    if monomer.is_ladder or len(path) < 2:
        return []
    order = {}
    for i, j, o in monomer.bonds:
        order[(i, j)] = order[(j, i)] = o
    saturated = {a for a in path
                 if all(o <= 1.0 for (x, _y), o in order.items()
                        if x == a)}
    out = []
    for k in range(len(path) - 1):
        a, b = path[k], path[k + 1]
        if (order.get((a, b), 0.0) == 1.0 and a in saturated
                and b in saturated and not _in_ring(monomer, a, b)):
            out.append(k)
    return out


def _in_ring(monomer: Monomer, a: int, b: int) -> bool:
    """Whether bond a-b closes a cycle: ``b`` reachable from ``a``
    without it."""
    return a in _side(monomer, b, a)


def _side(monomer: Monomer, start: int, block: int) -> set[int]:
    """Atoms reachable from ``start`` without passing through
    ``block`` -- the head point and the tail point counted, since
    turning the tail side of a bond carries its ``X`` with it."""
    around: dict[int, list[int]] = {}
    for i, j, _ in monomer.bonds:
        around.setdefault(i, []).append(j)
        around.setdefault(j, []).append(i)
    seen = {start}
    queue = [start]
    while queue:
        atom = queue.pop()
        for other in around.get(atom, ()):
            if atom == start and other == block:
                continue
            if other not in seen:
                seen.add(other)
                queue.append(other)
    return seen


def rotamers(monomer: Monomer) -> list[tuple[Monomer, tuple]]:
    """Every staggered setting of the unit's free backbone bonds:
    ``(monomer, torsions)``, the torsions in degrees.

    The joint torsion alone is not enough.  A bond set trans inside
    the unit makes the joints either side of it parallel, so a
    polyethylene chain with every other torsion frozen at the
    embedding's trans drifted straight across the box whatever its
    joints did: C_n 91 against a melt's 7.
    """
    from dataclasses import replace

    path = monomer.backbone
    free = free_bonds(monomer)
    if not free:
        return [(monomer, ())]
    out = []
    for setting in np.array(np.meshgrid(*[STAGGERED] * len(free),
                                        indexing="ij")).reshape(
                                            len(free), -1).T:
        cart = np.array(monomer.cart, dtype=float)
        for k, angle in zip(free, setting, strict=True):
            a, b = path[k], path[k + 1]
            before = path[k - 1] if k > 0 else monomer.head
            after = path[k + 2] if k + 2 < len(path) else monomer.tail
            now = dihedral(cart[before], cart[a], cart[b], cart[after])
            axis = cart[b] - cart[a]
            axis /= np.linalg.norm(axis)
            turn = _about(axis, np.radians(angle - now))
            moving = sorted(_side(monomer, b, a))
            cart[moving] = (cart[moving] - cart[b]) @ turn.T + cart[b]
        body = list(monomer.body)
        cart -= cart[body].mean(axis=0)
        if out and not _roomy(monomer, cart):
            continue
        out.append((replace(monomer, cart=cart),
                    tuple(float(v) for v in setting)))
    return out


#: A rotamer whose own atoms four bonds apart or more come closer than
#: this fraction of their van der Waals sum is not offered: nothing
#: else would see it, since a unit's atoms are scored against the box
#: and never against each other.
ROOM = 0.6


def _roomy(monomer: Monomer, cart) -> bool:
    body = list(monomer.body)
    around: dict[int, set] = {i: set() for i in body}
    for i, j, _ in monomer.bonds:
        if i in around and j in around:
            around[i].add(j)
            around[j].add(i)
    radii = {i: elements.vdw_radius(monomer.elements[i]) for i in body}
    for i in body:
        near = {i} | around[i]
        for _ in range(2):
            near |= {k for n in near for k in around[n]}
        for j in body:
            if j > i and j not in near:
                d = float(np.linalg.norm(cart[i] - cart[j]))
                if d < ROOM * (radii[i] + radii[j]):
                    return False
    return True


def joint_torsion(tail: Unit, head: Unit) -> float:
    """The backbone torsion across a single joint, in degrees.

    Measured along each unit's own backbone, and where a backbone is
    one atom long, through the ``X`` that stands for the unit beyond.
    """
    before, after = tail.monomer.backbone, head.monomer.backbone
    a = (tail.cart[before[-2]] if len(before) > 1
         else tail.point("head"))
    d = (head.cart[after[1]] if len(after) > 1
         else head.point("tail"))
    return dihedral(a, tail.cart[before[-1]], head.cart[after[0]], d)


def place_at(tail: Unit, monomer: Monomer, torsion: float = 180.0,
             flip: bool = False) -> tuple[Unit, Joint]:
    """:func:`place`, with the backbone torsion across a single joint
    set to ``torsion`` degrees: 180 is trans."""
    unit, joint = place(tail, monomer, 0.0, flip)
    if monomer.is_ladder:
        return unit, joint
    turn = np.radians(torsion - joint_torsion(tail, unit))
    return place(tail, monomer, turn, flip)


@dataclass
class Chain:
    """Units in order, and the joints between them."""

    units: list[Unit] = field(default_factory=list)
    joints: list[Joint] = field(default_factory=list)

    @property
    def n_units(self) -> int:
        return len(self.units)

    def atoms(self, cap: bool = True):
        """``(elements, cart, bonds)`` for the whole chain: the ``X``
        gone, every joint bonded, and both ends capped with hydrogen
        unless ``cap`` is false."""
        symbols: list[str] = []
        positions: list[np.ndarray] = []
        bonds: list[tuple[int, int, float]] = []
        index: list[dict[int, int]] = []
        for unit in self.units:
            m = unit.monomer
            here = {}
            for i in m.body:
                here[i] = len(symbols)
                symbols.append(m.elements[i])
                positions.append(unit.cart[i])
            index.append(here)
            bonds.extend((here[i], here[j], o) for i, j, o in m.bonds
                         if i in here and j in here)
        for k, joint in enumerate(self.joints):
            bonds.extend((index[k][t], index[k + 1][h], JOINT_ORDER)
                         for t, h in joint.pairs)
        if cap and self.units:
            for unit, end, at in ((self.units[0], "head", index[0]),
                                  (self.units[-1], "tail", index[-1])):
                for member, cart in _caps(unit, end):
                    bonds.append((at[member], len(symbols), 1.0))
                    symbols.append("H")
                    positions.append(cart)
        return (tuple(symbols), np.array(positions, dtype=float),
                tuple(bonds))


def _caps(unit: Unit, end: str) -> list[tuple[int, np.ndarray]]:
    """A hydrogen on each member of an open end, along the bond the
    next unit would have made -- turned outward where that bond would
    have closed a ladder's ring."""
    m = unit.monomer
    members = m.head_members if end == "head" else m.tail_members
    turned = tail_rotation(unit)
    out = []
    for member in members:
        direction = turned @ m.free_direction(member, outward=True)
        length = radius(m, member) + elements.covalent_radius("H")
        out.append((member, unit.cart[member] + length * direction))
    return out


def single_chain(units, torsion: float = 180.0, flips=None,
                 cap: bool = True) -> Chain:
    """One chain in vacuum: every single joint at ``torsion`` degrees
    (trans by default), every ladder joint flipped where ``flips``
    says.  ``units`` are monomers, each already the hand it should
    be -- see :func:`xtal.polymer.sequence.units`."""
    units = list(units)
    chain = Chain()
    if not units:
        return chain
    chain.units.append(first(units[0]))
    for k, monomer in enumerate(units[1:]):
        flip = bool(flips[k]) if flips is not None else False
        unit, joint = place_at(chain.units[-1], monomer, torsion, flip)
        chain.units.append(unit)
        chain.joints.append(joint)
    return chain
