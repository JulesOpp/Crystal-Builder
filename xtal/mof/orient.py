"""
xtal.mof.orient
===============
Which way round a block goes on its slot.

A node block is placed by fitting its connection directions onto the
slot's, and for a symmetric node a great many fits are equally good.
An octahedral node has **24** of them and they are not cosmetic: the
RMSD spread across the 24 is 6e-08 while the body of the block moves
up to 8.2 A between them.  The primary fit has no reason to prefer one
over another and takes whichever its Euler grid reached first, so
which face a node presents to its neighbour is, today, an accident.

That did not matter while a connection point stood for one atom --
there is nothing to present.  It matters as soon as one stands for
two: the two ends of a joint bond well exactly when their members
line up, and a node turned a quarter turn about the joint axis has
its two members across the other end's rather than along them.
MFU-4l's joints come out as a *square* -- all four member-to-member
distances equal -- which is that quarter turn with nothing to break
it.

So the tie is broken here, and only the tie.  Three things make that
safe rather than a second fit:

* the tie set is **enumerated, not searched**.  ``G``, the block's own
  rotation group, comes from Kabsch on ordered triples of connection
  directions -- ``n^3`` candidates and never ``n!`` -- and composed
  with the primary fit it *is* the brute-force tie set, checked
  against all 720 permutations of a six-connected node;
* every candidate is validated by calling the vendored
  ``locator.locate_with_permutation``, so the placement that is scored
  is the placement that will be produced;
* the default rule is :data:`AS_FOUND`, which is today's behaviour and
  returns nothing at all.  A build only reaches any of this when a
  block is polydentate *and* the user asked for the other rule.

**What is scored is the two nodes at the ends of an edge, not a node
against its linker.**  A linker's angle about its own axis is a
continuous freedom and the primary fit leaves it undetermined --
``locate_with_permutation`` on a two-point target is Kabsch on two
vectors, which scipy itself warns is "not uniquely defined".  Turning
the linker is therefore free and belongs to the next phase; what no
continuous turn can repair is two *nodes* presenting faces a quarter
turn apart across the same edge, and that is what a discrete choice
is for.

**Two tolerances are measured rather than chosen**, and both are in
``docs/ROADMAP.md`` § 2.  The rotation-group search needs
:data:`TOLERANCE` = 1e-3, because a block cut from a real crystal is
octahedral to about a thousandth of a degree and at 1e-6 the search
returns only the identity.  And a tie is decided by a **gap** and
never by an absolute epsilon: the blocks' own imperfection is around
1e-5, larger than any fixed threshold worth writing, while the gap
between a fit and a worse one is a factor of 10^5 -- 4.6e-06 against
8.2e-01 on MFU-4l, and 98,000-fold against the scaled net.

PORMAKE is imported at the point of use, as everywhere else in
:mod:`xtal`; nothing here touches Qt and every test of it is headless.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np

from xtal.mof.attach import Attachment, members_of, pair_cost
from xtal.mof.build import (
    MofError,
    edge_axis,
    edge_ends,
    import_pormake,
    point_at,
)

#: Today's behaviour: the primary fit chooses, and nothing here runs.
AS_FOUND = "as-found"

#: Minimise the disagreement between the two ends of every edge.
CONSISTENT = "consistent"

#: The rules, in the order a form should offer them.
RULES = (AS_FOUND, CONSISTENT)

#: How nearly a candidate rotation has to be a rotation.
#:
#: Not cosmetic and not a safety margin.  A block cut out of a real
#: crystal is octahedral to about a thousandth of a degree rather than
#: to machine precision, so at 1e-6 the search below finds only the
#: identity and the whole tie set collapses to one member -- which
#: reads exactly like "this block has no symmetry" and is wrong.
TOLERANCE = 1e-3

#: How much worse a fit has to be before it is not a tie.
#:
#: A *factor*, because the thing being separated is a fit at 1e-6 from
#: one at 1e-1 and no absolute epsilon sits between them for every
#: block: the imperfection of a block cut from a crystal is around
#: 1e-5, larger than any epsilon small enough to be safe.  The
#: measured gap is five orders of magnitude and the spread *within* a
#: tie set is a factor of four, so a hundred is two orders clear of
#: both ends.
TIE_GAP = 100.0

#: Three directions this nearly coplanar do not say which way round a
#: block is.  PORMAKE's own locator works to the same figure.
COPLANAR = 0.3

#: Below this a fit is exact and a ratio against it means nothing.
_FLOOR = 1e-12

#: Costs are compared to this many places, so that two orientations
#: that differ only in rounding are decided by the tie-break below
#: them rather than by the last bit of a sum.
_PLACES = 9

#: How many whole-net evaluations the by-type sweep may make before it
#: descends one type at a time instead.  One node type on an
#: octahedral block is 24; two is 576; the limit is reached only by a
#: net with three or more node types, where a product over all of them
#: stops being worth its time.
_SWEEP_BUDGET = 1024


@dataclass(frozen=True)
class Fit:
    """One way a block sits on one slot, and how well.

    ``permutation`` is what ``Builder.build(permutations=...)`` takes;
    ``rotation`` is the element of the block's own rotation group that
    produced it, and is what makes the same choice nameable on two
    different slots -- their permutations differ, because each is
    composed with that slot's own primary fit, but the rotation is the
    same turn of the same block.
    """

    slot: int
    permutation: tuple[int, ...]
    rotation: tuple[int, ...]
    rmsd: float


# ======================================================================
#  THE BLOCK'S OWN SYMMETRY
# ======================================================================

def _locator():
    """PORMAKE's locator, with PORMAKE imported at the point of use.

    Through :func:`xtal.mof.build.import_pormake` and never by a plain
    import, because that is where its logger is rewired onto the run
    log -- a module that reached round it would put PORMAKE's forty
    lines back on stdout.
    """
    import_pormake()
    from xtal.mof.pormake.locator import Locator

    return Locator()


def directions(block) -> np.ndarray:
    """A block's connection directions, as PORMAKE normalises them."""
    return np.asarray(block.local_structure().atoms.positions,
                      dtype=float)


