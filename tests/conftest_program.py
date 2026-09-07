"""A stand-in for a binary the application shells out to.

Every test that exercises :mod:`xtal.modules.process` without the real
DFTB+ or Zeo++ writes a small Python program and points the module's
environment variable at it.  On a Unix machine that is a file with a
``#!`` line and the executable bit, and it works because running a
script is something the *kernel* does.

Windows has nothing like it.  ``CreateProcess`` reads the first bytes
of the file, finds no PE header, and the launch fails with
``[WinError 193] %1 is not a valid Win32 application`` -- which
:class:`~xtal.modules.process.ExternalProcess` then reports, correctly
for its own purposes, as *not found on PATH*.  That is one error and
twenty-four failures, and none of them are about the module.

So on Windows the body goes in a ``.py`` beside a ``.bat`` that calls
this interpreter on it, and the ``.bat`` is what gets launched: a
batch file is the one kind of script Windows will start from a bare
path, which is the same reason ``npm.cmd`` is what you run there.

Helpers rather than fixtures, following ``conftest_ff.py`` and
``conftest_zeo.py``: three test modules want this, and a fixture
defined in one and imported into another is a redefinition rather
than a share.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def write_program(directory, name: str, body: str) -> Path:
    """Write *body* as a runnable program called *name*, and say
    where it is.

    The interpreter is :data:`sys.executable` and not whatever
    ``python`` is on PATH -- in a virtual environment those are
    different, and the difference shows up as a stand-in that will
    not start.
    """
    directory = Path(directory)
    if os.name != "nt":
        script = directory / name
        script.write_text(f"#!{sys.executable}\n{body}")
        script.chmod(0o755)
        return script

    script = directory / f"{name}.py"
    script.write_text(body)
    launcher = directory / f"{name}.bat"
    # `@echo off` so the command line does not land in the output the
    # tests read back, and `%*` because the whole point of some of
    # these stand-ins is to record the arguments they were given.
    launcher.write_text(
        f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n')
    return launcher
