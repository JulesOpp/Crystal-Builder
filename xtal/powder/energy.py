"""
xtal.powder.energy
==================
Rietveld with energies: the atoms fitted to the pattern and to a force
field at once, as Materials Studio's Reflex does.

**The objective is one number with a weight in it**::

    f = (1 - w) chi2 / chi2_0 + w (E - E_0) / dE

``chi2_0`` and ``E_0`` are the pattern's misfit and the energy where
the run starts, and ``dE`` is how far the energy falls when the atoms
answer to it alone -- one force-field relaxation at the same cell,
which is the ``w = 1`` end.  Both terms are then of order one, so a
weight means the same thing on rutile and on a framework of a
thousand atoms, and ``w = 0.5`` is an even split rather than whichever
term has the larger units.

**RietX has no cost term of anyone else's**, so the minimiser is ours:
scipy's L-BFGS over RietX's own variables -- each atom a step along
the directions its site allows, and the cell's free numbers when the
cell is let move.  The pattern's gradient is RietX's analytic Jacobian
(:class:`~xtal.powder.bridge.PatternTerm`), the energy's the engine's
forces carried back over each orbit.  **A site on a special position
stays on it** because there is no variable that would take it off:
the directions are the site's, and the energy's gradient is only ever
read along them.

**What the Rietveld step's boxes free is fitted first and then held**:
the scale, background, zero and peak shape are the pattern's, fitted
with the atoms and the cell where they are, before the atoms are asked
to answer to anything.  The cell is held by default -- Julius's
choice; a cell that moves under an energy is a different experiment
-- and, let move, its energy gradient is the engine's stress.

**The engine is read, never configured** (``build``): the Force Field
panel's, markers held back at the door by
:meth:`~xtal.ff.registry.Engine.__call__`, as a scan reads it.

**Nothing here touches a document**, as in :mod:`xtal.powder.rietveld`:
frames go out through ``on_frame`` and the refined structure comes
back, with the same sites and the same bonds.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np

from xtal.powder.data import PowderData, PowderError, PowderStopped, Radiation
from xtal.powder.rietveld import RietveldFit, RietveldFrame, RietveldOptions

__all__ = ["EnergyFit", "EnergyOptions", "EnergyProblem", "EnergyScale",
           "rietveld_with_energy"]

#: The smallest ``dE`` the energy term is divided by, in kcal/mol.  A
#: structure that is already at the force field's minimum falls by
#: nothing, and dividing by that would hand the whole objective to the
#: energy at any weight at all.
MIN_ENERGY_DROP = 0.1

#: When a relaxation (the ``w = 1`` end) counts as done: the largest
#: gradient along any variable, in kcal/mol/Å -- the variables are
#: scaled to Å, so this is a force.
RELAX_TOLERANCE = 1e-3


@dataclass(frozen=True)
class EnergyOptions:
    """What the step asks.

    ``weight`` is ``w``: 0 is the pattern alone, 1 the force field
    alone.  ``cell`` lets the cell move with the atoms.  ``rietveld``
    is the Rietveld step's boxes and range, for the fit that comes
    first -- its atoms, cell and occupancies are never freed there.
    """

    weight: float = 0.1
    cell: bool = False
    max_steps: int = 500
    rietveld: RietveldOptions = field(default_factory=RietveldOptions)


@dataclass(frozen=True)
class EnergyScale:
    """The two ends a weight is measured between.

    ``chi2`` and ``energy`` are where the run started; ``relaxed`` is
    the energy with the atoms answering to it alone, and
    ``relaxed_rwp`` the pattern's Rwp there.  A sweep of weights over
    one pattern and one engine computes this once and hands it back.
    """

    chi2: float
    energy: float
    rwp: float
    relaxed: float = math.nan
    relaxed_rwp: float = math.nan

    @property
    def drop(self) -> float:
        """``dE``: how far the energy falls alone, floored."""
        if math.isnan(self.relaxed):
            return math.nan
        return max(abs(self.energy - self.relaxed), MIN_ENERGY_DROP)


@dataclass
class EnergyFit(RietveldFit):
    """A Rietveld-with-energy fit: a Rietveld fit, and the energy."""

    weight: float = 0.0
    #: kcal/mol, of the whole cell, at the answer
    energy: float = math.nan
    scale: EnergyScale | None = None
    #: the engine's name, as the Force Field panel offers it
    engine: str = ""
    steps: int = 0


def rietveld_with_energy(structure, data: PowderData,
                         radiation: Radiation, build,
                         options: EnergyOptions | None = None, *,
                         engine: str = "", scale: EnergyScale | None = None,
                         on_frame=None, frame_interval: float = 0.2,
                         cancel=None, folder=None, say=None) -> EnergyFit:
    """Refine ``structure`` against ``data`` and an energy at once.

    ``build(structure)`` makes the engine's calculator.  ``scale``, if
    given, is a previous run's :class:`EnergyScale` over the same
    pattern, engine and start, and saves the relaxation.  Stop raises
    :class:`~xtal.powder.data.PowderStopped`; putting the atoms back is
    the caller's, as for Rietveld.
    """
    options = options or EnergyOptions()
    weight = float(options.weight)
    _check_weight(weight)
    problem = EnergyProblem(structure, data, radiation, build, options,
                            engine=engine, scale=scale,
                            on_frame=on_frame,
                            frame_interval=frame_interval,
                            cancel=cancel, folder=folder, say=say)
    relaxation = None
    if weight == 1.0 or (weight > 0.0 and problem.needs_relaxation):
        relaxation = problem.relax()
    if weight == 1.0:
        answer, steps, converged, why = relaxation
    else:
        answer, steps, converged, why = problem.solve(weight)
    return problem.fit(answer, weight, steps, converged, why)


def _check_weight(weight: float) -> None:
    if not 0.0 <= weight <= 1.0:
        raise PowderError(f"the weight is {weight:g}; it runs from 0, "
                          f"the pattern alone, to 1, the energy alone")


class EnergyProblem:
    """One pattern, one engine, one start: the objective at any weight.

    Built once -- the scale, background and peak shape fitted, RietX's
    model compiled, the engine made -- and then minimised at as many
    weights as are asked, each from wherever the caller says.  That is
    what a sweep of weights needs (:mod:`xtal.powder.pareto`): every
    point on one objective family, with the pattern's own parameters
    the same at each, rather than a front whose points were each
    scored against a background of their own.
    """

    def __init__(self, structure, data: PowderData, radiation: Radiation,
                 build, options: EnergyOptions, *, engine: str = "",
                 scale: EnergyScale | None = None, on_frame=None,
                 frame_interval: float = 0.2, cancel=None, folder=None,
                 say=None):
        from xtal.powder import bridge

        self.structure, self.options = structure, options
        self.radiation = radiation
        self.engine_name = engine
        self.cancel = cancel
        self.say = say or (lambda _text: None)
        boxes = options.rietveld
        window = data.window(boxes.start or None, boxes.finish or None)

        self.say("fitting the scale, background and peak shape")
        term, result, indices, refinement = bridge.pattern_term(
            structure, window, radiation, free=boxes.free(radiation),
            background_terms=boxes.background_terms,
            preferred_axis=boxes.preferred_axis, cell=options.cell,
            folder=folder, cancel=bridge.cancel_token(cancel))
        self.term, self.result = term, result
        self.indices, self.refinement = indices, refinement
        self.prepared = bridge.apply_phase(
            structure, refinement.structure.phases[0], indices)
        self.energy = _Energy(build(self.prepared), self.prepared,
                              indices, term)
        self.variables = _Variables(term, self.prepared.lattice.matrix)
        chi2_0, _gradient = term(term.theta0)
        self.energy_0, _gradient = self.energy(term.theta0, options.cell)
        if scale is None:
            scale = EnergyScale(chi2=chi2_0, energy=self.energy_0,
                                rwp=term.statistics(term.theta0)["rwp"])
        self.scale = scale
        self.frames = _Frames(term, self.energy, on_frame,
                              frame_interval)

    @property
    def needs_relaxation(self) -> bool:
        """Whether ``dE`` is still unknown: a weight above 0 needs it."""
        return math.isnan(self.scale.relaxed)

    def _stopped(self) -> None:
        if getattr(self.cancel, "requested", False):
            raise PowderStopped("stopped")

    def relax(self):
        """The ``w = 1`` end from the start, which sets ``dE``:
        ``(theta, steps, converged, why)``."""
        options, energy = self.options, self.energy
        self.say(f"relaxing the atoms under "
                 f"{self.engine_name or 'the engine'} alone, for the "
                 f"energy's scale")

        def alone(theta):
            self._stopped()
            value, gradient = energy(theta, options.cell)
            return value - self.energy_0, gradient

        relaxation = self.variables.minimise(
            alone, options.max_steps, RELAX_TOLERANCE,
            lambda theta: self.frames(theta, "energy alone"))
        relaxed = relaxation[0]
        scale = self.scale
        self.scale = EnergyScale(
            chi2=scale.chi2, energy=scale.energy, rwp=scale.rwp,
            relaxed=energy(relaxed, options.cell)[0],
            relaxed_rwp=self.term.statistics(relaxed)["rwp"])
        return relaxation

    def solve(self, weight: float, start=None):
        """The minimum at ``weight`` below 1, from ``start`` (the
        variables' values; the structure's own when ``None``):
        ``(theta, steps, converged, why)``."""
        _check_weight(weight)
        term, energy, scale = self.term, self.energy, self.scale
        cell = self.options.cell
        self.say(f"refining the atoms against the pattern and the "
                 f"energy, w = {weight:g}")
        drop = scale.drop if weight > 0.0 else 1.0

        def joint(theta):
            self._stopped()
            chi2, g_pattern = term(theta)
            value = (1.0 - weight) * chi2 / scale.chi2
            gradient = (1.0 - weight) * g_pattern / scale.chi2
            if weight > 0.0:
                e, g_energy = energy(theta, cell)
                value += weight * (e - scale.energy) / drop
                gradient = gradient + weight * g_energy / drop
            return value, gradient

        return self.variables.minimise(
            joint, self.options.max_steps, 1e-6,
            lambda theta: self.frames(theta, f"w = {weight:g}"),
            start=start)

    def fit(self, answer, weight: float, steps: int, converged: bool,
            why: str) -> EnergyFit:
        """The :class:`EnergyFit` at the variables ``answer``."""
        from xtal.powder import bridge

        structure, term, scale = self.structure, self.term, self.scale
        cell = self.options.cell
        refined = _placed(self.prepared, self.indices,
                          term.fractions(answer),
                          term.cell(answer) if cell else None)
        if len(refined.sites) != len(structure.sites) \
                or refined.bonds != structure.bonds:
            raise PowderError("the refinement changed the atoms or the "
                              "bonds, and was not kept")
        stats = term.statistics(answer)
        moved = np.linalg.norm(refined.lattice.to_cart(
            refined.frac - structure.frac), axis=1)
        values = dict(bridge.refined_values(self.result))
        values.update({path: (float(value), 0.0) for path, value
                       in zip(term.paths, answer, strict=True)})
        phase = self.refinement.structure.phases[0]
        notes = [d.message for d in self.result.diagnostics]
        if weight > 0.0 and abs(scale.energy - scale.relaxed) \
                < MIN_ENERGY_DROP:
            notes.append(f"The force field moves these atoms by almost "
                         f"nothing on its own, so the energy is weighed "
                         f"against a drop of {MIN_ENERGY_DROP} kcal/mol.")
        return EnergyFit(
            structure=refined,
            cell=tuple(float(v) for v in term.cell(answer)),
            cell_esd=(0.0,) * 6,
            rwp=stats["rwp"], rp=stats["rp"], rexp=stats["rexp"],
            gof=stats["gof"],
            status="converged" if converged else why,
            two_theta=term.two_theta, y_obs=term.y_obs,
            y_calc=term.y_calc(answer),
            y_background=np.asarray(self.result.y_background),
            ticks=np.array([row[2] for row
                            in bridge.reflections(self.refinement)]),
            radiation=self.radiation,
            refined=values,
            moved=float(moved.max()) if moved.size else 0.0,
            atom_labels=tuple(atom.label for atom in phase.atoms),
            notes=notes, weight=weight,
            energy=float(self.energy(answer, cell)[0]), scale=scale,
            engine=self.engine_name, steps=int(steps))


# ======================================================================
#  THE ENERGY AS A FUNCTION OF THE PATTERN'S VARIABLES
# ======================================================================

class _Energy:
    """The engine's energy, and its gradient, over the pattern term's
    variables.

    The engine is handed the whole P1 cell, built here from the sites
    by the operations that generated it -- the same arithmetic as
    :class:`~xtal.ff.optimize.SymmetryDOF`, kept in fractions because
    the cell may move.  A dummy atom is not one of the phase's atoms
    and stays where it is; the engine never sees it.
    """

    def __init__(self, calculator, structure, indices, term):
        from xtal.core import p1

        self.calculator = calculator
        self.term = term
        self.indices = np.asarray(indices, dtype=int)
        self.start = structure.frac.copy()
        cell = p1.expand(structure)
        ops = structure.space_group.operations
        self.parent = np.asarray(cell.site_idx, dtype=int)
        self.rotations = np.array(
            [ops[int(k)].rot for k in cell.op_idx], dtype=float)
        self.offsets = np.array(
            [ops[int(k)].trans for k in cell.op_idx], dtype=float) \
            + np.asarray(cell.tau, dtype=float)
        self._at, self._value = None, None

    def __call__(self, theta, cell: bool) -> tuple[float, np.ndarray]:
        """``(E, dE/dtheta)``: kcal/mol, of the whole cell."""
        from xtal.core.lattice import Lattice

        theta = np.asarray(theta, dtype=float)
        if self._at is not None and np.array_equal(theta, self._at):
            return self._value
        term = self.term
        frac = self.start.copy()
        frac[self.indices] = term.fractions(theta)
        parameters = term.cell(theta)
        matrix = Lattice.from_parameters(*parameters).matrix
        images = np.einsum("kij,kj->ki", self.rotations,
                           frac[self.parent]) + self.offsets
        positions = images @ matrix
        result = self.calculator.compute(positions, matrix)
        if not math.isfinite(result.energy):
            raise PowderError("the engine's energy is not a number at "
                              "these positions")
        # dE/d(image fractions), then back over each orbit to the site
        per_image = -np.asarray(result.forces, dtype=float) @ matrix.T
        per_site = np.zeros_like(frac)
        np.add.at(per_site, self.parent,
                  np.einsum("ki,kij->kj", per_image, self.rotations))
        gradient = np.einsum("ai,cai->c", per_site[self.indices],
                             term.frac_basis)
        if cell and np.any(term.cell_basis):
            gradient = gradient + term.cell_basis @ self._cell_gradient(
                result, positions, matrix, parameters)
        self._at, self._value = theta.copy(), (float(result.energy),
                                               gradient)
        return self._value

    def _cell_gradient(self, result, positions, matrix, parameters):
        """``dE/d(a, b, c, alpha, beta, gamma)`` at fixed fractions.

        The stress is ``dE/d(strain) / V`` for ``M -> M (1 + e)``, so
        ``dE/dM = V M^-T sigma``; the lattice's own derivative with
        respect to each number is a difference, since it is six
        evaluations of a formula and not of an engine.
        """
        from xtal.core.lattice import Lattice

        stress = result.stress
        if stress is None:
            stress = self.calculator.numeric_stress(positions, matrix)
        volume = abs(float(np.linalg.det(matrix)))
        by_matrix = volume * np.linalg.inv(matrix).T @ np.asarray(stress)
        out = np.zeros(6)
        for k in range(6):
            step = 1e-5
            up, down = np.array(parameters), np.array(parameters)
            up[k] += step
            down[k] -= step
            d_matrix = (Lattice.from_parameters(*up).matrix
                        - Lattice.from_parameters(*down).matrix) \
                / (2 * step)
            out[k] = float(np.sum(by_matrix * d_matrix))
        return out


class _Variables:
    """The pattern term's variables as scipy minimises them.

    Scaled so that a unit step moves the furthest atom it moves by one
    Å, and a cell number by one Å or one degree: RietX's steps are in
    fractions, and a fraction of a 30 Å axis is thirty times a
    fraction of a 1 Å one, which L-BFGS would otherwise have to learn.
    """

    def __init__(self, term, matrix):
        self.term = term
        reach = np.linalg.norm(
            np.einsum("cai,ij->caj", term.frac_basis, matrix), axis=2)
        furthest = reach.max(axis=1) if reach.size else np.zeros(0)
        self.scale = np.where(furthest > 1e-12, 1.0 / np.maximum(
            furthest, 1e-12), 1.0)

    def minimise(self, function, max_steps: int, tolerance: float,
                 callback, start=None):
        """``(theta, steps, converged, why)``, from ``start`` or the
        term's own values."""
        from scipy.optimize import minimize

        theta0, scale = self.term.theta0, self.scale
        z0 = np.zeros(len(theta0)) if start is None \
            else (np.asarray(start, dtype=float) - theta0) / scale

        def scaled(z):
            value, gradient = function(theta0 + scale * z)
            return value, gradient * scale

        answer = minimize(
            scaled, z0, jac=True, method="L-BFGS-B",
            callback=lambda z: callback(theta0 + scale * z),
            options={"maxiter": int(max_steps), "gtol": tolerance,
                     "ftol": 1e-12})
        why = "converged" if answer.success else (
            f"stopped at {max_steps} steps" if answer.nit >= max_steps
            else str(answer.message))
        return (theta0 + scale * answer.x, int(answer.nit),
                bool(answer.success), why)