def rotation_group(block, tolerance: float = TOLERANCE) -> tuple:
    """The proper rotations that map a block's connection directions
    onto themselves, as permutations of those directions.

    Enumerated rather than searched: **two** directions and the normal
    of the plane they span fix a rotation, so every candidate is an
    ordered pair and there are at most ``n(n-1)`` of them -- 24 for a
    six-connected node against 720 permutations, and 132 for a
    twelve-connected one against 479 million.  Each candidate is then
    kept only if it really does permute the set, to ``tolerance``.

    Composed with a slot's primary fit this equals the brute-force
    tie set exactly: measured over all 720 permutations of an
    octahedral node, where the gap it has to find is 4.21e-08 against
    8.16e-01.

    **Ordered pairs and not ordered triples**, which is what
    ``probes/polydentate/p2_lever.py`` measured with.  Three
    directions of a *planar* block never span a volume, so a triple
    can name no rotation of one at all and the search returns the
    identity alone -- which reads exactly like "this block is not
    symmetric" and is wrong by a factor of six for the trigonal node
    a layer net is built out of.  A pair and a normal has no such
    blind spot, and on the octahedral node the two agree member for
    member.

    Reflections are excluded, and that is the point of the
    determinant test: a mirrored block is a different molecule, and
    PORMAKE substitutes one deliberately or not at all.
    """
    q = directions(block)
    n = len(q)
    pairs = [pair for pair in itertools.permutations(range(n), 2)
             if _frame(q[pair[0]], q[pair[1]]) is not None]
    if not pairs:
        # Every direction parallel to every other -- a two-connected
        # linker.  Its freedom is the continuous angle about its own
        # axis, which is not a permutation of anything and is not
        # this function's to name.
        return ((),) if n == 0 else (tuple(range(n)),)
    first = _frame(q[pairs[0][0]], q[pairs[0][1]])
    found: set[tuple[int, ...]] = set()
    for i, j in pairs:
        rotation = first.T @ _frame(q[i], q[j])
        if not np.allclose(rotation.T @ rotation, np.eye(3),
                           atol=tolerance):
            continue
        if float(np.linalg.det(rotation)) < 0:      # pragma: no cover
            continue
        mapping = _mapping(q, q @ rotation, tolerance)
        if mapping is not None:
            found.add(mapping)
    return tuple(sorted(found))


