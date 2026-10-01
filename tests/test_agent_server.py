"""The window's MCP server: an assistant drives the open tabs over HTTP.

A real server thread, a real SDK client on a thread of its own, and a
real window whose GUI thread serves every verb; only the viewport is a
stub.  What breaks if these regress: an assistant that cannot connect,
one that can without the token, a window that will not quit while a
call waits on it, or a discovery file left naming a dead server.
"""

import json
import os
import socket
import stat
import threading
import time

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")
pytest.importorskip("mcp")

import anyio  # noqa: E402
import httpx  # noqa: E402
from mcp import ClientSession  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QWidget  # noqa: E402

from xtal.agent import discovery, proxy  # noqa: E402
from xtal.agent.session import Session  # noqa: E402
from xtal.io import write_cif  # noqa: E402
from xtalapp import applog  # noqa: E402
from xtalapp.agent_host import STOPPED, WindowSession  # noqa: E402
from xtalapp.agent_server import AgentServer  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402

PAGE = "AI assistant"


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def appdata(tmp_path, monkeypatch):
    folder = tmp_path / "appdata"
    monkeypatch.setenv(discovery.ENV, str(folder))
    return folder


def _window(qtbot, tmp_path, name="Server"):
    settings = AppSettings("CrystalBuilderTest", f"{name}{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


@pytest.fixture
def window(qtbot, tmp_path, appdata):
    return _window(qtbot, tmp_path)


def _rutile_tab(window, tmp_path, rutile):
    cif = tmp_path / "rutile.cif"
    write_cif(rutile, cif)
    assert window.open_path(cif) is not None
    return cif


def _switch_on(qtbot, window):
    """The way a person does it: the page's checkbox."""
    dialog = window.preferences_dialog()
    qtbot.addWidget(dialog)
    page = dialog.page(PAGE)
    with qtbot.waitSignal(window.agent_server.started, timeout=10000):
        page.serve.setChecked(True)
    return page


def _in_a_thread(qtbot, call, timeout=30000):
    """``call()`` on a thread of its own, the GUI thread turning until
    it is answered -- as a client in another process would be."""
    out = {}

    def work():
        try:
            out["answer"] = call()
        except BaseException as exc:          # noqa: BLE001 -- re-raised
            out["error"] = exc

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    qtbot.waitUntil(lambda: "answer" in out or "error" in out,
                    timeout=timeout)
    thread.join(5)
    return out


def _call(server, tool, arguments=None):
    """One tool call through the SDK's own client, with the token."""
    async def go():
        async with proxy.connect(server.url, server.token) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                return await session.call_tool(tool, arguments or {})
    return lambda: anyio.run(go)


def _in_the_background(call):
    out = {}

    def work():
        try:
            out["answer"] = call()
        except BaseException as exc:          # noqa: BLE001 -- recorded
            out["error"] = exc

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    return thread, out


def _answer(qtbot, server, tool, arguments=None):
    out = _in_a_thread(qtbot, _call(server, tool, arguments))
    if "error" in out:
        raise out["error"]
    assert "answer" in out, repr(out.get("error"))
    result = out["answer"]
    assert not result.isError, result.content
    return json.loads(result.content[0].text)


def test_turning_the_preference_on_starts_the_server_and_writes_the_discovery_file(  # noqa: E501
        qtbot, window, appdata):
    """On is a server answering on loopback and a file saying where,
    readable by nobody else -- the token in it is a key to the
    window."""
    _switch_on(qtbot, window)
    server = window.agent_server

    assert window.settings.agent_serve
    assert server.running
    entry = discovery.read(appdata)
    assert entry["port"] == server.port
    assert entry["token"] == server.token
    assert entry["pid"] == os.getpid()
    assert entry["url"] == server.url == \
        f"http://127.0.0.1:{server.port}/mcp"
    assert len(server.token) == 32
    if os.name == "posix":
        mode = (appdata / discovery.FILE).stat().st_mode
        assert stat.S_IMODE(mode) == 0o600
    assert discovery.alive(entry)


def test_turning_the_preference_off_stops_it_and_removes_the_file(
        qtbot, window, appdata):
    page = _switch_on(qtbot, window)
    server = window.agent_server
    entry = discovery.read(appdata)

    with qtbot.waitSignal(server.stopped, timeout=10000):
        page.serve.setChecked(False)

    assert not window.settings.agent_serve
    assert not server.running
    assert discovery.read(appdata) is None
    assert not discovery.alive(entry)


def test_a_client_on_another_thread_is_served_by_the_gui_thread(
        qtbot, monkeypatch, window, tmp_path, rutile):
    """The SDK's client, on a thread of its own, asks ``inspect`` of
    the open tab; the tab's structure is read on the GUI thread and
    nowhere else, or the server races the viewport drawing it."""
    _rutile_tab(window, tmp_path, rutile)
    _switch_on(qtbot, window)
    readers = []
    real = WindowSession.structure

    def structure(self):
        readers.append(threading.current_thread())
        return real.fget(self)

    monkeypatch.setattr(WindowSession, "structure", property(structure))

    answer = _answer(qtbot, window.agent_server, "inspect")

    assert answer["formula"] == Session(rutile).inspect().formula
    assert readers
    assert set(readers) == {threading.main_thread()}


def test_a_wrong_token_is_refused(qtbot, window):
    """Any page in a browser can reach loopback; the token is what
    stops it driving the window."""
    _switch_on(qtbot, window)
    server = window.agent_server
    hello = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "0"}}}
    accept = {"Accept": "application/json, text/event-stream"}
    with httpx.Client(trust_env=False, timeout=10) as client:
        wrong = client.post(server.url, json=hello, headers={
            **accept, "Authorization": "Bearer " + "0" * 32})
        missing = client.post(server.url, json=hello, headers=accept)
        bare_get = client.get(server.url)
        right = client.post(server.url, json=hello, headers={
            **accept, "Authorization": f"Bearer {server.token}"})

    assert wrong.status_code == 401
    assert missing.status_code == 401
    assert bare_get.status_code == 401
    assert right.status_code == 200


