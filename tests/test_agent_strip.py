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

from PySide6.QtCore import Qt  # noqa: E402
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
    assert strip.isHidden()


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


def test_restore_is_withdrawn_once_redo_holds_other_steps_on_top(
        window, tab, serving):
    """Counting is not enough: after Revert took the person's P1 and
    the assistant's A1, one more Ctrl+Z puts X0 on top of Redo, and a
    Restore of two steps would redo X0 and A1 and leave P1 behind."""
    tab.apply(lambda s: None, label="X0")
    session = window.agent_host.current()
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    tab.apply(lambda s: None, label="P1")
    strip = _strip(window, tab)
    (burst,) = changes.bursts(tab.stack)
    strip.revert(burst.number)
    assert strip.action_button.text() == "Restore"
    tab.undo()
    assert not strip.action_button.text().startswith("Restore")
    assert not strip.action_button.isEnabled()
    strip.restore()
    assert tab.stack.depth == 0


@pytest.fixture
def clock(monkeypatch):
    """``changes.clock`` moved by hand, so nobody sleeps."""
    now = [1000.0]
    monkeypatch.setattr(changes, "clock", lambda: now[0])
    return now


def test_a_relaxation_in_the_window_longer_than_the_gap_is_one_burst(
        window, tab, clock, monkeypatch):
    """The window relaxes a copy and lands the result on the tab; the
    gap measured to the landing read a two-minute optimize as the
    person pausing, and split the request in two."""
    from xtal.ff import optimize as ff_optimize

    real = ff_optimize.run

    def slow(*args, **kwargs):
        clock[0] += 2 * changes.BURST_GAP
        return real(*args, **kwargs)

    monkeypatch.setattr(ff_optimize, "run", slow)
    session = window.agent_host.current()
    session.checkpoint("Prepare and relax")
    session.set_element([0], "Zr")
    assert session.optimize(engine="uff", max_steps=20).undo_label
    assert [(b.label, b.steps) for b in changes.bursts(tab.stack)] == [
        ("Prepare and relax", 2)]


def test_a_long_calculation_in_the_window_counts_as_the_assistant_working(
        window, tab, clock, monkeypatch):
    """``energy`` is answered by a copy's session; unless the tab's
    hears it, the step after a long one is measured from before it and
    opens a burst of its own."""
    from xtal.agent.session import Session

    real = Session.energy

    def slow(self, *args, **kwargs):
        clock[0] += 2 * changes.BURST_GAP
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Session, "energy", slow)
    session = window.agent_host.current()
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    assert session.energy(engine="uff").ok
    session.add_atom("O", frac=[0.2, 0.3, 0.4])
    assert {origin_of(c).burst for c in tab.stack.done()} == {1}


def _history(strip, monkeypatch):
    from xtalapp import menus

    shown = []
    monkeypatch.setattr(menus, "popup",
                        lambda menu, position: shown.append(menu))
    strip.history_button.click()
    (menu,) = shown
    return menu


def test_history_shows_why_an_entry_is_greyed(window, tab, serving):
    """A greyed entry's reason is its tooltip, and a menu hides
    tooltips unless told: the person saw a dead entry and no why."""
    window.agent_host.current().add_atom("O", frac=[0.1, 0.2, 0.3])
    assert _strip(window, tab).history_menu().toolTipsVisible()


def test_the_assistants_label_is_shown_as_plain_text(window, tab,
                                                     serving,
                                                     monkeypatch):
    """The label is the assistant's words: read as markup, it could
    restyle the strip or the tooltip, and an ampersand would vanish
    into a menu mnemonic."""
    from PySide6.QtGui import QTextDocument

    session = window.agent_host.current()
    session.checkpoint("<b>R&D</b>")
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    strip = _strip(window, tab)
    tip = strip.label.toolTip()
    shown = QTextDocument()
    shown.setHtml(tip)
    assert "<b>R&D</b>" in shown.toPlainText()
    assert strip.label.textFormat() == Qt.PlainText
    (entry,) = [a for a in _history(strip, monkeypatch).actions()
                if a.text()]
    assert "<b>R&D</b>" in entry.iconText()


def test_the_line_puts_the_request_first(window, tab, serving):
    """Elided from the right in a narrow column, the line must keep
    what the request was, not who made it."""
    session = window.agent_host.current()
    session.checkpoint("Two oxygens")
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    assert _strip(window, tab).label.text().startswith("Two oxygens · ")


def test_revert_greys_when_a_trajectory_starts_playing(window, tab,
                                                       serving):
    """Playback refuses undo as a hold does, and announces itself on
    its own signal: unheard, Revert looked pressable and did
    nothing."""
    from xtal.io.trajectory import Trajectory, frame_of
    from xtalapp.widgets.agent_strip import HELD

    window.agent_host.current().add_atom("O", frac=[0.1, 0.2, 0.3])
    strip = _strip(window, tab)
    assert strip.action_button.isEnabled()
    moved = tab.structure.copy()
    moved.sites[0].frac = moved.sites[0].frac + [0.01, 0.0, 0.0]
    moved.touch()
    tab.open_trajectory(Trajectory(
        [frame_of(tab.structure, step=0), frame_of(moved, step=1)]))
    assert not strip.action_button.isEnabled()
    assert strip.action_button.toolTip() == HELD


