"""
xtalapp.extras
==============
What is optional, whether it is here, and how to get it.

Three features are gated on a package this application does not
install: the molecule builder needs RDKit, the sketcher needs
rdeditor, and the PXRD overlay window needs matplotlib.  Each greys
its entry out and names the extra to install -- ``pip install
'crystal-builder[build]'`` -- which is exactly the right advice on a
source checkout.

The third is the narrowest of the three and is worth the distinction:
what is missing without matplotlib is a *window*, not a feature.  The
pattern is still calculated, still drawn in the Results panel by
:mod:`xtalapp.curve`, and still written as ``.xy``; the button that
zooms into it and lays a measured file over it is what greys out.

**In a frozen build it is advice about nothing.**  There is no
environment to install into: the bundled interpreter is not on the
user's PATH and has no pip.  Repeating that sentence in a nicely laid
out dialog would be a polished way of saying something untrue, so this
module knows which build it is in and the page says different things.

The decision behind it (SHELL.md 3) is *bundle the small ones and be
honest about the big one*.  RDKit is about 107 MB and buys two whole
features; rdeditor is a megabyte on top of a PySide6 that is bundled
anyway.

**The MOF builder was the big one, and it is not on this page any
more.**  It needed PORMAKE: 44 packages and about 889 MB, jax and
pymatgen for one dialog, larger than the rest of the application put
together.  So it was excluded, and it was the single feature a
packaged user could not have.  PORMAKE is now vendored and trimmed of
all three -- :mod:`xtal.mof.pormake`, about 23 MB with the ``ase``
it is written over, see ``xtal/mof/pormake/PROVENANCE.md`` -- so the
builder ships, there is
nothing to install, and a page listing it as optional would be the
untrue thing this module exists to avoid.

**The folder on ``sys.path`` outlives that.**  A user-writable
directory beside the log, prepended at start-up, so that ``pip install
--target`` from any Python can put a pure-Python package where a
frozen build will find it.  It is ten lines and it is the only answer
a bundle has to "install a plugin" at all -- see SHELL.md 2, where the
entry-point half has none.  It kept the warning that used to be about
PORMAKE in particular, because that warning was never really about
PORMAKE: a package with compiled dependencies has to match the bundled
interpreter's exact version and ABI, and its numpy will collide with
the one already here.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from xtal import build as build_extra
from xtalapp import applog
from xtalapp.dialogs import pattern, sketch

#: The folder under the application's data directory, and the variable
#: that moves it.  The suite points this at a scratch directory the way
#: it does the log's, so that no test writes into somebody's real
#: Application Support.
NAME = "packages"
DIR_VAR = "XTAL_PACKAGES_DIR"


def frozen() -> bool:
    """Whether this is a packaged build rather than a checkout.

    PyInstaller sets both; ``sys.frozen`` alone is what every other
    freezer sets too, which is the point of checking it rather than
    ``_MEIPASS``.
    """
    return bool(getattr(sys, "frozen", False))


@dataclass(frozen=True)
class Extra:
    """One optional feature, and what it costs to have."""

    label: str
    package: str                # what is imported
    extra: str                  # the pip extra that installs it
    powers: str
    #: Whether a packaged build includes it.  Both rows say ``True``
    #: now that the MOF builder is vendored, and the field stays: it
    #: is the product decision this table exists to record, and
    #: :func:`status` tells "missing from a build meant to carry it"
    #: -- a fault -- apart from "deliberately left out".
    bundled: bool

    def installed(self) -> bool:
        """``find_spec``, never an import -- see the modules this
        delegates to."""
        return installed(self.package)

    def command(self) -> str:
        """What to type on a source checkout to get it."""
        return f"pip install 'crystal-builder[{self.extra}]'"


#: Asked through each feature's own check, so there is one answer to
#: "is RDKit there" in the application and this is not a second one.
#: Called through the module rather than bound here, so that patching
#: a feature's own check -- which is what a test has to do, since no
#: machine has all three states at once -- is felt through this table
#: as well.
_CHECKS = {
    "rdkit": lambda: build_extra.installed(),
    "rdeditor": lambda: sketch.installed(),
    "matplotlib": lambda: pattern.installed(),
}


def installed(package: str) -> bool:
    """Whether that optional package is importable."""
    check = _CHECKS.get(package)
    return bool(check()) if check is not None else False


EXTRAS = (
    Extra("Molecule builder", "rdkit", "build",
          "Insert molecule builds a molecule from a SMILES string and "
          "pastes it into the structure.  It also reads the fragment "
          "library.", True),
    Extra("Molecule sketcher", "rdeditor", "sketch",
          "Draw a molecule instead of typing a SMILES string.  Needs "
          "the molecule builder as well.", True),
    Extra("Pattern plot window", "matplotlib", "pxrd",
          "Zoom into a calculated PXRD pattern, overlay a measured "
          ".xy file on it, and export the figure as a vector with "
          "the text still editable.  The pattern itself is "
          "calculated, drawn in the Results panel and written as .xy "
          "without it.", True),
)

#: What the folder below is for, in the words the page uses.
PACKAGES_REASON = (
    "A packaged build has no pip and nothing to install into, so this "
    "folder is the only way to add a Python package to it.  It is put "
    "first on the import path when the application starts, which is "
    "also how a package here can replace one that shipped.")

#: The warning that belongs on the page rather than in a document.
#: It used to be about PORMAKE, which is now vendored; it was never
#: really about PORMAKE.
TARGET_WARNING = (
    "This works for a package that is pure Python.  It is not "
    "reliable for one with compiled dependencies: they have to match "
    "this build's exact Python version and ABI, and a second numpy "
    "would collide with the one already here.  For those, run "
    "Crystal Builder from Python instead.")


# ======================================================================
#  THE FOLDER ON sys.path
# ======================================================================

def folder(create: bool = False) -> Path:
    """The directory added to ``sys.path`` at start-up.

    Not created unless asked for: an empty folder that appears in
    somebody's Application Support without them doing anything is the
    same discourtesy as a workspace made behind their back.  Revealing
    it is what creates it, because that is somebody asking for it.
    """
    given = os.environ.get(DIR_VAR, "").strip()
    path = (Path(given).expanduser() if given
            else applog.app_data() / NAME)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def add_to_path() -> Path | None:
    """Put that folder first on ``sys.path``, if it is there.

    Called by :func:`xtalapp.main.main` and by nothing else -- a
    window built by a test must not change the interpreter's import
    path.  Prepended, so a package a user installed there wins over
    one of the same name inside the bundle, which is the only way
    "add it to this copy" can mean anything.  Idempotent, because a
    second call must not shadow the first entry with a duplicate.
    """
    path = folder()
    if not path.is_dir():
        return None
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)
    return path


def target_command(package: str = "<package>") -> str:
    """``pip install --target`` into that folder, ready to paste."""
    return f'pip install --target "{folder()}" {package}'


def reveal() -> bool:
    """Show the folder in Finder or Explorer, making it first."""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    return bool(QDesktopServices.openUrl(
        QUrl.fromLocalFile(str(folder(create=True)))))


# ======================================================================
#  WHAT THE PAGE SAYS
# ======================================================================

def status(extra: Extra) -> tuple[bool, str]:
    """Whether the feature works, and the sentence saying why.

    The four answers are different states and not one wording with a
    hole in it: it works; it is missing and there is a command; it is
    missing from a build that was supposed to carry it, which is a
    fault rather than a choice; and it is missing because this build
    deliberately left it out.
    """
    if extra.installed():
        return True, ("Working, and included in this build."
                      if frozen() and extra.bundled else "Working.")
    if not frozen():
        return False, f"Not installed.  {extra.command()}"
    if extra.bundled:
        # Not a thing the user can act on: this build was supposed to
        # carry it.  Saying "pip install" here would be advice about
        # an interpreter they cannot reach.
        return False, ("Not working, and this build was built to "
                       "include it.  That is a fault in the build "
                       "rather than something to install -- please "
                       "report it.")
    return False, "Not included in this build."
