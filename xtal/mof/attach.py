"""
xtal.mof.attach
===============
What one connection point stands for.

A connection point marks where the next building block goes.  Until
now it stood for exactly one atom -- the one it hangs off -- and the
bond it carried into the framework was that atom's.  A great many real
nodes do not join that way: MFU-4l's Zn5Cl4 kernel meets each
triazolate through *two* ring atoms, and Ni3(HITP)2's nickel meets
each imine through two nitrogens.  Written as one point per atom those
blocks have twice the coordination number they should and fit no net
in the catalogue; written as one point per *attachment* they fit
``pcu`` and ``hcb`` exactly.

**An attachment is one ``X`` plus the body atoms bonded to it.**  Its
denticity is the number of distinct partners in the block's bond
block, and nothing new enters the ``.xyz`` format to say so -- the
bonds were always written, and PORMAKE has always read them.

Three numbers come out of an attachment and they are separable:

* the **axis**, from the members' centroid to the point, which is
  where the next block goes and is all a monodentate attachment has;
* the **lateral**, each member's offset from the axis, which is the
  attachment's own frame -- the triazole plane, the chelate plane --
  and exists only above denticity one;
* the **span**, how far apart the members are, which is the only thing
  here that says a selection was a mistake.

Laterals are compared as **directions and never as lengths**.  Two
ends of one joint can have quite different spans -- MFU-4l's node
members are 1.405 A apart and its linker's are 2.861 -- so comparing
the offsets themselves leaves a floor of 0.53 A^2 that is the span
difference and nothing else.  Normalised first, the crystal's own
orientation scores exactly 0.000000 and a 90-degree twist exactly
2.000000, which is the whole of what the tie-break is about.

Numpy at import and nothing else: this is the concept, and both the
builder and the block writer are allowed to depend on it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: How far apart the atoms of one attachment may be.
#:
#: Measured rather than chosen.  The four blocks this work was built
#: for span 1.405, 1.408, 2.558 and 2.861 A; the two shipped blocks
#: that read as polydentate (both upstream data errors) span 0.971 and
#: 1.288.  What the limit exists to catch is a person marking two
#: atoms at opposite ends of a molecule, and half the 867 shipped
#: blocks are more than 10.33 A wide -- 821 of them wider than this.
#: So 5.0 clears the widest real attachment by three quarters of its
#: own width, leaves room for a tetradentate pocket whose diagonal is
#: around 4 A, and still catches the mis-click in 95 % of the database.
MAX_ATTACHMENT_SPAN = 5.0

#: How far back along its bond a face's two virtual members sit, as a
#: fraction of their reach: enough for ``Attachment.axis`` to have a
#: direction, and a millionth of a radian of lean at worst.
_HAIR = 1e-6


@dataclass(frozen=True)
class Attachment:
    """One connection point and the atoms it hangs off.

    ``point`` and ``members`` are indices into whatever array the
    positions came from -- a block's, or a placed block's in the
    framework frame -- and ``offsets`` is ``(n, 3)``, each member's
    position minus the point's.  Storing the offsets rather than the
    positions is what lets the same object describe an attachment in
    its block and the same attachment after placement, which is what
    :func:`pair_cost` compares across a joint.
    """

    point: int
    members: tuple[int, ...]
    offsets: np.ndarray

    @property
    def denticity(self) -> int:
        return len(self.members)

    @property
    def is_polydentate(self) -> bool:
        return len(self.members) > 1

    @property
    def span(self) -> float:
        """The widest gap between two members, 0.0 for one member."""
        if len(self.members) < 2:
            return 0.0
        d = self.offsets[:, None, :] - self.offsets[None, :, :]
        return float(np.linalg.norm(d, axis=-1).max())

    @property
    def axis(self) -> np.ndarray:
        """Unit vector from the members' centroid to the point.

        Where the next block goes.  With one member this is the bond
        direction the monodentate path has always used, to the bit.
        """
        middle = self.offsets.mean(axis=0)
        length = float(np.linalg.norm(middle))
        if length < 1e-9:
            raise ValueError("this connection point sits on its "
                             "members' centroid, so it has no "
                             "direction")
        return -middle / length


def members_of(connections, bonds) -> dict[int, tuple[int, ...]]:
    """Connection point -> the *distinct* atoms it hangs off.

    The one rule, in one place, because it is read from two different
    objects: :class:`xtal.mof.catalog.BuildingBlock`, which is what
    the picker and the writer see, and PORMAKE's own
    ``BuildingBlock``, which is what a build is made out of.  Two
    implementations of it would drift, and the direction they would
    drift in is a block being read as bidentate at one end of the
    application and monodentate at the other.

    Distinct, and never the number of bond records: 54 of the 4256
    shipped connection points carry more than one record and 52 of
    those name the same partner twice, across 26 blocks.

    A bond onto another connection point is not a member -- a point
    stands for the atoms of the block, and two of them standing for
    each other describe a joint to nowhere.  A point with no record at
    all maps to an empty tuple rather than being left out, so a caller
    can tell "this block says nothing about its bonds" from "this
    point has none".
    """
    marked = {int(c) for c in connections}
    found: dict[int, set[int]] = {c: set() for c in marked}
    for record in () if bonds is None else bonds:
        i, j = int(record[0]), int(record[1])
        if i in marked and j not in marked:
            found[i].add(j)
        elif j in marked and i not in marked:
            found[j].add(i)
    return {c: tuple(sorted(found[c])) for c in sorted(marked)}


def face_of(connections, bonds, positions, point) -> Attachment | None:
    """The face a single-atom connection point presents, or ``None``.

    Where the atom a point hangs off has exactly **two** other
    neighbours in the block, the plane of that atom and those two is
    what meets the next block: a carboxylate on a Zn4O node, a ring on
    a linker.  A planar linker cannot lie flat against two
    carboxylates turned a quarter turn apart, which is the whole
    reason MOF-5's clusters alternate -- 0 degrees across each of its
    24 linkers in the crystal, 90 across all 24 in a build that
    ignored this.

    Presented as a **virtual bidentate**: two members at +-*w*, *w* in
    that plane and across the atom-to-point bond, so that
    :func:`pair_cost`, :func:`pairing` and :func:`unit_laterals` read
    a face exactly as they read a chelate, and ``axis`` still points
    from the atom towards the point.  ``members`` names the two
    neighbours, which are the atoms the plane was taken from; nothing
    that bonds ever reads a face, so they are never taken for atoms
    that join.

    Where the point was written plays no part in the plane, and it
    must not: 2045 of the 3899 faces the shipped blocks present have
    their ``X`` more than 0.1 off it -- E102's is 0.65.  A point with
    one other neighbour is linear and has no plane; one with three or
    more is a free rotor, or a metal, with no preferred angle.  Of the
    4215 shipped points 3899 present a face, 67 are linear and 234
    have more neighbours.
    """
    positions = np.asarray(positions, dtype=float)
    point = int(point)
    members = members_of(connections, bonds).get(point, ())
    if len(members) != 1:
        return None
    atom = members[0]
    marked = {int(c) for c in connections}
    around = set()
    for record in () if bonds is None else bonds:
        i, j = int(record[0]), int(record[1])
        if i == atom and j not in marked:
            around.add(j)
        elif j == atom and i not in marked:
            around.add(i)
    if len(around) != 2:
        return None
    a, b = sorted(around)
    normal = np.cross(positions[a] - positions[atom],
                      positions[b] - positions[atom])
    bond = positions[point] - positions[atom]
    across = np.cross(normal, bond)
    length = float(np.linalg.norm(across))
    if length < 1e-9:
        return None
    reach = 0.5 * float(np.linalg.norm(positions[a] - positions[b]))
    across *= reach / length
    # +-w and nothing else, bar a hair back along the bond so that
    # `axis` still says which way the point faces.  The atom-to-point
    # offset itself must not be in here: with the X off the plane it
    # has a part across the joint that survives projection, and the
    # face would lean with the X.
    back = -bond / float(np.linalg.norm(bond)) * reach * _HAIR
    return Attachment(point, (a, b),
                      np.array([back + across, back - across]))


def presents_face(connections, bonds, positions) -> bool:
    """Whether any connection point of a block has a frame to agree
    about: it stands for several atoms, or its one atom presents a
    face (:func:`face_of`)."""
    for point, members in members_of(connections, bonds).items():
        if len(members) > 1:
            return True
        if face_of(connections, bonds, positions, point) is not None:
            return True
    return False


def attachments_of(block) -> list[Attachment]:
    """Every attachment of a catalogue :class:`BuildingBlock`.

    Only the points whose members are known: a block written with no
    bond block says nothing about which atom a connection point hangs
    off, and guessing the nearest one is how a block gets built into a
    framework along a direction nobody wrote down.  Such a block has
    no attachments here and takes the path it always took.
    """
    positions = np.asarray(block.positions, dtype=float)
    found = []
    for point, members in sorted(block.members.items()):
        if not members:
            continue
        found.append(Attachment(
            int(point), tuple(int(m) for m in members),
            positions[list(members)] - positions[point]))
    return found


def lateral(attachment: Attachment, axis=None) -> np.ndarray:
    """Each member's offset from the point, across ``axis``.

    The component along the axis is the attachment's reach and is the
    same for both ends of a joint by construction; what is left is the
    frame the attachment presents, and is what two ends have to agree
    on for their members to end up bonded to each other.
    """
    axis = attachment.axis if axis is None else _unit(axis)
    return attachment.offsets - np.outer(attachment.offsets @ axis,
                                         axis)


def pair_cost(a: Attachment, b: Attachment, axis) -> float:
    """How badly two ends of a joint disagree about their frame.

    The mean squared difference of the **unit** laterals under the
    best pairing of one end's members with the other's -- rectangular,
    because denticity may differ across a joint and a bidentate end
    may meet a tridentate one.

    Zero when either end is monodentate: a single member has no
    lateral to disagree about, so there is no twist to measure and no
    orientation to prefer.  That is why a catalogue of single-point
    blocks reaches none of this.
    """
    if not (a.is_polydentate and b.is_polydentate):
        return 0.0
    ua = unit_laterals(a, axis)
    ub = unit_laterals(b, axis)
    if ua is None or ub is None:
        return 0.0
    rows, cols, cost = pairing(ua, ub)
    return float(cost[rows, cols].mean())


def unit_laterals(attachment: Attachment, axis):
    """The frame an attachment presents across ``axis``, or ``None``.

    The laterals normalised, which is the whole of what two ends of a
    joint have to agree about: their reach along the axis is the same
    by construction and their spans need not be -- MFU-4l's node
    members sit 1.405 A apart and its linker's 2.861 -- so comparing
    the raw offsets leaves a floor that is the span difference and
    nothing to do with orientation.

    One function because two callers need exactly this and for the
    same reason: :func:`pair_cost`, which says how badly two ends
    disagree, and :func:`xtal.mof.orient.align_edges`, which turns one
    of them until they do not.
    """
    return _directions(lateral(attachment, axis))


def pairing(here: np.ndarray, there: np.ndarray):
    """Which of one end's laterals answers which of the other's.

    ``(rows, cols, cost)`` from a **rectangular** assignment on the
    squared difference, because denticity may differ across a joint
    and a bidentate end may meet a tridentate one.  The cost matrix
    comes back with them: what it is minimised over and what its value
    is are the same numbers, and the caller that wants the angle needs
    the pairing while the caller that wants the cost needs the sum.
    """
    # Imported here and not above: this module is on the path
    # `xtal.mof.block` takes, which `xtal.build.chem` takes in turn,
    # and that one is deliberately cheap to import.
    from scipy.optimize import linear_sum_assignment

    cost = np.sum((here[:, None, :] - there[None, :, :]) ** 2, axis=-1)
    rows, cols = linear_sum_assignment(cost)
    return rows, cols, cost


def _directions(vectors: np.ndarray):
    """Unit laterals, or ``None`` if any of them has no direction.

    A member sitting exactly on the axis has a lateral of zero length,
    and normalising it would manufacture a direction out of rounding
    noise -- which, being compared against a real one, would decide an
    orientation.  Better to say the frame is undefined and let the
    fit alone choose.
    """
    lengths = np.linalg.norm(vectors, axis=1)
    if np.any(lengths < 1e-9):
        return None
    return vectors / lengths[:, None]


def _unit(vector) -> np.ndarray:
    vector = np.asarray(vector, dtype=float).reshape(3)
    length = float(np.linalg.norm(vector))
    if length < 1e-9:
        raise ValueError("an attachment axis needs a direction")
    return vector / length
