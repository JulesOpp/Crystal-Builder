"""
xtal.powder.peaks
=================
Peak fitting: every resolvable line in a pattern, with a fitted
position, an area and an esd -- TOPAS's ``xo_Is`` step, and what
indexing reads.

Two stages, as TOPAS's ``a_peak`` is used.  **Finding** is RietX's
(``rietx.indexing.pick_peaks_with_state``, or ``fit_peaks`` at named
positions): each line fitted in its own window over the background
envelope RietX's detector draws.  **Refining** (:func:`refine_peaks`)
is one least-squares fit of the whole range -- a Chebyshev background
of the order asked for under every line kept, each line's position,
area, width and Lorentzian fraction free, its Kα2 placed by Bragg's
law at RietX's weight -- which is what TOPAS's ``xo_Is`` with a
``bkg`` line is.  RietX has no whole-pattern peak fit (its
``compile_model`` needs a cell, and a cell is what this step is
for), so the refinement is written here, on ``scipy``'s
``least_squares``; the peak shape is
:func:`xtal.analysis.pxrd.profile`, the one the calculated pattern
uses.

What is also decided here is what the answer looks like to this
application: a table a person can read, untick a line in, add a line
to, and hand to indexing -- and the curves to draw over the data, the
sum and each line on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from xtal.powder.data import PowderData, PowderError, Radiation

__all__ = ["Peak", "PeakFit", "PeakOptions", "empty_fit", "fit_peaks",
           "refine_peaks"]


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
    #: Lorentzian fraction of the pseudo-Voigt
    eta: float = 0.5
    #: ``"fitted"``, or ``"manual"`` for a line a person placed
    origin: str = "fitted"
    #: RietX's own record of a line it found, kept so indexing reads
    #: exactly what was fitted; ``None`` for one refined or placed here
    line: Any = None


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
    #: ``[(wavelength, weight), ...]``, the primary line first at 1:
    #: what each line is drawn with, its Kα2 included
    emission: list = field(default_factory=list)
    #: the whole-pattern Rwp, for a refined fit; ``None`` for a found one
    rwp: float | None = None

    @property
    def ticks(self) -> np.ndarray:
        """Where the lines in use are, for the comb under the plot."""
        return np.array([p.two_theta for p in self.peaks if p.use])

    @property
    def n_used(self) -> int:
        return sum(1 for peak in self.peaks if peak.use)

    def for_indexing(self):
        """RietX's list with the unticked lines flagged ``excluded``.

        ``excluded`` is RietX's own word for a line its caller took
        out, so ``PeakList.usable()`` -- which every indexing engine
        reads -- leaves it out without anything here re-implementing
        what "usable" means.  A line RietX found goes as RietX
        recorded it; one refined or placed here is recorded afresh.
        """
        from xtal.powder import bridge

        if not self.peaks:
            raise PowderError("fit the peaks before indexing them")
        lines = []
        for k, peak in enumerate(self.peaks):
            line = peak.line
            if line is None:
                line = bridge.observed_peak(
                    peak.two_theta, peak.two_theta_esd, peak.area,
                    peak.area_esd, peak.fwhm, peak.eta, self.wavelength,
                    group=k, origin=peak.origin)
            flags = [f for f in line.flags if f != "excluded"]
            if not peak.use:
                flags.append("excluded")
            lines.append(line.model_copy(update={"flags": flags}))
        if self.native is not None:
            return self.native.model_copy(update={"peaks": lines})
        return bridge.peak_list(lines, self.wavelength,
                                float(self.two_theta[0]),
                                float(self.two_theta[-1]))

    def curves(self) -> list:
        """Each line on its own, Kα2 included, above no background:
        ``None`` for a line out of use, which is not drawn."""
        return [_lines_profile(self.two_theta, [p], self.emission)
                if p.use else None for p in self.peaks]

    def add(self, positions, data: PowderData) -> list[Peak]:
        """Lines placed by hand at ``positions``, in use, for
        :func:`refine_peaks` to fit.

        Seeded from the data: the height above the background at the
        position, and the median width of the lines already there --
        or, with none yet, the width of the data's own peak there.
        Nothing is fitted until Refine; until then the line is drawn
        where it was put, so a person can see it is on the peak meant.
        """
        lo, hi = float(self.two_theta[0]), float(self.two_theta[-1])
        widths = [p.fwhm for p in self.peaks if p.use and p.fwhm > 0]
        added = []
        for x in positions:
            x = float(x)
            if not lo <= x <= hi:
                raise PowderError(
                    f"{x:g}° is outside the fitted range {lo:g}-{hi:g}°")
            height = float(np.interp(x, data.two_theta, data.intensity)
                           - np.interp(x, self.two_theta,
                                       self.y_background))
            fwhm = float(np.median(widths)) if widths else \
                _width_at(self, x)
            sin_theta = np.sin(np.radians(x / 2.0))
            peak = Peak(two_theta=x, two_theta_esd=np.nan,
                        d=self.wavelength / (2.0 * sin_theta),
                        area=max(height, 0.0) * fwhm * 1.2,
                        area_esd=np.nan, fwhm=fwhm, flags=("manual",),
                        origin="manual")
            added.append(peak)
        self.peaks = sorted(self.peaks + added,
                            key=lambda p: p.two_theta)
        self.native = None
        return added


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
                  use=line.usable, eta=float(line.eta), line=line)
             for k, line in enumerate(native.peaks)]
    emission = bridge.emission_lines(radiation)
    drawn = [peak for k, peak in enumerate(peaks) if k not in twins]
    calc = background + _lines_profile(grid, drawn, emission)
    observed = np.interp(grid, window.two_theta, window.intensity)
    return PeakFit(
        peaks=peaks, two_theta=grid, y_obs=observed, y_calc=calc,
        y_background=background, radiation=radiation,
        wavelength=float(native.wavelength),
        notes=[d.message for d in native.diagnostics], native=native,
        emission=emission)


def empty_fit(data: PowderData, radiation: Radiation, start: float,
              finish: float) -> PeakFit:
    """A peak list with no lines in it yet, for lines placed by hand.

    The background it starts from is flat at the pattern's tenth
    percentile -- a seed for Refine, which fits its own.
    """
    from xtal.powder import bridge

    window = data.window(start, finish)
    level = float(np.percentile(window.intensity, 10))
    background = np.full(len(window), level)
    emission = bridge.emission_lines(radiation)
    return PeakFit(
        peaks=[], two_theta=window.two_theta, y_obs=window.intensity,
        y_calc=background.copy(), y_background=background,
        radiation=radiation, wavelength=float(emission[0][0]),
        emission=emission)


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
    """Every line (a :class:`Peak`) drawn on the grid, its Kα2 included.

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
        if not (line.fwhm > 0 and np.isfinite(line.area)):
            continue
        sin_theta = np.sin(np.radians(line.two_theta / 2.0))
        for wavelength, weight in emission:
            s = sin_theta * wavelength / primary
            if s >= 1.0:
                continue
            at = 2.0 * np.degrees(np.arcsin(s))
            total += weight * line.area * profile(
                grid, at, line.fwhm, "pseudo-voigt", line.eta)
    return total


