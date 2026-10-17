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

from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt  # noqa: E402

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
from xtal.mof.catalog import installed  # noqa: E402
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


def _builder(qtbot, window, entry, initial=None):
    """The dialog of one MOF builder entry, as the menu opens it."""
    from xtalapp.dialogs import module_dialog

    _module, action = MODULES.find(f"mof.{entry}")
    built = module_dialog(action.dialog)(MODULES.get("mof"), action,
                                         window, initial or {})
    qtbot.addWidget(built)
    return built


@pytest.fixture
def pacs(qtbot, window):
    return _builder(qtbot, window, "pacs")


@pytest.fixture
def sets(qtbot, window):
    return _builder(qtbot, window, "sets")


@pytest.fixture
def st(qtbot, window):
    return _builder(qtbot, window, "supertetrahedra")


@needs_database
def test_the_dialog_asks_about_every_slot_the_topology_has(dialog):
    assert [row.slot.token for row in dialog._rows] == ["0", "0-0"]
    assert dialog.values()["topology"] == "pcu"


@needs_database
def test_a_block_drawn_on_a_row_is_what_the_build_builds_with(
        dialog, window, tmp_path):
    """Draw wrote the block into the workspace, the row selected it,
    and then the build could not find it: the run read the two named
    folders and not the one the block was certain to be in."""
    from xtal.modules.job import Job
    from xtal.modules.mof import catalog_for

    window.set_workspace(tmp_path / "ws", create=True)
    blocks = window.workspace.blocks
    blocks.mkdir(parents=True, exist_ok=True)
    (blocks / "drawn6.xyz").write_text(
        "6\n0 1 2 3 4 5\n"
        "X  1.5  0.0  0.0\nX -1.5  0.0  0.0\n"
        "X  0.0  1.5  0.0\nX  0.0 -1.5  0.0\n"
        "X  0.0  0.0  1.5\nX  0.0  0.0 -1.5\n")

    node = next(row for row in dialog._rows if not row.slot.is_edge)
    dialog._blocks = blocks
    # Through the row's own signal, which is what the Draw dialog
    # returning a path does: the handler selects the block on whichever
    # row asked for it, and that row is the sender.
    node.drawn.emit("drawn6")
    assert node.block() == "drawn6"

    entry = window.workspace.add_document("framework")
    run = entry.path / "runs" / "mof-build-001"
    run.mkdir(parents=True)
    job = Job(params=dialog.values(),
              folder=SimpleNamespace(path=run))
    assert catalog_for(job).building_block("drawn6").n_connections == 6


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
def test_the_stacking_rows_are_live_only_for_a_layer_net(dialog):
    """``hcb`` has sheets to stack and ``pcu`` does not.

    The rows are there for every net and greyed for most, rather
    than appearing with the layers: rows that come and go as the list
    is scrolled move the Build button under the cursor.  And what was
    typed while ``hcb`` was selected is not handed on for ``pcu``,
    where the run would refuse it for a box nobody can edit.
    """
    assert not dialog.spacing.isEnabled()
    assert not dialog.offset.isEnabled()

    assert dialog._select("hcb")
    assert dialog.spacing.isEnabled() and dialog.offset.isEnabled()
    dialog.spacing.setText("3.24")
    dialog.offset.setText("1/3, 2/3")
    assert dialog.values()["spacing"] == "3.24"
    assert dialog.values()["offset"] == "1/3, 2/3"

    assert dialog._select("pcu")
    assert not dialog.spacing.isEnabled()
    assert dialog.values()["spacing"] == ""
    assert dialog.values()["offset"] == ""


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


# ------------------------------------------------- turning the net picture

def _mouse(widget, kind, x, y, button, buttons):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    kinds = {"press": QEvent.MouseButtonPress,
             "move": QEvent.MouseMove,
             "release": QEvent.MouseButtonRelease,
             "double": QEvent.MouseButtonDblClick}
    local = QPointF(x, y)
    event = QMouseEvent(kinds[kind], local, widget.mapToGlobal(local),
                        button, buttons, Qt.NoModifier)
    QApplication.sendEvent(widget, event)


def _drag(widget, dx, dy, steps=6):
    from PySide6.QtCore import Qt

    x, y = widget.width() / 2, widget.height() / 2
    _mouse(widget, "press", x, y, Qt.LeftButton, Qt.LeftButton)
    for step in range(1, steps + 1):
        _mouse(widget, "move", x + dx * step / steps,
               y + dy * step / steps, Qt.NoButton, Qt.LeftButton)
    _mouse(widget, "release", x + dx, y + dy, Qt.LeftButton,
           Qt.NoButton)


@pytest.fixture
def net_picture(qtbot, dialog):
    dialog.show()
    qtbot.waitExposed(dialog)
    return dialog.net_preview


def _points(preview):
    from PySide6.QtCore import QRectF
    return preview.screen_points(QRectF(preview.rect()))


@needs_database
def test_dragging_the_net_preview_turns_it(net_picture):
    """A net whose defining feature is edge-on from the one angle it
    was drawn at could not be recognised; now it can be turned until
    it is."""
    import numpy as np

    vertices, edges = _points(net_picture)
    _drag(net_picture, 60, 25)
    turned, turned_edges = _points(net_picture)

    assert turned.shape == vertices.shape
    assert turned_edges.shape == edges.shape
    assert not np.allclose(turned, vertices, atol=1.0)


