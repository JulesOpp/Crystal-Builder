"""
xtal.powder
===========
Refinement against a measured powder pattern: peak fitting, indexing,
Pawley, Rietveld, and Rietveld with an energy beside it.

**The physics is rietx's, not ours.**  rietx (MIT, ``pip install
rietx``) fits the profiles, searches for the cell and refines; this
package is what a structure of this application, a ``.xy`` file and a
radiation look like to it, and what comes back.  It is the ``refine``
extra, pinned below the next minor release because its API is young,
and :mod:`xtal.powder.bridge` is the only module that imports it --
so a rename upstream breaks one file and the test that holds it.

**Nothing here imports rietx to ask whether it is there.**
:func:`available` is ``find_spec``, the same rule the MOF builder
keeps: loading numba and rietx's kernels to grey out a menu entry
would put two seconds on every window that never refines anything.
"""

from __future__ import annotations

import importlib.util

from xtal.params import Availability

__all__ = ["EXTRA", "availability", "available", "missing"]

#: The ``pip install crystal-builder[...]`` name that brings rietx in.
EXTRA = "refine"


def available() -> bool:
    """Whether rietx is installed -- without importing it."""
    try:
        return importlib.util.find_spec("rietx") is not None
    except (ImportError, ValueError):
        return False


def availability() -> Availability:
    """Whether a refinement can run here, and how to make it when not."""
    if available():
        return Availability(True)
    from xtal import install

    return Availability(False, "Refinement needs rietx",
                        install.command(EXTRA))


def missing() -> str:
    """Why a refinement cannot run here, or ``""`` when it can."""
    return availability().reason
