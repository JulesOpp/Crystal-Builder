"""
xtal.modules.scan
=================
The relaxed scan, as something a person can run.

:mod:`xtal.ff.scan` does the work; this decides what it is asked, what
it leaves on disk and what comes back on screen.  Three of those
decisions are worth stating.

**One run, not one per point.**  A twelve by twelve grid of a real
framework is a couple of hours, and the temptation is to make each
point its own job with its own folder and its own worker.  It runs in
a single job on a single thread instead, because the application's
worker teardown has a known race (``docs/TODO.md``, "a finished worker
thread can deadlock the application") and multiplying it by a hundred
and forty-four would make an overnight scan a coin toss.

**Every point is written the moment it finishes.**  Not gathered up
and saved at the end.  Stop has to leave a landscape behind rather
than lose one, and so does a crash.

**The scan returns no structure.**  A module that hands back a
geometry replaces the document it ran on, which is right for an
optimisation and wrong for this: the tab the scan started from is the
crystal the landscape is *of*, and the hundred relaxed points are
files to open, not a replacement for it.
"""

from __future__ import annotations

import csv

import numpy as np

from xtal.core import p1
from xtal.core.lattice import PARAMETER_NAMES
from xtal.ff import coordinates as co
from xtal.ff import scan as driver
from xtal.ff.optimize import METHODS
from xtal.ff.registry import ENGINES
from xtal.modules.job import JobResult
from xtal.modules.registry import MODULES, Action, Module
from xtal.modules.report import Curve, Report, Row, Surface, Table
from xtal.params import Param, ParamError

#: How an axis is written down in a parameter, a command line and the
#: run log.  A dialog builds these rather than inventing a second way
#: of saying the same thing, so that every scan can be re-run from the
#: line printed in its own log.
AXIS_HELP = (
    "A cell parameter (a, b, c, alpha, beta, gamma), 'volume', or an "
    "internal coordinate over groups of P1 atom indices: "
    "'distance 0 5', 'angle 0 1 2', 'torsion 0 1 2 3', "
    "'plane 0,1,2 6,7,8'.  A group of several atoms is their "
    "centroid, and it follows them.")

_INTERNAL = {"distance": 2, "angle": 3, "torsion": 4, "plane": 2}
_KINDS = {"distance": "distance", "angle": "angle",
          "torsion": "torsion", "plane": "plane angle"}


def parse_axis(structure, cell, spec: str):
    """A coordinate from the way it is written down.

    One grammar for the dialog, the command line and the log, so that
    a scan can always be re-run from the line it printed.
    """
    words = str(spec).split()
    if not words:
        raise ParamError("an axis needs a coordinate; " + AXIS_HELP)
    head = words[0].lower()
    if head == "volume":
        return co.CellVolume()
    if head in PARAMETER_NAMES:
        return co.CellParameter(head)
    if head not in _INTERNAL:
        raise ParamError(
            f"{spec!r} is not a coordinate.  " + AXIS_HELP)
    # Space separates the anchors and a comma joins one.  "0 1 2" is
    # three atoms and "0,1,2" is the centroid of three, and nothing
    # but the punctuation can say which was meant.
    groups = []
    for token in words[1:]:
        parts = [part for part in token.split(",") if part]
        for part in parts:
            if not part.isdigit():
                raise ParamError(
                    f"{part!r} is not an atom index in {spec!r}")
        if parts:
            groups.append([int(part) for part in parts])
    wanted = _INTERNAL[head]
    if len(groups) != wanted:
        raise ParamError(
            f"a {head} takes {wanted} anchors, not {len(groups)}: "
            f"{spec!r}")
    return co.internal(structure, cell, _KINDS[head], groups)


def axes_from(job, structure):
    """The one or two axes this job asks for."""
    cell = p1.expand(structure)
    out = []
    for number in (1, 2):
        spec = str(job.param(f"axis{number}", "") or "").strip()
        if not spec:
            continue
        steps = int(job.param(f"axis{number}_steps", 5))
        out.append(driver.Axis.over(
            parse_axis(structure, cell, spec),
            float(job.param(f"axis{number}_start", 0.0)),
            float(job.param(f"axis{number}_stop", 0.0)),
            steps))
    if not out:
        raise ParamError(
            "a scan needs at least one axis.  " + AXIS_HELP)
    return out


