"""
xtal.ff.optimize
================
Geometry optimisation: FIRE and L-BFGS, over degrees of freedom that
respect the space group.

**The variables are the asymmetric unit, not the cell.**  A calculator
works on the P1 cell, because that is what has an energy; an optimiser
that moved those atoms independently would break the symmetry of the
structure on the first step, and there would then be no way to write
the answer back -- a structure in P4_2/mnm has nowhere to put six
independently displaced oxygens.  So the variables here are the sites
of the asymmetric unit, the P1 cell is regenerated from them at every
step, and the gradient is carried back through the symmetry operations
that generated it.

That one decision gives three things at once.  Symmetry is preserved
exactly, and for free.  An atom on a special position stays on it,
because the step is projected onto the subspace its site symmetry
leaves invariant -- the oxygen of rutile relaxes along the [110]
direction it is free in and nowhere else.  And a structure already in
P1 falls out as the ordinary case, with every atom free, no projection,
and no special path through the code.

**Optimisers are generators.**  Each yields a :class:`Step` per
iteration and then waits.  The GUI's worker thread uses that to draw
the geometry as it moves, to pause, and to cancel without leaving a
half-applied structure behind; the CLI uses it to print a line per
step; the tests use it to assert on the trajectory rather than only on
the answer.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

import numpy as np

from xtal.core import p1
from xtal.ff.api import CalculatorError

# Convergence: the largest force on any atom, in kcal/mol/Angstrom.
# Loose enough to reach on a framework, tight enough that the geometry
# has stopped moving visibly.
DEFAULT_FORCE_TOLERANCE = 0.05
DEFAULT_MAX_STEPS = 200
# No single step moves an atom further than this, whatever the
# optimiser asks for.  A bad first guess -- two atoms almost on top of
# each other, which happens whenever someone builds by hand -- gives a
# force of tens of thousands, and without a cap the first step throws
# the atom out of the crystal.
DEFAULT_MAX_STEP = 0.2


@dataclass(frozen=True)
class Step:
    """One iteration, as the caller sees it."""

    iteration: int
    energy: float
    max_force: float                # per atom, after symmetry projection
    rms_force: float
    frac: np.ndarray                # (n_sites, 3) asymmetric unit
    terms: dict = field(default_factory=dict)
    converged: bool = False

    def line(self) -> str:
        return (f"{self.iteration:5d}  E = {self.energy:14.5f}  "
                f"|F|max = {self.max_force:10.5f}")


@dataclass
class OptimizationResult:
    """What the optimisation did, for the report and the command."""

    converged: bool
    steps: int
    initial_energy: float
    energy: float
    max_force: float
    frac: np.ndarray
    terms: dict = field(default_factory=dict)
    history: list = field(default_factory=list)   # (step, E, |F|max)
    message: str = ""

    @property
    def energy_change(self) -> float:
        return self.energy - self.initial_energy

    def summary(self) -> str:
        verdict = ("converged" if self.converged
                   else "stopped without converging")
        return (f"{verdict} after {self.steps} steps: "
                f"{self.energy_change:+.4f} kcal/mol to "
                f"{self.energy:.4f}, |F|max {self.max_force:.4f} "
                f"kcal/mol/A")


# ======================================================================
#  DEGREES OF FREEDOM
# ======================================================================

class SymmetryDOF:
    """The asymmetric unit as the variables, the P1 cell as the value.

    Every atom of the cell is ``x_parent @ W + b`` for a rotation ``W``
    and an offset ``b`` fixed by the operation that generated it, so
    moving a site moves its whole orbit rigidly and correctly.  The
    gradient comes back the same way, through ``W`` transposed.

    ``project`` is the part that keeps special positions special.  The
    operations that map a site onto itself form its site-symmetry
    group, and the average of their (orthogonal) cartesian matrices is
    the projector onto the displacements they all leave alone.  A site
    on a three-fold axis is projected onto that axis; a site on a
    general position is projected onto everything, which is no
    projection at all.
    """

    def __init__(self, structure, frozen=()):
        self.structure = structure
        self.cell = p1.expand(structure)
        self.matrix = structure.lattice.matrix
        self.inverse = np.linalg.inv(self.matrix)
        self.n_sites = structure.n_sites
        self.frozen = {int(i) for i in frozen}

        ops = structure.space_group.operations
        n = self.cell.n_atoms
        self.parent = np.asarray(self.cell.site_idx, dtype=int)
        rotations = np.zeros((n, 3, 3))
        offsets = np.zeros((n, 3))
        for k in range(n):
            op = ops[int(self.cell.op_idx[k])]
            rotations[k] = self.inverse @ op.rot.T @ self.matrix
            offsets[k] = (op.trans + self.cell.tau[k]) @ self.matrix
        self.rotations = rotations
        self.offsets = offsets
        self.multiplicity = np.maximum(
            self.cell.multiplicities(self.n_sites), 1)
        self.projectors = self._projectors(ops)

        self.free = np.array([i not in self.frozen
                              for i in range(self.n_sites)])
        if not self.free.any():
            raise CalculatorError(
                "every site is frozen, so there is nothing to relax")

    def _projectors(self, ops) -> np.ndarray:
        """One (3,3) projector per site: what its site symmetry lets it
        do."""
        out = np.zeros((self.n_sites, 3, 3))
        for index, site in enumerate(self.structure.sites):
            stabiliser = []
            for op in ops:
                shift = op.apply(site.frac) - site.frac
                if np.allclose(shift, np.round(shift), atol=1e-6):
                    stabiliser.append(
                        self.inverse @ op.rot.T @ self.matrix)
            out[index] = (np.mean(stabiliser, axis=0) if stabiliser
                          else np.eye(3))
        return out

    # -- the mapping ---------------------------------------------------

    @property
    def start(self) -> np.ndarray:
        """Cartesian coordinates of the sites, the initial variables."""
        return self.structure.frac @ self.matrix

    def positions(self, x) -> np.ndarray:
        """P1 cartesian positions for these site coordinates."""
        return (np.einsum("kj,kji->ki", x[self.parent], self.rotations)
                + self.offsets)

    def gradient(self, cell_gradient) -> np.ndarray:
        """The P1 gradient, carried back onto the sites and projected.

        Summing over the orbit is not an approximation: displacing a
        site displaces every one of its images, so the derivative with
        respect to the site really is the sum of the derivatives with
        respect to them.
        """
        per_atom = np.einsum("kj,kij->ki", cell_gradient,
                             self.rotations)
        out = np.zeros((self.n_sites, 3))
        np.add.at(out, self.parent, per_atom)
        out = np.einsum("sj,sji->si", out, self.projectors)
        out[~self.free] = 0.0
        return out

    def to_frac(self, x) -> np.ndarray:
        return x @ self.inverse

    def force_scale(self) -> np.ndarray:
        """Divide a site gradient by this to get a force per atom.

        A site of multiplicity four collects four atoms' worth of
        gradient, so the raw number is four times what a
        crystallographer would call the force on that atom -- and a
        tolerance of 0.05 would mean something different for every
        Wyckoff position.
        """
        return self.multiplicity.astype(float)[:, None]


# ======================================================================
#  THE OPTIMISERS
# ======================================================================

class _Problem:
    """Energy and gradient in the variables the optimisers see."""

    def __init__(self, calculator, dof):
        self.calculator = calculator
        self.dof = dof
        self.evaluations = 0
        self.terms: dict = {}

    def __call__(self, x):
        self.evaluations += 1
        result = self.calculator.compute(self.dof.positions(x),
                                         self.dof.matrix)
        self.terms = result.terms
        return result.energy, self.dof.gradient(-result.forces)

    def forces(self, gradient):
        """``(max, rms)`` force per atom for a site gradient."""
        scaled = gradient / self.dof.force_scale()
        norms = np.linalg.norm(scaled, axis=1)
        if not len(norms):                          # pragma: no cover
            return 0.0, 0.0
        return float(norms.max()), float(
            np.sqrt(np.mean(norms ** 2)))


def _capped(step, limit: float) -> np.ndarray:
    """Nothing moves further than ``limit`` in one iteration."""
    longest = np.linalg.norm(step, axis=1).max() if len(step) else 0.0
    if longest > limit:
        step = step * (limit / longest)
    return step


def fire(calculator, structure, dof=None, max_steps=DEFAULT_MAX_STEPS,
         force_tolerance=DEFAULT_FORCE_TOLERANCE,
         max_step=DEFAULT_MAX_STEP, dt=0.1, dt_max=1.0, n_min=5,
         f_inc=1.1, f_dec=0.5, alpha_start=0.1,
         f_alpha=0.99) -> Iterator[Step]:
    """FIRE (Bitzek et al., *Phys. Rev. Lett.* **2006**, 97, 170201).

    Molecular dynamics with the velocity steered towards the force and
    the time step grown while progress continues, thrown away the
    moment it stops.  Slower than L-BFGS near a minimum and far more
    forgiving a long way from one, which is what a hand-built
    structure needs.
    """
    dof = dof or SymmetryDOF(structure)
    problem = _Problem(calculator, dof)
    x = dof.start.copy()
    velocity = np.zeros_like(x)
    alpha = alpha_start
    since_uphill = 0

    energy, gradient = problem(x)
    for iteration in range(max_steps + 1):
        peak, rms = problem.forces(gradient)
        converged = peak <= force_tolerance
        yield Step(iteration, energy, peak, rms, dof.to_frac(x),
                   dict(problem.terms), converged)
        if converged or iteration == max_steps:
            return

        force = -gradient
        power = float(np.sum(force * velocity))
        if power > 0.0:
            norm_f = np.linalg.norm(force)
            norm_v = np.linalg.norm(velocity)
            if norm_f > 0:
                velocity = ((1.0 - alpha) * velocity
                            + alpha * norm_v * force / norm_f)
            if since_uphill > n_min:
                dt = min(dt * f_inc, dt_max)
                alpha *= f_alpha
            since_uphill += 1
        else:
            velocity = np.zeros_like(x)
            since_uphill = 0
            dt *= f_dec
            alpha = alpha_start

        velocity = velocity + dt * force
        x = x + _capped(dt * velocity, max_step)
        energy, gradient = problem(x)


def lbfgs(calculator, structure, dof=None,
          max_steps=DEFAULT_MAX_STEPS,
          force_tolerance=DEFAULT_FORCE_TOLERANCE,
          max_step=DEFAULT_MAX_STEP, memory=10,
          c1=1e-4) -> Iterator[Step]:
    """L-BFGS with a backtracking line search.

    The inverse Hessian is never formed; the last ``memory`` pairs of
    (step, change in gradient) stand in for it through the two-loop
    recursion.  Curvature pairs that fail the ``s . y > 0`` test are
    dropped rather than stored: keeping one makes the approximation
    indefinite, and the next direction points uphill.
    """
    dof = dof or SymmetryDOF(structure)
    problem = _Problem(calculator, dof)
    x = dof.start.copy()
    energy, gradient = problem(x)
    history: list[tuple[np.ndarray, np.ndarray, float]] = []

    for iteration in range(max_steps + 1):
        peak, rms = problem.forces(gradient)
        converged = peak <= force_tolerance
        yield Step(iteration, energy, peak, rms, dof.to_frac(x),
                   dict(problem.terms), converged)
        if converged or iteration == max_steps:
            return

        direction = -_two_loop(gradient, history)
        slope = float(np.sum(gradient * direction))
        if slope >= 0.0:
            # The approximation has gone bad -- start again from
            # steepest descent rather than walking uphill.
            history.clear()
            direction = -gradient
            slope = float(np.sum(gradient * direction))

        length = 1.0
        longest = np.linalg.norm(direction, axis=1).max()
        if longest > max_step:
            length = max_step / longest

        for _attempt in range(20):
            trial = x + length * direction
            new_energy, new_gradient = problem(trial)
            if new_energy <= energy + c1 * length * slope:
                break
            length *= 0.5
        else:
            return                          # the line search gave up

        s = trial - x
        y = new_gradient - gradient
        curvature = float(np.sum(s * y))
        if curvature > 1e-12:
            history.append((s, y, 1.0 / curvature))
            if len(history) > memory:
                history.pop(0)
        x, energy, gradient = trial, new_energy, new_gradient


def _two_loop(gradient, history) -> np.ndarray:
    """The L-BFGS two-loop recursion: the inverse Hessian applied to
    the gradient without ever building it."""
    q = gradient.copy()
    alphas = []
    for s, y, rho in reversed(history):
        alpha = rho * float(np.sum(s * q))
        alphas.append(alpha)
        q = q - alpha * y
    if history:
        s, y, _rho = history[-1]
        scale = float(np.sum(s * y)) / float(np.sum(y * y))
        q = q * scale
    for (s, y, rho), alpha in zip(history, reversed(alphas),
                                  strict=True):
        beta = rho * float(np.sum(y * q))
        q = q + s * (alpha - beta)
    return q


METHODS = {"fire": fire, "lbfgs": lbfgs}


# ======================================================================
#  RUNNING ONE TO THE END
# ======================================================================

def steps(calculator, structure, method: str = "lbfgs",
          frozen=(), **kwargs) -> Iterator[Step]:
    """The chosen optimiser, as a generator of steps."""
    try:
        optimizer = METHODS[method]
    except KeyError:
        raise ValueError(
            f"unknown optimiser {method!r}; "
            f"have {', '.join(sorted(METHODS))}") from None
    dof = SymmetryDOF(structure, frozen)
    return optimizer(calculator, structure, dof=dof, **kwargs)


def run(calculator, structure, method: str = "lbfgs", frozen=(),
        callback=None, **kwargs) -> OptimizationResult:
    """Optimise to convergence (or to the step limit) and report.

    ``callback(step)`` is called after each iteration and may return
    ``False`` to stop early -- which is how the CLI prints a running
    trace, and how a caller without a thread cancels.
    """
    history = []
    first = last = None
    stopped = False
    for step in steps(calculator, structure, method, frozen, **kwargs):
        history.append((step.iteration, step.energy, step.max_force))
        if first is None:
            first = step
        last = step
        if callback is not None and callback(step) is False:
            stopped = True
            break

    if last is None:                                # pragma: no cover
        raise CalculatorError("the optimiser produced no steps")
    message = last.line()
    if stopped:
        message = f"stopped by the caller at step {last.iteration}"
    return OptimizationResult(
        converged=last.converged and not stopped,
        steps=last.iteration,
        initial_energy=first.energy,
        energy=last.energy,
        max_force=last.max_force,
        frac=last.frac,
        terms=dict(last.terms),
        history=history,
        message=message,
    )
