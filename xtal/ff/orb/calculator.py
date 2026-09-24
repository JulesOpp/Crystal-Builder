"""
xtal.ff.orb.calculator
======================
ORB-v3 as an energy engine -- a machine-learned potential, in process.

ORB-v3 is Orbital Materials' universal potential, Apache-2.0 code and
weights, and the reason it is here beside MACE is the benchmark the
deep review read: on MOFSimBench the best universal potentials reach
89 % volume accuracy on frameworks, where UFF4MOF reaches 62 %.  It is
the second model on :class:`~xtal.ff.ase_engine.ASECalculator`, which
is why this module is a loader, a list of choices and nothing else.

Four things are particular to it, and each was measured on orb-models
0.7.0 rather than read.

**Only the conservative models are offered.**  ORB's "direct" models
predict forces from a head of their own rather than differentiating
the energy, so the force is not the gradient of the energy the
optimiser's line search compares -- which is the one thing a
relaxation needs from them.

**Double precision, as for MACE, and for the same reason.**  Along the
force on MOF-5, a 1e-4 A step changes the energy by 5.8e-4 eV; in
float32 the computed change is off by 2.1e-4 eV, a third of it, and in
float64 by 4e-7.  An optimiser reads exactly those differences.  It
costs 2.7x (MOF-5, 424 atoms, 0.94 -> 2.58 s an evaluation on this
CPU; MFU-4l, 648 atoms, 1.70 -> 5.92 s), which is still faster than
MACE-MPA-0 at the same precision (3.32 and 7.06 s).

**No Apple GPU.**  orb-models builds its model and then calls
``.cuda(device)`` for any device that is not the CPU, so ``mps``
fails at load with "Invalid device, must be cuda device".  'auto'
here means CUDA if there is one and the CPU otherwise --
:func:`~xtal.ff.ase_engine.torch_device` with ``allow_mps=False``,
because left to itself it would pick mps on a Mac and fail.

**Loading one changes torch's default dtype for the whole process**,
and warns that it has.  That is a global another engine in the same
process reads, so it is put back once the model is built; the model
keeps the precision it was built in, which was checked by evaluating
after resetting the default.
"""

from __future__ import annotations

import functools
import importlib.util
import warnings
from dataclasses import dataclass

from xtal import install
from xtal.ff.api import CalculatorError
from xtal.ff.ase_engine import (
    KCAL_PER_EV,
    ASECalculator,
    ModelCache,
    torch_device,
)
from xtal.ff.registry import ENGINES, Engine, arxiv, github
from xtal.params import Availability, Param

__all__ = ["DEFAULT_MODEL", "DEVICE_CHOICES", "INSTALL", "KCAL_PER_EV",
           "MODEL_CHOICES", "OPTIONS", "ORBCalculator", "ORBOptions",
           "available", "build", "forget_models", "installed"]

#: The package that has to be installed, and how.
PACKAGE = "orb_models"
INSTALL = install.command("orb")

#: The conservative ORB-v3 models, by the name orb-models knows them.
#: The descriptions are upstream's own -- training set and neighbour
#: limit, from each loader's docstring -- for the reason MACE's are.
#: "Unlimited" is upstream's word for every neighbour inside 6 A.
MODEL_CHOICES = (
    ("orb-v3-conservative-inf-omat",
     "ORB-v3 -- OMat24, all neighbours within 6 A (recommended)"),
    ("orb-v3-conservative-20-omat",
     "ORB-v3 -- OMat24, 20 neighbours, faster"),
    ("orb-v3-conservative-inf-mpa",
     "ORB-v3 -- MPtrj + Alexandria, all neighbours within 6 A"),
    ("orb-v3-conservative-20-mpa",
     "ORB-v3 -- MPtrj + Alexandria, 20 neighbours, faster"),
)
DEFAULT_MODEL = "orb-v3-conservative-inf-omat"

DEVICE_CHOICES = (
    ("auto", "The NVIDIA GPU if there is one, otherwise the CPU"),
    ("cpu", "CPU"),
    ("cuda", "NVIDIA GPU (cuda)"),
)


def installed() -> bool:
    """Whether ``orb_models`` is importable -- without importing it.

    See :func:`xtal.ff.mace.calculator.installed`: this is asked on
    every refresh of the panel, and importing it is torch.
    """
    try:
        return importlib.util.find_spec(PACKAGE) is not None
    except (ImportError, ValueError):               # pragma: no cover
        return False


def available(model: str = DEFAULT_MODEL, **_rest) -> Availability:
    """Installed, and saying that the weights are a download."""
    if not installed():
        return Availability(
            False, f"ORB is not installed -- {INSTALL}")
    if model not in dict(MODEL_CHOICES):
        return Availability(False, f"{model!r} is not an ORB-v3 model "
                                   f"this application offers")
    return Availability(
        True, f"{model} -- about 100 MB, downloaded to orb-models' "
              f"cache the first time it is used")


@dataclass(frozen=True)
class ORBOptions:
    """Everything about the calculation that is not the structure."""

    model: str = DEFAULT_MODEL
    device: str = "auto"
    #: See the module docstring: float32's noise is a third of the
    #: energy differences a line search reads.
    double_precision: bool = True


