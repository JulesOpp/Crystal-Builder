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

__all__ = ["DATA_PARAMS", "INDEX_PARAMS", "PAWLEY_PARAMS", "PEAK_PARAMS",
           "REFINE", "RIETVELD_PARAMS", "STEPS", "STEP_PARAMS",
           "radiation_of", "refined_notes", "run_index", "run_pawley",
           "run_peaks", "run_rietveld"]


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


#: What Refine adds to the peak step.
REFINE_PEAK_PARAMS = (
    Param("background_terms", "Background terms", kind="int",
          default=8, minimum=1, maximum=30,
          help="Coefficients of the Chebyshev background Refine fits "
               "under the lines (TOPAS's bkg line).  More follow a "
               "curved or humped background; too many start fitting "
               "the tails of broad peaks.  Find peaks draws its own "
               "background and does not read this."),
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
    try:
        data, radiation, fit = _fit_peaks(job.params)
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


def run_refine_peaks(job) -> JobResult:
    """Refine the lines in use together; leave ``peaks.csv`` and
    ``fit.xy``.

    The lines are the ones the job was handed -- the workbench's,
    with its unticks and the lines added by hand -- or, run on its
    own, found here first (or fitted at ``positions``).
    """
    from xtal.powder.data import PowderStopped
    from xtal.powder.peaks import refine_peaks

    values = job.params
    try:
        if job.given is not None:
            fit, radiation = job.given, job.given.radiation
            data = _data_of(values)
        else:
            job.say("finding the peaks first")
            data, radiation, fit = _fit_peaks(values)
        job.say(f"refining {fit.n_used} lines together")
        refined = refine_peaks(
            data, radiation, fit,
            int(values.get("background_terms", 8)), cancel=job.cancel)
    except PowderStopped:
        return JobResult.stopped("peak refinement stopped")
    except PowderError as exc:
        return JobResult.failure(str(exc))
    for note in refined.notes:
        job.note(note)
    artifacts = _write_peaks(job, refined) \
        if job.folder is not None else []
    return JobResult(
        message=(f"{len(refined.peaks)} peaks refined in {data.name}, "
                 f"Rwp {100 * refined.rwp:.2f} %"),
        artifacts=tuple(artifacts),
        report=peaks_report(refined, data.name), answer=refined)


def _fit_peaks(values: dict):
    """``(data, radiation, fit)`` from the peak step's parameters."""
    from xtal.powder.peaks import PeakOptions, fit_peaks

    data = _data_of(values)
    radiation = radiation_of(values)
    start = float(values.get("start", 0.0) or 0.0)
    finish = float(values.get("finish", 0.0) or 0.0)
    fit = fit_peaks(data, radiation, PeakOptions(
        start=start or None, finish=finish or None,
        shoulders=bool(values.get("shoulders", True)),
        flag_ghosts=bool(values.get("flag_ghosts", True)),
        positions=_positions(values.get("positions", ""))))
    return data, radiation, fit


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


def fit_curve(fit, title: str, ticks: str = "peaks") -> Curve:
    """Observed, calculated and their difference, on counts."""
    return Curve(
        title=title, x=fit.two_theta, y=fit.y_obs,
        x_label="2-theta (degrees)", y_label="counts",
        series=(("calculated", fit.y_calc),
                ("background", fit.y_background),
                ("difference", fit.y_obs - fit.y_calc)),
        tick_sets=((ticks, np.asarray(fit.ticks)),),
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
#  INDEXING
# ======================================================================

INDEX_PARAMS = (
    Param("bravais", "Bravais lattices", kind="text", default="all",
          help="Which lattices to search, TOPAS's Bravais_*_sgs: aP mP "
               "mC oP oC oI oF tP tI hP hR cP cI cF, separated by "
               "commas, or all.  hP is hexagonal and trigonal P "
               "together.  Leaving out the low symmetries saves most "
               "of the time."),
    Param("space_groups", "Space groups", kind="text", default="",
          help="Only these groups, by symbol or number, separated by "
               "commas (C2221, Ccc2).  The search is kept to their "
               "lattices and only the extinction classes holding one "
               "are listed.  Empty is every group."),
    Param("zero_error", "Zero error allowance", kind="float",
          default=0.3, minimum=0.0, maximum=1.0, step=0.1, decimals=3,
          suffix=" °",
          help="How far a systematic 2θ shift may move the lines, "
               "TOPAS's index_zero_error, from 0 to 1°.  0 lets RietX "
               "measure it from line pairs, or assume 0.05°.  A wide "
               "allowance finds a cell through a badly aligned "
               "sample and lets wrong cells match too: on a clean "
               "rutile pattern the right cell ranks first up to 0.3° "
               "and a wrong one does from 0.5°."),
    Param("max_volume", "Largest volume", kind="float", default=0.0,
          minimum=0.0, maximum=1e6, decimals=0, suffix=" Å³",
          help="The largest cell to report.  0 takes the bound from "
               "the number of lines and their positions."),
    Param("longest_axis", "Longest axis", kind="float", default=50.0,
          minimum=5.0, maximum=100.0, decimals=1, suffix=" Å",
          help="The longest cell axis searched (strictly, d(100)).  "
               "50 Å holds most frameworks' cells.  The search grows "
               "fast with it: a cell known to be small is found in "
               "seconds with this lowered, and 50 Å over the low "
               "symmetries can use the whole time budget."),
    Param("budget", "Time budget", kind="float", default=60.0,
          minimum=1.0, maximum=3600.0, decimals=0, suffix=" s",
          help="The most the search and its validation may take.  "
               "What was reached when it runs out is reported, with "
               "the systems it did not finish named."),
    Param("rank_groups", "Rank space groups for the top", kind="int",
          default=3, minimum=0, maximum=20, suffix=" cells",
          help="Fit each extinction class of this many of the best "
               "cells, to say which space groups the absences allow.  "
               "About a second a cell for a small one; 0 skips it."),
)

INDEX_COLUMNS = ("Rank", "System", "Lattice", "a", "b", "c", "α", "β",
                 "γ", "V (Å³)", "GoF", "Unindexed", "GoF/(Unind.+1)",
                 "Confidence", "Le Bail Rwp", "Space groups")

#: How the cell table can be ordered: ``(key, label)``.  TOPAS sorts
#: its .ndx by GOF or by GOF over the unindexed lines; RietX's own
#: rank weighs its whole figure-of-merit panel and the engines'
#: agreement.
INDEX_SORTS = (("rank", "RietX's rank"), ("gof", "GoF"),
               ("gof_unindexed", "GoF / (unindexed + 1)"))


#: RietX's figure-of-merit keys as the literature writes them.
FOM_NAMES = {"m20": "M20", "f_n": "F_N", "m_sym": "M_sym",
             "m_rev": "M_rev"}


def index_options(values: dict):
    """The :class:`~xtal.powder.index.IndexOptions` the form says."""
    from xtal.powder.index import IndexOptions, parse_bravais

    return IndexOptions(
        bravais=parse_bravais(values.get("bravais", "all")),
        space_groups=str(values.get("space_groups", "") or ""),
        zero_error=float(values.get("zero_error", 0.3) or 0.0),
        max_volume=float(values.get("max_volume", 0.0) or 0.0),
        longest_axis=float(values.get("longest_axis", 50.0) or 50.0),
        budget=float(values.get("budget", 60.0) or 60.0),
        rank_groups=int(values.get("rank_groups", 3)))


def run_index(job) -> JobResult:
    """Search for the cell; leave ``cells.csv``.

    The peaks are the ones the job was handed -- the workbench's, with
    the user's unticks -- or, run on its own, fitted here with the
    peak step's parameters.
    """
    from xtal.powder.index import index

    values = job.params
    try:
        options = index_options(values)
        if job.given is not None:
            fit = job.given
            data = _data_of(values).window(*_range_of(fit))
            radiation = fit.radiation
        else:
            job.say("fitting the peaks first")
            _data, radiation, fit = _fit_peaks(values)
            data = _data.window(*_range_of(fit))
        peak_list = fit.for_indexing()
        job.say(f"indexing {len(peak_list.usable())} lines over "
                f"{', '.join(sorted(options.bravais))}")
        result = index(peak_list, data, radiation, options,
                       cancel=job.cancel, say=job.say)
    except PowderError as exc:
        return JobResult.failure(str(exc))
    for note in result.notes:
        job.note(note)
    artifacts = []
    if job.folder is not None:
        artifacts.append(_write_cells(job.file("cells.csv"), result))
        job.note("wrote cells.csv")
    top = result.rows[0] if result.rows else None
    if top is None:
        message = "no cell indexes these lines in the lattices searched"
    else:
        a, b, c = top.cell[:3]
        message = (f"{len(result.rows)} cells; the first is "
                   f"{top.bravais} {a:.4f} {b:.4f} {c:.4f} Å, "
                   f"{top.confidence} confidence")
    if result.stopped:
        message = "stopped -- " + message
    return JobResult(message=message, artifacts=tuple(artifacts),
                     report=index_report(result, data.name),
                     answer=result, cancelled=result.stopped)


def _range_of(fit) -> tuple[float, float]:
    return float(fit.two_theta[0]), float(fit.two_theta[-1])


def gof_name(result) -> str:
    """Which figure the GoF column is, for its header: one figure for
    every row of a run, because every row was scored on the same
    lines."""
    names = {row.fom[0] for row in result.rows if row.fom}
    return ", ".join(FOM_NAMES[n] for n in sorted(names)) or "--"


def sorted_rows(result, key: str = "rank") -> list:
    """The rows in the order ``key`` (an :data:`INDEX_SORTS` key) asks,
    best first; a row with no figure goes last."""
    rows = list(result.rows)
    if key == "gof":
        return sorted(rows, key=lambda r: -(r.gof or -1.0))
    if key == "gof_unindexed":
        return sorted(rows, key=lambda r: -(r.gof_per_unindexed or -1.0))
    return sorted(rows, key=lambda r: r.rank)


def index_cells(row) -> tuple[str, ...]:
    """A row's cell, as the table writes it."""
    a, b, c, alpha, beta, gamma = row.cell
    fom = f"{row.gof:.2f}" if row.gof is not None else "--"
    per = f"{row.gof_per_unindexed:.2f}" \
        if row.gof_per_unindexed is not None else "--"
    rwp = f"{100 * row.lebail_rwp:.2f} %" \
        if row.lebail_rwp is not None else "not validated"
    return (str(row.rank), row.system, row.bravais, f"{a:.5f}",
            f"{b:.5f}", f"{c:.5f}", f"{alpha:.3f}", f"{beta:.3f}",
            f"{gamma:.3f}", f"{row.volume:.2f}", fom,
            str(row.unindexed), per, row.confidence, rwp,
            row.space_groups if row.classes is not None else "--")


def index_report(result, name: str = "") -> Report:
    rows = tuple(Row.of(*index_cells(row)) for row in result.rows)
    if result.best is not None:
        verdict = (f"RietX names cell {result.best + 1}: every engine "
                   f"found it and nothing refuted it.")
    else:
        verdict = ("RietX names no cell -- the engines, the figures of "
                   "merit or the whole-pattern fit did not agree well "
                   "enough.  The ranking is still the ranking; the "
                   "confidence column says why each is not higher.")
    unfinished = [s for s, done in result.complete.items() if not done]
    if unfinished:
        verdict += ("  Not searched to the end: "
                    + ", ".join(unfinished) + ".")
    return Report(
        title=f"Indexing, {name}" if name else "Indexing",
        blocks=(Table(title=f"Cells ({len(rows)})",
                      columns=INDEX_COLUMNS, rows=rows,
                      note=f"GoF is {gof_name(result)}: how well the "
                           "cell explains the line positions, higher "
                           "better.  Space groups are the most likely "
                           "extinction class's, all of them: a powder "
                           "pattern cannot tell groups in one class "
                           "apart."),),
        note=verdict)


def _write_cells(path, result):
    """TOPAS's ``.ndx``, as a table anything can read."""
    lines = ["rank,system,lattice,a,b,c,alpha,beta,gamma,volume,"
             "gof,unindexed,confidence,lebail_rwp,space_groups"]
    for row in result.rows:
        a, b, c, alpha, beta, gamma = row.cell
        fom = f"{row.fom[0]} {row.fom[1]:.3f}" if row.fom else ""
        rwp = "" if row.lebail_rwp is None else f"{row.lebail_rwp:.5f}"
        groups = row.space_groups.replace(",", ";") \
            if row.classes is not None else ""
        lines.append(
            f"{row.rank},{row.system},{row.bravais},{a:.6f},{b:.6f},"
            f"{c:.6f},{alpha:.4f},{beta:.4f},{gamma:.4f},"
            f"{row.volume:.3f},{fom},{row.unindexed},{row.confidence},"
            f"{rwp},{groups}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ======================================================================
#  PAWLEY
# ======================================================================

PAWLEY_PARAMS = (
    Param("cell", "Cell", kind="text", default="",
          help="a b c, or a b c α β γ, in Å and degrees -- a row of "
               "the indexing table, or the open structure's."),
    Param("space_group", "Space group", kind="text", default="",
          help="By symbol or number.  A group with fewer absences "
               "than the true one fits as well and says less; one with "
               "more leaves real lines unfitted."),
    Param("start", "2θ from", kind="float", default=0.0, minimum=0.0,
          maximum=180.0, decimals=2, suffix=" °",
          help="Where the fit starts (TOPAS start_X).  0 is the start "
               "of the file."),
    Param("finish", "2θ to", kind="float", default=0.0, minimum=0.0,
          maximum=180.0, decimals=2, suffix=" °",
          help="Where it stops (TOPAS finish_X).  0 is the end of the "
               "file."),
    Param("background_terms", "Background terms", kind="int",
          default=8, minimum=1, maximum=30,
          help="Coefficients of the Chebyshev background, TOPAS's bkg "
               "line.  More follow a curved or humped background; too "
               "many start fitting the tails of broad peaks."),
    Param("zero", "Refine zero error", kind="bool", default=False,
          help="A constant shift of every line (TOPAS Zero_Error).  "
               "Strongly correlated with specimen displacement: free "
               "one of the two unless the range is wide."),
    Param("displacement", "Refine specimen displacement", kind="bool",
          default=True,
          help="A shift that falls off as cos θ (TOPAS "
               "Specimen_Displacement).  Strongly correlated with the "
               "zero error and with the cell: free one of the two "
               "unless the range is wide.  Not refined for a "
               "synchrotron capillary."),
    Param("hold", "Hold", kind="text", default="",
          help="Cell numbers held at the value given while the rest "
               "refine: a b c alpha beta gamma, separated by commas, "
               "or cell for all of them.  Empty refines every number "
               "the space group leaves free."),
    Param("size", "Crystallite size broadening", kind="bool",
          default=True,
          help="Lorentzian and Gaussian size terms (TOPAS CS_L, "
               "CS_G): widths that grow as 1/cos θ."),
    Param("strain", "Strain broadening", kind="bool", default=True,
          help="Lorentzian and Gaussian strain terms (TOPAS Strain_L, "
               "Strain_G): widths that grow as tan θ."),
)

REFLECTION_COLUMNS = ("h", "k", "l", "d (Å)", "2θ (°)", "m",
                      "Intensity")


def pawley_options(values: dict):
    from xtal.powder.pawley import PawleyOptions, parse_hold

    start = float(values.get("start", 0.0) or 0.0)
    finish = float(values.get("finish", 0.0) or 0.0)
    return PawleyOptions(
        start=start or None, finish=finish or None,
        background_terms=int(values.get("background_terms", 8)),
        zero=bool(values.get("zero", False)),
        displacement=bool(values.get("displacement", True)),
        hold_cell=parse_hold(values.get("hold", "")),
        size=bool(values.get("size", True)),
        strain=bool(values.get("strain", True)))


def run_pawley(job) -> JobResult:
    """Fit the cell; leave ``fit.xy`` and ``reflections.csv``."""
    from xtal.powder.data import PowderStopped
    from xtal.powder.pawley import pawley

    values = job.params
    try:
        data = _data_of(values)
        radiation = radiation_of(values)
        cell = str(values.get("cell", "") or "")
        group = str(values.get("space_group", "") or "").strip()
        if not cell.strip() or not group:
            raise PowderError("a Pawley fit needs a cell and a space "
                              "group -- choose a row of the indexing "
                              "table, or type them")
        job.say(f"Pawley fit of {cell} in {group}")
        fit = pawley(data, radiation, cell, group,
                     pawley_options(values), cancel=job.cancel,
                     folder=job.path)
    except PowderStopped:
        return JobResult.stopped("Pawley fit stopped")
    except PowderError as exc:
        return JobResult.failure(str(exc))
    for note in fit.notes:
        job.note(note)
    artifacts = []
    if job.folder is not None:
        artifacts = [_write_fit(job.file("fit.xy"), fit, "Pawley fit"),
                     _write_reflections(job.file("reflections.csv"),
                                        fit)]
        job.note("wrote fit.xy and reflections.csv")
    a, b, c = fit.cell[:3]
    message = (f"Pawley Rwp {100 * fit.rwp:.2f} %, GoF {fit.gof:.2f}: "
               f"{a:.5f} {b:.5f} {c:.5f} Å in {fit.space_group}")
    if not fit.converged:
        message += f" ({fit.status}, not converged)"
    return JobResult(message=message, artifacts=tuple(artifacts),
                     report=pawley_report(fit, data.name), answer=fit)


def pawley_summary(fit) -> str:
    """The fit's figures and cell, as the result box shows them."""
    names = ("a", "b", "c", "α", "β", "γ")
    cell = "   ".join(
        f"{n} {_with_esd(v, e)}" for n, v, e in
        zip(names, fit.cell, fit.cell_esd, strict=True))
    return (f"Rwp {100 * fit.rwp:.2f} %   Rp {100 * fit.rp:.2f} %   "
            f"Rexp {100 * fit.rexp:.2f} %   GoF {fit.gof:.3f}\n"
            f"{cell}\nV {fit.volume:.2f} Å³, {fit.space_group}"
            + ("" if fit.converged else f"\n{fit.status}: not converged"))


def _with_esd(value: float, esd: float) -> str:
    """``4.59398(4)``: the esd in the last digit, as a paper writes it."""
    if not esd or not np.isfinite(esd):
        # held by the symmetry: 90, not 90.0000
        return f"{value:g}" if float(value).is_integer() \
            else f"{value:.4f}"
    digits = max(0, min(6, 1 - int(np.floor(np.log10(esd)))))
    scaled = int(round(esd * 10 ** digits))
    if scaled >= 20 and digits > 0:
        digits -= 1
        scaled = int(round(esd * 10 ** digits))
    return f"{value:.{digits}f}({scaled})"


def pawley_report(fit, name: str = "") -> Report:
    rows = tuple(Row.of(*r.hkl, f"{r.d:.5f}", f"{r.two_theta:.4f}",
                        r.multiplicity, f"{r.intensity:.2f}")
                 for r in fit.reflections)
    return Report(
        title=f"Pawley, {name}" if name else "Pawley",
        blocks=(fit_curve(fit, "Pawley fit", "reflections"),
                Table(title=f"Reflections ({len(rows)})",
                      columns=REFLECTION_COLUMNS, rows=rows,
                      note="Intensities are the Pawley fit's, "
                           "multiplicity included, at Kα1.")),
        note=pawley_summary(fit).replace("\n", ".  ")
        + ("  " + "  ".join(fit.notes) if fit.notes else ""))


def _write_reflections(path, fit):
    """TOPAS's ``hkl_Is`` list."""
    lines = ["h,k,l,d,two_theta,multiplicity,intensity"]
    lines += [f"{h},{k},{m},{r.d:.6f},{r.two_theta:.5f},"
              f"{r.multiplicity},{r.intensity:.5f}"
              for r in fit.reflections for h, k, m in [r.hkl]]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ======================================================================
#  WHAT A FIT REFINED
# ======================================================================

#: What each box of a form refined, as ``(RietX path, label, unit)``:
#: the numbers written beside the box once a fit has run.
_SHOWN = {
    "zero": (("instrument.zero_shift", "", "°"),),
    "displacement": (("instrument.geometry.sample_displacement", "",
                      " mm"),),
    "size": (("phases.0.lor_size", "L", "°"),
             ("phases.0.gauss_size", "G", "°²")),
    "strain": (("phases.0.lor_strain", "L", "°"),
               ("phases.0.gauss_strain", "G", "°²")),
    "profile": tuple((f"instrument.profile.{t}", t.upper(), "")
                     for t in "uvwxy"),
    "preferred_axis": (("phases.0.preferred_orientation.r", "r", ""),),
}

#: The per-atom boxes: the label of the atom is the path's middle.
_PER_ATOM = {"biso": "biso", "occupancy": "occ"}


def refined_notes(fit) -> dict[str, str]:
    """``{box: text}``: what a fit refined, to write beside each box
    that freed it -- ``4.594(1)`` beside a cell number, ``L 0.12(1)
    G 0.03(2)`` beside strain broadening.  A box that refined nothing
    has no entry.
    """
    refined = getattr(fit, "refined", None) or {}
    out = {}
    for box, rows in _SHOWN.items():
        words = [f"{label} {_with_esd(*refined[path])}{unit}".strip()
                 for path, label, unit in rows if path in refined]
        if words:
            # three to a line: five profile terms on one ran off the
            # side of the form
            out[box] = "\n".join("   ".join(words[i:i + 3])
                                  for i in range(0, len(words), 3))
    background = [k for k in refined if k.startswith(
        "instrument.background.")]
    if background:
        out["background_terms"] = f"{len(background)} refined"
    for n, name in enumerate(("a", "b", "c", "alpha", "beta", "gamma")):
        path = f"phases.0.cell.{name}"
        if path in refined:
            out[name] = _with_esd(fit.cell[n], fit.cell_esd[n])
    labels = getattr(fit, "atom_labels", ())
    for box, key in _PER_ATOM.items():
        words = []
        for path, (value, esd) in refined.items():
            parts = path.split(".")
            if len(parts) == 5 and parts[2] == "atoms" \
                    and parts[4] == key:
                k = int(parts[3])
                label = labels[k] if k < len(labels) else f"#{k + 1}"
                words.append(f"{label} {_with_esd(value, esd)}")
        if words:
            out[box] = ", ".join(words[:4]) + (
                f" (+{len(words) - 4})" if len(words) > 4 else "")
    moved = getattr(fit, "moved", None)
    if moved is not None and any(".dof." in k for k in refined):
        out["positions"] = f"furthest {moved:.3f} Å"
    return out


# ======================================================================
#  RIETVELD
# ======================================================================

RIETVELD_PARAMS = (
    Param("plan", "Plan", kind="choice", default="",
          choices=(("", "The boxes below"),
                   ("mccusker_structural", "RietX: McCusker, structural"),
                   ("mccusker_default", "RietX: McCusker, profile"),
                   ("lab_bragg_brentano", "RietX: lab Bragg-Brentano"),
                   ("lab_sample_refine", "RietX: sample on a calibrated "
                                         "instrument")),
          help="What is freed, and in what order.  The boxes below "
               "free in McCusker's order: background and scale, line "
               "positions, cell, widths, then the atoms.  RietX's own "
               "plans ignore the boxes."),
    Param("start", "2θ from", kind="float", default=0.0, minimum=0.0,
          maximum=180.0, decimals=2, suffix=" °",
          help="Where the fit starts (TOPAS start_X).  0 is the start "
               "of the file."),
    Param("finish", "2θ to", kind="float", default=0.0, minimum=0.0,
          maximum=180.0, decimals=2, suffix=" °",
          help="Where it stops (TOPAS finish_X).  0 is the end of the "
               "file."),
    Param("background_terms", "Background terms", kind="int",
          default=8, minimum=1, maximum=30,
          help="Coefficients of the Chebyshev background, TOPAS's bkg "
               "line."),
    Param("background", "Refine the background", kind="bool",
          default=True,
          help="The Chebyshev coefficients.  The scale is always "
               "refined: a Rietveld fit with it held fits nothing."),
    Param("zero", "Refine zero error", kind="bool", default=False,
          help="A constant shift of every line (TOPAS Zero_Error).  "
               "Strongly correlated with specimen displacement."),
    Param("displacement", "Refine specimen displacement", kind="bool",
          default=True,
          help="A shift that falls off as cos θ (TOPAS "
               "Specimen_Displacement).  Not refined for a synchrotron "
               "capillary."),
    Param("cell", "Refine the cell", kind="bool", default=True,
          help="The numbers the space group leaves free, less any held "
               "below."),
    Param("hold", "Hold", kind="text", default="",
          help="Cell numbers held while the rest refine: a b c alpha "
               "beta gamma, separated by commas.  Empty refines every "
               "free one."),
    Param("profile", "Refine the peak shape", kind="bool", default=True,
          help="The instrument's Caglioti U V W and Lorentzian X Y, W "
               "first."),
    Param("size", "Crystallite size broadening", kind="bool",
          default=False,
          help="Lorentzian and Gaussian size terms (TOPAS CS_L, CS_G)."),
    Param("strain", "Strain broadening", kind="bool", default=False,
          help="Lorentzian and Gaussian strain terms (TOPAS Strain_L, "
               "Strain_G)."),
    Param("positions", "Refine atom positions", kind="bool",
          default=True,
          help="Each atom along the directions its site allows: an "
               "atom on a special position stays on it."),
    Param("biso", "Refine displacement parameters", kind="bool",
          default=True,
          help="Biso of each atom (8π²U), or its anisotropic U where "
               "the structure has one."),
    Param("occupancy", "Refine occupancies", kind="bool", default=False,
          help="Off unless the model says a site is partly filled: an "
               "occupancy trades against the displacement parameter "
               "and the scale."),
    Param("preferred_axis", "Preferred orientation", kind="text",
          default="",
          help="The March-Dollase axis as h k l -- 0 0 1 for plates "
               "lying on their c face.  Empty is no texture."),
)


#: The boxes a RietX plan decides for itself: with one chosen they are
#: never read, and a box left live beside it says it is.  The range
#: and the background's order still count, since the plan refines
#: over whatever pattern and background it is handed.
PLAN_DECIDES = ("background", "zero", "displacement", "cell", "hold",
                "profile", "size", "strain", "positions", "biso",
                "occupancy", "preferred_axis")


def rietveld_options(values: dict):
    from xtal.powder.pawley import parse_hold
    from xtal.powder.rietveld import RietveldOptions, parse_axis

    start = float(values.get("start", 0.0) or 0.0)
    finish = float(values.get("finish", 0.0) or 0.0)
    return RietveldOptions(
        start=start or None, finish=finish or None,
        background_terms=int(values.get("background_terms", 8)),
        plan=str(values.get("plan", "") or ""),
        background=bool(values.get("background", True)),
        zero=bool(values.get("zero", False)),
        displacement=bool(values.get("displacement", True)),
        cell=bool(values.get("cell", True)),
        hold_cell=parse_hold(values.get("hold", "")),
        profile=bool(values.get("profile", True)),
        size=bool(values.get("size", False)),
        strain=bool(values.get("strain", False)),
        positions=bool(values.get("positions", True)),
        biso=bool(values.get("biso", True)),
        occupancy=bool(values.get("occupancy", False)),
        preferred_axis=parse_axis(values.get("preferred_axis", "")))


def rietveld_plan_note(values: dict) -> str:
    """What the plan the form names does, stage by stage -- the note
    under the Plan box.  ``""`` without the ``refine`` extra."""
    if not powder.available():
        return ""
    from xtal.powder import bridge

    try:
        options = rietveld_options(values)
    except PowderError:
        # an axis half typed: the note is about the plan, not the axis
        options = rietveld_options({**values, "preferred_axis": ""})
    return bridge.plan_notes(options.plan,
                             options.free(radiation_of(values)))


def run_rietveld(job) -> JobResult:
    """Refine the structure; leave ``fit.xy`` and ``refined.cif``.

    Frames go out through ``job.update`` as the fit runs, no more often
    than ``frame_interval`` seconds (the window's preview interval; not
    a parameter of the fit, and negative for none); the refined
    structure is the result's, for the window to commit.
    """
    from xtal.powder.data import PowderStopped
    from xtal.powder.rietveld import rietveld

    values = job.params
    structure = job.structure
    if structure is None or not structure.sites:
        return JobResult.failure("Rietveld needs a structure: open one "
                                 "and refine it from its window")
    try:
        data = _data_of(values)
        options = rietveld_options(values)
        job.say(f"Rietveld fit of {len(structure.sites)} sites")
        interval = float(values.get("frame_interval", 0.2))
        fit = rietveld(structure, data, radiation_of(values), options,
                       on_frame=job.update if interval >= 0 else None,
                       frame_interval=max(interval, 0.0),
                       cancel=job.cancel, folder=job.path)
    except PowderStopped:
        return JobResult.stopped("Rietveld fit stopped")
    except PowderError as exc:
        return JobResult.failure(str(exc))
    for note in fit.notes:
        job.note(note)
    artifacts = []
    if job.folder is not None:
        from xtal.io import write_cif

        artifacts = [_write_fit(job.file("fit.xy"), fit, "Rietveld fit")]
        path = job.file("refined.cif")
        write_cif(fit.structure, path)
        artifacts.append(path)
        job.note("wrote fit.xy and refined.cif")
    message = (f"Rietveld Rwp {100 * fit.rwp:.2f} %, GoF {fit.gof:.2f}; "
               f"the furthest atom moved {fit.moved:.3f} Å")
    if not fit.converged:
        message += f" ({fit.status}, not converged)"
    return JobResult(message=message, artifacts=tuple(artifacts),
                     report=rietveld_report(fit, data.name), answer=fit)


def rietveld_summary(fit) -> str:
    """The fit's figures, as the result box shows them."""
    names = ("a", "b", "c", "α", "β", "γ")
    cell = "   ".join(
        f"{n} {_with_esd(v, e)}" for n, v, e in
        zip(names, fit.cell, fit.cell_esd, strict=True))
    return (f"Rwp {100 * fit.rwp:.2f} %   Rp {100 * fit.rp:.2f} %   "
            f"Rexp {100 * fit.rexp:.2f} %   GoF {fit.gof:.3f}\n"
            f"{cell}\nthe furthest atom moved {fit.moved:.3f} Å"
            + ("" if fit.converged else f"\n{fit.status}: not converged"))


def rietveld_report(fit, name: str = "") -> Report:
    rows = tuple(Row.of(path, f"{value:.6g}", f"{esd:.2g}" if esd else "")
                 for path, (value, esd) in fit.refined.items())
    return Report(
        title=f"Rietveld, {name}" if name else "Rietveld",
        blocks=(fit_curve(fit, "Rietveld fit", "reflections"),
                Table(title=f"Refined ({len(rows)})",
                      columns=("Parameter", "Value", "esd"), rows=rows)),
        note=rietveld_summary(fit).replace("\n", ".  ")
        + ("  " + "  ".join(fit.notes) if fit.notes else ""))


# ======================================================================
#  AUTOMATIC
# ======================================================================

AUTO_PARAMS = (
    Param("cells", "Pawley the top", kind="int", default=5, minimum=1,
          maximum=20, suffix=" cells",
          help="How many of indexing's leading cells are Pawley fitted."),
    Param("classes", "In each cell's top", kind="int", default=3,
          minimum=1, maximum=10, suffix=" space-group classes",
          help="How many extinction classes of each cell are fitted, "
               "refuted ones left out: a Pawley fit per class, which is "
               "what says whether the absences are real."),
    Param("continue_rietveld", "Continue to Rietveld", kind="bool",
          default=False,
          help="Go on from the ranked table to refine the open "
               "structure, when its cell is a row's to 1 % and 1° and "
               "the pattern refutes none of its space group.  "
               "Unticked, the run stops at the table."),
)


def _prefixed(params, prefix: str, leave=()) -> tuple:
    """A step's parameters under ``prefix``: the automatic run asks the
    Pawley and Rietveld steps' own questions, whose names -- the range,
    the zero -- would otherwise collide with the peak step's."""
    import dataclasses

    return tuple(dataclasses.replace(p, name=prefix + p.name)
                 for p in params if p.name not in leave)


def _unprefixed(values: dict, prefix: str) -> dict:
    return {k[len(prefix):]: v for k, v in values.items()
            if k.startswith(prefix)}


#: Everything ``xtal run pxrd.auto`` takes: the pattern, the peak and
#: index steps' questions as they are, the Pawley and Rietveld steps'
#: under ``pawley_`` and ``rietveld_``, and the run's own.
AUTO_RUN_PARAMS = (
    DATA_PARAMS
    + tuple(p for p in PEAK_PARAMS if p.name != "positions")
    + INDEX_PARAMS + AUTO_PARAMS
    + _prefixed(PAWLEY_PARAMS, "pawley_", ("cell", "space_group",
                                           "hold"))
    + _prefixed(RIETVELD_PARAMS, "rietveld_"))

AUTO_COLUMNS = ("Rank", "Cell", "Lattice", "Space group", "Class", "a",
                "b", "c", "α", "β", "γ", "V (Å³)", "Rwp (%)", "GoF")


def auto_options(values: dict):
    from xtal.powder.auto import AutoOptions
    from xtal.powder.peaks import PeakOptions

    start = float(values.get("start", 0.0) or 0.0)
    finish = float(values.get("finish", 0.0) or 0.0)
    return AutoOptions(
        peaks=PeakOptions(
            start=start or None, finish=finish or None,
            shoulders=bool(values.get("shoulders", True)),
            flag_ghosts=bool(values.get("flag_ghosts", True))),
        index=index_options(values),
        pawley=pawley_options(_unprefixed(values, "pawley_")),
        cells=int(values.get("cells", 5)),
        classes=int(values.get("classes", 3)),
        rietveld=bool(values.get("continue_rietveld", False)),
        rietveld_options=rietveld_options(
            _unprefixed(values, "rietveld_")))


def run_auto(job) -> JobResult:
    """Peaks, index, Pawley the leading cells in their leading classes,
    rank them; leave ``ranked.csv``, and a folder per stage."""
    from xtal.powder.auto import auto

    values = job.params
    structure = job.structure
    try:
        data = _data_of(values)
        options = auto_options(values)
        interval = float(values.get("frame_interval", 0.2))
        result = auto(data, radiation_of(values), options,
                      structure=structure, cancel=job.cancel,
                      say=job.say, folder=job.path,
                      on_frame=job.update if interval >= 0 else None,
                      frame_interval=max(interval, 0.0))
    except PowderError as exc:
        return JobResult.failure(str(exc))
    for note in result.notes:
        job.note(note)
    if result.rietveld_refused:
        job.note(result.rietveld_refused)
    artifacts = []
    if job.folder is not None:
        artifacts.append(_write_ranked(job.file("ranked.csv"), result))
        if result.rietveld is not None:
            from xtal.io import write_cif

            path = job.file("refined.cif")
            write_cif(result.rietveld.structure, path)
            artifacts.append(path)
        job.note("wrote ranked.csv")
    best = result.best
    if best is None:
        message = "no cell was Pawley fitted" if result.cells is None \
            or not result.cells.rows else "every Pawley fit failed"
    else:
        a, b, c = best.fit.cell[:3]
        message = (f"{len(result.rows)} Pawley fits; the best is "
                   f"{best.bravais} {a:.4f} {b:.4f} {c:.4f} Å in "
                   f"{best.fit.space_group}, Rwp "
                   f"{100 * best.rwp:.2f} %")
    if result.rietveld is not None:
        message += (f"; Rietveld Rwp {100 * result.rietveld.rwp:.2f} %, "
                    f"GoF {result.rietveld.gof:.2f}")
    elif result.rietveld_refused:
        message += "; not refined: see the log"
    if result.stopped:
        message = "stopped -- " + message
    return JobResult(message=message, artifacts=tuple(artifacts),
                     report=auto_report(result, data.name),
                     answer=result, cancelled=result.stopped)


def auto_cells(row) -> tuple[str, ...]:
    """A row of the ranked table, as it is written."""
    cell = row.fit.cell if row.fit is not None else row.cell
    a, b, c, alpha, beta, gamma = cell
    rwp = f"{100 * row.rwp:.2f}" if row.fit is not None else "--"
    gof = f"{row.gof:.3f}" if row.fit is not None else row.error
    return (str(row.rank), str(row.cell_rank), row.bravais,
            row.fit.space_group if row.fit is not None
            else row.space_group, row.class_symbol, f"{a:.5f}",
            f"{b:.5f}", f"{c:.5f}", f"{alpha:.3f}", f"{beta:.3f}",
            f"{gamma:.3f}", f"{row.volume:.2f}", rwp, gof)


def auto_report(result, name: str = "") -> Report:
    rows = tuple(Row.of(*auto_cells(row)) for row in result.rows)
    note = ""
    if result.rietveld is not None:
        note = ("Rietveld on the structure, in the cell of row "
                f"{result.rietveld_row.rank}: "
                + rietveld_summary(result.rietveld).replace("\n", ".  "))
    elif result.rietveld_refused:
        note = result.rietveld_refused
    return Report(
        title=f"Automatic, {name}" if name else "Automatic",
        blocks=(Table(title=f"Pawley fits ({len(rows)})",
                      columns=AUTO_COLUMNS, rows=rows,
                      note="Ranked by Rwp; fits within 1 % of each "
                           "other are in indexing's order.  Cell is "
                           "indexing's rank of the cell."),),
        note=note)


def _write_ranked(path, result):
    lines = ["rank,cell_rank,lattice,space_group,class,a,b,c,alpha,"
             "beta,gamma,volume,rwp,gof,folder,error"]
    for row in result.rows:
        texts = auto_cells(row)
        rwp = f"{row.rwp:.5f}" if row.fit is not None else ""
        gof = f"{row.gof:.4f}" if row.fit is not None else ""
        folder = row.folder.name if row.folder is not None else ""
        lines.append(",".join(texts[:12]) + f",{rwp},{gof},{folder},"
                     + row.error.replace(",", ";"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
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
    Action(name="refine_peaks", label="Refine peaks",
           tip="Refine the lines in use together over a Chebyshev "
               "background",
           params=DATA_PARAMS + PEAK_PARAMS + REFINE_PEAK_PARAMS,
           run=run_refine_peaks, needs_structure=False, listed=False,
           check=refine_available),
    Action(name="index", label="Index",
           tip="Find the unit cells that explain the fitted lines",
           params=DATA_PARAMS + PEAK_PARAMS + INDEX_PARAMS,
           run=run_index, needs_structure=False, listed=False,
           check=refine_available),
    Action(name="pawley", label="Pawley",
           tip="Fit a cell and space group to the whole pattern",
           params=DATA_PARAMS + PAWLEY_PARAMS, run=run_pawley,
           needs_structure=False, listed=False,
           check=refine_available),
    Action(name="auto", label="Automatic",
           tip="Peaks, indexing and a Pawley fit of every leading cell "
               "and space group, ranked -- and on into Rietveld when "
               "asked",
           params=AUTO_RUN_PARAMS, run=run_auto,
           needs_structure=False, listed=False,
           check=refine_available),
    Action(name="rietveld", label="Rietveld",
           tip="Refine a structure's atoms against the whole pattern",
           params=DATA_PARAMS + RIETVELD_PARAMS, run=run_rietveld,
           listed=False, check=refine_available),
)

#: What each step's own form shows in the workbench: the pattern and
#: radiation are shown once above the steps, and indexing reads the
#: peaks the Peaks step fitted, so neither is asked again.
#: The peak form leaves out "Fit only at": the workbench places lines
#: by hand and refines them instead, and ``xtal run`` keeps it.
STEP_PARAMS = {"peaks": tuple(p for p in PEAK_PARAMS
                              if p.name != "positions")
               + REFINE_PEAK_PARAMS,
               "index": INDEX_PARAMS,
               "pawley": PAWLEY_PARAMS,
               "rietveld": RIETVELD_PARAMS,
               "auto": AUTO_PARAMS}
