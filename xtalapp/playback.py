"""
xtalapp.playback
================
A trajectory, being scrubbed.

The optimiser produced a frame per step, the panel drew each one and
threw it away, and when the run ended the only thing left was the final
geometry.  Watching the relaxation again -- which is how anyone works
out *why* it went somewhere odd -- was impossible.  This is the state
that makes it possible: which trajectory, which frame, and where the
atoms were before it started.

**A frame is not an editable structure.**  Scrubbing while an edit is
half made would lose the edit at the next frame, so a document with a
playback open refuses edits and offers one way out that keeps a frame
-- "adopt this frame", which is the same command an optimisation
pushes -- and one that throws it away.  Everything shown in between is
a preview: no undo entry, no modified flag, nothing on disk.

The mapping from a frame to the document is the interesting part.  A
trajectory holds the **P1 cell**, because that is what OVITO, VMD and
ASE read; a document varies its **asymmetric unit**.  The reference
cell is expanded once when playback starts and every frame is carried
back through it (:func:`xtal.core.p1.parent_frac`), so a structure in
P4_2/mnm plays back in P4_2/mnm rather than being silently reduced to
P1 by being watched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from xtal.core import p1
from xtal.io.trajectory import Frame, Trajectory


class IncompatibleTrajectory(ValueError):
    """The trajectory is not of this structure."""


@dataclass
class Playback:
    """One trajectory open against one document."""

    trajectory: Trajectory
    before: np.ndarray                  # the asymmetric unit at start
    reference: object                   # the P1Cell frames map through
    # The structure the reference cell came from.  Held privately
    # because a playback is state *about* a document and never a
    # second owner of its crystal: it reads the symmetry and writes
    # nothing.
    structure: object = None
    path: Path | None = None
    index: int = 0
    playing: bool = False
    interval_ms: int = 80
    _cache: dict = field(default_factory=dict, repr=False)

    @property
    def n_frames(self) -> int:
        return self.trajectory.n_frames

    @property
    def frame(self) -> Frame:
        return self.trajectory[self.clamp(self.index)]

    @property
    def name(self) -> str:
        return self.path.name if self.path else "trajectory"

    def clamp(self, index: int) -> int:
        if not self.n_frames:
            return 0
        return max(0, min(int(index), self.n_frames - 1))

    def frac_at(self, index: int, lattice=None) -> np.ndarray:
        """The asymmetric unit that shows frame ``index``.

        Memoised, because scrubbing goes backwards as often as
        forwards and the mapping is a small matrix solve per site.
        """
        index = self.clamp(index)
        cached = self._cache.get(index)
        if cached is not None:
            return cached
        frame = self.trajectory[index]
        cell = self.reference
        frac = frame.frac(lattice or cell.lattice)
        parent = p1.parent_frac(self.structure, cell, frac)
        self._cache[index] = parent
        return parent

    def label(self, index: int | None = None) -> str:
        """"frame 12 of 201   E = -1234.5678", for the transport bar."""
        index = self.clamp(self.index if index is None else index)
        text = f"frame {index + 1} of {self.n_frames}"
        if not self.n_frames:
            return "no frames"
        frame = self.trajectory[index]
        if frame.step is not None:
            text += f"   step {frame.step}"
        if frame.energy is not None:
            text += f"   E = {frame.energy:.4f}"
        return text


def open_playback(structure, trajectory: Trajectory,
                  path=None) -> Playback:
    """Prepare a trajectory to be played against ``structure``.

    Refuses a trajectory of a different crystal.  Atom counts alone
    would let one structure's run drive another with the same number of
    atoms, which would be nonsense drawn convincingly -- so the test is
    the elements of the cell, in order.
    """
    if not trajectory.n_frames:
        raise IncompatibleTrajectory("the trajectory has no frames")
    cell = p1.expand(structure)
    if tuple(cell.elements) != trajectory.elements:
        raise IncompatibleTrajectory(
            f"the trajectory has {trajectory.n_atoms} atoms "
            f"({_formula(trajectory.elements)}) and this structure's "
            f"cell has {cell.n_atoms} ({_formula(cell.elements)})")
    return Playback(
        trajectory=trajectory,
        before=structure.frac.copy(),
        reference=cell,
        structure=structure,
        path=Path(path) if path else trajectory.path)


def _formula(elements) -> str:
    counts: dict[str, int] = {}
    for symbol in elements:
        counts[symbol] = counts.get(symbol, 0) + 1
    return "".join(f"{k}{v}" if v > 1 else k
                   for k, v in sorted(counts.items()))