def test_a_file_naming_another_servers_port_is_not_alive(
        qtbot, window, tmp_path):
    """A window that crashed leaves its file; another may since be
    listening on that port, and is not the one the file's token is
    for.  ``xtal mcp`` would proxy into a wall of 401s."""
    _switch_on(qtbot, window)
    server = window.agent_server
    discovery.write(tmp_path, port=server.port, token="0" * 32,
                    pid=os.getpid(), version="old")

    assert not discovery.alive(discovery.read(tmp_path))


def test_a_busy_port_falls_back_to_a_free_one(qtbot, window, appdata):
    """Somebody else on the preferred port is not a reason to refuse:
    the OS picks another, and the file and the page say which.  The
    port held is one the OS chose rather than 7781 itself, which a
    parallel test worker may be holding already."""
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        taken = busy.getsockname()[1]
        server = AgentServer(window, port=taken)
        with qtbot.waitSignal(server.started, timeout=10000) as started:
            host, port = server.start()
        try:
            assert host == "127.0.0.1"
            assert port != taken
            assert started.args == [port]
            assert server.port == port
            assert discovery.read(appdata)["port"] == port
            assert discovery.alive(discovery.read(appdata))
        finally:
            server.stop()


def test_off_and_on_again_keeps_the_port_a_client_was_given(
        qtbot, window):
    """The pasted line names the port.  Stopping closes a connected
    client's connections from the server's end, which leaves the port
    in TIME_WAIT for half a minute; that must not move the server to
    another port when it is turned off and on again.  The port is
    one the OS chose, not 7781, which a parallel worker may take in
    the moment between the stop and the start."""
    with socket.socket() as free:
        free.bind(("127.0.0.1", 0))
        port = free.getsockname()[1]
    window.settings.agent_port = port
    _switch_on(qtbot, window)
    server = window.agent_server
    assert server.port == port
    asked, hang_up = threading.Event(), threading.Event()

    async def connected():
        async with proxy.connect(server.url, server.token) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                await session.call_tool("documents", {})
                asked.set()
                await anyio.to_thread.run_sync(hang_up.wait, 20)

    client, _out = _in_the_background(lambda: anyio.run(connected))
    qtbot.waitUntil(asked.is_set, timeout=20000)
    server.stop()
    hang_up.set()
    qtbot.waitUntil(lambda: not client.is_alive(), timeout=20000)

    with qtbot.waitSignal(server.started, timeout=10000):
        server.start()
    assert server.port == port


