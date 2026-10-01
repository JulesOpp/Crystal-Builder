"""``xtal mcp``: the tools on stdio, for an assistant that starts it.

An MCP client launches the command and speaks JSON-RPC on its stdin
and stdout, so the test that matters is a real process answering a
real ``initialize`` -- a stray print on stdout, or a warning raised on
import, is a server no client can talk to.
"""

import importlib.util
import json
import os
import subprocess
import sys

import pytest

from xtal import cli, install


def test_xtal_mcp_headless_answers_initialize_over_stdio(tmp_path):
    """What every client sends first.  An answer naming the server,
    and a clean exit when the client hangs up, is the whole of what a
    client needs before it lists the tools."""
    pytest.importorskip("mcp")
    hello = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "0"}}}
    env = dict(os.environ, PYTHONWARNINGS="error::DeprecationWarning")
    finished = subprocess.run(
        [sys.executable, "-m", "xtal.cli", "mcp", "--headless"],
        input=json.dumps(hello) + "\n", capture_output=True, text=True,
        timeout=60, cwd=tmp_path, env=env)
    assert finished.returncode == 0, finished.stderr
    assert "Traceback" not in finished.stderr
    reply = json.loads(finished.stdout.splitlines()[0])
    assert reply["id"] == 1
    assert reply["result"]["serverInfo"]["name"] == "crystal-builder"
    assert reply["result"]["capabilities"]["tools"] is not None


def test_without_the_extra_the_command_says_what_to_install(monkeypatch,
                                                            capsys):
    """An assistant's config names the command; when the extra is
    missing, the person reading the client's log is told the one line
    that fixes it, not shown an ImportError."""
    real = importlib.util.find_spec

    def find_spec(name, *args, **kwargs):
        if name == "mcp" or name.startswith("mcp."):
            return None
        return real(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", find_spec)
    assert cli.main(["mcp", "--headless"]) == 2
    err = capsys.readouterr().err
    assert install.command("mcp") in err


def test_window_mode_says_no_window_is_listening(capsys):
    """``--window`` promises the open window and must not quietly
    hand an assistant a headless server instead."""
    pytest.importorskip("mcp")
    assert cli.main(["mcp", "--window"]) == 2
    assert "no window is listening" in capsys.readouterr().err