def _frame(a, b):
    """An orthonormal frame built on two directions, or ``None``.

    ``None`` when they are too nearly parallel to span a plane, which
    is where a normal cannot be taken and a rotation is therefore not
    determined -- the two opposite arms of an octahedral node, and
    both ends of any linker.  :data:`COPLANAR` is a sine here, so the
    pairs it refuses are within about 17 degrees of a straight line.
    """
    normal = np.cross(a, b)
    length = float(np.linalg.norm(normal))
    if length < COPLANAR:
        return None
    normal = normal / length
    along = a / float(np.linalg.norm(a))
    return np.array([along, np.cross(normal, along), normal])


def _mapping(q, turned, tolerance):
    """Which direction each turned one landed on, or ``None``.

    ``None`` when a turned direction is not on any of them, and when
    two of them land on the same one: a rotation of the set is a
    permutation of it, and anything else is a numerical accident of
    the tolerance above.
    """
    out = []
    for row in turned:
        distance = np.linalg.norm(q - row, axis=1)
        if float(distance.min()) > tolerance:
            return None
        out.append(int(np.argmin(distance)))
    return tuple(out) if len(set(out)) == len(out) else None


def readable(block) -> bool:
    """Whether a placed block still has the atoms that mark where it
    connects.

    It need not.  The framework's atoms are built as
    ``sum(bb_atoms_list[1:], bb_atoms_list[0])`` and its connection
    points then deleted; where exactly one slot is filled -- one node
    type on a net with no linker -- that sum **is** its one argument,
    so the delete lands on the located block as well and it comes
    back short of every ``X`` it had, while ``bonds`` and
    ``connection_point_indices`` go on naming them.  The same
    upstream accident :func:`xtal.mof.build._placed_atoms` works
    around; here there is nothing to work around with, because the
    positions themselves are what has gone.
    """
    points = np.asarray(block.connection_point_indices, dtype=int)
    return bool(points.size) and int(points.max()) < len(block.atoms)


def handedness(block) -> float:
    """The signed volume of three of a block's connection directions.

    How a mirrored block is told from the block itself -- see
    :func:`mirrored`.  ``0.0`` when no three of them span a volume,
    which is a planar or linear block, whose mirror image is one of
    its own rotations and so is not a substitution at all.

    The *first* triple in a fixed order rather than the largest, so
    that two copies of one block are always measured on the same three
    directions: the sign is what is compared and the magnitude is
    never used.
    """
    q = directions(block)
    for triple in itertools.permutations(range(len(q)), 3):
        volume = float(np.linalg.det(q[list(triple)]))
        if abs(volume) > COPLANAR:
            return volume
    return 0.0


def mirrored(block, located) -> bool:
    """Whether a placed block is the mirror image of the one given.

    ``builder.py:313`` substitutes ``make_chiral_building_block`` when
    a slot's fit is more than 1 % above the best that block can do,
    and it says so only in a log line.  A second pass that pins
    permutations ``continue``s at ``:266``, before that substitution
    is ever reached -- so it would place the *un-mirrored* block, come
    out worse than the pass before it, and have nothing to say about
    why.  This is how that is caught: a mirror flips the sign of the
    volume three connection directions span, and a rotation does not.
    """
    return handedness(block) * handedness(located) < 0


def substitute_mirrored(blocks, framework) -> tuple[list, list]:
    """Put back whatever the first pass quietly mirrored.

    Modifies ``blocks`` in place and returns ``(substituted,
    unchecked)`` -- the slots it turned over, and the slots whose
    placement could not be read at all, so that a build can say both
    rather than leaving a substitution that happened in one pass and
    not the other, or a check that silently did not happen.

    A slot is unreadable exactly when one node type is on a net with
    no linker; see :func:`readable`.  Its placement is then the only
    one in the framework, so what a wrong answer there costs is one
    block turned inside out rather than a framework half mirrored --
    and it is reported rather than assumed away.

    Measured at **0** substitutions over ``pcu`` and ``acs`` with the
    four probe blocks, because their fits are near-exact and the 1 %
    retry is never reached.  The guard stays: the sample is two nets.
    """
    located = framework.info["located_bbs"]
    changed, unchecked = [], []
    for slot, block in enumerate(blocks):
        if block is None or located[slot] is None:
            continue
        if not (readable(block) and readable(located[slot])):
            unchecked.append(slot)
            continue
        if mirrored(block, located[slot]):
            blocks[slot] = block.make_chiral_building_block()
            changed.append(slot)
    return changed, unchecked


