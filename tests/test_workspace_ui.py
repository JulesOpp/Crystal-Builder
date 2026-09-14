"""The workspace on screen: the tree, the transport bar, the log.

The window is driven with the stub viewport from test_app_shell, so
none of this needs a display.
"""

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QDialog  # noqa: E402

from tests.test_app_shell import StubViewport  # noqa: E402
from xtal.io import read_cif, write_cif  # noqa: E402
from xtal.io.trajectory import (  # noqa: E402
    frame_of,
    write_trajectory,
)
from xtal.workspace import Workspace  # noqa: E402
from xtalapp.docks.workspace import ARTIFACT_ROLE  # noqa: E402
from xtalapp.document import PlaybackActive  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


@pytest.fixture
def settings(tmp_path):
    settings = AppSettings("CrystalBuilderTest",
                           f"Workspace{tmp_path.name}")
    settings.clear_recent_files()
    settings.last_directory = str(tmp_path)
    settings.last_workspace = ""
    return settings


@pytest.fixture
def window(qtbot, settings):
    win = MainWindow(viewport_factory=StubViewport, settings=settings)
    qtbot.addWidget(win)
    return win


@pytest.fixture
def opened(window, tmp_path, rutile):
    """A workspace, with rutile opened into it."""
    source = tmp_path / "rutile.cif"
    write_cif(rutile, source)
    window.set_workspace(tmp_path / "ws", create=True)
    document = window.open_path(source)
    return window, document


@pytest.fixture
def trajectory_file(tmp_path, rutile):
    frames = []
    for step in range(5):
        moved = rutile.copy()
        moved.set_frac(1, [0.3053 + 0.004 * step,
                           0.3053 + 0.004 * step, 0.0])
        frames.append(frame_of(moved, step=step, energy=-10.0 + step,
                               max_force=1.0 / (step + 1)))
    return write_trajectory(frames, tmp_path / "run.extxyz")


# ==================================================================
#  THE TREE
# ==================================================================

def _rows(model, parent=None):
    from PySide6.QtCore import QModelIndex
    parent = QModelIndex() if parent is None else parent
    return [model.index(r, 0, parent)
            for r in range(model.rowCount(parent))]


def _labels(model, parent=None):
    return [model.itemFromIndex(i).text()
            for i in _rows(model, parent)]


def test_an_opened_structure_becomes_the_root_of_the_tree(opened):
    window, document = opened
    tree = window.file_dock.tree

    assert _labels(tree.model_) == ["rutile"]
    assert document.entry is not None
    assert document.entry.name == "rutile"
    # the copy, so the workspace is whole
    assert (document.entry.path / "rutile.cif").is_file()


def test_a_run_appears_underneath_the_structure(opened):
    window, document = opened
    with document.entry.next_run("uff", "optimise") as folder:
        folder.log().write("hello")
        folder.write_final(document.structure)
    window.refresh_workspace()

    tree = window.file_dock.tree
    entry_row, = _rows(tree.model_)
    children = _labels(tree.model_, entry_row)
    assert "rutile.cif" in children
    assert "uff-optimise-001" in children

    run_row = _rows(tree.model_, entry_row)[-1]
    assert [t.split()[0] for t in _labels(tree.model_, run_row)] == \
        ["final.cif", "run.log"]


def test_the_tree_says_what_a_node_is_not_what_it_is_called(opened):
    """A .cif that is a run's output and a .cif that is the input want
    the same viewer and different labelling."""
    window, document = opened
    with document.entry.next_run("uff", "optimise") as folder:
        folder.write_final(document.structure)
    window.refresh_workspace()

    tree = window.file_dock.tree
    kinds = {}
    for index in tree._walk():
        payload = tree.model_.itemFromIndex(index).data(ARTIFACT_ROLE)
        if payload:
            kinds[Path(payload[1]).name] = payload[0]
    assert kinds["rutile.cif"] == "structure"
    assert kinds["final.cif"] == "final"