@needs_database
def test_double_clicking_the_net_preview_puts_it_back(net_picture):
    import numpy as np
    from PySide6.QtCore import Qt

    from xtalapp.dialogs.mof_preview import DEFAULT_ROTATION

    _drag(net_picture, 80, -40)
    assert not np.allclose(net_picture.rotation, DEFAULT_ROTATION)
    middle = (net_picture.width() / 2, net_picture.height() / 2)
    _mouse(net_picture, "double", *middle, Qt.LeftButton, Qt.LeftButton)

    assert np.allclose(net_picture.rotation, DEFAULT_ROTATION)


@needs_database
def test_the_reset_view_button_puts_the_net_back(net_picture):
    import numpy as np

    from xtalapp.dialogs.mof_preview import DEFAULT_ROTATION

    net_picture.turn_by(90, 30)
    net_picture.reset_button.click()

    assert np.allclose(net_picture.rotation, DEFAULT_ROTATION)
    assert not net_picture.reset_button.autoDefault()


@needs_database
def test_turning_the_net_does_not_rescale_it(net_picture):
    """Fitted to the bounding sphere, so it neither breathes while it
    turns nor pushes a vertex out of the box at some angle."""
    import numpy as np

    rect = net_picture.rect()
    spans = []
    for _step in range(12):
        net_picture.turn_by(37, 23)
        vertices, edges = _points(net_picture)
        everything = np.vstack([vertices, edges.reshape(-1, 2)])
        assert everything[:, 0].min() >= rect.left()
        assert everything[:, 0].max() <= rect.right()
        assert everything[:, 1].min() >= rect.top()
        assert everything[:, 1].max() <= rect.bottom()
        centre = everything.mean(axis=0)
        spans.append(np.linalg.norm(everything - centre, axis=1).max())
    # A rigid turn: the farthest point from the middle is as far away
    # at every angle, give or take which point that is.
    assert max(spans) < 1.8 * min(spans)


@needs_database
def test_a_new_topology_starts_from_the_default_view(dialog):
    import numpy as np

    from xtalapp.dialogs.mof_preview import DEFAULT_ROTATION

    dialog.net_preview.turn_by(120, 45)
    assert dialog._select("dia")

    assert np.allclose(dialog.net_preview.rotation, DEFAULT_ROTATION)


@needs_database
def test_the_interpenetration_row_hands_back_a_count(dialog):
    """1 is shown as "none" and handed on as 1, which is the framework
    alone; the run parses the number, so the spinbox and a command
    line spell it the same way."""
    assert dialog.interpenetration.text() == "none"
    assert dialog.values()["interpenetration"] == 1
    dialog.interpenetration.setValue(2)
    assert dialog.values()["interpenetration"] == 2


def _offered(row) -> set:
    return {row.combo.itemData(i) for i in range(row.combo.count())} \
        - {""}


@needs_database
def test_the_denticity_boxes_offer_one_kind_of_block_or_both(dialog):
    """pcu's six-connected slot has both kinds -- MFU-4l's Kuratowski
    node is polydentate, N59 is not -- and each box alone offers only
    its own kind, with both together offering everything."""
    row = dialog._rows[0]
    both = _offered(row)
    dialog.monodentate.setChecked(False)
    poly = _offered(row)
    dialog.monodentate.setChecked(True)
    dialog.polydentate.setChecked(False)
    mono = _offered(row)

    assert "MFU4l_Kuratowski" in poly and "N59" not in poly
    assert "N59" in mono and "MFU4l_Kuratowski" not in mono
    assert poly | mono == both


@needs_database
def test_unticking_the_last_kind_ticks_the_other_instead(dialog):
    """Two empty boxes would empty every list with nothing on screen
    to say why."""
    dialog.polydentate.setChecked(False)
    dialog.monodentate.setChecked(False)

    assert dialog.polydentate.isChecked()
    assert _offered(dialog._rows[0])


@needs_database
def test_the_denticity_boxes_say_how_many_of_each_kind_there_are(
        dialog):
    assert "Monodentate (" in dialog.monodentate.text()
    assert "Polydentate (" in dialog.polydentate.text()
    assert dialog.polydentate.text() != "Polydentate (0)"


@needs_database
def test_a_block_can_be_searched_for_by_name(dialog):
    row = dialog._rows[0]
    dialog.composition.setText("N59")

    offered = _offered(row)
    assert "N59" in offered
    assert all("N59" in name for name in offered)


@needs_database
def test_switching_topology_keeps_the_denticity_applied(dialog):
    dialog.monodentate.setChecked(False)
    assert dialog._select("tbo")

    for row in dialog._rows:
        assert all(dialog.catalog.building_block(name).is_polydentate
                   for name in _offered(row))


def _listed(dialog) -> set:
    from PySide6.QtCore import Qt

    items = (dialog.topologies.item(i)
             for i in range(dialog.topologies.count()))
    return {item.data(Qt.UserRole) for item in items
            if not item.isHidden()}