# ======================================================================
#  THE TIE SET
# ======================================================================

def tie_set(topology, slot, block, group=None) -> tuple[Fit, ...]:
    """Every way this block fits this slot as well as the best one.

    The block's rotation group composed with the slot's primary fit,
    each member then **validated by placing it** -- the same
    ``locate_with_permutation`` the builder will call, so the RMSD
    scored is the RMSD produced rather than one derived from the
    group.

    Ordered by permutation and never by RMSD, and that is not tidiness
    either.  ``locate``'s early exit at ``locator.py:189-190`` stops at
    the first orientation on its Euler grid that is good enough, so
    the primary fit -- and with it every permutation here -- depends on
    the order the grid was walked in.  Sorting by the permutation
    itself is what makes two runs of one build choose the same
    orientation.
    """
    locator = _locator()
    target = topology.local_structure(int(slot))
    baseline = np.asarray(locator.locate(target, block)[1], dtype=int)
    group = rotation_group(block) if group is None else group
    fits = []
    for rotation in group:
        permutation = tuple(int(v) for v in
                            np.asarray(rotation)[baseline])
        rmsd = float(locator.locate_with_permutation(
            target, block, np.asarray(permutation))[1])
        fits.append(Fit(int(slot), permutation, tuple(rotation),
                        rmsd))
    return _tied(fits)


def _tied(fits) -> tuple[Fit, ...]:
    """The fits below the first real gap above the best one.

    Gap-based and never an absolute epsilon: see :data:`TIE_GAP`.
    With nothing above the gap -- which is the ordinary case, because
    a rotation group's members all fit by construction -- every one of
    them is a tie.
    """
    ordered = sorted(fits, key=lambda fit: fit.rmsd)
    cut = len(ordered)
    for k in range(len(ordered) - 1):
        if ordered[k + 1].rmsd > max(ordered[k].rmsd,
                                     _FLOOR) * TIE_GAP:
            cut = k + 1
            break
    return tuple(sorted(ordered[:cut],
                        key=lambda fit: fit.permutation))


# ======================================================================
#  CHOOSING BETWEEN THEM
# ======================================================================

def choose_permutations(topology, blocks, rule: str = AS_FOUND,
                        baseline=None, log=None) -> dict:
    """``{node slot: permutation}`` for ``Builder.build``.

    Empty under :data:`AS_FOUND`, which is the default and is today's
    behaviour: an empty map is exactly "let the locator decide", so
    the rule that changes nothing changes nothing structurally rather
    than by agreeing with itself.

    Under :data:`CONSISTENT` the sum of
    :func:`xtal.mof.attach.pair_cost` over every edge of the net is
    minimised -- the two nodes an edge joins, scored on the *unit*
    laterals their attachments present across that edge, which is
    0.000000 when they agree and 2.000000 at a quarter turn.

    Solved by trying one rotation per node **type** first, which is
    exact whenever the slots of a type are related by a symmetry of
    the net -- and 24 evaluations for an octahedral node -- then by
    coordinate descent over the slots themselves, which can only
    improve on it.  Both break ties by the lowest permutation, so two
    runs of one build choose the same orientation.

    ``baseline`` is what the fit already chose, and giving it is what
    makes this rule unable to make a build worse: the search starts
    there and moves only where it is **strictly** better, so a net on
    which the cost is already at its minimum -- which is every net
    whose edges join a node to an image of itself, where the two ends
    of an edge are antipodal points of one block and agree by
    construction -- comes back with the placement it arrived with
    rather than with another that merely scores the same.
    """
    if rule not in RULES:
        raise MofError(
            f"{rule!r} is not a way of orienting nodes; have "
            f"{', '.join(RULES)}")
    if rule == AS_FOUND:
        return {}

    nodes = [int(i) for i in topology.node_indices]
    members = {slot: members_of(blocks[slot].connection_point_indices,
                                blocks[slot].bonds)
               for slot in nodes}
    if not any(len(found) > 1 for table in members.values()
               for found in table.values()):
        # Not "no bond block": PORMAKE guesses one for a file that
        # has none, so every block declares *something*.  What
        # decides whether there is anything to score is denticity --
        # a connection point standing for one atom presents no frame,
        # and `pair_cost` is 0 for every joint in such a build.
        raise MofError(
            f"the {rule!r} rule turns a node so that the two ends of "
            f"a joint present the same face, and no connection point "
            f"of these blocks stands for more than one atom -- so "
            f"there are no faces and nothing to choose between")

    groups: dict[tuple, tuple] = {}
    ties: dict[int, tuple[Fit, ...]] = {}
    for slot in nodes:
        block = blocks[slot]
        key = (block.name, handedness(block) > 0)
        if key not in groups:
            groups[key] = rotation_group(block)
        ties[slot] = tie_set(topology, slot, block, groups[key])

    score = _Score(topology, blocks, members, nodes)
    start = _start(nodes, ties, baseline)
    choice = _by_type(topology, nodes, ties, score, start)
    choice = _descend(nodes, ties, score, choice)
    _say(log, f"orientation {rule}: joints disagree by "
              f"{score.cost(choice):.6f} over {len(score.edges)} "
              f"edge(s), against {score.cost(start):.6f} as found")
    return {slot: np.asarray(choice[slot]) for slot in nodes}


