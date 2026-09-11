"""
xtal.ff.mace.calculator
=======================
MACE as an energy engine -- a machine-learned potential, in process.

MACE is an equivariant message-passing model in the atomic cluster
expansion family, and what makes it worth an entry here is not the
architecture but the **foundation models**: MACE-MP is fitted over the
Materials Project and answers for an arbitrary inorganic framework
with no parameters to assign and no atom typing to get right.  That is
the gap between UFF, which has to be extended to describe a metal node
at all, and DFTB+, which needs a Slater-Koster set downloading per
element pair.

Four things are particular to this engine.

**It runs in this process, not as a subprocess.**  xTB and DFTB+ are
binaries and every evaluation is a directory, a geometry file and a
parse; MACE is a Python object holding tensors, so the structure is
handed to it once and the geometry moves under it.  That makes the
per-step cost the model's own, which is the point of using it inside an
optimisation.

**The model is loaded once and cached.**  Building one costs seconds
and a foundation model is tens of megabytes off disk, while an
optimisation asks for hundreds of evaluations -- so the loaded model
is kept in :data:`_MODELS`, keyed by everything that defines it, and a
second calculator over the same choice reuses it.  The lock is not
decoration: the Force Field panel runs on a worker thread, and two
threads reaching for the same uncached model would build it twice.

**A foundation model is downloaded on first use.**  ``mace_mp`` fetches
the weights to the user's own cache the first time they are asked for,
which is a download this application did not start and cannot do
silently -- so :func:`available` says so before anything runs, and the
choice of a local file is offered beside it.

**The stress is ASE's and is claimed only because it was checked.**
:mod:`xtal.ff.xtb.calculator` refuses to claim one and its docstring
gives the reason: a stress that is quietly wrong relaxes a cell to the
wrong volume while reporting that it converged.  The same standard
applies here -- ``tests/test_mace.py`` compares what the model reports
against :meth:`~xtal.ff.api.Calculator.numeric_stress`, and the
conversion below is one factor with no normalisation guessed at,
because ASE's stress is already ``(1/V) dE/de`` in eV/A^3, which is
what ``numeric_stress`` computes in kcal/mol/A^3.
"""

from __future__ import annotations

import importlib.util
import threading
from dataclasses import dataclass, fields
from pathlib import Path

import numpy as np

from xtal.core import p1
from xtal.ff.api import Calculator, CalculatorError, Result
from xtal.ff.registry import ENGINES, Engine
from xtal.params import Availability, Param

#: eV to kcal/mol.  Forces and stresses carry the same factor, being
#: an energy per Angstrom and an energy per Angstrom cubed.
KCAL_PER_EV = 23.060547830619026

#: The package that has to be installed, and how.
PACKAGE = "mace"
INSTALL = "pip install 'crystal-builder[mace]'"

#: The foundation models, by the name ``mace_mp`` knows them, with the
#: size of the download beside each.  Three rather than all of them
#: because these are the three that differ in the only way that
#: matters to somebody choosing: how long an evaluation takes.
MODEL_CHOICES = (
    ("small", "MACE-MP small -- fastest"),
    ("medium", "MACE-MP medium -- the usual choice"),
    ("large", "MACE-MP large -- slowest and most accurate"),
    (CUSTOM := "custom", "A model file of my own"),
)

DEVICE_CHOICES = (
    ("auto", "Whatever is fastest here"),
    ("cpu", "CPU"),
    ("mps", "Apple GPU (mps)"),
    ("cuda", "NVIDIA GPU (cuda)"),
)


def installed() -> bool:
    """Whether ``mace`` is importable -- without importing it.

    ``find_spec`` reads the location off the path and stops, which is
    what every other optional dependency in this application is
    tested with: importing mace pulls in torch, which is seconds, and
    this is called every time the panel refreshes.
    """
    try:
        return importlib.util.find_spec(PACKAGE) is not None
    except (ImportError, ValueError):               # pragma: no cover
        return False


def available(model: str = "medium", model_path: str = "",
              **_rest) -> Availability:
    """Installed, and with a model this option set can actually load.

    The model matters as much as the package, for opposite reasons in
    the two cases: a file of one's own has to *be there*, and a
    foundation model has to be *fetched*, which is a download on first
    use and is said here rather than discovered as a pause.
    """
    if not installed():
        return Availability(
            False, f"MACE is not installed -- {INSTALL}")
    if model == CUSTOM:
        if not str(model_path or "").strip():
            return Availability(
                False, "name the model file to use, or choose one of "
                       "the MACE-MP models instead")
        if not Path(model_path).expanduser().is_file():
            return Availability(
                False, f"there is no model file at {model_path}")
        return Availability(True, str(Path(model_path).expanduser()))
    return Availability(
        True, f"MACE-MP {model} -- downloaded to the MACE cache the "
              f"first time it is used")


@dataclass(frozen=True)
class MACEOptions:
    """Everything about the calculation that is not the structure."""

    model: str = "medium"
    model_path: str = ""
    device: str = "auto"
    #: float64 rather than float32, and not for accuracy of the energy
    #: -- for the *consistency* of it.  An optimiser reads differences
    #: between energies a few thousandths of a kcal/mol apart, and in
    #: float32 the model's own noise is larger than that, so a line
    #: search stops converging and starts wandering.
    double_precision: bool = True


