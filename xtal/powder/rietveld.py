"""
xtal.powder.rietveld
====================
Rietveld: a structure's own atoms fitted to the whole pattern --
TOPAS's ``d_riet`` step, and the one a person watches.

RietX fits (``mode="rietveld"``); what is decided here is what a
person sets and what comes back.  The boxes free, in McCusker's
order, the background, the line positions, the cell number by number,
the widths, and then the structure -- coordinates along each site's
allowed directions, displacements, occupancies, and March-Dollase
texture about an axis.  Or one of RietX's own plans instead of the
boxes.

**A refinement moves atoms; it never adds, removes or bonds them.**
The refined structure is the one given with new numbers on the same
sites -- :func:`~xtal.powder.bridge.apply_phase` writes back by index
and refuses a phase of another length -- and :func:`rietveld` checks
the count and the bonds before it hands anything back.  Dummy atoms
are markers, never scatterers: they do not go to RietX and come back
where they were, at the same fractional coordinates.

**Nothing here touches a document.**  Frames go out through
``on_frame`` for the window to preview, and the result is a structure
the window commits as one undo step.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from xtal.powder.data import PowderData, PowderError, Radiation

__all__ = ["RietveldFit", "RietveldFrame", "RietveldOptions",
           "parse_axis", "rietveld"]


@dataclass(frozen=True)
class RietveldOptions:
    """What the Rietveld step asks (TOPAS ``d_riet.inp``).

    The booleans are the free boxes; ``hold_cell`` names cell numbers
    held while the others refine.  ``plan`` is one of RietX's presets
    (:data:`~xtal.powder.bridge.RIETVELD_PRESETS`), or empty for the
    plan the boxes make.  ``preferred_axis`` is the March-Dollase
    direction as three integers, ``None`` for no texture.
    """

    start: float | None = None
    finish: float | None = None
    background_terms: int = 8
    plan: str = ""
    background: bool = True
    zero: bool = False
    displacement: bool = True
    cell: bool = True
    hold_cell: tuple[str, ...] = ()
    profile: bool = True
    size: bool = False
    strain: bool = False
    positions: bool = True
    biso: bool = True
    occupancy: bool = False
    preferred_axis: tuple[int, int, int] | None = None

    def free(self, radiation: Radiation) -> tuple[str, ...]:
        """The bridge's words for what is freed.  A capillary has no
        specimen displacement, so it is never freed for one."""
        out = [key for key in ("background", "zero", "cell", "profile",
                               "size", "strain", "positions", "biso",
                               "occupancy") if getattr(self, key)]
        if self.displacement and not radiation.is_synchrotron:
            out.append("displacement")
        if self.preferred_axis is not None:
            out.append("preferred_orientation")
        return tuple(out)


@dataclass(frozen=True)
class RietveldFrame:
    """One moment of a run: the pattern and the atoms as they stand.

    ``frac`` has a row for every site of the structure, dummies at
    their own coordinates, so it goes straight to
    ``Document.preview_positions`` with ``matrix``.
    """

    stage: str
    two_theta: np.ndarray
    y_obs: np.ndarray
    y_calc: np.ndarray
    frac: np.ndarray
    matrix: np.ndarray


@dataclass
class RietveldFit:
    """A Rietveld fit, the structure it refined, and its curves."""

    structure: object
    cell: tuple[float, ...]
    cell_esd: tuple[float, ...]
    rwp: float
    rp: float
    rexp: float
    gof: float
    status: str
    two_theta: np.ndarray
    y_obs: np.ndarray
    y_calc: np.ndarray
    y_background: np.ndarray
    ticks: np.ndarray
    radiation: Radiation
    #: ``{path: (value, esd)}`` of every number refined, RietX's paths
    refined: dict = field(default_factory=dict)
    #: the furthest any atom moved within the cell, in Å
    moved: float = 0.0
    #: RietX's label of each atom of the phase, in its order
    atom_labels: tuple[str, ...] = ()
    notes: list[str] = field(default_factory=list)

    @property
    def converged(self) -> bool:
        return self.status == "converged"


def parse_axis(text) -> tuple[int, int, int] | None:
    """``"0 0 1"`` or ``"001"`` as three integers; empty is none."""
    text = str(text or "").strip()
    if not text:
        return None
    words = text.replace(",", " ").split()
    if len(words) == 1 and len(words[0]) == 3 and words[0].isdigit():
        words = list(words[0])
    try:
        axis = tuple(int(w) for w in words)
    except ValueError:
        raise PowderError(f"{text!r} is not an axis -- three integers, "
                          f"h k l") from None
    if len(axis) != 3 or not any(axis):
        raise PowderError(f"{text!r} is not an axis -- three integers, "
                          f"h k l, not all zero")
    return axis


def rietveld(structure, data: PowderData, radiation: Radiation,
             options: RietveldOptions | None = None, *, on_frame=None,
             frame_interval: float = 0.2, cancel=None,
             folder=None) -> RietveldFit:
    """Refine ``structure`` against ``data``.

    ``on_frame(RietveldFrame)`` is called from the fitting thread as
    the fit goes; ``cancel`` is a job's
    :class:`~xtal.modules.job.Cancellation`, and Stop raises
    :class:`~xtal.powder.data.PowderStopped` -- the atoms go back to
    where they started, which is the caller's to do.
    """
    from xtal.core.lattice import Lattice
    from xtal.powder import bridge

    options = options or RietveldOptions()
    window = data.window(options.start or None, options.finish or None)
    start_frac = structure.frac.copy()

    frame_out = None
    if on_frame is not None:
        def frame_out(stage, y_calc, fractions, cell):
            frac = start_frac.copy()
            frac[indices] = fractions
            on_frame(RietveldFrame(
                stage=stage, two_theta=window.two_theta,
                y_obs=window.intensity, y_calc=y_calc, frac=frac,
                matrix=Lattice.from_parameters(*cell).matrix))

    # the map is needed by the frames before the fit returns it
    _phase, indices = bridge.phase_of(structure)
    refinement, result, indices = bridge.rietveld(
        structure, window, radiation, free=options.free(radiation),
        hold_cell=options.hold_cell, plan=options.plan,
        background_terms=options.background_terms,
        preferred_axis=options.preferred_axis, on_frame=frame_out,
        frame_interval=frame_interval, folder=folder,
        cancel=bridge.cancel_token(cancel))
    phase = refinement.structure.phases[0]
    refined = bridge.apply_phase(structure, phase, indices)
    if len(refined.sites) != len(structure.sites) \
            or refined.bonds != structure.bonds:
        raise PowderError("the refinement changed the atoms or the "
                          "bonds, and was not kept")
    names = ("a", "b", "c", "alpha", "beta", "gamma")
    # how far the atoms moved within the cell, a strain of the cell
    # left out: that is the cell's own row in the result
    moved = np.linalg.norm(refined.lattice.to_cart(
        refined.frac - structure.frac), axis=1)
    stats = result.statistics
    return RietveldFit(
        structure=refined,
        cell=tuple(float(getattr(phase.cell, n).value) for n in names),
        cell_esd=tuple(float(getattr(phase.cell, n).stderr or 0.0)
                       for n in names),
        rwp=float(stats.rwp), rp=float(stats.rp), rexp=float(stats.rexp),
        gof=float(stats.gof), status=str(result.status),
        two_theta=np.asarray(result.two_theta),
        y_obs=np.asarray(result.y_obs), y_calc=np.asarray(result.y_calc),
        y_background=np.asarray(result.y_background),
        ticks=np.array([row[2] for row in bridge.reflections(refinement)]),
        radiation=radiation, refined=bridge.refined_values(result),
        moved=float(moved.max()) if moved.size else 0.0,
        atom_labels=tuple(atom.label for atom in phase.atoms),
        notes=[d.message for d in result.diagnostics])