def test_the_help_action_opens_preferences_on_the_assistant_page(
        monkeypatch, window):
    shown = []

    class _Preferences:
        def show_page(self, title):
            shown.append(title)

        def exec(self):
            shown.append("exec")

    monkeypatch.setattr(window, "preferences_dialog",
                        lambda: _Preferences())
    action = window.actions_["connect_ai_assistant"]
    action.trigger()

    assert shown == [PAGE, "exec"]
    assert action.text().replace("&", "") == "Connect an AI assistant..."
    entries = [a for a in window.menuBar().actions()
               if a.text().replace("&", "") == "Help"][0].menu().actions()
    names = [a for a in entries if not a.isSeparator()]
    after = names.index(window.actions_["install_ai_skill"]) + 1
    assert names[after] is action


def test_closing_the_window_stops_the_server(qtbot, window, appdata):
    """A server outliving its window would answer for tabs that are
    gone, and its file would send the next ``xtal mcp`` to it."""
    _switch_on(qtbot, window)
    server = window.agent_server
    entry = discovery.read(appdata)

    window.close()

    assert not server.running
    assert discovery.read(appdata) is None
    assert not discovery.alive(entry)


def test_stopping_while_a_call_waits_on_the_window_does_not_hang(
        qtbot, monkeypatch, window, tmp_path, rutile):
    """The deadlock Task 4 named: the server's thread blocked on the
    GUI thread, and the GUI thread stopping the server.  Stopping
    turns the GUI while it waits, so the call it was waiting on is
    answered, and the next one is refused rather than queued.

    The refusal is read where the tool made it: the client itself may
    lose it, since its next request can meet a server already gone.
    """
    _rutile_tab(window, tmp_path, rutile)
    _switch_on(qtbot, window)
    server = window.agent_server
    bridge = window.agent_host.bridge
    answers = []
    real = WindowSession.inspect

    def inspect(session, *args, **kwargs):
        answers.append(real(session, *args, **kwargs))
        return answers[-1]

    monkeypatch.setattr(WindowSession, "inspect", inspect)
    client, _out = _in_the_background(_call(server, "inspect"))
    # The GUI thread is not turning, so the call waits on it.
    deadline = time.monotonic() + 20
    while bridge._pending is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert bridge._pending is not None

    began = time.monotonic()
    server.stop()
    took = time.monotonic() - began

    assert took < 3.5
    assert not server.running
    qtbot.waitUntil(lambda: bool(answers) and not client.is_alive(),
                    timeout=20000)
    answer = answers[0]
    assert [d.code for d in answer.diagnostics] == ["WINDOW_BUSY"]
    assert "closing" in answer.message


def test_a_client_and_each_verb_it_lands_are_said_in_the_status_bar(
        qtbot, window, tmp_path, rutile):
    """The person is watching: what the assistant did is said where
    the window says what it did itself."""
    _rutile_tab(window, tmp_path, rutile)
    _switch_on(qtbot, window)
    server = window.agent_server
    said = []
    window.statusBar().messageChanged.connect(said.append)

    with qtbot.waitSignal(server.clientConnected, timeout=20000):
        answer = _answer(qtbot, server, "add_atom",
                         {"element": "O", "frac": [0.5, 0.5, 0.5]})

    assert answer["ok"]
    assert any("AI assistant connected" in s for s in said)
    assert f"AI assistant: add_atom: {answer['message']}" in said


def test_a_second_window_does_not_start_over_a_live_one(
        qtbot, window, tmp_path, appdata):
    """Two windows cannot both be what ``xtal mcp`` finds: the second
    says who is listening and leaves the first's file alone."""
    _switch_on(qtbot, window)
    first = window.agent_server
    other = _window(qtbot, tmp_path, "Second")
    dialog = other.preferences_dialog()
    qtbot.addWidget(dialog)
    page = dialog.page(PAGE)

    with qtbot.waitSignal(other.agent_server.failed, timeout=10000):
        page.serve.setChecked(True)

    assert not other.agent_server.running
    assert (f"another window is already listening on port {first.port}"
            in page.status.text())
    assert discovery.read(appdata)["token"] == first.token
    other.close()
    assert discovery.read(appdata)["token"] == first.token


def test_the_core_and_the_window_agree_on_the_discovery_folder():
    """``xtal mcp`` has no Qt to ask, so the rule is written twice."""
    assert discovery.platform_folder() == applog.app_data()


