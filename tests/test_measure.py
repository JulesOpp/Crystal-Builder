"""Distances, angles and torsions -- against known geometry.

Self-consistency is not enough here: a measurement tool that is wrong
in a plausible way is worse than one that is missing, so these check
real numbers (water's geometry, a dihedral dialled to a known value)
rather than that the code agrees with itself.
"""

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.core import measure, p1

# r(O-H) and the H-O-H angle of the experimental water monomer.
WATER = np.array([[0.0, 0.0, 0.0],
                  [0.9572, 0.0, 0.0],
                  [-0.2400, 0.9270, 0.0]])
WATER_OH = 0.9572
WATER_ANGLE = 104.52


def isolated(symbols, cartesian, box=30.0) -> Structure:
    """A molecule alone in a box big enough that nothing wraps."""
    lattice = Lattice.cubic(box)
    return Structure.from_arrays(
        lattice, symbols, np.asarray(cartesian) / box,
        space_group="P1")


def cell_of(structure):
    return p1.expand(structure), structure.lattice


# ---------------------------------------------------------- geometry

def test_water_geometry():
    water = isolated(["O", "H", "H"], WATER)
    cell, lattice = cell_of(water)
    assert measure.distance(cell, lattice, 0, 1) == pytest.approx(
        WATER_OH, abs=1e-4)
    assert measure.distance(cell, lattice, 1, 2) == pytest.approx(
        1.5151, abs=1e-3)                       # the H...H distance
    assert measure.angle(cell, lattice, 1, 0, 2) == pytest.approx(
        WATER_ANGLE, abs=0.01)


def test_angle_is_measured_at_the_middle_atom():
    """i-j-k puts j at the vertex; naming them in another order asks a
    different question and must give a different answer."""
    water = isolated(["O", "H", "H"], WATER)
    cell, lattice = cell_of(water)
    at_oxygen = measure.angle(cell, lattice, 1, 0, 2)
    at_hydrogen = measure.angle(cell, lattice, 0, 1, 2)
    assert at_oxygen == pytest.approx(WATER_ANGLE, abs=0.01)
    assert at_hydrogen == pytest.approx(37.74, abs=0.1)


@pytest.mark.parametrize("wanted", [0.0, 30.0, 60.0, 90.0, 120.0,
                                    179.0, -30.0, -90.0, -150.0])
def test_torsion_reads_back_the_angle_it_was_built_with(wanted):
    """Four atoms placed at a known dihedral, measured back -- sign
    included, because a torsion without its sign cannot tell one
    enantiomer from the other."""
    radians = np.radians(wanted)
    points = [[1.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 1.5],
              [np.cos(radians), np.sin(radians), 1.5]]
    chain = isolated(["C"] * 4, points)
    cell, lattice = cell_of(chain)
    assert measure.torsion(cell, lattice, 0, 1, 2, 3) == pytest.approx(
        wanted, abs=1e-6)


def test_a_collinear_torsion_has_no_answer():
    """Three points in a line define no plane; saying "0 degrees"
    would be inventing one."""
    flat = isolated(["C"] * 4, [[0, 0, 0], [1, 0, 0], [2, 0, 0],
                                [3, 0, 0]])
    cell, lattice = cell_of(flat)
    assert np.isnan(measure.torsion(cell, lattice, 0, 1, 2, 3))


# ------------------------------------------------ across the boundary

def test_a_distance_takes_the_short_way_round():
    """Two atoms at opposite ends of the cell are 0.2 A apart through
    the wall, not 4.8 A through the middle.  Subtracting fractional
    coordinates gives the second answer, which looks plausible and is
    wrong."""
    pair = Structure.from_arrays(
        Lattice.cubic(5.0), ["C", "O"],
        [[0.02, 0.5, 0.5], [0.98, 0.5, 0.5]], space_group="P1")
    cell, lattice = cell_of(pair)
    assert measure.distance(cell, lattice, 0, 1) == pytest.approx(0.2)


