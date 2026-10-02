"""
xtal.ff.eos
===========
An equation of state through the points of a volume scan: the bulk
modulus.

The scan does the physics -- each point a cell held at one volume
with its shape and its atoms relaxed (`CellFreedom.constant_volume`),
which is what a bulk modulus is the curvature of.  This only fits a
curve through what came back.  Two curves, because a modulus quoted
from one functional form is a modulus of that form: the third-order
Birch-Murnaghan is what papers report, and Vinet is the check.  When
the two disagree by much, the points are further from the minimum
than either form describes, and the number should be read that way.

Three things are refused rather than fitted, because each gives a
plausible number that is wrong:

* **fewer than** :data:`MINIMUM_POINTS` **converged points** -- four
  parameters through four points is interpolation, not a fit;
* **an unconverged point** is left out, never fitted: it is not a
  number (see the scan's own rule), and the energy of a cell that
  stopped half way down is above the curve by however far it had left
  to go;
* **a minimum that is not bracketed** -- the lowest energy at the
  first or last volume.  Then V0 is outside the scan and the modulus
  is an extrapolation; the cure is a wider scan, or relaxing the cell
  before scanning round it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from xtal.ff.optimize import GPA

#: Four parameters, so a fifth point is the least that tests the form.
MINIMUM_POINTS = 5


class EOSError(ValueError):
    """The points cannot give a modulus worth reporting."""


@dataclass(frozen=True)
class EOSFit:
    """One equation of state through the points."""

    name: str                   # "Birch-Murnaghan", "Vinet"
    v0: float                   # A^3, the volume at the minimum
    e0: float                   # kcal/mol, the energy there
    b0: float                   # GPa
    b0_prime: float             # dB/dP, dimensionless
    rms: float                  # kcal/mol, the residual
    n_points: int

    def energy(self, volume) -> np.ndarray:
        """The fitted energy at ``volume``, kcal/mol."""
        return _FORMS[self.name](np.asarray(volume, float), self.e0,
                                 self.v0, self.b0 * GPA, self.b0_prime)


def birch_murnaghan(volume, e0, v0, b0, b0_prime):
    """Third-order Birch-Murnaghan; ``b0`` in energy per volume."""
    eta = (v0 / volume) ** (2.0 / 3.0) - 1.0
    return e0 + 9.0 * v0 * b0 / 16.0 * (
        eta ** 3 * b0_prime + eta ** 2 * (6.0 - 4.0 * (eta + 1.0)))


def vinet(volume, e0, v0, b0, b0_prime):
    """Vinet's universal form; ``b0`` in energy per volume."""
    x = (volume / v0) ** (1.0 / 3.0)
    k = 1.5 * (b0_prime - 1.0)
    return e0 + 9.0 * b0 * v0 / k ** 2 * (
        1.0 + (k * (1.0 - x) - 1.0) * np.exp(k * (1.0 - x)))


_FORMS = {"Birch-Murnaghan": birch_murnaghan, "Vinet": vinet}


def fit(volumes, energies, form: str = "Birch-Murnaghan") -> EOSFit:
    """``form`` through the finite points, or :class:`EOSError` saying
    why not.

    ``volumes`` in A^3 and ``energies`` in kcal/mol for the whole
    cell, as a scan reports them.  A NaN energy is a point that did
    not converge and is left out.
    """
    from scipy.optimize import curve_fit

    v, e = _usable(volumes, energies)
    # A parabola in V gives the start: its vertex is V0 and its
    # curvature times V0 is B0.  Good enough that the fit only has to
    # settle B0', which no parabola has an opinion about.
    a, b, c = np.polyfit(v, e, 2)
    if a <= 0:
        raise EOSError("the energy does not curve upwards on both "
                       "sides of the lowest point, so there is no "
                       "minimum to fit")
    v0 = -b / (2.0 * a)
    start = (float(np.polyval((a, b, c), v0)), float(v0),
             float(2.0 * a * v0), 4.0)
    try:
        values, _ = curve_fit(_FORMS[form], v, e, p0=start,
                              maxfev=20000)
    except RuntimeError as error:
        raise EOSError(f"the {form} fit did not converge: "
                       f"{error}") from error
    e0, v0, b0, b0_prime = (float(x) for x in values)
    if not (v.min() <= v0 <= v.max()) or b0 <= 0:
        raise EOSError(f"the {form} fit puts the minimum outside the "
                       f"scan; widen it")
    residual = e - _FORMS[form](v, e0, v0, b0, b0_prime)
    return EOSFit(name=form, v0=v0, e0=e0, b0=b0 / GPA,
                  b0_prime=b0_prime,
                  rms=float(np.sqrt(np.mean(residual ** 2))),
                  n_points=len(v))


def both(volumes, energies) -> tuple[EOSFit, EOSFit]:
    """Birch-Murnaghan, and Vinet as its check."""
    return (fit(volumes, energies, "Birch-Murnaghan"),
            fit(volumes, energies, "Vinet"))


def _usable(volumes, energies):
    v = np.asarray(volumes, float)
    e = np.asarray(energies, float)
    keep = np.isfinite(v) & np.isfinite(e)
    v, e = v[keep], e[keep]
    if len(v) < MINIMUM_POINTS:
        raise EOSError(
            f"{len(v)} converged point{'s' if len(v) != 1 else ''}; "
            f"a bulk modulus needs at least {MINIMUM_POINTS}")
    order = np.argsort(v)
    v, e = v[order], e[order]
    lowest = int(np.argmin(e))
    if lowest in (0, len(v) - 1):
        side = "smallest" if lowest == 0 else "largest"
        raise EOSError(
            f"the lowest energy is at the {side} volume, so the "
            f"minimum is outside the scan; widen it, or relax the "
            f"cell first")
    return v, e