@needs_database
def test_the_dimension_boxes_offer_3d_nets_2d_nets_or_both(dialog):
    """hcb is a layer and pcu is not, and each box alone lists only
    its own kind -- the denticity boxes' rule, asked of the nets."""
    both = _listed(dialog)
    dialog.three_d.setChecked(False)
    layers = _listed(dialog)
    dialog.three_d.setChecked(True)
    dialog.two_d.setChecked(False)
    solid = _listed(dialog)

    assert "hcb" in layers and "pcu" not in layers
    assert "pcu" in solid and "hcb" not in solid
    assert layers | solid == both


@needs_database
def test_unticking_the_last_dimension_ticks_the_other_instead(dialog):
    dialog.two_d.setChecked(False)
    dialog.three_d.setChecked(False)

    assert dialog.two_d.isChecked()
    assert _listed(dialog)


@needs_database
def test_the_dimension_boxes_and_the_name_filter_both_apply(dialog):
    dialog.filter.setText("hcb")
    assert "hcb" in _listed(dialog)
    dialog.two_d.setChecked(False)
    assert "hcb" not in _listed(dialog)
    dialog.filter.setText("")
    assert "hcb" not in _listed(dialog) and "pcu" in _listed(dialog)


@needs_database
def test_the_dimension_boxes_say_how_many_nets_each_has(dialog):
    three = int(dialog.three_d.text().split("(")[1].rstrip(")"))
    two = int(dialog.two_d.text().split("(")[1].rstrip(")"))

    assert two >= 4 and three > 2000
    assert two + three == dialog.topologies.count()


@needs_database
def test_numbered_blocks_are_offered_in_numeric_order(dialog):
    """N2 before N10 before N100: sorted as text, N10 and N100 came
    before N2 and a block looked for by its number was not where the
    number said."""
    row = dialog._rows[0]
    names = [row.combo.itemData(i) for i in range(row.combo.count())]
    organic = [n for n in names
               if not dialog.catalog.building_block(n).has_metal]
    numbered = [n for n in organic
                if n[:1] == "N" and n[1:].isdigit()]
    assert len(numbered) > 10
    assert numbered == sorted(numbered, key=lambda n: int(n[1:]))


@needs_database
def test_the_dialog_is_never_taller_than_the_screen(dialog):
    """It opened 780 px tall with a 320 px floor on the slot rows,
    and on a laptop the Build button was below the screen.  Every
    section now scrolls, so the size is the screen's to decide."""
    room = dialog.screen().availableGeometry()
    assert dialog.height() <= room.height()
    assert dialog.width() <= room.width()
    assert dialog.minimumSizeHint().height() < room.height()


@needs_database
def test_every_section_folds_away(dialog):
    for fold in (dialog.topology_fold, dialog.blocks_fold,
                 dialog.how_fold, dialog.folders_fold):
        fold.set_open(False)
        assert not fold.body.isVisibleTo(dialog)
        fold.set_open(True)
        assert fold.body.isVisibleTo(dialog)


@needs_database
def test_a_repeat_asked_for_last_time_is_not_hidden(qtbot, window):
    """A 2x2x2 repeat folded out of sight builds eight times the cell
    nobody remembers asking for."""
    from xtalapp.dialogs.mof_build import MofBuildDialog

    _module, action = MODULES.find("mof.build")
    plain = MofBuildDialog(MODULES.get("mof"), action, window,
                           {"topology": "pcu"})
    tiled = MofBuildDialog(MODULES.get("mof"), action, window,
                           {"topology": "pcu", "repeat": "2x2x2"})
    qtbot.addWidget(plain)
    qtbot.addWidget(tiled)

    assert not plain.how_fold.is_open()
    assert tiled.how_fold.is_open()


@needs_database
def test_the_orientation_form_offers_consistent_first(dialog):
    """``consistent`` is the default, and a form offers the default
    first; ``as-found`` stays, one down, for PORMAKE's own choice."""
    offered = [dialog.orientation.itemData(i)
               for i in range(dialog.orientation.count())]

    assert offered == ["consistent", "as-found"]
    assert dialog.orientation.currentData() == "consistent"


@needs_database
def test_as_found_last_time_is_not_hidden_and_the_default_is(qtbot,
                                                              window):
    """The section opens when last time's answer was not the default.
    It used to ask whether the rule was the *first* one offered, which
    is the same question only while the default is listed first; it
    now asks for the default by name.  No rule at all is the
    default."""
    from xtalapp.dialogs.mof_build import MofBuildDialog

    _module, action = MODULES.find("mof.build")
    shown = {}
    for rule in ("consistent", "as-found", None):
        given = {"topology": "pcu"}
        if rule is not None:
            given["orientation"] = rule
        made = MofBuildDialog(MODULES.get("mof"), action, window, given)
        qtbot.addWidget(made)
        shown[rule] = (made.how_fold.is_open(),
                       made.orientation.currentData())

    assert shown["consistent"] == (False, "consistent")
    assert shown["as-found"] == (True, "as-found")
    assert shown[None] == (False, "consistent")