def test_an_angle_follows_a_molecule_across_the_boundary():
    """A bent trimer straddling the cell edge has the angle it would
    have anywhere else."""
    box = 6.0
    inside = isolated(["O", "H", "H"], WATER, box=box)
    straddling = Structure.from_arrays(
        Lattice.cubic(box), ["O", "H", "H"],
        (np.asarray(WATER) / box + [0.99, 0.0, 0.0]) % 1.0,
        space_group="P1")

    inside_cell, lattice = cell_of(inside)
    edge_cell, _ = cell_of(straddling)
    assert measure.angle(edge_cell, lattice, 1, 0, 2) == pytest.approx(
        measure.angle(inside_cell, lattice, 1, 0, 2), abs=1e-6)
    # ... and the atoms really are split by the boundary
    assert edge_cell.frac[:, 0].max() > 0.9
    assert edge_cell.frac[:, 0].min() < 0.2


def test_a_torsion_follows_a_molecule_across_the_boundary():
    box = 6.0
    points = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 0.0],
                       [0.0, 0.0, 1.5], [0.0, 1.0, 1.5]])
    inside = isolated(["C"] * 4, points, box=box)
    shifted = Structure.from_arrays(
        Lattice.cubic(box), ["C"] * 4,
        (points / box + [0.0, 0.98, 0.0]) % 1.0, space_group="P1")
    cell_in, lattice = cell_of(inside)
    cell_edge, _ = cell_of(shifted)
    assert measure.torsion(cell_edge, lattice, 0, 1, 2, 3) == \
        pytest.approx(measure.torsion(cell_in, lattice, 0, 1, 2, 3),
                      abs=1e-6)


# ------------------------------------------------------- the front door

def test_the_number_of_atoms_chooses_the_measurement():
    water = isolated(["O", "H", "H"], WATER)
    cell, lattice = cell_of(water)
    assert measure.measure(cell, lattice, [0, 1]).kind == "distance"
    assert measure.measure(cell, lattice, [1, 0, 2]).kind == "angle"

    chain = isolated(["C"] * 4, [[1, 0, 0], [0, 0, 0], [0, 0, 1.5],
                                 [0, 1, 1.5]])
    four, four_lattice = cell_of(chain)
    assert measure.measure(four, four_lattice,
                           [0, 1, 2, 3]).kind == "torsion"


def test_a_measurement_carries_its_labels_and_units():
    water = isolated(["O", "H", "H"], WATER)
    water.ensure_labels()
    cell, lattice = cell_of(water)
    result = measure.measure(cell, lattice, [0, 1])
    assert result.unit == "A"
    assert result.labels == ("O1", "H1")
    assert "O1 - H1" in result.text()
    assert "0.9572" in result.text()

    angle = measure.measure(cell, lattice, [1, 0, 2])
    assert angle.unit == "deg"
    assert "104.52" in angle.text()


def test_a_measurement_round_trips_through_a_dict():
    water = isolated(["O", "H", "H"], WATER)
    cell, lattice = cell_of(water)
    original = measure.measure(cell, lattice, [1, 0, 2])
    back = measure.Measurement.from_dict(original.to_dict())
    assert back == original


def test_bad_measurements_are_refused():
    water = isolated(["O", "H", "H"], WATER)
    cell, lattice = cell_of(water)
    with pytest.raises(ValueError):
        measure.measure(cell, lattice, [0])             # too few
    with pytest.raises(ValueError):
        measure.measure(cell, lattice, [0, 1, 2, 0, 1])  # too many
    with pytest.raises(ValueError):
        measure.measure(cell, lattice, [0, 0])          # same atom


# ------------------------------------------------------------- planes

#: A benzene ring in the xy plane, and the same ring tilted about x by
#: a known angle -- the two planes a measurement has to get right.
def ring(radius: float = 1.39, tilt: float = 0.0) -> np.ndarray:
    angles = np.radians(np.arange(0.0, 360.0, 60.0))
    points = np.stack([radius * np.cos(angles),
                       radius * np.sin(angles),
                       np.zeros(6)], axis=1)
    theta = np.radians(tilt)
    rotation = np.array([[1.0, 0.0, 0.0],
                         [0.0, np.cos(theta), -np.sin(theta)],
                         [0.0, np.sin(theta), np.cos(theta)]])
    return points @ rotation.T


