"""The workspace: a directory layout, and what a run leaves in it.

All headless.  The layout is written by the module that ran and not by
the tree that shows it, which is what makes a run started from a script
openable in the window -- so it has to be testable without one.
"""

import numpy as np
import pytest

from xtal.io import read_cif, write_cif
from xtal.io.trajectory import read_trajectory
from xtal.workspace import (
    WORKSPACE_FILE,
    NotAWorkspace,
    Run,
    Workspace,
    classify,
    safe_name,
)


@pytest.fixture
def workspace(tmp_path):
    return Workspace.create(tmp_path / "ws")


@pytest.fixture
def entry(workspace, tmp_path, rutile):
    source = tmp_path / "rutile.cif"
    write_cif(rutile, source)
    return workspace.add_structure(source)


# ------------------------------------------------------- making one

def test_a_workspace_is_a_folder_with_a_marker_in_it(workspace):
    assert (workspace.root / WORKSPACE_FILE).is_file()
    assert Workspace.is_workspace(workspace.root)
    assert workspace.version == 1


def test_creating_over_an_existing_workspace_opens_it(workspace,
                                                      entry):
    """"New workspace" pointed at one that already exists should open
    it, not stop with an error about a file nobody has seen."""
    again = Workspace.create(workspace.root)
    assert [e.name for e in again.entries()] == [entry.name]


def test_an_ordinary_folder_is_not_a_workspace(tmp_path):
    with pytest.raises(NotAWorkspace):
        Workspace.open(tmp_path)


def test_a_workspace_is_found_by_looking_upwards(workspace, entry):
    """How a reopened project finds the workspace it belongs to.

    Walking up beats storing the root: a workspace that was moved,
    renamed or copied to another machine still answers.
    """
    run = entry.next_run("uff", "optimise")
    assert Workspace.find(run.path) == workspace
    assert Workspace.find(entry.structure_path) == workspace
    assert Workspace.find(workspace.root.parent) is None


# ------------------------------------------------------- the structure

def test_the_opened_file_is_copied_in(workspace, tmp_path, rutile):
    """A workspace pointing at a file the user then moves is a tree of
    broken nodes; the copy costs kilobytes."""
    source = tmp_path / "rutile.cif"
    write_cif(rutile, source)
    entry = workspace.add_structure(source)

    assert entry.structure_path.parent == entry.path
    assert entry.structure_path != source
    source.unlink()
    assert read_cif(entry.structure_path).n_sites == 2


def test_opening_the_same_file_twice_is_one_entry(workspace,
                                                 tmp_path, rutile):
    source = tmp_path / "rutile.cif"
    write_cif(rutile, source)
    first = workspace.add_structure(source)
    second = workspace.add_structure(source)

    assert first.path == second.path
    assert len(workspace.entries()) == 1


def test_a_built_structure_never_lands_in_a_folder_in_use(
        workspace, tmp_path, rutile):
    """``new_document`` is ``add_document`` that will not share.

    Both file a structure at ``<entry>/<name>.cif``, so a build whose
    title matches an opened file would write over that file's
    workspace copy -- which is the copy that exists so the workspace
    is whole.
    """
    source = tmp_path / "rutile.cif"
    write_cif(rutile, source)
    opened = workspace.add_structure(source)

    first = workspace.new_document("rutile")
    second = workspace.new_document("rutile")

    assert first.path.name == "rutile-2"
    assert second.path.name == "rutile-3"
    assert opened.structure_path == opened.path / "rutile.cif"


def test_a_document_entry_is_reused_and_a_built_one_is_not(workspace):
    """The reason there are two methods.

    A module files every run it makes under its own label and wants
    the same folder each time; a structure wants one nobody else is
    in.
    """
    assert (workspace.add_document("Maker").path
            == workspace.add_document("Maker").path)
    assert (workspace.new_document("Maker").path
            != workspace.new_document("Maker").path)


def test_a_name_that_would_not_survive_a_filesystem(workspace):
    assert safe_name("Fe(bpy)3 2+") == "Fe_bpy_3_2+"
    assert safe_name("///") == "structure"
    entry = workspace.add_document("Fe(bpy)3 2+")
    assert entry.path.is_dir()


# ------------------------------------------------------- the runs

def test_a_run_folder_is_named_by_what_made_it(entry):
    first = entry.next_run("uff", "optimise")
    second = entry.next_run("uff", "single-point")

    assert first.name == "uff-optimise-001"
    assert second.name == "uff-single-point-002"
    assert [r.name for r in entry.runs()] == [first.name, second.name]
    assert entry.runs()[0].label == "uff optimise 001"


def test_the_numbering_is_read_back_from_the_folders(entry):
    entry.next_run("uff", "optimise")
    # A fresh Entry object, as the tree makes on every refresh: the
    # number is derived from what is there, not remembered.
    from xtal.workspace import Entry
    again = Entry(path=entry.path)
    assert again.next_run("uff", "optimise").name == "uff-optimise-002"


def test_a_folder_that_is_not_a_run_is_not_read_as_one(entry):
    (entry.path / "notes").mkdir()
    assert Run.at(entry.path / "notes") is None
    assert [r.name for r in entry.runs()] == []


def test_a_run_writes_the_three_files(entry, rutile):
    from xtal.io.trajectory import frame_of

    with entry.next_run("uff", "optimise") as folder:
        folder.log().write("hello")
        folder.trajectory().append_frame(frame_of(rutile, step=0))
        folder.write_final(rutile)

    run = entry.runs()[0]
    assert [a.kind for a in run.artifacts()] == ["final", "trajectory",
                                                 "log"]
    assert run.log_path.read_text() == "hello\n"
    assert read_trajectory(run.trajectory_path).n_frames == 1
    assert read_cif(run.final_path).n_sites == 2