def test_a_project_written_and_reread_gives_the_identical_tree(
        opened, qtbot):
    window, document = opened
    with document.entry.next_run("uff", "optimise") as folder:
        folder.log().write("a run")
        folder.write_final(document.structure)

    written = document.save(document.entry.project_path)
    before = _tree_text(window)

    window.close_document(0)
    reopened = window.open_path(written)
    assert reopened.entry is not None
    assert reopened.entry.path == document.entry.path
    assert _tree_text(window) == before


def _tree_text(window) -> list:
    """Every row of the tree, flattened, with its kind."""
    window.refresh_workspace()
    tree = window.file_dock.tree
    out = []
    for index in tree._walk():
        item = tree.model_.itemFromIndex(index)
        payload = item.data(ARTIFACT_ROLE)
        out.append((item.text(), payload[0] if payload else None))
    return sorted(out)


def test_the_workspace_is_reopened_next_time(tmp_path, settings,
                                             qtbot, rutile):
    source = tmp_path / "rutile.cif"
    write_cif(rutile, source)
    first = MainWindow(viewport_factory=StubViewport,
                       settings=settings)
    qtbot.addWidget(first)
    first.set_workspace(tmp_path / "ws", create=True)
    first.open_path(source)

    second = MainWindow(viewport_factory=StubViewport,
                        settings=settings)
    qtbot.addWidget(second)
    assert second.workspace is not None
    assert second.workspace.root == tmp_path / "ws"
    assert _labels(second.file_dock.tree.model_) == ["rutile"]


def test_a_fresh_window_makes_the_workspace_it_needs(window, rutile,
                                                    tmp_path):
    """The application does not let anybody work without one.

    A structure opened with no workspace used to open, run and leave
    nothing behind.  That was a deliberate trade -- a folder created
    behind somebody's back is one they find later and do not
    recognise -- and it was the wrong way round: what got lost was the
    framework somebody had just built and the run they had just
    watched finish, and the status bar sentence saying so had scrolled
    past before the tab was closed.
    """
    assert window.workspace is not None
    assert window.workspace.root == tmp_path / "Crystal Builder"
    assert Workspace.is_workspace(window.workspace.root)

    source = tmp_path / "rutile.cif"
    write_cif(rutile, source)
    assert window.open_path(source).entry is not None


def test_switching_workspace_closes_the_tabs_of_the_old_one(
        opened, tmp_path):
    """A tab is a structure *of* the workspace it was opened in."""
    window, _document = opened
    assert window.tabs.count() == 1

    window.workspace_shell.switch_workspace(tmp_path / "other",
                                            create=True)

    assert window.workspace.root == tmp_path / "other"
    assert window.tabs.count() == 0
    assert window.documents == []


def test_a_run_after_switching_is_filed_in_the_new_workspace(
        opened, tmp_path, rutile):
    """The bug this closes: a document carried across a switch kept
    the entry it was given, so its next run was filed in the folder
    the user had walked away from."""
    window, _document = opened
    source = tmp_path / "rutile.cif"

    window.workspace_shell.switch_workspace(tmp_path / "other",
                                            create=True)
    document = window.open_path(source)

    assert document.entry is not None
    assert document.entry.path.parent == tmp_path / "other"


def test_a_workspace_that_will_not_open_costs_nobody_their_tabs(
        opened, tmp_path):
    """Opened first, closed second: a folder that is not a workspace
    must not already have thrown the work away."""
    window, _document = opened
    (tmp_path / "not a workspace").mkdir()

    assert window.workspace_shell.switch_workspace(
        tmp_path / "not a workspace") is None
    assert window.workspace.root == tmp_path / "ws"
    assert window.tabs.count() == 1


def test_switching_to_the_workspace_already_open_changes_nothing(
        opened, tmp_path):
    window, document = opened

    window.workspace_shell.switch_workspace(tmp_path / "ws")

    assert window.tabs.count() == 1
    assert window.current_document() is document


