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
from xtal.modules.report import (
    REPORT_NAME,
    Curve,
    Report,
    Row,
    Surface,
    Table,
)
from xtal.modules.report import save as save_report
from xtal.params import Param, ParamError

#: How an axis is written down in a parameter, a command line and the
#: run log.  A dialog builds these rather than inventing a second way
#: of saying the same thing, so that every scan can be re-run from the
#: line printed in its own log.
AXIS_HELP = (
    "A cell parameter (a, b, c, alpha, beta, gamma), 'volume', or an "
    "internal coordinate over P1 atom indices: "
    "'distance 0, 5', 'angle 0, 1, 2', 'torsion 0, 1, 2, 3', "
    "'plane 0+1+2, 6+7+8'.  Atoms joined by '+' are their "
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
    wanted = _INTERNAL[head]
    text = " ".join(words[1:])
    groups = read_anchors(text, spec)
    if len(groups) != wanted and "+" not in text:
        # The first grammar: space between anchors, comma inside one.
        # Every scan run before '+' existed printed its axis that way,
        # and a log line has to stay something that can be re-run.
        older = read_anchors(text, spec, legacy=True)
        if len(older) == wanted:
            groups = older
    if len(groups) != wanted:
        raise ParamError(
            f"a {head} takes {wanted} anchors, not {len(groups)}: "
            f"{spec!r}")
    return co.internal(structure, cell, _KINDS[head], groups)


def read_anchors(text: str, spec: str, legacy: bool = False):
    """Groups of atom indices, one per anchor.

    Commas or spaces separate the anchors and '+' joins atoms into
    one, so "32, 33" -- what a person writes, and what Add the
    selection writes -- is two atoms.  It used to be one centroid of
    two, because a comma was the joiner, and a distance over the two
    chlorides somebody had selected was refused for having one
    anchor.
    """
    tokens = (text.split() if legacy
              else text.replace(",", " ").split())
    joiner = "," if legacy else "+"
    groups = []
    for token in tokens:
        parts = [part.strip() for part in token.split(joiner)]
        parts = [part for part in parts if part]
        for part in parts:
            if not part.isdigit():
                raise ParamError(
                    f"{part!r} is not an atom index in {spec!r}")
        if parts:
            groups.append([int(part) for part in parts])
    return groups


def spell_anchors(groups) -> str:
    """The text :func:`parse_axis` reads back as these anchors."""
    return ", ".join("+".join(str(int(a)) for a in group)
                     for group in groups)


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
    Param("method", "Optimiser", "choice", default="smart",
          choices=tuple(sorted(METHODS)),
          help="Smart descends steeply at first and changes rule as "
               "the forces fall, which is what a scan wants: every "
               "point after the first starts near a minimum, but the "
               "first one may not."),
    Param("max_steps", "Steps per point", "int", default=500,
          minimum=1, maximum=100000,
          help="A point that stops at the limit is reported as not "
               "converged and drawn apart, so this is a ceiling "
               "rather than a target."),
    Param("tolerance", "Force tolerance", "float", default=0.05,
          minimum=1e-6, decimals=4, suffix=" kcal/mol/A"),
    Param("pre_engine", "Pre-relax with", "choice", default="",
          choices=(("", "Nothing"),
                   *((e.name, e.label) for e in ENGINES)),
          help="A cheaper engine run at every point before the one "
               "the landscape is of -- UFF4MOF ahead of MACE, say.  "
               "A volume step moves every atom with the cell, and "
               "this spends the long walk back at the cheap price.  "
               "Only the main engine's energy is reported."),
    Param("pre_max_steps", "Pre-relaxation steps", "int",
          default=500, minimum=1, maximum=100000),
    Param("pre_tolerance", "Pre-relaxation tolerance", "float",
          default=0.5, minimum=1e-6, decimals=4,
          suffix=" kcal/mol/A",
          help="Loose on purpose: the cheap engine's minimum is not "
               "the one wanted, so converging to it tightly buys "
               "nothing."),
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

    settings = engine_settings(job, engine)
    prerelax, pre_said = _prerelax(job)

    job.say(f"{plan.n_points} points on {_engine_said(engine, settings)}"
            + (f", each pre-relaxed with {pre_said}" if pre_said
               else ""))
    job.note(plan.describe())

    writer = _Files(job, plan)
    points: list[driver.ScanPoint] = []
    iterator = driver.scan(
        lambda s: ENGINES.build(engine, s, **settings), structure, axes,
        seed=seed, direction=direction, cancel=job.cancel,
        prerelax=prerelax,
        method=str(job.param("method", "smart")),
        max_steps=int(job.param("max_steps", 500)),
        force_tolerance=float(job.param("tolerance", 0.05)))
    for point in iterator:
        points.append(point)
        writer.wrote(point, structure)
        job.say(_said(plan, point, len(points)))
    writer.close()

    result = driver.ScanResult(plan, points)
    report = _report(plan, result, engine, writer.paths, settings,
                     pre_said)
    writer.keep(report)
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
        report=report,
        artifacts=writer.artifacts)


