"""Which strains a relaxation may still use.

`docs/PLAN.md` promised "fix a lattice parameter" among the force
field's constraints and it was the one item on that list never built.
The volume is here for the same machinery's sake and is the more
useful of the two: a profile taken at a frozen cell *shape* depends on
which shape was frozen, so holding the volume while the shape relaxes
is what the flexible-framework literature actually scans.
"""

from __future__ import annotations

import numpy as np
import pytest

from xtal.core.lattice import Lattice
from xtal.ff import optimize
from xtal.ff.api import CalculatorError
from xtal.ff.optimize import CellFreedom
from xtal.ff.registry import ENGINES


def _relaxed(structure, freedom, steps=40):
    return optimize.run(ENGINES.build("uff", structure), structure,
                        method="lbfgs", max_steps=steps,
                        relax_cell=True, freedom=freedom)


def test_a_free_cell_relaxes_exactly_as_it_did_before(quartz):
    """The regression that matters most: the default path must not
    notice any of this exists."""
    plain = optimize.run(ENGINES.build("uff", quartz), quartz,
                         method="lbfgs", max_steps=20,
                         relax_cell=True)
    masked = _relaxed(quartz, CellFreedom.free(), steps=20)
    assert plain.energy == pytest.approx(masked.energy, rel=1e-12)
    assert np.allclose(plain.matrix, masked.matrix, atol=1e-12)


def test_a_constant_volume_relaxation_keeps_the_volume(quartz):
    """And still moves the shape, or it has held the cell rigid and
    proved nothing."""
    before = quartz.lattice.volume
    result = _relaxed(quartz, CellFreedom.constant_volume())
    after = Lattice(result.matrix)
    assert after.volume == pytest.approx(before, rel=1e-4)
    assert after.parameters[0] != pytest.approx(
        quartz.lattice.parameters[0], rel=1e-5)


def test_fixing_a_stops_it_moving_while_c_relaxes(quartz):
    """Both halves.  A mask that froze the whole cell would pass the
    first assertion on its own."""
    before = quartz.lattice.parameters
    after = Lattice(_relaxed(quartz, CellFreedom.fixing(("a",))
                             ).matrix).parameters
    assert after[0] == pytest.approx(before[0], rel=1e-6)
    assert after[2] != pytest.approx(before[2], rel=1e-4)


def test_fixing_c_stops_it_moving_while_a_relaxes(quartz):
    before = quartz.lattice.parameters
    after = Lattice(_relaxed(quartz, CellFreedom.fixing(("c",))
                             ).matrix).parameters
    assert after[2] == pytest.approx(before[2], rel=1e-6)
    assert after[0] != pytest.approx(before[0], rel=1e-4)


def test_a_tied_parameter_is_held_with_the_one_it_follows(quartz):
    """b = a in a trigonal group, so holding a holds b -- not because
    anything checks, but because the group's own projector has no
    strain that would part them."""
    after = Lattice(_relaxed(quartz, CellFreedom.fixing(("a",))
                             ).matrix).parameters
    assert after[1] == pytest.approx(after[0], rel=1e-9)


def test_the_angles_of_a_trigonal_cell_are_left_alone(quartz):
    """The mask composes with the space group rather than replacing
    it: gamma is 120 degrees by symmetry and stays there whatever is
    held."""
    after = Lattice(_relaxed(quartz, CellFreedom.constant_volume()
                             ).matrix).parameters
    assert after[3] == pytest.approx(90.0, abs=1e-6)
    assert after[5] == pytest.approx(120.0, abs=1e-6)


def test_a_cubic_cell_with_a_fixed_has_nothing_left_to_relax(halite):
    """Fm-3m leaves one free strain and holding a takes it.

    Refused with a sentence rather than relaxed into a silent no-op,
    because "the cell did not move" and "the cell was not allowed to
    move" look identical in a report.
    """
    with pytest.raises(CalculatorError, match="nothing to relax"):
        optimize.SymmetryDOF(halite, relax_cell=True,
                             freedom=CellFreedom.fixing(("a",)))


