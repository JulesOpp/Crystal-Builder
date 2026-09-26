"""
xtal.modules.powder
===================
The refinement steps, as registry entries of the PXRD module.

Each step of the refinement workbench -- peak fitting now; indexing,
Pawley, Rietveld and the rest as they arrive -- is an
:class:`~xtal.modules.registry.Action` here.  That buys what every
module gets: ``xtal run pxrd.peaks -p xy=...`` works on a machine with
no display, every run leaves a folder with its log, and the window
runs a step on the same worker, with the same Stop, as it runs Zeo++.
The science is :mod:`xtal.powder`; nothing here computes.

**The steps are not in the Modules menu** (``listed=False``).  A
step's input is the step before it -- indexing reads the peaks just
fitted and unticked -- and a generic form in a menu cannot hand it
that.  The workbench, *Refine against a measured pattern...*, is the
way in, and is the one entry listed.

**Every step greys out naming the extra** when RietX is missing, by
``find_spec`` and never an import.
"""

from __future__ import annotations

import numpy as np

from xtal import powder
from xtal.modules.job import JobResult
from xtal.modules.registry import Action, Param
from xtal.modules.report import Curve, Report, Row, Table
from xtal.params import Availability
from xtal.powder.data import RADIATIONS, PowderData, PowderError, Radiation

__all__ = ["DATA_PARAMS", "PEAK_PARAMS", "REFINE", "STEPS",
           "radiation_of", "run_peaks"]


def refine_available() -> Availability:
    reason = powder.missing()
    return Availability(not reason, reason)


#: What every step needs: the measurement, and what it was measured
#: with.  The workbench shows these once, above the steps; ``xtal
#: run`` takes them on every step.
DATA_PARAMS = (
    Param("xy", "Measured pattern", kind="path", default="",
          help="The pattern to refine against: 2θ and counts, one pair "
               "a line (.xy).  A third column is read as each point's "
               "error when every row has one."),
    Param("radiation", "Radiation", kind="choice", default="cu",
          choices=tuple((key, label) for key, label, _p in RADIATIONS),
          help="What the pattern was measured with.  A laboratory "
               "tube is a Kα1/Kα2 doublet unless a monochromator "
               "removed Kα2; the wavelengths are the standard ones."),
    Param("wavelength", "Wavelength", kind="float", default=0.0,
          minimum=0.0, maximum=5.0, decimals=6, suffix=" Å",
          help="A synchrotron's wavelength, from the beamline's "
               "calibration.  Read only for Synchrotron: the cell is "
               "only as right as this number."),
    Param("monochromator", "Monochromator 2θ", kind="float",
          default=0.0, minimum=0.0, maximum=90.0, decimals=2,
          suffix=" °",
          help="A diffracted-beam monochromator's angle, which changes "
               "the polarisation correction (TOPAS LP_Factor).  0 is "
               "none; 26.6 is graphite (002) with Cu."),
)

PEAK_PARAMS = (
    Param("start", "2θ from", kind="float", default=0.0, minimum=0.0,
          maximum=180.0, decimals=2, suffix=" °",
          help="Where the fit starts (TOPAS start_X).  0 is the start "
               "of the file."),
    Param("finish", "2θ to", kind="float", default=0.0, minimum=0.0,
          maximum=180.0, decimals=2, suffix=" °",
          help="Where it stops (TOPAS finish_X).  0 is the end of the "
               "file.  High-angle lines are weak and overlapped, and "
               "indexing does better without them."),
    Param("shoulders", "Look for shoulders", kind="bool", default=True,
          help="Seed a second line where a peak's curvature says one "
               "is hiding in its flank.  A seed that does not pay for "
               "itself is dropped again."),
    Param("flag_ghosts", "Flag Kβ and tungsten lines", kind="bool",
          default=True,
          help="Mark lines that sit where a strong line's Kβ or a "
               "tungsten-contaminated tube would put one, and keep "
               "them out of indexing."),
    Param("positions", "Fit only at", kind="text", default="",
          help="2θ positions, separated by commas, to fit exactly -- "
               "TOPAS's hand-written xo_Is list.  Empty finds the "
               "peaks.  A position with nothing at it comes back "
               "flagged, not dropped."),
)


def radiation_of(values: dict) -> Radiation:
    """The :class:`Radiation` a step's parameters describe."""
    monochromator = float(values.get("monochromator", 0.0) or 0.0)
    return Radiation(
        kind=str(values.get("radiation", "cu")),
        wavelength=float(values.get("wavelength", 0.0) or 0.0),
        monochromator_two_theta=monochromator or None)


def _data_of(values: dict) -> PowderData:
    path = str(values.get("xy", "") or "").strip()
    if not path:
        raise PowderError("no pattern given -- a .xy file to refine "
                          "against")
    return PowderData.from_xy(path)


def _positions(text: str) -> tuple[float, ...]:
    out = []
    for word in str(text or "").replace(";", ",").replace(
            " ", ",").split(","):
        if word.strip():
            try:
                out.append(float(word))
            except ValueError:
                raise PowderError(
                    f"{word!r} is not a 2θ position") from None
    return tuple(out)