class _Frames:
    """The run as a person watches it: the curve and the atoms, at the
    Rietveld step's pace -- no more often than ``interval`` or three
    times what the last frame cost."""

    def __init__(self, term, energy, on_frame, interval: float):
        self.term, self.energy = term, energy
        self.on_frame, self.interval = on_frame, float(interval)
        self.last, self.cost = -math.inf, 0.0

    def __call__(self, theta, stage: str) -> None:
        from xtal.core.lattice import Lattice

        if self.on_frame is None:
            return
        now = time.monotonic()
        if now - self.last < max(self.interval, 3.0 * self.cost):
            return
        frac = self.energy.start.copy()
        frac[self.energy.indices] = self.term.fractions(theta)
        self.on_frame(RietveldFrame(
            stage=stage, two_theta=self.term.two_theta,
            y_obs=self.term.y_obs, y_calc=self.term.y_calc(theta),
            frac=frac,
            matrix=Lattice.from_parameters(*self.term.cell(theta)).matrix))
        self.last = time.monotonic()
        self.cost = self.last - now


def _placed(structure, indices, fractions, cell):
    """A copy of ``structure`` with the phase's atoms at ``fractions``
    and, when given, the cell; every other site where it was."""
    from xtal.core.lattice import Lattice

    out = structure.copy()
    if cell is not None:
        out.set_lattice(Lattice.from_parameters(*cell))
    for row, index in zip(fractions, indices, strict=True):
        out.set_frac(int(index), np.asarray(row, dtype=float))
    return out
