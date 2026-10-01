"""The discovery file: how ``xtal mcp`` finds the window to proxy to.

A file left behind by a window that crashed names a pid that is gone
and a port nobody answers on -- or, worse, one somebody else answers
on.  ``xtal mcp`` believing it would hand the assistant a connection
error instead of the headless session it should have had.
"""

import os
import socket
import stat
import subprocess
import sys

import pytest

from xtal.agent import discovery


def _entry(folder, pid, port):
    discovery.write(folder, port=port, token="0" * 32, pid=pid,
                    version="test")
    return discovery.read(folder)


def test_discovery_of_a_dead_pid_is_not_alive(tmp_path):
    """A window that crashed leaves its file; its pid is the proof."""
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    entry = _entry(tmp_path, gone.pid, 7781)

    assert entry["pid"] == gone.pid
    assert not discovery.alive(entry)


def test_a_live_pid_with_nobody_listening_is_not_alive(tmp_path):
    """The pid is this test's own and alive, but nothing answers on
    the port: a window that stopped serving without removing it."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    entry = _entry(tmp_path, os.getpid(), port)

    assert not discovery.alive(entry)


def test_the_file_is_private_and_reads_back(tmp_path):
    """The token is a key to the window: nobody else on the machine
    may read it -- not even through a half-written file left behind
    by a crash, readable by everyone."""
    leftover = tmp_path / f".{discovery.FILE}.{os.getpid()}"
    leftover.write_text("{}")
    leftover.chmod(0o644)
    path = discovery.write(tmp_path, port=7790, token="ab" * 16,
                           pid=os.getpid(), version="1.2")

    entry = discovery.read(tmp_path)
    assert entry == {"port": 7790, "token": "ab" * 16,
                     "pid": os.getpid(), "version": "1.2",
                     "url": "http://127.0.0.1:7790/mcp"}
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize("text", ["", "{", "[]", '{"port": 1}'])
def test_a_missing_or_mangled_file_is_no_window(tmp_path, text):
    assert discovery.read(tmp_path) is None
    (tmp_path / discovery.FILE).write_text(text)
    assert discovery.read(tmp_path) is None


def test_removing_leaves_another_servers_file_alone(tmp_path):
    """A window that refused to start, because another one was
    listening, must not take that one's file away when it stops."""
    discovery.write(tmp_path, port=7781, token="a" * 32, pid=1,
                    version="1")
    discovery.remove(tmp_path, token="b" * 32)
    assert discovery.read(tmp_path) is not None
    discovery.remove(tmp_path, token="a" * 32)
    assert discovery.read(tmp_path) is None


def test_the_folder_is_the_environments_when_it_names_one(
        tmp_path, monkeypatch):
    monkeypatch.setenv(discovery.ENV, str(tmp_path))
    assert discovery.folder() == tmp_path
    assert discovery.folder(default=tmp_path / "other") == tmp_path
    monkeypatch.delenv(discovery.ENV)
    assert discovery.folder(default=tmp_path / "other") == \
        tmp_path / "other"
    assert discovery.folder() == discovery.platform_folder()
