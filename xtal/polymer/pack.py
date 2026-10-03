"""
xtal.polymer.pack
=================
Chains grown into a box all at once: the packed starting model.

**Every chain grows at once.**  Each starts from a seed at a random
place and turn, and the chains then take one unit each in a shuffled
round until all are full.  Grown one at a time, the first chains would
wander through an empty box and the last would be pushed into whatever
holes were left, which is a model of the order it was built in rather
than of a melt -- the argument Theodorou and Suter made for Amorphous
Cell, and the one EMC and RadonPy follow.

**A step is configurational-bias.**  The next unit is tried at
:attr:`Recipe.trials` torsions about its joint bond (an even grid with
a random offset, so no angle is preferred by construction), and one
trial is taken with its Rosenbluth weight: the soft overlap of its
atoms with everything already in the box, plus a three-fold torsion
term that favours trans and gauche over eclipsed.  Without that term
every torsion is equally likely and the chain is freely rotating -- too
coiled by half.  A ladder joint has no torsion; its trials are the two
flips.  The atoms of the *next* unit that this one already fixes --
its head members -- are scored with it, because a torsion there cannot
move them.  If every trial overlaps badly the chain is a dead end and
gives back units, one more each time it fails short of the furthest it
has reached, and tries again.

**The core is soft while growing, and pushed off after.**  A trial is
refused only for atoms nearly on top of each other (:data:`HARD`);
closer than :data:`OVERLAP` is merely unlikely.  What is left is taken
out by :mod:`xtal.polymer.pushoff`, which holds every bond and angle
and moves nothing else.

**What is near what is a periodic cell list, kept up to date.**  An
atom is added when its unit is taken and removed when its unit is
given back; nothing is rebuilt for a trial, so a step costs the atoms
of one unit times their neighbours, whatever the box holds.

**A membrane is grown between walls.**  The box is periodic across
*a* and *b*; along *c* two repulsive planes stand at the faces of the
film, and vacuum is added afterwards.  No bond crosses *c*, and the
surfaces are the chains' own, not a cut.

**The model is packed, not equilibrated, and says so.**  A packed box
has the right density and no close contacts, and its chains have the local
shape the torsion term gave them; it has not relaxed at the scale of a
chain, and how entangled it is is a question for molecular dynamics.
:class:`Built` carries the numbers a person needs to judge it, and its
:meth:`Built.lines` end by saying what it is not.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from xtal.core import elements
from xtal.polymer import chain as chains
from xtal.polymer import sequence as sequences
from xtal.polymer.monomer import Monomer
from xtal.polymer.sequence import Sequence

AVOGADRO = 0.602214076          # g/cm3 per (g/mol)/A3

#: Two atoms overlap when they are closer than this fraction of the
#: sum of their van der Waals radii: 2.55 A for two carbons, 1.80 for
#: two hydrogens.  A packed melt sits at about 0.9 of the sum.
OVERLAP = 0.75
#: Two atoms closer than this fraction of their radii's sum are a
#: trial refused outright, and a step with no other trial is a dead
#: end: 1.02 A for two carbons, 0.72 for two hydrogens -- atoms nearly
#: on top of each other.  Anything between this and :data:`OVERLAP` is
#: weighted against and left to :mod:`xtal.polymer.pushoff`.  At 0.55
#: polyethylene jammed at 0.85 g/cm3 with a quarter of it unplaced, and
#: at 0.5 g/cm3 still did: with explicit hydrogens a step needs four
#: atoms clear at once, which a melt seldom offers twelve trials of.
HARD = 0.3
#: The same as the largest overlap fraction a trial may have.
DEAD = 1.0 - HARD / OVERLAP
#: The Rosenbluth temperature, in the overlap energy's units.
TAU = 0.25
#: The torsion term: ``BARRIER * (1 + cos 3 phi) / 2`` makes eclipsed
#: improbable, and ``GAUCHE * (1 + cos phi) / 2`` puts gauche above
#: trans.  At TAU, a gauche state is taken 0.47 times as often as
#: trans, which is Flory's sigma for polyethylene near 400 K.  It is
#: applied to every backbone torsion that turns, at the joints and
#: inside the units, whatever the chemistry: a packed model's local
#: shape, not a force field's.
BARRIER = 0.8
GAUCHE = 0.25
#: Two gauche torsions of opposite sign in a row bring the atoms either
#: side of them a bond's length apart -- the pentane effect -- and
#: cost this much: Flory's omega, exp(-PENTANE / TAU), about 0.09.
#: Without it the torsions are independent and polyethylene came out
#: C_n 3.3 against a melt's 7.  The soft core cannot supply it: the
#: two carbons meet at 2.5 A, right where :data:`OVERLAP` begins.
PENTANE = 0.6
#: Where growth is tried when no start density is given: fractions of
#: the target for a chain that turns, densities in g/cm3 for a ladder.
#: The second of each is the retry after a jam.
START_FRACTIONS = (0.75, 0.4)
LADDER_STARTS = (0.2, 0.1)
#: How many chains' seeds, and how many backtracks per unit asked
#: for, before a build is given up as too full.
SEED_TRIES = 200
BACKTRACKS_PER_UNIT = 4
#: The most units one dead end gives back.
MAX_BACK = 8


class PackError(ValueError):
    """A recipe that cannot be packed, said before or during growth."""


class Jammed(PackError):
    """A box too full to grow into at the density it was grown at:
    worth trying lower, which a refusal is not."""


@dataclass(frozen=True)
class Recipe:
    """What to build.

    ``monomers`` are :class:`~xtal.polymer.monomer.Monomer` objects,
    already embedded.  ``density`` is the target in g/cm3;
    ``start_density`` is what the box is grown at, the same unless a
    later compression is planned (the 21-step protocol starts near
    0.1 of the target).  ``thickness`` and ``vacuum`` are a
    membrane's, in A.  ``relax_steps`` are the push-off's after growth
    or compression.
    """

    monomers: tuple[Monomer, ...]
    chains: int = 10
    length: int = 20
    sequence: Sequence = field(default_factory=Sequence)
    periodic: str = "bulk"
    density: float = 0.85
    start_density: float | None = None
    thickness: float = 30.0
    vacuum: float = 20.0
    trials: int = 12
    seed: int = 0
    relax_steps: int = 600
    max_atoms: int = 20000

    @property
    def grown_at(self) -> float:
        """The density the chains are grown at: the start density if
        one is given, otherwise the first of :meth:`starts`."""
        return self.start_density or self.starts()[0]

    def starts(self) -> tuple[float, ...]:
        """The densities growth is tried at, in turn, when no start
        density is given -- each compressed to the target after.

        Below the target because a step needs room the target seldom
        offers: polystyrene, PMMA, PET and nylon-6 grown at their
        densities jammed nine tenths placed, after up to a minute,
        and at three quarters of them grew in two to eight seconds.  A
        ladder's chain is rigid and steers only by its flips and its
        hands, and PIM-1 and PIM-EA-TB grew at 0.2 g/cm3 and no
        higher.  A squeeze of a tenth along each axis costs a chain
        little of its shape; the report says it was done.
        """
        if self.start_density:
            return (self.start_density,)
        if any(m.is_ladder for m in self.monomers):
            return tuple(min(self.density, s) for s in LADDER_STARTS)
        return tuple(f * self.density for f in START_FRACTIONS)

    def n_atoms(self) -> int:
        """Atoms the model will have, end caps included, at worst."""
        widest = max(len(m.body) for m in self.monomers)
        caps = 2 * max(len(m.head_members) for m in self.monomers)
        return self.chains * (self.length * widest + caps)

    def check(self) -> None:
        """Everything refusable, refused before anything is grown."""
        if not self.monomers:
            raise PackError("a polymer needs a monomer")
        # A joint pairs the members of one end with the other's, so
        # every end must stand for as many atoms: a ladder's two
        # against a chain's one is a bond left over at every joint.
        ends = {len(m.head_members) for m in self.monomers} | {
            len(m.tail_members) for m in self.monomers}
        if len(ends) > 1:
            raise PackError(
                "a ladder monomer, joined through two atoms at each "
                "end, cannot be copolymerised with one joined through "
                "one: every monomer's ends must stand for as many "
                "atoms")
        if self.chains < 1 or self.length < 1:
            raise PackError("a model needs one chain of one unit at "
                            "least")
        if self.periodic not in ("bulk", "membrane"):
            raise PackError(f"a model is bulk or a membrane, not "
                            f"{self.periodic!r}")
        if not 0.0 < self.density < 5.0:
            raise PackError(f"{self.density} g/cm3 is not a polymer's "
                            f"density")
        if self.start_density is not None and not (
                0.0 < self.start_density <= self.density):
            raise PackError("the start density is at most the target: "
                            "a box is grown loose and compressed, never "
                            "the other way")
        if self.periodic == "membrane" and self.thickness < 10.0:
            raise PackError(f"a membrane {self.thickness} A thick is "
                            f"thinner than the chains it is made of")
        if self.trials < 2:
            raise PackError("configurational bias needs two trials a "
                            "step at least")
        n = self.n_atoms()
        if n > self.max_atoms:
            raise PackError(
                f"{self.chains} chains of {self.length} units is about "
                f"{n} atoms, over the {self.max_atoms} this build is "
                f"limited to -- fewer or shorter chains, or raise the "
                f"limit knowing what a window of that many atoms costs")
        self.sequence.check(len(self.monomers))

    def box(self, density: float | None = None) -> np.ndarray:
        """The box (a, b, c) in A that holds the chains at ``density``,
        by default the one they are grown at."""
        counts = sequences.expected(self.sequence, len(self.monomers),
                                    self.length)
        mass = self.chains * float(
            counts @ [m.mass for m in self.monomers])
        volume = mass / ((density or self.grown_at) * AVOGADRO)
        if self.periodic == "membrane":
            side = float(np.sqrt(volume / self.thickness))
            return np.array([side, side, self.thickness])
        side = float(volume ** (1.0 / 3.0))
        return np.array([side, side, side])


class _Hash:
    """A cell list over the box, periodic in the axes that are.

    Fixed-capacity cells so a query is one gather: ``cells[x, y, z, k]``
    holds atom ids and -1 where empty, and a cell that fills up doubles
    every cell's capacity.
    """

    def __init__(self, box, periodic, cutoff: float, capacity: int):
        self.box = np.asarray(box, dtype=float)
        self.periodic = np.asarray(periodic, dtype=bool)
        self.n = np.maximum((self.box // cutoff).astype(int), 1)
        self.size = self.box / self.n
        self.cells = np.full((*self.n, 4), -1, dtype=np.int64)
        self.count = np.zeros(tuple(self.n), dtype=np.int64)
        self.pos = np.zeros((capacity, 3))
        self.radius = np.zeros(capacity)
        self.where = np.zeros((capacity, 3), dtype=np.int64)
        self.free = list(range(capacity - 1, -1, -1))
        offsets = np.array(np.meshgrid([-1, 0, 1], [-1, 0, 1],
                                       [-1, 0, 1], indexing="ij"))
        self.offsets = offsets.reshape(3, -1).T

    def _cell(self, positions) -> np.ndarray:
        wrapped = self._wrap(positions)
        index = np.floor(wrapped / self.size).astype(np.int64)
        return np.clip(index, 0, self.n - 1)

    def _wrap(self, positions) -> np.ndarray:
        positions = np.array(positions, dtype=float)
        positions[:, self.periodic] = np.mod(
            positions[:, self.periodic], self.box[self.periodic])
        return positions

    def add(self, positions, radii) -> np.ndarray:
        positions = np.asarray(positions, dtype=float).reshape(-1, 3)
        if len(positions) > len(self.free):
            raise PackError("the build ran past the atoms it was sized "
                            "for")
        ids = np.array([self.free.pop() for _ in range(len(positions))],
                       dtype=np.int64)
        cells = self._cell(positions)
        self.pos[ids] = self._wrap(positions)
        self.radius[ids] = radii
        self.where[ids] = cells
        for atom, (x, y, z) in zip(ids, cells, strict=True):
            k = self.count[x, y, z]
            if k == self.cells.shape[3]:
                grown = np.full((*self.n, 2 * k), -1, dtype=np.int64)
                grown[..., :k] = self.cells
                self.cells = grown
            self.cells[x, y, z, k] = atom
            self.count[x, y, z] = k + 1
        return ids

    def remove(self, ids) -> None:
        for atom in ids:
            x, y, z = self.where[atom]
            k = self.count[x, y, z]
            row = self.cells[x, y, z, :k]
            slot = int(np.nonzero(row == atom)[0][0])
            row[slot] = row[k - 1]
            self.cells[x, y, z, k - 1] = -1
            self.count[x, y, z] = k - 1
            self.radius[atom] = 0.0
            self.free.append(int(atom))

    def energies(self, positions, radii, exclude=None):
        """``(energy, worst)`` of each position against every atom
        held: ``sum ((sigma - d) / sigma)^2`` over the pairs closer
        than ``sigma``, and the largest ``(sigma - d) / sigma``.
        ``exclude`` maps a row to ids it does not see."""
        positions = np.asarray(positions, dtype=float).reshape(-1, 3)
        cells = self._cell(positions)
        around = cells[:, None, :] + self.offsets[None, :, :]
        outside = np.zeros(around.shape[:2], dtype=bool)
        for axis in range(3):
            if self.periodic[axis]:
                around[..., axis] %= self.n[axis]
            else:
                outside |= (around[..., axis] < 0) | (
                    around[..., axis] >= self.n[axis])
                around[..., axis] = np.clip(around[..., axis], 0,
                                            self.n[axis] - 1)
        ids = self.cells[around[..., 0], around[..., 1], around[..., 2]]
        ids[outside] = -1
        if self.n.min() < 3:
            ids = np.where(_repeated(ids), -1, ids)
        ids = ids.reshape(len(positions), -1)
        valid = ids >= 0
        if exclude:
            for row, hidden in exclude.items():
                valid[row] &= ~np.isin(ids[row], hidden)
        delta = self.pos[np.where(valid, ids, 0)] - self._wrap(
            positions)[:, None, :]
        for axis in np.nonzero(self.periodic)[0]:
            length = self.box[axis]
            delta[..., axis] -= length * np.round(delta[..., axis]
                                                  / length)
        distance = np.linalg.norm(delta, axis=-1)
        sigma = OVERLAP * (self.radius[np.where(valid, ids, 0)]
                           + np.asarray(radii)[:, None])
        overlap = np.where(valid, np.clip((sigma - distance) / sigma,
                                          0.0, None), 0.0)
        worst = overlap.max(axis=1) if overlap.shape[1] else np.zeros(
            len(positions))
        return np.sum(overlap ** 2, axis=1), worst

    def nearest(self, positions, exclude=None) -> np.ndarray:
        """Distance from each position to the closest atom held."""
        positions = np.asarray(positions, dtype=float).reshape(-1, 3)
        out = np.full(len(positions), np.inf)
        held = np.nonzero(self.radius > 0)[0]
        for row, point in enumerate(self._wrap(positions)):
            others = held if not exclude or row not in exclude else \
                np.setdiff1d(held, exclude[row])
            delta = self.pos[others] - point
            for axis in np.nonzero(self.periodic)[0]:
                length = self.box[axis]
                delta[:, axis] -= length * np.round(delta[:, axis]
                                                    / length)
            if len(delta):
                out[row] = float(np.linalg.norm(delta, axis=1).min())
        return out


def _repeated(ids) -> np.ndarray:
    """Where a small box's 27 neighbour cells name one cell twice, the
    repeats -- so an atom is not counted once per alias."""
    flat = ids.reshape(ids.shape[0], -1)
    out = np.zeros_like(flat, dtype=bool)
    for row in range(len(flat)):
        _, first = np.unique(flat[row], return_index=True)
        mask = np.ones(flat.shape[1], dtype=bool)
        mask[first] = False
        out[row] = mask & (flat[row] >= 0)
    return out.reshape(ids.shape)


def _wall(positions, recipe: Recipe) -> np.ndarray:
    """A membrane's walls: the squared distance outside the film."""
    if recipe.periodic != "membrane":
        return np.zeros(len(positions))
    z = np.asarray(positions)[:, 2]
    below = np.clip(-z, 0.0, None)
    above = np.clip(z - recipe.thickness, 0.0, None)
    return below ** 2 + above ** 2


