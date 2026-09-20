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
    ua = _directions(lateral(a, axis))
    ub = _directions(lateral(b, axis))
    if ua is None or ub is None:
        return 0.0
    # Imported here and not above: this module is on the path
    # `xtal.mof.block` takes, which `xtal.build.chem` takes in turn,
    # and that one is deliberately cheap to import.
    from scipy.optimize import linear_sum_assignment

    cost = np.sum((ua[:, None, :] - ub[None, :, :]) ** 2, axis=-1)
    rows, cols = linear_sum_assignment(cost)
    return float(cost[rows, cols].mean())


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
