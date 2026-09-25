"""
xtal.commands.prepare
=====================
Preparing a deposited structure for simulation, as one undoable step.

The work is :mod:`xtal.core.prepare`; this makes it a
:class:`~xtal.commands.base.StructureOperation`, so the dialog can show
what every step would do while the user is still choosing steps, and
Ctrl+Z gives back the structure as deposited.  One step for the lot:
the steps are one thing the user asked for, and undoing half of them
leaves a cell nobody chose -- ordered but in the centred cell, or
capped but with the solvent put back.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from xtal.commands.base import StructureOperation
from xtal.core import p1
from xtal.core import prepare as core
from xtal.core.structure import Change
from xtal.core.symmetry import SymmetryReport


@dataclass
class PrepareReport(SymmetryReport):
    """A report with the cautions of :func:`xtal.core.prepare.run`:
    kept apart from ``warnings``, which are each step's sentence, so
    the dialog can show them as warnings and not as one more line."""

    cautions: list[str] = field(default_factory=list)


class Prepare(StructureOperation):
    """The chosen steps of :func:`xtal.core.prepare.prepare`.

    ``ALL``, because a step can change the cell (the primitive cell),
    the group (ordering is in P1 unless whole orbits went) and the
    atoms.  The bonds of the result are perceived afresh when they are
    next asked for -- as after any change of group -- and that is the
    exception Add hydrogens already is: bonding what was added, and
    forgetting what was taken away, is the operation.  What cannot be
    carried through an ordering is a bond the user drew, so a structure
    with any is refused rather than quietly losing them.

    A report with ``ok=False`` -- nothing to do, or bonds drawn by hand
    -- pushes nothing (:meth:`xtalapp.document.Document.operate`).
    """

    change = Change.ALL
    label = "Prepare for simulation"

    def __init__(self, steps=core.DEFAULT_STEPS):
        super().__init__()
        self.steps = tuple(s for s in core.STEPS if s in set(steps))
        self.messages: list[str] = []

    def apply_to(self, structure):
        before = p1.expand(structure).n_atoms
        if not self.steps:
            return structure, PrepareReport(
                ok=False, message="no step chosen", n_before=before,
                n_after=before)
        refused = _held(structure)
        if refused:
            return structure, PrepareReport(
                ok=False, n_before=before, n_after=before,
                message=refused)
        outcome = core.run(structure, self.steps)
        out, self.messages = outcome.structure, outcome.said
        if out is structure:
            return structure, PrepareReport(
                ok=False, n_before=before, n_after=before,
                message="nothing to prepare",
                warnings=list(self.messages),
                cautions=list(outcome.cautions))
        after = p1.expand(out).n_atoms
        return out, PrepareReport(
            n_before=before, n_after=after,
            message=(f"prepared for simulation: {before} -> {after} "
                     f"atoms, {out.space_group.short_name}"),
            warnings=list(self.messages),
            cautions=list(outcome.cautions))


def _held(structure) -> str:
    """Why the stored bonds cannot be carried through, or ``""``."""
    edits = sum(1 for b in structure.bonds
                if b.kind in ("explicit", "suppressed"))
    if edits:
        return (f"this structure has {edits} bond(s) stated in its "
                f"file or drawn or removed by hand, which ordering the "
                f"disorder cannot carry through; prepare the file as "
                f"deposited, or Reset bonds to automatic first")
    if structure.bonds:
        return (f"this structure has a net drawn over it "
                f"({len(structure.bonds)} edge(s)), which ordering the "
                f"disorder cannot carry through; prepare the file as "
                f"deposited and draw the net on the result")
    return ""
