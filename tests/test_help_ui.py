"""The generated help pages.

They are read off the action registry and the module registry at the
moment the window opens, so what these assert is the generation and
not the prose: a command that gained a tip is in the page without
anybody editing it, and a command that never had one is visible as a
name rather than as a sentence repeating its own name.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QWidget  # noqa: E402

from xtal.modules import MODULES, Action, Module, Param  # noqa: E402
from xtalapp.dialogs.help import (  # noqa: E402
    HelpWindow,
    command_sections,
    commands_html,
    modules_html,
    param_range,
)
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.Yes)
    settings = AppSettings("CrystalBuilderTest",
                           f"Scratch{tmp_path.name}")
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=lambda document, parent=None:
                     QWidget(parent), settings=settings)
    qtbot.addWidget(win)
    return win


def test_the_commands_page_is_grouped_the_way_the_menu_bar_is(window):
    """A user looks for a command where they last saw it, so File is
    the File section and the order is the menu bar's own."""
    titles = [title for title, _rows in command_sections(window)]
    assert titles[:3] == ["File", "Edit", "Select"]
    assert "Help" in titles


def test_a_command_is_described_by_its_own_tip(window):
    rows = {label: (key, tip)
            for _t, entries in command_sections(window)
            for label, key, tip in entries}
    assert rows["Recalculate bonds"][1] == \
        window.actions_["recompute_bonds"].toolTip()


def test_a_command_with_no_tip_does_not_repeat_its_own_name(window):
    """QAction.toolTip falls back to the action's text, so an untipped
    command would otherwise explain itself with its own name."""
    window.actions_.add("_untipped", "Do a thing")
    rows = [row for _t, entries in command_sections(window)
            for row in entries if row[0] == "Do a thing"]
    assert rows == [("Do a thing", "", "")]


def test_a_command_that_opens_a_dialog_does_not_repeat_its_name(window):
    """Qt builds its fallback tooltip by dropping the mnemonic and the
    trailing ellipsis both, so "&Open..." arrives as "Open"."""
    window.actions_.add("_dialogish", "&Do a thing...")
    rows = [row for _t, entries in command_sections(window)
            for row in entries if row[0] == "Do a thing..."]
    assert rows == [("Do a thing...", "", "")]


def test_every_registry_command_reaches_the_page(window):
    """A command reachable only from a context menu is the one a user
    most needs help finding, so nothing in the registry is dropped."""
    listed = {label for _t, entries in command_sections(window)
              for label, _k, _tip in entries}
    for name in window.actions_.names():
        text = window.actions_[name].text().replace("&", "")
        assert any(label.endswith(text) for label in listed), name


def test_a_command_is_listed_once(window):
    """The boundary rules and the styles are in the View menu and in
    the viewport's context menu both."""
    labels = [label for _t, entries in command_sections(window)
              for label, _k, _tip in entries]
    assert len(labels) == len(set(labels))


def test_the_documents_in_the_menus_are_not_commands(window):
    """Open Recent, By element and the dock toggles list files,
    elements and panels rather than things to run, and are built as
    bare actions -- which is the line that keeps them out.

    The samples are the other side of it: each is a registered action
    whose tip says what the structure is, and that is help.
    """
    page = commands_html(window)
    assert "Open Recent" not in page
    assert "By element" not in page
    assert "Open Sample ▸ MOF-5" in page


def test_a_module_parameter_is_documented_by_its_own_help():
    module = MODULES.register(Module(
        name="_helptest", label="Help test",
        description="A module registered by a test",
        actions=(Action(name="go", label="Go", tip="Run the thing",
                        params=(Param("steps", "Steps", kind="int",
                                      default=5, minimum=1,
                                      maximum=99,
                                      help="How many to take"),),
                        run=lambda job: None),)))
    try:
        page = modules_html()
    finally:
        MODULES.unregister(module.name)
    assert "How many to take" in page
    assert "Run the thing" in page
    assert "A module registered by a test" in page


def test_a_parameter_says_what_it_accepts():
    """The kind, the bounds and the default are three of the four
    things a user asks of a field they have never set."""
    assert param_range(Param("t", kind="float", minimum=0.0,
                             maximum=1.0, suffix=" A")) == \
        "float, 0 to 1 A"
    assert param_range(Param("n", kind="int", minimum=1000,
                             maximum=1_000_000)) == \
        "int, 1000 to 1000000"
    assert param_range(Param("c", kind="choice",
                             choices=("fast", "slow"))) == \
        "one of fast, slow"


def test_the_help_window_opens_and_is_kept(window):
    """Modeless, so it can be read beside the structure it is about,
    and built once so the pages are generated once."""
    window.actions_["help_contents"].trigger()
    first = window._help_window
    assert isinstance(first, HelpWindow)
    assert first.isVisible() and not first.isModal()
    window.actions_["help_contents"].trigger()
    assert window._help_window is first
    first.close()