PARAMS = (
    Param("engine", "Engine", "choice", default="uff",
          choices=tuple((e.name, e.label) for e in ENGINES),
          help="Which energy engine relaxes each point.  For a "
               "flexible framework a machine-learned potential is "
               "the better choice: UFF4MOF was never fitted to "
               "reproduce a breathing double well."),
    Param("axis1", "First axis", "text", default="volume",
          help=AXIS_HELP),
    Param("axis1_start", "From", "float", default=0.0, decimals=4),
    Param("axis1_stop", "To", "float", default=0.0, decimals=4),
    Param("axis1_steps", "Points", "int", default=9, minimum=1,
          maximum=201),
    Param("axis2", "Second axis", "text", default="",
          help="Leave empty for a one-dimensional scan.  "
               + AXIS_HELP),
    Param("axis2_start", "From", "float", default=0.0, decimals=4),
    Param("axis2_stop", "To", "float", default=0.0, decimals=4),
    Param("axis2_steps", "Points", "int", default=9, minimum=1,
          maximum=201),
    Param("seed", "Starting geometry", "choice", default="previous",
          choices=(("previous", "Carry on from the nearest point"),
                   ("input", "Restart from this structure")),
          help="Carrying the last relaxed geometry into the next "
               "cell is what makes a scan affordable, and it is also "
               "what makes it path-dependent: near a transition the "
               "optimiser stays in the basin it arrived in."),
    Param("direction", "Direction", "choice", default="both",
          choices=(("both", "Both, and report each"),
                   ("forward", "Forwards only"),
                   ("reverse", "Backwards only")),
          help="Walking the grid both ways and drawing both is how "
               "hysteresis shows up instead of hiding in one curve."),
    Param("method", "Optimiser", "choice", default="lbfgs",
          choices=tuple(sorted(METHODS))),
    Param("max_steps", "Steps per point", "int", default=200,
          minimum=1, maximum=100000),
    Param("tolerance", "Force tolerance", "float", default=0.05,
          minimum=1e-6, decimals=4, suffix=" kcal/mol/A"),
)


# ======================================================================
#  THE RUN
# ======================================================================

def run_scan(job) -> JobResult:
    """Relax the structure at every point of the grid."""
    structure = job.structure
    axes = axes_from(job, structure)
    seed = str(job.param("seed", "previous"))
    direction = str(job.param("direction", "both"))
    plan = driver.plan(structure, axes, seed=seed,
                       direction=direction)
    engine = str(job.param("engine", "uff"))

    job.say(f"{plan.n_points} points on {ENGINES.get(engine).label}")
    job.note(plan.describe())

    writer = _Files(job, plan)
    points: list[driver.ScanPoint] = []
    iterator = driver.scan(
        lambda s: ENGINES.build(engine, s), structure, axes,
        seed=seed, direction=direction, cancel=job.cancel,
        method=str(job.param("method", "lbfgs")),
        max_steps=int(job.param("max_steps", 200)),
        force_tolerance=float(job.param("tolerance", 0.05)))
    for point in iterator:
        points.append(point)
        writer.wrote(point, structure)
        job.say(_said(plan, point, len(points)))
    writer.close()

    result = driver.ScanResult(plan, points)
    finished = len(result.finished())
    if job.cancelled and finished < plan.n_points:
        message = (f"Stopped after {finished} of {plan.n_points} "
                   f"points; they are on disk.")
    else:
        message = (f"{finished} of {plan.n_points} points relaxed"
                   + _shortfall(result))
    return JobResult(
        message=message,
        cancelled=bool(job.cancelled),
        report=_report(plan, result, engine, writer.paths),
        artifacts=writer.artifacts)


def _shortfall(result) -> str:
    unconverged = sum(1 for p in result.finished()
                      if not p.converged)
    if not unconverged:
        return ""
    return (f"; {unconverged} did not reach the force tolerance and "
            f"are marked apart")


