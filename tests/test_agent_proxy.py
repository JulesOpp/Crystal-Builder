"""``xtal mcp`` as the window's stdio door.

A client that only speaks stdio (Claude Desktop, Cursor) starts
``xtal mcp``; with a window serving, its tools must be the window's
-- its tabs -- and with none, the headless session it always was.
The window is in this process and the stdio side is a real ``xtal
mcp`` process, as a client would start it.
"""

import json
import os
import subprocess
import sys
import threading

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


@pytest.mark.slow
def test_a_proxy_whose_window_stops_serving_says_so_and_exits(
        qtbot, window, tmp_path, appdata, rutile):
    """The SDK's client waits an hour for an answer that will never
    come from a window that has gone, and the assistant waited with
    it.  The next call is answered with the reason, and the proxy
    exits non-zero so the client can start it again."""
    import time

    cif = tmp_path / "rutile.cif"
    write_cif(rutile, cif)
    assert window.open_path(cif) is not None
    dialog = window.preferences_dialog()
    qtbot.addWidget(dialog)
    with qtbot.waitSignal(window.agent_server.started, timeout=10000):
        dialog.page("AI assistant").serve.setChecked(True)
    env = dict(os.environ, PYTHONWARNINGS="error::DeprecationWarning")
    env[discovery.ENV] = str(appdata)
    process = subprocess.Popen(
        [sys.executable, "-m", "xtal.cli", "mcp"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, cwd=tmp_path, env=env)
    replies = {}

    def read():
        for line in process.stdout:
            reply = json.loads(line)
            if "id" in reply:
                replies[reply["id"]] = (time.monotonic(), reply)

    threading.Thread(target=read, daemon=True).start()
    try:
        process.stdin.write(_message("initialize", 1, {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"}}))
        process.stdin.write(_message("notifications/initialized"))
        process.stdin.write(_message("tools/call", 2, {
            "name": "inspect", "arguments": {}}))
        process.stdin.flush()
        qtbot.waitUntil(lambda: 2 in replies, timeout=60000)
        first = replies[2][1]["result"]
        assert not first.get("isError"), first
        assert "formula" in first["content"][0]["text"]

        window.agent_server.stop()
        asked = time.monotonic()
        process.stdin.write(_message("tools/call", 3, {
            "name": "inspect", "arguments": {}}))
        process.stdin.flush()
        qtbot.waitUntil(lambda: 3 in replies, timeout=15000)
        answered, reply = replies[3]
        assert answered - asked < 15
        result = reply["result"]
        assert result["isError"]
        assert "stopped serving" in result["content"][0]["text"]
        assert process.wait(timeout=15) != 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    said = process.stderr.read()
    assert "stopped serving" in said
    assert "Traceback" not in said
