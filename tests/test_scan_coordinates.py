"""The coordinates a relaxed scan can hold.

The gradients are the part everything else rests on: a wrong
derivative does not crash, it converges the constrained optimiser onto
the wrong manifold and reports the energy there with confidence.  So
every kind is differenced against central differences, on every atom,
on real structures rather than on one contrived quadruple.
"""

from __future__ import annotations

import numpy as np
import pytest

from xtal.core import measure, p1
from xtal.ff import coordinates as co


def _numeric(coordinate, positions, matrix, step=1e-6):
    """Central differences of the value, minding the torsion's cut.

    A dihedral reported in ``(-180, 180]`` jumps by a full turn when a
    difference straddles 180 degrees, which is an artefact of how the
    number is written down and not of the geometry.  Unwrapping each
    sample onto the branch the centre is on is what makes the
    comparison a test of the derivative rather than of ``arctan2``.
    """
    centre = coordinate.value(positions, matrix)

    def sample(moved):
        value = coordinate.value(moved, matrix)
        if coordinate.units == "deg":
            value -= 360.0 * round((value - centre) / 360.0)
        return value

    out = np.zeros_like(positions)
    for atom in coordinate.atoms:
        for axis in range(3):
            moved = positions.copy()
            moved[atom, axis] += step
            high = sample(moved)
            moved[atom, axis] -= 2.0 * step
            low = sample(moved)
            out[atom, axis] = (high - low) / (2.0 * step)
    return out


def _cell_of(structure):
    cell = p1.expand(structure)
    matrix = structure.lattice.matrix
    return cell, matrix, cell.frac @ matrix


CASES = [
    ("distance", [(0,), (1,)]),
    ("distance", [(0, 1, 2), (3, 4, 5)]),
    ("angle", [(0,), (1,), (2,)]),
    ("angle", [(0, 1), (2, 3), (4, 5)]),
    ("torsion", [(0,), (1,), (2,), (3,)]),
    ("torsion", [(0, 1), (2, 3), (4, 5), (6, 7)]),
    ("plane angle", [(3, 4, 5), (6, 7, 8)]),
]


@pytest.mark.parametrize("kind,groups", CASES)
def test_every_coordinate_gradient_matches_central_differences(
        dry_ice, kind, groups):
    """The test the whole feature rests on.

    If this regresses, a scan still runs and still draws a landscape;
    the landscape is simply of the wrong function.
    """
    cell, matrix, positions = _cell_of(dry_ice)
    coordinate = co.internal(dry_ice, cell, kind, groups)
    analytic = coordinate.gradient(positions, matrix)
    numeric = _numeric(coordinate, positions, matrix)
    scale = max(float(np.abs(numeric).max()), 1e-9)
    assert np.abs(analytic - numeric).max() / scale < 1e-5


@pytest.mark.parametrize("kind,groups", CASES)
def test_every_coordinate_gradient_survives_a_non_orthogonal_cell(
        quartz, kind, groups):
    """Gamma is 120 degrees here.  A derivative taken in fractional
    coordinates by mistake is right in a cubic cell and wrong in this
    one."""
    cell, matrix, positions = _cell_of(quartz)
    coordinate = co.internal(quartz, cell, kind, groups)
    analytic = coordinate.gradient(positions, matrix)
    numeric = _numeric(coordinate, positions, matrix)
    scale = max(float(np.abs(numeric).max()), 1e-9)
    assert np.abs(analytic - numeric).max() / scale < 1e-5


def test_a_one_atom_anchor_is_the_atom_itself(dry_ice):
    """The degenerate case is not a special case: a group of one has
    to be exactly the atom, or every distance in the app is off by
    whatever a one-atom centroid rounds to."""
    cell, matrix, positions = _cell_of(dry_ice)
    anchor = co.resolve(dry_ice, cell, [(5,)])[0]
    assert anchor.is_atom
    assert np.allclose(anchor.position(positions, matrix),
                       positions[5])


def test_a_many_atom_anchor_follows_its_atoms(dry_ice):
    """The live-centroid contract.

    A snapshot centroid -- which is what a placed dummy atom is --
    passes every other test in this file and fails this one, because
    it does not move when its atoms do.
    """
    cell, matrix, positions = _cell_of(dry_ice)
    coordinate = co.internal(dry_ice, cell, "distance",
                             [(0, 1, 2), (3, 4, 5)])
    before = coordinate.value(positions, matrix)
    moved = positions.copy()
    moved[0] += np.array([0.3, 0.0, 0.0])
    assert coordinate.value(moved, matrix) != pytest.approx(before)


def test_an_anchor_gathers_its_atoms_across_the_cell_boundary(
        dry_ice):
    """The middle of a group that straddles the boundary is *in* the
    group, not in the middle of the box.

    This is why the images are resolved through the minimum-image
    rule rather than by averaging wrapped coordinates.
    """
    cell, matrix, positions = _cell_of(dry_ice)
    atoms = tuple(int(a) for a in np.argsort(cell.frac[:, 0])[:2]) + \
        tuple(int(a) for a in np.argsort(cell.frac[:, 0])[-2:])
    anchor = co.resolve(dry_ice, cell, [atoms])[0]
    ours = anchor.position(positions, matrix)
    theirs = measure.centroid(cell, dry_ice.lattice, atoms)
    assert np.allclose(ours, theirs, atol=1e-9)


