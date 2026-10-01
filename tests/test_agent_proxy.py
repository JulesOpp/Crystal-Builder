"""``xtal mcp`` as the window's stdio door.

A client that only speaks stdio (Claude Desktop, Cursor) starts
``xtal mcp``; with a window serving, its tools must be the window's
-- its tabs -- and with none, the headless session it always was.
The window is in this process and the stdio side is a real ``xtal
mcp`` process, as a client would start it.
"""

import json
import os
import socket
import subprocess
import sys
import threading
import time

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")
pytest.importorskip("mcp")

from PySide6.QtWidgets import QWidget  # noqa: E402

from xtal.agent import discovery  # noqa: E402
from xtal.agent.session import Session  # noqa: E402
from xtal.agent.tools import NO_SESSION  # noqa: E402
from xtal.io import write_cif  # noqa: E402
from xtalapp.mainwindow import MainWindow  # noqa: E402
from xtalapp.settings import AppSettings  # noqa: E402


class _Stub(QWidget):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document


@pytest.fixture
def appdata(tmp_path, monkeypatch):
    folder = tmp_path / "appdata"
    monkeypatch.setenv(discovery.ENV, str(folder))
    return folder


@pytest.fixture
def window(qtbot, tmp_path, appdata):
    settings = AppSettings("CrystalBuilderTest", f"Proxy{tmp_path.name}")
    settings.clear_window()
    settings.last_directory = str(tmp_path)
    win = MainWindow(viewport_factory=_Stub, settings=settings)
    qtbot.addWidget(win)
    return win


def _message(method, ident=None, params=None):
    message = {"jsonrpc": "2.0", "method": method}
    if ident is not None:
        message["id"] = ident
    if params is not None:
        message["params"] = params
    return json.dumps(message) + "\n"


