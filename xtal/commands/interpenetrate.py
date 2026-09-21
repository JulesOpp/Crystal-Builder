"""
xtal.commands.interpenetrate
============================
Interpenetrating a framework, as one undoable step.

The work is :mod:`xtal.analysis.interpenetrate`; this is the wrapper
that makes it a :class:`~xtal.commands.base.StructureOperation`, so the
dialog can preview a placement and the undo stack keeps the structure
as it was.  A whole-structure rebuild, for the reason every symmetry
operation is one: the array is in P1 and has twice the atoms, and
there is no smaller honest description of that than the structure
before it.
"""

from __future__ import annotations

from xtal.analysis import interpenetrate
from xtal.commands.base import StructureOperation
from xtal.core.structure import Change
from xtal.core.symmetry import SymmetryReport


class Interpenetrate(StructureOperation):
    """Add copies of the framework where a placement says.

    ``TOPOLOGY`` because atoms and bonds arrive -- which is also what
    drops a pore network measured on the single framework -- and
    ``SYMMETRY`` because the array is in P1 whatever the copy was.
    Not ``CELL``: every copy fits the cell it was given (see
    :mod:`xtal.analysis.interpenetrate`).

    A refused placement comes back as ``ok=False`` with the sentence,
    so :meth:`xtalapp.document.Document.operate` pushes nothing.
    """

    change = Change.TOPOLOGY | Change.SYMMETRY
    label = "Interpenetrate"

    def __init__(self, placement: interpenetrate.Placement):
        super().__init__()
        self.placement = placement
        self.label = f"Interpenetrate {placement.fold}-fold"

    def apply_to(self, structure):
        before = len(_atoms(structure))
        try:
            out, placed = interpenetrate.build(structure, self.placement)
        except interpenetrate.InterpenetrationError as exc:
            return structure, SymmetryReport(
                ok=False, message=str(exc), n_before=before,
                n_after=before)
        n = placed.fold
        return out, SymmetryReport(
            n_before=before, n_after=out.n_sites,
            message=(f"{n}-fold interpenetrated by {placed.name} "
                     f"({placed.relation}): {out.n_sites} atoms in P1, "
                     f"closest contact between copies "
                     f"{placed.contact_text()}"))


def _atoms(structure):
    from xtal.core import p1

    return p1.expand(structure).frac
