"""
xtal.powder.peaks
=================
Peak fitting: every resolvable line in a pattern, with a fitted
position, an area and an esd -- TOPAS's ``xo_Is`` step, and what
indexing reads.

RietX does the work (``rietx.indexing.pick_peaks_with_state``, or
``fit_peaks`` at positions the user names).  What is decided here is
what the answer looks like to this application: a table a person can
read, untick a line in, and hand to indexing -- and the curve to draw
over the data, which RietX does not return as one array but as a
background envelope plus one fitted profile per window.

**TOPAS's background order and size/strain terms are not options
here, and that is not an omission.**  RietX's peak fit holds the
background as the envelope its detector draws and fits each window's
widths directly; there is no Chebyshev order or crystallite size to
set, because nothing in this step refines them.  They are Pawley's
options, where they are refined.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from xtal.powder.data import PowderData, PowderError, Radiation

__all__ = ["Peak", "PeakFit", "PeakOptions", "fit_peaks"]


@dataclass(frozen=True)
class PeakOptions:
    """What the peak step asks.

    ``positions`` empty is *find the peaks*; a list is *fit exactly
    these*, which is TOPAS's hand-written ``xo_Is`` list.  A named
    position with nothing at it comes back flagged ``no_intensity``
    and out of use, never silently dropped.
    """

    start: float | None = None
    finish: float | None = None
    shoulders: bool = True
    flag_ghosts: bool = True
    positions: tuple[float, ...] = ()


@dataclass
class Peak:
    """One fitted line, as the table shows it.

    ``use`` is whether indexing reads it.  It starts as RietX's own
    verdict (a Kβ ghost, a failed fit or a line it could not separate
    is out) and is the user's to change after that, which is TOPAS's
    "comment out a peak".
    """

    two_theta: float
    two_theta_esd: float
    d: float
    area: float
    area_esd: float
    fwhm: float
    flags: tuple[str, ...] = ()
    use: bool = True


@dataclass
class PeakFit:
    """The peaks, and the curves to draw them against.

    ``two_theta`` / ``y_obs`` / ``y_calc`` / ``y_background`` are on
    the grid the fit ran on, which is the pattern cropped to the range
    asked for.  ``native`` is RietX's own peak list, kept so indexing
    reads exactly what was fitted rather than a copy of it rebuilt
    from the table.
    """

    peaks: list[Peak]
    two_theta: np.ndarray
    y_obs: np.ndarray
    y_calc: np.ndarray
    y_background: np.ndarray
    radiation: Radiation
    wavelength: float
    notes: list[str] = field(default_factory=list)
    native: Any = None

    @property
    def n_used(self) -> int:
        return sum(1 for peak in self.peaks if peak.use)

    def for_indexing(self):
        """RietX's list with the unticked lines flagged ``excluded``.

        ``excluded`` is RietX's own word for a line its caller took
        out, so ``PeakList.usable()`` -- which every indexing engine
        reads -- leaves it out without anything here re-implementing
        what "usable" means.
        """
        if self.native is None:
            raise PowderError("fit the peaks before indexing them")
        lines = []
        for peak, line in zip(self.peaks, self.native.peaks,
                              strict=True):
            flags = [f for f in line.flags if f != "excluded"]
            if not peak.use:
                flags.append("excluded")
            lines.append(line.model_copy(update={"flags": flags}))
        return self.native.model_copy(update={"peaks": lines})


def fit_peaks(data: PowderData, radiation: Radiation,
              options: PeakOptions | None = None) -> PeakFit:
    """Find (or fit at the given positions) every line in ``data``."""
    from xtal.powder import bridge

    options = options or PeakOptions()
    lo, hi = data.range
    if options.start is not None:
        lo = max(lo, float(options.start))
    if options.finish is not None:
        hi = min(hi, float(options.finish))
    if not hi > lo:
        raise PowderError(f"{lo:g}-{hi:g}° is not a range")
    window = data.window(lo, hi)
    if options.positions:
        native, grid, background = bridge.fit_peaks_at(
            window, radiation, options.positions)
    else:
        native, grid, background = bridge.pick_peaks(
            window, radiation, shoulders=options.shoulders,
            flag_ghosts=options.flag_ghosts)
    native, twins = _drop_twins(native)

    peaks = [Peak(two_theta=line.two_theta,
                  two_theta_esd=line.two_theta_esd,
                  d=1.0 / np.sqrt(line.q) if line.q > 0 else np.nan,
                  area=line.intensity, area_esd=line.intensity_esd,
                  fwhm=line.fwhm,
                  flags=tuple(line.flags) + (("duplicate",)
                                             if k in twins else ()),
                  use=line.usable)
             for k, line in enumerate(native.peaks)]
    drawn = [line for k, line in enumerate(native.peaks)
             if k not in twins]
    calc = background + _lines_profile(
        grid, drawn, bridge.emission_lines(radiation))
    observed = np.interp(grid, window.two_theta, window.intensity)
    return PeakFit(
        peaks=peaks, two_theta=grid, y_obs=observed, y_calc=calc,
        y_background=background, radiation=radiation,
        wavelength=float(native.wavelength),
        notes=[d.message for d in native.diagnostics], native=native)


def _drop_twins(native):
    """``(peak_list, twins)``: a line fitted twice taken out once.

    RietX's fitting windows can overlap, and each fits the line they
    share -- rutile's 101 arrives as two lines from two groups at one
    position.  Indexing would read that as two observations of one
    d-spacing and weight it double, and a curve summed from both draws
    the line twice as tall as it is.  The copy with the larger esd is
    flagged ``excluded`` (RietX's word for a line its caller took out)
    and its index returned, so the table can say ``duplicate``.
    """
    lines = list(native.peaks)
    twins: set[int] = set()
    for i, line in enumerate(lines):
        for j in range(i):
            other = lines[j]
            if other.group == line.group or j in twins:
                continue
            close = max(0.1 * min(line.fwhm, other.fwhm),
                        3.0 * max(line.two_theta_esd,
                                  other.two_theta_esd))
            if abs(line.two_theta - other.two_theta) > close:
                continue
            twins.add(i if line.two_theta_esd >= other.two_theta_esd
                      else j)
    for k in twins:
        lines[k] = lines[k].model_copy(update={
            "flags": [*lines[k].flags, "excluded"]})
    if not twins:
        return native, twins
    return native.model_copy(update={"peaks": lines}), twins


def _lines_profile(grid: np.ndarray, lines, emission) -> np.ndarray:
    """Every fitted line drawn on the grid, its Kα2 included.

    For drawing only.  Each line's area, width and mixing are RietX's,
    placed at its Kα1 position and again at every further emission
    line's Bragg angle with that line's weight -- RietX fits the
    doublet as a constrained pair, but only inside a window that can
    stop short of the Kα2 (54.44° against rutile's 54.48°), so its own
    per-window curves leave the Kα2 undrawn.  Asymmetry is not drawn.
    """
    from xtal.analysis.pxrd import profile

    total = np.zeros_like(grid, dtype=float)
    primary = emission[0][0]
    for line in lines:
        if not (line.fwhm > 0 and np.isfinite(line.intensity)):
            continue
        sin_theta = np.sin(np.radians(line.two_theta / 2.0))
        for wavelength, weight in emission:
            s = sin_theta * wavelength / primary
            if s >= 1.0:
                continue
            at = 2.0 * np.degrees(np.arcsin(s))
            total += weight * line.intensity * profile(
                grid, at, line.fwhm, "pseudo-voigt", line.eta)
    return total
