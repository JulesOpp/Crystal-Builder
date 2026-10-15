"""
xtal.ff.qha
===========
Quasi-harmonic free energy: F(V, T) = E(V) + F_vib(V, T), each volume
relaxed with the shape free and its vibrations summed harmonically,
and the minimum over V taken at every temperature.

That is the cheapest honest way to put temperature into a flexible
framework's landscape.  A volume scan is at zero kelvin, and for
MIL-53 the large- and narrow-pore difference changes sign between 100
and 500 K: entropy decides which phase is stable, and E(V) cannot see
it.  The thermal expansion comes from the frequencies' dependence on
volume and from nothing else -- a crystal whose frequencies do not
move with V does not expand, and a test holds that.

**A volume with imaginary modes is a hole, not a free energy.**  Its
F would leave out the modes the energy falls along, which is a number
for a structure that is not there; it is NaN, left out of every fit,
and named.  So is a volume whose relaxation did not converge.

**A two-well landscape is fitted one well at a time.**  An equation
of state has one minimum, and fitted across MIL-53's two it puts V0
in the barrier.  The volumes are split at the local maxima of the
finite E(V) points, each well is fitted on its own, and where the
wells' G cross is the transition temperature.  A well with too few
points for Birch-Murnaghan (five) but at least three is fitted with a
parabola and says so.

No Qt, no run folder: :mod:`xtal.modules.qha` drives the scan and the
Hessians and writes the files; this is the arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from xtal.ff import eos, thermo
from xtal.ff.optimize import GPA

#: The least a well can be fitted on at all, with a parabola.
PARABOLA_POINTS = 3


@dataclass(frozen=True)
class Volume:
    """One relaxed volume: its energy (kcal/mol per cell) and the
    frequencies (cm^-1) and weights its free energy is summed over.

    ``note`` says why it is a hole when it is one -- a relaxation that
    did not converge, imaginary modes, a Hessian that was not taken.
    """

    volume: float
    energy: float
    frequencies: np.ndarray | None = None
    weights: np.ndarray | None = None
    note: str = ""

    @property
    def hole(self) -> bool:
        return bool(self.note) or self.frequencies is None \
            or not np.isfinite(self.energy)


def judge(volume: float, energy: float, frequencies, weights=None,
          converged: bool = True) -> Volume:
    """A :class:`Volume`, made a hole when it cannot be summed: not
    converged, or with modes below :data:`thermo.IMAGINARY_BELOW`."""
    frequencies = np.asarray(frequencies, float)
    weights = (np.ones_like(frequencies) if weights is None
               else np.asarray(weights, float))
    note = ""
    if not converged:
        note = "the relaxation did not converge"
    else:
        imaginary = int(np.count_nonzero(
            frequencies < thermo.IMAGINARY_BELOW))
        if imaginary:
            note = (f"{imaginary} imaginary mode"
                    f"{'s' if imaginary != 1 else ''}")
    return Volume(float(volume), float(energy), frequencies, weights,
                  note)


def free_energies(points, temperatures) -> np.ndarray:
    """F (kcal/mol per cell) at every volume and temperature, ``(n
    volumes, n temperatures)``; NaN along a hole's row."""
    temperatures = np.asarray(temperatures, float)
    out = np.full((len(points), len(temperatures)), np.nan)
    for i, point in enumerate(points):
        if point.hole:
            continue
        for j, t in enumerate(temperatures):
            terms = thermo.harmonic(point.frequencies, point.weights,
                                    temperature=float(t))
            out[i, j] = point.energy + terms.f_vib
    return out


def wells(volumes, energies) -> list[np.ndarray]:
    """The indices of each well, smallest volume first: the finite
    points split at every local maximum of E(V), the maximum itself
    in neither -- a barrier top is not part of either curve."""
    volumes = np.asarray(volumes, float)
    energies = np.asarray(energies, float)
    finite = np.flatnonzero(np.isfinite(volumes) & np.isfinite(energies))
    order = finite[np.argsort(volumes[finite])]
    if len(order) < 3:
        return [order] if len(order) else []
    e = energies[order]
    out, start = [], 0
    for k in range(1, len(order) - 1):
        if e[k] > e[k - 1] and e[k] > e[k + 1]:
            out.append(order[start:k])
            start = k + 1
    out.append(order[start:])
    return [w for w in out if len(w)]


@dataclass(frozen=True)
class Minimum:
    """A well's minimum at one temperature: V (A^3), G (kcal/mol per
    cell, F + pV) and B (GPa) there."""

    temperature: float
    volume: float
    g: float
    b: float


