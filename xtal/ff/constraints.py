"""
xtal.ff.constraints
===================
Holding a coordinate while everything else relaxes.

A relaxed scan sets a distance, an angle, a torsion or a plane angle
and asks what the rest of the crystal does about it.  The obvious way
to make the coordinate stay put is to freeze the atoms that define it,
and the application already can -- but freezing four atoms to hold one
dihedral removes twelve degrees of freedom to constrain one.  What
comes back is not the profile of the material, it is the profile of
the constraint, biased upward by however much the frozen atoms wanted
to move for reasons that had nothing to do with the dihedral.

So the coordinate is held properly, by the two halves every
constrained minimiser has had since SHAKE:

* the search direction is **projected** onto the subspace that leaves
  the coordinate alone, so a step does not try to change it; and
* the point is **restored** onto the constraint afterwards by Newton's
  method, because a tangent step leaves it by order of the step
  squared and that accumulates over a few hundred iterations.

Both are done in the optimiser's own variables -- the asymmetric unit
and the symmetry-adapted strain -- rather than on the P1 cell, so a
held coordinate composes with everything already there: a site on a
special position stays on it, a frozen site stays frozen, and a cubic
cell stays cubic.  The constraint can only ever remove freedom.  It is
applied last for that reason.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from xtal.ff.api import CalculatorError

#: Newton iterations allowed to put a point back on the constraint.
#: Two is the usual number; the cap is for the pathological case.
MAX_RESTORE = 24

#: A row of the constraint matrix this short means the variables
#: cannot change the coordinate at all.  Relative to the largest row,
#: so it is a statement about rank and not about units.
SINGULAR = 1e-9


class ConstraintError(CalculatorError):
    """A coordinate that cannot be held where it was asked to be."""


@dataclass(frozen=True)
class Holonomic:
    """Coordinates and the values they are held at.

    One or two of them in practice -- the axes of a scan -- which is
    why the linear algebra below solves the whole ``m x m`` system at
    once rather than iterating constraint by constraint as SHAKE
    classically does.  For ``m`` of two there is nothing to gain by
    being clever and something to lose: coupled constraints converge
    together here and only alternately there.
    """

    pairs: tuple[tuple, ...] = ()

    @property
    def size(self) -> int:
        return len(self.pairs)

    def __bool__(self) -> bool:
        return bool(self.pairs)

    # -- reading the coordinates ---------------------------------------

    def values(self, dof, x) -> np.ndarray:
        positions = dof.positions(x)
        matrix = dof.matrix_of(x)
        return np.array([c.value(positions, matrix)
                         for c, _target in self.pairs])

    def residual(self, dof, x) -> np.ndarray:
        """How far each coordinate is from where it is held.

        An angle is wrapped onto the turn nearest its target, so a
        torsion held at 179 degrees is not thought to be 358 degrees
        out when it reads -179.
        """
        out = []
        for value, (coordinate, target) in zip(
                self.values(dof, x), self.pairs, strict=True):
            error = float(value) - float(target)
            if coordinate.units == "deg":
                error -= 360.0 * round(error / 360.0)
            out.append(error)
        return np.array(out)

    def tolerances(self) -> np.ndarray:
        return np.array([c.tolerance for c, _t in self.pairs])

    def satisfied(self, dof, x) -> bool:
        return bool(np.all(np.abs(self.residual(dof, x))
                           <= self.tolerances()))

    # -- the constraint matrix -----------------------------------------

    def matrix(self, dof, x) -> np.ndarray:
        """``d(coordinate)/d(variable)``, one row per coordinate.

        The site half goes through :meth:`SymmetryDOF.carry`, which is
        the very chain rule the energy's own gradient takes, so a
        coordinate and the energy are differentiated with respect to
        the same variables in the same frame.

        The strain half is central differences, and that is not
        laziness.  The energy's strain gradient is read off the stress
        because a virial over a periodic cell is not the sum of
        position times force; a coordinate is an explicit function of
        a handful of atoms and their held images, so no such sum
        applies to it either, and the images move with the cell in a
        way no single formula covers for all four kinds.  Differencing
        it evaluates *arithmetic* six times over -- microseconds
        against the seconds an engine spends on one force call.
        """
        rows = []
        positions = dof.positions(x)
        matrix = dof.matrix_of(x)
        for coordinate, _target in self.pairs:
            site = dof.carry(coordinate.gradient(positions, matrix), x)
            if not dof.relax_cell:
                rows.append(site.reshape(-1))
                continue
            rows.append(np.concatenate(
                [site.reshape(-1),
                 self._strain_row(dof, x, coordinate).reshape(-1)]))
        return np.array(rows)

    @staticmethod
    def _strain_row(dof, x, coordinate, step=1e-6) -> np.ndarray:
        out = np.zeros((2, 3))
        flat = out.reshape(-1)
        for k in range(6):
            high = np.array(x, dtype=float, copy=True)
            high[dof.n_sites:].reshape(-1)[k] += step
            low = np.array(x, dtype=float, copy=True)
            low[dof.n_sites:].reshape(-1)[k] -= step
            up = coordinate.value(dof.positions(high),
                                  dof.matrix_of(high))
            down = coordinate.value(dof.positions(low),
                                    dof.matrix_of(low))
            flat[k] = (up - down) / (2.0 * step)
        return out

    # -- what the optimiser asks for -----------------------------------

    def check(self, dof, x) -> None:
        """Refuse a coordinate the variables cannot move.

        A distance between two atoms the space group holds apart, a
        plane angle whose atoms do not fix a normal, an angle sitting
        exactly at zero where it folds: in each the row is zero, the
        normal equations are singular, and without this the failure is
        a ``LinAlgError`` several screens below anything the user did.
        """
        rows = self.matrix(dof, x)
        scale = float(np.abs(rows).max()) if rows.size else 0.0
        for row, (coordinate, _target) in zip(rows, self.pairs,
                                              strict=True):
            if float(np.abs(row).max()) <= SINGULAR * max(scale, 1.0):
                raise ConstraintError(
                    f"nothing the optimiser may change moves the "
                    f"{coordinate.label}: the space group ties it, or "
                    f"its atoms are frozen, or it sits where it is "
                    f"undefined.  Reduce to P1 first, or scan a "
                    f"coordinate the symmetry leaves free.")

    def project(self, dof, direction, x) -> np.ndarray:
        """``direction`` with the part that would move a held
        coordinate taken out of it."""
        rows = self.matrix(dof, x)
        flat = np.asarray(direction, dtype=float).reshape(-1)
        correction = rows.T @ _solve(rows, rows @ flat)
        return (flat - correction).reshape(np.shape(direction))

    def restore(self, dof, x) -> np.ndarray:
        """``x`` moved back onto the constraint, along the shortest
        way there.

        Newton on the residual: each pass solves for the multipliers
        that would cancel it to first order and recomputes, because a
        torsion is not linear in the coordinates and one pass is not
        enough when the step was large.  The correction lies in the
        row space of a matrix that has already been through the site
        projectors and the frozen mask, so restoring can no more break
        a special position than stepping can.
        """
        out = np.array(x, dtype=float, copy=True)
        tolerances = self.tolerances()
        for _ in range(MAX_RESTORE):
            residual = self.residual(dof, out)
            if np.all(np.abs(residual) <= tolerances):
                return out
            rows = self.matrix(dof, out)
            correction = rows.T @ _solve(rows, residual)
            out = out - correction.reshape(out.shape)
        return out


def _solve(rows, right) -> np.ndarray:
    """``(A A^T)^-1 b``, tolerating a rank the caller has not checked.

    ``check`` refuses a genuinely immovable coordinate up front.  This
    is the other case: two coordinates that are independent where the
    scan started and become parallel somewhere in the middle of it.
    The least-squares answer is the smallest correction that does as
    much as can be done, which keeps the point on whichever
    constraints are still reachable instead of failing the run.
    """
    gram = rows @ rows.T
    try:
        return np.linalg.solve(gram, right)
    except np.linalg.LinAlgError:
        return np.linalg.lstsq(gram, right, rcond=None)[0]
