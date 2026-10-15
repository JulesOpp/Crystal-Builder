"""
xtal.modules.qha
================
Energy scan ▸ Quasi-harmonic free energy...: the bulk modulus's
volume scan, with the vibrations taken at every converged volume and
F(V, T) minimised at every temperature (:mod:`xtal.ff.qha`).

**A point is on disk before the next starts.**  Each volume's CIF and
``scan.csv`` row are the scan's own; its frequencies (``<point>-
frequencies.txt``, with their weights, which is all F needs) and its
row of ``qha.csv`` are written the moment its Hessian is, and
``free_energy.dat`` -- F at every volume and temperature so far -- is
rewritten after it.  A night's run that is stopped, or crashes, at the
seventh volume leaves six that can be summed again.

**The Hessian is the thermochemistry's.**  The same choice of method
(:func:`xtal.modules.thermo.choose_method`), the same size refusals
before anything runs, and a crystal always: a volume scan of a
molecule in a box is not a thing.  Unlike a single thermochemistry
there is no ``forces.npz``: a point's displacements are a means, and
its frequencies are what is kept.

**It returns no structure**, as a scan does: the tab is the crystal
the free energy is *of*, and every volume is a file to open.
"""

from __future__ import annotations

import csv
from dataclasses import replace

import numpy as np

from xtal.core.lattice import Lattice
from xtal.ff import phonons, qha, vibrations
from xtal.ff import scan as driver
from xtal.ff.api import CalculatorError, CalculatorStopped
from xtal.ff.registry import ENGINES
from xtal.io import atomic
from xtal.modules import thermo as thermo_run
from xtal.modules.job import JobResult
from xtal.modules.report import (
    REPORT_NAME,
    Curve,
    Report,
    Row,
    Table,
)
from xtal.modules.report import save as save_report
from xtal.params import ParamError

#: How many temperatures the minima table lists; ``free_energy.dat``
#: and ``minima.dat`` have every one.
TABLE_ROWS = 9
#: How many temperatures F(V) is drawn at.
CURVE_TEMPERATURES = 6


