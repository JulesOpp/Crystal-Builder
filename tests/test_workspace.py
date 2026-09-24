"""The workspace: a directory layout, and what a run leaves in it.

All headless.  The layout is written by the module that ran and not by
the tree that shows it, which is what makes a run started from a script
openable in the window -- so it has to be testable without one.
"""

import json

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
    resolved,
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


def test_two_different_files_of_the_same_name_get_two_entries(
        workspace, tmp_path, rutile, quartz):
    """Two people's MFU4l.cif are two structures.

    If it regresses, the second one is copied over the first and the
    workspace keeps one of them without saying anything.
    """
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    write_cif(rutile, tmp_path / "a" / "same.cif")
    write_cif(quartz, tmp_path / "b" / "same.cif")

    first = workspace.add_structure(tmp_path / "a" / "same.cif")
    second = workspace.add_structure(tmp_path / "b" / "same.cif")

    assert first.path != second.path
    assert len(workspace.entries()) == 2
    assert read_cif(first.structure_path).n_sites == rutile.n_sites
    assert read_cif(second.structure_path).n_sites == quartz.n_sites


def test_the_same_bytes_under_a_taken_name_still_find_their_entry(
        workspace, tmp_path, rutile, quartz):
    """Third time lucky: the file is already in the numbered folder."""
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    write_cif(rutile, tmp_path / "a" / "same.cif")
    write_cif(quartz, tmp_path / "b" / "same.cif")
    workspace.add_structure(tmp_path / "a" / "same.cif")
    second = workspace.add_structure(tmp_path / "b" / "same.cif")

    again = workspace.add_structure(tmp_path / "b" / "same.cif")

    assert again.path == second.path
    assert len(workspace.entries()) == 2


# ------------------------------------------------------- the session

def test_a_workspace_remembers_what_was_open(workspace, entry):
    workspace.set_session([entry.structure_path], active=0)

    reopened = Workspace.open(workspace.root)

    assert reopened.session["open"] == ["rutile/rutile.cif"]
    assert reopened.session_paths() == [entry.structure_path]


def test_a_remembered_file_that_has_gone_is_skipped(workspace, entry):
    """A deleted structure must not stop the workspace opening."""
    workspace.set_session([entry.structure_path])
    entry.structure_path.unlink()

    assert workspace.session["open"] == ["rutile/rutile.cif"]
    assert workspace.session_paths() == []


def test_a_session_survives_the_workspace_being_moved(workspace, entry,
                                                      tmp_path):
    """Relative paths, for the reason `find` walks upwards."""
    workspace.set_session([entry.structure_path])
    moved = tmp_path / "somewhere else"
    workspace.root.rename(moved)

    reopened = Workspace.open(moved)

    assert reopened.session_paths() == [moved / "rutile" / "rutile.cif"]


def test_a_marker_nobody_has_written_a_session_into_opens_empty(
        workspace):
    assert workspace.session == {"open": [], "active": 0}


def test_a_marker_edited_into_nonsense_opens_empty(workspace):
    """Rather than refusing to open the workspace at all."""
    (workspace.root / WORKSPACE_FILE).write_text("{not json")

    assert workspace.session == {"open": [], "active": 0}


@pytest.mark.parametrize("text", ["[1, 2, 3]", "null", "42", '"a"'])
def test_a_marker_that_is_json_but_not_an_object_opens_empty(workspace,
                                                            text):
    """Valid JSON that is not a marker used to raise on `.get`, while
    the workspace was being opened and before any window could say
    why."""
    (workspace.root / WORKSPACE_FILE).write_text(text)

    assert workspace.session == {"open": [], "active": 0}
    assert workspace.version == 0
    workspace.set_session([])       # and writing one over it works


def test_a_session_open_list_that_is_a_string_opens_nothing(workspace,
                                                            entry):
    """"a.cif" iterated is five paths, and "." among them is the root
    -- a directory offered as a document."""
    (workspace.root / WORKSPACE_FILE).write_text(
        '{"session": {"open": "rutile/rutile.cif"}}')

    assert workspace.session_paths() == []


def test_a_remembered_path_outside_the_workspace_is_not_opened(
        workspace, entry, tmp_path):
    """A marker in a shared folder does not get to choose a file
    anywhere on the disk; `set_session` never writes one."""
    outside = tmp_path / "outside.cif"
    outside.write_text("data_x\n", encoding="utf-8")
    (workspace.root / WORKSPACE_FILE).write_text(json.dumps(
        {"session": {"open": [outside.as_posix(), "../outside.cif",
                              "rutile/rutile.cif"]}}))

    assert workspace.session_paths() == [entry.structure_path]


