"""Modules on screen: the menu, the tree, the generated form, the run.

The window is driven with the stub viewport from test_app_shell, so
none of this needs a display, and the module under test is the stub --
which is what lets the worker, the run folder and the Stop button be
checked on a machine with no external binary installed.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QKeySequence  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QLineEdit,
    QMenu,
    QSpinBox,
)

from tests.test_app_shell import StubViewport  # noqa: E402
from xtal.io import write_cif  # noqa: E402
from xtal.modules import MODULES, stub  # noqa: E402
from xtal.modules.registry import (  # noqa: E402
    Action,
    Availability,
    Module,
    Param,
)
from xtalapp.dialogs.module_form import ModuleDialog, ParamForm  # noqa: E402
from xtalapp.docks.modules import MODULE_ROLE, ModuleTree  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


@pytest.fixture
def registered():
    """The stub, in the registry the window reads, for one test."""
    stub.register(MODULES)
    yield MODULES
    MODULES.unregister("stub")


@pytest.fixture
def settings(tmp_path):
    settings = AppSettings("CrystalBuilderTest",
                           f"Modules{tmp_path.name}")
    settings.clear_recent_files()
    settings.last_directory = str(tmp_path)
    settings.last_workspace = ""
    return settings


@pytest.fixture
def window(qtbot, settings, registered):
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
def quick(monkeypatch):
    """Answer the parameter dialog without showing it."""
    asked = []

    def ask(module, action, parent=None, initial=None):
        asked.append((module.name, action.name, initial))
        return action.coerce({"steps": 2, "interval": 0.0,
                              "note": "from the form", "fail": False})

    monkeypatch.setattr(ModuleDialog, "ask", staticmethod(ask))
    return asked


def run_and_wait(window, qtbot, module, action):
    window.run_module_action(module, action)
    qtbot.waitUntil(lambda: window.module_worker is None,
                    timeout=15000)


# ------------------------------------------------------- the menu

def test_the_menu_bar_has_modules_where_calculate_was(window):
    titles = [a.text() for a in window.menuBar().actions()]
    assert "&Modules" in titles
    assert "Ca&lculate" not in titles


def test_the_menu_is_built_from_the_registry(window):
    """Nothing in the window names a module.  A module registered
    before it opens appears without this file changing."""
    submenus = [a.text() for a in window.modules_menu.actions()]
    assert submenus == [m.label for m in MODULES]
    assert "Stub" in submenus


def _submenu(menu, title):
    """The submenu of that name.

    Found among the menu's *children* rather than through
    ``action.menu()``.  PySide6 hands the caller of ``QAction.menu()``
    ownership of the QMenu, so the submenu is destroyed as soon as the
    QAction wrapper that produced it goes out of scope -- and the
    assertion afterwards then fails on a deleted C++ object rather
    than on what it was checking.
    """
    for child in menu.findChildren(QMenu):
        if child.title() == title:
            return child
    raise AssertionError(f"no {title!r} submenu")


def test_the_three_forcefield_entries_moved_unchanged(window):
    forcefield = _submenu(window.modules_menu, "Forcefield")
    entries = [a.text() for a in forcefield.actions()]
    assert entries == ["&Force Field panel", "&Single point energy",
                       "&Optimise geometry"]
    # And they are the very same actions, not copies of them.
    assert forcefield.actions()[1] is window.actions_["single_point"]


def test_the_shortcuts_followed_the_entries_into_the_menu(window):
    forcefield = _submenu(window.modules_menu, "Forcefield")
    shortcuts = {s.toString() for a in forcefield.actions()
                 for s in a.shortcuts()}
    assert QKeySequence("Ctrl+E").toString() in shortcuts
    assert QKeySequence("Ctrl+Shift+E").toString() in shortcuts


def test_a_registry_action_gets_an_action_of_its_own(window):
    assert "module.stub.count" in window.actions_
    assert window.actions_["module.stub.count"].text() == \
        "Count here..."


def test_an_unavailable_module_is_greyed_out_with_the_reason(
        qtbot, settings):
    MODULES.register(Module(
        name="absent", label="Absent", order=800,
        check=lambda: Availability(False, "nothing is installed"),
        actions=(Action(name="go", label="Go",
                        run=lambda job: None),)))
    try:
        win = MainWindow(viewport_factory=StubViewport,
                         settings=settings)
        qtbot.addWidget(win)
        absent = _submenu(win.modules_menu, "Absent")
        assert not absent.isEnabled()
        assert "nothing is installed" in absent.toolTip()
    finally:
        MODULES.unregister("absent")


def test_availability_is_asked_again_when_the_menu_opens(qtbot,
                                                          settings):
    """A binary installed while the window was open should stop the
    module being greyed out, so nothing may cache the answer."""
    installed = []
    MODULES.register(Module(
        name="later", label="Later", order=810,
        check=lambda: Availability(bool(installed), "not yet"),
        actions=(Action(name="go", label="Go",
                        run=lambda job: None),)))
    try:
        win = MainWindow(viewport_factory=StubViewport,
                         settings=settings)
        qtbot.addWidget(win)
        assert not _submenu(win.modules_menu, "Later").isEnabled()
        installed.append(True)
        win.modules_menu.aboutToShow.emit()
        assert _submenu(win.modules_menu, "Later").isEnabled()
    finally:
        MODULES.unregister("later")


# ------------------------------------------------------- the tree

def test_the_tree_shows_every_module_and_its_entries(window):
    tree = window.modules_dock.tree
    labels = []
    for row in range(tree.model_.rowCount()):
        item = tree.model_.item(row)
        labels.append((item.text(),
                       [item.child(c).text()
                        for c in range(item.rowCount())]))
    assert ("Stub", ["Count here...",
                     "Count in a subprocess..."]) in labels


def test_activating_a_leaf_runs_that_action(window, qtbot, quick,
                                            monkeypatch):
    started = []
    monkeypatch.setattr(
        window, "run_module_action",
        lambda m, a: started.append((m, a)))
    tree = window.modules_dock.tree
    index = _index_of(tree, "stub", "count")
    tree.activated.emit(index)
    assert started == [("stub", "count")]


def test_activating_a_module_row_folds_it_rather_than_running(window):
    tree = window.modules_dock.tree
    index = _index_of(tree, "stub", "")
    was = tree.isExpanded(index)
    tree.activated.emit(index)
    assert tree.isExpanded(index) is not was


def test_an_unavailable_module_is_disabled_in_the_tree():
    registry = type(MODULES)()
    registry.register(Module(
        name="absent", label="Absent",
        check=lambda: Availability(False, "no binary here"),
        actions=(Action(name="go", label="Go",
                        run=lambda job: None),)))
    tree = ModuleTree(registry)
    item = tree.model_.item(0)
    assert not item.isEnabled()
    assert "no binary here" in item.toolTip()
    assert not item.child(0).isEnabled()


def _index_of(tree, module, action):
    for row in range(tree.model_.rowCount()):
        item = tree.model_.item(row)
        if item.data(MODULE_ROLE) == (module, ""):
            if not action:
                return tree.model_.indexFromItem(item)
            for child in range(item.rowCount()):
                leaf = item.child(child)
                if leaf.data(MODULE_ROLE) == (module, action):
                    return tree.model_.indexFromItem(leaf)
    raise AssertionError(f"no {module}.{action} in the tree")


# ------------------------------------------------------- the form

def test_a_widget_per_kind(qtbot):
    form = ParamForm((Param("a", kind="bool"),
                      Param("b", kind="int", default=3),
                      Param("c", kind="float", default=1.5),
                      Param("d", kind="choice", choices=("x", "y")),
                      Param("e", kind="text", default="hello")))
    qtbot.addWidget(form)
    assert isinstance(form.widgets["a"], QCheckBox)
    assert isinstance(form.widgets["b"], QSpinBox)
    assert isinstance(form.widgets["c"], QDoubleSpinBox)
    assert isinstance(form.widgets["d"], QComboBox)
    assert isinstance(form.widgets["e"], QLineEdit)
    assert form.values() == {"a": False, "b": 3, "c": 1.5,
                             "d": "x", "e": "hello"}


def test_the_form_hands_back_declared_types(qtbot):
    form = ParamForm((Param("n", kind="int", default=2),))
    qtbot.addWidget(form)
    form.widgets["n"].setValue(9)
    assert form.values() == {"n": 9}
    assert isinstance(form.values()["n"], int)


def test_a_choice_gives_back_its_value_not_its_label(qtbot):
    form = ParamForm((Param("m", kind="choice",
                            choices=(("lbfgs", "L-BFGS"),
                                     ("fire", "FIRE"))),))
    qtbot.addWidget(form)
    form.widgets["m"].setCurrentIndex(1)
    assert form.values() == {"m": "fire"}


def test_a_saved_value_for_a_parameter_that_is_gone_is_ignored(qtbot):
    """A saved set of values outlives the parameter it was saved for,
    and the module that dropped one must still open its own form."""
    form = ParamForm((Param("n", kind="int", default=1),))
    qtbot.addWidget(form)
    form.set_values({"n": 4, "removed_last_year": True})
    assert form.values() == {"n": 4}


def test_an_action_with_no_parameters_gets_no_dialog(qtbot):
    action = Action(name="go", label="Go", run=lambda job: None)
    module = Module(name="m", label="M", actions=(action,))
    assert ModuleDialog.ask(module, action) == {}


def test_the_dialog_is_titled_by_what_it_will_run(qtbot, window):
    module, action = MODULES.find("stub.count")
    dialog = ModuleDialog(module, action, window)
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "Stub: Count here"
    assert dialog.values()["steps"] == 5


# -------------------------------------------------------- running

def test_a_run_leaves_a_folder_under_the_structure(opened, qtbot,
                                                   quick):
    window, document = opened
    run_and_wait(window, qtbot, "stub", "count")

    runs = document.entry.runs()
    assert [r.name for r in runs] == ["stub-count-001"]
    assert (runs[0].path / "counted.txt").read_text() == "1\n2\n"
    assert "counted to 2" in runs[0].log_path.read_text()


def test_what_the_form_collected_is_what_the_run_received(opened,
                                                          qtbot,
                                                          quick):
    window, document = opened
    run_and_wait(window, qtbot, "stub", "count")
    log = document.entry.runs()[0].log_path.read_text()
    assert "note         from the form" in log


def test_the_run_appears_in_the_workspace_tree(opened, qtbot, quick):
    window, _document = opened
    run_and_wait(window, qtbot, "stub", "count")
    names = _tree_labels(window.file_dock.tree)
    assert "stub-count-001" in names


def test_the_log_opens_while_the_run_is_going(opened, qtbot, quick):
    window, document = opened
    run_and_wait(window, qtbot, "stub", "count")
    assert window.log_dock.path == \
        document.entry.runs()[0].log_path


def test_the_parameters_are_offered_again_next_time(opened, qtbot,
                                                    quick):
    window, _document = opened
    run_and_wait(window, qtbot, "stub", "count")
    run_and_wait(window, qtbot, "stub", "count")
    # The second ask was handed what the first run used.
    assert quick[1][2]["note"] == "from the form"


def test_only_one_module_runs_at_a_time(opened, qtbot, monkeypatch):
    window, _document = opened
    monkeypatch.setattr(
        ModuleDialog, "ask",
        staticmethod(lambda m, a, parent=None, initial=None:
                     a.coerce({"steps": 40, "interval": 0.05})))
    window.run_module_action("stub", "count")
    assert window.module_worker is not None
    assert not window.actions_["module.stub.count"].isEnabled()
    window.run_module_action("stub", "subprocess")
    assert window.module_worker.action.name == "count"
    window.stop_module()
    qtbot.waitUntil(lambda: window.module_worker is None,
                    timeout=15000)


def test_stopping_a_run_is_not_a_failure(opened, qtbot, monkeypatch):
    window, document = opened
    monkeypatch.setattr(
        ModuleDialog, "ask",
        staticmethod(lambda m, a, parent=None, initial=None:
                     a.coerce({"steps": 200, "interval": 0.05})))
    window.run_module_action("stub", "count")
    qtbot.waitUntil(lambda: window.module_worker is not None)
    window.stop_module()
    qtbot.waitUntil(lambda: window.module_worker is None,
                    timeout=15000)
    log = document.entry.runs()[0].log_path.read_text()
    assert "where it got to" in log
    assert "failed" not in log


def test_a_failing_run_says_so_and_still_closes_its_log(opened, qtbot,
                                                        monkeypatch):
    window, document = opened
    monkeypatch.setattr(
        ModuleDialog, "ask",
        staticmethod(lambda m, a, parent=None, initial=None:
                     a.coerce({"steps": 1, "interval": 0.0,
                               "fail": True})))
    run_and_wait(window, qtbot, "stub", "count")
    log = document.entry.runs()[0].log_path.read_text()
    assert "asked to fail" in log
    assert "finished" in log


def test_a_module_that_raises_is_reported_not_a_traceback(opened,
                                                          qtbot,
                                                          monkeypatch):
    window, document = opened

    def explode(job):
        raise RuntimeError("the parameter set has no Zn-O pair")

    MODULES.register(Module(
        name="broken", label="Broken", order=850,
        actions=(Action(name="go", label="Go", run=explode),)))
    try:
        window._build_modules_menu()
        run_and_wait(window, qtbot, "broken", "go")
        log = (document.entry.runs()[0].log_path).read_text()
        assert "the run failed: the parameter set has no Zn-O pair" \
            in log
    finally:
        MODULES.unregister("broken")


def test_a_structure_a_module_produced_is_one_undoable_edit(opened,
                                                            qtbot):
    window, document = opened

    def double_the_cell(job):
        from xtal.core import supercell
        from xtal.modules.job import JobResult
        return JobResult(message="doubled",
                         structure=supercell.supercell(
                             job.structure, 2, 1, 1))

    MODULES.register(Module(
        name="doubler", label="Doubler", order=860,
        actions=(Action(name="go", label="Go", run=double_the_cell),)))
    try:
        window._build_modules_menu()
        before = document.structure.lattice.lengths[0]
        run_and_wait(window, qtbot, "doubler", "go")
        assert document.structure.lattice.lengths[0] == \
            pytest.approx(2 * before)
        document.undo()
        assert document.structure.lattice.lengths[0] == \
            pytest.approx(before)
    finally:
        MODULES.unregister("doubler")


def test_a_module_needs_a_structure(window, qtbot, quick):
    """With nothing open there is nothing to run against, and the menu
    entry says so by being disabled."""
    assert not window.actions_["module.stub.count"].isEnabled()
    window.run_module_action("stub", "count")
    assert window.module_worker is None
    assert quick == []


def test_a_document_with_no_workspace_still_runs(window, qtbot, quick,
                                                 tmp_path, rutile):
    """It just leaves nothing behind, which is what this application
    did before there was anywhere to leave anything."""
    source = tmp_path / "rutile.cif"
    write_cif(rutile, source)
    document = window.open_path(source)
    assert document.entry is None
    run_and_wait(window, qtbot, "stub", "count")
    assert window.module_worker is None


def test_the_stop_button_is_only_live_while_something_runs(opened,
                                                           qtbot,
                                                           quick):
    window, _document = opened
    dock = window.modules_dock
    assert not dock.stop_button.isEnabled()
    run_and_wait(window, qtbot, "stub", "count")
    assert not dock.stop_button.isEnabled()
    assert "counted to 2" in dock.status.text()


def _tree_labels(tree) -> list:
    out = []
    stack = [tree.model_.index(r, 0)
             for r in range(tree.model_.rowCount())]
    while stack:
        index = stack.pop()
        out.append(index.data(Qt.DisplayRole))
        for row in range(tree.model_.rowCount(index)):
            stack.append(tree.model_.index(row, 0, index))
    return out


def test_a_frame_being_played_is_not_something_to_run_against(
        opened, qtbot, quick, tmp_path, rutile):
    """The atoms are showing a trajectory frame, so the geometry a
    module would be handed is not the document's."""
    from xtal.io.trajectory import frame_of, write_trajectory

    window, document = opened
    frames = []
    for step in range(3):
        moved = rutile.copy()
        moved.set_frac(1, [0.3053 + 0.004 * step,
                           0.3053 + 0.004 * step, 0.0])
        frames.append(frame_of(moved, step=step))
    path = tmp_path / "run.extxyz"
    write_trajectory(frames, path)
    window.trajectory_dock.set_document(document)
    window.trajectory_dock.open_path(path)
    assert document.is_playing

    window.run_module_action("stub", "count")
    assert window.module_worker is None
    assert quick == []