def _pentane(torsions) -> float:
    """:data:`PENTANE` for each consecutive pair of torsions that are
    gauche of opposite signs."""
    out = 0.0
    for a, b in zip(torsions, torsions[1:], strict=False):
        if abs(a) < 120.0 and abs(b) < 120.0 and a * b < 0.0:
            out += PENTANE
    return out


def _backbone_torsions(tail: chains.Unit, before, unit: chains.Unit
                       ) -> list[float]:
    """The backbone torsions a new unit makes, with the one before it
    -- the last three backbone atoms of the chain so far (``before``,
    the tail's included), the new unit's, and its tail ``X``, which
    lies along the next backbone bond: without it the torsion inside
    the new unit was never paired with the joint before it."""
    points = np.vstack([before, unit.cart[list(unit.monomer.backbone)],
                        unit.point("tail")[None, :]])
    return [chains.dihedral(*points[i:i + 4])
            for i in range(len(points) - 3)]


def _torsion(phi_degrees: float) -> float:
    phi = np.radians(phi_degrees)
    return (BARRIER * 0.5 * (1.0 + np.cos(3.0 * phi))
            + GAUCHE * 0.5 * (1.0 + np.cos(phi)))


def _random_rotation(rng) -> np.ndarray:
    q, r = np.linalg.qr(rng.normal(size=(3, 3)))
    q = q * np.sign(np.diag(r))
    if np.linalg.det(q) < 0:
        q[:, 0] = -q[:, 0]
    return q