@needs_database
def test_the_mof_builder_searches_by_group_number_and_transitivity(
        dialog):
    """MOF+'s fields, in the topology list: a layer by its plane group
    number, a 3-D net by its space group's."""
    dialog.search.number.setText("17")
    dialog.search.transitivity.setText("1 1")
    found = _listed(dialog)
    assert {"hcb", "hxl", "kgm"} <= found and "pcu" not in found

    dialog.search.number.setText("221")
    assert "pcu" in _listed(dialog) and "hcb" not in _listed(dialog)


@needs_database
def test_the_builder_links_to_pormake_and_the_rcsr(dialog):
    """Where the builder and its nets come from, outside the scroll
    so that it is there whichever section is open; the chosen net's
    RCSR page where it has one, and nothing where it has not."""
    assert dialog.sources.openExternalLinks()
    assert "https://github.com/Sangwon91/PORMAKE" in dialog.sources.urls()
    assert "https://doi.org/10.1021/acsami.1c02471" in \
        dialog.sources.urls()
    assert "https://doi.org/10.1021/ar800124u" in dialog.sources.urls()
    assert dialog.net_links.urls() == ["http://rcsr.net/nets/pcu"]

    assert dialog._select("lcw_component_3")   # PORMAKE's, not the RCSR's
    assert dialog.net_links.urls() == []
    assert dialog.net_links.isHidden()


def test_an_answered_build_dialog_is_deleted_on_the_gui_thread(
        qtbot, window, monkeypatch):
    """After ``exec`` PySide hands the dialog to Python, and its slot
    rows hold it in a cycle, so only the cyclic collector frees it --
    on whichever thread runs it next, which is the build's worker, and
    widgets destroyed there segfault."""
    import shiboken6
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QDialog

    from xtalapp.dialogs.mof_build import MofBuildDialog

    made = []

    def answer(self):
        made.append(self)
        return QDialog.Accepted

    monkeypatch.setattr(MofBuildDialog, "exec", answer)
    module, action = MODULES.find("mof.build")
    values = MofBuildDialog.ask(module, action, window,
                                {"topology": "pcu", "nodes": "N59",
                                 "edges": "E32"})
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    assert values["topology"] == "pcu"
    assert not shiboken6.isValid(made[0])


def _acs(pacs, node="N589", linker="E14"):
    assert pacs._select("acs")
    pacs._rows[0].set_block(node)
    next(r for r in pacs._rows if r.slot.is_edge).set_block(linker)
    return pacs.partition


@needs_database
def test_the_partition_box_is_live_only_for_an_open_trimer(pacs, dialog):
    """Only the pacs builder has the section, and it builds on acs
    alone: live there with an open M3O trimer, and greyed for a trimer
    whose own carboxylate sits on the site."""
    assert dialog.partition_fold.isHidden()
    assert dialog.values()["partition"] == ""
    assert pacs.topologies.count() == 1
    assert pacs._topology.name == "acs"

    box = _acs(pacs)
    assert box.choice.isEnabled()
    assert pacs.values()["partition"] == ""
    assert box.set_value("tpt")
    assert pacs.values()["partition"] == "tpt"
    assert "Predicted" in box.status.text()

    # N86 is not offered in the row any more; a drawn one like it is.
    assert not pacs._rows[0].set_block("N86")
    box.set_framework(pacs.catalog, "acs", "N86", "E14")
    assert not box.choice.isEnabled()
    assert "no open site" in box.status.text()
    assert box.value() == ""


@needs_database
def test_the_pacs_trimer_row_offers_only_trimers_it_can_partition(
        pacs, tmp_path):
    """The nine open M3O trimers, not the two hundred six-connected
    blocks Build would refuse -- and a block drawn on the row is
    offered whatever it is."""
    from pathlib import Path

    from xtal.mof import partition

    pacs._select("acs")
    row = pacs._rows[0]
    offered = {row.combo.itemData(i) for i in range(row.combo.count())}
    assert offered == {n.name for n in
                       partition.compatible_nodes(pacs.catalog)}
    assert "N589" in offered and "N86" not in offered
    edge = next(r for r in pacs._rows if r.slot.is_edge)
    assert edge.combo.count() > 100

    drawn = Path(row.folder) / "my-node.xyz"
    drawn.parent.mkdir(parents=True, exist_ok=True)
    drawn.write_text(Path(pacs.catalog.building_block("N86").path)
                     .read_text())
    pacs._on_block_drawn("my-node")
    row = pacs._rows[0]
    assert row.set_block("my-node")


@needs_database
def test_a_refused_partitioner_shows_its_reason_and_cannot_be_chosen(
        pacs):
    """tppb on BDC cannot close the cell: listed, greyed, with the
    reason as its tooltip and in the status line."""
    box = _acs(pacs)
    at = box.choice.findData("tppb")
    assert at >= 0
    assert not box._enabled(at)
    assert "too wide for E14" in box.choice.itemData(at, Qt.ToolTipRole)
    assert not box.set_value("tppb")
    assert "Cannot close the cell" in box.status.text()


