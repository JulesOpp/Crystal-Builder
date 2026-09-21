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
    first; ``as-found`` stays, one down, for PORMAKE's own build."""
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
