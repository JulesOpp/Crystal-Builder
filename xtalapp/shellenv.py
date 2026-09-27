"""The PATH the user's login shell has, for an application that was not
given it.

macOS starts an application from Finder, the Dock or Spotlight with
launchd's PATH, ``/usr/bin:/bin:/usr/sbin:/sbin``: no Homebrew, no
conda, nothing the user's shell startup files add.  So ``xtb`` on the
PATH in a terminal was "Not found" in Preferences ▸ Engines when the
same copy of Crystal Builder was opened from the Dock, and the Test
button agreed.  Asking the login shell is how a Finder-launched program
learns the PATH its user actually set up.

Only then: an application started from a terminal already has that
shell's PATH, and it may have a conda environment activated in front
of the base one, which the login shell's PATH would shadow.
"""

import os
import subprocess

_MARKER = "__XTAL_LOGIN_PATH__"

# Long enough for a conda init in a slow startup file; short enough
# that a shell waiting on a prompt costs a moment and not the launch.
TIMEOUT = 5.0


def login_path(shell: str | None = None,
               timeout: float = TIMEOUT) -> str | None:
    """The PATH ``shell`` has as an interactive login shell, or None.

    The answer is marked, because a startup file may print anything
    before it -- a conda banner, a "Last login" line.  None when the
    shell is missing, fails, hangs or never answers.
    """
    shell = shell or os.environ.get("SHELL") or "/bin/zsh"
    command = f'printf "\\n%s%s\\n" {_MARKER} "$PATH"'
    try:
        done = subprocess.run([shell, "-ilc", command],
                              stdin=subprocess.DEVNULL,
                              capture_output=True, text=True,
                              timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    for line in reversed(done.stdout.splitlines()):
        if line.startswith(_MARKER):
            return line[len(_MARKER):] or None
    return None


def merged(first: str, then: str) -> str:
    """``first``'s folders, then any of ``then``'s it did not have."""
    seen: list[str] = []
    for folder in first.split(os.pathsep) + then.split(os.pathsep):
        if folder and folder not in seen:
            seen.append(folder)
    return os.pathsep.join(seen)


def adopt(environ=None, platform: str | None = None) -> str | None:
    """Put the login shell's PATH in front of ``environ``'s, where the
    application was opened from Finder on macOS.

    Returns the PATH it set, or None when it left it alone.
    """
    import sys

    environ = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform
    if platform != "darwin" or "TERM" in environ:
        return None
    found = login_path(environ.get("SHELL"))
    if found is None:
        return None
    environ["PATH"] = merged(found, environ.get("PATH", ""))
    return environ["PATH"]