def test_a_cubic_cell_may_still_be_held_at_constant_volume(halite):
    """The same refusal, reached the other way: a cubic group's one
    strain is the isotropic one, which is exactly the one a constant
    volume forbids."""
    with pytest.raises(CalculatorError, match="nothing to relax"):
        optimize.SymmetryDOF(halite, relax_cell=True,
                             freedom=CellFreedom.constant_volume())


def test_the_residual_stress_ignores_a_strain_the_mask_forbids(
        quartz):
    """Otherwise no held run converges: a stress no permitted strain
    can relieve would sit in the criterion for ever."""
    held = optimize.SymmetryDOF(
        quartz, relax_cell=True,
        freedom=CellFreedom.constant_volume())
    pressure = np.eye(3) * 1.0
    assert held.residual_stress(pressure) == pytest.approx(0.0,
                                                           abs=1e-9)
    free = optimize.SymmetryDOF(quartz, relax_cell=True)
    assert free.residual_stress(pressure) > 0.1


def test_a_mask_is_a_projector(quartz):
    """Applied twice it must do no more than applied once, or the
    strain the optimiser reads back depends on how many times it was
    asked for."""
    dof = optimize.SymmetryDOF(
        quartz, relax_cell=True,
        freedom=CellFreedom.fixing(("c",)))
    arbitrary = np.array([[0.01, 0.002, 0.003],
                          [0.002, -0.004, 0.001],
                          [0.003, 0.001, 0.007]])
    once = dof.project_strain(arbitrary)
    assert np.allclose(dof.project_strain(once), once, atol=1e-12)


def test_what_holding_b_takes_away_is_perpendicular_to_what_it_leaves(
        quartz):
    """The shears are scaled by root two so that the ordinary dot
    product is the tensor one, and the mask an *orthogonal*
    projector in it.  Unscaled, the mask still projects onto the
    right subspace and still passes the test above, but along the
    wrong direction: the part of a stress it throws away is no longer
    perpendicular to the strains it keeps, so a held relaxation walks
    downhill in the wrong direction.

    Only a held quantity whose derivative mixes a stretch with a
    shear can tell the two apart, and no cell of higher symmetry
    offers one -- which is why every other test here passed without
    the root two.  *b* of a hexagonal cell in P1 lies at 120 degrees
    to x, so it is one.  Measured: 1e-14 scaled, 6.2 unscaled."""
    from xtal.core.symmetry import reduce_to_p1

    dof = optimize.SymmetryDOF(
        reduce_to_p1(quartz), relax_cell=True,
        freedom=CellFreedom.fixing(("b",)))
    rng = np.random.default_rng(0)

    def symmetric():
        m = rng.normal(size=(3, 3))
        return m + m.T

    for _ in range(3):
        strain = symmetric()
        rejected = strain - dof.project_strain(strain)
        for _ in range(3):
            kept = dof.project_strain(symmetric())
            assert np.trace(rejected @ kept) == pytest.approx(
                0.0, abs=1e-9)


def test_a_fixed_cell_ignores_the_mask_entirely(quartz):
    """With no cell variables there is nothing to hold back, and
    building the mask would refuse cases that are perfectly fine."""
    dof = optimize.SymmetryDOF(
        quartz, freedom=CellFreedom.fixing(("a", "c")))
    assert dof.strain_mask is None


def test_an_unknown_cell_quantity_is_refused_by_name():
    with pytest.raises(ValueError, match="volume"):
        CellFreedom.fixing(("d",))


def test_the_freedom_says_what_it_is_holding():
    assert "freely" in CellFreedom.free().describe()
    assert "volume" in CellFreedom.constant_volume().describe()
    assert "a, c" in CellFreedom.fixing(("a", "c")).describe()