@dataclass
class _Growing:
    """One chain while it grows: its plan and what is placed so far."""

    plan: list
    #: Each unit's other hand, where the growth may choose it.
    other: list | None = None
    #: The rotamers of each monomer, shared by every chain.
    shapes: dict = field(default_factory=dict)
    chain: chains.Chain = field(default_factory=chains.Chain)
    ids: list = field(default_factory=list)       # hash ids per unit
    flips: list = field(default_factory=list)
    failures: int = 0
    stuck_at: int = 0

    @property
    def done(self) -> bool:
        return self.chain.n_units == len(self.plan)


def _radii(monomer: Monomer) -> np.ndarray:
    return np.array([elements.vdw_radius(monomer.elements[i])
                     for i in monomer.body])


def _exclusions(tail: chains.Unit, tail_ids, head_monomer: Monomer,
                joint) -> dict:
    """Rows of a trial unit's body -> hash ids it does not see: the
    atoms one and two bonds from it across the joint."""
    old = tail.monomer
    body = list(old.body)
    near_tail = {}
    for t, _h in joint.pairs:
        around = {t} | {j if i == t else i for i, j, _ in old.bonds
                        if t in (i, j)}
        near_tail[t] = [tail_ids[body.index(a)] for a in around
                        if a in body]
    row_of = {atom: row for row, atom in enumerate(head_monomer.body)}
    out: dict[int, list] = {}
    for t, h in joint.pairs:
        out.setdefault(row_of[h], []).extend(near_tail[t])
        for i, j, _ in head_monomer.bonds:
            if h in (i, j):
                other = j if i == h else i
                if other in row_of:
                    out.setdefault(row_of[other], []).append(
                        tail_ids[body.index(t)])
    return {row: np.array(sorted(set(ids)), dtype=np.int64)
            for row, ids in out.items()}