def _said(plan, point, number) -> str:
    where = ", ".join(
        f"{axis.label} {value:.4g}" for axis, value
        in zip(plan.axes, point.targets, strict=True))
    if not point.finished:
        return f"[{number}/{plan.n_points}] {where}: {point.message}"
    mark = "" if point.converged else " (not converged)"
    return (f"[{number}/{plan.n_points}] {where}: "
            f"{point.energy:.4f} kcal/mol{mark}")


# ======================================================================
#  WHAT IT LEAVES BEHIND
# ======================================================================

class _Files:
    """One CIF and one CSV row per point, written as it finishes.

    Not gathered and saved at the end.  A scan is an overnight job and
    Stop -- or a crash, or a full disk -- has to leave the points that
    did finish where somebody can open them.

    With no workspace there is nowhere to write and that is not an
    error: the answer is a landscape on screen, which is the same
    argument :mod:`xtal.modules.pxrd` makes about its pattern.
    """

    def __init__(self, job, plan):
        self.job = job
        self.plan = plan
        self.artifacts: list = []
        self.paths: dict = {}
        self._csv = None
        self._writer = None
        if job.folder is None:
            return
        self._csv = job.file("scan.csv").open(
            "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._csv)
        self._writer.writerow(
            [*(f"{a.label} target" for a in plan.axes),
             *(f"{a.label} achieved" for a in plan.axes),
             "branch", "energy (kcal/mol)", "converged", "steps",
             "|F|max", "a", "b", "c", "alpha", "beta", "gamma",
             "file"])

    def wrote(self, point, structure) -> None:
        name = self._name(point)
        if self._writer is not None:
            self._writer.writerow([
                *(f"{v:.10g}" for v in point.targets),
                *(f"{v:.10g}" for v in point.achieved),
                point.branch,
                "" if not point.finished else f"{point.energy:.10g}",
                str(bool(point.converged)), point.steps,
                "" if not point.finished else f"{point.max_force:.6g}",
                *(f"{v:.6f}" for v in point.parameters),
                name])
            self._csv.flush()
        if point.finished and self.job.folder is not None:
            self.paths[(point.branch, point.index)] = self._write_cif(
                point, structure, name)

    def _write_cif(self, point, structure, name) -> str:
        from xtal.core.lattice import Lattice
        from xtal.io import FORMATS

        out = structure.copy()
        for site, row in zip(out.sites, point.frac, strict=True):
            site.frac = row
        out.set_lattice(Lattice(point.matrix))
        path = self.job.file(name)
        FORMATS.write(out, path)
        self.artifacts.append(path)
        return str(path)

    def _name(self, point) -> str:
        index = "-".join(f"{i:02d}" for i in point.index)
        return f"{point.branch}-{index}.cif"

    def close(self) -> None:
        if self._csv is not None:
            self._csv.close()
            self.artifacts.insert(0, self.job.file("scan.csv"))
            self.job.note("wrote scan.csv and one CIF per point")


# ======================================================================
#  WHAT COMES BACK
# ======================================================================

def _report(plan, result, engine, paths=None) -> Report:
    blocks: list = [_table(plan, result)]
    if len(plan.axes) == 2:
        blocks.append(_surface(plan, result, paths or {}))
    else:
        blocks.extend(_curves(plan, result))
    return Report(
        title="Relaxed scan",
        blocks=tuple(blocks),
        # The plan is said once, on the block that draws it, rather
        # than here as well: a report is read top to bottom and the
        # same paragraph twice reads as a mistake.
        note=(f"Energies from {ENGINES.get(engine).label}, in "
              f"kcal/mol for the whole cell.  This is a landscape at "
              f"zero kelvin: it is an energy, not a free energy, and "
              f"for a flexible framework the two can order the "
              f"phases differently."))


def _table(plan, result) -> Table:
    columns = [*(f"{a.label} ({a.units})" if a.units else a.label
                 for a in plan.axes),
               "branch", "E (kcal/mol)", "dE", "steps", "|F|max",
               "a", "c", "converged"]
    lowest = result.minimum()
    base = lowest.energy if lowest is not None else 0.0
    rows = []
    for point in result.points:
        energy = ("-" if not point.finished
                  else f"{point.energy:.4f}")
        delta = ("-" if not point.finished
                 else f"{point.energy - base:+.4f}")
        rows.append(Row.of(
            *(f"{v:.4f}" for v in point.achieved),
            point.branch, energy, delta, str(point.steps),
            "-" if not point.finished else f"{point.max_force:.4f}",
            f"{point.parameters[0]:.4f}",
            f"{point.parameters[2]:.4f}",
            "yes" if point.converged else "no"))
    return Table(title="Every point", columns=tuple(columns),
                 rows=tuple(rows),
                 note="The achieved value is reported beside the "
                      "relaxed cell so that a kink in the landscape "
                      "can be told from a jump between basins.")


def _surface(plan, result, paths) -> Surface:
    """The grid, oriented as the block wants it.

    The first axis runs *down* the rows and the second across the
    columns -- ``y`` and ``x`` -- which is the grid's own index order
    and needs no transpose.  Getting that backwards draws a landscape
    that is the right numbers about the wrong axes, and looks
    entirely plausible on a square grid.
    """
    first, second = plan.axes
    branches = plan.directions
    lowest = result.minimum()
    base = lowest.energy if lowest is not None else 0.0
    return Surface(
        title="Energy landscape",
        x=np.array(second.values), y=np.array(first.values),
        z=result.relative(branches[0]),
        x_label=_axis_label(second), y_label=_axis_label(first),
        z_label=f"E - E(min) (kcal/mol), {branches[0]}",
        converged=result.converged(branches[0]),
        paths=tuple(
            tuple(paths.get((branches[0], (row, column)), "")
                  for column in range(len(second)))
            for row in range(len(first))),
        sheets=tuple((name, result.grid(name) - base)
                     for name in branches[1:]),
        note=plan.describe())


def _axis_label(axis) -> str:
    return f"{axis.label} ({axis.units})" if axis.units else axis.label


def _curves(plan, result) -> list[Curve]:
    axis = plan.axes[0]
    lowest = result.minimum()
    base = lowest.energy if lowest is not None else 0.0
    forward = sorted(result.branch(plan.directions[0]),
                     key=lambda p: p.targets[0])
    if not forward:
        return []
    x = np.array([p.targets[0] for p in forward])
    y = np.array([p.energy - base for p in forward])
    series = []
    for name in plan.directions[1:]:
        other = sorted(result.branch(name),
                       key=lambda p: p.targets[0])
        series.append((name, np.array(
            [p.energy - base for p in other])))
    out = [Curve(title="Energy profile", x=x, y=y,
                 x_label=_axis_label(axis),
                 y_label="E - E(min) (kcal/mol)",
                 series=tuple(series), note=plan.describe())]
    pressure = result.pressure(plan.directions[0])
    if pressure is not None:
        volume, values = pressure
        out.append(Curve(
            title="Pressure", x=volume, y=values,
            x_label="volume (A^3)", y_label="P = -dE/dV (GPa)",
            note="Where this rises with volume the cell is not "
                 "mechanically stable, which is where a breathing "
                 "framework's hysteresis comes from."))
    return out


# ======================================================================
#  THE ENTRY
# ======================================================================

SCAN = Module(
    name="scan",
    label="Energy scan",
    description="Walk one or two coordinates and relax everything "
                "else at each point, to map the energy landscape of "
                "a flexible structure.  An axis is a lattice "
                "parameter, the cell volume, or an internal "
                "coordinate -- a distance, an angle, a dihedral, or "
                "the angle between two planes -- and it is held by a "
                "constraint rather than by freezing the atoms that "
                "define it.  Every point is left behind as a "
                "structure to open.",
    order=60,
    actions=(
        Action(name="run", label="Relaxed scan...",
               tip="Map the energy landscape over one or two "
                   "coordinates",
               kind="scan",
               params=PARAMS,
               run=run_scan),
    ),
)


def register(registry=MODULES) -> Module:
    return registry.register(SCAN)
