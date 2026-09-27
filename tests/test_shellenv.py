"""The PATH an application opened from Finder is given, and the one it
takes instead.

macOS starts an application from Finder, the Dock or Spotlight with the
system's four folders as its PATH -- no Homebrew, no conda -- so a
program installed the ordinary way was found when Crystal Builder was
started from a terminal and not otherwise.  The login shell's PATH is
the one the user set up, and the application asks the shell for it.

Every shell here is a stand-in script: it prints what a real one's
startup files do before answering, or hangs, or answers.
"""

import sys
import time

import pytest

from xtalapp import shellenv

pytestmark = pytest.mark.skipif(sys.platform == "win32",
                                reason="the stand-in shells are sh")


def a_shell(tmp_path, body: str) -> str:
    """A stand-in login shell: ``shell -ilc COMMAND`` runs the body,
    then COMMAND."""
    shell = tmp_path / "fake-shell"
    shell.write_text(f'#!/bin/sh\n{body}\neval "$2"\n')
    shell.chmod(0o755)
    return str(shell)


def test_the_login_shell_path_is_read_past_what_its_startup_files_say(
        tmp_path):
    """A conda banner or a "Last login" line comes before the answer."""
    shell = a_shell(tmp_path,
                    'echo "Last login: Fri on ttys001"\n'
                    'echo "(base) conda says hello"\n'
                    'PATH=/opt/homebrew/bin:/usr/bin:/bin; export PATH')

    assert shellenv.login_path(shell) == "/opt/homebrew/bin:/usr/bin:/bin"


def test_a_shell_that_hangs_is_given_up_on(tmp_path):
    """A broken startup file must not stop the application opening."""
    shell = a_shell(tmp_path, "sleep 30")
    started = time.monotonic()

    assert shellenv.login_path(shell, timeout=0.5) is None
    assert time.monotonic() - started < 5


def test_a_shell_that_is_not_there_is_no_answer(tmp_path):
    assert shellenv.login_path(str(tmp_path / "no-such-shell")) is None


def test_the_shell_path_goes_first_and_nothing_is_lost():
    assert shellenv.merged("/opt/homebrew/bin:/usr/bin",
                           "/usr/bin:/bin:/custom") == \
        "/opt/homebrew/bin:/usr/bin:/bin:/custom"


def test_opened_from_finder_the_login_shell_path_is_taken(tmp_path):
    shell = a_shell(tmp_path,
                    "PATH=/opt/homebrew/bin:/usr/bin; export PATH")
    environ = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "SHELL": shell}

    shellenv.adopt(environ, platform="darwin")

    assert environ["PATH"] == \
        "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def test_started_from_a_terminal_the_path_is_left_alone(tmp_path):
    """A terminal may have a conda environment activated, and the login
    shell's PATH would put the base environment in front of it."""
    shell = a_shell(tmp_path,
                    "PATH=/opt/homebrew/bin:/usr/bin; export PATH")
    environ = {"PATH": "/envs/dftb/bin:/usr/bin", "SHELL": shell,
               "TERM": "xterm-256color"}

    shellenv.adopt(environ, platform="darwin")

    assert environ["PATH"] == "/envs/dftb/bin:/usr/bin"


def test_off_macos_the_path_is_left_alone(tmp_path):
    shell = a_shell(tmp_path,
                    "PATH=/opt/homebrew/bin:/usr/bin; export PATH")
    environ = {"PATH": "/usr/bin", "SHELL": shell}

    shellenv.adopt(environ, platform="linux")

    assert environ["PATH"] == "/usr/bin"