OPTIONS = (
    Param("model", "Model", kind="choice", choices=MODEL_CHOICES,
          default=DEFAULT_MODEL,
          help="Conservative ORB-v3 models only: their forces are the "
               "gradient of their energy, which is what a relaxation "
               "needs.  Each is downloaded once, to orb-models' own "
               "cache."),
    Param("device", "Run on", kind="choice", choices=DEVICE_CHOICES,
          default="auto",
          help="orb-models cannot run on an Apple GPU, so on a Mac "
               "this is the CPU."),
    Param("double_precision", "Double precision", kind="bool",
          default=True,
          help="Leave this on for geometry optimisation: in single "
               "precision the model's own noise is a third of the "
               "energy differences an optimiser reads.  Off is about "
               "2.7 times faster."),
)


# ======================================================================
#  THE MODEL, LOADED ONCE
# ======================================================================

_MODELS = ModelCache()


def _torch_device(wanted: str) -> str:
    """CUDA if asked for or there, otherwise the CPU -- never mps."""
    return torch_device(wanted, allow_mps=False)


#: A module global, as MACE's is, so the tests answer "cpu" without
#: importing torch.
_device = _torch_device


def _load_model(options: ORBOptions):
    """An ASE calculator for these options, built once and kept.

    **This is the seam the tests use**, as in
    :mod:`xtal.ff.mace.calculator`.
    """
    key = (options.model, options.device, options.double_precision)
    return _MODELS.get(key, lambda: _build_model(options))


def _build_model(options: ORBOptions):
    """Load the model :func:`_load_model` found no cached copy of."""
    device = _device(options.device)
    precision = "float64" if options.double_precision else "float32-high"
    try:
        import torch
        from orb_models.forcefield import pretrained
        from orb_models.forcefield.inference.calculator import (
            ORBCalculator as _Model,
        )
    except ImportError as exc:
        raise CalculatorError(
            f"ORB is not installed -- {INSTALL} ({exc})") from None
    loader = pretrained.ORB_PRETRAINED_MODELS.get(options.model)
    if loader is None:
        raise CalculatorError(
            f"orb-models does not know a model called {options.model!r}")
    default = torch.get_default_dtype()
    try:
        # Its two warnings are about the global it is about to change,
        # which is put back below, and advice to use float32, which
        # the module docstring measured and declined.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            model, adapter = loader(device=device, precision=precision,
                                    compile=False)
        return _pin_dtype(_Model(model, adapter, device=device))
    except Exception as exc:                        # noqa: BLE001
        raise CalculatorError(
            f"the ORB model could not be loaded ({options.model}): "
            f"{exc}") from None
    finally:
        torch.set_default_dtype(default)


def _pin_dtype(model):
    """Build every input graph in the model's own precision.

    orb-models builds a graph -- positions, edge vectors, the strain
    the stress is taken through -- in torch's *global* default dtype
    unless it is told one, and its ASE calculator never tells it.  The
    global is put back after loading (above), because every other
    engine in the process reads it; so a float64 model was handed
    float32 geometry, and along the force on MOF-74 the energy's slope
    disagreed with the force by 2e-3 at a 1e-4 A step, against 6e-9
    with float64 geometry.  That is the error double precision was
    chosen to remove.

    Given here, once, from the weights.  An orb-models that stops
    taking these keywords fails loudly at the first evaluation rather
    than going back to float32 in silence.
    """
    dtype = next(model.model.parameters()).dtype
    model.adapter.from_ase_atoms = functools.partial(
        model.adapter.from_ase_atoms, output_dtype=dtype,
        graph_construction_dtype=dtype)
    return model


def forget_models() -> None:
    """Drop the loaded models.  For the tests."""
    _MODELS.clear()


# ======================================================================
#  THE CALCULATOR
# ======================================================================

class ORBCalculator(ASECalculator):
    """An ORB-v3 model over a structure's P1 cell."""

    name = "orb"
    label = "ORB"
    install = INSTALL

    def __init__(self, structure, options: ORBOptions | None = None):
        super().__init__(structure, options or ORBOptions())

    def load_model(self, options):
        return _load_model(options)

    def summary(self) -> str:
        precision = ("double" if self.options.double_precision
                     else "single")
        return (f"{self.n_atoms} atoms, {self.options.model}, "
                f"{precision} precision, on "
                f"{_device(self.options.device)}")


# ======================================================================
#  THE ENGINE
# ======================================================================

def build(structure, **options) -> ORBCalculator:
    """Registry entry point: keyword options in, calculator out."""
    return ORBCalculator(structure, ORBOptions(**options))


ENGINES.register(Engine(
    name="orb",
    label="ORB-v3 (machine-learned)",
    description="Orbital Materials' universal potential.  Like MACE it "
                "needs no parameters assigning; on the MOFSimBench "
                "framework benchmark it is among the most accurate "
                "for cell volumes.",
    build=build,
    order=31,
    provides=frozenset({"forces", "stress", "periodic"}),
    options=OPTIONS,
    check=available,
    references=(
        arxiv("Orb-v3: Rhodes et al., 2025", "2504.06231"),
        github("orbital-materials/orb-models"),
    ),
))
