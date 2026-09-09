"""The dialog the application opens with, and the launch that shows it.

The one dialog the rest of the suite never meets: it is called from
``xtalapp.main.main`` and not from ``MainWindow.__init__``, so that a
window built by hand -- which is every other widget test -- still opens
without one.  Which means these tests have to drive it directly.  They
never call ``exec``; the autouse guard in conftest patches it to raise,
and reaching it here would be the same bug it is there.
"""

from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QDialog  # noqa: E402

from xtal.workspace import Workspace  # noqa: E402
from xtalapp.dialogs.workspace_chooser import (  # noqa: E402
    _PATH,
    WorkspaceChooser,
)
from xtalapp.settings import AppSettings  # noqa: E402


@pytest.fixture
def settings(tmp_path):
    settings = AppSettings("CrystalBuilderTest",
                           f"Chooser{tmp_path.name}")
    settings.last_workspace = ""
    settings.default_workspace_root = str(tmp_path / "Crystal Builder")
    return settings


@pytest.fixture
def chooser(qtbot, settings):
    def build():
        dialog = WorkspaceChooser(settings)
        qtbot.addWidget(dialog)
        return dialog
    return build


def _rows(dialog):
    return [dialog.list.item(i).data(_PATH)
            for i in range(dialog.list.count())]


def test_a_first_run_is_offered_the_default_workspace(chooser,
                                                      tmp_path):
    """Somebody who has never opened this has no recent workspaces,
    and an empty list is a dialog with no way forward."""
    dialog = chooser()

    assert _rows(dialog) == [str(tmp_path / "Crystal Builder")]
    assert "will be created" in dialog.list.item(0).text()


def test_continuing_on_a_folder_that_is_not_there_yet_makes_it(
        chooser, tmp_path):
    dialog = chooser()

    dialog._accept()

    assert dialog.workspace is not None
    assert dialog.workspace.root == tmp_path / "Crystal Builder"
    assert Workspace.is_workspace(dialog.workspace.root)
    assert dialog.result() == QDialog.Accepted


def test_the_recent_workspaces_are_listed_newest_first(chooser,
                                                       settings,
                                                       tmp_path):
    for name in ("one", "two", "three"):
        Workspace.create(tmp_path / name)
        settings.add_recent_workspace(tmp_path / name)

    assert [Path(p).name for p in _rows(chooser())] == \
        ["three", "two", "one"]


def test_the_workspace_from_last_time_is_the_one_selected(chooser,
                                                          settings,
                                                          tmp_path):
    """So that Return is the answer for somebody who has one."""
    for name in ("one", "two"):
        Workspace.create(tmp_path / name)
        settings.add_recent_workspace(tmp_path / name)
    settings.last_workspace = str(tmp_path / "one")

    dialog = chooser()

    assert dialog._chosen() == tmp_path / "one"


def test_a_folder_that_cannot_be_made_leaves_the_dialog_open(
        chooser, settings, tmp_path):
    """There is no window behind this to report into, so the error is
    shown here and the question goes on being asked."""
    # A plain file where the default workspace would go, which is the
    # same shape as a folder there is no permission to write in.
    (tmp_path / "Crystal Builder").write_text("in the way\n")
    dialog = chooser()

    dialog._accept()

    assert dialog.workspace is None
    assert not dialog.result()
    assert not dialog.error.isHidden()
    assert "Crystal Builder" in dialog.error.text()


def test_an_ordinary_folder_is_not_opened_as_a_workspace(chooser,
                                                         settings,
                                                         tmp_path):
    """Open Other... on a folder with no marker in it says so rather
    than adopting somebody's Documents folder."""
    plain = tmp_path / "just a folder"
    plain.mkdir()
    dialog = chooser()

    dialog._accept_choice(plain, create=False)

    assert dialog.workspace is None
    assert not dialog.error.isHidden()


def test_a_recent_workspace_that_is_there_shows_when_it_was_used(
        chooser, settings, tmp_path):
    Workspace.create(tmp_path / "ws")
    settings.add_recent_workspace(tmp_path / "ws")

    assert "just now" in chooser().list.item(0).text()


def test_return_continues_rather_than_quitting(chooser):
    """Quit is added first and takes the default on macOS unless it is
    told twice not to.  Return ending the launch is not a mistake
    anybody makes twice, but they only need to make it once."""
    dialog = chooser()

    assert dialog.go.isDefault()
    assert not dialog.quit.isDefault()


def test_a_row_says_where_the_folder_is_without_the_home_path(
        chooser, settings, tmp_path, monkeypatch):
    """The path is what gets elided, so it goes last and loses the
    part every row would have shared."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    Workspace.create(tmp_path / "work" / "ws")
    settings.add_recent_workspace(tmp_path / "work" / "ws")

    assert "~/work" in chooser().list.item(0).text()


# -- the launch ---------------------------------------------------------

def test_a_file_inside_a_workspace_is_not_asked_about(settings,
                                                      tmp_path,
                                                      monkeypatch):
    """Double-clicking a structure in a folder this application filled
    has one sensible answer, and a dialog in front of it is a dialog
    between a double-click and the crystal."""
    from xtalapp import main as entry
    workspace = Workspace.create(tmp_path / "ws")
    entry_folder = workspace.add_document("rutile")
    structure = entry_folder.path / "rutile.cif"
    structure.write_text("data_rutile\n")
    monkeypatch.setattr(WorkspaceChooser, "ask",
                        lambda *a, **k: pytest.fail("asked anyway"))

    chosen = entry.choose_workspace([str(structure)], settings)

    assert chosen == workspace


def test_a_file_from_anywhere_else_is_asked_about(settings, tmp_path,
                                                 monkeypatch):
    from xtalapp import main as entry
    loose = tmp_path / "downloaded.cif"
    loose.write_text("data_x\n")
    asked = []
    monkeypatch.setattr(WorkspaceChooser, "ask",
                        lambda *a, **k: asked.append(True))

    entry.choose_workspace([str(loose)], settings)

    assert asked == [True]


def test_a_file_the_desktop_sent_counts_as_much_as_an_argument(
        settings, tmp_path, monkeypatch):
    """On macOS a double-click is a QFileOpenEvent and never an
    argument, so reading argv alone would skip the shortcut on the one
    platform where nobody launches this from a shell."""
    from xtalapp import main as entry
    workspace = Workspace.create(tmp_path / "ws")
    folder = workspace.add_document("rutile")
    structure = folder.path / "rutile.cif"
    structure.write_text("data_rutile\n")
    monkeypatch.setattr(WorkspaceChooser, "ask",
                        lambda *a, **k: pytest.fail("asked anyway"))

    # What main() passes: the command line, then the queue.
    chosen = entry.choose_workspace([] + [str(structure)], settings)

    assert chosen == workspace


def test_quitting_from_the_chooser_opens_no_window(settings,
                                                   monkeypatch):
    from xtalapp import main as entry
    monkeypatch.setattr(WorkspaceChooser, "ask", lambda *a, **k: None)

    assert entry.choose_workspace([], settings) is None