def run_qha(job) -> JobResult:
    from xtal.modules import scan as scan_run

    engine = str(job.param("engine", "uff"))
    settings = scan_run.engine_settings(job, engine)
    said = scan_run._engine_said(engine, settings)
    asked = str(job.param("hessian", "auto"))
    try:
        method, why = thermo_run.choose_method(asked, "crystal",
                                               engine=engine)
        if method == "phonopy":
            thermo_run._check_supercell(job.structure,
                                        job.param("supercell", "auto"))
        if method == "analytic":
            thermo_run.check_analytic(job.structure)
    except thermo_run.SizeRefused as error:
        return JobResult(message=str(error), ok=False,
                         warnings=(("SIZE_LIMIT", str(error)),))
    except ParamError as error:
        return JobResult.failure(str(error))
    if why:
        job.say(why)

    prepared = scan_run.volume_window(job)
    if isinstance(prepared, JobResult):
        return prepared
    structure, params = prepared
    job = replace(job, params=params)
    # One supercell and one q-mesh for every volume: ``auto`` asked
    # of each volume's own cell gave MIL-53 2x2x1 at its open pore and
    # 2x2x2 a few percent smaller, and the step that put in F(V) was
    # the sampling's, not the crystal's.  The supercell is the relaxed
    # start's; the mesh is the first volume's, held from then on.
    sampling = {}
    if method == "phonopy":
        try:
            sampling["supercell"] = thermo_run._check_supercell(
                structure, job.param("supercell", "auto"))
        except thermo_run.SizeRefused as error:
            return JobResult(message=str(error), ok=False,
                             warnings=(("SIZE_LIMIT", str(error)),))
        sampling["mesh"] = float(job.param("mesh", phonons.MESH))
    axes = scan_run.axes_from(job, structure)
    seed = str(job.param("seed", "previous"))
    direction = str(job.param("direction", "forward"))
    plan = driver.plan(structure, axes, seed=seed, direction=direction)
    temperatures = thermo_run.temperatures(job)
    prerelax, pre_said = scan_run._prerelax(job)
    job.say(f"{plan.n_points} volumes on {said}, each relaxed and its "
            f"Hessian taken ({_method_said(method)})"
            + (f", pre-relaxed with {pre_said}" if pre_said else ""))

    writer = scan_run._Files(job, plan)
    kept = _Kept(job, temperatures)
    best: dict = {}
    stopped = ""
    iterator = driver.scan(
        lambda s: ENGINES.build(engine, s, **settings), structure, axes,
        seed=seed, direction=direction, cancel=job.cancel,
        prerelax=prerelax, method=str(job.param("method", "smart")),
        max_steps=int(job.param("max_steps", 500)),
        force_tolerance=float(job.param("tolerance", 0.01)))
    for number, point in enumerate(iterator, start=1):
        writer.wrote(point, structure)
        if not point.finished:
            volume = qha.Volume(point.volume, np.nan,
                                note=point.message or "did not finish")
        else:
            try:
                found = _vibrations(job, _at(structure, point), method,
                                    engine, settings, sampling)
            except CalculatorStopped:
                stopped = (f"Stopped during the Hessian of volume "
                           f"{number}; the {len(kept.points)} before it "
                           f"are on disk.")
                break
            except (CalculatorError, ValueError) as error:
                # A hole with its reason, as the scan makes of a
                # relaxation that fails: one volume is not the run.
                found = None
                volume = qha.Volume(point.volume, point.energy,
                                    note=f"no Hessian: {error}")
            if found is not None:
                if found.q_mesh is not None and \
                        np.ndim(sampling.get("mesh")) == 0:
                    sampling["mesh"] = found.q_mesh
                frequencies, weights = found.sampled()
                volume = qha.judge(point.volume, point.energy,
                                   frequencies, weights,
                                   converged=point.converged)
        kept.add(point, volume, writer)
        job.say(f"volume {number} of {plan.n_points}: "
                f"{point.volume:.2f} A^3, "
                + (f"hole ({volume.note})" if volume.hole else
                   f"E {volume.energy:.4f} kcal/mol"))
        previous = best.get(point.index)
        if previous is None or _lower(volume, previous):
            best[point.index] = volume
    writer.close()
    kept.close()

    points = [best[i] for i in sorted(best)]
    result = qha.analyse(points, temperatures,
                         pressure=float(job.param("pressure", 0.0)))
    for hole in result.holes:
        job.note(f"hole at {hole.volume:.2f} A^3: {hole.note}")
    report = _report(result, said, _method_said(method, sampling))
    files = {"free_energy.dat": _free_dat(result),
             "minima.dat": _minima_dat(result)}
    artifacts = list(writer.artifacts) + kept.artifacts
    if job.folder is not None:
        for name, text in files.items():
            atomic.write_text(job.file(name), text, encoding="utf-8")
            artifacts.append(job.file(name))
        save_report(report, job.file(REPORT_NAME))
        artifacts.insert(0, job.file(REPORT_NAME))
    warnings = []
    if result.holes:
        warnings.append((
            "IMAGINARY_MODES" if any("imaginary" in h.note
                                     for h in result.holes)
            else "NOT_CONVERGED",
            f"{len(result.holes)} of {len(points)} volumes are holes "
            f"and left out of every fit: "
            + "; ".join(f"{h.volume:.1f} A^3 {h.note}"
                        for h in result.holes)))
    return JobResult(message=stopped or _message(result),
                     cancelled=bool(stopped) or bool(job.cancelled),
                     report=report, artifacts=tuple(artifacts),
                     answer=result, warnings=tuple(warnings))


def _lower(volume, previous) -> bool:
    """Walked both ways, a volume is the branch that is lower -- and
    one that can be summed beats a hole whatever its energy."""
    if previous.hole != volume.hole:
        return previous.hole
    if volume.hole:
        return False
    return volume.energy < previous.energy


def _at(structure, point):
    """The structure at a relaxed point, through ``set_frac`` so the
    expansion the Hessian reads is the relaxed one."""
    out = structure.copy()
    out.set_lattice(Lattice(point.matrix))
    for index, row in enumerate(point.frac):
        out.set_frac(index, row)
    return out


def _vibrations(job, structure, method, engine, settings,
                sampling=None):
    delta = float(job.param("delta", vibrations.DELTA))
    sampling = sampling or {}
    if method == "phonopy":
        return phonons.phonopy_vibrations(
            lambda big: ENGINES.build(engine, big, **settings),
            structure, supercell=sampling.get("supercell", "auto"),
            mesh=sampling.get("mesh", phonons.MESH), delta=delta,
            cancel=job.cancel)
    calculator = ENGINES.build(engine, structure, **settings)
    return vibrations.hessian(calculator, structure, kind="crystal",
                              delta=delta, cancel=job.cancel,
                              analytic=method == "analytic")


def _method_said(method, sampling=None) -> str:
    if method == "phonopy" and sampling and "supercell" in sampling:
        said = "phonopy, supercell " + "x".join(
            str(v) for v in sampling["supercell"])
        if np.ndim(sampling.get("mesh")) == 1:
            said += ", q-mesh " + "x".join(
                str(v) for v in sampling["mesh"])
        return said + " at every volume"
    return {"phonopy": "phonopy, supercell and q-mesh",
            "analytic": "analytic, Gamma only",
            "gamma": "Gamma only, finite differences"}[method]


