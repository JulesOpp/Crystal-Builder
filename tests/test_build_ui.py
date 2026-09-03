"""The molecule builder on screen: one dialog, two entries.

The build itself is headless and tested in
:mod:`tests.test_build_molecule`.  What is here is the shell: that the
Structure entry is greyed with a reason rather than missing, that the
dialog says what the button will do before it is pressed, and that the
same class serves the entry that opens a tab and the entry that pastes.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from tests.test_app_shell import StubViewport  # noqa: E402
from xtal.build import installed  # noqa: E402
from xtal.io import write_cif  # noqa: E402
from xtal.modules.build import BUILD, INSERT  # noqa: E402
from xtalapp.dialogs import module_dialog  # noqa: E402
from xtalapp.dialogs.build_molecule import (  # noqa: E402
    BuildMoleculeDialog,
)
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402

needs_rdkit = pytest.mark.skipif(
    not installed(),
    reason="RDKit is not installed; pip install "
           "'crystal-builder[build]'")


@pytest.fixture
def settings(tmp_path):
    settings = AppSettings("CrystalBuilderTest",
                           f"Build{tmp_path.name}")
    settings.clear_recent_files()
    settings.last_directory = str(tmp_path)
    settings.last_workspace = ""
    return settings


@pytest.fixture
def window(qtbot, settings):
    win = MainWindow(viewport_factory=StubViewport, settings=settings)
    qtbot.addWidget(win)
    return win


def opened(window, tmp_path, structure, name="crystal"):
    path = tmp_path / f"{name}.cif"
    write_cif(structure, path)
    return window.open_path(path)


def typed(dialog, qtbot, text):
    """Type a string and wait for the build the keystrokes start."""
    dialog.form.widgets["smiles"].setText(text)
    qtbot.waitUntil(lambda: not dialog._quiet.isActive(), timeout=5000)


# --------------------------------------------------- the shell entry

def test_the_insert_entry_needs_a_structure_to_insert_into(window):
    assert not window.actions_["insert_molecule"].isEnabled()


@needs_rdkit
def test_the_insert_entry_is_on_once_something_is_open(
        window, tmp_path, rutile):
    opened(window, tmp_path, rutile)
    assert window.actions_["insert_molecule"].isEnabled()


def test_without_rdkit_the_entry_is_greyed_and_says_what_to_install(
        window, tmp_path, rutile, monkeypatch):
    """Greyed with a sentence, not absent.  A menu entry that is
    simply not there leaves somebody looking for a feature they have
    read about with nothing to find."""
    import xtalapp.mainwindow as shell
    monkeypatch.setattr(shell, "rdkit_installed", lambda: False)
    opened(window, tmp_path, rutile)

    action = window.actions_["insert_molecule"]
    assert not action.isEnabled()
    assert "crystal-builder[build]" in action.toolTip()


def test_both_dialog_names_reach_the_one_class():
    """Two entries, one dialog: they differ in what the footer says
    and in whether connection points are on offer, and that is read
    off the action's name."""
    assert module_dialog("build-molecule") is BuildMoleculeDialog
    assert module_dialog("build-insert") is BuildMoleculeDialog


# ------------------------------------------------------- the dialog

@needs_rdkit
def test_the_footer_says_how_far_the_symmetry_will_multiply_it(
        window, qtbot, tmp_path, rutile):
    """Eleven atoms into Fm-3m is 2112 atoms and a window that stops
    responding.  PasteFragment.describe has always said so; the point
    of the footer is that it says so before the click."""
    opened(window, tmp_path, rutile)
    dialog = BuildMoleculeDialog(BUILD, INSERT, window)
    qtbot.addWidget(dialog)
    typed(dialog, qtbot, "c1ccccc1")

    assert "multiply" in dialog.footer.text()
    assert rutile.space_group.short_name in dialog.footer.text()
    assert dialog.ok_button.isEnabled()


@needs_rdkit
def test_the_footer_of_the_new_document_entry_talks_about_a_tab(
        window, qtbot, tmp_path, rutile):
    """The same dialog, the other action, and no paste in sight --
    what it builds is a document of its own whatever is in front."""
    opened(window, tmp_path, rutile)
    dialog = BuildMoleculeDialog(BUILD, BUILD.action("molecule"),
                                 window)
    qtbot.addWidget(dialog)
    typed(dialog, qtbot, "c1ccccc1")

    assert "tab of its own" in dialog.footer.text()
    assert "multiply" not in dialog.footer.text()


@needs_rdkit
def test_a_connection_point_is_refused_by_the_entry_that_pastes(
        window, qtbot):
    """A star in the box that drops a molecule into a cell meant
    something, and a benzene with a silent extra hydrogen is a worse
    answer than being told this box does not do connection points."""
    dialog = BuildMoleculeDialog(BUILD, INSERT, window)
    qtbot.addWidget(dialog)
    typed(dialog, qtbot, "[*:1]c1ccccc1")

    assert dialog.molecule is None
    assert not dialog.ok_button.isEnabled()
    assert "connection point" in dialog.footer.text()


