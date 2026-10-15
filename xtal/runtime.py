"""
xtal.runtime
============
What a packaged build has to undo in its own environment before it
starts anything.

On Linux, PyInstaller's bootloader puts the bundle's library folder
(``_internal/``) first on ``LD_LIBRARY_PATH`` and keeps the user's own
value in ``LD_LIBRARY_PATH_ORIG``.  Every program this application
starts inherits that -- DFTB+, xTB, Zeo++ and Blender through
:mod:`xtal.modules.process`, and ``xdg-open`` behind every URL Qt
opens -- and a system program then loads the bundle's libstdc++,
libssl or Qt instead of its own, and fails or crashes.  It is the
classic AppImage bug, and PyInstaller's own advice is to put the
original back for children.  This process loses nothing by it: glibc
reads ``LD_LIBRARY_PATH`` once, at start-up, and the bundle's
libraries were found through it then.
"""

from __future__ import annotations

import os
import sys

LIBRARY_PATH = "LD_LIBRARY_PATH"
#: Where the bootloader keeps the user's value; absent if they had none.
ORIGINAL = LIBRARY_PATH + "_ORIG"


def restore_system_library_path(environ=None, platform=None,
                                frozen=None) -> None:
    """Give ``environ`` back the library path the user launched with.

    Only a frozen Linux build is touched: a checkout's path is the
    user's already, and the macOS and Windows builds are not handed
    this one, so a value there is somebody's own.  With no original
    the variable is removed rather than emptied: the user launched
    with none, and children should see none.  Called first thing
    by both entry points, so that everything started afterwards --
    including what Qt starts for itself -- inherits the result.
    """
    environ = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))
    if not (frozen and platform.startswith("linux")):
        return
    original = environ.pop(ORIGINAL, None)
    if original is not None:
        environ[LIBRARY_PATH] = original
    else:
        environ.pop(LIBRARY_PATH, None)
