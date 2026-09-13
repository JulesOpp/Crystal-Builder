"""A file that is already open is not opened again.

Two tabs over the same bytes are two documents with two undo stacks
editing what the user thinks is one structure: whichever is saved last
wins and the other one's work is gone, with nothing having said so.

The interesting half is what counts as "the same file".  Not the name
-- ``data/a/MFU4l.cif`` and ``data/b/MFU4l.cif`` are two crystals that
happen to share one -- and not the string either, because a symlink and
``/var`` versus ``/private/var`` are one file spelled two ways.
"""

import os

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QWidget  # noqa: E402

from xtal.io import write_cif  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Once{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


@pytest.fixture
def two_folders(tmp_path, rutile):
    """The same crystal written into two directories under one name."""
    for name in ("a", "b"):
        (tmp_path / name).mkdir()
        write_cif(rutile, tmp_path / name / "rutile.cif")
    return tmp_path


def test_opening_it_twice_gives_one_document(window, two_folders):
    first = window.open_path(two_folders / "a" / "rutile.cif")
    again = window.open_path(two_folders / "a" / "rutile.cif")

    assert again is first
    assert window.tabs.count() == 1
    assert len(window.documents) == 1


def test_the_tab_it_is_already_in_is_raised(window, two_folders):
    """The user asked to see that file, and showing it to them is the
    answer -- not a dialog, and not a refusal."""
    first = window.open_path(two_folders / "a" / "rutile.cif")
    second = window.open_path(two_folders / "b" / "rutile.cif")
    assert window.tabs.currentIndex() == 1

    window.open_path(two_folders / "a" / "rutile.cif")

    assert window.tabs.currentIndex() == 0
    assert window.current_document() is first
    assert second is not first


def test_it_says_so(window, two_folders, qtbot):
    window.open_path(two_folders / "a" / "rutile.cif")
    window.open_path(two_folders / "a" / "rutile.cif")
    assert "already open" in window.statusBar().currentMessage()


def test_two_files_of_the_same_name_are_two_documents(window,
                                                      two_folders):
    """Refusing the second would be worse than the bug."""
    first = window.open_path(two_folders / "a" / "rutile.cif")
    second = window.open_path(two_folders / "b" / "rutile.cif")

    assert second is not first
    assert window.tabs.count() == 2


def test_a_symlink_to_it_is_the_same_file(window, two_folders):
    os.symlink(two_folders / "a", two_folders / "link")
    first = window.open_path(two_folders / "a" / "rutile.cif")

    assert window.open_path(two_folders / "link" / "rutile.cif") is first
    assert window.tabs.count() == 1


def test_a_relative_spelling_is_the_same_file(window, two_folders,
                                              monkeypatch):
    first = window.open_path(two_folders / "a" / "rutile.cif")
    monkeypatch.chdir(two_folders)

    assert window.open_path("a/rutile.cif") is first
    assert window.tabs.count() == 1


def test_a_document_that_was_never_saved_matches_nothing(window,
                                                         two_folders):
    """``document_for`` must not treat two path-less documents as each
    other, which a naive equality on ``None`` would."""
    from xtalapp.document import Document

    window.add_document(Document())
    window.add_document(Document())
    assert window.document_for(None) is None
    assert window.tabs.count() == 2

    opened = window.open_path(two_folders / "a" / "rutile.cif")
    assert window.document_for(two_folders / "a" / "rutile.cif") is opened


def test_the_workspace_tree_goes_through_the_same_door(window,
                                                       two_folders):
    """Every route in -- the Open dialog, the recent list, the tree,
    drag and drop, the command line -- is ``open_path``."""
    path = str(two_folders / "a" / "rutile.cif")
    first = window.open_path(path)

    window.open_artifact("structure", path)

    assert window.tabs.count() == 1
    assert window.current_document() is first


# ============================================================ the copy
#
# Opening a structure from outside a workspace copies it in, so the
# file the user opened and the node the tree draws underneath it are
# two paths to one crystal.  Double-clicking that node used to open a
# second document over the same atoms -- the duplicate-tab failure this
# file is about, arriving through the one route that did not check for
# it.

@pytest.fixture
def workspace_window(window, tmp_path, rutile):
    """A window with a workspace open and a structure opened from
    *outside* it, so the workspace holds a copy."""
    from xtal.workspace import Workspace

    outside = tmp_path / "elsewhere"
    outside.mkdir()
    source = outside / "rutile.cif"
    write_cif(rutile, source)
    Workspace.create(tmp_path / "ws")
    window.set_workspace(tmp_path / "ws")
    document = window.open_path(source)
    return window, document, source


def test_the_workspaces_copy_is_the_document_that_made_it(
        workspace_window):
    window, document, source = workspace_window
    copy = document.entry.structure_path

    assert copy is not None
    assert copy.resolve() != source.resolve()    # genuinely two files
    assert window.document_for(copy) is document


def test_double_clicking_the_copy_raises_the_tab_it_is_already_in(
        workspace_window):
    window, document, _source = workspace_window
    copy = document.entry.structure_path

    window.open_artifact("structure", str(copy))

    assert window.tabs.count() == 1
    assert window.current_document() is document
    assert "already open" in window.statusBar().currentMessage()


def test_a_runs_output_still_earns_a_tab_of_its_own(workspace_window,
                                                    rutile):
    """Only the entry's *structure* file is the document's other name.
    ``final.cif`` is a different geometry and opening it beside the
    input is the whole point of having it."""
    window, document, _source = workspace_window
    folder = document.entry.next_run("uff", "optimise")
    final = folder.path / "final.cif"
    write_cif(rutile, final)

    assert window.document_for(final) is None
    window.open_artifact("final", str(final))
    assert window.tabs.count() == 2


def test_reopening_the_file_it_was_copied_from_finds_the_same_tab(
        workspace_window):
    """The tab is over the workspace's copy now, so the file the user
    opened is the one that is spelled differently -- and opening it
    again must still be that tab and not a second one over the same
    atoms."""
    window, document, source = workspace_window

    window.open_path(source)

    assert window.tabs.count() == 1
    assert window.current_document() is document
    assert "already open" in window.statusBar().currentMessage()


def test_a_project_saved_beside_the_structure_names_the_tab(
        workspace_window):
    """"rutile.cif is already open" over a tab called rutile.xtalproj
    reads as a bug; saying which tab does not."""
    window, document, _source = workspace_window
    document.save(document.entry.project_path)

    window.open_path(document.entry.structure_path)

    message = window.statusBar().currentMessage()
    assert "already open, as" in message
    assert document.title in message


def test_reopening_a_file_does_not_name_a_tab_spelled_the_same(
        workspace_window):
    """The tab is over the workspace's copy, a different path with the
    same name, and the message said "rutile.cif is already open, as
    rutile.cif" -- which reads as though it were not the same file."""
    window, document, source = workspace_window
    assert document.title == source.name

    window.open_path(source)

    assert window.statusBar().currentMessage() == (
        "rutile.cif is already open")