OPTIONS = (
    Param("model", "Model", kind="choice", choices=MODEL_CHOICES,
          default="medium",
          help="The MACE-MP foundation models are fitted over the "
               "Materials Project and need nothing assigning -- they "
               "answer for a framework whose metal node UFF has no "
               "parameters for.  Each is downloaded once, to MACE's "
               "own cache.  Choose 'a model file of my own' for one "
               "you have fitted."),
    Param("model_path", "Model file", kind="path",
          help="A .model file, for the 'my own' choice above.  "
               "Ignored by the MACE-MP models."),
    Param("device", "Run on", kind="choice", choices=DEVICE_CHOICES,
          default="auto",
          help="A GPU is worth an order of magnitude on a framework "
               "of a few thousand atoms.  'Whatever is fastest here' "
               "asks torch what this machine has."),
    Param("double_precision", "Double precision", kind="bool",
          default=True,
          help="Leave this on for geometry optimisation: in single "
               "precision the model's own noise is larger than the "
               "energy differences an optimiser is reading, and the "
               "line search wanders instead of converging."),
)


# ======================================================================
#  THE MODEL, LOADED ONCE
# ======================================================================

#: Loaded models, by what defines one.  See the module docstring: an
#: optimisation is hundreds of evaluations and a load is seconds.
_MODELS: dict[tuple, object] = {}
_LOCK = threading.Lock()


def _device(wanted: str) -> str:
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


def _load_model(options: MACEOptions):
    """An ASE calculator for these options, built once and kept.

    **This is the seam the tests use.**  Everything above it -- the
    unit conversion, the P1 ordering, the cell handling -- is this
    application's code and is what can be got wrong; the model itself
    is MACE's.  So the tests replace this with a cheap ASE calculator
    and check the arithmetic, and one slow test that skips without
    mace installed checks the real thing.
    """
    key = (options.model, options.model_path, options.device,
           options.double_precision)
    with _LOCK:
        if key in _MODELS:
            return _MODELS[key]
        dtype = "float64" if options.double_precision else "float32"
        device = _device(options.device)
        try:
            if options.model == CUSTOM:
                from mace.calculators import MACECalculator as _Model

                model = _Model(
                    model_paths=str(Path(options.model_path)
                                    .expanduser()),
                    device=device, default_dtype=dtype)
            else:
                from mace.calculators import mace_mp

                model = mace_mp(model=options.model, device=device,
                                default_dtype=dtype)
        except ImportError as exc:
            raise CalculatorError(
                f"MACE is not installed -- {INSTALL} ({exc})"
            ) from None
        except Exception as exc:                    # noqa: BLE001
            # A model that will not load is the common failure and it
            # is nearly always the download or the file: say which
            # model it was, because the panel's message is all the
            # user gets.
            raise CalculatorError(
                f"the MACE model could not be loaded "
                f"({options.model_path or options.model}): {exc}"
            ) from None
        _MODELS[key] = model
        return model


def forget_models() -> None:
    """Drop the loaded models.  For the tests, and for a user who has
    just refitted the file they pointed at."""
    with _LOCK:
        _MODELS.clear()


# ======================================================================
#  THE CALCULATOR
# ======================================================================

class MACECalculator(Calculator):
    """A MACE model over a structure's P1 cell."""

    name = "mace"
    label = "MACE"
    provides_forces = True
    #: ASE reports ``(1/V) dE/de`` in eV/A^3, which is what
    #: ``numeric_stress`` computes in kcal/mol/A^3 -- one factor, no
    #: normalisation guessed at, and checked against it in the tests.
    provides_stress = True

    def __init__(self, structure, options: MACEOptions | None = None):
        self.options = options or MACEOptions()
        self.structure = structure
        self.cell = p1.expand(structure)
        if self.cell.n_atoms == 0:
            raise CalculatorError(
                "there are no atoms to compute an energy for")
        self.symbols = tuple(self.cell.elements)
        self.warnings: list[str] = []
        self.calls = 0
        self._model = _load_model(self.options)
        self._atoms = self._make_atoms()

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
                f"MACE needs ase -- {INSTALL}") from None
        atoms = Atoms(symbols=list(self.symbols),
                      positions=np.asarray(self.cell.cart,
                                           dtype=float),
                      cell=np.asarray(self.structure.lattice.matrix,
                                      dtype=float),
                      pbc=True)
        atoms.calc = self._model
        return atoms

    # -- what the panel asks about -------------------------------------

    @property
    def n_atoms(self) -> int:
        return self.cell.n_atoms

    def summary(self) -> str:
        what = (Path(self.options.model_path).name
                if self.options.model == CUSTOM
                else f"MACE-MP {self.options.model}")
        return (f"{self.n_atoms} atoms, {what}, on "
                f"{_device(self.options.device)}")

    # -- the evaluation -------------------------------------------------

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
            stress = np.asarray(self._atoms.get_stress(voigt=False),
                                dtype=float)
        except CalculatorError:                     # pragma: no cover
            raise
        except Exception as exc:                    # noqa: BLE001
            raise CalculatorError(
                f"MACE could not compute this structure: {exc}"
            ) from None
        self.calls += 1
        return Result(energy=energy * KCAL_PER_EV,
                      forces=forces * KCAL_PER_EV,
                      terms={"mace": energy * KCAL_PER_EV},
                      stress=stress * KCAL_PER_EV)


# ======================================================================
#  THE ENGINE
# ======================================================================

def build(structure, **options) -> MACECalculator:
    """Registry entry point: keyword options in, calculator out."""
    known = {f.name for f in fields(MACEOptions)}
    return MACECalculator(structure, MACEOptions(
        **{k: v for k, v in options.items() if k in known}))


ENGINES.register(Engine(
    name="mace",
    label="MACE (machine-learned)",
    description="A machine-learned potential in the atomic cluster "
                "expansion family.  The MACE-MP foundation models "
                "answer for a framework with no parameters to assign "
                "and no atom typing to get right, at a cost between "
                "a force field's and tight binding's.",
    build=build,
    order=30,
    provides=frozenset({"forces", "stress", "periodic"}),
    options=OPTIONS,
    check=available,
))
