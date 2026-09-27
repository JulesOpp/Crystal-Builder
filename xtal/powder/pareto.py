"""
xtal.powder.pareto
==================
Which weight: a sweep of Rietveld with energies from the pattern alone
to the energy alone, the points no other point beats on both counts,
and the one where giving up fit starts to buy little energy.

**A sweep is one problem minimised at every weight**
(:class:`~xtal.powder.energy.EnergyProblem`): the scale, background
and peak shape are fitted once, so every point is scored against the
same pattern parameters.  Fitting them again at each point would put
each point on an objective of its own, and a front of points from
different objectives is not a front.

**Each point starts from its neighbour**, the weights walked upwards
from 0 -- except ``w = 1``, which is the relaxation from the start
that sets the energy's scale, and is the first point finished.  A
point is handed to ``on_point`` the moment it finishes, so a stopped
or crashed sweep leaves every point it reached; a point that did not
converge keeps its structure but has no numbers, because a hole drawn
as a number is a point on the front that is not there.

**The knee is a suggestion.**  With both axes scaled to the front's
own range, it is the front point furthest from the chord between the
front's two ends: where the curve bends most.  A front of fewer than
three points, or one with nothing off its chord, has none.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from xtal.powder.data import PowderData, PowderError, PowderStopped, Radiation
from xtal.powder.energy import (
    EnergyFit,
    EnergyOptions,
    EnergyProblem,
    EnergyScale,
)

__all__ = ["DEFAULT_WEIGHTS", "ParetoPoint", "ParetoResult", "front",
           "knee", "parse_weights", "sweep"]

#: Denser near 0, where a little energy changes the answer most: the
#: pattern's term falls off a cliff and the energy's does not.
DEFAULT_WEIGHTS = (0.0, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8,
                   0.9, 1.0)


@dataclass
class ParetoPoint:
    """One weight's answer."""

    weight: float
    fit: EnergyFit | None = None
    #: the refined structure's file, once somebody has written it
    path: str = ""

    @property
    def converged(self) -> bool:
        return self.fit is not None and self.fit.converged

    @property
    def rwp(self) -> float:
        return self.fit.rwp if self.converged else math.nan

    @property
    def energy(self) -> float:
        return self.fit.energy if self.converged else math.nan

    @property
    def status(self) -> str:
        return self.fit.status if self.fit is not None else "not run"


@dataclass
class ParetoResult:
    """The points reached, in order of weight, and what they say."""

    points: list[ParetoPoint] = field(default_factory=list)
    scale: EnergyScale | None = None
    stopped: bool = False

    @property
    def front(self) -> list[int]:
        return front(self.points)

    @property
    def knee(self) -> int | None:
        return knee(self.points)


def parse_weights(text: str) -> tuple[float, ...]:
    """``"0, 0.1, 0.5 1"``: commas or spaces, sorted, each once.
    Empty is :data:`DEFAULT_WEIGHTS`."""
    words = text.replace(",", " ").split()
    if not words:
        return DEFAULT_WEIGHTS
    try:
        weights = sorted({float(word) for word in words})
    except ValueError as exc:
        raise PowderError(f"the weights are numbers from 0 to 1, "
                          f"separated by commas: {exc}") from None
    outside = [w for w in weights if not 0.0 <= w <= 1.0]
    if outside:
        raise PowderError(f"a weight runs from 0 to 1; {outside[0]:g} "
                          f"does not")
    return tuple(weights)


def front(points) -> list[int]:
    """The indices of the points no other point beats on both Rwp and
    energy -- at least as good on each and better on one.  A point
    with no numbers is on no front."""
    values = [(k, p.rwp, p.energy) for k, p in enumerate(points)
              if math.isfinite(p.rwp) and math.isfinite(p.energy)]
    out = []
    for k, rwp, energy in values:
        beaten = any(r <= rwp and e <= energy and (r < rwp or e < energy)
                     for j, r, e in values if j != k)
        if not beaten:
            out.append(k)
    return out


def knee(points) -> int | None:
    """The index of the front point furthest from the chord between
    the front's ends, both axes scaled to the front's range."""
    on = front(points)
    if len(on) < 3:
        return None
    xy = np.array([(points[k].rwp, points[k].energy) for k in on])
    span = xy.max(axis=0) - xy.min(axis=0)
    if np.any(span <= 0):
        return None
    xy = (xy - xy.min(axis=0)) / span
    order = np.argsort(xy[:, 0])
    first, last = xy[order[0]], xy[order[-1]]
    chord = last - first
    length = float(np.hypot(*chord))
    distance = np.abs(chord[0] * (xy[:, 1] - first[1])
                      - chord[1] * (xy[:, 0] - first[0])) / length
    best = int(np.argmax(distance))
    return on[best] if distance[best] > 1e-9 else None


def sweep(structure, data: PowderData, radiation: Radiation, build,
          options: EnergyOptions | None = None,
          weights=DEFAULT_WEIGHTS, *, engine: str = "", on_point=None,
          on_frame=None, frame_interval: float = 0.2, cancel=None,
          folder=None, say=None) -> ParetoResult:
    """Refine ``structure`` at every weight in ``weights``.

    ``options`` is the With energy step's, its own weight unread.
    ``on_point(point)`` is called as each point finishes -- the place
    to write it.  Stop returns what was reached with ``stopped`` set,
    rather than raising: every finished point is an answer.  A Stop
    while the pattern's own parameters are still being fitted has
    reached nothing, and raises :class:`PowderStopped`.
    """
    options = options or EnergyOptions()
    weights = sorted({float(w) for w in weights})
    if not weights:
        raise PowderError("there are no weights to refine at")
    for w in weights:
        if not 0.0 <= w <= 1.0:
            raise PowderError(f"a weight runs from 0 to 1; {w:g} does not")
    say = say or (lambda _text: None)
    problem = EnergyProblem(structure, data, radiation, build, options,
                            engine=engine, on_frame=on_frame,
                            frame_interval=frame_interval,
                            cancel=cancel, folder=folder, say=say)
    result = ParetoResult(scale=problem.scale)
    points = {}
    counted = [""]
    problem.say = lambda text: say(counted[0] + text)

    def finished(weight, answer, steps, converged, why):
        point = ParetoPoint(weight, problem.fit(answer, weight, steps,
                                                converged, why))
        points[weight] = point
        result.points = [points[w] for w in sorted(points)]
        if on_point is not None:
            on_point(point)
        return point

    try:
        if any(w > 0.0 for w in weights):
            relaxation = problem.relax()
            result.scale = problem.scale
            if 1.0 in weights:
                finished(1.0, *relaxation)
        start = None
        for weight in (w for w in weights if w < 1.0):
            counted[0] = f"[{len(points) + 1}/{len(weights)}] "
            answer, *rest = problem.solve(weight, start=start)
            finished(weight, answer, *rest)
            start = answer
    except PowderStopped:
        result.stopped = True
    return result