def grow(recipe: Recipe, say=None, check=None) -> list[chains.Chain]:
    """Every chain of ``recipe``, packed into its box.  ``check`` is
    called between steps and stops the build by raising."""
    recipe.check()
    say = say or (lambda _text: None)
    check = check or (lambda: None)
    rng = np.random.default_rng(recipe.seed)
    box = recipe.box()
    periodic = (True, True, recipe.periodic == "bulk")
    biggest = max(elements.vdw_radius(e) for m in recipe.monomers
                  for e in m.body_elements)
    space = _Hash(box, periodic, 2.0 * OVERLAP * biggest,
                  recipe.n_atoms() + 64)

    mirrored = [m.mirrored() for m in recipe.monomers]
    free = recipe.sequence.tacticity == "atactic"
    shapes: dict = {}
    for monomer, mirror in zip(recipe.monomers, mirrored, strict=True):
        _hands(shapes, monomer, mirror, rng, check)
    growing = []
    for _ in range(recipe.chains):
        drawn = sequences.draw(recipe.sequence, len(recipe.monomers),
                               recipe.length, rng)
        plan = [mirrored[i] if hand else recipe.monomers[i]
                for i, hand in drawn]
        other = ([recipe.monomers[i] if hand else mirrored[i]
                  for i, hand in drawn] if free else None)
        growing.append(_Growing(plan, other, shapes))

    for k, item in enumerate(growing):
        check()
        _seed(item, space, box, recipe, rng)
        if k == 0:
            say(f"growing {recipe.chains} chains of {recipe.length} in "
                f"a {' x '.join(f'{v:.1f}' for v in box)} A box at "
                f"{recipe.grown_at:g} g/cm3")
    budget = BACKTRACKS_PER_UNIT * recipe.chains * recipe.length
    spent = 0
    taken = recipe.chains
    total = recipe.chains * recipe.length
    reported = 0
    while True:
        open_chains = [g for g in growing if not g.done]
        if not open_chains:
            break
        for index in rng.permutation(len(open_chains)):
            check()
            item = open_chains[index]
            if _extend(item, space, recipe, rng):
                taken += 1
                continue
            spent += 1
            if spent > budget:
                raise Jammed(
                    f"the box is too full to grow into at "
                    f"{recipe.grown_at:g} g/cm3: {taken} of {total} "
                    f"units placed after {spent} dead ends.  Grow at a "
                    f"lower start density and compress, or ask for "
                    f"fewer units")
            # A dead end at or before the chain's last one gives back
            # a unit more than that did, and one past it starts again
            # at one: an end in a pocket regrows into the same pocket
            # from a fixed depth, and counting from the furthest the
            # chain ever got instead slid PIM-EA-TB back to its seed.
            if item.chain.n_units > item.stuck_at:
                item.failures = 0
            item.stuck_at = item.chain.n_units
            item.failures += 1
            back = min(item.failures, MAX_BACK, item.chain.n_units - 1)
            for _ in range(back):
                _retract(item, space)
                taken -= 1
            if back == 0:
                _retract(item, space)
                taken -= 1
                _seed(item, space, box, recipe, rng)
                taken += 1
        if taken * 10 // total > reported:
            reported = taken * 10 // total
            say(f"{taken} of {total} units placed")
    return [g.chain for g in growing]


