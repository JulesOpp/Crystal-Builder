"""
xtal.core.limits
================
How big a thing may get before it is asked about or refused.

One module, so that the window, the CLI and an agent's Session read
the same numbers.  Today it holds the undo history's budget; the
estimates for drawing, supercells, porosity grids and carbon builds
join it next.
"""

from __future__ import annotations

#: Sites the undo history may hold in whole-structure steps (a
#: supercell, Reduce to P1, a change of group) before its oldest such
#: steps are let go.  Steps were capped only by count, two hundred of
#: them, and an MFU-4l 3x3x3 held 43 MB a step: a long session on a
#: big cell kept gigabytes of crystals nobody would undo back to.
UNDO_ATOMS = 2_000_000

#: The most recent steps, which are never let go whatever they hold.
UNDO_KEEP = 5
