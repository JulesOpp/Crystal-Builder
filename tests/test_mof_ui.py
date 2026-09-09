"""The MOF builder on screen: the new tab, and the dialog of its own.

Two things Phase Q added to the shell, and neither of them needs
PORMAKE to be installed.

The **new tab** is the runner's, not the builder's: "a module that did
not need a structure opens the one it made in a new tab" is a rule
about ``needs_structure``, so it is tested with a two-line module
registered here rather than with a real framework build.

The **dialog** is the builder's, and it is skipped when PORMAKE's
database is not there because there is nothing for it to show.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from tests.test_app_shell import StubViewport  # noqa: E402
from xtal.core.lattice import Lattice  # noqa: E402
from xtal.core.structure import (  # noqa: E402
    TOPOLOGY,
    Bond,
    Site,
    Structure,
)
from xtal.io import read_cif, write_cif  # noqa: E402
from xtal.modules import MODULES  # noqa: E402
from xtal.modules.job import JobResult  # noqa: E402
from xtal.modules.registry import (  # noqa: E402
    Action,
    Availability,
    Module,
)
from xtal.mof import database_root  # noqa: E402
from xtalapp.dialogs import module_dialog  # noqa: E402
from xtalapp.dialogs.module_form import ModuleDialog  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402

needs_database = pytest.mark.skipif(
    database_root() is None,
    reason="PORMAKE is not installed; pip install "
           "'crystal-builder[mof]'")


def made_structure(job) -> JobResult:
    """A module that builds rather than measures, in four lines."""
    built = Structure(lattice=Lattice.from_parameters(
        5.0, 5.0, 5.0, 90, 90, 90),
        sites=[Site("Si", [0.0, 0.0, 0.0])])
    built.meta["title"] = "made up"
    return JobResult(message="built one", structure=built)


def written_structure(job) -> JobResult:
    """A build that makes its structure by writing a file.

    Which is how PORMAKE builds -- it writes a CIF and the module
    reads it back -- and is the case the shell has to move rather than
    copy, or the framework is in the workspace twice under two names.
    """
    result = made_structure(job)
    cif = job.folder.path / "made up.cif"
    write_cif(result.structure, cif)
    return JobResult(message="wrote one", structure=result.structure,
                     artifacts=(cif,))


def bonded_structure(job) -> JobResult:
    """A build that draws something over what it made.

    Which is what ``xtal.mof.build.draw_net`` does to a framework: the
    net is :data:`~xtal.core.structure.TOPOLOGY` bonds, and bonds are
    the thing a CIF has nowhere to put.
    """
    result = made_structure(job)
    built = result.structure
    built.sites.append(Site("Si", [0.5, 0.5, 0.5]))
    built.sites.append(Site("X", [0.25, 0.25, 0.25]))
    built.bonds.append(Bond(0, 1, (1, 0, 0), kind=TOPOLOGY))
    return JobResult(message="drew one", structure=built)


MAKER = Module(
    name="maker", label="Maker",
    actions=(Action(name="make", label="Make one",
                    needs_structure=False, writes_run_folder=True,
                    run=made_structure),
             Action(name="write", label="Write one",
                    needs_structure=False, writes_run_folder=True,
                    run=written_structure),
             Action(name="bonded", label="Draw over one",
                    needs_structure=False, writes_run_folder=True,
                    run=bonded_structure)))


@pytest.fixture
def registered():
    MODULES.register(MAKER)
    yield MODULES
    MODULES.unregister("maker")


@pytest.fixture
def settings(tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Mof{tmp_path.name}")
    settings.clear_recent_files()
    settings.last_directory = str(tmp_path)
    settings.last_workspace = ""
    settings.mof_topology_dir = ""
    settings.mof_bb_dir = ""
    return settings


@pytest.fixture
def window(qtbot, settings, registered):
    win = MainWindow(viewport_factory=StubViewport, settings=settings)
    qtbot.addWidget(win)
    return win


@pytest.fixture
def quick(monkeypatch):
    """Answer the parameter dialog without showing it."""
    monkeypatch.setattr(ModuleDialog, "ask",
                        staticmethod(lambda *a, **k: {}))


def run_and_wait(window, qtbot, module, action):
    window.run_module_action(module, action)
    qtbot.waitUntil(lambda: window.module_worker is None,
                    timeout=15000)


# ------------------------------------------- a structure from nothing

def test_a_module_that_builds_a_structure_opens_it_in_a_new_tab(
        window, qtbot, quick):
    """The other end of ``needs_structure = False``.

    The flag has existed since the registry was written and nothing
    used it; the half that was missing was this.  Without it a build
    with nothing open silently did nothing.
    """
    assert window.documents == []
    run_and_wait(window, qtbot, "maker", "make")
    assert len(window.documents) == 1
    assert window.documents[0].structure.meta["title"] == "made up"


def test_a_build_leaves_the_document_that_was_in_front_alone(
        window, qtbot, quick, tmp_path, rutile):
    """The rule this branch exists to break.

    ``_adopt_module_structure`` replaces the structure that is in
    front, so a build with something open would have destroyed it --
    and would have destroyed it as an undoable edit on a document the
    run had nothing to do with.
    """
    source = tmp_path / "rutile.cif"
    write_cif(rutile, source)
    window.open_path(source)
    before = window.documents[0].structure.n_sites

    run_and_wait(window, qtbot, "maker", "make")
    assert len(window.documents) == 2
    assert window.documents[0].structure.n_sites == before
    assert not window.documents[0].modified
    assert window.tabs.currentIndex() == 1


def test_a_build_has_no_undo_step_because_it_edited_nothing(
        window, qtbot, quick):
    """It built rather than changed something, so there is nothing to
    take back -- and it arrives saved rather than merely unmodified."""
    run_and_wait(window, qtbot, "maker", "make")
    assert not window.documents[0].modified
    assert not window.documents[0].stack.can_undo


def test_a_build_files_its_run_under_the_thing_it_built(
        window, qtbot, quick, tmp_path, rutile):
    """Not under whichever crystal happened to be in front, and not
    under the module either once there is a name for it.

    The run folder is opened before the build starts, so it goes under
    an entry named for the *module* -- which is right while the run is
    going and wrong the moment there is a framework to name it after.
    """
    source = tmp_path / "rutile.cif"
    write_cif(rutile, source)
    window.set_workspace(tmp_path / "ws", create=True)
    document = window.open_path(source)

    run_and_wait(window, qtbot, "maker", "make")
    names = {entry.name for entry in window.workspace.entries()}
    assert names == {"rutile", "made_up"}
    assert [run.name for run in
            window.workspace.entry("made_up").runs()] == \
        ["maker-make-001"]
    assert not list(document.entry.path.glob("*maker*"))


def test_a_build_lands_in_the_workspace_without_being_asked(
        window, qtbot, quick, tmp_path):
    """The tab used to be the only copy of what was just built.

    Everything else in the tree got there without a dialog, and a
    build is the one case where the file the user would save does not
    exist anywhere else -- so closing the tab threw the framework
    away and the only way to keep one was Save As.
    """
    window.set_workspace(tmp_path / "ws", create=True)
    run_and_wait(window, qtbot, "maker", "make")

    entry = window.workspace.entry("made_up")
    assert entry is not None
    assert entry.structure_path == entry.path / "made_up.cif"
    assert not entry.project_path.exists()
    document = window.documents[0]
    assert document.path == entry.structure_path
    assert document.entry.path == entry.path
    assert not document.modified


def test_the_filed_build_is_a_structure_that_reads_back(
        window, qtbot, quick, tmp_path):
    """What is kept has to be openable, not just present."""
    window.set_workspace(tmp_path / "ws", create=True)
    run_and_wait(window, qtbot, "maker", "make")

    written = read_cif(window.workspace.entry("made_up").structure_path)
    assert written.n_sites == window.documents[0].structure.n_sites


def test_the_node_a_build_wrote_opens_the_tab_it_is_already_in(
        window, qtbot, quick, tmp_path):
    """The entry and the document name one file between them.

    Double-clicking the node the build just made must not open a
    second document over the same atoms -- which is what would happen
    if the entry were attached and the path left unset, because the
    duplicate check compares both.
    """
    window.set_workspace(tmp_path / "ws", create=True)
    run_and_wait(window, qtbot, "maker", "make")
    built = window.documents[0]

    window.open_path(window.workspace.entry("made_up").structure_path)
    assert window.documents == [built]


def test_a_build_never_writes_over_a_structure_already_filed(
        window, qtbot, quick, tmp_path, rutile):
    """A title is not a file, and two of them are not one structure.

    An entry holds ``<name>.cif`` whether the structure was opened or
    built, so a build filed into the folder of a crystal somebody has
    open would take that crystal's workspace copy and leave the tab
    over atoms no longer in the file underneath it.
    """
    source = tmp_path / "made_up.cif"
    write_cif(rutile, source)
    window.set_workspace(tmp_path / "ws", create=True)
    opened = window.open_path(source)
    kept = read_cif(opened.entry.structure_path).n_sites

    run_and_wait(window, qtbot, "maker", "make")
    built = window.documents[1]

    assert built.entry.path != opened.entry.path
    assert built.entry.name == "made_up-2"
    assert read_cif(opened.entry.structure_path).n_sites == kept


def test_a_build_that_wrote_its_own_file_leaves_only_one_of_it(
        window, qtbot, quick, tmp_path):
    """The framework goes in the workspace once.

    A module that builds by writing a file and reading it back already
    has a CIF in its run folder, so the shell moves that one up rather
    than writing a second beside it -- two copies of a 3856-atom
    framework under two folder names is a question about which one is
    real, not thoroughness.
    """
    window.set_workspace(tmp_path / "ws", create=True)
    run_and_wait(window, qtbot, "maker", "write")

    entry = window.workspace.entry("made_up")
    assert [p.name for p in sorted(entry.path.rglob("*.cif"))] == \
        ["made_up.cif"]
    assert entry.runs()[0].log_path.is_file()


def test_the_file_a_build_leaves_is_named_after_its_entry(
        window, qtbot, quick, tmp_path, rutile):
    """A numbered entry cannot hold a file the module named.

    ``made up.cif`` written into ``made_up-2`` would be an entry whose
    folder and whose structure file disagree, which is one nobody
    finds twice.
    """
    source = tmp_path / "ws" / "made_up" / "made_up.cif"
    source.parent.mkdir(parents=True)
    write_cif(rutile, source)
    window.set_workspace(tmp_path / "ws", create=True)

    run_and_wait(window, qtbot, "maker", "write")
    entry = window.workspace.entry("made_up-2")
    assert entry.structure_path == entry.path / "made_up-2.cif"


def test_the_net_drawn_over_a_build_survives_into_the_workspace(
        window, qtbot, quick, tmp_path):
    """What the builder draws is bonds, and now the CIF carries them.

    The MOF builder's whole output is a framework *with its net
    drawn* -- that is the picture it exists to produce -- so an entry
    whose CIF gave back a framework with no net would be keeping the
    wrong half of what was built.
    """
    window.set_workspace(tmp_path / "ws", create=True)
    run_and_wait(window, qtbot, "maker", "bonded")

    entry = window.workspace.entry("made_up")
    kept = read_cif(entry.structure_path).bonds
    assert [b.kind for b in kept] == [TOPOLOGY]
    assert kept[0].image == (1, 0, 0)


def test_what_a_build_leaves_is_a_marker_and_a_net_until_it_is_exported(
        window, qtbot, quick, tmp_path):
    """The two rules meet here, and they say opposite things on
    purpose.

    The workspace copy *is* the document, so it keeps the dummy atom
    the builder placed and the edge hanging off it.  A file for
    somebody else keeps neither -- a marker is not chemistry and a net
    edge is not a bond.
    """
    window.set_workspace(tmp_path / "ws", create=True)
    run_and_wait(window, qtbot, "maker", "bonded")
    entry = window.workspace.entry("made_up")

    kept = read_cif(entry.structure_path)
    assert [s.element for s in kept.sites] == ["Si", "Si", "X"]
    assert len(kept.bonds) == 1

    window.documents[0].export(tmp_path / "out.cif")
    sent = read_cif(tmp_path / "out.cif")
    assert [s.element for s in sent.sites] == ["Si", "Si"]
    assert sent.bonds == []


def test_a_build_with_no_workspace_still_opens_its_tab(window, qtbot,
                                                       quick):
    """A run with nowhere to write still answers.  The answer is a
    framework in a tab, and only the file is lost.

    Reached now only when the default workspace could not be made --
    see ``WorkspaceShell.restore_workspace`` -- which is why the state
    is set here rather than waited for.
    """
    window.workspace_shell.workspace = None
    run_and_wait(window, qtbot, "maker", "make")
    assert len(window.documents) == 1


def test_a_build_with_no_workspace_creates_nothing_and_says_so(
        window, qtbot, quick, tmp_path):
    """The failure path is a sentence, not a silence.

    A build that could not be kept has to say so where the build was
    started from, because the tab looks identical either way.
    """
    window.workspace_shell.workspace = None
    run_and_wait(window, qtbot, "maker", "make")

    assert window.documents[0].path is None
    assert window.documents[0].entry is None
    assert "no workspace" in window.statusBar().currentMessage()


# ---------------------------------------------------- Action.dialog

def test_an_action_with_no_dialog_named_still_gets_the_form():
    assert module_dialog("") is None
    assert module_dialog("nothing-answers-to-this") is None


def test_the_mof_action_names_a_dialog_the_shell_can_find():
    """``Action.dialog`` is a name because the registry imports no Qt.

    If this ever comes back ``None`` the build silently falls back to
    the generated form, which asks for the topology as free text and
    cannot ask about slots at all.
    """
    _module, action = MODULES.find("mof.build")
    assert action.dialog == "mof-build"
    assert module_dialog(action.dialog) is not None


def test_the_named_dialog_is_asked_instead_of_the_form(window,
                                                       monkeypatch):
    """The substitution is of the *collection* of the parameters and
    nothing else -- the values come back in the same dict.

    The availability check is faked, and that is the point rather than
    a convenience: this is a test about which dialog the runner
    reaches for, which is a fact about the shell and not about whether
    PORMAKE is installed.  Without the fake it passes on a machine
    that happens to have PORMAKE and silently asserts nothing
    anywhere else -- the runner refuses an unavailable module before
    it ever picks a dialog, so `asked` stays empty and the failure
    names the dialog rather than the missing package.
    """
    from xtalapp.dialogs.mof_build import MofBuildDialog

    # Module is a frozen dataclass, so its `check` field cannot be
    # replaced on the instance; the method that reads it can.
    monkeypatch.setattr(Module, "availability",
                        lambda self: Availability(True))

    asked = []
    monkeypatch.setattr(ModuleDialog, "ask",
                        staticmethod(lambda *a, **k: {}))
    monkeypatch.setattr(
        MofBuildDialog, "ask",
        classmethod(lambda cls, m, a, p=None, i=None:
                    asked.append(a.name) or None))
    window.run_module_action("mof", "build")
    assert asked == ["build"]


# ------------------------------------------------------- the dialog

@pytest.fixture
def dialog(qtbot, window):
    from xtalapp.dialogs.mof_build import MofBuildDialog

    _module, action = MODULES.find("mof.build")
    built = MofBuildDialog(MODULES.get("mof"), action, window,
                           {"topology": "pcu", "nodes": "N59",
                            "edges": "E32"})
    qtbot.addWidget(built)
    return built


@needs_database
def test_the_dialog_asks_about_every_slot_the_topology_has(dialog):
    assert [row.slot.token for row in dialog._rows] == ["0", "0-0"]
    assert dialog.values()["topology"] == "pcu"


@needs_database
def test_picking_another_topology_asks_about_its_slots_instead(
        dialog):
    """The whole reason a generated form cannot do this: how many
    slots there are is decided by the net, not by the module."""
    assert dialog._select("tbo")
    assert [row.slot.token for row in dialog._rows] == ["0", "1",
                                                        "0-1"]


@needs_database
def test_a_slot_offers_only_the_blocks_that_fit_it(dialog):
    """A six-connected slot takes a block with six connection points
    and nothing else fits it at all, so offering the other 657 makes
    every wrong answer a refusal after the fact."""
    from xtal.mof import Catalog

    catalog = Catalog.default()
    row = dialog._rows[0]
    offered = {row.combo.itemData(i)
               for i in range(row.combo.count())}
    assert offered == {b.name for b in catalog.fitting(6)}


@needs_database
def test_an_edge_slot_may_be_left_with_no_linker_at_all(dialog):
    """PORMAKE builds an empty edge as a direct bond between the
    nodes, which is a real framework and worth offering by name."""
    edge = dialog._rows[-1]
    assert edge.combo.itemData(0) == ""
    edge.combo.setCurrentIndex(0)
    assert dialog.values()["edges"] == ""


@needs_database
def test_the_dialog_hands_back_exactly_what_the_module_declared(
        dialog):
    """The contract ``Action.dialog`` rests on.  A key the module did
    not declare is dropped by ``coerce`` and would be lost silently."""
    _module, action = MODULES.find("mof.build")
    assert set(dialog.values()) == {p.name for p in action.params}


@needs_database
def test_what_was_picked_last_time_is_offered_again(dialog):
    assert dialog.values()["nodes"] == "0=N59"
    assert dialog.values()["edges"] == "0-0=E32"


@needs_database
def test_a_folder_of_your_own_blocks_appears_beside_pormakes(
        qtbot, window, tmp_path):
    """"A user's own building block is a folder, not a code change."""
    from xtalapp.dialogs.mof_build import MofBuildDialog

    (tmp_path / "MINE.xyz").write_text(
        "7\n   1   2   3   4   5   6\n"
        "Zn 0.0 0.0 0.0\nX 2.0 0.0 0.0\nX -2.0 0.0 0.0\n"
        "X 0.0 2.0 0.0\nX 0.0 -2.0 0.0\nX 0.0 0.0 2.0\n"
        "X 0.0 0.0 -2.0\n")
    _module, action = MODULES.find("mof.build")
    built = MofBuildDialog(MODULES.get("mof"), action, window,
                           {"topology": "pcu",
                            "bb_dir": str(tmp_path)})
    qtbot.addWidget(built)
    row = built._rows[0]
    offered = {row.combo.itemData(i)
               for i in range(row.combo.count())}
    assert "MINE" in offered
    assert "N59" in offered