def test_three_atoms_determine_a_plane_exactly():
    molecule = isolated(["C"] * 3, ring()[:3])
    cell, lattice = cell_of(molecule)
    plane = measure.plane(cell, lattice, [0, 1, 2])
    assert plane.deviation == pytest.approx(0.0, abs=1e-9)
    assert abs(plane.normal @ [0.0, 0.0, 1.0]) == pytest.approx(1.0)


def test_six_atoms_are_fitted_rather_than_refused():
    """The case the feature exists for: nobody picks exactly three
    atoms of a phenyl ring."""
    molecule = isolated(["C"] * 6, ring())
    cell, lattice = cell_of(molecule)
    plane = measure.plane(cell, lattice, range(6))
    assert plane.deviation == pytest.approx(0.0, abs=1e-9)
    assert abs(plane.normal @ [0.0, 0.0, 1.0]) == pytest.approx(1.0)


def test_a_puckered_ring_says_how_far_from_flat_it_is():
    """0.00 A and 0.11 A are the difference between a plane and a
    number dressed up as one."""
    points = ring()
    points[::2, 2] += 0.20              # a chair
    molecule = isolated(["C"] * 6, points)
    cell, lattice = cell_of(molecule)
    assert measure.plane(cell, lattice, range(6)).deviation > 0.05


def test_a_plane_needs_three_atoms():
    molecule = isolated(["C"] * 6, ring())
    cell, lattice = cell_of(molecule)
    with pytest.raises(ValueError):
        measure.plane(cell, lattice, [0, 1])
    with pytest.raises(ValueError):
        measure.plane(cell, lattice, [0, 1, 1])


def test_the_angle_between_two_planes_is_the_tilt_between_them():
    tilted = np.vstack([ring(), ring(tilt=35.0) + [8.0, 0.0, 0.0]])
    molecule = isolated(["C"] * 12, tilted)
    cell, lattice = cell_of(molecule)
    first = measure.plane(cell, lattice, range(6))
    second = measure.plane(cell, lattice, range(6, 12))
    assert measure.plane_angle(first, second) == pytest.approx(35.0)


def test_the_obtuse_answer_is_folded_onto_the_acute_one():
    """A plane has no side, so two normals 175 degrees apart describe
    planes 5 degrees apart -- which is what "nearly parallel" means."""
    tilted = np.vstack([ring(), ring(tilt=175.0) + [8.0, 0.0, 0.0]])
    molecule = isolated(["C"] * 12, tilted)
    cell, lattice = cell_of(molecule)
    angle = measure.plane_angle(
        measure.plane(cell, lattice, range(6)),
        measure.plane(cell, lattice, range(6, 12)))
    assert angle == pytest.approx(5.0)
    assert 0.0 <= angle <= 90.0


def test_a_plane_follows_a_ring_across_the_boundary():
    """The same rule the other measurements follow: a ring lying over a
    cell face is fitted as a ring, not as two halves of the box."""
    box = 8.0
    inside = isolated(["C"] * 6, ring(tilt=20.0), box=box)
    straddling = Structure.from_arrays(
        Lattice.cubic(box), ["C"] * 6,
        (ring(tilt=20.0) / box + [0.99, 0.0, 0.0]) % 1.0,
        space_group="P1")
    cell_in, lattice = cell_of(inside)
    cell_edge, _ = cell_of(straddling)
    assert cell_edge.frac[:, 0].max() > 0.9
    assert cell_edge.frac[:, 0].min() < 0.2

    flat = measure.plane(cell_in, lattice, range(6))
    split = measure.plane(cell_edge, lattice, range(6))
    assert split.deviation == pytest.approx(flat.deviation, abs=1e-9)
    assert abs(split.normal @ flat.normal) == pytest.approx(1.0)


# ------------------------------------------------- drawing a plane

def test_a_drawn_plane_lies_in_the_plane_it_was_fitted_to():
    """Every corner has to be *on* the plane.  A quad that is even
    slightly off it reads as a different plane the moment the picture
    is turned edge-on, which is exactly the view a plane is looked at
    in."""
    molecule = isolated(["C"] * 6, ring(tilt=35.0))
    cell, lattice = cell_of(molecule)
    fitted = measure.plane(cell, lattice, range(6))
    corners, _tip = measure.plane_quad(fitted, cell, lattice)
    offsets = (corners - fitted.centroid) @ fitted.normal
    assert np.abs(offsets).max() < 1e-9