def _start(nodes, ties, baseline) -> dict:
    """Where the search begins: what the fit chose, where it can.

    A permutation the fit chose that is not in the tie set cannot be
    started from -- it would be a placement this rule is not allowed
    to make -- so such a slot begins at its lowest permutation
    instead.  In practice it does not happen: the tie set is the
    fit's own choice composed with the block's rotation group, and
    the identity is in every group.
    """
    start = {}
    for slot in nodes:
        found = None if baseline is None else baseline.get(slot)
        given = (None if found is None
                 else tuple(int(v) for v in found))
        allowed = {fit.permutation for fit in ties[slot]}
        start[slot] = (given if given in allowed
                       else ties[slot][0].permutation)
    return start


class _Score:
    """The cost of one whole assignment, with the placements cached.

    A slot's block placed with a given permutation is one Kabsch fit
    and the search asks for the same few dozen of them over and over,
    so they are kept.  Only the *offsets* of an attachment are ever
    read, which is why the placement need not be translated onto the
    net: an attachment's frame is the same wherever the block is.
    """

    def __init__(self, topology, blocks, members, nodes):
        self.topology = topology
        self.blocks = blocks
        self.members = members
        self.locator = _locator()
        # Every edge of the net, and not only the ones with a linker
        # on them: what is scored is the two *nodes* an edge joins,
        # so an edge slot left empty is scored exactly as one with a
        # block on it -- and is the case where this decides the whole
        # joint rather than half of it.
        self.edges = {
            edge: ends for edge, ends in edge_ends(topology).items()
            if ends[0][0] in set(nodes) and ends[1][0] in set(nodes)}
        self.axes = {edge: edge_axis(topology, edge)
                     for edge in self.edges}
        self._placed: dict[tuple, np.ndarray] = {}
        self._nodes = nodes

    def positions(self, slot, permutation) -> np.ndarray:
        key = (slot, permutation)
        if key not in self._placed:
            located, _rmsd = self.locator.locate_with_permutation(
                self.topology.local_structure(slot),
                self.blocks[slot], np.asarray(permutation))
            self._placed[key] = np.asarray(
                located.atoms.get_positions(), dtype=float)
        return self._placed[key]

    def attachment(self, slot, permutation, ordinal):
        """The attachment one of this slot's edges leaves through, or
        ``None`` when it stands for fewer than two atoms and so has no
        frame to agree about."""
        point = point_at(self.blocks[slot], permutation, ordinal)
        found = self.members[slot].get(point, ())
        if len(found) < 2:
            return None
        positions = self.positions(slot, permutation)
        return Attachment(point, tuple(found),
                          positions[list(found)] - positions[point])

    def cost(self, choice) -> float:
        total = 0.0
        for edge, ((a, oa), (b, ob)) in self.edges.items():
            here = self.attachment(a, choice[a], oa)
            there = self.attachment(b, choice[b], ob)
            if here is None or there is None:
                continue
            total += pair_cost(here, there, self.axes[edge])
        return total

    def key(self, choice):
        """What makes one assignment better than another.

        The cost to :data:`_PLACES`, then the permutations themselves:
        two orientations that cost the same to nine places are decided
        by the lowest permutation, and never by whichever the search
        reached first.
        """
        return (round(self.cost(choice), _PLACES),
                tuple(choice[slot] for slot in self._nodes))