def _score(item: _Growing, space: _Hash, unit: chains.Unit,
           recipe: Recipe, exclude=None, beyond=None) -> float:
    """A trial unit's energy, ``inf`` when it cannot be taken.

    The atoms of the unit *after* it are scored too, where they are
    already fixed: a torsion at the next joint turns everything of the
    next unit but its head members, so a trial whose tail points into
    another chain is a dead end one step later, whatever is tried
    there.  Scoring only the unit's own atoms, a quarter of the
    polyethylene steps at 0.5 g/cm3 ended in one.
    """
    monomer = unit.monomer
    cart = unit.cart[list(monomer.body)]
    energy, worst = space.energies(cart, _radii(monomer), exclude)
    walls = _wall(cart, recipe)
    k = item.chain.n_units
    following = item.plan[k + 1] if k + 1 < len(item.plan) else None
    front = chains.ahead(unit, following)
    if following is None:
        radii = np.full(len(front), elements.vdw_radius("H"))
    else:
        radii = np.array([elements.vdw_radius(following.elements[h])
                          for h in following.head_members])
    near = {row: beyond for row in range(len(front))} if (
        beyond is not None) else None
    more, worse = space.energies(front, radii, near)
    if (max(worst.max(), worse.max()) >= DEAD
            or _wall(np.vstack([cart, front]), recipe).max() > 1.0):
        return np.inf
    return float(energy.sum() + more.sum() + walls.sum()
                 + _wall(front, recipe).sum())