@needs_database
def test_a_suggested_linker_goes_on_the_edge_row(pacs):
    box = _acs(pacs)
    box.set_value("tpt")
    box._suggest()
    assert "asks for a 2-connected aryl linker" in box.suggestions.text()
    box.use_linker.emit("E16")
    edge = next(r for r in pacs._rows if r.slot.is_edge)
    assert edge.block() == "E16"


@needs_database
def test_a_partitioner_picked_last_time_is_offered_again(qtbot, window):
    again = _builder(qtbot, window, "pacs",
                     {"topology": "acs", "nodes": "N589",
                      "edges": "E14", "partition": "tpt"})
    assert again.values()["partition"] == "tpt"
    assert again.partition_fold.is_open()


@needs_database
def test_the_note_names_the_compatible_nodes_and_a_click_uses_one(
        pacs):
    """A click on a trimer in the note puts it in the node row."""
    note = pacs.partition.nodes.text()
    assert "Nodes that can be partitioned" in note
    assert "N589" in note and "N590" not in note
    pacs.partition.use_node.emit("N92")
    assert pacs._topology.name == "acs"
    assert pacs._rows[0].block() == "N92"
    assert pacs.partition.choice.isEnabled()


def _sph(sets, hexa="N573", tri="N10", cluster="N419"):
    assert sets._select("sph")
    rows = {r.slot.key: r for r in sets._rows if not r.slot.is_edge}
    rows[2].set_block(cluster)
    if hexa:
        rows[0].set_block(hexa)
    if tri:
        rows[1].set_block(tri)
    return sets.linker_sets


@needs_database
def test_the_linker_set_box_is_live_only_for_a_cluster_on_a_merged_net(
        sets, dialog):
    """Only the mixed-linker builder has the section, and it lists the
    nets a set can be worked out on -- sph, never pcu, which has one
    kind of edge; live once a metal cluster is in sph's 12-c slot."""
    assert dialog.sets_fold.isHidden()
    assert not sets._select("pcu")
    box = _sph(sets)
    assert box.check.isEnabled() and box.suggest.isEnabled()
    assert "2 kinds of linker" in box.status.text()


@pytest.mark.slow
@needs_database
def test_a_set_that_checks_is_built_on_the_net_where_it_fits(sets):
    """The topology handed to the build is the re-embedded sph while
    the rows hold the set that checked, and sph again once one
    changes."""
    box = _sph(sets)
    assert sets.values()["topology"] == "sph"
    box._check()
    assert "This set fits" in box.status.text()
    assert sets.values()["topology"].startswith("sph@")
    next(r for r in sets._rows
         if r.slot.key == 1 and not r.slot.is_edge).set_block("N19")
    assert sets.values()["topology"] == "sph"


@pytest.mark.slow
@needs_database
def test_a_set_that_cannot_close_both_edges_says_why(sets):
    box = _sph(sets, hexa="N5", tri="N10")
    box._check()
    assert "does not fit" in box.status.text()
    assert "allows" in box.status.text()
    assert sets.values()["topology"] == "sph"


@pytest.mark.slow
@needs_database
def test_a_suggested_set_clicked_fills_both_linker_rows(sets):
    box = _sph(sets, hexa="N5", tri="N110")
    box._suggest()
    text = box.suggestions.text()
    assert "Sets from the catalogue" in text
    assert "N110 asks node 1 for a 6-connected" in text
    box._clicked("set:0=N573,1=N10")
    held = sets._node_blocks()
    assert held[0] == "N573" and held[1] == "N10"


@needs_database
def test_a_reembedded_net_picked_last_time_is_built_there_again(
        qtbot, window):
    again = _builder(qtbot, window, "sets",
                     {"topology": "sph@-0.1250",
                      "nodes": "0=N573,1=N10,2=N419"})
    assert again._topology.name == "sph"
    assert again.values()["topology"] == "sph@-0.1250"
    assert again.sets_fold.is_open()


# -- the supertetrahedra section ---------------------------------------

def _sod(st):
    assert st._select("sod")
    box = st.supertetrahedra
    box.decorate.setChecked(True)
    box.settle()
    return box


def _rows_by_key(st):
    return {r.slot.key: r for r in st._rows if not r.slot.is_edge}


@needs_database
def test_the_supertetrahedra_builder_lists_only_nets_it_can_decorate(
        st, dialog):
    """Only the supertetrahedra builder has the section; it lists the
    4-connected nets alone, the six zeolites first, and every net it
    shows is built of supertetrahedra -- there is no tick."""
    assert dialog.st_fold.isHidden()
    assert not st._select("pcu")
    first = [st.topologies.item(i).data(Qt.UserRole) for i in range(6)]
    assert set(first) == {"sod", "mtn", "lta", "rho", "cha", "fau"}
    assert all(set(st.catalog.topology(
        st.topologies.item(i).data(Qt.UserRole)).coordinations) == {4}
        for i in range(st.topologies.count()))
    assert st.supertetrahedra.decorate.isHidden()
    assert st.values()["topology"] == "sod-st"


@needs_database
def test_decorating_sod_asks_for_a_trimer_and_a_face(st):
    """The build is on sod-st and the rows are its trimer and its
    face."""
    _sod(st)
    assert st._topology.name == "sod-st"
    assert st.values()["topology"] == "sod-st"
    assert [r.slot.coordination for r in _rows_by_key(st).values()
            ] == [6, 3]
    assert "M3O trimer" in st.details.text()


