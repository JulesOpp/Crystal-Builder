"""ASE's own binary trajectory, read through ase.

The format is a pickle-adjacent container and its layout is ase's
business, so it is read through ase rather than reimplemented from
outside.  What that buys is every run anything ASE-driven produces --
an optimisation, a molecular-dynamics run, a calculator's history --
opening in the transport bar beside the runs this application writes
itself.
"""

import pytest

from xtal.io import read_trajectory
from xtal.io.trajectory import ase_available

ase = pytest.importorskip("ase", reason="reading .traj needs the ase extra")


@pytest.fixture
def run(tmp_path):
    """Four frames of a molecule stretching, written by ase itself."""
    from ase import Atoms
    from ase.io import write
    frames = [Atoms("H2O",
                    positions=[[0, 0, 0], [0.96 + 0.01 * i, 0, 0],
                               [0, 0.96, 0]],
                    cell=[8, 8, 8], pbc=True)
              for i in range(4)]
    path = tmp_path / "run.traj"
    write(str(path), frames)
    return path


def test_every_frame_of_the_run_is_read(run):
    assert len(read_trajectory(run)) == 4


def test_the_frames_are_in_the_order_they_were_written(run):
    """A trajectory read out of order is a playback that runs
    backwards, which is a hard thing to notice and a worse thing to
    debug."""
    xs = [frame.cart[1][0] for frame in read_trajectory(run)]
    assert xs == sorted(xs)
    assert xs[-1] > xs[0]


def test_a_frame_carries_its_atoms_and_its_cell(run):
    frame = read_trajectory(run)[0]
    assert frame.n_atoms == 3
    assert sorted(frame.elements) == ["H", "H", "O"]
    assert frame.lattice is not None
    assert frame.lattice.parameters[0] == pytest.approx(8.0)


def test_a_frame_knows_which_step_it_was(run):
    """The transport bar shows it, and a frame with no step is a
    frame the scrubber cannot label."""
    assert [f.step for f in read_trajectory(run)] == [0, 1, 2, 3]


def test_a_frame_becomes_a_structure_when_asked(run):
    """A Frame is not a Structure and does not pretend to be one --
    turning it into one stays the caller's decision."""
    structure = read_trajectory(run)[0].to_structure()
    assert len(structure.sites) == 3


def test_a_file_that_is_not_a_trajectory_says_so(tmp_path):
    """ase raises its own several kinds of error for a file it cannot
    read. They become one sentence naming the file, because a user who
    opened the wrong thing is owed that and not a traceback."""
    path = tmp_path / "notes.traj"
    path.write_bytes(b"")
    with pytest.raises(ValueError, match="could not be read"):
        read_trajectory(path)


def test_the_extended_xyz_reader_is_untouched(tmp_path):
    """.traj is a branch, not a replacement: the format this
    application writes its own runs in still reads the same way."""
    import numpy as np

    from xtal import Lattice
    from xtal.io import write_trajectory
    from xtal.io.trajectory import Frame
    frames = [Frame(elements=("H", "H"),
                    cart=np.array([[0.0, 0, 0], [0.7 + 0.1 * i, 0, 0]]),
                    lattice=Lattice.cubic(6.0), info={"step": i})
              for i in range(3)]
    path = tmp_path / "own.xyz"
    write_trajectory(frames, path)
    assert len(read_trajectory(path)) == 3


def test_ase_is_checked_for_without_importing_it():
    """find_spec and never an import: importing ase to find out
    whether ase is there costs a second and a hundred modules on a
    machine that has it."""
    import inspect
    assert "find_spec" in inspect.getsource(ase_available)
    assert ase_available() is True
