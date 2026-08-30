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