class _Kept:
    """``qha.csv`` and each volume's frequencies, written as each
    volume finishes, and ``free_energy.dat`` rewritten after it."""

    def __init__(self, job, temperatures):
        self.job = job
        self.temperatures = temperatures
        self.points: list = []
        self.artifacts: list = []
        self._csv = None
        if job.folder is None:
            return
        self._csv = job.file("qha.csv").open("w", newline="",
                                             encoding="utf-8")
        self._writer = csv.writer(self._csv)
        self._writer.writerow(["branch", "index", "volume (A^3)",
                               "energy (kcal/mol)", "converged",
                               "hole", "frequencies"])
        self._csv.flush()

    def add(self, point, volume, writer) -> None:
        self.points.append(volume)
        if self._csv is None:
            return
        name = writer._name(point).removesuffix(".cif")
        listed = ""
        if volume.frequencies is not None:
            listed = f"{name}-frequencies.txt"
            rows = "\n".join(f"{f:.6f} {w:.10g}" for f, w in
                             zip(volume.frequencies, volume.weights,
                                 strict=True))
            atomic.write_text(
                self.job.file(listed),
                "# frequency (cm-1, negative imaginary), weight\n"
                + rows + "\n", encoding="utf-8")
            self.artifacts.append(self.job.file(listed))
        self._writer.writerow([
            point.branch, "-".join(str(i) for i in point.index),
            f"{volume.volume:.6f}",
            "" if not np.isfinite(volume.energy)
            else f"{volume.energy:.10g}",
            str(bool(point.converged)), volume.note, listed])
        self._csv.flush()
        partial = qha.QHAResult(
            tuple(self.points), np.asarray(self.temperatures),
            qha.free_energies(self.points, self.temperatures), ())
        atomic.write_text(self.job.file("free_energy.dat"),
                          _free_dat(partial), encoding="utf-8")

    def close(self) -> None:
        if self._csv is not None:
            self._csv.close()
            self.artifacts.insert(0, self.job.file("qha.csv"))


# ======================================================================
#  WHAT COMES BACK
# ======================================================================

def _free_dat(result) -> str:
    """F (kcal/mol per cell) with a volume a row and a temperature a
    column; a hole's row is NaN."""
    head = "# V (A^3)  F(V, T) kcal/mol per cell at T (K) = " + " ".join(
        f"{t:g}" for t in result.temperatures)
    rows = [f"{v:.6f} " + " ".join(f"{f:.6f}" for f in row)
            for v, row in zip(result.volumes, result.free, strict=True)]
    return "\n".join([head, *rows]) + "\n"


def _minima_dat(result) -> str:
    lines = ["# well  T (K)  V (A^3)  G (kcal/mol per cell)  B (GPa)  "
             "alpha (1/K)"]
    for number, well in enumerate(result.wells, start=1):
        alpha = well.expansion
        for j, t in enumerate(result.temperatures):
            m = well.minima[j]
            if m is None:
                lines.append(f"{number} {t:g} nan nan nan nan")
            else:
                lines.append(f"{number} {t:g} {m.volume:.6f} {m.g:.6f} "
                             f"{m.b:.4f} {alpha[j]:.6g}")
    return "\n".join(lines) + "\n"


def _shown(temperatures, count) -> list[int]:
    n = len(temperatures)
    if n <= count:
        return list(range(n))
    return sorted({int(round(i)) for i in np.linspace(0, n - 1, count)})


def _report(result, said, how) -> Report:
    blocks: list = [_volumes_table(result)]
    for number, well in enumerate(result.wells, start=1):
        blocks.append(_well_table(result, well, number))
    if len(result.wells) > 1:
        blocks.append(_crossing_table(result))
    blocks += _curves(result)
    return Report(title=f"Quasi-harmonic free energy ({said}, {how})",
                  blocks=tuple(blocks))


def _volumes_table(result) -> Table:
    t = result.temperatures
    j = int(np.argmin(np.abs(t - 298.15)))
    rows = []
    for point, f in zip(result.points, result.free[:, j], strict=True):
        rows.append(Row.of(
            f"{point.volume:.2f}",
            "--" if not np.isfinite(point.energy)
            else f"{point.energy:.4f}",
            "--" if not np.isfinite(f) else f"{f:.4f}",
            point.note or "summed"))
    return Table("Volumes", tuple(rows),
                 columns=("V (A^3)", "E (kcal/mol)",
                          f"F({t[j]:g} K)", "Status"),
                 note="Per cell.  A hole -- unconverged, or with "
                      "imaginary modes -- is left out of every fit "
                      "rather than counted as a free energy.",
                 warning="" if not result.holes else
                 f"{len(result.holes)} of {len(result.points)} volumes "
                 f"are holes: the fits are over the rest, and a well "
                 f"short of volumes is fitted over fewer points than "
                 f"it was scanned with.")