def _shapes(item: _Growing, monomer: Monomer) -> list:
    """``(rotamer, torsion energy)`` for each staggered setting of the
    monomer's free backbone bonds -- one, the monomer itself, for a
    unit with none.  :func:`grow` fills these for both hands before
    any chain is seeded."""
    key = id(monomer)
    if key not in item.shapes:
        item.shapes[key] = (monomer, _scored(chains.rotamers(monomer)))
    return item.shapes[key][1]


def _scored(rotamers) -> list:
    return [(variant, sum(_torsion(t) for t in torsions))
            for variant, torsions in rotamers]


def _hands(shapes: dict, monomer: Monomer, mirror: Monomer, rng,
           check) -> None:
    """Both hands' rotamers into ``shapes``, the mirror's reflected
    from the first's.  A staggered set is its own mirror image and the
    torsion term is even, so they are the same settings with the same
    energies -- and when the settings are sampled, the same sample:
    enumerated apart, the two hands of a capped monomer would be built
    from different shapes."""
    first = _scored(chains.rotamers(monomer, rng=rng, check=check))
    shapes[id(monomer)] = (monomer, first)
    shapes[id(mirror)] = (mirror, [(variant.mirrored(), energy)
                                   for variant, energy in first])


def _seed(item: _Growing, space: _Hash, box, recipe: Recipe,
          rng) -> None:
    """Put a chain's first unit somewhere clear."""
    monomer = item.plan[0]
    best = None
    for _ in range(SEED_TRIES):
        origin = rng.random(3) * box
        shapes = _shapes(item, monomer)
        shape = shapes[int(rng.integers(len(shapes)))][0]
        unit = chains.first(shape, _random_rotation(rng), origin)
        energy = _score(item, space, unit, recipe)
        if np.isfinite(energy) and (best is None or energy < best[0]):
            best = (energy, unit)
        if energy == 0.0:
            break
    if best is None:
        raise Jammed(
            f"no room for another chain's first unit at "
            f"{recipe.grown_at:g} g/cm3 -- grow at a lower start "
            f"density, or ask for fewer chains")
    unit = best[1]
    item.chain.units.append(unit)
    item.ids.append(space.add(unit.cart[list(monomer.body)],
                              _radii(monomer)))