def _stdio_inspect(qtbot, tmp_path, appdata, *flags):
    """``inspect`` asked of a real ``xtal mcp`` over its stdin, the GUI
    thread turning meanwhile so a proxied call can be served."""
    env = dict(os.environ, PYTHONWARNINGS="error::DeprecationWarning")
    env[discovery.ENV] = str(appdata)
    process = subprocess.Popen(
        [sys.executable, "-m", "xtal.cli", "mcp", *flags],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, cwd=tmp_path, env=env)
    out = {}

    def talk():
        try:
            process.stdin.write(_message("initialize", 1, {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"}}))
            process.stdin.write(_message("notifications/initialized"))
            process.stdin.write(_message("tools/call", 2, {
                "name": "inspect", "arguments": {}}))
            process.stdin.flush()
            for line in process.stdout:
                reply = json.loads(line)
                if reply.get("id") == 2:
                    out["reply"] = reply
                    break
        finally:
            process.stdin.close()
            out["stderr"] = process.stderr.read()
            out["code"] = process.wait(timeout=30)

    thread = threading.Thread(target=talk, daemon=True)
    thread.start()
    qtbot.waitUntil(lambda: "code" in out, timeout=60000)
    assert out["code"] == 0, out["stderr"]
    assert "Traceback" not in out["stderr"]
    assert out["stderr"].strip() == ""
    content = out["reply"]["result"]["content"]
    return json.loads(content[0]["text"])


@pytest.mark.slow
def test_xtal_mcp_proxies_to_a_live_window_and_falls_back_headless(
        qtbot, window, tmp_path, appdata, rutile):
    cif = tmp_path / "rutile.cif"
    write_cif(rutile, cif)
    assert window.open_path(cif) is not None
    dialog = window.preferences_dialog()
    qtbot.addWidget(dialog)
    with qtbot.waitSignal(window.agent_server.started, timeout=10000):
        dialog.page("AI assistant").serve.setChecked(True)
    formula = Session(rutile).inspect().formula

    proxied = _stdio_inspect(qtbot, tmp_path, appdata)
    assert proxied["formula"] == formula

    headless = _stdio_inspect(qtbot, tmp_path, appdata, "--headless")
    assert NO_SESSION in headless["message"]

    window.agent_server.stop()
    assert discovery.read(appdata) is None
    fallen_back = _stdio_inspect(qtbot, tmp_path, appdata)
    assert NO_SESSION in fallen_back["message"]


class _Proxy:
    """A real ``xtal mcp`` proxying to ``window``, its replies by id
    with the moment each arrived."""

    def __init__(self, qtbot, tmp_path, appdata):
        env = dict(os.environ, PYTHONWARNINGS="error::DeprecationWarning")
        env[discovery.ENV] = str(appdata)
        self.qtbot = qtbot
        self.process = subprocess.Popen(
            [sys.executable, "-m", "xtal.cli", "mcp"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, cwd=tmp_path, env=env)
        self.replies = {}
        threading.Thread(target=self._read, daemon=True).start()
        self.send(_message("initialize", 1, {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"}}),
            _message("notifications/initialized"))

    def _read(self):
        for line in self.process.stdout:
            reply = json.loads(line)
            if "id" in reply:
                self.replies[reply["id"]] = (time.monotonic(), reply)

    def send(self, *messages):
        for message in messages:
            self.process.stdin.write(message)
        self.process.stdin.flush()

    def inspect(self, ident, timeout=60000):
        """``inspect`` asked, and its result with the seconds it took."""
        asked = time.monotonic()
        self.send(_message("tools/call", ident, {
            "name": "inspect", "arguments": {}}))
        self.qtbot.waitUntil(lambda: ident in self.replies,
                             timeout=timeout)
        answered, reply = self.replies[ident]
        return reply["result"], answered - asked

    def finish(self) -> str:
        """Its stderr, once it has gone; killed if it has not."""
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait()
        return self.process.stderr.read()


def _serving(qtbot, window, tmp_path, rutile):
    cif = tmp_path / "rutile.cif"
    write_cif(rutile, cif)
    assert window.open_path(cif) is not None
    with socket.socket() as free:
        free.bind(("127.0.0.1", 0))
        window.settings.agent_port = free.getsockname()[1]
    dialog = window.preferences_dialog()
    qtbot.addWidget(dialog)
    with qtbot.waitSignal(window.agent_server.started, timeout=10000):
        dialog.page("AI assistant").serve.setChecked(True)


def _answered(result) -> None:
    assert not result.get("isError"), result
    assert "formula" in result["content"][0]["text"]


@pytest.mark.slow
def test_a_proxy_whose_window_stops_serving_says_so_and_exits(
        qtbot, window, tmp_path, appdata, rutile):
    """The SDK's client waits an hour for an answer that will never
    come from a window that has gone, and the assistant waited with
    it.  The next call is answered with the reason, and the proxy
    exits non-zero so the client can start it again."""
    _serving(qtbot, window, tmp_path, rutile)
    proxy = _Proxy(qtbot, tmp_path, appdata)
    try:
        _answered(proxy.inspect(2)[0])
        window.agent_server.stop()
        result, took = proxy.inspect(3, timeout=15000)
        assert took < 15
        assert result["isError"]
        assert "stopped serving" in result["content"][0]["text"]
        assert proxy.process.wait(timeout=15) != 0
    finally:
        said = proxy.finish()
    assert "stopped serving" in said
    assert "Traceback" not in said


@pytest.mark.slow
def test_a_proxy_whose_session_the_window_ended_says_so_and_exits(
        qtbot, window, tmp_path, appdata, rutile):
    """Off and on again, the window answers on the same port to the
    same token, so the probe passes -- but the proxy's session went
    with the old server, and every call came back "Session
    terminated" while the proxy stayed up, unable to recover."""
    _serving(qtbot, window, tmp_path, rutile)
    server = window.agent_server
    port = server.port
    proxy = _Proxy(qtbot, tmp_path, appdata)
    try:
        _answered(proxy.inspect(2)[0])
        server.stop()
        with qtbot.waitSignal(server.started, timeout=10000):
            server.start()
        assert server.port == port
        result, took = proxy.inspect(3, timeout=15000)
        assert took < 15
        assert result["isError"]
        assert "session" in result["content"][0]["text"].lower()
        assert "terminated" in result["content"][0]["text"]
        assert proxy.process.wait(timeout=15) != 0
    finally:
        said = proxy.finish()
        server.stop()
    assert "terminated" in said
    assert "Traceback" not in said