@needs_database
def test_typing_a_composition_narrows_the_slot_that_fits_it(dialog,
                                                            qtbot):
    """N59 is C6Cd2O12 -- exactly six carbons, two cadmiums, twelve
    oxygens -- and the search box is one query for every row, not
    one per slot."""
    row = dialog._rows[0]
    before = row.combo.count()
    dialog.composition.setText("2Cd")

    offered = {row.combo.itemData(i)
              for i in range(row.combo.count())}
    assert "N59" in offered
    assert row.combo.count() < before


@needs_database
def test_clearing_the_composition_search_offers_everything_again(
        dialog):
    row = dialog._rows[0]
    before = row.combo.count()
    dialog.composition.setText("2Cd")
    dialog.composition.setText("")

    assert row.combo.count() == before


@needs_database
def test_a_composition_that_fits_nothing_is_not_an_error(dialog):
    """A query only RDKit's own periodic table would recognise as
    absurd -- "40C" on a slot where nothing has forty carbons -- empties
    the combo rather than raising, the same way a name typed into the
    topology filter that matches nothing just shows an empty list."""
    dialog.composition.setText("400C")

    row = dialog._rows[0]
    assert row.combo.count() == (1 if row.slot.is_edge else 0)


@needs_database
def test_switching_topology_keeps_the_composition_search_applied(
        dialog):
    """The search box is dialog-wide, not per slot -- so picking a
    different net must not silently drop what was typed into it."""
    dialog.composition.setText("2Cd")
    assert dialog._select("tbo")

    for row in dialog._rows:
        assert row._composition == "2Cd"


@needs_database
def test_a_net_that_cannot_be_expanded_refuses_rather_than_raises(
        dialog):
    """Four of PORMAKE's 2403 files give edge midpoints instead of
    endpoints, and a midpoint does not say what it joins.

    They are still in the list, because they are still nets and the
    list is where a name is found.  What they must not do is take the
    dialog down when they are clicked.
    """
    assert dialog._select("bcu-b")
    assert dialog._rows == []
    assert not dialog.build_button.isEnabled()
    assert "bcu-b" in dialog.details.text()


@needs_database
def test_the_net_picture_survives_one_it_cannot_draw(dialog):
    dialog._select("bcu-b")
    assert dialog.net_preview._drawing is None
    dialog.net_preview.grab()               # must not raise
