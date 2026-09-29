"""
xtal.build.clearance
====================
How much room a group of atoms has, in a periodic cell.

Two things turn a group of atoms to find it room: the MOF builder, a
linker about its own axis (:func:`xtal.mof.orient.align_edges`), and
Substitute, a group about the bond it hangs off.  Both ask the same
question -- at this angle, how close does the group come to anything
it is not part of? -- and both need the answer to count the group's
own periodic images, because a substituent on a 1x1x1 cell can land
on the copy of itself one cell over.  So it is asked here, once.

**The measure is the closest approach, not a sum.**  A score that adds
up soft repulsions will trade one atom on top of another for many a
little too close, and one atom on top of another is the only thing
worth avoiding.  What counts as enough room is :data:`CLEAR`, and it
is a margin rather than a target: an angle that already has it is
left alone, so a build that was right comes out byte for byte as it
did.
"""

from __future__ import annotations

import itertools

import numpy as np
from scipy.spatial import cKDTree

#: Enough room.  An angle whose closest approach is at least this is
#: not turned away from, whatever a search could find.  Every
#: framework in ``resources/samples`` has its shortest unbonded
#: contact above 1.99 A, and ``acs`` on N457 -- blocks that do not fit
#: that net at all -- is 1.66 A, so a build that is merely strained
#: stays exactly as it was.  Below it, atoms are on top of one another
#: and the angle is searched.
CLEAR = 1.5

#: How close to the best clearance an angle has to come to be taken.
#: Of those, the one nearest the angle something else preferred wins
#: -- the faces for a linker -- so clearance decides first and the
#: preference only breaks its ties.
SLACK = 0.1

#: The sampling of a full turn, in degrees.
STEP = 10.0


def _shifts(matrix) -> np.ndarray:
    """The 27 lattice translations of a cell and its neighbours, the
    zero one first."""
    offsets = sorted(itertools.product((-1, 0, 1), repeat=3),
                     key=lambda o: (o != (0, 0, 0), o))
    return np.asarray(offsets, dtype=float) @ np.asarray(matrix)


class Surroundings:
    """Everything a moving group is measured against, built once.

    ``environment`` is every atom the group must keep clear of, in
    cartesian coordinates of the same frame; the group's own atoms are
    *not* in it, because they move with it.  Their images one cell over
    are measured separately, from wherever the group has been turned
    to -- see :meth:`clearance`.

    Every image of the environment in the 27 cells around the origin
    is put in one KD-tree.  That is exact for any group smaller than
    the cell, which is every linker and every substituent: a
    minimum-image search would be cheaper and is not exact in a
    skewed cell.
    """

    def __init__(self, environment, matrix, centre=None,
                 reach: float | None = None):
        self.matrix = np.asarray(matrix, dtype=float)
        self.shifts = _shifts(self.matrix)
        self._lengths = np.linalg.norm(self.shifts, axis=1)
        points = np.asarray(environment, dtype=float).reshape(-1, 3)
        images = (points[None, :, :]
                  + self.shifts[:, None, :]).reshape(-1, 3)
        if centre is not None and reach is not None and len(images):
            # Only what the group could come near, turned any way at
            # all: a linker in a 2x2x2 MOF-5 is measured against 150
            # atoms rather than 27 copies of 3400.
            near = np.linalg.norm(images - np.asarray(centre, float),
                                  axis=1) <= reach
            images = images[near]
        self._tree = cKDTree(images) if len(images) else None

    def clearance(self, group) -> float:
        """The closest any atom of ``group`` comes to the environment,
        or to an image of the group itself in another cell.  ``inf``
        when there is nothing to come close to."""
        group = np.asarray(group, dtype=float).reshape(-1, 3)
        if not len(group):
            return float("inf")
        closest = float("inf")
        if self._tree is not None:
            distances, _ = self._tree.query(group, k=1)
            closest = float(distances.min())
        # An image one cell over can only be closer than what was found
        # if the cell is shorter than that plus the group's own width --
        # never, in a framework, and skipping the rest is exact.  It was
        # 26 queries on every call, and most of a one-per-ring plan.
        width = float(np.linalg.norm(np.ptp(group, axis=0)))
        own = None
        for shift, length in zip(self.shifts[1:], self._lengths[1:],
                                 strict=True):
            if length - width >= closest:
                continue
            if own is None:
                own = cKDTree(group)
            distances, _ = own.query(group + shift, k=1)
            closest = min(closest, float(distances.min()))
        return closest


def turn(points, axis, origin, angle) -> np.ndarray:
    """``points`` turned by ``angle`` radians about the line through
    ``origin`` along the unit vector ``axis`` (Rodrigues)."""
    axis = np.asarray(axis, dtype=float)
    cross = np.array([[0.0, -axis[2], axis[1]],
                      [axis[2], 0.0, -axis[0]],
                      [-axis[1], axis[0], 0.0]])
    rotation = (np.cos(angle) * np.eye(3) + np.sin(angle) * cross
                + (1.0 - np.cos(angle)) * np.outer(axis, axis))
    origin = np.asarray(origin, dtype=float)
    return (np.asarray(points, dtype=float) - origin) @ rotation.T \
        + origin


def clearest_angle(surroundings: Surroundings, group, axis, origin,
                   preferred: float = 0.0,
                   keep_clear: bool = True) -> tuple[float, float]:
    """``(angle, clearance)``: the turn about the axis that gives the
    group room, and how much room it gives.

    ``preferred`` is the angle something else chose -- the closed form
    for a linker's faces, nothing at all for a substituent.  If it
    already has :data:`CLEAR`, it is the answer and nothing is
    searched: that is the guarantee that a build which was right is
    not turned.  Otherwise a full turn is sampled every :data:`STEP`
    degrees from ``preferred``, every angle within :data:`SLACK` of the
    best clearance is admissible, and of those the one nearest
    ``preferred`` is taken -- the preference breaking clearance's ties,
    never overruling it.

    ``keep_clear=False`` searches whatever the preferred angle has:
    a substituent has nothing to be faithful to, and the angle with
    the most room is simply the answer (:mod:`xtal.build.substitute`).
    """
    at = surroundings.clearance(turn(group, axis, origin, preferred))
    if keep_clear and at >= CLEAR:
        return preferred, at
    # Every STEP from the preferred angle, and not from the block's
    # current one: where a linker happens to sit is the fit's rounding
    # (see `xtal.mof.orient.as_drawn`), and a grid anchored there
    # picked a different clear angle on a different BLAS.
    angles = [preferred + np.radians(STEP * k)
              for k in range(int(round(360 / STEP)))]
    scored = [(surroundings.clearance(turn(group, axis, origin, a)), a)
              for a in angles]
    best = max(score for score, _a in scored)

    def away(angle: float) -> float:
        return abs(float(np.angle(np.exp(1j * (angle - preferred)))))

    room, angle = min(((score, a) for score, a in scored
                       if score >= best - SLACK),
                      key=lambda pair: away(pair[1]))
    return angle, room
