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

from PySide6.QtWidgets import QDialog, QMenu  # noqa: E402

from xtal.workspace import Workspace  # noqa: E402
from xtalapp.dialogs.workspace_chooser import (  # noqa: E402
    _DETAIL,
    _NAME,
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


def test_return_continues_rather_than_quitting(chooser, qtbot):
    """Quit is added first and takes the default on macOS unless it is
    told twice not to.  Return ending the launch is not a mistake
    anybody makes twice, but they only need to make it once."""
    dialog = chooser()

    assert dialog.go.isDefault()
    assert not dialog.quit.isDefault()

    # And still once it is on screen, which is when a dialog chooses
    # its own default if the one it was given never reached it: that
    # is how Find symmetry's Return came to press Close.
    dialog.show()
    qtbot.waitExposed(dialog)
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


def test_a_recent_workspace_is_one_line_with_its_name_first(
        chooser, settings, tmp_path):
    """Two lines a row made the list half as long as the dialog could
    show; the name is what a row is recognised by, so it leads."""
    Workspace.create(tmp_path / "thesis")
    settings.add_recent_workspace(tmp_path / "thesis")
    dialog = chooser()
    item = dialog.list.item(0)

    assert "\n" not in item.text()
    assert item.text().startswith("thesis")
    assert item.data(_NAME) == "thesis"
    assert "just now" in item.data(_DETAIL)
    assert dialog.list.visualItemRect(item).height() < (
        2 * dialog.fontMetrics().height())


def test_the_chooser_shows_the_version_it_will_open(chooser):
    """"Is this the build I just installed" is asked at this dialog,
    and About is a window further in."""
    import xtal

    dialog = chooser()

    # A development version's local part is on a line of its own.
    shown = dialog.version.text().replace("\n", "")
    assert xtal.__version__ in shown


def test_the_chooser_draws_the_art_that_ships_with_it():
    """``resources/chooser`` holds a copy of the application icon,
    because ``packaging/`` does not travel with a bundle; a copy is
    something that drifts, so this is what notices."""
    from xtalapp.dialogs.workspace_chooser import ART
    root = ART.parents[1]

    assert (ART / "app.svg").read_bytes() == (
        root / "packaging" / "icons" / "app.svg").read_bytes()
    assert (ART / "framework.png").stat().st_size > 10_000


def test_open_sample_opens_the_selected_workspace_and_names_the_sample(
        chooser, settings, tmp_path):
    for name in ("one", "two"):
        Workspace.create(tmp_path / name)
        settings.add_recent_workspace(tmp_path / name)
    dialog = chooser()
    dialog.list.setCurrentRow(_rows(dialog).index(str(tmp_path / "one")))

    dialog.choose_sample("mof5")

    assert dialog.result() == QDialog.Accepted
    assert dialog.workspace.root == tmp_path / "one"
    assert dialog.sample == "mof5"


def test_open_sample_offers_every_sample_that_is_installed(chooser):
    from xtalapp import samples

    menu = chooser().sample_button.menu()

    def entries(menu):
        # Not ``QAction.menu()``, which can delete the submenu it hands
        # back; see test_samples.py.
        below = {m.menuAction(): m for m in menu.findChildren(QMenu)}
        for action in menu.actions():
            if action in below:
                yield from entries(below[action])
            elif not action.isSeparator():
                yield action.text()

    assert list(entries(menu)) == [s.label for s in samples.installed()]


def test_open_sample_on_a_folder_that_cannot_be_made_keeps_asking(
        chooser, tmp_path):
    (tmp_path / "Crystal Builder").write_text("in the way\n")
    dialog = chooser()

    dialog.choose_sample("mof5")

    assert dialog.workspace is None
    assert not dialog.result()
    assert not dialog.error.isHidden()
    # Continue after that is Continue, not a sample asked for once.
    assert dialog.sample is None


def test_open_sample_is_disabled_without_the_samples(chooser,
                                                     monkeypatch):
    """A wheel installed with pip has no resources/ folder, and seven
    menu entries that do nothing are worse than one sentence."""
    from xtalapp import samples
    monkeypatch.setattr(samples, "installed", lambda: ())

    button = chooser().sample_button

    assert not button.isEnabled()
    assert button.toolTip() == samples.MISSING


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

    assert chosen == (workspace, None)


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

    assert chosen == (workspace, None)


def test_quitting_from_the_chooser_opens_no_window(settings,
                                                   monkeypatch):
    from xtalapp import main as entry
    monkeypatch.setattr(WorkspaceChooser, "ask",
                        lambda *a, **k: (None, None))

    workspace, _sample = entry.choose_workspace([], settings)
    assert workspace is None


def test_main_opens_the_sample_the_chooser_returned(qtbot, settings,
                                                    tmp_path,
                                                    monkeypatch):
    """The chooser only names the sample; the window opens it, once it
    exists, through Open Sample -- so it is copied into the workspace
    like any other file."""
    from tests.test_app_shell import StubViewport
    from xtalapp import main as entry
    workspace = Workspace.create(tmp_path / "ws")
    monkeypatch.setattr(WorkspaceChooser, "ask",
                        lambda *a, **k: (workspace, "mof5"))

    chosen, sample = entry.choose_workspace([], settings)
    window = entry.open_window(chosen, sample,
                               viewport_factory=StubViewport,
                               settings=settings)
    qtbot.addWidget(window)

    document = window.current_document()
    assert document is not None
    assert document.path.is_relative_to(workspace.root)
    assert document.path.name == "MOF-5.cif"


def test_ask_hands_back_what_the_dialog_chose(settings, tmp_path,
                                              monkeypatch):
    """``ask`` is the one call main.py makes, and it had never been
    called: every test here drives the widget and stops short of it.
    exec is patched per class rather than left to the conftest guard,
    which would raise -- this is the dialog the suite never meets."""
    Workspace.create(tmp_path / "ws")
    settings.add_recent_workspace(tmp_path / "ws")
    settings.last_workspace = str(tmp_path / "ws")

    def accept(dialog):
        dialog._accept()
        return dialog.result()

    monkeypatch.setattr(WorkspaceChooser, "exec", accept)

    workspace, sample = WorkspaceChooser.ask(settings)

    assert workspace is not None
    assert workspace.root == tmp_path / "ws"
    assert sample is None


def test_quitting_the_chooser_is_no_workspace(settings, monkeypatch):
    """None is how main.py knows not to open a window at all."""
    monkeypatch.setattr(WorkspaceChooser, "exec",
                        lambda dialog: QDialog.Rejected)

    assert WorkspaceChooser.ask(settings) == (None, None)
