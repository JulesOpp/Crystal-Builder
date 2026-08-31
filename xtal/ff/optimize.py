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

**The cell can be a variable too.**  Six strain components sit
alongside the site coordinates in the same flat vector, so FIRE and
L-BFGS relax a lattice constant without either of them knowing that is
what they are doing.  The strain is *symmetry-adapted* by the same
argument that keeps an atom on its special position -- averaged over
the point group, which leaves a cubic cell with one free strain and a
hexagonal one with two -- and an external pressure enters as a ``P V``
term.  See :class:`SymmetryDOF`.

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

# 1 GPa, in the units everything here works in.  A pressure times a
# volume has to come out as an energy, and this is the one place a
# factor can quietly go missing: energies are kcal/mol, volumes are
# Angstrom^3, and 1 GPa is 10^9 J/m^3 = 10^-21 J/A^3, which is
# 10^-21 * N_A / 4184 kcal/mol per A^3.  The inverse, 6.9477, is the
# number of GPa in one kcal/mol/A^3 and is worth recognising.
GPA = 1e-21 * 6.02214076e23 / 4184.0        # 0.143933 kcal/mol/A^3


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
    # The cell at this step, when the cell is being relaxed too, and
    # ``None`` when it is not.  Fractional coordinates are unchanged by
    # a strain, so ``frac`` means the same thing either way and only
    # this is added.
    matrix: np.ndarray | None = None
    cell_force: float = 0.0         # the strain gradient, per atom

    def line(self) -> str:
        cell = ("" if self.matrix is None else
                f"  |dE/de| = {self.cell_force:9.5f}")
        return (f"{self.iteration:5d}  E = {self.energy:14.5f}  "
                f"|F|max = {self.max_force:10.5f}{cell}")


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
    matrix: np.ndarray | None = None        # the relaxed cell, or None
    initial_matrix: np.ndarray | None = None

    @property
    def energy_change(self) -> float:
        return self.energy - self.initial_energy

    @property
    def volume_change(self) -> float:
        """Fractional change in the cell volume, 0 if it was fixed."""
        if self.matrix is None or self.initial_matrix is None:
            return 0.0
        before = abs(float(np.linalg.det(self.initial_matrix)))
        after = abs(float(np.linalg.det(self.matrix)))
        return (after - before) / before if before else 0.0

    def summary(self) -> str:
        verdict = ("converged" if self.converged
                   else "stopped without converging")
        cell = ("" if self.matrix is None else
                f", cell {self.volume_change * 100:+.2f}% by volume")
        return (f"{verdict} after {self.steps} steps: "
                f"{self.energy_change:+.4f} kcal/mol to "
                f"{self.energy:.4f}, |F|max {self.max_force:.4f} "
                f"kcal/mol/A{cell}")


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

    **With ``relax_cell``, six more variables.**  The cell is deformed
    by ``F = I + e`` for a symmetric strain ``e``: the lattice matrix
    becomes ``M F``, and every atom is carried with it, ``r F``.  The
    site variables stay in the *undeformed* frame, which is what makes
    the two sets of variables independent and the fractional
    coordinates -- what a structure actually stores -- unchanged by a
    strain.

    The strain is symmetry-adapted by the same argument as the site
    projection, one rank up.  A strain is a rank-2 tensor, so the
    operation that acts on a displacement as ``u W`` acts on it as
    ``W^T e W``, and the average of that over the group is the
    projector onto the strains the group allows.  It needs no table of
    crystal systems: a cubic group leaves one free strain (the
    isotropic one), a hexagonal group two, a triclinic group all six,
    and the cell cannot leave its crystal system because there is no
    variable that would take it there.

    Two scalings make the six new variables behave like the old ones,
    so that FIRE's step cap and L-BFGS's line search need no special
    case.  The variable stored is the strain times a cell length, so a
    step in it is a distance; and the gradient is divided by the number
    of atoms, so the number compared against the force tolerance is a
    force per atom rather than a quantity that grows with the cell.
    """

    def __init__(self, structure, frozen=(), relax_cell: bool = False,
                 pressure: float = 0.0):
        self.structure = structure
        self.cell = p1.expand(structure)
        self.matrix = structure.lattice.matrix
        self.inverse = np.linalg.inv(self.matrix)
        self.n_sites = structure.n_sites
        self.frozen = {int(i) for i in frozen}
        self.relax_cell = bool(relax_cell)
        self.pressure = float(pressure)         # GPa
        self.volume = abs(float(np.linalg.det(self.matrix)))
        # One cell length, to give the strain variables the units of a
        # distance.  Without it a "step" of 0.2 would be a 20% strain.
        self.cell_scale = self.volume ** (1.0 / 3.0) if self.volume \
            else 1.0

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
        self.point_group = np.array(
            [self.inverse @ op.rot.T @ self.matrix for op in ops])

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

    # -- the strain ----------------------------------------------------

    def strain(self, x) -> np.ndarray:
        """The (3,3) symmetric strain these variables describe.

        Projected on the way out, so the answer is always one the
        space group allows however the optimiser got here -- and so
        the energy really is a function of the projected variables,
        which is what makes the projected gradient the right one.
        """
        if not self.relax_cell:
            return np.zeros((3, 3))
        voigt = np.asarray(x[self.n_sites:]).reshape(6) \
            / self.cell_scale
        return self.project_strain(_from_voigt(voigt))

    def project_strain(self, tensor) -> np.ndarray:
        """The part of a strain the space group leaves alone.

        A displacement transforms as ``u W`` and a strain, being one
        rank up, as ``W^T e W``; averaging that over the group is the
        projector onto the strains every operation preserves.  For a
        cubic group the image is the isotropic strain alone, which is
        why a cubic cell relaxed here stays cubic -- not because
        anything checks that it did.
        """
        tensor = np.asarray(tensor, dtype=float)
        tensor = 0.5 * (tensor + tensor.T)
        if not len(self.point_group):                # pragma: no cover
            return tensor
        averaged = np.einsum("gji,jk,gkl->il", self.point_group,
                             tensor, self.point_group)
        averaged /= len(self.point_group)
        return 0.5 * (averaged + averaged.T)

    def deformation(self, x) -> np.ndarray:
        """``F = I + e``: what the cell and every atom are multiplied
        by."""
        return np.eye(3) + self.strain(x)

    def matrix_of(self, x) -> np.ndarray:
        """The lattice at these variables."""
        if not self.relax_cell:
            return self.matrix
        return self.matrix @ self.deformation(x)

    def pressure_energy(self, x) -> float:
        """``P V`` in kcal/mol, so that "what does this do at 5 GPa" is
        a number in the panel rather than a separate script."""
        if not (self.relax_cell and self.pressure):
            return 0.0
        volume = self.volume * abs(float(np.linalg.det(
            self.deformation(x))))
        return self.pressure * GPA * volume

    # -- the mapping ---------------------------------------------------

    @property
    def start(self) -> np.ndarray:
        """Cartesian coordinates of the sites, the initial variables.

        With the cell relaxing, two more rows carrying the six strain
        components -- all zero, because the strain is measured from the
        cell the user handed us.
        """
        sites = self.structure.frac @ self.matrix
        if not self.relax_cell:
            return sites
        return np.vstack([sites, np.zeros((2, 3))])

    def sites_of(self, x) -> np.ndarray:
        """The site rows of the variable vector."""
        return x[:self.n_sites] if self.relax_cell else x

    def positions(self, x) -> np.ndarray:
        """P1 cartesian positions for these variables."""
        undeformed = (np.einsum("kj,kji->ki",
                                self.sites_of(x)[self.parent],
                                self.rotations) + self.offsets)
        if not self.relax_cell:
            return undeformed
        return undeformed @ self.deformation(x)

    def gradient(self, cell_gradient, x=None,
                 stress=None) -> np.ndarray:
        """The P1 gradient, carried back onto the variables.

        Summing over the orbit is not an approximation: displacing a
        site displaces every one of its images, so the derivative with
        respect to the site really is the sum of the derivatives with
        respect to them.

        With the cell relaxing there are two more things to do.  The
        atomic gradient is carried out of the deformed frame (through
        ``F^T``, because a site variable reaches the energy as
        ``x F``), and the strain gradient is read off the **stress**,
        which is what a stress is: ``dE/de = V sigma``.
        """
        deformation = (self.deformation(x) if self.relax_cell
                       else None)
        if deformation is not None:
            cell_gradient = cell_gradient @ deformation.T
        per_atom = np.einsum("kj,kij->ki", cell_gradient,
                             self.rotations)
        out = np.zeros((self.n_sites, 3))
        np.add.at(out, self.parent, per_atom)
        out = np.einsum("sj,sji->si", out, self.projectors)
        out[~self.free] = 0.0
        if not self.relax_cell:
            return out
        return np.vstack([out, self.strain_gradient(x, stress)])

    def strain_gradient(self, x, stress) -> np.ndarray:
        """``dE/de``, projected, in Voigt order and in the variable's
        own scaling.

        The pressure rides along here: ``d(P V)/de = P V I``, so an
        external pressure is one term added to the diagonal of the
        stress and nothing else in the optimiser changes.
        """
        deformation = self.deformation(x)
        volume = self.volume * abs(float(np.linalg.det(deformation)))
        total = np.asarray(stress, dtype=float)
        if self.pressure:
            total = total + self.pressure * GPA * np.eye(3)
        # The stress is the derivative with respect to a strain
        # applied to the *current* cell (``F -> F(I+d)``), while the
        # variable enters additively (``F -> F + dF``).  The two are
        # related by ``d = F^-1 dF``, so the derivative with respect to
        # the variable carries the inverse of the deformation already
        # there -- which is the identity on the first step and a few
        # percent by the last.
        gradient = np.linalg.inv(deformation).T @ (volume * total)
        gradient = self.project_strain(gradient)
        return (_to_voigt(gradient).reshape(2, 3)
                / self.cell_scale)

    def to_frac(self, x) -> np.ndarray:
        """Fractional coordinates of the sites.

        A strain leaves these alone -- it multiplies the atoms and the
        cell by the same thing -- which is why a step reports them
        whether the cell is relaxing or not.
        """
        return self.sites_of(x) @ self.inverse

    def force_scale(self) -> np.ndarray:
        """Divide a site gradient by this to get a force per atom.

        A site of multiplicity four collects four atoms' worth of
        gradient, so the raw number is four times what a
        crystallographer would call the force on that atom -- and a
        tolerance of 0.05 would mean something different for every
        Wyckoff position.  The strain rows are divided by the whole
        cell for the same reason: the stress is a sum over every atom
        in it.
        """
        scale = self.multiplicity.astype(float)[:, None]
        if not self.relax_cell:
            return scale
        atoms = max(self.cell.n_atoms, 1)
        return np.vstack([scale, np.full((2, 1), float(atoms))])


def _to_voigt(tensor) -> np.ndarray:
    """A symmetric tensor as six numbers.

    The off-diagonals are doubled because the variable is one number
    standing for two equal components, so its derivative collects both.
    """
    return np.array([tensor[0, 0], tensor[1, 1], tensor[2, 2],
                     2 * tensor[1, 2], 2 * tensor[0, 2],
                     2 * tensor[0, 1]])


def _from_voigt(voigt) -> np.ndarray:
    a, b, c, d, e, f = (float(v) for v in voigt)
    return np.array([[a, f, e], [f, b, d], [e, d, c]])


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
        matrix = self.dof.matrix_of(x)
        positions = self.dof.positions(x)
        result = self.calculator.compute(positions, matrix)
        self.terms = result.terms
        if not self.dof.relax_cell:
            return result.energy, self.dof.gradient(-result.forces)

        # An engine that computes its own stress is asked for it; one
        # that does not gets it by central differences, which is
        # twelve more energy evaluations a step.  Affordable for a few
        # hundred atoms, not for a few thousand -- and the reason the
        # first thing to write after this is an analytic virial.
        stress = result.stress
        if stress is None:
            stress = self.calculator.numeric_stress(positions, matrix)
        energy = result.energy + self.dof.pressure_energy(x)
        return energy, self.dof.gradient(-result.forces, x=x,
                                         stress=stress)

    def forces(self, gradient):
        """``(max, rms)`` force per atom, over the *atoms*.

        Deliberately not over the strain rows as well: |F|max is a
        number a user compares between runs and against a tolerance
        they know, and quietly redefining it the moment the cell is
        allowed to move would make two runs of the same structure
        incomparable.  The cell's own convergence is
        :meth:`cell_force`, reported beside it.
        """
        scaled = (gradient / self.dof.force_scale())[:self.dof.n_sites]
        norms = np.linalg.norm(scaled, axis=1)
        if not len(norms):                          # pragma: no cover
            return 0.0, 0.0
        return float(norms.max()), float(
            np.sqrt(np.mean(norms ** 2)))

    def cell_force(self, gradient) -> float:
        """How far from relaxed the cell is, per atom.

        The same units and the same scaling as an atomic force, so the
        one tolerance covers both -- which is the whole reason the
        strain variables were given the units of a distance.
        """
        if not self.dof.relax_cell:
            return 0.0
        scaled = (gradient / self.dof.force_scale())[self.dof.n_sites:]
        return float(np.abs(scaled).max())


def _step(iteration: int, energy: float, gradient, x, dof, problem,
          force_tolerance: float) -> Step:
    """One iteration, packaged for the caller.

    Convergence is both halves when both are variables: a cell still
    under a stress is not a relaxed structure, however still its atoms
    are.
    """
    peak, rms = problem.forces(gradient)
    cell = problem.cell_force(gradient)
    return Step(
        iteration, energy, peak, rms, dof.to_frac(x),
        dict(problem.terms),
        converged=(peak <= force_tolerance
                   and cell <= force_tolerance),
        matrix=(dof.matrix_of(x) if dof.relax_cell else None),
        cell_force=cell,
    )


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
        yield (step := _step(iteration, energy, gradient, x, dof,
                             problem, force_tolerance))
        if step.converged or iteration == max_steps:
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
        yield (step := _step(iteration, energy, gradient, x, dof,
                             problem, force_tolerance))
        if step.converged or iteration == max_steps:
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
          frozen=(), relax_cell: bool = False, pressure: float = 0.0,
          **kwargs) -> Iterator[Step]:
    """The chosen optimiser, as a generator of steps.

    ``relax_cell`` adds the six symmetry-adapted strain components to
    the variables; ``pressure`` is in GPa and is applied only when the
    cell can respond to it.
    """
    try:
        optimizer = METHODS[method]
    except KeyError:
        raise ValueError(
            f"unknown optimiser {method!r}; "
            f"have {', '.join(sorted(METHODS))}") from None
    dof = SymmetryDOF(structure, frozen, relax_cell=relax_cell,
                      pressure=pressure)
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
    for step in steps(calculator, structure, method, frozen,
                      **kwargs):
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
        matrix=last.matrix,
        initial_matrix=(None if last.matrix is None
                        else structure.lattice.matrix),
    )