def _extend(item: _Growing, space: _Hash, recipe: Recipe, rng) -> bool:
    """One unit onto a chain, by configurational bias.  ``False`` at a
    dead end, with nothing placed.

    **An atactic chain chooses each unit's hand as it grows**, among
    the trials, each weighted by how likely the sequence says that
    dyad is.  Drawn beforehand, a rigid chain had nothing left to
    choose: PIM-1's flip turns the next unit about an axis it is
    nearly symmetric about, so its path is fixed by the spiro centres'
    hands, and a chain whose hands were drawn was one rigid shape --
    six of them did not fit a box at 0.3 g/cm3.  The meso fraction is
    then a result, and the report gives it.
    """
    k = item.chain.n_units
    tail = item.chain.units[-1]
    hands = [item.plan[k]]
    if item.other is not None:
        hands.append(item.other[k])
    p = recipe.sequence.p_meso
    prior = [p if m.mirror == tail.monomer.mirror else 1.0 - p
             for m in hands]
    body = list(hands[0].body)
    if hands[0].is_ladder:
        options = [(0.0, flip, hand, hands[hand], 0.0)
                   for flip in (False, True)
                   for hand in range(len(hands))]
    else:
        # Each trial a joint torsion off an even grid and a rotamer
        # of the unit's own backbone, drawn at random.
        start = rng.random() * 2.0 * np.pi
        options = []
        for j in range(recipe.trials):
            hand = j % len(hands)
            shapes = _shapes(item, hands[hand])
            shape, inside = shapes[int(rng.integers(len(shapes)))]
            options.append((start + 2.0 * np.pi * j / recipe.trials,
                            False, hand, shape, inside))
    # A one-atom backbone puts the next head member two bonds from
    # this unit's tail, not three.
    beyond = (item.ids[-1] if len(hands[0].backbone) == 1 else None)
    before = None
    if not hands[0].is_ladder:
        recent = np.vstack([u.cart[list(u.monomer.backbone)]
                            for u in item.chain.units[-3:]])
        if len(recent) >= 3:
            before = recent[-3:]
    placed, energies, priors = [], [], []
    for twist, flip, hand, monomer, inside in options:
        if prior[hand] <= 0.0:
            continue
        unit, joint = chains.place(tail, monomer, twist, flip)
        exclude = _exclusions(tail, item.ids[-1], monomer, joint)
        energy = _score(item, space, unit, recipe, exclude, beyond)
        if np.isfinite(energy) and not monomer.is_ladder:
            energy += inside + _torsion(chains.joint_torsion(tail, unit))
            if before is not None:
                energy += _pentane(_backbone_torsions(tail, before,
                                                      unit))
        elif np.isfinite(energy) and not _continues(item, space, unit):
            energy = np.inf
        placed.append((unit, joint, flip))
        energies.append(energy)
        priors.append(prior[hand])
    energies = np.array(energies)
    if not np.isfinite(energies).any():
        return False
    weights = np.array(priors) * np.exp(-(energies - energies.min())
                                        / TAU)
    choice = int(rng.choice(len(placed), p=weights / weights.sum()))
    unit, joint, flip = placed[choice]
    item.chain.units.append(unit)
    item.chain.joints.append(joint)
    item.flips.append(flip)
    item.ids.append(space.add(unit.cart[body], _radii(unit.monomer)))
    return True


def _continues(item: _Growing, space: _Hash, unit: chains.Unit) -> bool:
    """Whether a ladder unit leaves the next one anywhere to go.

    A ladder step has four choices at most, and a rigid chain can take
    one that every continuation folds back from: PIM-EA-TB passed a
    step with all four clear and failed the next with none, again and
    again, so each step is taken only where a next one fits.
    """
    k = item.chain.n_units + 1
    if k >= len(item.plan):
        return True
    hands = [item.plan[k]]
    if item.other is not None:
        hands.append(item.other[k])
    for monomer in hands:
        radii = _radii(monomer)
        for flip in (False, True):
            after, _ = chains.place(unit, monomer, 0.0, flip)
            _, worst = space.energies(after.cart[list(monomer.body)],
                                      radii)
            if worst.max() < DEAD:
                return True
    return False


def _retract(item: _Growing, space: _Hash) -> None:
    """Give back a chain's last unit."""
    space.remove(item.ids.pop())
    item.chain.units.pop()
    if item.chain.joints:
        item.chain.joints.pop()
        item.flips.pop()