def test_a_path_outside_the_workspace_is_not_remembered(workspace,
                                                        tmp_path):
    workspace.set_session([tmp_path / "elsewhere.cif"])

    assert workspace.session["open"] == []


def test_recording_a_session_keeps_the_marker_a_marker(workspace,
                                                       entry):
    """The format and version have to survive the session write."""
    workspace.set_session([entry.structure_path])

    assert Workspace.is_workspace(workspace.root)
    assert Workspace.open(workspace.root).version == 1


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


def test_an_accented_name_keeps_its_letters():
    """The accent goes and the letter stays.  Deleting the whole
    character made "quartz café" an entry called quartz_caf, and café
    and cafè the same folder."""
    assert safe_name("quartz café") == "quartz_cafe"
    assert safe_name("Ångström") == "Angstrom"
    assert safe_name("Straße") == "Strasse"


def test_a_greek_letter_is_spelled_out():
    """α-quartz, β-cristobalite and γ-Fe are how phases are named, and
    the letter is the part that says which one."""
    assert safe_name("α-quartz") == "alpha-quartz"
    assert safe_name("β-cristobalite") == "beta-cristobalite"
    assert safe_name("Δ") == "Delta"


def test_a_name_with_nothing_latin_in_it_still_gets_a_folder():
    assert safe_name("結晶") == "structure"


def test_a_file_filed_under_the_old_spelling_is_still_found(workspace,
                                                            tmp_path):
    """A workspace made before accents were kept holds "café.cif" in a
    folder called caf.  Opening the same file again has to find that
    entry by its bytes, not file a second copy under cafe."""
    source = tmp_path / "café.cif"
    source.write_text("data_x\n")
    old = workspace.root / "caf"
    old.mkdir()
    (old / source.name).write_bytes(source.read_bytes())

    assert workspace.add_structure(source).path == old
    assert not (workspace.root / "cafe").exists()


def test_the_old_spelling_is_searched_past_a_folder_it_shares(
        workspace, tmp_path):
    """café and cafè were both caf; whichever came second is in caf-2,
    and caf holding the other one is not a reason to stop looking."""
    other = tmp_path / "cafè.cif"
    other.write_text("data_other\n")
    source = tmp_path / "café.cif"
    source.write_text("data_x\n")
    for folder, file in (("caf", other), ("caf-2", source)):
        (workspace.root / folder).mkdir()
        (workspace.root / folder / file.name).write_bytes(
            file.read_bytes())

    assert workspace.add_structure(source).path == workspace.root / "caf-2"


# ------------------------------------------------------- the runs

def test_a_run_folder_is_named_by_what_made_it(entry):
    first = entry.next_run("uff", "optimise")
    second = entry.next_run("uff", "single-point")

    assert first.name == "uff-optimise-001"
    assert second.name == "uff-single-point-002"
    assert [r.name for r in entry.runs()] == [first.name, second.name]
    assert entry.runs()[0].label == "uff optimise 001"


