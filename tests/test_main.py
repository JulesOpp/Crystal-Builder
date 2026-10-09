"""``xtalapp.main``'s environment, before anything imports Qt.

The entry point chooses the Qt platform at import time and nowhere
else, so the choice is only observable in an interpreter that has not
imported Qt yet -- which the suite, with pytest-qt in it, is not.  The
probe is therefore a child process, the same shape
``tests/test_mof_builder.py`` uses to ask what a build imports.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

#: What the child prints: the platform choice ``main.py`` made, or
#: ``unset`` where it made none.
PROBE = ("import xtalapp.main, os; "
         "print(os.environ.get('QT_QPA_PLATFORM') or 'unset')")

#: The three variables the choice reads, cleared before every probe so
#: that the machine running the suite does not decide the answer.
CHOICE = ("QT_QPA_PLATFORM", "WAYLAND_DISPLAY", "DISPLAY")

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="the X11 choice is Linux's, and main.py makes it there only")


def probe(**environment) -> str:
    """Import ``xtalapp.main`` in a child and return what it chose."""
    env = {name: value for name, value in os.environ.items()
           if name not in CHOICE}
    env.update(environment)
    run = subprocess.run([sys.executable, "-c", PROBE], cwd=ROOT,
                         env=env, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    return run.stdout.strip()


def test_a_wayland_session_that_has_xwayland_is_asked_for_xcb():
    """Qt 6 picks Wayland on a session that offers it, and VTK's Qt
    bridge is X11: without this the first document with a 3D view
    dies on ``XChangeWindowAttributes`` with BadWindow."""
    assert probe(WAYLAND_DISPLAY="wayland-0", DISPLAY=":0") == "xcb"


def test_a_wayland_session_without_xwayland_is_left_alone():
    """With no DISPLAY there is no X server to ask for, and forcing
    xcb would be a window that cannot open at all rather than a 3D
    view that cannot draw."""
    assert probe(WAYLAND_DISPLAY="wayland-0") == "unset"


def test_an_x11_session_is_left_alone():
    assert probe(DISPLAY=":0") == "unset"


def test_an_explicit_platform_still_wins():
    """Somebody who set QT_QPA_PLATFORM knows something this does
    not."""
    assert probe(WAYLAND_DISPLAY="wayland-0", DISPLAY=":0",
                 QT_QPA_PLATFORM="wayland") == "wayland"