@needs_database
def test_filling_four_rings_keeps_the_blocks_and_adds_a_filler_row(
        st):
    """sod-st-f4: the trimer slot is seven-connected and still offers
    the six-connected trimer the build makes its twin from, so N92 and
    BTC stay where they were put."""
    box = _sod(st)
    rows = _rows_by_key(st)
    rows[0].set_block("N92")
    rows[1].set_block("N10")
    tick, _every = box._rows[4]
    tick.setChecked(True)
    assert st._topology.name == "sod-st-f4"
    rows = _rows_by_key(st)
    assert rows[0].slot.coordination == 7
    assert rows[0].block() == "N92" and rows[1].block() == "N10"
    assert rows[2].slot.coordination == 4
    assert "fills the 4-rings" in st.details.text()
    values = st.values()
    assert values["topology"] == "sod-st-f4"
    assert "N92" in values["nodes"] and "N10" in values["nodes"]


@needs_database
def test_a_refused_fill_is_greyed_with_its_reason(st):
    """Every other site of sod's 4-ring is turned onto the others by
    its fourfold axis: listed, greyed, the reason its tooltip."""
    box = _sod(st)
    _tick, every = box._rows[4]
    at = every.findData(2)
    assert at >= 0
    assert not every.model().item(at).isEnabled()
    assert "symmetry" in every.itemData(at, Qt.ToolTipRole)


@needs_database
def test_half_a_six_ring_is_offered_and_says_the_group_it_is_written_in(
        st):
    """Every other site of sod's 6-ring is the I-43m sod-ZMOFs': it is
    no longer greyed, and the section says why the group dropped."""
    box = _sod(st)
    tick, every = box._rows[6]
    at = every.findData(2)
    assert every.model().item(at).isEnabled()
    every.setCurrentIndex(at)
    tick.setChecked(True)
    assert st._topology.name == "sod-st-f6e2"
    assert "Written in I-43m" in box.status.text()
    assert "fills the 6-rings" in st.details.text()


@needs_database
def test_two_fills_refused_together_put_the_tick_back_and_say_why(
        st, monkeypatch):
    from xtal.mof.catalog import CatalogError

    box = _sod(st)
    box._rows[4][0].setChecked(True)
    real = st.catalog.topology

    def refuse(name):
        if name == "sod-st-f4-f6":
            raise CatalogError("asks four open sites of a trimer")
        return real(name)

    monkeypatch.setattr(st.catalog, "topology", refuse)
    box._rows[6][0].setChecked(True)
    assert not box._rows[6][0].isChecked()
    assert "four open sites" in box.status.text()
    assert st._topology.name == "sod-st-f4"


@needs_database
def test_the_same_trimer_goes_in_every_trimer_slot(st):
    """lta has three kinds of edge, so three trimer slots and three
    face slots; one pick fills all three, unless asked otherwise."""
    assert st._select("lta")
    box = st.supertetrahedra
    box.decorate.setChecked(True)
    rows = _rows_by_key(st)
    rows[0].set_block("N92")
    rows[3].set_block("N10")
    assert [rows[k].block() for k in range(6)] == ["N92"] * 3 + [
        "N10"] * 3
    box.same.setChecked(False)
    rows[1].set_block("N536")
    assert rows[0].block() == "N92"


@needs_database
def test_the_supertetrahedra_builder_opens_on_a_nickel_trimer_and_btc(st):
    """N589 (Ni3O) and N10 (BTC) on sod-st, unless something else was
    picked last time."""
    assert st._topology.name == "sod-st"
    assert [r.block() for r in _rows_by_key(st).values()] == [
        "N589", "N10"]


@needs_database
def test_a_net_clicked_leaves_no_row_of_the_last_one_on_screen(st):
    """The rows a net replaces are unparented at once: a deferred
    delete posted before the modal loop starts is not delivered inside
    it, and the old row's picture stayed as a white box behind "Node
    1, 6-connected"."""
    from xtalapp.dialogs.mof_build import _SlotRow

    assert st._select("lta")
    assert st._select("sod")
    left = [w for w in st.slots_box.findChildren(_SlotRow)
            if w.parent() is st.slots_box]
    assert left == st._rows


@needs_database
def test_a_net_clicked_lists_its_fills_and_tries_them_afterwards(st):
    """Trying every fill was three seconds of a click on fau; the
    rows are there at once and greyed as each is tried."""
    assert st._select("lta")
    assert st._select("sod")
    box = st.supertetrahedra
    _tick, every = box._rows[4]
    assert every.findData(2) >= 0 and box._untried
    box.settle()
    assert not box._untried
    assert not every.model().item(every.findData(2)).isEnabled()


@needs_database
def test_a_decorated_net_picked_last_time_is_offered_again(qtbot,
                                                          window):
    again = _builder(qtbot, window, "supertetrahedra",
                     {"topology": "sod-st-f4",
                      "nodes": "0=N92,1=N10"})
    assert again._listed.name == "sod"
    assert again._topology.name == "sod-st-f4"
    assert again.supertetrahedra._rows[4][0].isChecked()
    assert _rows_by_key(again)[0].block() == "N92"
    assert again.st_fold.is_open()
    assert again.values()["topology"] == "sod-st-f4"


