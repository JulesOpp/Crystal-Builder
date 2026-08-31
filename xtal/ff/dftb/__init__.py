"""
xtal.ff.dftb
============
DFTB+ behind :class:`xtal.ff.api.Calculator`.

Importing this registers the engine, which is all it takes for DFTB+
to appear in the Force Field panel's chooser beside UFF -- and, with
it, everything the panel already does: a single point, a geometry
optimisation under the space group, the live plot, the trajectory, the
frozen selection, the cell as a variable, Pause and Stop, and one
undoable command at the end.  That is the whole argument for reaching
DFTB+ this way rather than as a module of its own.
"""

from xtal.ff.dftb.calculator import (
    DFTBCalculator,
    DFTBOptions,
    available,
)
from xtal.ff.dftb.hsd import hsd_string, missing_parameters
from xtal.ff.dftb.params import ANGULAR_MOMENTUM, PARAMETER_SETS

__all__ = ["DFTBCalculator", "DFTBOptions", "available", "hsd_string",
           "missing_parameters", "ANGULAR_MOMENTUM", "PARAMETER_SETS"]