@dataclass(frozen=True)
class Well:
    """One well, fitted at every temperature.  ``minima[j]`` is
    ``None`` where the fit at that temperature refused, and
    ``reasons[j]`` says why."""

    indices: np.ndarray
    form: str
    minima: tuple
    reasons: tuple

    def series(self, name: str) -> np.ndarray:
        return np.array([np.nan if m is None else getattr(m, name)
                         for m in self.minima])

    @property
    def expansion(self) -> np.ndarray:
        """alpha = d ln V / dT, 1/K, where both neighbours fitted."""
        t = np.array([m.temperature if m else np.nan
                      for m in self.minima])
        v = self.series("volume")
        out = np.full(len(v), np.nan)
        for j in range(1, len(v) - 1):
            if np.isfinite(v[j - 1:j + 2]).all():
                out[j] = (np.log(v[j + 1]) - np.log(v[j - 1])) \
                    / (t[j + 1] - t[j - 1])
        return out


@dataclass(frozen=True)
class Crossing:
    """Where two wells' G are equal: ``below`` is the well lower
    under ``temperature``, ``above`` the one lower over it."""

    temperature: float
    below: int
    above: int


@dataclass(frozen=True)
class QHAResult:
    points: tuple
    temperatures: np.ndarray
    free: np.ndarray
    wells: tuple
    pressure: float = 0.0
    crossings: tuple = field(default=())

    @property
    def volumes(self) -> np.ndarray:
        return np.array([p.volume for p in self.points])

    @property
    def holes(self) -> list[Volume]:
        return [p for p in self.points if p.hole]


def analyse(points, temperatures, pressure: float = 0.0) -> QHAResult:
    """F(V, T), split into wells and each fitted at every temperature;
    ``pressure`` in GPa (G = F + pV at the minimum)."""
    points = tuple(points)
    temperatures = np.asarray(temperatures, float)
    free = free_energies(points, temperatures)
    volumes = np.array([p.volume for p in points])
    energies = np.array([np.nan if p.hole else p.energy for p in points])
    found = []
    for indices in wells(volumes, energies):
        found.append(_fit_well(volumes, free, indices, temperatures,
                               pressure))
    return QHAResult(points, temperatures, free, tuple(found), pressure,
                     tuple(_crossings(found, temperatures)))


def _fit_well(volumes, free, indices, temperatures, pressure) -> Well:
    v = volumes[indices]
    form = ("Birch-Murnaghan" if len(indices) >= eos.MINIMUM_POINTS
            else "parabola")
    minima, reasons = [], []
    for j, t in enumerate(temperatures):
        try:
            curve = (_eos_curve(v, free[indices, j]) if form != "parabola"
                     else _parabola(v, free[indices, j]))
            minima.append(_minimum(curve, v, float(t), pressure))
            reasons.append("")
        except eos.EOSError as error:
            minima.append(None)
            reasons.append(str(error))
    return Well(np.asarray(indices), form, tuple(minima), tuple(reasons))


def _eos_curve(v, f):
    return eos.fit(v, f, "Birch-Murnaghan").energy


def _parabola(v, f):
    keep = np.isfinite(f)
    v, f = v[keep], f[keep]
    if len(v) < PARABOLA_POINTS:
        raise eos.EOSError(
            f"{len(v)} usable volume{'s' if len(v) != 1 else ''} in "
            f"this well; it needs at least {PARABOLA_POINTS}")
    a, b, c = np.polyfit(v, f, 2)
    if a <= 0 or not v.min() <= -b / (2 * a) <= v.max():
        raise eos.EOSError("the well's minimum is outside its volumes")
    return lambda x: np.polyval((a, b, c), x)


def _minimum(curve, v, temperature, pressure) -> Minimum:
    """The fitted F + pV minimised over the well's volumes, and the
    curvature there as B = V d2F/dV2."""
    from scipy.optimize import minimize_scalar

    pv = pressure * GPA

    def g(x):
        return float(curve(np.asarray(x, float))) + pv * x

    found = minimize_scalar(g, bounds=(float(v.min()), float(v.max())),
                            method="bounded",
                            options={"xatol": 1e-6 * float(v.max())})
    x = float(found.x)
    span = float(v.max() - v.min())
    if x - v.min() < 1e-4 * span or v.max() - x < 1e-4 * span:
        raise eos.EOSError("the minimum is at the edge of the well's "
                           "volumes; widen the scan")
    h = 1e-3 * span
    second = (g(x + h) - 2.0 * g(x) + g(x - h)) / (h * h)
    return Minimum(temperature, x, g(x), x * second / GPA)


def _crossings(found, temperatures) -> list[Crossing]:
    out = []
    for a in range(len(found)):
        for b in range(a + 1, len(found)):
            d = found[a].series("g") - found[b].series("g")
            for j in range(len(d) - 1):
                if not np.isfinite(d[j:j + 2]).all() or \
                        np.sign(d[j]) == np.sign(d[j + 1]) or d[j] == 0:
                    continue
                t0, t1 = temperatures[j], temperatures[j + 1]
                t = t0 + (t1 - t0) * d[j] / (d[j] - d[j + 1])
                lower, upper = (a, b) if d[j] < 0 else (b, a)
                out.append(Crossing(float(t), lower, upper))
    return sorted(out, key=lambda c: c.temperature)