def test_a_new_document_gets_a_folder_of_its_own(window):
    """Not untitled and nowhere: a structure with nowhere to be is one
    whose first run has nowhere to land."""
    first = window.new_document()
    second = window.new_document()

    assert first.entry.name == "untitled"
    assert second.entry.name == "untitled-2"
    assert first.path == first.entry.path / "untitled.cif"
    assert first.path.is_file()


def test_reopening_a_workspace_reopens_its_tabs(tmp_path, settings,
                                                qtbot, rutile):
    """The workspace is the session -- there is no preference for it
    any more, and entering one is where the tabs come back."""
    source = tmp_path / "rutile.cif"
    write_cif(rutile, source)
    first = MainWindow(viewport_factory=StubViewport,
                       settings=settings)
    qtbot.addWidget(first)
    first.set_workspace(tmp_path / "ws", create=True)
    document = first.open_path(source)
    first.close()

    second = MainWindow(viewport_factory=StubViewport,
                        settings=settings)
    qtbot.addWidget(second)

    assert second.tabs.count() == 1
    assert second.current_document().path == document.path


def test_switching_back_brings_the_first_workspace_tabs_back(
        opened, tmp_path):
    window, document = opened

    window.workspace_shell.switch_workspace(tmp_path / "other",
                                            create=True)
    assert window.tabs.count() == 0
    window.workspace_shell.switch_workspace(tmp_path / "ws")

    assert window.tabs.count() == 1
    assert window.current_document().path == document.path


def test_a_remembered_tab_whose_file_has_gone_is_skipped(opened,
                                                         tmp_path):
    """A workspace must still open when a structure was deleted from
    underneath it."""
    window, document = opened
    entry = document.entry
    window.workspace_shell.switch_workspace(tmp_path / "other",
                                            create=True)
    for path in entry.path.iterdir():
        path.unlink()

    window.workspace_shell.switch_workspace(tmp_path / "ws")

    assert window.tabs.count() == 0


# -- Save File ----------------------------------------------------------

def test_save_file_converts_a_structure_to_the_project_beside_it(
        opened):
    """A CIF cannot hold a measurement, a plane or the view it was
    being looked at in, so the first save is a conversion: the tab
    becomes the project, and the CIF it was read from is left alone.
    Nothing is asked, because there is nowhere else it could go."""
    window, document = opened
    cif = document.path
    before = cif.read_text()

    window.save_document()

    assert document.path == cif.with_suffix(".xtalproj")
    assert document.path.is_file()
    assert cif.is_file() and cif.read_text() == before
    assert not document.modified
    assert document.path.parent == document.entry.path


def test_saving_again_writes_the_same_file_without_asking(opened):
    """The autouse guard raises on any modal, so reaching one here is
    the failure -- Save File never stops to ask where."""
    window, document = opened
    window.save_document()
    target = document.path

    window.save_document()

    assert document.path == target


def test_the_confirm_preference_asks_before_writing_over(opened,
                                                         monkeypatch):
    """Only over a file that is already there: the first save is
    creating something and has nothing to confirm."""
    from PySide6.QtWidgets import QMessageBox
    window, document = opened
    window.settings.confirm_overwrite = True
    asked = []
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *a, **k: asked.append(a[2]) or QMessageBox.Yes)

    window.save_document()
    assert asked == []                     # created, not overwritten

    window.save_document()
    assert len(asked) == 1
    assert document.path.name in asked[0]


def test_answering_no_leaves_the_file_as_it_was(opened, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    window, document = opened
    window.save_document()
    written = document.path.read_bytes()
    window.settings.confirm_overwrite = True
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.No)

    window.save_document()

    assert document.path.read_bytes() == written