def _prerelax(job):
    """The :class:`driver.Prerelax` this job asks for, and how to
    name it in a log line -- ``(None, "")`` when it asks for none."""
    engine = str(job.param("pre_engine", "") or "")
    if not engine:
        return None, ""
    settings = engine_settings(job, engine, key="pre_engine_options")
    steps = int(job.param("pre_max_steps", 500))
    prerelax = driver.Prerelax(
        build=lambda s: ENGINES.build(engine, s, **settings),
        max_steps=steps,
        force_tolerance=float(job.param("pre_tolerance", 0.5)))
    return prerelax, (f"{_engine_said(engine, settings)} for up to "
                      f"{steps} steps")


def engine_settings(job, engine: str,
                    key: str = "engine_options") -> dict:
    """The engine's own options, coerced, defaults filled in.

    They arrive under one key rather than spread through the job's
    parameters, because a scan already has ten of its own and an
    engine has up to nine more -- and because which nine depends on
    the engine, which a flat parameter list cannot say.  Coerced
    through the registry so that a command line handing in strings
    gets the same answer a dialog does.
    """
    given = job.param(key, None) or {}
    entry = ENGINES.get(engine)
    values = dict(entry.defaults())
    values.update({k: v for k, v in dict(given).items()
                   if k in values})
    return entry.coerce(values)