def _by_type(topology, nodes, ties, score, start) -> dict:
    """One rotation for every slot of a node type, the best such.

    Exact wherever the slots of a type are related by a symmetry of
    the net, which is most of them: the same turn of the same block
    applied everywhere is what "the nodes agree" means on such a net.
    It is also small -- one octahedral node type is 24 whole-net
    evaluations -- which is why it runs before the descent rather
    than instead of it.

    Only rotations every slot of the type ties on are offered, because
    a rotation that is a tie on one slot and a worse fit on another is
    not a choice this may make: the fit comes first and this breaks
    what it leaves.
    """
    by_type: dict[int, list[int]] = {}
    for slot in nodes:
        by_type.setdefault(int(topology.get_node_type(slot)),
                           []).append(slot)
    shared = {}
    for kind, slots in by_type.items():
        shared[kind] = sorted(set.intersection(
            *[{fit.rotation for fit in ties[slot]}
              for slot in slots]))
    kinds = sorted(shared)
    if not all(shared[kind] for kind in kinds):     # pragma: no cover
        return start

    total = 1
    for kind in kinds:
        total *= len(shared[kind])
    combinations = (itertools.product(*[shared[k] for k in kinds])
                    if total <= _SWEEP_BUDGET
                    else _one_type_at_a_time(kinds, shared))

    best, best_key = None, None
    for turns in combinations:
        trial = {}
        for kind, rotation in zip(kinds, turns, strict=True):
            for slot in by_type[kind]:
                trial[slot] = _same_rotation(ties[slot], rotation)
        key = score.key(trial)
        if best_key is None or key < best_key:
            best, best_key = trial, key
    return best if _better(score, best_key, start) else start


def _better(score, key, incumbent) -> bool:
    """Whether a candidate is worth moving off what the fit chose.

    **Strictly cheaper, never merely as cheap.**  Equally good is what
    every net whose edges join a node to an image of itself answers,
    and on such a net "as good" would still mean a different
    framework: a different orientation of the same block, chosen by
    nothing.  The lowest-permutation rule breaks ties *between
    candidates* and never against the placement already in hand.
    """
    if key is None:                                 # pragma: no cover
        return False
    return key[0] < round(score.cost(incumbent), _PLACES)


def _one_type_at_a_time(kinds, shared):
    """The sweep, for a net with too many node types to take at once.

    Each type's rotations against the first of every other type's, so
    that a net with five node types is five times 24 evaluations
    rather than 24 to the fifth.  It does **not** carry an
    improvement forward from one type to the next and is not meant
    to: it is a cheap starting point, and :func:`_descend` is the
    descent, over every slot rather than every type.
    """
    base = [shared[kind][0] for kind in kinds]
    for position, kind in enumerate(kinds):
        for rotation in shared[kind]:
            yield tuple(base[:position] + [rotation]
                        + base[position + 1:])


def _same_rotation(fits, rotation) -> tuple[int, ...]:
    """The permutation this slot reaches that turn of its block by."""
    for fit in fits:
        if fit.rotation == rotation:
            return fit.permutation
    return fits[0].permutation                      # pragma: no cover


def _descend(nodes, ties, score, choice) -> dict:
    """Coordinate descent: one slot at a time, until nothing improves.

    ICM, and it can only improve on what :func:`_by_type` found
    because that assignment is where it starts.  What it is for is the
    net whose slots of one type are *not* all alike -- an interface, a
    defect, a supercell with two blocks in it -- where one turn for
    the whole type is not the answer and no closed form gives one.

    A slot moves only when some fit of its own is **strictly**
    cheaper than the one it holds, and where several are equally
    cheap the lowest permutation takes it.  Both halves of that are
    what stop two runs of one build differing.
    """
    choice = dict(choice)
    for _sweep in range(len(nodes) + 1):
        moved = False
        for slot in nodes:
            best, best_key = None, None
            for fit in ties[slot]:
                trial = dict(choice)
                trial[slot] = fit.permutation
                key = score.key(trial)
                if best_key is None or key < best_key:
                    best, best_key = trial, key
            if _better(score, best_key, choice):
                choice, moved = best, True
        if not moved or round(score.cost(choice), _PLACES) <= 0.0:
            break
    return choice


def _say(log, text: str) -> None:
    if log is not None:
        log(text)
