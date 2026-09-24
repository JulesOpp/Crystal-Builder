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

It is claimed **per model** and not per engine, which matters only for
a model file of somebody's own: every foundation model here reports a
stress and a dipole-only model reports none, and asking one that has
none used to fail the whole evaluation rather than the part that was
missing.  See :func:`implements_stress`.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path

from xtal import install
from xtal.ff.api import CalculatorError
from xtal.ff.ase_engine import (  # noqa: F401 -- implements_stress, too
    KCAL_PER_EV,
    ASECalculator,
    ModelCache,
    implements_stress,
    torch_device,
)
from xtal.ff.registry import ENGINES, Engine
from xtal.params import Availability, Param

#: The package that has to be installed, and how.
PACKAGE = "mace"
INSTALL = install.command("mace")

#: The foundation models this offers, newest first, by the name
#: ``mace_mp`` knows them.  Not all seventeen: these are the ones whose
#: training set, level of theory or licence makes them a *different
#: answer* to "which model for this framework", and a chooser of
#: seventeen is one nobody reads to the bottom of.
#:
#: **Every description is the upstream table's own** -- training set,
#: level of theory, licence -- and deliberately not a characterisation
#: of our own.  Inventing one is how a user comes to quote r2SCAN
#: numbers off a PBE+U model.
#:
#: The MP-0a three are kept below the newer ones rather than dropped.
#: They were this engine's only choices, they are what a run recorded
#: before today names, and a parameter set that outlives the catalogue
#: it was chosen from is the same promise ``mof_build`` makes.
MODEL_CHOICES = (
    ("medium-mpa-0",
     "MACE-MPA-0 -- MPtrj + sAlex, PBE+U (recommended)"),
    ("medium-0b3",
     "MACE-MP-0b3 -- MPtrj, PBE+U, steadier under pressure"),
    ("medium-omat-0",
     "MACE-OMAT-0 -- OMat, PBE+U [ASL licence]"),
    ("mace-matpes-r2scan-0",
     "MACE-MATPES-r2SCAN-0 -- r2SCAN, no +U [ASL licence]"),
    ("mh-1",
     "MACE-MH-1 -- crystals, molecules and surfaces [ASL licence]"),
    ("medium", "MACE-MP-0a medium -- the default before mace 0.3.10"),
    ("small", "MACE-MP-0a small -- fastest"),
    ("large", "MACE-MP-0a large"),
    (CUSTOM := "custom", "A model file of my own"),
)

#: The default, and it is ``mace_mp``'s own: from mace-torch 0.3.10 the
#: package stopped defaulting to ``medium`` and started defaulting to
#: this, which is the same model fitted over MPtrj *and* sAlex.  Asking
#: for ``medium`` explicitly now gets the older generation -- mace
#: prints a line saying exactly that -- so a chooser whose first entry
#: was ``medium`` handed everybody the previous default while looking
#: like the current one.
DEFAULT_MODEL = "medium-mpa-0"

#: The models under the Academic Software License rather than MIT, by
#: the licence column of MACE's own table.
#:
#: The label says so *before* the choice is made, and that is the whole
#: point: MACE ``print``s "you accept the terms of the license" as it
#: downloads, which is a poor moment to find out, and this application
#: is the thing doing the downloading.  Naming the licence in the combo
#: keeps the acceptance the user's.  (MACE's own notice covers four of
#: these; its table marks all six.)
ASL_MODELS = frozenset({
    "small-omat-0", "medium-omat-0", "mace-matpes-pbe-0",
    "mace-matpes-r2scan-0", "mh-0", "mh-1",
})

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


def available(model: str = DEFAULT_MODEL, model_path: str = "",
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
    licence = (" -- under the Academic Software License, which "
               "using it accepts (https://github.com/gabor1/ASL)"
               if model in ASL_MODELS else "")
    return Availability(
        True, f"{model} -- downloaded to the MACE cache the first "
              f"time it is used{licence}")


@dataclass(frozen=True)
class MACEOptions:
    """Everything about the calculation that is not the structure."""

    model: str = DEFAULT_MODEL
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
          default=DEFAULT_MODEL,
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
_MODELS = ModelCache()

#: A module global and not a call to :func:`torch_device` inline, so
#: the tests can answer "cpu" without importing torch.
_device = torch_device


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
    return _MODELS.get(key, lambda: _build_model(options))


def _build_model(options: MACEOptions):
    """Load the model :func:`_load_model` found no cached copy of."""
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
    return model


def forget_models() -> None:
    """Drop the loaded models.  For the tests, and for a user who has
    just refitted the file they pointed at."""
    _MODELS.clear()


# ======================================================================
#  THE CALCULATOR
# ======================================================================

class MACECalculator(ASECalculator):
    """A MACE model over a structure's P1 cell.

    Everything but the model and its name is
    :class:`~xtal.ff.ase_engine.ASECalculator`'s, and the stress it
    claims is checked against a numeric one in ``tests/test_mace.py``.
    """

    name = "mace"
    label = "MACE"
    install = INSTALL

    def __init__(self, structure, options: MACEOptions | None = None):
        super().__init__(structure, options or MACEOptions())

    def load_model(self, options):
        return _load_model(options)

    def summary(self) -> str:
        what = (Path(self.options.model_path).name
                if self.options.model == CUSTOM
                else f"MACE-MP {self.options.model}")
        return (f"{self.n_atoms} atoms, {what}, on "
                f"{_device(self.options.device)}")


# ======================================================================
#  THE ENGINE
# ======================================================================

def build(structure, **options) -> MACECalculator:
    """Registry entry point: keyword options in, calculator out.

    The options arrive coerced to :data:`OPTIONS` -- see
    :meth:`xtal.ff.registry.Engine.__call__`.
    """
    return MACECalculator(structure, MACEOptions(**options))


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