@pytest.mark.slow
@needs_database
@pytest.mark.skipif(not installed(), reason="PORMAKE needs ase")
def test_a_suggested_filler_clicked_fills_its_window(st):
    """TPyP is In-sod-ZMOF-320's 4-ring filler on TATB; on BTC the
    4-ring asks for less, but a click on any suggestion fills the
    window and puts the filler in the row it made."""
    box = _sod(st)
    rows = _rows_by_key(st)
    rows[0].set_block("N92")
    rows[1].set_block("N10")
    assert box.suggest.isEnabled()
    box._suggest()
    text = box.suggestions.text()
    assert "T-O-T" in text
    assert "4-ring, 4 sites" in text and "6-ring, 6 sites" in text
    href = next(h for h in text.split("href='")[1:]
                if h.startswith("6:1:0:")).split("'")[0]
    name = href.split(":", 3)[3]
    box._clicked(href)
    assert st._topology.name == "sod-st-f6"
    assert _rows_by_key(st)[2].block() == name
    assert "6-ring" in box.suggestions.text()


needs_merged = pytest.mark.skipif(
    not __import__("xtal.mof.merged_nets", fromlist=["table"]).table(),
    reason="the merged-net table is missing")


@needs_merged
def test_the_explorer_opens_from_the_menu_and_filters_by_cluster(window):
    explorer = window.open_net_explorer()
    assert window.open_net_explorer() is explorer
    total = len(explorer.visible_names())
    explorer.cluster.setCurrentText("12")
    twelve = explorer.visible_names()
    assert "sph" in twelve and len(twelve) < total
    explorer.kind.setCurrentText("3p-0p")
    assert "sph" not in explorer.visible_names()
    assert explorer.count.text().endswith(f"of {total}")
    assert explorer.table.horizontalHeaderItem(7).text() == \
        "Example MOF"


@needs_merged
def test_choosing_a_row_says_its_parents_and_opens_the_net_with_groups(
        window, monkeypatch):
    asked = []
    monkeypatch.setattr(window, "run_module_action",
                        lambda *a, **k: asked.append((a, k)))
    explorer = window.open_net_explorer()
    assert explorer.choose("sph")
    text = explorer.diagram.text()
    assert "spn" in text and "hxg" in text and "sph" in text
    explorer.open_button.click()
    assert asked[-1][0] == ("net", "draw", {"net": "sph"})
    explorer.build_button.click()
    assert asked[-1] == (("mof", "sets"), {"initial": {"topology": "sph"}})


@needs_merged
def test_build_on_a_net_with_no_linker_set_opens_the_general_builder(
        window, monkeypatch):
    """The mixed-linker builder lists only the nets a set can be
    worked out on, so a merged net it does not list goes to the
    general one rather than to a dialog that cannot show it."""
    from xtal.mof import merged, merged_nets

    asked = []
    monkeypatch.setattr(window, "run_module_action",
                        lambda *a, **k: asked.append(a))
    explorer = window.open_net_explorer()
    name = next(r.name for r in merged_nets.table()
                if r.name not in merged.set_nets()
                and explorer.choose(r.name))
    explorer.build_button.click()
    assert asked[-1] == ("mof", "build")
    assert name


def test_each_builder_has_its_own_entry_and_the_explorer_is_a_net_one(
        window):
    """Modules > MOF builder holds the five builders and Modules > Net
    builder the explorer; each entry opens its own dialog."""
    from xtalapp.dialogs import module_dialog

    labels = [a.text() for a in
              window._module_submenus["mof"].actions()]
    assert labels == ["Build a framework (MOF)...",
                      "Build a pore-partitioned MOF (pacs)...",
                      "Build a supertetrahedral MOF...",
                      "Build a mixed-linker MOF (merged net)...",
                      "Build a rod framework..."]
    net = [a.text() for a in window._module_submenus["net"].actions()]
    assert "Merged-net explorer..." in net
    dialogs = {MODULES.find(f"mof.{name}")[1].dialog for name in
               ("build", "pacs", "supertetrahedra", "sets", "rod")}
    assert len(dialogs) == 5
    assert all(module_dialog(name) is not None for name in dialogs)


@needs_merged
def test_a_merged_net_drawn_by_the_net_builder_opens_with_its_groups(
        window, qtbot):
    from xtal.modules.job import Job
    from xtalapp.document import Document

    _module, action = MODULES.find("net.draw")
    result = action.run(Job(params={"net": "sph"}))
    assert result.structure is not None
    document = Document(result.structure)
    assert [g.name for g in document.atom_groups] == ["spn", "hxg"]
    assert all(g.color is not None for g in document.atom_groups)


@needs_database
@pytest.mark.parametrize("entry",
                         ["build", "pacs", "supertetrahedra", "sets"])
