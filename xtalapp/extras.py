"""
xtalapp.extras
==============
What is optional, whether it is here, and how to get it.

Five features are gated on a package this application does not
install: the molecule builder needs RDKit, the sketcher rdeditor, the
PXRD overlay window matplotlib, the MOF builder ASE, and the MACE
engine mace-torch.  Each greys its entry out and names the extra to
install, spelled by :func:`xtal.install.command` for *this*
interpreter and *this* checkout -- see that module for why the
shorthand ``pip install 'crystal-builder[build]'`` is not good enough.

The PXRD one is the narrowest and is worth the distinction:
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

**The MOF builder was the big one.**  It needed PORMAKE: 44 packages
and about 889 MB, jax and pymatgen for one dialog.  PORMAKE is now
vendored and trimmed of all three -- :mod:`xtal.mof.pormake`, about
23 MB with the ``ase`` it is written over, see
``xtal/mof/pormake/PROVENANCE.md`` -- so the builder ships.  It is
back on this page for a source checkout, where ``ase`` is still an
extra and the builder greys out without it; a build says it came
with it.

**The big one now is PyTorch**, which every ML engine brings and no
build carries.  Those rows say "not included in this build" rather
than offering an install nobody can do.

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
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from xtal import build as build_extra
from xtal import install
from xtal import mof as mof_extra
from xtal.ff import mace as mace_extra
from xtal.ff import mattersim as mattersim_extra
from xtal.ff import orb as orb_extra
from xtal.ff.registry import ENGINES
from xtal.references import PORMAKE, Reference, doi, github
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
    #: Whether a packaged build includes it.  The ML engines say
    #: ``False``: PyTorch is larger than the rest of the application
    #: put together and is not bundled.  :func:`status` tells "missing
    #: from a build meant to carry it" -- a fault -- apart from
    #: "deliberately left out", and this field is that decision.
    bundled: bool
    #: What Test imports, where importing the package alone proves
    #: nothing: ``import mace`` is 0.05 s and never touches torch,
    #: ``import mace.calculators`` is 4.6 s and does.
    module: str = ""
    #: Seconds Test waits, where the default five would stop a torch
    #: import that was going to succeed.
    timeout: float = 0.0
    #: What else it takes, where the command alone is known to fail.
    note: str = ""
    #: The command, where it depends on what else is installed.  The
    #: feature's own function, so the Force Field panel's note and this
    #: page cannot give two different answers.
    command_for: Callable[[], str] | None = None
    #: Where it comes from, linked on the page.
    references: tuple = ()

    def installed(self) -> bool:
        """``find_spec``, never an import -- see the modules this
        delegates to."""
        return installed(self.package)

    def command(self) -> str:
        """What to type on a source checkout to get it -- see
        :mod:`xtal.install` for why it is not the shorthand."""
        if self.command_for is not None:
            return self.command_for()
        return install.command(self.extra)


#: Asked through each feature's own check, so there is one answer to
#: "is RDKit there" in the application and this is not a second one.
#: Called through the module rather than bound here, so that patching
#: a feature's own check -- which is what a test has to do, since no
#: machine has all three states at once -- is felt through this table
#: as well.
_CHECKS = {
    "ase": lambda: mof_extra.has_ase(),
    "rdkit": lambda: build_extra.installed(),
    "rdeditor": lambda: sketch.installed(),
    "matplotlib": lambda: pattern.installed(),
    "mace": lambda: mace_extra.installed(),
    "orb_models": lambda: orb_extra.installed(),
    "mattersim": lambda: mattersim_extra.installed(),
}


def installed(package: str) -> bool:
    """Whether that optional package is importable."""
    check = _CHECKS.get(package)
    return bool(check()) if check is not None else False


def _engine(name: str) -> tuple:
    """An ML engine's own references, as the Force Field panel shows
    them, so the two cannot disagree."""
    engine = ENGINES.get(name)
    return engine.sources(**engine.defaults())


EXTRAS = (
    Extra("Molecule builder", "rdkit", "build",
          "Insert molecule builds a molecule from a SMILES string and "
          "pastes it into the structure.  It also reads the fragment "
          "library.", True,
          references=(Reference("rdkit.org", "https://www.rdkit.org"),
                      github("rdkit/rdkit"))),
    Extra("Molecule sketcher", "rdeditor", "sketch",
          "Draw a molecule instead of typing a SMILES string.  Needs "
          "the molecule builder as well.", True,
          references=(github("EBjerrum/rdeditor"),)),
    Extra("Pattern plot window", "matplotlib", "pxrd",
          "Zoom into a calculated PXRD pattern, overlay a measured "
          ".xy file on it, and export the figure as a vector with "
          "the text still editable.  The pattern itself is "
          "calculated, drawn in the Results panel and written as .xy "
          "without it.", True,
          references=(Reference("matplotlib.org",
                                "https://matplotlib.org"),)),
    Extra("MOF builder", "ase", "ase",
          "Build a framework from a net, a node and a linker.  PORMAKE "
          "is part of this application; ASE is what it is written "
          "over.", True,
          references=(doi("ASE: Hjorth Larsen et al., J. Phys.: "
                          "Condens. Matter 2017",
                          "10.1088/1361-648X/aa680e"),
                      Reference("gitlab.com/ase/ase",
                                "https://gitlab.com/ase/ase"))
          + PORMAKE),
    Extra("MACE engine", "mace", "mace",
          "The MACE machine-learned potentials in the Force Field "
          "panel.  Brings PyTorch, which is gigabytes.", False,
          module="mace.calculators", timeout=60.0,
          references=_engine("mace")),
    Extra("ORB engine", "orb_models", "orb",
          "The ORB-v3 machine-learned potentials in the Force Field "
          "panel.  Brings PyTorch, which is gigabytes.", False,
          module="orb_models.forcefield.pretrained", timeout=60.0,
          references=_engine("orb"),
          note="orb-models pins dm-tree 0.1.8, which has no ready-made "
               "wheel for Python 3.13 and does not build with CMake 4. "
               " If the install stops while building dm-tree, run it "
               "again with CMAKE_POLICY_VERSION_MINIMUM=3.5 set in the "
               "environment."),
    Extra("MatterSim engine", "mattersim", "mattersim",
          "The MatterSim machine-learned potentials in the Force "
          "Field panel.  Brings PyTorch, which is gigabytes.", False,
          module="mattersim.forcefield", timeout=60.0,
          command_for=lambda: mattersim_extra.install_command(),
          references=_engine("mattersim"),
          note="mattersim asks for e3nn 0.5 or newer and MACE needs "
               "exactly 0.4.4, and MatterSim runs on 0.4.4.  With MACE "
               "installed, the command above leaves mattersim's own "
               "dependencies out and installs the three it needs, so "
               "that MACE keeps working."),
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
        # The command is the page's box below, ready to copy.  It was
        # repeated here while it was short; spelled out for this
        # interpreter and checkout it is a wrapped path twice over.
        return False, "Not installed."
    if extra.bundled:
        # Not a thing the user can act on: this build was supposed to
        # carry it.  Saying "pip install" here would be advice about
        # an interpreter they cannot reach.
        return False, ("Not working, and this build was built to "
                       "include it.  That is a fault in the build "
                       "rather than something to install -- please "
                       "report it.")
    return False, "Not included in this build."