# ======================================================================
#  REFINING
# ======================================================================

#: How far either side of its starting place a line's profile is
#: evaluated, in widths: a pseudo-Voigt's Lorentzian tail at 15 FWHM is
#: 0.1 % of its height, below the noise of any real pattern.
_REACH_FWHM = 15.0


def _width_at(fit: PeakFit, x: float) -> float:
    """The full width at half maximum of the data's peak nearest ``x``,
    above the fit's background: a seed, not a measurement."""
    grid, net = fit.two_theta, fit.y_obs - fit.y_background
    step = float(np.median(np.diff(grid)))
    near = np.flatnonzero(np.abs(grid - x) <= max(0.2, 5 * step))
    if not len(near):
        return 5.0 * step
    top = near[np.argmax(net[near])]
    half = net[top] / 2.0
    if not half > 0:
        return 5.0 * step
    left, right = top, top
    while left > 0 and net[left] > half:
        left -= 1
    while right < len(net) - 1 and net[right] > half:
        right += 1
    return max(float(grid[right] - grid[left]), 2.0 * step)


def refine_peaks(data: PowderData, radiation: Radiation, fit: PeakFit,
                 background_terms: int = 8, *, cancel=None) -> PeakFit:
    """The lines in use, refined together over the whole range.

    A Chebyshev background of ``background_terms`` coefficients, and
    for every line in use its position, area, width and Lorentzian
    fraction -- TOPAS's ``xo_Is`` under a ``bkg`` line.  **The lines
    out of use are gone from the answer**: refining is what a person
    does once the list is the list, and a line unticked is one they
    have said is not there.  The Kα2 of each line sits where Bragg's
    law puts it, at the emission line's weight, and is never a free
    line of its own.

    ``cancel`` is a job's :class:`~xtal.modules.job.Cancellation`;
    Stop raises :class:`~xtal.powder.data.PowderStopped`.
    """
    from numpy.polynomial import chebyshev
    from scipy.optimize import least_squares
    from scipy.sparse import lil_matrix

    from xtal.powder import bridge
    from xtal.powder.data import PowderStopped

    kept = [p for p in fit.peaks if p.use]
    if not kept:
        raise PowderError("no lines are in use -- tick at least one "
                          "before refining")
    lo, hi = float(fit.two_theta[0]), float(fit.two_theta[-1])
    window = data.window(lo, hi)
    x, y = window.two_theta, window.intensity
    sigma = window.sigma if window.sigma is not None \
        else np.sqrt(np.maximum(y, 1.0))
    emission = fit.emission or bridge.emission_lines(radiation)
    step = float(np.median(np.diff(x)))
    n_bkg = max(int(background_terms), 1)
    basis = chebyshev.chebvander(2.0 * (x - lo) / (hi - lo) - 1.0,
                                 n_bkg - 1)
    start_bkg = np.interp(x, fit.two_theta, fit.y_background)
    b0 = np.linalg.lstsq(basis, start_bkg, rcond=None)[0]

    x0, lower, upper, rows = list(b0), [-np.inf] * n_bkg, \
        [np.inf] * n_bkg, []
    for peak in kept:
        width = peak.fwhm if peak.fwhm > 0 else 10.0 * step
        slack = max(2.0 * width, 5.0 * step)
        split = _doublet_span(peak.two_theta, emission)
        reach = _REACH_FWHM * width + split + slack
        rows.append(slice(int(np.searchsorted(x, peak.two_theta - reach)),
                          int(np.searchsorted(x, peak.two_theta + reach))))
        x0 += [peak.two_theta, max(peak.area, 0.0), width,
               min(max(peak.eta, 0.0), 1.0)]
        # a width may shrink to the data's own step: a seed placed by
        # hand can start several times too wide
        lower += [peak.two_theta - slack, 0.0, step, 0.0]
        upper += [peak.two_theta + slack, np.inf, 5.0 * width, 1.0]
    x0 = np.clip(np.asarray(x0), lower, upper)

    def model(params):
        background = basis @ params[:n_bkg]
        total = background.copy()
        for j, sl in enumerate(rows):
            at, area, width, eta = params[n_bkg + 4 * j:n_bkg + 4 * j + 4]
            total[sl] += area * _doublet(x[sl], at, width, eta, emission)
        return total, background

    def residual(params):
        if cancel is not None and cancel.requested:
            raise PowderStopped("stopped")
        return (model(params)[0] - y) / sigma

    sparsity = lil_matrix((len(x), len(x0)), dtype=int)
    sparsity[:, :n_bkg] = 1
    for j, sl in enumerate(rows):
        sparsity[sl, n_bkg + 4 * j:n_bkg + 4 * j + 4] = 1
    solution = least_squares(residual, x0, bounds=(lower, upper),
                             jac_sparsity=sparsity, method="trf",
                             x_scale="jac")
    params = solution.x
    calc, background = model(params)
    esd = _esds(solution, len(x))
    rwp = float(np.sqrt(np.sum(((y - calc) / sigma) ** 2)
                        / np.sum((y / sigma) ** 2)))

    peaks = []
    for j, before in enumerate(kept):
        k = n_bkg + 4 * j
        at, area, width, eta = params[k:k + 4]
        sin_theta = np.sin(np.radians(at / 2.0))
        peaks.append(Peak(
            two_theta=float(at), two_theta_esd=float(esd[k]),
            d=fit.wavelength / (2.0 * sin_theta), area=float(area),
            area_esd=float(esd[k + 1]), fwhm=float(width),
            flags=("manual",) if before.origin == "manual" else (),
            eta=float(eta), origin=before.origin))
    notes = [f"refined {len(peaks)} lines over a {n_bkg}-term "
             f"background: Rwp {100 * rwp:.2f} %"]
    if not solution.success:
        notes.append(f"the fit did not converge: {solution.message}")
    dropped = len(fit.peaks) - len(kept)
    if dropped:
        notes.append(f"{dropped} lines out of use were removed")
    return PeakFit(
        peaks=peaks, two_theta=x, y_obs=y, y_calc=calc,
        y_background=background, radiation=radiation,
        wavelength=fit.wavelength, notes=notes, native=None,
        emission=emission, rwp=rwp)