def test_two_runs_started_together_get_two_numbers(entry):
    """Both read the same maximum; the second used to raise
    FileExistsError from a worker thread instead of numbering."""
    import threading

    barrier = threading.Barrier(6)
    made, failed = [], []

    def start():
        barrier.wait()
        try:
            made.append(entry.next_run("uff", "optimise").name)
        except Exception as error:      # noqa: BLE001 -- recorded
            failed.append(error)

    threads = [threading.Thread(target=start) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failed == []
    assert sorted(made) == [f"uff-optimise-{i:03d}" for i in range(1, 7)]


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
    assert classify(entry.path / "report.json") == "report"
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


# ------------------------------------------------------- autosave

def test_an_autosave_mirrors_the_file_it_is_for(workspace, entry):
    kept = workspace.autosave_path(entry.structure_path)

    assert kept == (workspace.root / ".autosave" / "rutile"
                    / "rutile.xtalproj")
    assert kept != entry.structure_path


def test_the_autosave_folder_is_not_an_entry(workspace, entry):
    kept = workspace.autosave_path(entry.structure_path)
    kept.parent.mkdir(parents=True)
    kept.write_bytes(b"")

    assert [e.name for e in workspace.entries()] == ["rutile"]


def test_a_file_outside_the_workspace_has_no_autosave(workspace,
                                                     tmp_path):
    assert workspace.autosave_path(tmp_path / "elsewhere.cif") is None


# --------------------------------------------------- filing a build

def _placeholder_run(workspace, rutile):
    """A run opened under an entry named for the module, holding the
    copy of the structure the module wrote for itself."""
    run = workspace.add_document("MOF builder").next_run("mof", "build")
    own = run.path / "pormake.cif"
    write_cif(rutile, own)
    return run.path, own


def test_adopting_a_build_leaves_one_entry_and_one_cif(workspace,
                                                       rutile):
    """Two copies of a build are a question about which is real."""
    run, own = _placeholder_run(workspace, rutile)
    built = rutile.copy()
    built.meta["title"] = "pcu-N1"

    filed = workspace.adopt_build(built, run=run, artifacts=(own,))

    assert filed.entry.path == workspace.root / "pcu-N1"
    assert filed.path == filed.entry.path / "pcu-N1.cif"
    assert filed.run == filed.entry.path / run.name
    assert [p.name for p in filed.run.iterdir()
            if p.suffix == ".cif"] == []
    assert not run.parent.exists()            # the placeholder went
    assert [e.name for e in workspace.entries()] == ["pcu-N1"]


def test_a_placeholder_holding_another_run_is_left_alone(workspace,
                                                         rutile):
    run, own = _placeholder_run(workspace, rutile)
    workspace.add_document("MOF builder").next_run("mof", "build")

    workspace.adopt_build(rutile.copy(), run=run, artifacts=(own,))

    assert run.parent.is_dir()


def test_a_second_build_of_one_name_gets_a_folder_of_its_own(
        workspace, rutile):
    first = workspace.adopt_build(rutile.copy())
    second = workspace.adopt_build(rutile.copy())

    assert first.entry.path != second.entry.path
    assert first.run is None and second.run is None


# ------------------------------------------ a force-field run's life

def _stable(log_text: str) -> list[str]:
    """A log without the lines that name a moment or a place."""
    return [line for line in log_text.splitlines()
            if not any(word in line for word in
                       ("started", "finished", "folder", "timing",
                        "seconds", "version", "/"))]


def test_a_failed_run_closes_its_log_once(entry, rutile):
    """The panel used to write its failure path twice, differently."""
    from xtal.ff import ENGINES
    from xtal.ff import record as ff_record

    calculator = ENGINES.get("uff")(rutile)
    recorder = ff_record.open_run(entry, "uff", "optimise", rutile,
                                  calculator)
    ff_record.close_run(recorder, error="it went wrong",
                        warning="recording stopped: disk full")
    ff_record.close_run(None, error="nothing to close")

    run, = entry.runs()
    log = run.log_path.read_text()
    assert log.count("the run failed: it went wrong") == 1
    assert log.count("recording stopped: disk full") == 1
    assert log.count("finished") == 1
    assert not run.final_path.exists()


def test_no_entry_is_a_run_that_leaves_nothing(rutile):
    from xtal.ff import record as ff_record

    assert ff_record.open_run(None, "uff", "single-point", rutile,
                              None) is None


def test_cli_and_panel_write_the_same_run_folder(tmp_path, entry,
                                                 rutile):
    """The panel calls ``open_run`` and ``write_single_point``; the CLI
    must write the same log from them, not from a copy of them."""
    from xtal.cli import main
    from xtal.core import p1
    from xtal.ff import ENGINES
    from xtal.ff import record as ff_record

    source = tmp_path / "rutile.cif"
    write_cif(rutile, source)
    structure = read_cif(source)                # as the CLI sees it
    options = ENGINES.get("uff").coerce({})
    calculator = ENGINES.get("uff")(structure, **options)
    cell = p1.expand(structure)
    result = calculator.compute(cell.cart, structure.lattice.matrix)
    ff_record.write_single_point(ff_record.open_run(
        entry, "uff", "single-point", structure, calculator,
        options=options), result)
    root = tmp_path / "cli-ws"
    main(["energy", str(source), "--workspace", str(root)])

    ours, = entry.runs()
    theirs, = Workspace.open(root).entries()[0].runs()
    assert ours.name == theirs.name == "uff-single-point-001"
    assert _stable(ours.log_path.read_text()) \
        == _stable(theirs.log_path.read_text())



# ------------------------------------------------- the same file

def test_no_path_is_not_the_current_directory():
    """``Path("").resolve()`` is the working directory, which every
    unsaved document would then have matched."""
    assert resolved(None) is None
    assert resolved("") is None


def test_a_symlink_is_the_file_it_points_at(tmp_path):
    target = tmp_path / "a.cif"
    target.write_text("data_a\n")
    link = tmp_path / "b.cif"
    link.symlink_to(target)

    assert resolved(link) == resolved(target)


def test_a_path_that_cannot_be_resolved_still_matches_itself(
        tmp_path, monkeypatch):
    """The tab set said None here and the tree kept the spelling; None
    matches nothing, so the tree was right."""
    def refuse(self, strict=False):
        raise OSError("the volume went away")

    monkeypatch.setattr(type(tmp_path), "resolve", refuse)

    assert resolved(tmp_path / "x.cif") == tmp_path / "x.cif"