def _engine_said(engine: str, settings) -> str:
    """The engine and the one setting worth naming in a log line."""
    label = ENGINES.get(engine).label
    for key in ("parameter_set", "model", "method"):
        if key in settings and settings[key]:
            return f"{label} ({settings[key]})"
    return label


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
    pre = (f" after {point.pre_steps} pre-relaxation steps"
           if point.pre_steps else "")
    if point.pre_skipped:
        pre = f"; pre-relaxation skipped: {point.pre_skipped}"
    return (f"[{number}/{plan.n_points}] {where}: "
            f"{point.energy:.4f} kcal/mol{mark}{pre}")


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
             "pre-relaxation steps", "|F|max",
             "a", "b", "c", "alpha", "beta", "gamma", "file"])

    def wrote(self, point, structure) -> None:
        name = self._name(point)
        if self._writer is not None:
            self._writer.writerow([
                *(f"{v:.10g}" for v in point.targets),
                *(f"{v:.10g}" for v in point.achieved),
                point.branch,
                "" if not point.finished else f"{point.energy:.10g}",
                str(bool(point.converged)), point.steps,
                point.pre_steps,
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
        # With the bonds the scan held, not only the ones the user
        # drew: opened on its own, a stretched point would otherwise
        # be perceived again at the stretched geometry, and the
        # crystal behind a cell of the landscape would not be the
        # molecule its energy was scored over.
        FORMATS.write(out, path, perception=True)
        self.artifacts.append(path)
        return str(path)

    def _name(self, point) -> str:
        index = "-".join(f"{i:02d}" for i in point.index)
        return f"{point.branch}-{index}.cif"

    def keep(self, report) -> None:
        """Write the report beside the points, to be opened again.

        Double-clicking it in the workspace puts the landscape back in
        the Results panel -- after the panel was closed, or the
        application was, which for an overnight run is the usual
        case rather than the odd one.
        """
        if self.job.folder is None:
            return
        path = self.job.file(REPORT_NAME)
        save_report(report, path)
        self.artifacts.insert(0, path)

    def close(self) -> None:
        if self._csv is not None:
            self._csv.close()
            self.artifacts.insert(0, self.job.file("scan.csv"))
            self.job.note("wrote scan.csv and one CIF per point")


# ======================================================================
#  WHAT COMES BACK
# ======================================================================

def _report(plan, result, engine, paths=None, settings=None,
            pre_said="") -> Report:
    blocks: list = [_table(plan, result)]
    if len(plan.axes) == 2:
        blocks.append(_surface(plan, result, paths or {}))
    else:
        blocks.extend(_curves(plan, result, paths))
    return Report(
        title="Relaxed scan",
        blocks=tuple(blocks),
        # The plan is said once, on the block that draws it, rather
        # than here as well: a report is read top to bottom and the
        # same paragraph twice reads as a mistake.
        note=(f"Energies from "
              f"{_engine_said(engine, settings or {})}, in kcal/mol "
              f"for the whole cell"
              + (f"; each point was first pre-relaxed with "
                 f"{pre_said}, whose energies are not shown"
                 if pre_said else "")
              + ".  This is a landscape at zero "
              "kelvin: it is an energy, not a free energy, and for "
              "a flexible framework the two can order the phases "
              "differently."))


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
    base = result.base()
    both = len(branches) > 1

    # With two branches the sheet shown *first* is the lower of them,
    # not the forward one.  Neither branch alone is the landscape --
    # each is the energy of whichever basin that direction of travel
    # arrived in -- and drawing one of them means half the picture is
    # an artefact of the direction.  The branches stay, and so does
    # their difference, because that difference is the hysteresis and
    # is the whole point of walking both ways; but it is the second
    # question, and the lower envelope is the first.
    primary = result.best() - base if both else \
        result.relative(branches[0])
    label = "lowest of both" if both else branches[0]
    sheets = []
    if both:
        sheets.extend((name, result.grid(name) - base)
                      for name in branches)
        difference = result.hysteresis()
        if difference is not None:
            sheets.append(
                (f"{branches[0]} - {branches[1]}", difference))

    chosen = result.best_points() if both else None
    converged = (_converged_of(chosen, plan.shape) if both
                 else result.converged(branches[0]))
    return Surface(
        title="Energy landscape",
        x=np.array(second.values), y=np.array(first.values),
        z=primary,
        x_label=_axis_label(second), y_label=_axis_label(first),
        z_label=f"E - E(min) (kcal/mol), {label}",
        converged=converged,
        paths=tuple(
            tuple(_path_for(paths, chosen, branches[0], (row, column))
                  for column in range(len(second)))
            for row in range(len(first))),
        sheets=tuple(sheets),
        note=plan.describe())


def _converged_of(chosen, shape) -> np.ndarray:
    out = np.zeros(shape, dtype=bool)
    for index, point in chosen.items():
        out[index] = point.converged
    return out


def _path_for(paths, chosen, fallback, index) -> str:
    """The file behind a cell -- of whichever branch is being drawn.

    With the lower envelope on screen, clicking a cell has to open the
    structure that *gave* that energy.  Opening the forward one
    regardless would show a crystal whose energy is not the number
    under the cursor, which is the kind of quiet mismatch the rest of
    this feature is built to avoid.
    """
    if chosen is not None and index in chosen:
        return paths.get((chosen[index].branch, index), "")
    return paths.get((fallback, index), "")


def _axis_label(axis) -> str:
    return f"{axis.label} ({axis.units})" if axis.units else axis.label


def _curves(plan, result, paths=None) -> list[Curve]:
    axis = plan.axes[0]
    lowest = result.minimum()
    base = lowest.energy if lowest is not None else 0.0
    paths = paths or {}
    branches = [sorted(result.branch(name), key=lambda p: p.targets[0])
                for name in plan.directions]
    forward = branches[0]
    if not forward:
        return []
    x = np.array([p.targets[0] for p in forward])
    y = np.array([p.energy - base for p in forward])
    series = tuple(
        (name, np.array([p.energy - base for p in points]))
        for name, points in zip(plan.directions[1:], branches[1:],
                                strict=True))
    out = [Curve(title="Energy profile", x=x, y=y,
                 x_label=_axis_label(axis),
                 y_label="E - E(min) (kcal/mol)",
                 series=series, note=plan.describe(),
                 normalised=False,
                 paths=tuple(
                     tuple(paths.get((p.branch, p.index), "")
                           for p in points)
                     for points in branches))]
    pressure = result.pressure(plan.directions[0])
    if pressure is not None:
        volume, values = pressure
        out.append(Curve(
            title="Pressure", x=volume, y=values,
            x_label="volume (A^3)", y_label="P = -dE/dV (GPa)",
            normalised=False,
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
               kind="scan", dialog="scan",
               params=PARAMS,
               run=run_scan),
    ),
)


def register(registry=MODULES) -> Module:
    return registry.register(SCAN)
