"""The assistant's changes in the window: tagged in the tab's own
history, listed by the Agent changes strip, reverted and restored.

What breaks if these regress: a strip that lists the person's edits as
the assistant's, a Revert that takes more than it said, a Restore that
redoes nothing, or an assistant never told its work was taken back.
Real window and tabs; only the viewport is a stub, and the server is
said to be running rather than started.
"""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QWidget  # noqa: E402

from xtal.agent import changes  # noqa: E402
from xtal.agent.changes import origin_of  # noqa: E402
from xtal.io import write_cif  # noqa: E402
from xtalapp.agent_host import AgentCalculation  # noqa: E402
from xtalapp.agent_server import AgentServer  # noqa: E402
from xtalapp.document import DocumentHeld  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("XTAL_APP_DATA", str(tmp_path / "appdata"))
    settings = AppSettings("CrystalBuilderTest", f"Strip{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


@pytest.fixture
def serving(monkeypatch):
    """The strip shows only while an assistant could be connected."""
    monkeypatch.setattr(AgentServer, "running",
                        property(lambda self: True))


@pytest.fixture
def tab(window, tmp_path, rutile):
    cif = tmp_path / "rutile.cif"
    write_cif(rutile, cif)
    document = window.open_path(cif)
    assert document is not None
    return document


def _codes(answer):
    return [d.code for d in answer.diagnostics]


def test_a_window_sessions_steps_are_tagged_in_the_tabs_own_history(
        window, tab):
    """The tab's history is what the strip reads and Undo walks: a tag
    put anywhere else is one the strip never sees."""
    session = window.agent_host.current()
    session.checkpoint("Two oxygens")
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    origin = origin_of(tab.stack.done()[-1])
    assert (origin.verb, origin.label) == ("add_atom", "Two oxygens")


def test_switching_documents_ends_the_burst(window, tab, tmp_path,
                                            quartz):
    """Work on another document is another request: one burst across
    both would be reverted as one."""
    other = tmp_path / "quartz.cif"
    write_cif(quartz, other)
    session = window.agent_host.current()
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    window.agent_host.open(other)
    window.agent_host.switch(tab.path)
    session.add_atom("O", frac=[0.2, 0.3, 0.4])
    assert [origin_of(c).burst for c in tab.stack.done()[-2:]] == [1, 2]


def test_opening_the_document_already_open_ends_the_burst(window, tab):
    """``open`` of a tab already open makes it current as ``switch``
    does, and is as much a new request."""
    session = window.agent_host.current()
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    assert window.agent_host.open(tab.path) is session
    session.add_atom("O", frac=[0.2, 0.3, 0.4])
    assert [origin_of(c).burst for c in tab.stack.done()[-2:]] == [1, 2]


def test_checkpoint_is_answered_while_a_calculation_holds_the_tab(
        window, tab):
    """It changes nothing, so it must not wait behind a relaxation."""
    session = window.agent_host.current()
    tab.hold("a test calculation")
    try:
        with AgentCalculation(window, "optimize"):
            refused = session.add_atom("O", frac=[0.1, 0.2, 0.3])
            answer = session.checkpoint("Next")
    finally:
        tab.release()
    assert "WINDOW_BUSY" in _codes(refused)
    assert answer.ok


def test_a_step_the_held_tab_refused_leaves_the_burst_as_it_was(
        window, tab):
    """A tab held with nothing counted as running gets past the gate,
    and ``Document.run`` refuses; tagged for a step never pushed, the
    next one would open a burst of its own and Revert take half the
    request."""
    session = window.agent_host.current()
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    tab.hold("a test calculation")
    try:
        with pytest.raises(DocumentHeld):
            session.add_atom("O", frac=[0.2, 0.3, 0.4])
    finally:
        tab.release()
    session.add_atom("O", frac=[0.3, 0.4, 0.5])
    assert [(origin_of(c).burst, origin_of(c).step)
            for c in tab.stack.done()[-2:]] == [(1, 1), (1, 2)]


def test_the_assistants_own_undo_in_the_window_is_not_news_to_it(
        window, tab):
    """The window's undo is its own, through ``Document.undo``: told
    its steps were reverted when it undid them itself, an assistant
    inspects for nothing or puts them back."""
    session = window.agent_host.current()
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    undone = session.undo()
    assert undone.ok
    assert "AGENT_CHANGES_REVERTED" not in _codes(undone)
    after = session.add_atom("O", frac=[0.2, 0.3, 0.4])
    assert "AGENT_CHANGES_REVERTED" not in _codes(after)


def test_the_assistants_own_undo_and_redo_in_the_window_keep_its_burst(
        window, tab):
    """Taking back its own misstep is still the same request."""
    session = window.agent_host.current()
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    session.add_atom("O", frac=[0.2, 0.3, 0.4])
    session.undo()
    session.redo()
    session.add_atom("O", frac=[0.3, 0.4, 0.5])
    assert {origin_of(c).burst for c in tab.stack.done()[-3:]} == {1}


def test_the_persons_undo_in_the_tab_is_told_to_the_assistant(window,
                                                              tab):
    """Ctrl+Z in the tab is the person's: the assistant's next answer
    says its step is gone."""
    session = window.agent_host.current()
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    tab.undo()
    told = session.inspect()
    assert "AGENT_CHANGES_REVERTED" in _codes(told)


def _strip(window, tab):
    window.agent_strip.follow(tab)
    window.agent_strip.refresh()
    return window.agent_strip


def test_the_strip_is_hidden_with_no_assistant_or_nothing_it_did(
        window, tab, monkeypatch):
    """A person who never connects an assistant must not see it."""
    strip = _strip(window, tab)
    assert strip.isHidden()
    monkeypatch.setattr(AgentServer, "running",
                        property(lambda self: True))
    strip.refresh()
    assert strip.isHidden()


def test_the_strip_shows_the_latest_burst_with_revert(window, tab,
                                                      serving):
    """The line names the request and its size; without them a person
    cannot tell what Revert would take back."""
    session = window.agent_host.current()
    session.checkpoint("Two oxygens")
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    session.add_atom("O", frac=[0.2, 0.3, 0.4])
    strip = _strip(window, tab)
    assert not strip.isHidden()
    assert "Two oxygens" in strip.label.text()
    assert "2 steps" in strip.label.text()
    assert strip.action_button.text() == "Revert"
    assert strip.action_button.isEnabled()


def test_revert_says_beforehand_what_else_it_takes(window, tab, serving):
    """Linear history: the person's later edit goes too, and they are
    told on the button before they press it."""
    session = window.agent_host.current()
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    tab.apply(lambda s: None, label="Person's edit")
    strip = _strip(window, tab)
    assert "also undoes 1 of yours" in strip.action_button.text()


def test_revert_undoes_exactly_the_plan_and_restore_brings_it_back(
        window, tab, serving):
    """Revert taking more than it said loses work; a Restore that
    redoes less leaves the person short of what they had."""
    session = window.agent_host.current()
    atoms = session.n_atoms
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    session.add_atom("O", frac=[0.2, 0.3, 0.4])
    strip = _strip(window, tab)
    (burst,) = changes.bursts(tab.stack)
    strip.revert(burst.number)
    assert session.n_atoms == atoms
    assert strip.action_button.text() == "Restore"
    assert "Reverted" in strip.label.text()
    strip.restore()
    assert tab.stack.depth == 2
    assert strip.action_button.text().startswith("Revert")


def test_revert_is_greyed_while_a_calculation_holds_the_tab(window, tab,
                                                           serving):
    """An undo under a running optimisation is refused by the
    Document; a button that looked pressable would do nothing."""
    session = window.agent_host.current()
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    strip = _strip(window, tab)
    tab.hold("a test calculation")
    try:
        strip.refresh()
        assert not strip.action_button.isEnabled()
        assert "calculation" in strip.action_button.toolTip()
    finally:
        tab.release()


def test_history_lists_every_burst_through_the_popup_seam(
        window, tab, serving, monkeypatch):
    """Every menu goes through ``menus.popup``: one raised with
    ``QMenu.exec`` cannot be stopped by the suite's guard."""
    from xtalapp import menus

    shown = []
    monkeypatch.setattr(menus, "popup",
                        lambda menu, position: shown.append(menu))
    session = window.agent_host.current()
    session.checkpoint("First")
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    session.checkpoint("Second")
    session.add_atom("O", frac=[0.2, 0.3, 0.4])
    strip = _strip(window, tab)
    strip.history_button.click()
    (menu,) = shown
    texts = [a.text() for a in menu.actions() if a.text()]
    assert any("Second" in t for t in texts)
    assert any("First" in t and "1 later" in t for t in texts)


def test_the_assistant_is_told_after_a_revert_in_the_strip(window, tab,
                                                           serving):
    """The strip reverts through the tab's own undo, so the assistant
    learns of it as of any Ctrl+Z, and does not build on what is
    gone."""
    session = window.agent_host.current()
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    strip = _strip(window, tab)
    (burst,) = changes.bursts(tab.stack)
    strip.revert(burst.number)
    told = session.add_atom("O", frac=[0.2, 0.3, 0.4])
    assert "AGENT_CHANGES_REVERTED" in [d.code for d in told.diagnostics]


def test_restore_gives_back_everything_its_revert_took(window, tab,
                                                       serving):
    """Revert took the person's later edit too; a Restore that brought
    back the burst alone would leave that edit lost in Redo."""
    session = window.agent_host.current()
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    tab.apply(lambda s: None, label="Person's edit")
    strip = _strip(window, tab)
    (burst,) = changes.bursts(tab.stack)
    strip.revert(burst.number)
    assert tab.stack.depth == 0
    strip.restore()
    assert tab.stack.depth == 2
    assert not tab.stack.undone()


def test_an_edit_after_a_revert_takes_restore_away(window, tab, serving):
    """An edit clears Redo; a Restore still offered would redo nothing,
    or something else."""
    session = window.agent_host.current()
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    strip = _strip(window, tab)
    (burst,) = changes.bursts(tab.stack)
    strip.revert(burst.number)
    tab.apply(lambda s: None, label="Person's edit")
    assert strip.isHidden() or not strip.action_button.text().startswith(
        "Restore")


def test_history_restores_a_burst_and_nothing_made_after_it(
        window, tab, serving, monkeypatch):
    """History's Restore is the one burst: redoing the later request
    with it would put back what the person meant to keep reverted."""
    from xtalapp import menus

    shown = []
    monkeypatch.setattr(menus, "popup",
                        lambda menu, position: shown.append(menu))
    session = window.agent_host.current()
    session.checkpoint("First")
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    session.checkpoint("Second")
    session.add_atom("O", frac=[0.2, 0.3, 0.4])
    strip = _strip(window, tab)
    first = changes.bursts(tab.stack)[-1]
    strip.revert(first.number)
    strip.history_button.click()
    (menu,) = shown
    (restore,) = [a for a in menu.actions()
                  if a.text().startswith("Restore: First")]
    assert restore.isEnabled()
    restore.trigger()
    assert tab.stack.depth == 1
    assert [b.applied for b in changes.bursts(tab.stack)] == ["none",
                                                             "all"]