def test_no_builder_needs_scrolling_sideways(qtbot, window, entry):
    """The rows' combo boxes sized to their longest block held every
    builder at 715 px, and one net with a dozen vertex kinds gave the
    net list a scroll bar of its own; a laptop's dialog scrolled
    sideways for both."""
    from PySide6.QtCore import Qt

    built = _builder(qtbot, window, entry)
    assert built.scroll.widget().minimumSizeHint().width() <= 560
    assert (built.topologies.horizontalScrollBarPolicy()
            == Qt.ScrollBarAlwaysOff)
    assert built.topologies.textElideMode() == Qt.ElideRight


@needs_database
@pytest.mark.skipif(not __import__("xtal.build", fromlist=["installed"])
                    .installed(), reason="needs the build extra")
def test_the_chosen_partitioner_is_drawn(pacs):
    """tpt picked: its molecule in the column of the node's and the
    linker's pictures, three points on its nitrogens; None picked: the
    same box, empty."""
    box = _acs(pacs)
    assert not box.picture.isHidden() and box.picture._block is None
    assert box.set_value("tpt")
    drawn = box.picture._block
    assert drawn.name == "tpt" and len(drawn.connections) == 3
    assert drawn.formula == "C18H12N6"
    from PySide6.QtWidgets import QApplication

    pacs.show()
    QApplication.processEvents()
    edge = next(r for r in pacs._rows if r.slot.is_edge)
    right = box.picture.mapTo(pacs, box.picture.rect().topRight()).x()
    assert right == edge.preview.mapTo(
        pacs, edge.preview.rect().topRight()).x()
    assert "close the cell" in box.count.text()
    box.set_value("")
    assert box.picture._block is None and not box.picture.isHidden()


@needs_database
def test_each_window_says_its_rough_size_on_the_blocks_chosen(st):
    """sod on N589 and BTC: the 6-ring's trimers about 10 A out and a
    hexatopic filler of about 5.6 A donor radius, said as rough; a
    face with no trimer to measure says only the count."""
    box = _sod(st)
    six = box._notes[6][0].text()
    assert "A from its middle" in six and "(rough)" in six
    assert "6-topic filler of ~5." in six
    box.set_blocks(st._topology, {})
    assert "rough" not in box._notes[6][0].text()


@needs_database
def test_a_partitioner_drawn_from_the_row_is_listed_and_chosen(
        pacs, monkeypatch):
    """Draw writes into the workspace's blocks/partitioners, never
    blocks/ itself, and the drawing is then a row of the list,
    ranked like the rest and selected."""
    from pathlib import Path

    from xtal.mof import partition
    from xtalapp.dialogs.draw_block import DrawBlockDialog

    box = _acs(pacs)
    asked = {}

    def ask(slot, folder, parent=None, smiles=""):
        asked.update(slot=slot, folder=folder, smiles=smiles)
        path = Path(folder) / "my-tpt.xyz"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_tpt_block_text())
        return path

    monkeypatch.setattr(DrawBlockDialog, "ask", staticmethod(ask))
    box.set_value("tpt")
    box.draw.click()
    assert asked["slot"].coordination == 3 and asked["slot"].nitrogen
    assert Path(asked["folder"]).name == partition.DRAWN
    assert asked["smiles"] == partition.partitioner("tpt").smiles
    assert box.value() == "my-tpt"
    assert pacs.values()["partition"] == "my-tpt"
    assert "my-tpt" in box.choice.currentText()


def _tpt_block_text():
    pytest.importorskip("rdkit")
    from xtal.mof import partition

    return partition.drawn("tpt").text()


@needs_database
def test_a_six_connected_slot_starts_on_n589_never_a_polydentate_block(
        qtbot, window):
    """Nothing named, a node row took the top of its list, and the top
    of the six-connected list is MFU4l_Kuratowski, a chelating node:
    every net an entry opened without blocks of its own started on
    it.  Six-connected starts on N589, any other count on its first
    monodentate block."""
    built = _builder(qtbot, window, "build")
    assert built._select("acs")
    assert built._rows[0].block() == "N589"
    assert built._select("tbo")
    nodes = [r for r in built._rows if not r.slot.is_edge]
    for row in nodes:
        block = built.catalog.building_block(row.block())
        assert not block.is_polydentate


@needs_database
@pytest.mark.parametrize("entry, doi", [
    ("build", "10.1021/acsami.1c02471"),
    ("pacs", "10.1021/ja512137t"),
    ("pacs", "10.1021/acs.accounts.6b00526"),
    ("supertetrahedra", "10.1038/s44160-023-00401-8"),
    ("sets", "10.1021/jacs.8b04745"),
    ("sets", "10.1126/science.ads7866"),
])
def test_each_builder_cites_the_papers_its_feature_comes_from(
        qtbot, window, entry, doi):
    """Each entry cites its own feature's papers above PORMAKE and the
    RCSR, which every entry cites."""
    urls = _builder(qtbot, window, entry).sources.urls()
    assert f"https://doi.org/{doi}" in urls
    assert "https://doi.org/10.1021/ar800124u" in urls


@needs_merged
def test_the_net_explorer_cites_the_merged_nets_papers(window):
    urls = window.open_net_explorer().sources.urls()
    assert "https://doi.org/10.1126/science.ads7866" in urls
    assert "https://doi.org/10.1021/jacs.8b04745" in urls