def test_a_drawn_plane_crosses_the_whole_cell():
    """Two planes meet in a line, and the line is the thing worth
    looking at.  Quads cropped to their own rings never touch, so
    there is nothing to see -- a plane has to span the box for
    several of them to be readable together."""
    box = 30.0
    molecule = isolated(["C"] * 6, ring(radius=1.39), box=box)
    cell, lattice = cell_of(molecule)
    fitted = measure.plane(cell, lattice, range(6))
    corners, _tip = measure.plane_quad(fitted, cell, lattice)

    reach = np.linalg.norm(corners - fitted.centroid, axis=1).max()
    assert reach > box / 2                      # the box, not the ring


def test_two_planes_that_are_not_parallel_actually_intersect():
    """The whole reason they are drawn to the cell: two rings eight
    Angstrom apart, canted against each other, have to show where
    their planes cross."""
    box = 30.0
    both = np.vstack([ring(), ring(tilt=40.0) + [8.0, 0.0, 0.0]])
    molecule = isolated(["C"] * 12, both, box=box)
    cell, lattice = cell_of(molecule)
    quads = [measure.plane_quad(
        measure.plane(cell, lattice, group), cell, lattice)[0]
        for group in (range(6), range(6, 12))]

    # each quad reaches across the other plane -- corners on both
    # sides of it -- which is what an intersection inside the picture
    # is
    for quad, other in ((quads[0], 1), (quads[1], 0)):
        plane = measure.plane(cell, lattice,
                              range(6 * other, 6 * other + 6))
        side = (quad - plane.centroid) @ plane.normal
        assert side.min() < 0 < side.max()


def test_a_drawn_plane_carries_a_normal_at_right_angles_to_itself():
    """Two nearly parallel planes have faces that look identical and
    normals that do not, which is the whole reason the normal is
    drawn."""
    molecule = isolated(["C"] * 6, ring(tilt=35.0))
    cell, lattice = cell_of(molecule)
    fitted = measure.plane(cell, lattice, range(6))
    corners, tip = measure.plane_quad(fitted, cell, lattice)
    along = tip - fitted.centroid
    assert np.linalg.norm(along) > 0.5
    for edge in (corners[1] - corners[0], corners[3] - corners[0]):
        assert abs(along @ edge) < 1e-9


def test_a_drawn_plane_sits_on_the_ring_it_was_fitted_through():
    """The quad spans the cell, but it is still *that* plane: its
    centre is the fitted centroid, which for a ring lying over a cell
    face is on the ring rather than in the middle of the box."""
    box = 8.0
    straddling = Structure.from_arrays(
        Lattice.cubic(box), ["C"] * 6,
        (ring() / box + [0.99, 0.0, 0.0]) % 1.0, space_group="P1")
    cell, lattice = cell_of(straddling)
    fitted = measure.plane(cell, lattice, range(6))
    corners, _tip = measure.plane_quad(fitted, cell, lattice)
    assert np.allclose(corners.mean(axis=0), fitted.centroid)
    offsets = (corners - fitted.centroid) @ fitted.normal
    assert np.abs(offsets).max() < 1e-9


def test_an_interplanar_angle_is_a_measurement_like_any_other():
    tilted = np.vstack([ring(), ring(tilt=35.0) + [8.0, 0.0, 0.0]])
    molecule = isolated(["C"] * 12, tilted)
    cell, lattice = cell_of(molecule)
    result = measure.interplanar_angle(
        measure.plane(cell, lattice, range(6), name="Plane 1"),
        measure.plane(cell, lattice, range(6, 12), name="Plane 2"))

    assert result.kind == measure.PLANE_ANGLE
    assert result.unit == "deg"
    assert result.value == pytest.approx(35.0)
    assert set(result.atoms) == set(range(12))      # what it depends on
    assert "Plane 1 ^ Plane 2" in result.text()

    back = measure.Measurement.from_dict(result.to_dict())
    assert back.planes == result.planes
    assert back.value == pytest.approx(result.value)