def test_a_run_that_left_nothing_says_nothing(entry):
    """The directory is the truth about what a killed run wrote."""
    folder = entry.next_run("uff", "optimise")
    folder.close()
    assert entry.runs()[0].artifacts() == []


def test_a_single_point_has_no_trajectory_file(entry):
    """An empty trajectory.extxyz beside a run that never had one is a
    file that says something untrue."""
    with entry.next_run("uff", "single-point") as folder:
        folder.log().write("just an energy")

    run = entry.runs()[0]
    assert not run.trajectory_path.exists()
    assert [a.kind for a in run.artifacts()] == ["log"]


def test_what_each_file_is_is_not_its_extension(entry):
    assert classify(entry.path / "run.log") == "log"
    assert classify(entry.path / "final.cif") == "final"
    assert classify(entry.path / "MFU4l.cif") == "structure"
    assert classify(entry.path / "trajectory.extxyz") == "trajectory"
    assert classify(entry.path / "MFU4l.xtalproj") == "project"
    assert classify(entry.path / "notes.txt") == "file"


def test_the_log_lines_a_table_up(entry):
    with entry.next_run("uff", "optimise") as folder:
        folder.log().table([["C1", "C_3"], ["Halloumi", "H_"]],
                           headers=("site", "type"))
    lines = entry.runs()[0].log_path.read_text().splitlines()
    assert lines[0] == "site      type"
    assert lines[2] == "C1        C_3"


# ------------------------------------------------------- the recorder

def test_a_recorded_run_is_readable_three_months_later(entry, rutile):
    """What the log has to contain to be worth keeping."""
    from xtal.ff import ENGINES, optimize
    from xtal.ff.record import RunRecorder

    calculator = ENGINES.build("uff", rutile)
    with RunRecorder(entry.next_run("uff", "optimise"), rutile,
                     calculator, engine="uff",
                     options={"coulomb": False}) as recorder:
        recorder.header("geometry optimisation")
        recorder.typing()
        recorder.topology()
        recorder.begin_steps()
        last = None
        for step in optimize.steps(calculator, rutile, "lbfgs",
                                   max_steps=3):
            recorder.step(step)
            last = step
        recorder.result(optimize.OptimizationResult(
            converged=False, steps=last.iteration, initial_energy=0.0,
            energy=last.energy, max_force=last.max_force,
            frac=last.frac, terms=dict(last.terms)), final=rutile)

    run = entry.runs()[0]
    log = run.log_path.read_text()

    assert "Crystal Builder" in log              # the version
    assert "engine         uff  (UFF)" in log    # and its options
    assert "coulomb      off" in log
    assert "Atom types" in log                   # the typing table...
    assert "Ti6+4" in log and "likely" in log    # ...with the reasons
    assert "octahedral Ti(IV)" in log            # ...and in words
    assert "Topology" in log                     # the counts
    assert "|F|max" in log                       # a line per step
    assert "bond" in log                         # the term breakdown
    assert "not a minimum" in log                # and the verdict
    assert "wrote final.cif" in log

    assert read_trajectory(run.trajectory_path).n_frames >= 1
    assert run.final_path.exists()


def test_the_trajectory_has_one_frame_per_step_whatever_is_drawn(
        entry, rutile):
    """Phase I: the redraw rate is a property of the viewport, and the
    file left behind must not depend on it.  ``RunRecorder.step`` is
    called once per optimiser step regardless of anything about
    drawing, so this is asserted at the level nothing about a preview
    interval could ever reach -- the recorder has no such concept."""
    from xtal.ff import ENGINES, optimize
    from xtal.ff.record import RunRecorder

    calculator = ENGINES.build("uff", rutile)
    steps_taken = 0
    with RunRecorder(entry.next_run("uff", "optimise"), rutile,
                     calculator, engine="uff",
                     options={"coulomb": False}) as recorder:
        recorder.begin_steps()
        for step in optimize.steps(calculator, rutile, "lbfgs",
                                   max_steps=5):
            recorder.step(step)
            steps_taken += 1

    run = entry.runs()[0]
    assert steps_taken > 1
    assert (read_trajectory(run.trajectory_path).n_frames
           == steps_taken)


def test_the_recorder_writes_the_cell_not_the_asymmetric_unit(entry,
                                                              rutile):
    """The trajectory is what another program will read."""
    from xtal.ff import ENGINES, optimize
    from xtal.ff.record import RunRecorder

    calculator = ENGINES.build("uff", rutile)
    with RunRecorder(entry.next_run("uff", "optimise"), rutile,
                     calculator, engine="uff") as recorder:
        for step in optimize.steps(calculator, rutile, "lbfgs",
                                   max_steps=2):
            recorder.step(step)

    trajectory = read_trajectory(entry.runs()[0].trajectory_path)
    assert trajectory.n_atoms == 6               # not 2
    assert trajectory.is_compatible(rutile)
    assert not np.isnan(trajectory.energies).any()


def test_the_cli_writes_the_same_layout(tmp_path, rutile):
    """A run started from a script is one the window can open."""
    from xtal.cli import main

    source = tmp_path / "rutile.cif"
    write_cif(rutile, source)
    root = tmp_path / "ws"
    main(["optimize", str(source), "--workspace", str(root),
          "--max-steps", "3", "-q"])

    workspace = Workspace.open(root)
    entry, = workspace.entries()
    run, = entry.runs()
    assert run.name == "uff-optimise-001"
    assert {a.kind for a in run.artifacts()} == {"final", "trajectory",
                                                 "log"}
