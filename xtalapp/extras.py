"""
xtalapp.extras
==============
What is optional, whether it is here, and how to get it.

Three features are gated on a package this application does not
install: the molecule builder needs RDKit, the sketcher needs
rdeditor, and the MOF builder needs PORMAKE.  Each greys its menu
entry out and names the extra to install -- ``pip install
'crystal-builder[mof]'`` -- which is exactly the right advice on a
source checkout.

**In a frozen build it is advice about nothing.**  There is no
environment to install into: the bundled interpreter is not on the
user's PATH and has no pip.  Repeating that sentence in a nicely laid
out dialog would be a polished way of saying something untrue, so this
module knows which build it is in and the page says different things.

The decision behind it (SHELL.md 3) is *bundle the small ones and be
honest about the big one*.  RDKit is about 107 MB and buys two whole
features; rdeditor is a megabyte on top of a PySide6 that is bundled
anyway.  PORMAKE is 44 packages and about 889 MB -- jax and pymatgen
for one dialog -- which is larger than the rest of the application put
together, so it is the one feature a packaged user cannot have, and
the page says so in those words rather than pretending.

**The folder on ``sys.path``** is the other half.  A user-writable
directory beside the log, prepended at start-up, so that ``pip install
--target`` from any Python can put a pure-Python package where a
frozen build will find it.  It is ten lines, it is the only answer a
bundle has to "install a plugin" at all -- see SHELL.md 2, where the
entry-point half has none -- and for PORMAKE specifically it is the
route that is *not* recommended: its dependencies are compiled and
have to match the bundled interpreter's exact version and ABI, and its
numpy would collide with the one already in the bundle.  The page says
that where somebody reading it will see it, rather than in a document
nobody opens.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from xtal import build as build_extra
from xtal.mof import catalog as mof_catalog
from xtalapp import applog
from xtalapp.dialogs import sketch

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
    #: Whether a packaged build includes it.  PORMAKE does not, and
    #: that is the product decision this table exists to record.
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
    "pormake": lambda: mof_catalog.installed(),
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
    Extra("MOF builder", "pormake", "mof",
          "Build a framework from a net, a metal node and a linker.  "
          "Net identification and the .cgd reader are this project's "
          "own and keep working without it.", False),
)

#: What to install to get the MOF builder the supported way: the
#: application itself, from Python, with the extra.
FULL_COMMAND = "pip install 'crystal-builder[gui,mof]'"

#: Why PORMAKE is not in a packaged build, in the words the page uses.
#: The honest reason and not a shorter one.
PORMAKE_REASON = (
    "PORMAKE is 44 packages and about 889 MB -- jax and pymatgen "
    "among them -- for one dialog.  That is larger than the rest of "
    "this application put together, so a build that included it would "
    "be a gigabyte download for everybody to give one feature to a "
    "few.")

#: The warning that belongs on the page rather than in a document.
TARGET_WARNING = (
    "This works for a package that is pure Python.  It is not "
    "reliable for PORMAKE: its dependencies are compiled, they have "
    "to match this build's exact Python version and ABI, and its "
    "numpy would collide with the one already here.  For PORMAKE, "
    "run Crystal Builder from Python instead.")


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


def target_command(package: str = "pormake") -> str:
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
