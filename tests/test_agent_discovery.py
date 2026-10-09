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


def test_the_launcher_beside_the_running_python_comes_before_path(
        tmp_path, monkeypatch):
    """A virtual environment nobody activated runs the window with its
    own ``xtal`` beside its Python, and another install's ``xtal`` on
    PATH would serve the assistant an older ``xtal mcp`` -- the line
    the Preferences page shows must name the one beside us."""
    bin_ = tmp_path / "venv" / "bin"
    bin_.mkdir(parents=True)
    other = tmp_path / "elsewhere" / discovery.launcher_file_name()
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "executable", str(bin_ / "python"))
    monkeypatch.setattr(discovery.shutil, "which",
                        lambda name: str(other))
    beside = bin_ / discovery.launcher_file_name()

    assert discovery.launcher() == other
    beside.write_text("")
    assert discovery.launcher() == beside

    beside.unlink()
    monkeypatch.setattr(discovery.shutil, "which", lambda name: None)
    assert discovery.launcher() == beside


def test_the_launcher_command_names_the_appimage_when_running_from_one(
        tmp_path, monkeypatch):
    """Inside an AppImage the ``xtal`` beside the window is in a mount
    that goes when the window quits, so a client given that path finds
    nothing the next time it starts; the ``.AppImage`` file lasts, and
    its ``AppRun`` starts the CLI when asked for ``xtal``."""
    image = tmp_path / "Crystal_Builder-1.0-x86_64.AppImage"
    image.write_bytes(b"")
    monkeypatch.setenv("APPIMAGE", str(image))

    assert discovery.launcher_command() == [str(image), "xtal"]


def test_the_launcher_command_is_the_xtal_beside_the_app_otherwise(
        tmp_path, monkeypatch):
    """Everywhere else the line is :func:`launcher` alone, as it was;
    an ``APPIMAGE`` left in the environment naming a file that is not
    there is not an AppImage to run."""
    monkeypatch.delenv("APPIMAGE", raising=False)
    assert discovery.launcher_command() == [str(discovery.launcher())]

    monkeypatch.setenv("APPIMAGE", str(tmp_path / "gone.AppImage"))
    assert discovery.launcher_command() == [str(discovery.launcher())]


def test_removing_the_file_never_raises(tmp_path, monkeypatch):
    """Windows refuses to delete a file ``xtal mcp`` has open; the
    window's close must still reach the workers it stops after."""
    discovery.write(tmp_path, port=7781, token="a" * 32, pid=1,
                    version="1")

    def refused(self, missing_ok=False):
        raise PermissionError(13, "in use", str(self))

    monkeypatch.setattr(discovery.Path, "unlink", refused)
    discovery.remove(tmp_path, token="a" * 32)
    discovery.remove(tmp_path)