def _doublet(x, at: float, width: float, eta: float, emission):
    """One line of unit Kα1 area, every emission line placed by Bragg."""
    from xtal.analysis.pxrd import profile

    primary = emission[0][0]
    sin_theta = np.sin(np.radians(at / 2.0))
    total = np.zeros_like(x)
    for wavelength, weight in emission:
        s = sin_theta * wavelength / primary
        if s < 1.0:
            total += weight * profile(x, 2.0 * np.degrees(np.arcsin(s)),
                                      width, "pseudo-voigt", eta)
    return total


def _doublet_span(two_theta: float, emission) -> float:
    """How far past its Kα1 a line's last emission line lands."""
    primary = emission[0][0]
    sin_theta = np.sin(np.radians(two_theta / 2.0))
    furthest = 0.0
    for wavelength, _weight in emission[1:]:
        s = min(sin_theta * wavelength / primary, 1.0)
        furthest = max(furthest,
                       abs(2.0 * np.degrees(np.arcsin(s)) - two_theta))
    return furthest


def _esds(solution, n_points: int) -> np.ndarray:
    """Standard uncertainties from the Jacobian at the minimum, scaled
    by the reduced chi-squared as a least-squares esd is."""
    jac = solution.jac
    jac = jac.toarray() if hasattr(jac, "toarray") else np.asarray(jac)
    dof = max(n_points - jac.shape[1], 1)
    chi2 = 2.0 * float(solution.cost) / dof
    covariance = np.linalg.pinv(jac.T @ jac) * chi2
    return np.sqrt(np.clip(np.diag(covariance), 0.0, None))