def test_an_anchor_holds_the_image_it_chose(dry_ice):
    """The images are chosen once and then kept.

    Re-deciding them every call is right for a number in a panel and
    fatal for a constraint: an atom drifting past the half-cell would
    step the coordinate by a lattice vector, and no optimiser can
    descend a function with a jump in it.
    """
    cell, matrix, positions = _cell_of(dry_ice)
    coordinate = co.internal(dry_ice, cell, "distance", [(0,), (7,)])
    values = []
    for shift in np.linspace(0.0, 1.0, 21):
        moved = positions.copy()
        moved[7] = moved[7] + shift * matrix[0]
        values.append(coordinate.value(moved, matrix))
    steps = np.abs(np.diff(values))
    assert steps.max() < 0.5      # smooth; a re-decided image jumps


def test_the_values_agree_with_the_measure_panel(dry_ice):
    """A scan holds the number the Measure panel shows, or the two
    tools are describing different crystals."""
    cell, matrix, positions = _cell_of(dry_ice)
    lattice = dry_ice.lattice
    assert co.internal(dry_ice, cell, "distance", [(0,), (1,)]).value(
        positions, matrix) == pytest.approx(
            measure.distance(cell, lattice, 0, 1), abs=1e-9)
    assert co.internal(dry_ice, cell, "angle",
                       [(0,), (1,), (2,)]).value(
        positions, matrix) == pytest.approx(
            measure.angle(cell, lattice, 0, 1, 2), abs=1e-9)
    # Folded onto one branch: a dihedral of +180 and one of -180 are
    # the same dihedral, and which sign arctan2 hands back for an
    # exactly planar arrangement is a question about the sign of zero.
    ours = co.internal(dry_ice, cell, "torsion",
                       [(0,), (1,), (2,), (3,)]).value(positions, matrix)
    theirs = measure.torsion(cell, lattice, 0, 1, 2, 3)
    assert abs(ours - theirs) % 360.0 == pytest.approx(0.0, abs=1e-9)


def test_a_dummy_atom_is_refused_as_an_anchor(dry_ice):
    """A marker feels no force from any engine, so a coordinate held
    to one would be satisfied by sliding the marker -- a flat profile
    that looks like a result.  The message has to name the way
    through: hand in the atoms it marks."""
    from xtal.core.structure import Site

    structure = dry_ice.copy()
    structure.sites.append(Site("X", [0.4, 0.4, 0.4], label="X1"))
    cell = p1.expand(structure)
    marker = int(np.flatnonzero(
        np.array(cell.elements) == "X")[0])
    with pytest.raises(co.CoordinateError, match="marker"):
        co.internal(structure, cell, "distance", [(0,), (marker,)])


def test_a_plane_needs_three_atoms(dry_ice):
    """Two atoms do not determine a plane, and being handed an
    arbitrary one is worse than being refused."""
    cell = p1.expand(dry_ice)
    with pytest.raises(co.CoordinateError, match="three"):
        co.internal(dry_ice, cell, "plane angle", [(0, 1), (2, 3, 4)])


def test_a_coordinate_refuses_the_wrong_number_of_anchors(dry_ice):
    """So that no caller has to remember how many anchors a torsion
    takes."""
    cell = p1.expand(dry_ice)
    with pytest.raises(co.CoordinateError, match="4 anchors"):
        co.internal(dry_ice, cell, "torsion", [(0,), (1,), (2,)])


def test_an_unknown_kind_names_the_ones_there_are(dry_ice):
    cell = p1.expand(dry_ice)
    with pytest.raises(co.CoordinateError, match="distance"):
        co.internal(dry_ice, cell, "improper", [(0,), (1,)])


def test_a_cell_parameter_reads_the_lattice_not_the_atoms(quartz):
    """A cell coordinate is not a function of where the atoms are, and
    says so: it is held by restricting the strain instead."""
    cell, matrix, positions = _cell_of(quartz)
    a = co.CellParameter("a")
    assert a.is_cell
    assert a.value(positions, matrix) == pytest.approx(4.9134, abs=1e-3)
    assert not a.gradient(positions, matrix).any()
    gamma = co.CellParameter("gamma")
    assert gamma.value(positions, matrix) == pytest.approx(120.0)
    assert gamma.units == "deg"


def test_the_volume_axis_reads_the_cell(quartz):
    cell, matrix, positions = _cell_of(quartz)
    volume = co.CellVolume()
    assert volume.is_cell
    assert volume.value(positions, matrix) == pytest.approx(
        quartz.lattice.volume)


def test_an_unknown_cell_parameter_names_the_six(quartz):
    with pytest.raises(co.CoordinateError, match="gamma"):
        co.CellParameter("d")


def test_a_plane_no_atoms_determine_is_refused_rather_than_fitted(
        dry_ice):
    """Four atoms round a symmetric site vary equally in every
    direction, so every direction is equally their normal.

    The fitted answer is whichever way the rounding error pointed and
    its derivative is enormous; a scan that held it would draw a
    confident landscape of nothing.  NaN is how the constraint later
    refuses it.
    """
    cell, matrix, positions = _cell_of(dry_ice)
    isotropic = co.internal(dry_ice, cell, "plane angle",
                            [(0, 1, 2, 3), (4, 5, 6, 7)])
    assert np.isnan(isotropic.value(positions, matrix))
    assert not isotropic.gradient(positions, matrix).any()


def test_a_plane_its_atoms_do_determine_is_fitted(dry_ice):
    """The guard above must not refuse an ordinary plane."""
    cell, matrix, positions = _cell_of(dry_ice)
    real = co.internal(dry_ice, cell, "plane angle",
                       [(4, 5, 6), (7, 8, 9)])
    assert 0.0 <= real.value(positions, matrix) <= 90.0
