"""
xtal.agent.discovery
====================
How ``xtal mcp`` finds a window that is serving the tools.

The window writes ``mcp.json`` -- port, token, pid, version, url --
into its application-data folder when its server starts and removes
it when the server stops.  ``xtal mcp`` reads it and proxies to the
window when the file's pid is alive **and** the port answers: a window
that crashed leaves its file behind, and a port can be taken by
somebody else once its owner has gone.

**The folder is decided here, without Qt,** because ``xtal mcp`` runs
without it and both sides have to agree.  The window's is
:func:`xtalapp.applog.app_data`, which asks ``QStandardPaths``;
:func:`platform_folder` is the same rule written out, and a test holds
the two together.  ``XTAL_APP_DATA`` overrides both, so a suite or a
second install can keep its file to itself.

The token is a key to the window, so the file is written readable by
its owner alone, and the token is never logged.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

FILE = "mcp.json"
ENV = "XTAL_APP_DATA"
HOST = "127.0.0.1"
#: :data:`xtalapp.applog.FOLDER`, which this module cannot import.
APP_FOLDER = "CrystalBuilder"
#: Seconds the probe waits.  The window answers from its own thread,
#: never the GUI's, so a live one answers in milliseconds.
PROBE_TIMEOUT = 2.0

_KEYS = ("port", "token", "pid", "version", "url")

log = logging.getLogger(__name__)


def url(port: int) -> str:
    return f"http://{HOST}:{port}/mcp"


def platform_folder() -> Path:
    """``QStandardPaths.GenericDataLocation`` plus ``CrystalBuilder``,
    as :func:`xtalapp.applog.app_data` asks for it."""
    home = Path.home()
    if sys.platform == "darwin":
        root = home / "Library" / "Application Support"
    elif sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA")
                    or home / "AppData" / "Local")
    else:
        root = Path(os.environ.get("XDG_DATA_HOME")
                    or home / ".local" / "share")
    return root / APP_FOLDER


def folder(default=None) -> Path:
    """Where the file is: ``XTAL_APP_DATA`` if set, else ``default``
    (the window passes its own), else :func:`platform_folder`."""
    given = os.environ.get(ENV, "").strip()
    if given:
        return Path(given).expanduser()
    if default is not None:
        return Path(default)
    return platform_folder()


def path(where=None) -> Path:
    return folder(where) / FILE


def write(where, port: int, token: str, pid: int,
          version: str) -> Path:
    """The file, readable by its owner only, replaced whole so a
    reader never sees half of it."""
    target = Path(where) / FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    entry = {"port": int(port), "token": token, "pid": int(pid),
             "version": version, "url": url(port)}
    partial = target.with_name(f".{FILE}.{os.getpid()}")
    # Made afresh, never reopened: a leftover partial keeps whatever
    # mode it had, and the mode given here applies only to a new file.
    partial.unlink(missing_ok=True)
    descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                         0o600)
    if hasattr(os, "fchmod"):
        os.fchmod(descriptor, 0o600)      # whatever the umask says
    with os.fdopen(descriptor, "w", encoding="utf-8") as out:
        json.dump(entry, out)
    os.replace(partial, target)
    return target


def read(where) -> dict | None:
    """The entry, or ``None`` when there is no file or it is not one."""
    try:
        entry = json.loads((Path(where) / FILE).read_text(
            encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(entry, dict) or any(k not in entry for k in _KEYS):
        return None
    return entry


def remove(where, token: str | None = None) -> None:
    """Remove the file -- only if it is ours, when ``token`` says
    whose we are.

    Never raises: Windows refuses to delete a file another process
    has open, as ``xtal mcp`` does while it reads it, and the window
    removes it on its way to stopping its workers.  A file left
    behind names a server that no longer answers, which
    :func:`alive` already treats as none.
    """
    target = Path(where) / FILE
    if token is not None:
        entry = read(where)
        if entry is None or entry["token"] != token:
            return
    try:
        target.unlink(missing_ok=True)
    except OSError as exc:
        log.debug("could not remove %s: %s", target, exc)


def alive(entry: dict) -> bool:
    """The pid is running and the port answers, to this token.

    Any HTTP answer will do but a 401 -- the MCP endpoint answers a
    bare ``GET`` with another 4xx, which still proves it is listening.
    A 401 is a server that does not know the token: another window's,
    on the port a dead one left in its file.
    """
    try:
        pid = int(entry["pid"])
    except (KeyError, TypeError, ValueError):
        return False
    if not _running(pid):
        return False
    request = urllib.request.Request(
        str(entry["url"]),
        headers={"Authorization": f"Bearer {entry['token']}"})
    # No proxy: an HTTP_PROXY in the environment would otherwise be
    # asked about a port on this machine.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=PROBE_TIMEOUT):
            return True
    except urllib.error.HTTPError as answer:
        return answer.code != 401
    except (OSError, ValueError):
        return False


def _running(pid: int) -> bool:
    if sys.platform == "win32":
        return _running_on_windows(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _running_on_windows(pid: int) -> bool:                # pragma: no cover
    # Not os.kill: on Windows that terminates the process, whatever
    # the signal.
    import ctypes

    kernel = ctypes.windll.kernel32
    handle = kernel.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == 259                     # STILL_ACTIVE
    finally:
        kernel.CloseHandle(handle)


#: The ``xtal`` program's name, the one ``packaging/bundle.py`` builds
#: beside the window: without the ``.exe`` Windows gives the file
#: (:func:`launcher_file_name`).
LAUNCHER_NAME = "xtal"


def launcher_file_name() -> str:
    """The ``xtal`` program's file name here.  A packaged build carries
    it beside the application's own executable (``packaging/bundle.py``
    builds it there), and ``xtalapp.selftest`` looks for it by this
    name."""
    suffix = ".exe" if sys.platform == "win32" else ""
    return f"{LAUNCHER_NAME}{suffix}"


def launcher() -> Path:
    """The ``xtal`` command a client's configuration names.

    A frozen build carries it beside the application's own executable.
    A source install has one beside the Python that is running -- a
    virtual environment, activated or not -- and that is the one
    whose package this window is, so it comes before whatever ``xtal``
    is first on ``PATH``, which may be another install's.  The path is
    given even when nothing is there yet, so the line can be shown and
    the reason it fails found.
    """
    beside = Path(sys.executable).with_name(launcher_file_name())
    if getattr(sys, "frozen", False) or beside.exists():
        return beside
    found = shutil.which(LAUNCHER_NAME)
    return Path(found) if found else beside
