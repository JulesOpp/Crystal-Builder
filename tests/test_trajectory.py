"""Multi-frame extended XYZ, and playing it back onto a structure.

The round trip is the part worth pinning: a trajectory that OVITO, VMD
and ASE can read is most of what a trajectory is for, and the thing
that would break it -- a comment line that stops being key-value, a
frame boundary that drifts -- breaks silently.
"""

import numpy as np
import pytest

from xtal import Lattice, Structure
from xtal.core import p1
from xtal.io import FORMATS
from xtal.io.trajectory import (
    Frame,
    TrajectoryWriter,
    format_info,
    frame_of,
    parse_info,
    read_frames,
    read_trajectory,
    write_trajectory,
)


@pytest.fixture
def moving(rutile):
    """Rutile, with its oxygen walked along the diagonal."""
    frames = []
    for step in range(4):
        structure = rutile.copy()
        structure.set_frac(1, [0.3053 + 0.01 * step,
                               0.3053 + 0.01 * step, 0.0])
        frames.append(frame_of(structure, step=step,
                               energy=-100.0 + step,
                               max_force=1.0 / (step + 1)))
    return frames


# ----------------------------------------------------------- the format

def test_a_frame_round_trips_through_text(rutile):
    frame = frame_of(rutile, step=7, energy=-12.5)
    back, = read_frames(frame.text())

    assert back.elements == frame.elements
    assert back.step == 7
    assert back.energy == pytest.approx(-12.5)
    assert np.allclose(back.cart, frame.cart)
    assert np.allclose(back.lattice.matrix, rutile.lattice.matrix)


def test_every_frame_survives_a_file(tmp_path, moving):
    path = write_trajectory(moving, tmp_path / "run.extxyz")
    trajectory = read_trajectory(path)

    assert trajectory.n_frames == 4
    assert trajectory.n_atoms == 6           # the P1 cell of rutile
    assert trajectory.steps == [0, 1, 2, 3]
    assert np.allclose(trajectory.energies,
                       [-100.0, -99.0, -98.0, -97.0])
    assert trajectory.is_fixed_cell


def test_the_writer_flushes_every_frame(tmp_path, moving):
    """A run that is killed has still written what it reported.

    The frames go to disk as they arrive rather than being collected
    and written at the end, and this is the property that buys.
    """
    path = tmp_path / "partial.extxyz"
    writer = TrajectoryWriter(path)
    for frame in moving[:2]:
        writer.append_frame(frame)
        # Read it back without closing the writer, exactly as a viewer
        # tailing a live run would.
        assert read_trajectory(path).n_frames == writer.n_frames
    writer.close()
    assert read_trajectory(path).n_frames == 2


def test_the_comment_line_is_key_value(rutile):
    info = parse_info(
        'Lattice="1 0 0 0 2 0 0 0 3" Properties=species:S:1:pos:R:3 '
        'energy=-1.5 step=12 name="a run"')

    assert info["step"] == 12
    assert info["energy"] == pytest.approx(-1.5)
    assert info["name"] == "a run"
    assert np.allclose(info["Lattice"], np.diag([1.0, 2.0, 3.0]))
    # and what is written can be read again
    assert parse_info(format_info(info))["step"] == 12


def test_prose_on_the_comment_line_is_not_an_error():
    """A plain XYZ file has a title where the keys would be."""
    text = "1\nsome molecule I drew\nH 0.0 0.0 0.0\n"
    frame, = read_frames(text)

    assert frame.elements == ("H",)
    assert frame.lattice is None
    assert frame.energy is None


def test_a_truncated_frame_says_so(tmp_path):
    path = tmp_path / "cut.extxyz"
    path.write_text("3\nLattice=\"1 0 0 0 1 0 0 0 1\"\nH 0 0 0\n")
    with pytest.raises(ValueError, match="claims 3 atoms"):
        read_trajectory(path)


def test_the_registry_reads_every_frame(tmp_path, moving):
    """``read_all`` used to answer with the first frame of a hundred."""
    path = write_trajectory(moving, tmp_path / "run.extxyz")
    structures = FORMATS.read_all(path)

    assert len(structures) == 4
    assert all(s.n_sites == 6 for s in structures)
    assert FORMATS.read(path).n_sites == 6      # one frame, as before


# -------------------------------------------------------- playing it back

def test_a_frame_maps_back_onto_the_asymmetric_unit(rutile):
    """A trajectory holds the cell; a document varies its sites.

    Watching a P4_2/mnm structure must not quietly reduce it to P1.
    """
    moved = rutile.copy()
    moved.set_frac(1, [0.31, 0.31, 0.0])
    frame = frame_of(moved)

    cell = p1.expand(rutile)
    parent = p1.parent_frac(rutile, cell, frame.frac(rutile.lattice))

    assert parent.shape == (2, 3)
    assert np.allclose(parent % 1.0, moved.frac % 1.0)


def test_the_mapping_refuses_a_cell_of_the_wrong_size(rutile):
    cell = p1.expand(rutile)
    with pytest.raises(ValueError, match="one per atom"):
        p1.parent_frac(rutile, cell, np.zeros((3, 3)))


def test_a_frame_becomes_a_p1_structure(rutile):
    structure = frame_of(rutile).to_structure()

    assert structure.n_sites == 6
    assert structure.space_group.number == 1
    assert np.allclose(structure.lattice.matrix, rutile.lattice.matrix)


def test_a_frame_with_no_cell_will_not_pretend_to_be_a_crystal():
    frame = Frame(("H",), np.zeros((1, 3)))
    with pytest.raises(ValueError, match="no cell"):
        frame.to_structure()


def test_a_trajectory_knows_which_crystal_it_is_of(rutile, quartz):
    """Atom counts alone would let one run drive another structure."""
    from xtal.io.trajectory import Trajectory

    trajectory = Trajectory([frame_of(rutile)])
    assert trajectory.is_compatible(rutile)
    assert not trajectory.is_compatible(quartz)


def test_a_cell_that_changes_is_not_a_fixed_cell(rutile):
    from xtal.io.trajectory import Trajectory

    stretched = rutile.copy()
    stretched.lattice = Lattice.from_parameters(5.0, 4.594, 2.959,
                                                90, 90, 90)
    trajectory = Trajectory([frame_of(rutile), frame_of(stretched)])
    assert not trajectory.is_fixed_cell


def test_an_empty_structure_still_writes_a_frame():
    """Nothing in the cell yet is a state the application allows."""
    empty = Structure(lattice=Lattice.cubic(10.0))
    frame = frame_of(empty)

    assert frame.n_atoms == 0
    assert read_frames(frame.text())[0].n_atoms == 0
