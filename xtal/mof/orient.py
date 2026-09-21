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
  returns nothing at all.  A build only reaches any of this when the
  user asked for the other rule *and* a connection point has a frame:
  several atoms, or the plane its one atom presents
  (:func:`xtal.mof.attach.face_of`), which is what makes MOF-5's
  clusters alternate.

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

from xtal.mof.attach import (
    Attachment,
    face_of,
    members_of,
    pair_cost,
    pairing,
    presents_face,
    unit_laterals,
)
from xtal.mof.build import (
    MofError,
    _framework_indices,
    edge_axis,
    edge_ends,
    fused_points,
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

#: How much worse, in Angstrom, a second pass may fit than the first
#: before it is thrown away and the first kept.
#:
#: Measured, not chosen: the second pass rebuilt with the *same*
#: permutations the first chose comes back with the same ``max_rmsd``
#: to the last bit on all eight builds tried, so there is no rebuild
#: noise to allow for -- only the spread inside a tie set, which is
#: 1e-5 on a block cut from a crystal.  What this has to catch is two
#: orders the other side: ``nbo`` on N466 and E14, turned, fitted
#: 0.973 A against 0.562 as found.
FIT_SLACK = 1e-3

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
    which the cost is already at its minimum comes back with the
    placement it arrived with rather than with another that merely
    scores the same.

    A net whose edges join a node to an image of itself cannot be
    helped by this at all: one slot, one orientation, and both ends of
    every edge are points of the same placed block.  Where those
    antipodal points present the same face that costs nothing; where
    they do not it cannot be fixed on that cell.  MOF-5's cluster is
    the second kind -- a Td node's opposite carboxylates are turned a
    quarter turn apart -- so ``pcu`` x 1x1x1 on N16 stays at 6.0 over
    its three edges, and the net repeated 2x2x2 has the eight slots
    that alternate to 0.
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
    if not any(presents_face(blocks[slot].connection_point_indices,
                             blocks[slot].bonds,
                             blocks[slot].atoms.get_positions())
               for slot in nodes):
        # Not "no bond block": PORMAKE guesses one for a file that
        # has none, so every block declares *something*.  What
        # decides whether there is anything to score is denticity --
        # a connection point standing for one atom presents no frame,
        # and `pair_cost` is 0 for every joint in such a build.
        raise MofError(
            f"the {rule!r} rule turns a node so that the two ends of "
            f"a joint present the same face, and no connection point "
            f"of these blocks stands for more than one atom or hangs "
            f"off an atom with a plane to present -- so there are no "
            f"faces and nothing to choose between")

    groups: dict[tuple, tuple] = {}
    ties: dict[int, tuple[Fit, ...]] = {}
    for slot in nodes:
        block = blocks[slot]
        key = (block.name, handedness(block) > 0)
        if key not in groups:
            groups[key] = rotation_group(block)
        ties[slot] = tie_set(topology, slot, block, groups[key])

    ties = _admit(nodes, ties, baseline)
    score = _Score(topology, blocks, members, nodes)
    start = _start(nodes, ties, baseline)
    choice = _by_type(topology, nodes, ties, score, start)
    choice = _descend(nodes, ties, score, choice)
    _say(log, f"orientation {rule}: joints disagree by "
              f"{score.cost(choice):.6f} over {len(score.edges)} "
              f"edge(s), against {score.cost(start):.6f} as found")
    return {slot: np.asarray(choice[slot]) for slot in nodes}


def _admit(nodes, ties, baseline) -> dict:
    """The tie sets, with the fit's own permutation in every one.

    It was assumed to be there already -- the tie set is the fit
    composed with the block's rotation group, and the identity is in
    every group -- and it is not always.  :func:`tie_set` locates the
    block afresh, and ``locate`` stops at the first orientation on its
    Euler grid that is good enough, so on a block that fits its slot
    loosely the two land on different permutations: ``cds`` on N307
    had a tie set of one that was not the builder's, and the
    synthetic node on ``acs`` two of 24 that were not.  The search
    then started such a slot somewhere else and rebuilt the framework
    whether or not that was any cheaper -- on ``cds`` a joint went
    from 3.49 A to 2.54 at the *same* cost.  Admitted as a candidate
    and started from, the fit is left only for something strictly
    better, which is the promise the rest of this module makes.
    """
    if baseline is None:
        return ties
    ties = dict(ties)
    for slot in nodes:
        found = baseline.get(slot)
        if found is None:
            continue
        given = tuple(int(v) for v in found)
        if given not in {fit.permutation for fit in ties[slot]}:
            ties[slot] = tuple(sorted(
                (*ties[slot], Fit(int(slot), given, (), float("nan"))),
                key=lambda fit: fit.permutation))
    return ties


def _start(nodes, ties, baseline) -> dict:
    """Where the search begins: what the fit chose.

    After :func:`_admit` the fit's own permutation is in every slot's
    tie set, so the lowest permutation is only where a search with no
    baseline at all begins.
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
        # The search asks for the same joint under the same two
        # orientations over and over -- 15 096 times on MFU-4l's pcu
        # x 2x2x2 for 1736 distinct answers -- so each is scored once.
        self._attached: dict[tuple, Attachment | None] = {}
        self._joint: dict[tuple, float] = {}
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
        """The attachment one of this slot's edges leaves through --
        its members, or the face its one atom presents -- or ``None``
        where it has no frame to agree about."""
        key = (slot, permutation, ordinal)
        if key not in self._attached:
            self._attached[key] = self._attach(slot, permutation,
                                               ordinal)
        return self._attached[key]

    def _attach(self, slot, permutation, ordinal):
        block = self.blocks[slot]
        point = point_at(block, permutation, ordinal)
        found = self.members[slot].get(point, ())
        positions = self.positions(slot, permutation)
        if len(found) < 2:
            return face_of(block.connection_point_indices, block.bonds,
                           positions, point)
        return Attachment(point, tuple(found),
                          positions[list(found)] - positions[point])

    def joint(self, edge, here, there) -> float:
        """One edge's cost with its two nodes turned ``here`` and
        ``there``; 0.0 where either end presents no frame."""
        key = (edge, here, there)
        if key not in self._joint:
            (a, oa), (b, ob) = self.edges[edge]
            mine = self.attachment(a, here, oa)
            theirs = self.attachment(b, there, ob)
            self._joint[key] = (
                0.0 if mine is None or theirs is None
                else pair_cost(mine, theirs, self.axes[edge]))
        return self._joint[key]

    def cost(self, choice) -> float:
        # Summed in the same order every time, so a cost read from the
        # cache is the same float as one computed afresh and the
        # rounding in `key` breaks the same ties it always did.
        total = 0.0
        for edge, ((a, _oa), (b, _ob)) in self.edges.items():
            total += self.joint(edge, choice[a], choice[b])
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
    what it leaves.  The fit's own permutation, where :func:`_admit`
    had to add it, is no rotation of the block and so is never shared;
    such a slot is reached by the descent instead.
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
        trial = dict(start)
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


# ======================================================================
#  THE ANGLE ABOUT A BLOCK'S OWN AXIS
# ======================================================================
#
# Everything above this line chooses between placements that are
# *discretely* different, and there is nothing else it could do: a
# node's fit is over-determined and the only freedom left in it is
# which of the block's own rotations was applied.
#
# A two-connected block is the opposite case.  Its fit is Kabsch on
# two vectors, which scipy itself warns is "not uniquely defined": the
# angle about the line through its two connection points is left
# **undetermined** by the fit rather than decided by it, so there is
# no earlier answer here to be faithful to and settling it is not
# overriding anything.  That is why this runs whatever rule was asked
# for, and why the guarantee it has to keep is the other one -- a
# framework of single-point blocks built ``as-found`` must come out
# exactly as it always did.  Faces -- the plane a single-atom point
# presents -- are read only when ``faces`` is asked for, which the
# build does under :data:`CONSISTENT` and nowhere else.  Without them
# it holds structurally: :func:`_turnable` is empty unless a
# block presents a face at one of its two ends, and no shipped block
# does.
#
# Turning about that line is a legal refinement and not a second fit,
# and for one reason worth stating plainly: **both connection points
# are on the line**, so they do not move at all.  The primary RMSD,
# the relaxed cell and every X-to-X coincidence the builder made are
# preserved exactly, and what moves is only the body of the block
# between them.

#: How many times the pairing between two ends is re-solved.
#:
#: The angle is exact once the pairing is fixed and the pairing is
#: exact once the angle is, so the two are taken in turn.  Twice is
#: where it stops: a second round changes the answer only where the
#: first one's turn carried a member past its neighbour's, and it is
#: the round that catches a linker the fit left more than a quarter
#: turn out.
_ROUNDS = 2

#: How many times the whole set of turnable blocks is swept.
#:
#: One sweep is exact wherever no two turnable blocks meet, which is
#: every net whose linkers sit between many-connected nodes: an edge
#: slot's two neighbours are node slots by construction.  Where a
#: *node* is two-connected as well -- Ni3(HITP)2's NiN4H4 is -- two
#: turnable blocks do meet, each sweep is one step of a coordinate
#: descent, and every step is a closed-form minimum for the block it
#: moves.  Four is where the descent is stopped rather than where it
#: is known to have converged, and a block still moving at the fourth
#: is left where the fourth put it.
_SWEEPS = 4

#: A turn smaller than this, in radians, is not made at all.
#:
#: Not a convergence criterion -- the closed form does not converge,
#: it answers.  It is what keeps a block that is *already* settled
#: from being turned by its own rounding error, and the number is
#: measured: Ni3(HITP)2's three NiN4H4 blocks come back wanting
#: 1.5e-08, 6.1e-08 and 4.2e-08 radians, which is the same 1e-05-ish
#: imperfection a block cut from a real crystal has everywhere else
#: in this module and is not a turn.  At 1e-06 the widest attachment
#: there is moves its furthest member by 5e-06 A, which is below the
#: figure a CIF is written to, so nothing that is stopped here could
#: have been seen in the file.
_STILL = 1e-6

#: Below this the two ends have nothing to say about the angle.
_UNDECIDED = 1e-9


def align_edges(framework, log=None, faces: bool = False) -> int:
    """Turn every two-connected block about its own axis until its
    ends face the blocks they meet.  Returns how many were turned.

    The block is rotated in place -- ``info["located_bbs"]`` and the
    framework's own atoms both -- so everything downstream reads the
    settled geometry: :func:`xtal.mof.build.bond_joints` pairs members
    that have been brought together rather than members a quarter turn
    apart, and the CIF is written from it.

    **The cost is the one Phase 5 minimised**, joint by joint:
    :func:`xtal.mof.attach.pair_cost` over the unit laterals the two
    ends present across the joint.  What differs is the lever.  A node
    can only be turned onto one of its own rotations, so its tie is
    discrete and is searched; a two-connected block turns continuously
    about the line through its two points, so its angle is *solved*:

    .. code-block:: text

        phi* = -arg( sum over ends, sum over paired members
                     z_here * conj(z_there) )

    with each member's unit lateral written as a complex number in one
    basis across the axis, the same basis at both ends.  Rotating by
    ``phi`` multiplies every ``z_here`` by ``exp(i phi)``, so the sum
    of squared differences is ``const - 2 Re(exp(i phi) S)`` and is
    least where ``exp(i phi) S`` is real and positive.  No scan, no
    tolerance, and no starting guess -- measured on Ni3(HITP)2 the
    closed form returns 0.000 degrees, which is the angle the crystal
    has.

    A C2-symmetric linker gives two equal minima half a turn apart and
    either is correct; which one comes back is decided by the sum
    above and so is the same on two runs of one build.
    """
    blocks = framework.info["located_bbs"]
    turnable = _turnable(blocks, faces)
    if not turnable:
        return 0
    partner = {}
    for here, there in fused_points(framework.info["topology"], blocks,
                                    framework.info["permutations"]):
        partner[here] = there
        partner[there] = here
    turned: set[int] = set()
    for _sweep in range(_SWEEPS):
        moved = False
        for slot in turnable:
            angle, axis, origin = _axial(blocks, partner, slot,
                                         faces)
            if angle is None or abs(angle) < _STILL:
                continue
            _turn(blocks[slot], axis, origin, angle)
            turned.add(slot)
            moved = True
        if not moved:
            break
    if turned:
        _write_back(framework, blocks, turned)
        _say(log, f"settled {len(turned)} block(s) about their own "
                  f"axis, of {len(turnable)} that could turn")
    return len(turned)


def _turnable(blocks, faces: bool = False) -> list[int]:
    """The slots whose block has two connection points and a face to
    present at one of them.

    Two points and not "is an edge slot": a two-connected *node* has
    exactly the same freedom and exactly the same reason to settle it
    -- Ni3(HITP)2's NiN4H4 sits on a node slot -- and asking the block
    rather than the net is what covers both without naming either.

    Without ``faces``, a block whose every point stands for one atom
    presents nothing, so no angle is better than any other and this is
    empty.  That is the whole of the guarantee for the shipped blocks
    built ``as-found``: not a rule they are exempt from, but a list
    they are not on.  With ``faces`` -- under ``consistent`` -- a ring
    or a carboxylate at either end is a face, and E14 turns until its
    ring lies flat against both carboxylates it meets.
    """
    out = []
    for slot, block in enumerate(blocks):
        if block is None or block.bonds is None:
            continue
        points = np.asarray(block.connection_point_indices, dtype=int)
        if len(points) != 2 or not readable(block):
            continue
        if faces:
            if presents_face(points, block.bonds,
                             block.atoms.get_positions()):
                out.append(slot)
            continue
        members = members_of(points, block.bonds)
        if any(len(found) > 1 for found in members.values()):
            out.append(slot)
    return out


def _axial(blocks, partner, slot, faces: bool = False):
    """``(angle, axis, origin)`` for one block, or three ``None``.

    ``None`` where there is nothing to settle: an end whose partner
    presents no face, a member sitting on the axis -- where a unit
    lateral would be manufactured out of rounding noise -- or two
    connection points on top of each other, which is not an axis.
    """
    block = blocks[slot]
    positions = np.asarray(block.atoms.get_positions(), dtype=float)
    first, second = (int(p) for p in block.connection_point_indices)
    axis = positions[second] - positions[first]
    length = float(np.linalg.norm(axis))
    if length < _UNDECIDED:                         # pragma: no cover
        return None, None, None
    axis = axis / length
    ends = []
    for point in (first, second):
        met = partner.get((slot, point))
        here = _attachment_at(blocks, slot, point, faces)
        there = (None if met is None
                 else _attachment_at(blocks, *met, faces))
        if here is None or there is None:
            continue
        mine = unit_laterals(here, axis)
        theirs = unit_laterals(there, axis)
        if mine is not None and theirs is not None:
            ends.append((mine, theirs))
    if not ends:
        return None, None, None
    return _angle(axis, ends), axis, positions[first]


def _attachment_at(blocks, slot, point, faces: bool = False):
    """The face a placed block presents at one of its points, or
    ``None`` where it presents none.

    In the framework's own frame, because that is where the two ends
    of a joint have to agree -- but only the *offsets* are ever read,
    so it does not matter that two placed blocks need not be in the
    same cell.  The distances between them do, and
    :func:`xtal.mof.build._joint_bonds` takes those at their minimum
    image; an offset inside one block is the same vector wherever the
    block is.

    With ``faces`` a single-atom point presents the plane of its atom
    (:func:`xtal.mof.attach.face_of`); without, only a point standing
    for several atoms presents anything.
    """
    block = blocks[slot]
    if block is None or block.bonds is None or not readable(block):
        return None
    members = members_of(block.connection_point_indices,
                         block.bonds).get(int(point), ())
    positions = np.asarray(block.atoms.get_positions(), dtype=float)
    if len(members) < 2:
        if not faces:
            return None
        return face_of(block.connection_point_indices, block.bonds,
                       positions, point)
    return Attachment(int(point), tuple(int(m) for m in members),
                      positions[list(members)] - positions[point])


def _angle(axis, ends) -> float:
    """The turn about ``axis`` that brings these ends onto the ones
    they meet, in closed form.

    Solved twice, because the closed form is exact only for a fixed
    pairing of one end's members with the other's: the pairing is
    taken at the angle in hand, the angle is then the minimum for that
    pairing, and the second round is where a pairing the first turn
    invalidated is put right.
    """
    across = _across(axis)
    angle = 0.0
    for _round in range(_ROUNDS):
        rotation = _rotation(axis, angle)
        total = 0j
        for here, there in ends:
            rows, cols, _cost = pairing(here @ rotation.T, there)
            total += complex(np.sum(
                _plane(here[rows], across)
                * np.conj(_plane(there[cols], across))))
        if abs(total) < _UNDECIDED:
            # The two ends' frames cancel each other out, which is a
            # linker whose members are symmetric about its axis
            # meeting a node whose are too.  Every angle then costs
            # exactly the same and there is nothing to choose, so the
            # block is left where the fit put it.
            return 0.0
        angle = -float(np.angle(total))
    return angle


def _across(axis):
    """An orthonormal pair across ``axis``, the same for both ends.

    Which pair does not matter and cannot: turning the pair turns
    every complex coordinate on both sides of the product below by the
    same phase, and the product is one conjugated against the other.
    """
    other = (np.array([0.0, 1.0, 0.0]) if abs(float(axis[0])) > 0.9
             else np.array([1.0, 0.0, 0.0]))
    first = np.cross(axis, other)
    first = first / float(np.linalg.norm(first))
    return first, np.cross(axis, first)


def _plane(vectors, across):
    """Vectors across the axis, as complex numbers in that basis."""
    first, second = across
    return vectors @ first + 1j * (vectors @ second)


def _rotation(axis, angle) -> np.ndarray:
    """Rodrigues: the matrix that turns a vector about ``axis``."""
    cross = np.array([[0.0, -axis[2], axis[1]],
                      [axis[2], 0.0, -axis[0]],
                      [-axis[1], axis[0], 0.0]])
    return (np.cos(angle) * np.eye(3) + np.sin(angle) * cross
            + (1.0 - np.cos(angle)) * np.outer(axis, axis))


def _turn(block, axis, origin, angle) -> None:
    """One placed block, turned about the line through its points."""
    rotation = _rotation(axis, angle)
    positions = np.asarray(block.atoms.get_positions(), dtype=float)
    block.atoms.set_positions(
        (positions - origin) @ rotation.T + origin)


def _write_back(framework, blocks, turned) -> None:
    """The turned blocks' atoms, back into the framework's own.

    Over the index range :func:`xtal.mof.build._framework_indices`
    gives that slot -- the one walk, because a private copy of that
    arithmetic here would move the wrong atoms rather than fail to
    find them.  The framework then wraps itself again: it wrapped once
    when it was made (``framework.py:76``), a turned block is back
    outside the cell, and wrapping is idempotent for everything that
    was already in it.
    """
    starts, kept = _framework_indices(blocks)
    positions = np.asarray(framework.atoms.get_positions(),
                           dtype=float)
    for slot in sorted(turned):
        placed = np.asarray(blocks[slot].atoms.get_positions(),
                            dtype=float)
        for local in range(len(placed)):
            index = kept.get(starts[slot] + local)
            if index is not None:
                positions[index] = placed[local]
    framework.atoms.set_positions(positions)
    framework.wrap()


def _say(log, text: str) -> None:
    if log is not None:
        log(text)