def _well_table(result, well, number) -> Table:
    alpha = well.expansion
    rows = []
    for j in _shown(result.temperatures, TABLE_ROWS):
        m = well.minima[j]
        t = result.temperatures[j]
        if m is None:
            rows.append(Row.of(f"{t:g}", "--", "--", "--", "--",
                               note=well.reasons[j]))
            continue
        rows.append(Row.of(
            f"{t:g}", f"{m.volume:.3f}", f"{m.g:.4f}", f"{m.b:.2f}",
            "--" if not np.isfinite(alpha[j]) else f"{alpha[j]:.3e}"))
    lo = result.volumes[well.indices].min()
    hi = result.volumes[well.indices].max()
    title = "Minimum" if len(result.wells) == 1 else \
        f"Well {number} ({lo:.0f}-{hi:.0f} A^3)"
    pressure = (f" at {result.pressure:g} GPa"
                if result.pressure else " at zero pressure")
    return Table(title, tuple(rows),
                 columns=("T (K)", "V (A^3)", "G (kcal/mol)", "B (GPa)",
                          "alpha (1/K)"),
                 note=f"{well.form} through F(V) at each temperature, "
                      f"over {len(well.indices)} volumes; G = F + pV"
                      f"{pressure}, per cell.  Every temperature is in "
                      f"minima.dat.")


def _crossing_table(result) -> Table:
    rows = [Row.of(f"{c.temperature:.0f}", f"well {c.below + 1}",
                   f"well {c.above + 1}")
            for c in result.crossings]
    note = ("Where two wells' G are equal: the transition temperature "
            "in this approximation.")
    if not rows:
        note = ("The wells' G do not cross between "
                f"{result.temperatures[0]:g} and "
                f"{result.temperatures[-1]:g} K.")
    return Table("Crossings", tuple(rows),
                 columns=("T (K)", "Lower below", "Lower above"),
                 note=note)


def _curves(result) -> list[Curve]:
    t = result.temperatures
    v = result.volumes
    order = np.argsort(v)
    shown = _shown(t, CURVE_TEMPERATURES)
    free = result.free[order]
    base = np.nanmin(free[:, shown[0]]) if np.isfinite(
        free[:, shown[0]]).any() else 0.0
    traces = [(f"{t[j]:g} K", free[:, j] - base) for j in shown]
    out = [Curve(title="F(V) at several temperatures (kcal/mol per "
                       "cell)",
                 x=v[order], y=traces[0][1], x_label="V (A^3)",
                 y_label=traces[0][0], series=tuple(traces[1:]),
                 normalised=False,
                 note="Measured from the lowest F at the first "
                      "temperature; a hole is a gap.")]
    if result.wells:
        named = [(f"well {n}" if len(result.wells) > 1 else "V",
                  w) for n, w in enumerate(result.wells, start=1)]
        out.append(Curve(title="V(T) (A^3)", x=t,
                         y=named[0][1].series("volume"),
                         x_label="T (K)", y_label=named[0][0],
                         series=tuple((n, w.series("volume"))
                                      for n, w in named[1:]),
                         normalised=False))
        g0 = np.nanmin([np.nanmin(w.series("g")) for _, w in named
                        if np.isfinite(w.series("g")).any()] or [0.0])
        out.append(Curve(title="G(T) (kcal/mol per cell)", x=t,
                         y=named[0][1].series("g") - g0,
                         x_label="T (K)", y_label=named[0][0],
                         series=tuple((n, w.series("g") - g0)
                                      for n, w in named[1:]),
                         normalised=False,
                         note="Measured from the lowest G of any "
                              "well."))
    return out


def _message(result) -> str:
    summed = len(result.points) - len(result.holes)
    head = f"{summed} of {len(result.points)} volumes summed"
    if not result.wells:
        return head + "; nothing to fit"
    if result.crossings:
        c = result.crossings[0]
        return (head + f"; well {c.above + 1} is lower above "
                f"{c.temperature:.0f} K")
    well = result.wells[0]
    v = well.series("volume")
    finite = np.flatnonzero(np.isfinite(v))
    if not len(finite):
        return head + "; " + (well.reasons[0] or "no fit")
    first, last = finite[0], finite[-1]
    t = result.temperatures
    return (head + f"; V {v[first]:.2f} A^3 at {t[first]:g} K to "
            f"{v[last]:.2f} at {t[last]:g} K")