def test_a_numbered_entry_saves_beside_its_own_file(window, tmp_path,
                                                    rutile, quartz):
    """Two structures called rutile give entries rutile and rutile-2,
    and both hold a file called rutile.cif.  The project is named
    after the *file*, so a second save finds the first one again."""
    window.set_workspace(tmp_path / "ws", create=True)
    for folder, structure in (("a", rutile), ("b", quartz)):
        (tmp_path / folder).mkdir()
        write_cif(structure, tmp_path / folder / "rutile.cif")
    window.open_path(tmp_path / "a" / "rutile.cif")
    second = window.open_path(tmp_path / "b" / "rutile.cif")

    window.save_document()

    assert second.entry.name == "rutile-2"
    assert second.path == second.entry.path / "rutile.xtalproj"
    assert second.path.is_file()


def test_a_saved_project_is_the_tab_the_workspace_reopens(opened,
                                                          tmp_path):
    """The session records the file the tab is, so the view and the
    measurements come back rather than the bare crystal."""
    window, document = opened
    window.save_document()
    saved = document.path

    window.workspace_shell.switch_workspace(tmp_path / "other",
                                            create=True)
    window.workspace_shell.switch_workspace(tmp_path / "ws")

    assert window.tabs.count() == 1
    assert window.current_document().path == saved


def test_the_title_says_which_workspace_this_is(opened):
    window, _document = opened

    assert "ws" in window.windowTitle()


def test_close_all_closes_every_tab(opened, tmp_path, quartz):
    window, _document = opened
    other = tmp_path / "quartz.cif"
    write_cif(quartz, other)
    window.open_path(other)
    assert window.tabs.count() == 2

    window.close_all_documents()

    assert window.tabs.count() == 0


def test_a_workspace_that_cannot_be_made_still_opens_a_window(
        qtbot, settings, rutile, tmp_path, monkeypatch):
    """The fallback, and why every ``workspace is None`` branch
    downstream is still reachable and still means what it said.

    A window that will not open is worse than a window with nowhere to
    put its runs, so a home folder that cannot be written to is a
    status bar message and not a refusal to start.
    """
    blocked = tmp_path / "blocked"
    blocked.write_text("a file where the workspace would go")
    monkeypatch.setenv("XTAL_WORKSPACE_ROOT", str(blocked))

    win = MainWindow(viewport_factory=StubViewport, settings=settings)
    qtbot.addWidget(win)
    assert win.workspace is None

    source = tmp_path / "rutile.cif"
    write_cif(rutile, source)
    document = win.open_path(source)
    assert document is not None
    assert document.entry is None


def test_a_structure_opened_with_no_workspace_says_so_and_makes_none(
        qtbot, settings, rutile, tmp_path, monkeypatch):
    """The degraded window makes no folder beside the file -- there was
    a preference for that, and it is gone -- and says, once, that the
    runs will not be kept."""
    blocked = tmp_path / "blocked"
    blocked.write_text("a file where the workspace would go")
    monkeypatch.setenv("XTAL_WORKSPACE_ROOT", str(blocked))
    win = MainWindow(viewport_factory=StubViewport, settings=settings)
    qtbot.addWidget(win)
    folder = tmp_path / "structures"
    folder.mkdir()
    source = folder / "rutile.cif"
    write_cif(rutile, source)

    win.open_path(source)

    assert win.workspace is None
    assert sorted(p.name for p in folder.iterdir()) == ["rutile.cif"]
    assert "no workspace open" in win.statusBar().currentMessage()


def test_the_browser_is_still_there(window, tmp_path):
    """Opening a file from somewhere else is how everything starts."""
    window.file_dock.set_browsing(True)
    assert window.file_dock.browsing
    window.file_dock.set_root(tmp_path)
    assert window.file_dock.root == tmp_path


# ==================================================================
#  RUNNING INTO IT
# ==================================================================

def test_an_optimisation_leaves_a_run_folder_behind(opened, qtbot):
    window, document = opened
    panel = window.ff_dock
    panel.set_document(document)
    panel.max_steps.setValue(3)
    panel.start()
    # `is_running` is set on the worker thread, so it is still False
    # the instant after start(); waiting for the panel to let go of
    # the worker waits for the finish handler as well.
    qtbot.waitUntil(lambda: panel.worker is None, timeout=20000)

    run, = document.entry.runs()
    assert run.log_path.exists()
    assert run.trajectory_path.exists()
    assert run.final_path.exists()
    assert read_cif(run.final_path).n_sites == 2

    from xtal.io.trajectory import read_trajectory
    trajectory = read_trajectory(run.trajectory_path)
    assert trajectory.n_frames >= 1
    assert trajectory.is_compatible(document.structure)
    # the log is on screen while it is written
    assert "Atom types" in window.log_dock.text


