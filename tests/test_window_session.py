"""The window as a Session: an assistant's verbs land in the open tab.

What an assistant does to a structure the person is looking at has to
be what the person could have done: one undo step on that tab's stack,
pushed on the GUI thread, refused while the tab is showing a
trajectory or a calculation is about to overwrite it.  These tests
drive a real window with real documents and real commands; only the
viewport is a stub.
"""

import json
import threading
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QWidget  # noqa: E402

from xtal.agent.session import LOG_NAME, Session  # noqa: E402
from xtal.io import write_cif  # noqa: E402
from xtal.io.trajectory import Trajectory, frame_of  # noqa: E402
from xtalapp.agent_host import AgentCalculation, WindowSession  # noqa: E402
from xtalapp.document import Document  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def window(qtbot, tmp_path):
    settings = AppSettings("CrystalBuilderTest", f"Agent{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def _open(window, tmp_path, structure, name="rutile"):
    cif = tmp_path / f"{name}.cif"
    write_cif(structure, cif)
    document = window.open_path(cif)
    assert document is not None
    return document, cif


@pytest.fixture
def tab(window, tmp_path, rutile):
    """Rutile open in the window, and the session over its tab."""
    document, _cif = _open(window, tmp_path, rutile)
    session = window.agent_host.current()
    assert session.document is document
    return document, session


def _in_a_thread(qtbot, call):
    """``call()`` on a thread of its own, the way the server will make
    it, with the GUI thread kept turning until it is answered."""
    out = {}

    def work():
        try:
            out["answer"] = call()
        except BaseException as exc:         # noqa: BLE001 -- re-raised
            out["error"] = exc

    thread = threading.Thread(target=work)
    thread.start()
    qtbot.waitUntil(lambda: "answer" in out or "error" in out,
                    timeout=20000)
    thread.join()
    if "error" in out:
        raise out["error"]
    return out["answer"]


def _codes(answer) -> list[str]:
    return [d.code for d in answer.diagnostics]


def test_every_structure_verb_lands_as_one_undo_step_in_the_tab(tab):
    """If this breaks, an assistant's edit is two steps in the tab, or
    none, and the person's Ctrl+Z takes back something else."""
    document, session = tab
    # substitute, fill_pores, place_molecule and interpenetrate are
    # left out: the first needs a hydrogen to replace and a group
    # library, the next two a molecule, and the last a framework.
    steps = [
        lambda: session.add_atom("O", frac=[0.5, 0.5, 0.5]),
        lambda: session.set_element([0], "Zr"),
        lambda: session.move_sites([1], frac_delta=[0.01, 0.01, 0]),
        lambda: session.set_cell(4.7, 4.7, 3.0, 90, 90, 90),
        # Before any bond is drawn by hand, which prepare refuses.
        lambda: session.prepare(),
        lambda: session.standardize(),
        lambda: session.set_space_group("P1"),
        lambda: session.add_bond(0, 2),
        lambda: session.set_bond_type(0, 2, 2),
        lambda: session.remove_bond(0, 2),
        lambda: session.add_atom(
            session.structure.sites[1].element,
            frac=list(session.structure.sites[1].frac + [0.02, 0, 0])),
        lambda: session.merge_duplicates(0.5),
        lambda: session.add_atom(
            "N", frac=list(session.cell.frac[2] + [0, 0, 0.45]),
            bonded_to=2),
        lambda: session.add_hydrogens(),
        lambda: session.supercell(1, 1, 2),
        lambda: session.slab((1, 1, 0), layers=2, vacuum=10.0),
        lambda: session.recalculate_bonds(),
        lambda: session.reduce_to_p1(),
        lambda: session.delete_sites([0]),
    ]
    for step in steps:
        depth = len(document.stack._done)
        atoms = document.cell.n_atoms
        answer = step()
        assert answer.ok, answer
        assert "no duplicates" not in answer.message
        assert len(document.stack._done) == depth + 1, answer.verb
        assert document.stack._done[-1].label == answer.undo_label
        assert session.history()[-1] == answer.undo_label
        document.undo()
        assert len(document.stack._done) == depth, answer.verb
        assert document.cell.n_atoms == atoms, answer.verb
        document.redo()
    assert session.modified


def test_a_verb_from_another_thread_is_served_on_the_gui_thread(
        qtbot, monkeypatch, tab):
    """A command run on the server's thread would race the viewport
    drawing the same structure -- the hazard workers.py copies for."""
    document, session = tab
    seen = []
    run = Document.run

    def recording(self, command):
        seen.append(threading.get_ident())
        return run(self, command)

    monkeypatch.setattr(Document, "run", recording)
    answer = _in_a_thread(
        qtbot, lambda: session.add_atom("O", frac=[0.5, 0.5, 0.5]))
    assert answer.ok, answer
    assert seen == [threading.get_ident()]
    assert len(document.stack._done) == 1


def test_the_window_refuses_while_a_trajectory_is_open(tab, rutile):
    """The atoms on screen are a frame; an edit against them would be
    wiped by the next one, and Document.run would raise."""
    document, session = tab
    moved = document.structure.copy()
    moved.sites[0].frac = moved.sites[0].frac + [0.01, 0.0, 0.0]
    moved.touch()
    document.open_trajectory(Trajectory(
        [frame_of(document.structure, step=0), frame_of(moved, step=1)]))
    assert document.is_playing
    for answer in (session.add_atom("O", frac=[0.5, 0.5, 0.5]),
                   session.supercell(1, 1, 2),
                   session.undo(),
                   session.optimize(max_steps=2)):
        assert not answer.ok
        assert _codes(answer) == ["WINDOW_BUSY"], answer
        assert answer.diagnostics[0].level == "error"
    assert not document.stack._done
    # Reading is not editing.
    assert session.inspect().to_dict("none")


def test_the_window_refuses_while_a_calculation_runs(
        monkeypatch, tmp_path, window, tab):
    """The Force Field panel applies its result over whatever is there
    when it finishes; an edit made meanwhile would be overwritten."""
    document, session = tab
    monkeypatch.setattr(window, "has_running_calculation", lambda: True)
    answers = [session.add_atom("O", frac=[0.5, 0.5, 0.5]),
               session.recalculate_bonds(),
               session.prepare(),
               session.undo(), session.redo(),
               session.save(),
               session.energy(),
               session.optimize(max_steps=2),
               session.render(tmp_path / "busy.png")]
    for answer in answers:
        assert not answer.ok, answer
        assert _codes(answer) == ["WINDOW_BUSY"], answer
        # The refusal is the whole answer: a verb that adds to its
        # answer after pushing must not dress a refusal as a success.
        assert "recalculated" not in answer.message
    assert not document.stack._done
    assert not document.path.with_suffix(".xtalproj").exists()


class _Still:
    """A calculator with no forces, which calls ``midway()`` on the
    calculating thread at its first evaluation -- an edit, or a run,
    started in the window while the agent's goes."""

    name = "uff"
    provides_forces = True
    provides_stress = False
    warnings = []

    def __init__(self, n_atoms, midway=None):
        self._n = n_atoms
        self.midway = midway
        self.called = False

    @property
    def n_atoms(self):
        return self._n

    def summary(self):
        return "no forces"

    def stop_with(self, cancel):
        pass

    def compute(self, positions, matrix):
        from xtal.ff.api import Result

        if not self.called:
            self.called = True
            if self.midway is not None:
                self.midway()
        positions = np.asarray(positions, dtype=float)
        return Result(0.0, np.zeros_like(positions), {"none": 0.0})


def _calculating_with(monkeypatch, calculator) -> None:
    monkeypatch.setattr(Session, "_calculator",
                        lambda self, engine, options: (calculator, None))


def _kept(answer) -> Path:
    """The run folder RESULT_NOT_APPLIED names, holding the result."""
    assert _codes(answer)[1] == "RESULT_NOT_APPLIED", answer
    kept = Path(answer.diagnostics[1].where)
    assert (kept / "final.cif").is_file()
    assert answer.data["run"] == str(kept)
    return kept


class _Recording:
    """The real engine, noting the thread of every evaluation and
    calling ``midway()`` at the first."""

    def __init__(self, inner, midway=None):
        self._inner = inner
        self.midway = midway
        self.threads = []

    def compute(self, positions, matrix):
        if not self.threads and self.midway is not None:
            self.midway()
        self.threads.append(threading.get_ident())
        return self._inner.compute(positions, matrix)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _real_engine(monkeypatch, midway=None) -> list:
    """UFF, which moves rutile's oxygens a few thousandths of an
    Angstrom: enough that applying the result is a push."""
    calculators = []
    original = Session._calculator

    def recording(self, engine, options):
        calculator, refused = original(self, engine, options)
        calculators.append(_Recording(calculator, midway))
        return calculators[-1], refused

    monkeypatch.setattr(Session, "_calculator", recording)
    return calculators


def test_a_relaxation_is_not_applied_if_the_tab_changed_meanwhile(
        qtbot, monkeypatch, window, tab):
    """Applying it would put back the geometry from before the
    person's edit, and with it undo the edit nobody undid."""
    document, session = tab
    sites = document.structure.n_sites
    calculator = _Still(document.cell.n_atoms, lambda: (
        window.agent_host.bridge.call(
            lambda: document.add_atom("O", [0.5, 0.5, 0.5]))))
    _calculating_with(monkeypatch, calculator)
    answer = _in_a_thread(qtbot, lambda: session.optimize(max_steps=5))
    assert calculator.called
    assert not answer.ok
    assert _codes(answer)[0] == "DOCUMENT_CHANGED", answer
    _kept(answer)
    assert document.structure.n_sites == sites + 1
    assert len(document.stack._done) == 1
    assert not window.has_running_calculation()


def test_an_edit_queued_between_the_check_and_the_apply_survives(
        qtbot, monkeypatch, tab):
    """The check and the apply are one crossing to the GUI thread.  As
    two, a move the person made between them was put back by the
    relaxation -- whose answer still said ok."""
    from PySide6.QtCore import QTimer

    from xtal.commands import atoms as atom_commands
    from xtalapp.agent_host import WindowSession

    document, session = tab
    moved = document.structure.sites[1].frac + [0.03, 0.0, 0.0]
    landed = []

    def move():
        document.run(atom_commands.MoveSites({1: moved}))
        landed.append(True)

    check = WindowSession._unless_changed

    def checking(self, pending):
        QTimer.singleShot(0, move)
        return check(self, pending)

    monkeypatch.setattr(WindowSession, "_unless_changed", checking)
    _real_engine(monkeypatch)
    answer = _in_a_thread(qtbot, lambda: session.optimize(max_steps=3))
    qtbot.waitUntil(lambda: bool(landed))
    assert answer.ok, answer
    assert "nothing moved" not in answer.message
    # Applied first, and the person's move on top of it.
    assert np.allclose(document.structure.sites[1].frac, moved)
    assert [c.label for c in document.stack._done] == [
        answer.undo_label, atom_commands.MoveSites({1: moved}).label]


def test_a_relaxation_that_no_longer_fits_the_tab_is_refused_not_raised(
        qtbot, monkeypatch, window, tab):
    """Should a change slip past the check, the apply's own refusal --
    a site count that no longer matches -- is an answer, and the run
    is closed with its result, rather than a traceback out of the
    tool with the run left open."""
    from xtalapp.agent_host import WindowSession

    document, session = tab
    monkeypatch.setattr(WindowSession, "_unless_changed",
                        lambda self, pending: None)
    _real_engine(monkeypatch, lambda: window.agent_host.bridge.call(
        lambda: document.add_atom("O", [0.5, 0.5, 0.5])))
    answer = _in_a_thread(qtbot, lambda: session.optimize(max_steps=3))
    assert not answer.ok
    assert _codes(answer)[0] == "DOCUMENT_CHANGED", answer
    _kept(answer)
    assert len(document.stack._done) == 1


def test_a_relaxation_is_not_applied_over_a_run_the_person_started(
        qtbot, monkeypatch, window, tab):
    """A Force Field run started meanwhile applies its own result when
    it finishes; ours landing first would be overwritten by it."""
    document, session = tab
    started = []

    def panel_starts():
        monkeypatch.setattr(window, "has_running_calculation",
                            lambda: True)
        started.append(True)

    _calculating_with(monkeypatch,
                      _Still(document.cell.n_atoms, panel_starts))
    answer = _in_a_thread(qtbot, lambda: session.optimize(max_steps=5))
    assert started
    assert not answer.ok
    assert _codes(answer)[0] == "WINDOW_BUSY", answer
    _kept(answer)
    assert not document.stack._done


def test_a_relaxation_is_not_applied_to_a_tab_the_person_closed(
        qtbot, monkeypatch, window, tmp_path, tab, quartz):
    """The document outlives its tab while the session holds it, and
    the apply pushed onto its orphaned stack -- an answer saying ok
    about a change nobody can see, and a run folder never named."""
    document, session = tab
    _open(window, tmp_path, quartz, name="quartz")

    def close_rutile():
        window.agent_host.bridge.call(lambda: window.close_document(
            window.documents.index(document)))

    _real_engine(monkeypatch, close_rutile)
    answer = _in_a_thread(qtbot, lambda: session.optimize(max_steps=3))
    assert all(d is not document for d in window.documents)
    assert not answer.ok
    assert _codes(answer)[0] == "DOCUMENT_CHANGED", answer
    assert "the tab was closed" in answer.message
    _kept(answer)
    assert not document.stack._done


def test_an_agent_calculation_shows_its_run_folder_in_the_workspace(
        qtbot, monkeypatch, window, tab):
    """``save`` refreshed the Workspace panel and a relaxation or a
    module run did not, so the run folder the answer named was not
    there for the person to open until something else refreshed it."""
    document, session = tab
    refreshed = []
    monkeypatch.setattr(window, "refresh_workspace",
                        lambda: refreshed.append(threading.get_ident()))
    _real_engine(monkeypatch)
    answer = _in_a_thread(qtbot, lambda: session.optimize(max_steps=2))
    assert answer.ok, answer
    qtbot.waitUntil(lambda: bool(refreshed))
    assert refreshed == [threading.get_ident()]

    monkeypatch.setattr(Session, "run", lambda self, action, **params:
                        Session._refused(self, action, params, "no"))
    _in_a_thread(qtbot, lambda: session.run("scan.run"))
    qtbot.waitUntil(lambda: len(refreshed) == 2)


def test_a_relaxation_computes_off_the_gui_thread(qtbot, monkeypatch,
                                                  tab):
    """On the GUI thread the window would stop answering for the whole
    run -- no redraw, and no way to tell it from a crash."""
    document, session = tab
    calculators = _real_engine(monkeypatch)
    answer = _in_a_thread(qtbot, lambda: session.optimize(max_steps=3))
    assert answer.ok, answer
    assert "moved" in answer.message and "nothing" not in answer.message
    threads = calculators[0].threads
    assert threads and threading.get_ident() not in threads
    assert len(document.stack._done) == 1


def test_an_agent_calculation_is_counted_so_quitting_asks_first(
        window, tab):
    """has_running_calculation is what quitting asks and what the
    agent's own gates read: an agent run must count like the panel's.
    The person's edits are not refused meanwhile; DOCUMENT_CHANGED at
    the apply is what keeps them."""
    assert not window.has_running_calculation()
    with AgentCalculation(window, "optimize"):
        assert window.has_running_calculation()
        assert window.statusBar().currentMessage() == \
            "AI assistant: optimize running"
    assert not window.has_running_calculation()


def test_the_log_is_written_to_the_entry(tab):
    """The log is how somebody opening the entry learns an assistant
    worked on it -- written by the window's sessions as by a script's."""
    document, session = tab
    session.add_atom("O", frac=[0.5, 0.5, 0.5])
    session.undo()
    log = document.entry.path / LOG_NAME
    assert log.is_file()
    verbs = [line for line in log.read_text().splitlines() if line]
    assert '"verb": "add_atom"' in verbs[-2]
    assert '"verb": "undo"' in verbs[-1]


def test_render_in_the_window_grabs_the_viewport(monkeypatch, window,
                                                 tmp_path, tab):
    """The window's picture is the person's view of the tab, drawn
    by the viewport in front of them rather than a subprocess."""
    document, session = tab
    viewport = window.tabs.widget(window.documents.index(document))
    calls = []

    def save_image(path, magnification=2, transparent=False):
        calls.append((str(path), threading.get_ident()))
        with open(path, "wb") as out:
            out.write(b"\x89PNG\r\n\x1a\n")

    monkeypatch.setattr(viewport, "save_image", save_image,
                        raising=False)
    out = tmp_path / "view.png"
    out.write_bytes(b"an earlier picture")
    answer = session.render(out)
    assert answer.ok, answer
    assert calls == [(str(out), threading.get_ident())]
    assert answer.data["path"] == str(out)
    assert answer.data["honoured"] == ["path", "view"]
    assert out.read_bytes() != b"an earlier picture"
    assert answer.atoms_after == document.cell.n_atoms
    assert not document.stack._done


def test_the_host_opens_a_new_tab_and_switches_between_them(
        window, tmp_path, rutile, quartz):
    """A document an assistant opens is a tab the person can see, and
    the same file asked for twice is the same tab."""
    host = window.agent_host
    with pytest.raises(LookupError):
        host.current()
    first, rutile_cif = _open(window, tmp_path, rutile)
    session = host.current()
    assert isinstance(session, WindowSession)
    assert session.document is first
    assert host.current() is session

    quartz_cif = tmp_path / "quartz.cif"
    write_cif(quartz, quartz_cif)
    opened = host.open(quartz_cif)
    assert window.tabs.count() == 2
    assert window.current_document() is opened.document
    assert host.current() is opened
    assert opened.path == opened.document.path
    assert [s.document for s in host.sessions()] == window.documents

    # The original path, the workspace's copy: both are this tab.
    assert host.open(rutile_cif) is session
    assert window.current_document() is first
    assert host.current() is session
    assert host.switch(opened.path) is opened
    assert window.current_document() is opened.document
    assert window.tabs.count() == 2

    with pytest.raises(FileNotFoundError):
        host.open(tmp_path / "missing.cif")
    with pytest.raises(LookupError):
        host.switch(tmp_path / "missing.cif")

    window.close_document(window.documents.index(opened.document))
    assert [s.document for s in host.sessions()] == [first]


def test_the_agents_current_tab_does_not_follow_the_persons_clicks(
        window, tmp_path, rutile, quartz):
    """Following the tab in front sent an assistant's next edit into
    whichever structure the person had clicked on meanwhile -- the
    wrong crystal, one undo step the person never asked for.  The
    assistant's document is the one it opened or switched to; the
    front tab is only where it starts."""
    from xtal.agent.tools import _verb_tool

    host = window.agent_host
    first, _cif = _open(window, tmp_path, rutile)
    session = host.current()
    assert session.document is first

    second, quartz_cif = _open(window, tmp_path, quartz, name="quartz")
    assert window.current_document() is second
    assert host.current() is session
    window.tabs.setCurrentIndex(window.documents.index(first))
    window.tabs.setCurrentIndex(window.documents.index(second))
    assert host.current() is session

    switched = host.switch(quartz_cif)
    assert switched.document is second
    window.tabs.setCurrentIndex(window.documents.index(first))
    assert host.current() is switched

    # Its tab closed under it: refused, never the next tab along.
    window.close_document(window.documents.index(second))
    with pytest.raises(LookupError, match="was closed"):
        host.current()
    tool, _description = _verb_tool(host, "add_atom")
    said = json.loads(tool(element="O", frac=[0.5, 0.5, 0.5]))
    assert not said["ok"] and "was closed" in said["message"]
    assert not first.stack._done

    assert host.switch(first.path) is session
    assert host.current() is session


def test_every_window_answer_names_its_document(
        qtbot, monkeypatch, window, tmp_path, tab, quartz):
    """An assistant reading an answer can see which tab it landed in
    -- the one thing a window adds to a headless session's answer."""
    document, session = tab
    named = str(document.path)
    viewport = window.tabs.widget(window.documents.index(document))

    def save_image(path, magnification=2, transparent=False):
        Path(path).write_bytes(b"\x89PNG\r\n\x1a\n")

    monkeypatch.setattr(viewport, "save_image", save_image,
                        raising=False)
    answers = [
        session.add_atom("O", frac=[0.5, 0.5, 0.5]),
        session.select("element", symbols=["O"]),
        session.undo(), session.redo(),
        session.merge_duplicates(0.5),
        session.render(tmp_path / "named.png"),
        session.energy(),
        _in_a_thread(qtbot, lambda: session.optimize(max_steps=2)),
    ]
    monkeypatch.setattr(window, "has_running_calculation", lambda: True)
    answers += [session.add_atom("O", frac=[0.2, 0.2, 0.2]),
                session.energy()]
    for answer in answers:
        assert answer.data.get("document") == named, answer
    assert session.inspect().to_dict()["document"] == named

    # The answers the tools build themselves, around the host.
    from xtal.agent.answers import VerbResult
    from xtal.agent.serve import HeadlessHost
    from xtal.agent.tools import (
        _build_tool,
        _new_tool,
        _open_tool,
        _verb_tool,
    )

    monkeypatch.setattr(window, "has_running_calculation", lambda: False)
    quartz_cif = tmp_path / "quartz.cif"
    write_cif(quartz, quartz_cif)
    built_cif = tmp_path / "built.cif"
    write_cif(quartz, built_cif)

    def built(cls, action, workspace, **params):
        made = Session.open(built_cif, workspace)
        made.built = VerbResult(action, True, "built", data={"run": ""})
        return made

    monkeypatch.setattr(Session, "build", classmethod(built))
    workspace = str(tmp_path / "elsewhere")

    def told(host, make, **kwargs):
        """The tool's answer, and the document the host is on after."""
        fn = make(host)[0] if make is not _verb_tool else make(
            host, kwargs.pop("verb"))[0]
        return json.loads(fn(**kwargs)), host.current().path

    host = window.agent_host
    for host_ in (host, HeadlessHost()):
        if host_ is not host:
            host_.open(document.path)
        calls = [
            told(host_, _verb_tool, verb="save"),
            told(host_, _verb_tool, verb="export",
                 path=str(tmp_path / "named.xyz")),
            told(host_, _open_tool, path=str(quartz_cif)),
            told(host_, _open_tool, path=str(quartz_cif)),
            told(host_, _new_tool, a=5.0, b=5.0, c=5.0, space_group="P1",
                 workspace=workspace),
            told(host_, _build_tool, action="mof.build",
                 workspace=workspace, params={}),
        ]
        for answer, current in calls:
            assert answer["ok"], answer
            if host_ is host:
                assert answer["data"]["document"] == str(current), answer
            else:
                assert "document" not in answer["data"], answer

    # Headless, nothing changes.
    plain = Session(document.structure.copy())
    assert "document" not in plain.add_atom(
        "O", frac=[0.5, 0.5, 0.5]).data
    assert "document" not in plain.inspect().to_dict()
