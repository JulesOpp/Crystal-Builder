"""
xtal.install
============
The command that installs an optional extra, spelled so that it works.

Every feature gated on an extra says what to install when it is
missing, and they all said ``pip install 'crystal-builder[x]'``.  That
is wrong twice over on the only kind of installation there is:

* **A bare ``pip`` is whichever is first on the PATH**, which is often
  not the Python the application is running in, and the package lands
  somewhere the application never looks.
* **``crystal-builder`` is not on PyPI.**  The name resolves only
  against the metadata written when the checkout was installed, and
  that metadata does not know an extra added to ``pyproject.toml``
  since.  pip says ``does not provide the extra 'orb'``, installs
  nothing, and the feature goes on saying it is not installed -- which
  is how the ORB engine's own hint failed the first person who
  followed it.

So the command names this interpreter, and installs the checkout
itself, which rewrites the metadata on the way.  One function, here in
the headless core, because the hints are in both halves: the Force
Field panel's reason comes from :mod:`xtal.ff`, the Engines page from
:mod:`xtalapp.extras`, and a second spelling is how they drifted.
"""

from __future__ import annotations

import sys
from pathlib import Path


def checkout() -> Path | None:
    """The source tree this is running from, or ``None``."""
    root = Path(__file__).resolve().parent.parent
    return root if (root / "pyproject.toml").is_file() else None


def command(extra: str) -> str:
    """What to type to get the ``extra`` into this Python."""
    root = checkout()
    target = (f'-e "{root}[{extra}]"' if root is not None
              else f'"crystal-builder[{extra}]"')
    return f'"{sys.executable}" -m pip install {target}'


def packages(names, no_deps: bool = False) -> str:
    """What to type to get named packages into this Python, rather
    than an extra -- for the one case where the extra's own
    dependencies are what would break something already installed."""
    flags = " --no-deps" if no_deps else ""
    return (f'"{sys.executable}" -m pip install{flags} '
            + " ".join(f'"{name}"' for name in names))