@needs_rdkit
def test_a_connection_point_is_kept_by_the_entry_that_opens_a_tab(
        window, qtbot):
    dialog = BuildMoleculeDialog(BUILD, BUILD.action("molecule"),
                                 window)
    qtbot.addWidget(dialog)
    typed(dialog, qtbot, "[*:1]c1ccccc1[*:2]")

    assert dialog.molecule is not None
    assert dialog.molecule.n_connections == 2
    assert "2 connection point(s)" in dialog.footer.text()


@needs_rdkit
def test_a_string_that_is_not_a_molecule_says_so_and_stops_the_button(
        window, qtbot):
    dialog = BuildMoleculeDialog(BUILD, INSERT, window)
    qtbot.addWidget(dialog)
    typed(dialog, qtbot, "c1ccccc")

    assert dialog.molecule is None
    assert not dialog.ok_button.isEnabled()
    assert "RDKit" in dialog.footer.text()


@needs_rdkit
def test_one_build_for_a_burst_of_keystrokes(window, qtbot):
    """Typing a twenty-character SMILES must not be twenty embeds.
    The timer is restarted by each keystroke, so only the last one
    builds anything."""
    dialog = BuildMoleculeDialog(BUILD, INSERT, window)
    qtbot.addWidget(dialog)
    builds = []
    dialog._quiet.timeout.connect(lambda: builds.append(1))
    for text in ("C", "CC", "CCO"):
        dialog.form.widgets["smiles"].setText(text)
    qtbot.waitUntil(lambda: not dialog._quiet.isActive(), timeout=5000)

    assert len(builds) == 1
    assert dialog.molecule.formula == "C2H6O"


@needs_rdkit
def test_the_picture_follows_the_string(window, qtbot):
    dialog = BuildMoleculeDialog(BUILD, INSERT, window)
    qtbot.addWidget(dialog)
    typed(dialog, qtbot, "c1ccccc1")

    assert dialog.sketch.smiles() == "c1ccccc1"
    assert dialog.sketch.view.renderer().isValid()
    assert dialog.sketch.view.isVisibleTo(dialog.sketch)


@needs_rdkit
def test_an_unfinished_string_leaves_the_last_picture_up(window,
                                                         qtbot):
    """Every ring is unreadable while it is being typed, and blanking
    the drawing on the way through one makes the panel flicker for
    every molecule that has a ring in it."""
    dialog = BuildMoleculeDialog(BUILD, INSERT, window)
    qtbot.addWidget(dialog)
    typed(dialog, qtbot, "c1ccccc1")
    drawn = dialog.sketch.view.renderer().defaultSize()

    typed(dialog, qtbot, "c1ccccc1(")
    assert dialog.sketch.view.renderer().defaultSize() == drawn
    assert dialog.sketch.view.renderer().isValid()
    assert dialog.sketch.view.isVisibleTo(dialog.sketch)


@needs_rdkit
def test_what_the_dialog_hands_back_is_what_the_module_would_run(
        window, qtbot):
    """The values dict and nothing else, coerced by the action -- the
    same contract the generated form honours."""
    dialog = BuildMoleculeDialog(BUILD, INSERT, window)
    qtbot.addWidget(dialog)
    typed(dialog, qtbot, "CCO")
    values = dialog.values()

    assert values["smiles"] == "CCO"
    assert set(values) == {p.name for p in INSERT.params}
    assert isinstance(values["seed"], int)
    assert isinstance(values["optimise"], bool)


# ---------------------------------------------------- the whole path

@needs_rdkit
def test_inserting_puts_the_molecule_into_the_open_structure(
        window, qtbot, tmp_path, rutile, monkeypatch):
    document = opened(window, tmp_path, rutile)
    before = document.structure.n_sites
    monkeypatch.setattr(
        BuildMoleculeDialog, "ask",
        classmethod(lambda cls, *a, **k: {"smiles": "O", "name": "",
                                          "optimise": False,
                                          "seed": 1}))
    window.insert_molecule_dialog()

    assert document.structure.n_sites == before + 3
    assert document.can_undo


@needs_rdkit
def test_a_cancelled_insert_changes_nothing(window, tmp_path, rutile,
                                            monkeypatch):
    document = opened(window, tmp_path, rutile)
    monkeypatch.setattr(BuildMoleculeDialog, "ask",
                        classmethod(lambda cls, *a, **k: None))
    window.insert_molecule_dialog()

    assert not document.can_undo
    assert document.structure.n_sites == rutile.n_sites