class _HeldRelaxation:
    """``optimize``'s compute half held until released: the copy's
    session (a plain :class:`Session`) waits, then relaxes for real."""

    def __init__(self, monkeypatch):
        self.entered = threading.Event()
        self.release = threading.Event()
        real = Session._relax

        def held(session, args, options):
            self.entered.set()
            self.release.wait(30)
            return real(session, args, options)

        monkeypatch.setattr(Session, "_relax", held)


def test_a_call_abandoned_at_stop_cannot_apply_after_a_restart(
        qtbot, monkeypatch, window, tmp_path, rutile):
    """A relaxation still computing when the server stopped is left to
    finish on its thread.  If the server is started again meanwhile,
    its apply must be refused: its client has gone, and the person
    would see the tab move with nobody having asked."""
    _rutile_tab(window, tmp_path, rutile)
    document = window.current_document()
    _switch_on(qtbot, window)
    server = window.agent_server
    held = _HeldRelaxation(monkeypatch)
    applied = []
    real_apply = WindowSession._apply_relaxation

    def apply(session, pending, args):
        answer = real_apply(session, pending, args)
        applied.append(answer)
        return answer

    monkeypatch.setattr(WindowSession, "_apply_relaxation", apply)
    _in_the_background(_call(server, "optimize", {"engine": "uff"}))
    qtbot.waitUntil(held.entered.is_set, timeout=20000)
    positions = [site.frac.copy() for site in document.structure.sites]
    depth = len(document.stack._done)

    began = time.monotonic()
    server.stop()
    assert time.monotonic() - began < 3.5
    with qtbot.waitSignal(server.started, timeout=10000):
        server.start()
    held.release.set()
    qtbot.waitUntil(lambda: bool(applied)
                    and not window.agent_calculations,
                    timeout=30000)

    answer = applied[0]
    assert not answer.ok
    assert answer.message == STOPPED
    codes = [d.code for d in answer.diagnostics]
    assert codes == ["WINDOW_BUSY", "RESULT_NOT_APPLIED"]
    assert len(document.stack._done) == depth
    for site, before in zip(document.structure.sites, positions,
                            strict=True):
        assert (site.frac == before).all()


def test_a_start_during_stop_is_refused_and_the_file_stays_removed(
        qtbot, window, appdata):
    """Stopping turns the event loop, so a timer -- or anything else
    queued -- can ask for a start, or another stop, half way through.
    The start would be undone by the rest of the stop and leave a
    server with no file, or a file with no server."""
    _switch_on(qtbot, window)
    server = window.agent_server
    refused, stops = [], []
    server.stopped.connect(lambda: stops.append(True))

    def meanwhile():
        try:
            server.start()
        except RuntimeError as exc:
            refused.append(str(exc))
        server.stop()

    QTimer.singleShot(0, meanwhile)
    server.stop()

    assert refused == ["stopping"]
    assert not server.running
    assert discovery.read(appdata) is None
    assert stops == [True]


def test_a_running_relaxation_does_not_silence_the_server(
        qtbot, monkeypatch, window, tmp_path, rutile, appdata):
    """While one client's relaxation computes, the server still
    answers: the discovery probe, a look from a second client, and a
    change refused with ``WINDOW_BUSY`` rather than queued behind the
    run."""
    _rutile_tab(window, tmp_path, rutile)
    _switch_on(qtbot, window)
    server = window.agent_server
    held = _HeldRelaxation(monkeypatch)
    first, out = _in_the_background(
        _call(server, "optimize", {"engine": "uff"}))
    qtbot.waitUntil(held.entered.is_set, timeout=20000)

    try:
        assert discovery.alive(discovery.read(appdata))
        looked = _answer(qtbot, server, "inspect")
        refused = _answer(qtbot, server, "add_atom",
                          {"element": "O", "frac": [0.5, 0.5, 0.5]})
    finally:
        held.release.set()

    assert looked["formula"] == Session(rutile).inspect().formula
    assert [d["code"] for d in refused["diagnostics"]] == ["WINDOW_BUSY"]
    qtbot.waitUntil(lambda: not first.is_alive(), timeout=30000)
    relaxed = json.loads(out["answer"].content[0].text)
    assert relaxed["ok"], relaxed
