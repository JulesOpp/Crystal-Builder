"""
xtal.ff.api
===========
What an energy engine has to provide, and nothing more.

A :class:`Calculator` is built for one structure and then answers the
same question over and over: given these cartesian positions and this
cell, what is the energy and what are the forces?  UFF is the one that
ships; LAMMPS, GULP, xTB or a machine-learned potential would each be
another class implementing this and one line in the registry, with no
change above them -- the optimiser, the worker thread and the panel
all speak only to this interface.

Two decisions keep that promise honest.  The calculator is built
**for a structure** rather than handed one per call, because assigning
atom types and enumerating a million angle terms is far too expensive
to repeat every step of an optimisation; the topology is fixed at
construction and the geometry moves under it.  And it works on the
**P1 cell** -- the real atoms in the box -- not the asymmetric unit,
because that is what has an energy.  Mapping a symmetry orbit back
onto the site it came from is :mod:`xtal.ff.optimize`'s job.

Energies are kcal/mol, forces kcal/mol/Angstrom, stresses kcal/mol per
Angstrom^3.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np


class CalculatorError(RuntimeError):
    """The structure cannot be given an energy: an element the force
    field has no parameters for, a missing charge, an empty cell."""


class CalculatorStopped(CalculatorError):
    """Stop was pressed during an evaluation, and the engine was
    killed rather than waited for.  Not a failure: whoever is running
    the optimisation keeps the last step it had."""


@dataclass(frozen=True)
class Result:
    """One energy evaluation."""

    energy: float                       # kcal/mol
    forces: np.ndarray                  # (N,3) kcal/mol/Angstrom
    terms: dict = field(default_factory=dict)   # per-term energies
    stress: np.ndarray | None = None    # (3,3) kcal/mol/Angstrom^3

    @property
    def max_force(self) -> float:
        if not len(self.forces):
            return 0.0
        return float(np.linalg.norm(self.forces, axis=1).max())

    @property
    def rms_force(self) -> float:
        if not len(self.forces):
            return 0.0
        return float(np.sqrt(np.mean(np.sum(self.forces ** 2,
                                            axis=1))))

    def breakdown(self) -> str:
        """The per-term energies, largest first -- the thing to read
        when a number looks wrong."""
        rows = sorted(self.terms.items(), key=lambda kv: -abs(kv[1]))
        width = max((len(k) for k, _v in rows), default=0)
        lines = [f"{k:<{width}s}  {v:12.4f}" for k, v in rows]
        lines.append(f"{'total':<{width}s}  {self.energy:12.4f}")
        return "\n".join(lines)


class Calculator(ABC):
    """An energy and forces engine for one fixed structure."""

    name = "calculator"
    label = "Calculator"
    provides_forces = True
    provides_stress = False
    #: A :class:`~xtal.modules.job.Cancellation`, or ``None``.  An
    #: engine that runs a program passes it to the program, so Stop
    #: kills a slow SCC cycle instead of waiting for it to end; one
    #: that computes in-process has nothing to kill and ignores it.
    cancel = None

    def stop_with(self, cancel) -> None:
        """Be stoppable by ``cancel`` from now on."""
        self.cancel = cancel

    @property
    @abstractmethod
    def n_atoms(self) -> int:
        """Atoms in the P1 cell this was built for."""

    @abstractmethod
    def compute(self, positions, matrix) -> Result:
        """Energy and forces at these cartesian positions."""

    # -- optional ------------------------------------------------------

    #: Anything the user should know before believing the numbers: a
    #: parameter the engine had to guess, a warning its own output
    #: printed.  The panel shows them; nothing here depends on them.
    warnings: list = []

    def summary(self) -> str:
        """One line about the model, shown above the result.

        Overridden by every engine that has something to say -- UFF
        counts its terms, DFTB+ names its parameter set -- and here so
        that an engine which has not bothered still renders.
        """
        return f"{self.n_atoms} atoms"

    def numeric_stress(self, positions, matrix,
                       strain: float = 1e-4) -> np.ndarray:
        """Stress by central differences of six symmetric strains.

        Every calculator gets this for free, which is what makes
        variable-cell relaxation possible before anyone writes an
        analytic stress: it costs twelve energy evaluations, which is
        nothing next to the optimisation it enables.
        """
        positions = np.asarray(positions, dtype=float)
        matrix = np.asarray(matrix, dtype=float)
        volume = abs(float(np.linalg.det(matrix)))
        frac = positions @ np.linalg.inv(matrix)
        out = np.zeros((3, 3))
        for a in range(3):
            for b in range(a, 3):
                deformation = np.zeros((3, 3))
                deformation[a, b] += 0.5
                deformation[b, a] += 0.5
                plus = np.eye(3) + strain * deformation
                minus = np.eye(3) - strain * deformation
                up = self.compute(frac @ (matrix @ plus),
                                  matrix @ plus).energy
                down = self.compute(frac @ (matrix @ minus),
                                    matrix @ minus).energy
                value = (up - down) / (2 * strain * volume)
                out[a, b] = out[b, a] = value
        return out

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.n_atoms} atoms)"
