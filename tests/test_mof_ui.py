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
from xtal.core.structure import Site, Structure  # noqa: E402
from xtal.io import write_cif  # noqa: E402
from xtal.modules import MODULES  # noqa: E402
from xtal.modules.job import JobResult  # noqa: E402
from xtal.modules.registry import Action, Module  # noqa: E402
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


MAKER = Module(
    name="maker", label="Maker",
    actions=(Action(name="make", label="Make one",
                    needs_structure=False, writes_run_folder=True,
                    run=made_structure),))


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
    assert window.documents[0].title == "made up"


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
    run_and_wait(window, qtbot, "maker", "make")
    assert not window.documents[0].modified
    assert window.documents[0].path is None


def test_a_build_puts_its_run_under_an_entry_of_its_own(
        window, qtbot, quick, tmp_path, rutile):
    """Not under whichever crystal happened to be in front.

    A framework built from nothing filed in MOF-5's folder is a filing
    error somebody then has to undo, and ``Workspace.add_document``
    exists for exactly this.
    """
    source = tmp_path / "rutile.cif"
    write_cif(rutile, source)
    window.set_workspace(tmp_path / "ws", create=True)
    document = window.open_path(source)

    run_and_wait(window, qtbot, "maker", "make")
    names = {entry.name for entry in window.workspace.entries()}
    assert "Maker" in names
    assert document.entry.name in names
    assert not list((document.entry.path).glob("*maker*"))


def test_a_build_with_no_workspace_still_opens_its_tab(window, qtbot,
                                                       quick):
    """A run with nowhere to write still answers.  The answer is a
    framework in a tab, and only the CIF is lost."""
    assert window.workspace is None
    run_and_wait(window, qtbot, "maker", "make")
    assert len(window.documents) == 1


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
    nothing else -- the values come back in the same dict."""
    from xtalapp.dialogs.mof_build import MofBuildDialog

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