def test_restore_survives_switching_tabs_and_back(window, tab, serving,
                                                  tmp_path, quartz):
    """Looking at another tab is not an edit: forgetting the Revert
    there left the person no way back to what it took."""
    window.agent_host.current().add_atom("O", frac=[0.1, 0.2, 0.3])
    strip = _strip(window, tab)
    strip.revert(changes.bursts(tab.stack)[0].number)
    other = tmp_path / "quartz.cif"
    write_cif(quartz, other)
    assert window.open_path(other) is not None
    assert strip._document is not tab
    window.tabs.setCurrentIndex(window.documents.index(tab))
    assert strip._document is tab
    assert strip.action_button.text() == "Restore"
    strip.restore()
    assert tab.stack.depth == 1


def test_historys_revert_says_it_takes_the_persons_later_edits(
        window, tab, serving, monkeypatch):
    """The strip's button says so before it is pressed; History's
    Revert of an older burst takes the same edits and must say it
    too."""
    session = window.agent_host.current()
    session.checkpoint("First")
    session.add_atom("O", frac=[0.1, 0.2, 0.3])
    session.checkpoint("Second")
    session.add_atom("O", frac=[0.2, 0.3, 0.4])
    tab.apply(lambda s: None, label="Person's edit")
    texts = [a.text() for a in _history(_strip(window, tab),
                                        monkeypatch).actions()]
    assert "Revert: First (and 1 later assistant change; also undoes " \
        "1 of yours)" in texts
    assert "Revert: Second (also undoes 1 of yours)" in texts


# -- the view ----------------------------------------------------------

def _play_back(tab):
    """The tab put into playback: two frames, as a trajectory opens."""
    from xtal.io.trajectory import Trajectory, frame_of

    moved = tab.structure.copy()
    moved.sites[0].frac = moved.sites[0].frac + [0.01, 0.0, 0.0]
    moved.touch()
    tab.open_trajectory(Trajectory(
        [frame_of(tab.structure, step=0), frame_of(moved, step=1)]))
    assert tab.is_playing


def test_set_view_in_the_window_changes_the_tabs_own_view(window, tab):
    """The tab's ``Document.view`` is what the scene draws and a Save
    writes; a ``set_view`` that only moved the session's private dict
    answered ok and changed nothing the person could see."""
    session = window.agent_host.current()
    heard = []
    tab.viewChanged.connect(lambda: heard.append(True))
    depth = tab.stack.depth
    style, rings = tab.view.style, tab.view.show_rings
    assert (style, rings) != ("polyhedra", True)
    answer = session.set_view({"style": "polyhedra", "show_rings": True})
    assert answer.ok, answer.message
    assert (tab.view.style, tab.view.show_rings) == ("polyhedra", True)
    assert heard
    assert session._view == {}
    assert answer.data["changed"] == {"style": "polyhedra",
                                      "show_rings": True}
    assert answer.data["was"] == {"style": style, "show_rings": rings}
    # Not an undo step, so the strip has nothing to list.
    assert tab.stack.depth == depth


def test_the_style_panel_shows_the_style_the_assistant_set(window, tab):
    """The person reads the style off the panel: a panel left showing
    the old one contradicts the picture, and the next touch of it
    would put the old style back."""
    from xtalapp.viewport import styles

    assert tab.view.style != "polyhedra"
    window.agent_host.current().set_view({"style": "polyhedra"})
    assert window.style_dock.style.currentText() == \
        styles.get("polyhedra").label


def test_set_view_is_refused_while_the_tab_plays_back(window, tab):
    """Playback is redrawing the tab frame by frame; the refusal says
    so, where a change landing under it would look ignored."""
    session = window.agent_host.current()
    style = tab.view.style
    _play_back(tab)
    answer = session.set_view({"style": "polyhedra"})
    assert "WINDOW_BUSY" in _codes(answer)
    assert tab.view.style == style


def test_set_view_is_answered_while_a_calculation_runs(window, tab):
    """A calculation holds the structure, not how it is drawn: refused
    here, an assistant could not restyle the tab while it waited."""
    session = window.agent_host.current()
    tab.hold("a test calculation")
    try:
        with AgentCalculation(window, "optimize"):
            answer = session.set_view({"style": "spacefill"})
    finally:
        tab.release()
    assert answer.ok, answer.message
    assert tab.view.style == "spacefill"


def test_view_in_the_window_reads_the_tabs_settings(window, tab):
    """What the person chose in the Style panel is the view; reading
    the session's own dict instead gave the defaults."""
    tab.update_view(style="spacefill", show_rings=True)
    _play_back(tab)
    answer = window.agent_host.current().view()
    assert answer.ok, answer.message
    assert answer.data["view"]["style"] == "spacefill"
    assert answer.data["view"]["show_rings"] is True


def test_the_windows_render_takes_the_same_arguments_as_headless():
    """One tool schema serves both hosts: a default that differs here
    is a different answer to the same call."""
    import inspect

    from xtal.agent.session import Session
    from xtalapp.agent_host import WindowSession

    assert inspect.signature(WindowSession.render) == \
        inspect.signature(Session.render)


def test_a_display_range_over_the_size_limit_leaves_the_tab_alone(
        window, tmp_path, halite):
    """The window's set_view answers through Session.set_view, so the
    size limit holds there too: forty cells a side of halite is
    512 000 atoms, and drawing it froze the window."""
    cif = tmp_path / "halite.cif"
    write_cif(halite, cif)
    tab = window.open_path(cif)
    session = window.agent_host.current()
    assert session.document is tab
    before = tab.view.to_dict()
    whole = [-20, 20]
    answer = session.set_view({"range_a": whole, "range_b": whole,
                               "range_c": whole})
    assert _codes(answer) == ["SIZE_LIMIT"]
    assert tab.view.to_dict() == before