def test_a_single_point_leaves_a_log(opened):
    window, document = opened
    window.ff_dock.set_document(document)
    window.ff_dock.single_point()

    run, = document.entry.runs()
    assert run.name == "uff-single-point-001"
    assert "Energy" in run.log_path.read_text()
    assert not run.trajectory_path.exists()


def test_a_document_with_no_workspace_still_runs(window, rutile,
                                                 tmp_path):
    """The workspace that could not be made, reached the other way.

    A run with nowhere to write is not an error, it is a run that
    leaves nothing behind -- and the panel must not learn that from a
    traceback.
    """
    window.workspace_shell.workspace = None
    source = tmp_path / "rutile.cif"
    write_cif(rutile, source)
    document = window.open_path(source)
    window.ff_dock.set_document(document)
    window.ff_dock.single_point()           # must not raise
    assert document.entry is None


# ==================================================================
#  THE LOG
# ==================================================================

def test_the_log_view_tails_a_file_that_is_still_growing(window,
                                                         tmp_path):
    path = tmp_path / "run.log"
    path.write_text("first\n")
    window.log_dock.show_file(path)
    assert "first" in window.log_dock.text

    with path.open("a") as handle:
        handle.write("second\n")
    window.log_dock.poll()
    assert "second" in window.log_dock.text
    # appended, not reread: the scroll position is the whole point
    assert window.log_dock.text.count("first") == 1


def test_a_log_replaced_underneath_the_view_starts_again(window,
                                                         tmp_path):
    path = tmp_path / "run.log"
    path.write_text("a long first run\n")
    window.log_dock.show_file(path)
    path.write_text("new\n")
    window.log_dock.poll()
    assert window.log_dock.text.strip() == "new"


# ==================================================================
#  THE TRANSPORT BAR
# ==================================================================

def test_scrubbing_moves_the_atoms_without_editing_anything(
        opened, trajectory_file):
    window, document = opened
    bar = window.trajectory_dock
    bar.set_document(document)
    assert bar.open_path(trajectory_file)

    before = document.structure.frac.copy()
    bar.show_frame(4)
    assert not np.allclose(document.structure.frac, before)
    assert not document.modified          # a preview, and nothing more
    assert not document.can_undo


def test_playing_advances_and_stops_at_the_end(opened,
                                               trajectory_file, qtbot):
    window, document = opened
    bar = window.trajectory_dock
    bar.set_document(document)
    bar.open_path(trajectory_file)
    bar.speed.setCurrentIndex(3)          # as fast as it draws

    bar.play()
    qtbot.waitUntil(lambda: not bar.is_playing, timeout=5000)
    assert document.playback.index == document.playback.n_frames - 1


def test_looping_starts_again_rather_than_stopping(opened,
                                                  trajectory_file,
                                                  qtbot):
    window, document = opened
    bar = window.trajectory_dock
    bar.set_document(document)
    bar.open_path(trajectory_file)
    bar.loop.setChecked(True)
    bar.show_frame(document.playback.n_frames - 1)

    bar._advance()
    assert bar.is_playing is False         # the timer was never started
    assert document.playback.index == 0


def test_a_frame_is_not_an_editable_structure(opened,
                                              trajectory_file):
    """Scrubbing while an edit is half made would lose the edit at the
    next frame, so the document refuses."""
    window, document = opened
    window.trajectory_dock.set_document(document)
    window.trajectory_dock.open_path(trajectory_file)

    assert document.is_playing
    assert not window.actions_["add_atom_dialog"].isEnabled()
    assert not window.actions_["optimize"].isEnabled()
    with pytest.raises(PlaybackActive):
        document.wrap_into_cell()


