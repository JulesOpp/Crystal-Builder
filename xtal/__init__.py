"""
xtal -- build, manipulate, analyse and export crystal structures.

The core (this package) is a headless library: no Qt, no VTK, no
display required.  The desktop application lives in ``xtalapp``.
"""

from importlib.metadata import PackageNotFoundError, version

from xtal.core.lattice import Lattice
from xtal.core.site import Site
from xtal.core.spacegroup import SpaceGroup, SymOp
from xtal.core.structure import Bond, Change, Structure

try:
    __version__ = version("crystal-builder")
except PackageNotFoundError:            # running from a source tree
    __version__ = "0.0.dev0"

__all__ = ["__version__", "Lattice", "Site", "SpaceGroup", "SymOp",
           "Bond", "Change", "Structure"]
