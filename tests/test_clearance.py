"""How much room a group of atoms has, and which turn gives it room.

Headless and fast: :mod:`xtal.build.clearance` is geometry, and the
builds that use it are in ``test_mof_orientation.py``.  What breaks if
these regress is a linker turned away from an angle that was fine --
every clean framework changing -- or a group measured without its own
images, landing on the copy of itself one cell over.
"""

import numpy as np
import pytest

from xtal.build.clearance import (
    CLEAR,
    Surroundings,
    clearest_angle,
    turn,
)

BOX = np.eye(3) * 20.0
AXIS = np.array([0.0, 0.0, 1.0])
ORIGIN = np.array([10.0, 10.0, 10.0])
#: One atom 1.5 A off the axis, pointing along +x at angle zero.
GROUP = np.array([[11.5, 10.0, 10.0]])


def test_an_angle_with_room_is_never_turned_away_from():
    """The guarantee a clean build rests on: the preferred angle is
    kept whenever it is clear, even where another angle has more."""
    far = Surroundings([[10.0, 13.2, 10.0]], BOX)

    angle, room = clearest_angle(far, GROUP, AXIS, ORIGIN, preferred=0.0)

    assert angle == 0.0
    assert room >= CLEAR


def test_a_blocked_angle_is_turned_to_the_clear_one_nearest_it():
    """Room decides first and the preference only breaks its ties: an
    atom sitting on the preferred angle sends the group to the nearest
    clear angle, not the far side of the turn."""
    blocker = Surroundings([[11.5, 10.0, 10.0]], BOX)

    angle, room = clearest_angle(blocker, GROUP, AXIS, ORIGIN,
                                 preferred=np.radians(10))
    turned = turn(GROUP, AXIS, ORIGIN, angle)

    assert room >= CLEAR
    assert np.linalg.norm(turned[0] - [11.5, 10.0, 10.0]) == \
        pytest.approx(room)
    assert abs(np.degrees(angle)) > 10


def test_faces_break_the_ties_clearance_leaves():
    """Two blockers leave two clear directions half a turn apart; the
    one nearer the preferred angle wins, whichever side it is on."""
    blockers = Surroundings([[10.0, 11.5, 10.0], [10.0, 8.5, 10.0]], BOX)

    near_zero, _ = clearest_angle(blockers, GROUP, AXIS, ORIGIN,
                                  preferred=np.radians(80))
    near_half, _ = clearest_angle(blockers, GROUP, AXIS, ORIGIN,
                                  preferred=np.radians(100))

    assert np.degrees(near_zero) % 360 == pytest.approx(0, abs=1e-6)
    assert np.degrees(near_half) % 360 == pytest.approx(180, abs=1e-6)


def test_a_group_is_measured_against_its_own_image_in_the_next_cell():
    """A substituent on a small cell can land on the copy of itself one
    cell over, and nothing else in the environment would say so."""
    small = np.eye(3) * 4.0
    pair = np.array([[0.2, 0.0, 0.0], [3.9, 0.0, 0.0]])

    assert Surroundings([], small).clearance(pair) == pytest.approx(0.3)


def test_only_what_the_group_could_reach_is_measured():
    """The reach is a filter, never a different answer: an atom beyond
    it could not have been the closest at any angle."""
    atoms = [[10.0, 13.2, 10.0], [18.0, 18.0, 18.0]]
    whole = Surroundings(atoms, BOX).clearance(GROUP)
    near = Surroundings(atoms, BOX, centre=ORIGIN,
                        reach=1.5 + CLEAR + 2.0).clearance(GROUP)

    assert near == pytest.approx(whole)