def test_adopting_a_frame_is_one_undoable_edit(opened,
                                               trajectory_file):
    window, document = opened
    before = document.structure.frac.copy()
    bar = window.trajectory_dock
    bar.set_document(document)
    bar.open_path(trajectory_file)
    bar.show_frame(4)
    bar.adopt()

    assert not document.is_playing
    assert document.modified
    assert document.can_undo
    assert not np.allclose(document.structure.frac, before)

    document.undo()
    assert np.allclose(document.structure.frac, before)


def test_closing_a_trajectory_puts_the_atoms_back(opened,
                                                  trajectory_file):
    window, document = opened
    before = document.structure.frac.copy()
    bar = window.trajectory_dock
    bar.set_document(document)
    bar.open_path(trajectory_file)
    bar.show_frame(3)
    bar.close_trajectory()

    assert not document.is_playing
    assert np.allclose(document.structure.frac, before)
    assert not document.modified
    assert window.actions_["add_atom_dialog"].isEnabled()


def test_a_trajectory_of_another_crystal_is_refused(opened, quartz,
                                                    tmp_path):
    window, document = opened
    other = write_trajectory([frame_of(quartz)],
                             tmp_path / "quartz.extxyz")
    bar = window.trajectory_dock
    bar.set_document(document)

    assert not bar.open_path(other)
    assert not document.is_playing


def test_clicking_the_energy_trace_jumps_to_that_frame(
        opened, trajectory_file):
    """The plot and the trajectory are the same run seen two ways."""
    window, document = opened
    bar = window.trajectory_dock
    bar.set_document(document)
    bar.open_path(trajectory_file)

    # opening the trajectory filled the plot, so the click has
    # somewhere to land
    assert len(window.ff_dock.plot.history) == 5
    window.ff_dock.plot.pointClicked.emit(3)
    assert document.playback.index == 3
    assert window.ff_dock.plot.marker == 3


def test_the_tree_opens_each_artefact_as_what_it_is(opened,
                                                    trajectory_file):
    window, document = opened
    with document.entry.next_run("uff", "optimise") as folder:
        folder.log().write("a run")
    run, = document.entry.runs()

    window.open_artifact("log", str(run.log_path))
    assert "a run" in window.log_dock.text

    window.open_artifact("trajectory", str(trajectory_file))
    assert document.is_playing


# ==================================================================
#  SAVE AND EXPORT
# ==================================================================

def test_save_offers_the_project_inside_the_entry(opened):
    window, document = opened
    assert window._suggested_project(document) == \
        document.entry.project_path


def test_export_does_not_become_the_documents_file(opened, tmp_path,
                                                    monkeypatch):
    from xtalapp.dialogs.export import ExportDialog

    window, document = opened
    target = tmp_path / "copy.xyz"

    def stub(self, *args, **kwargs):
        self.format.setCurrentIndex(
            [self.format.itemData(i)
             for i in range(self.format.count())].index("xyz"))
        self.path.setText(str(target))
        return QDialog.Accepted

    monkeypatch.setattr(ExportDialog, "exec", stub)
    window.export_dialog()

    assert target.exists()
    assert document.path.name == "rutile.cif"
    assert window._last_export[0] == str(target)


def test_the_export_dialog_says_what_the_format_drops(opened):
    from xtal.io import FORMATS
    from xtalapp.dialogs.export import ExportDialog, keeps_text

    window, document = opened
    dialog = ExportDialog(document, window)
    assert "not written" in dialog.keeps.text()
    assert "occupancy" in keeps_text(FORMATS.get("xyz"))
    assert "symmetry" in keeps_text(FORMATS.get("cif"))


def test_exporting_a_selection_writes_only_those_atoms(opened,
                                                       tmp_path):
    window, document = opened
    document.select([0, 1])
    target = document.export(tmp_path / "part.cif",
                             selection_only=True)
    assert read_cif(target).n_sites == 2