# ======================================================================
#  PEAKS
# ======================================================================

PEAK_COLUMNS = ("No.", "2θ (°)", "esd", "d (Å)", "Area", "FWHM (°)",
                "Use", "Flags")


def run_peaks(job) -> JobResult:
    """Fit every line, and leave ``peaks.csv`` and ``fit.xy``."""
    from xtal.powder.peaks import PeakOptions, fit_peaks

    values = job.params
    try:
        data = _data_of(values)
        radiation = radiation_of(values)
        start = float(values.get("start", 0.0) or 0.0)
        finish = float(values.get("finish", 0.0) or 0.0)
        fit = fit_peaks(data, radiation, PeakOptions(
            start=start or None, finish=finish or None,
            shoulders=bool(values.get("shoulders", True)),
            flag_ghosts=bool(values.get("flag_ghosts", True)),
            positions=_positions(values.get("positions", ""))))
    except PowderError as exc:
        return JobResult.failure(str(exc))
    job.say(f"{len(fit.peaks)} lines, {fit.n_used} usable for "
            f"indexing, {radiation.label}")
    for note in fit.notes:
        job.note(note)
    artifacts = _write_peaks(job, fit) if job.folder is not None else []
    return JobResult(
        message=(f"{len(fit.peaks)} peaks fitted in {data.name}, "
                 f"{fit.n_used} usable for indexing"),
        artifacts=tuple(artifacts), report=peaks_report(fit, data.name),
        answer=fit)


def peaks_report(fit, name: str = "") -> Report:
    rows = tuple(
        Row.of(k, f"{p.two_theta:.4f}", f"{p.two_theta_esd:.4f}",
               f"{p.d:.5f}", f"{p.area:.1f}", f"{p.fwhm:.4f}",
               "yes" if p.use else "no", ", ".join(p.flags))
        for k, p in enumerate(fit.peaks, start=1))
    return Report(
        title=f"Peaks, {name}" if name else "Peaks",
        blocks=(fit_curve(fit, "Peak fit"),
                Table(title=f"Peaks ({len(rows)})", columns=PEAK_COLUMNS,
                      rows=rows,
                      note="Positions are the Kα1 line's.  Area is the "
                           "Kα1 line's integrated area.  A line out of "
                           "use is left out of indexing.")),
        note="  ".join(fit.notes))


def fit_curve(fit, title: str) -> Curve:
    """Observed, calculated and their difference, on counts."""
    return Curve(
        title=title, x=fit.two_theta, y=fit.y_obs,
        x_label="2-theta (degrees)", y_label="counts",
        series=(("calculated", fit.y_calc),
                ("background", fit.y_background),
                ("difference", fit.y_obs - fit.y_calc)),
        tick_sets=(("peaks", np.array([p.two_theta for p in fit.peaks
                                       if p.use])),),
        normalised=False)


def _write_peaks(job, fit) -> list:
    peaks_path = job.file("peaks.csv")
    lines = ["two_theta,two_theta_esd,d,area,area_esd,fwhm,use,flags"]
    lines += [f"{p.two_theta:.5f},{p.two_theta_esd:.5f},{p.d:.6f},"
              f"{p.area:.4f},{p.area_esd:.4f},{p.fwhm:.5f},"
              f"{int(p.use)},{' '.join(p.flags)}" for p in fit.peaks]
    peaks_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    fit_path = _write_fit(job.file("fit.xy"), fit, "peak fit")
    job.note(f"wrote {peaks_path.name} and {fit_path.name}")
    return [peaks_path, fit_path]


def _write_fit(path, fit, what: str):
    """Five columns: 2θ, observed, calculated, background, difference.

    The file a figure is made from later, in whatever the group plots
    with -- the curves the workbench drew, not a picture of them.
    """
    table = np.column_stack([fit.two_theta, fit.y_obs, fit.y_calc,
                             fit.y_background, fit.y_obs - fit.y_calc])
    header = (f"{what}, {fit.radiation.label}\n"
              f"2theta  observed  calculated  background  difference")
    np.savetxt(path, table, fmt="%.5f  %.3f  %.3f  %.3f  %.3f",
               header=header)
    return path


# ======================================================================
#  THE ENTRIES
# ======================================================================

#: The one listed entry: the window, opened by the shell's action of
#: this name.  ``shell`` was the Force Field panel's alone, for a live
#: plot, a preview that moves the atoms and one undo step at the end;
#: a Rietveld run is those three things again.
REFINE = Action(
    name="refine", label="Refine against a measured pattern...",
    tip="Open the refinement workbench: fit peaks, index, and refine "
        "against a measured .xy pattern",
    shell="refine_workbench", needs_structure=False,
    check=refine_available)

STEPS = (
    Action(name="peaks", label="Fit peaks",
           tip="Fit every line in a measured pattern",
           params=DATA_PARAMS + PEAK_PARAMS, run=run_peaks,
           needs_structure=False, listed=False,
           check=refine_available),
)
