"""
xtal.ff.scan
============
A relaxed scan: set a coordinate, relax everything else, move on.

The energy landscape of a flexible framework is the case this was
written for -- what does a breathing MOF cost as its cell opens -- but
nothing here knows that.  An axis is a :class:`xtal.ff.coordinates.
Coordinate` and a list of values, and the same driver walks a cell
parameter, a volume, a bond, an angle, a dihedral or the angle between
two planes.

Three decisions are worth knowing before reading the code.

**The cell is held exactly when it can be.**  A hexagonal group leaves
a and c free and nothing else, so scanning both fixes the cell
completely: the point relaxes with no cell variables at all, which is
exact and costs one energy evaluation a step instead of thirteen on an
engine with no analytic stress.  Scanning fewer than all the free
parameters leaves the rest to relax, which is what
:class:`xtal.ff.optimize.CellFreedom` is for.

**A point starts from its neighbour, and that is visible.**  Carrying
the last relaxed geometry into the next cell is what makes a scan
affordable and it is also what makes it path-dependent: near a
spinodal the optimiser stays in the basin it arrived in.  Measured on
zinc acetate under UFF, the same target cell reached from a relaxed
neighbour and from the original input differed by 2.6 kcal/mol.  So
the seed is a parameter, both directions are walked by default, and
the two branches are reported side by side rather than averaged into
one curve.  The hysteresis is the interesting part.

**A point that did not finish is not a number.**  Its energy is NaN,
it does not seed its neighbour, and whatever draws the landscape has
to decide what to do about it rather than plotting a hole as a zero.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass, field

import numpy as np

from xtal.core import bonding
from xtal.core.lattice import PARAMETER_NAMES, Lattice
from xtal.ff import coordinates as co
from xtal.ff import optimize
from xtal.ff.api import CalculatorError, CalculatorStopped
from xtal.ff.constraints import Holonomic
from xtal.ff.optimize import CellFreedom

#: Seed policies.  "previous" carries the nearest relaxed neighbour
#: into the next point; "input" restarts from the structure the scan
#: was given, every time.
SEEDS = ("previous", "input")

#: Which way the grid is walked.  "both" walks it forwards and then
#: backwards and keeps the two as separate branches.
DIRECTIONS = ("forward", "reverse", "both")


class ScanError(CalculatorError):
    """A scan that cannot be set up as asked."""


@dataclass(frozen=True)
class Axis:
    """One coordinate and the values it is stepped through."""

    coordinate: co.Coordinate
    values: tuple[float, ...]

    @classmethod
    def over(cls, coordinate, start: float, stop: float,
             steps: int) -> Axis:
        """``steps`` points from ``start`` to ``stop``, inclusive."""
        if steps < 1:
            raise ScanError("an axis needs at least one point")
        if steps == 1:
            return cls(coordinate, (float(start),))
        return cls(coordinate, tuple(
            float(v) for v in np.linspace(start, stop, steps)))

    @property
    def label(self) -> str:
        return self.coordinate.label

    @property
    def units(self) -> str:
        return self.coordinate.units

    def __len__(self) -> int:
        return len(self.values)


@dataclass(frozen=True)
class ScanPoint:
    """One relaxed point of the grid."""

    index: tuple[int, ...]
    targets: tuple[float, ...]
    achieved: tuple[float, ...]
    energy: float
    converged: bool
    steps: int
    max_force: float
    frac: np.ndarray
    matrix: np.ndarray
    parameters: tuple[float, ...]
    branch: str = "forward"
    message: str = ""

    @property
    def finished(self) -> bool:
        """Did this point produce a number at all?

        Not the same as converged: a point can relax as far as the
        step limit allowed and still be worth plotting, as long as the
        landscape says which ones those are.
        """
        return bool(np.isfinite(self.energy))

    @property
    def volume(self) -> float:
        return float(abs(np.linalg.det(self.matrix)))


@dataclass(frozen=True)
class ScanPlan:
    """How a set of axes will actually be run.

    Built before anything is relaxed so that a dialog can say what is
    about to happen -- which coordinates are held, whether the cell
    relaxes, how many points there are -- and so that an impossible
    scan is refused up front rather than on the ninetieth point.
    """

    axes: tuple[Axis, ...]
    relax_cell: bool
    freedom: CellFreedom
    cell_axes: tuple[int, ...] = ()
    internal_axes: tuple[int, ...] = ()
    directions: tuple[str, ...] = ("forward",)
    seed: str = "previous"

    @property
    def shape(self) -> tuple[int, ...]:
        return tuple(len(axis) for axis in self.axes)

    @property
    def n_points(self) -> int:
        return int(np.prod(self.shape)) * len(self.directions)

    def describe(self) -> str:
        """What was held, in words, for the report.

        Half the confusion in the flexible-framework literature comes
        from profiles that do not say what was fixed while they were
        taken, so this is written into every scan's report rather than
        left for the reader to reconstruct.
        """
        held = ", ".join(f"{a.label} at each of {len(a)} values"
                         for a in self.axes)
        if self.relax_cell:
            cell = (f"the cell relaxed, {self.freedom.describe()}"
                    if self.freedom else "the cell relaxed freely")
        else:
            cell = "the cell held fixed at each point"
        branches = (", walked in both directions"
                    if len(self.directions) > 1 else "")
        return (f"Relaxed scan holding {held}, with {cell}, "
                f"seeded from the {self.seed} point{branches}.")


def plan(structure, axes, *, seed: str = "previous",
         direction: str = "both") -> ScanPlan:
    """Decide how these axes are run against this structure.

    The cell decision is the substance.  If every cell parameter the
    space group leaves free is being scanned, the cell at each point
    is completely determined and there is no reason to give the
    optimiser strain variables: it is exact without them, and on an
    engine with no analytic stress it is twelve energy evaluations a
    step cheaper.  Otherwise the unscanned parameters relax with the
    scanned ones held.
    """
    axes = tuple(axes)
    if not 1 <= len(axes) <= 2:
        raise ScanError(
            f"a scan takes one or two axes, not {len(axes)}")
    if seed not in SEEDS:
        raise ScanError(
            f"{seed!r} is not a seed policy; expected one of "
            f"{', '.join(SEEDS)}")
    if direction not in DIRECTIONS:
        raise ScanError(
            f"{direction!r} is not a direction; expected one of "
            f"{', '.join(DIRECTIONS)}")

    cell_axes = tuple(i for i, a in enumerate(axes)
                      if a.coordinate.is_cell)
    internal_axes = tuple(i for i in range(len(axes))
                          if i not in cell_axes)
    names = [axes[i].coordinate for i in cell_axes]
    volumes = [c for c in names if isinstance(c, co.CellVolume)]
    parameters = [c.name for c in names
                  if isinstance(c, co.CellParameter)]
    if volumes and parameters:
        raise ScanError(
            "scanning the volume and a lattice parameter together is "
            "ambiguous -- setting one changes the other.  Scan the "
            "volume with the shape free, or scan the parameters.")
    if len(parameters) != len(set(parameters)):
        raise ScanError("the same cell parameter is on both axes")

    free = set(structure.space_group.cell_constraint.free_names)
    for name in parameters:
        if name not in free:
            raise ScanError(
                f"{name} is not free in {structure.space_group}: "
                f"{structure.space_group.cell_constraint.describe()}."
                f"  Scan one of {', '.join(sorted(free))}.")

    if volumes:
        relax_cell, freedom = True, CellFreedom.constant_volume()
    elif parameters and free - set(parameters):
        relax_cell, freedom = True, CellFreedom.fixing(parameters)
    elif parameters:
        relax_cell, freedom = False, CellFreedom.free()
    else:
        relax_cell, freedom = False, CellFreedom.free()

    directions = (("forward", "reverse") if direction == "both"
                  else (direction,))
    return ScanPlan(axes, relax_cell, freedom, cell_axes,
                    internal_axes, directions, seed)


# ======================================================================
#  WALKING THE GRID
# ======================================================================

def raster(shape, reverse: bool = False) -> list[tuple[int, ...]]:
    """Every index of the grid, each next to the one before it.

    A plain nested loop jumps from the end of one row to the start of
    the next, so every row's first point is seeded from a geometry a
    whole axis away -- which is the seeding silently not happening,
    once per row.  Alternating the direction of each row (an ox
    ploughing, which is what boustrophedon means) keeps every step to
    one neighbour.
    """
    if len(shape) == 1:
        order = list(range(shape[0]))
        return [(i,) for i in (order[::-1] if reverse else order)]
    rows, columns = shape
    out = []
    for row in range(rows):
        span = range(columns)
        if row % 2:
            span = reversed(list(span))
        out.extend((row, column) for column in span)
    if reverse:
        out.reverse()
    return out


def _seeded_from(done, index, fallback):
    """The relaxed geometry to start this point from.

    The nearest finished neighbour, which the raster above makes
    adjacent in the ordinary case.  A point whose neighbour failed
    falls back to the nearest that did not, and then to the structure
    the scan was given: a failure must not propagate its absence
    down the rest of the row.
    """
    if not done:
        return fallback
    best = min(done, key=lambda other: sum(
        abs(a - b) for a, b in zip(other, index, strict=True)))
    return done[best]


def _with_cell(structure, lattice):
    """The structure in a new cell, fractional coordinates kept.

    Which is exactly "the closest cell's geometry transformed into the
    new cell": every atom keeps where it sits *relative to the cell*,
    so a framework carried into a wider cell arrives stretched rather
    than torn, and the relaxation has somewhere sensible to start.
    """
    out = structure.copy()
    out.set_lattice(lattice)
    return out


def _target_cell(structure, plan, targets):
    """The lattice a cell axis asks for, made legal for the group.

    ``CellConstraint.apply`` is what carries b along when a is
    scanned in a hexagonal group.  Without it the stored symmetry
    operations no longer map the structure onto itself and nothing
    anywhere reports it.
    """
    lattice = structure.lattice
    for index in plan.cell_axes:
        coordinate = plan.axes[index].coordinate
        value = targets[index]
        if isinstance(coordinate, co.CellVolume):
            lattice = lattice.scaled_to_volume(value)
        else:
            replaced = list(lattice.parameters)
            replaced[PARAMETER_NAMES.index(coordinate.name)] = value
            lattice = Lattice.from_parameters(
                *structure.space_group.cell_constraint.apply(replaced))
    return lattice


def _held(structure, plan, targets):
    """The internal coordinates this point holds, rebuilt on it.

    Rebuilt rather than carried, because a coordinate remembers which
    periodic images it was defined on and the seed geometry it is
    being applied to is a different arrangement of the same atoms.
    """
    from xtal.core import p1
    if not plan.internal_axes:
        return None
    cell = p1.expand(structure)
    pairs = []
    for index in plan.internal_axes:
        coordinate = plan.axes[index].coordinate
        pairs.append((co.internal(structure, cell,
                                  _kind_of(coordinate),
                                  [a.atoms for a in
                                   coordinate.anchors]),
                      targets[index]))
    return Holonomic(tuple(pairs))


def _kind_of(coordinate) -> str:
    for kind, cls in (("distance", co.Distance), ("angle", co.Angle),
                      ("torsion", co.Torsion),
                      ("plane angle", co.PlaneAngle)):
        if isinstance(coordinate, cls):
            return kind
    raise ScanError(                                # pragma: no cover
        f"{coordinate.label} is not an internal coordinate")


# ======================================================================
#  THE SCAN
# ======================================================================

def scan(build, structure, axes, *, seed: str = "previous",
         direction: str = "both", cancel=None, on_point=None,
         **optimiser) -> Iterator[ScanPoint]:
    """Relax the structure at every point of the grid.

    ``build(structure)`` returns a calculator for it; a fresh one is
    made per point because an engine is built over a particular cell.
    ``cancel`` is a :class:`xtal.modules.job.Cancellation`, checked
    between points and handed to the optimiser so that an engine
    running a program can be stopped mid-evaluation.

    Points come out as they finish, so that whatever is driving this
    can write each one to disk before the next begins.  A scan is an
    overnight job -- 0.44 seconds a step on a 1152-atom framework
    under UFF -- and Stop has to leave a landscape behind rather than
    lose one.
    """
    shape = tuple(len(a) for a in axes)
    prepared = plan(structure, axes, seed=seed, direction=direction)
    hold_bonding(structure)
    # A sweep back down starts where the sweep up finished, which is
    # what a hysteresis loop *is*: one continuous path out and back.
    # Started from the input instead, the return branch's first point
    # is a jump the whole width of the scan -- on MIL-53 that put the
    # reverse branch 606 kcal/mol above the forward one at the same
    # volume, for two or three points, until it found its way back.
    # Only the first point is borrowed; after that each branch is on
    # its own, because two branches sharing geometries all the way
    # along would have no hysteresis left to measure.
    ending: object = None
    for branch in prepared.directions:
        done: dict[tuple[int, ...], object] = {}
        first = True
        for index in raster(shape, reverse=(branch == "reverse")):
            if cancel is not None and cancel.requested:
                return
            targets = tuple(prepared.axes[k].values[i]
                            for k, i in enumerate(index))
            opening = ending if (first and ending is not None)\
                else structure
            first = False
            start = (structure if prepared.seed == "input"
                     else _seeded_from(done, index, opening))
            point = _one_point(build, structure, start, prepared,
                               index, targets, branch, cancel,
                               optimiser)
            if point.finished:
                done[index] = ending = _rebuilt(structure, point)
            if on_point is not None:
                on_point(point)
            yield point


def hold_bonding(structure) -> None:
    """Perceive once, here, so that every point is the same molecule.

    Distance perception is re-run on any structure that has none
    stored, and a scan hands the engine a new cell at every point --
    so without this the framework is re-perceived at each one and
    quietly comes apart as it opens.  Measured on ``MIL53.cif``:
    stretching *a* by 15% loses 24 of its 126 bonds and by 30% loses
    78, and *c* by 20% loses 36.  The landscape then has a cliff in it
    that is a change of topology rather than anything about the
    material, and nothing says so.

    Perceiving once writes the graph onto the structure, where
    ``copy`` carries it and a cell change does not disturb it, so
    every point is scored over the bonds the user had when they
    started.  Explicit bonds ride on top of it as they always do,
    which is how a bond type set by hand survives the whole scan.

    This is :data:`xtal.core.structure.CHEMISTRY`'s rule kept rather
    than bent: bonds change when the user asks them to, and a scan is
    not asking.
    """
    if structure.perceived is None:
        bonding.perceive(structure)


def _rebuilt(structure, point):
    out = structure.copy()
    for site, row in zip(out.sites, point.frac, strict=True):
        site.frac = row
    out.set_lattice(Lattice(point.matrix))
    return out


def _one_point(build, original, start, prepared, index, targets,
               branch, cancel, optimiser) -> ScanPoint:
    """One relaxation, with whatever failed it turned into a message.

    A point that raises does not stop the scan.  One bad cell in a
    hundred is a hole in the landscape; it is not a reason to lose the
    ninety-nine that worked.
    """
    lattice = (_target_cell(start, prepared, targets)
               if prepared.cell_axes else start.lattice)
    at = _with_cell(start, lattice)
    blank = np.full(len(original.sites), np.nan)
    try:
        held = _held(at, prepared, targets)
        result = optimize.run(
            build(at), at, cancel=cancel,
            relax_cell=prepared.relax_cell,
            freedom=prepared.freedom, constraints=held,
            **optimiser)
    except CalculatorStopped:
        return _failed(index, targets, branch, at, blank,
                       "stopped")
    except (CalculatorError, ValueError) as error:
        return _failed(index, targets, branch, at, blank, str(error))

    matrix = (result.matrix if result.matrix is not None
              else at.lattice.matrix)
    relaxed = Lattice(matrix)
    achieved = _achieved(original, prepared, result.frac, matrix,
                         relaxed)
    return ScanPoint(
        index=index, targets=targets, achieved=achieved,
        energy=float(result.energy), converged=bool(result.converged),
        steps=int(result.steps), max_force=float(result.max_force),
        frac=result.frac, matrix=matrix,
        parameters=tuple(float(v) for v in relaxed.parameters),
        branch=branch, message=result.message)


def _failed(index, targets, branch, at, blank, message) -> ScanPoint:
    return ScanPoint(
        index=index, targets=targets,
        achieved=tuple(float("nan") for _ in targets),
        energy=float("nan"), converged=False, steps=0,
        max_force=float("nan"), frac=at.frac.copy(),
        matrix=at.lattice.matrix,
        parameters=tuple(float(v) for v in at.lattice.parameters),
        branch=branch, message=message)


def _achieved(original, prepared, frac, matrix, lattice):
    """What each coordinate actually came out at.

    Reported beside the target rather than assumed equal to it.  A
    held internal coordinate lands on its target to machine precision;
    a held cell parameter is exact to first order in the strain and
    drifts by the square of it, and a reader deciding whether a kink
    in the landscape is physics needs to be able to rule that out.
    """
    from xtal.core import p1
    out = []
    moved = None
    for axis in prepared.axes:
        coordinate = axis.coordinate
        if coordinate.is_cell:
            if isinstance(coordinate, co.CellVolume):
                out.append(float(abs(np.linalg.det(matrix))))
            else:
                out.append(float(lattice.parameters[
                    PARAMETER_NAMES.index(coordinate.name)]))
            continue
        if moved is None:
            moved = original.copy()
            for site, row in zip(moved.sites, frac, strict=True):
                site.frac = row
            moved.set_lattice(lattice)
        cell = p1.expand(moved)
        rebuilt = co.internal(moved, cell, _kind_of(coordinate),
                              [a.atoms for a in coordinate.anchors])
        out.append(float(rebuilt.value(cell.frac @ matrix, matrix)))
    return tuple(out)


# ======================================================================
#  READING A FINISHED SCAN
# ======================================================================

@dataclass
class ScanResult:
    """Every point of a scan, and the grid they make."""

    plan: ScanPlan
    points: list[ScanPoint] = field(default_factory=list)

    def branch(self, name: str) -> list[ScanPoint]:
        return [p for p in self.points if p.branch == name]

    def finished(self) -> list[ScanPoint]:
        return [p for p in self.points if p.finished]

    def minimum(self) -> ScanPoint | None:
        """The lowest point that actually finished.

        Unfinished points take no part in it, which is the same rule
        the colour scale follows: a landscape referenced to a hole is
        a landscape of the hole.
        """
        done = self.finished()
        return min(done, key=lambda p: p.energy) if done else None

    def grid(self, branch: str = "forward") -> np.ndarray:
        """Energies on the grid, NaN where a point did not finish."""
        out = np.full(self.plan.shape, np.nan)
        for point in self.branch(branch):
            out[point.index] = point.energy
        return out

    def relative(self, branch: str = "forward") -> np.ndarray:
        """The same, measured from the lowest finished point."""
        return self.grid(branch) - self.base()

    def base(self) -> float:
        lowest = self.minimum()
        return lowest.energy if lowest is not None else 0.0

    def best(self) -> np.ndarray:
        """The lower of the branches at every point of the grid.

        The landscape somebody actually wants to look at.  A scan
        walked both ways gives two energies per cell, and neither
        alone is the answer: each is the energy of the basin that
        branch happened to arrive in, and the lower of the two is the
        better estimate of the ground state there.  Drawing one branch
        and calling it the landscape means half the picture is an
        artefact of the direction of travel.

        The two are still kept, because their *difference* is the
        hysteresis and that is the physics of a flexible framework --
        but it is a second question, and this is the first.
        """
        grids = [self.grid(name) for name in
                 dict.fromkeys(p.branch for p in self.points)]
        if not grids:
            return np.full(self.plan.shape, np.nan)   # pragma: no cover
        return np.fmin.reduce(grids)

    def hysteresis(self) -> np.ndarray | None:
        """Forward minus reverse, where a scan was walked both ways.

        ``None`` for one direction, because a difference of one thing
        is not a number anybody should be shown.
        """
        names = list(dict.fromkeys(p.branch for p in self.points))
        if len(names) < 2:
            return None
        return self.grid(names[0]) - self.grid(names[1])

    def best_points(self) -> dict:
        """The point that gave the lower energy at each index."""
        out: dict = {}
        for point in self.points:
            if not point.finished:
                continue
            held = out.get(point.index)
            if held is None or point.energy < held.energy:
                out[point.index] = point
        return out

    def converged(self, branch: str = "forward") -> np.ndarray:
        out = np.zeros(self.plan.shape, dtype=bool)
        for point in self.branch(branch):
            out[point.index] = point.converged
        return out

    def pressure(self, branch: str = "forward"):
        """``(volumes, P = -dE/dV)`` in GPa, for a volume scan.

        The derivative of the profile is the mechanical statement
        hiding inside it: where it turns the wrong way -- dP/dV above
        zero -- the cell is not mechanically stable, and that is where
        a breathing framework's hysteresis comes from.  ``None``
        unless the one axis really is a volume, because -dE/dV of a
        scan over a bond length is not a pressure.
        """
        if len(self.plan.axes) != 1:
            return None
        if not isinstance(self.plan.axes[0].coordinate, co.CellVolume):
            return None
        done = sorted((p for p in self.branch(branch) if p.finished),
                      key=lambda p: p.volume)
        if len(done) < 2:
            return None
        volume = np.array([p.volume for p in done])
        energy = np.array([p.energy for p in done])
        return volume, -np.gradient(energy, volume) / optimize.GPA


def collect(iterator, plan_used) -> ScanResult:
    """Drain a :func:`scan` into a :class:`ScanResult`."""
    out = ScanResult(plan_used)
    for point in iterator:
        out.points.append(point)
    return out


def estimate(plan_used, seconds_per_step: float,
             steps: int) -> float:
    """Roughly how long this scan will take, in seconds.

    Shown before the click rather than discovered after it: a twelve
    by twelve grid of a real framework is hours, and that is a thing
    to find out from a dialog.
    """
    return float(plan_used.n_points) * float(steps) * float(
        seconds_per_step) if not math.isnan(seconds_per_step) else 0.0
