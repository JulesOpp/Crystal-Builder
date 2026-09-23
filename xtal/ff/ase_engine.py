"""
xtal.ff.ase_engine
==================
An energy engine that is an ASE calculator, run in this process.

A machine-learned potential -- MACE today, the other universal ones
next -- is a model loaded once and asked hundreds of times, through
ASE's ``Atoms`` and ``get_potential_energy``.  Everything around that
call is the same for every such model and is this application's code,
which is what can be got wrong: the P1 order, the cell moved under the
atoms rather than with them, eV to kcal/mol, and a stress claimed only
by a model that has one.  It lived in :mod:`xtal.ff.mace.calculator`,
141 of its 219 lines; it lives here so the next model is its loader
and its choices and nothing else.

A new engine of this kind subclasses :class:`ASECalculator` and
supplies :meth:`~ASECalculator.load_model` (usually through a
:class:`ModelCache`) and ``summary``.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

import numpy as np

from xtal.core import p1
from xtal.ff.api import Calculator, CalculatorError, Result

#: eV to kcal/mol.  Forces and stresses carry the same factor, being
#: an energy per Angstrom and an energy per Angstrom cubed.
KCAL_PER_EV = 23.060547830619026


def torch_device(wanted: str) -> str:
    """The device to run on, asking torch what there is.

    'auto' is the default because the honest answer is
    machine-specific and nobody should have to know theirs: a laptop
    has mps, a cluster node has cuda, and a CI box has neither.
    """
    if wanted and wanted != "auto":
        return wanted
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None \
            and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class ModelCache:
    """Loaded models, by what defines one, each built once.

    An optimisation is hundreds of evaluations and a load is seconds
    and tens of megabytes.  The lock is not decoration: the Force
    Field panel runs on a worker thread, and two threads reaching for
    the same uncached model would build it twice.
    """

    def __init__(self):
        self._models: dict[tuple, object] = {}
        self._lock = threading.Lock()

    def get(self, key: tuple, load: Callable[[], object]):
        with self._lock:
            if key not in self._models:
                self._models[key] = load()
            return self._models[key]

    def clear(self) -> None:
        with self._lock:
            self._models.clear()


def implements_stress(model) -> bool:
    """Whether this loaded model will answer for a stress at all.

    ASE says through ``implemented_properties``; a model file of
    somebody's own -- a dipole-only MACE, say -- reports an energy and
    forces and no stress.  Asking anyway failed *every* evaluation,
    throwing the energy and forces away with the stress the model never
    had.  Answered here, the optimiser falls back to
    :meth:`~xtal.ff.api.Calculator.numeric_stress` on its own (a
    ``None`` stress is the signal), and a fixed-cell run never needed
    one.

    A model that does not say is taken at its word and asked: that is
    ASE's older convention, and being wrong here costs an error
    message rather than a silent number.
    """
    properties = getattr(model, "implemented_properties", None)
    if properties is None:
        return True
    return "stress" in properties


class ASECalculator(Calculator):
    """An ASE calculator over a structure's P1 cell."""

    provides_forces = True
    #: ASE reports ``(1/V) dE/de`` in eV/A^3, which is what
    #: ``numeric_stress`` computes in kcal/mol/A^3 -- one factor, no
    #: normalisation guessed at.
    #:
    #: True on the class and **answered again per instance**: a model
    #: file of somebody's own need not have one.  See
    #: :func:`implements_stress`.
    provides_stress = True
    #: What to install when ase itself is missing.
    install = "pip install ase"

    def __init__(self, structure, options):
        self.options = options
        self.structure = structure
        self.cell = p1.expand(structure)
        if self.cell.n_atoms == 0:
            raise CalculatorError(
                "there are no atoms to compute an energy for")
        self.symbols = tuple(self.cell.elements)
        self.warnings: list[str] = []
        self.calls = 0
        self._model = self.load_model(self.options)
        self.provides_stress = implements_stress(self._model)
        if not self.provides_stress:
            self.warnings.append(
                "this model reports no stress, so relaxing the cell "
                "will differentiate the energy numerically -- twelve "
                "evaluations a step instead of one")
        self._atoms = self._make_atoms()

    def load_model(self, options):
        """The ASE calculator these options name, loaded or cached."""
        raise NotImplementedError

    def _make_atoms(self):
        """One ASE Atoms, built once and moved under the model.

        In P1 cell order, which is the order everything above this
        speaks in: the optimiser maps forces back onto the sites they
        came from by index, so an atom container that reordered
        anything would put a force on the wrong atom.
        """
        try:
            from ase import Atoms
        except ImportError:                         # pragma: no cover
            raise CalculatorError(
                f"{self.label} needs ase -- {self.install}") from None
        atoms = Atoms(symbols=list(self.symbols),
                      positions=np.asarray(self.cell.cart,
                                           dtype=float),
                      cell=np.asarray(self.structure.lattice.matrix,
                                      dtype=float),
                      pbc=True)
        atoms.calc = self._model
        return atoms

    @property
    def n_atoms(self) -> int:
        return self.cell.n_atoms

    def compute(self, positions, matrix) -> Result:
        """Energy and forces at these cartesian positions."""
        positions = np.asarray(positions, dtype=float).reshape(-1, 3)
        if len(positions) != self.n_atoms:
            raise CalculatorError(
                f"got {len(positions)} positions for "
                f"{self.n_atoms} atoms")
        # scale_atoms=False: the positions given are already where the
        # atoms go.  Letting ASE carry them with the cell would apply
        # the strain twice, which is exactly the error that makes a
        # numeric stress disagree with an analytic one.
        self._atoms.set_cell(np.asarray(matrix, dtype=float),
                             scale_atoms=False)
        self._atoms.set_positions(positions)
        try:
            energy = float(self._atoms.get_potential_energy())
            forces = np.asarray(self._atoms.get_forces(), dtype=float)
            stress = (np.asarray(self._atoms.get_stress(voigt=False),
                                 dtype=float)
                      if self.provides_stress else None)
        except CalculatorError:                     # pragma: no cover
            raise
        except Exception as exc:                    # noqa: BLE001
            raise CalculatorError(
                f"{self.label} could not compute this structure: {exc}"
            ) from None
        self.calls += 1
        return Result(energy=energy * KCAL_PER_EV,
                      forces=forces * KCAL_PER_EV,
                      terms={self.name: energy * KCAL_PER_EV},
                      stress=(None if stress is None
                              else stress * KCAL_PER_EV))
