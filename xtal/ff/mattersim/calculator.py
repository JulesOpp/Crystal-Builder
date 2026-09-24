"""
xtal.ff.mattersim.calculator
============================
MatterSim as an energy engine -- a machine-learned potential, in
process.

MatterSim is Microsoft Research's universal potential, an M3GNet
trained across the periodic table, temperature and pressure; MIT code
and weights.  It is the third model on
:class:`~xtal.ff.ase_engine.ASECalculator`, and like ORB-v3 this module
is a loader, a list of choices and nothing else.

What is particular to it was measured on mattersim 1.2.5, torch 2.11,
the 1M model, on this CPU.

**Its limits, in its authors' words** (the model card): "relatively
low accuracy for organic polymeric systems", and trained on PBE with
PBE's limits.  A MOF's linkers are organic, so a relaxation here wants
checking against another engine.  Like ORB-v3 it runs with no
dispersion correction, and MOFSimBench's numbers for it are with D3;
see :mod:`xtal.ff.orb.calculator` for what that is worth in a volume.

**It is the fast one.**  MOF-5 (424 atoms) is 0.51 s an evaluation in
double precision, against ORB-v3's 2.58 s and MACE-MPA-0's 3.32 s.

**Double precision, for the reason the other two are.**  Along the
force on MOF-5, a 1e-4 A step changes the energy by 9.2e-3 eV; float32
gets that change wrong by 6.6e-4 eV, 7 % of it, where float64 gets it
to 5e-6.  Here it costs 1.5x (0.33 -> 0.51 s), not ORB's 2.7x.

**No Apple GPU.**  On macOS 13, where torch has no mps backend at all,
MatterSim does not ask before loading its weights onto it and the
process dies in ``torch.load`` with a segmentation fault -- not an
exception anything could catch.  Where mps does exist it cannot take
float64, which is the default here.  So 'auto' is CUDA or the CPU and
mps is not offered.

**Loading changes no global that matters here.**  Unlike ORB it leaves
torch's default dtype alone.  Importing it *does* replace every
handler loguru has with one of its own, which writes to stdout; nothing
in this application logs through loguru.

**One package conflicts.**  mattersim declares e3nn 0.5 or newer and
mace-torch pins 0.4.4, so pip will not resolve both extras into one
environment.  What MatterSim's inference imports from e3nn is in
0.4.4, so where MACE is installed the command offered
(:func:`install_command`) is mattersim with ``--no-deps`` and the three
packages it imports that MACE did not bring.
"""

from __future__ import annotations

import importlib.util
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

__all__ = ["BESIDE_MACE", "DEFAULT_MODEL", "DEVICE_CHOICES", "INSTALL",
           "KCAL_PER_EV", "install_command",
           "MODEL_CHOICES", "MODEL_SIZES", "OPTIONS",
           "MatterSimCalculator", "MatterSimOptions", "available",
           "build", "forget_models", "installed"]

#: The package that has to be installed, and how.
PACKAGE = "mattersim"
INSTALL = install.command("mattersim")

#: What MatterSim's inference imports that mace-torch did not already
#: bring, measured by installing it with ``--no-deps`` beside MACE and
#: importing :class:`mattersim.forcefield.MatterSimCalculator`.
BESIDE_MACE = ("mattersim>=1.2.5", "torch_runstats", "loguru",
               "deprecated")


def install_command() -> str:
    """The command to offer, which depends on whether MACE is here.

    The extra is right on its own and wrong beside MACE: its
    dependencies move e3nn to 0.6, which MACE refuses to load with,
    and that is what the extra did to the environment the first time
    it was followed from Preferences > Engines.  Beside MACE the
    command installs mattersim with ``--no-deps`` and the three
    packages it imports that MACE did not bring.
    """
    from xtal.ff.mace.calculator import installed as mace_installed

    if mace_installed():
        return install.packages(BESIDE_MACE, no_deps=True)
    return INSTALL

#: The two released checkpoints, by the name mattersim resolves and
#: downloads.  The parameter counts are upstream's.
MODEL_CHOICES = (
    ("MatterSim-v1.0.0-1M",
     "MatterSim 1M -- the smaller model, faster (recommended)"),
    ("MatterSim-v1.0.0-5M",
     "MatterSim 5M -- five times the parameters, more accurate"),
)
DEFAULT_MODEL = "MatterSim-v1.0.0-1M"

#: What the first use downloads, in MB, as GitHub reports it.
MODEL_SIZES = {"MatterSim-v1.0.0-1M": 18, "MatterSim-v1.0.0-5M": 91}

DEVICE_CHOICES = (
    ("auto", "The NVIDIA GPU if there is one, otherwise the CPU"),
    ("cpu", "CPU"),
    ("cuda", "NVIDIA GPU (cuda)"),
)


def installed() -> bool:
    """Whether ``mattersim`` is importable -- without importing it.

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
            False, f"MatterSim is not installed -- {install_command()}")
    if model not in dict(MODEL_CHOICES):
        return Availability(False, f"{model!r} is not a MatterSim "
                                   f"model this application offers")
    return Availability(
        True, f"{model} -- about {MODEL_SIZES[model]} MB, downloaded "
              f"to ~/.local/mattersim the first time it is used")


@dataclass(frozen=True)
class MatterSimOptions:
    """Everything about the calculation that is not the structure."""

    model: str = DEFAULT_MODEL
    device: str = "auto"
    #: See the module docstring: float32's noise is 7 % of the energy
    #: differences a line search reads.
    double_precision: bool = True


OPTIONS = (
    Param("model", "Model", kind="choice", choices=MODEL_CHOICES,
          default=DEFAULT_MODEL,
          help="Each is downloaded once, to ~/.local/mattersim."),
    Param("device", "Run on", kind="choice", choices=DEVICE_CHOICES,
          default="auto",
          help="MatterSim cannot load onto an Apple GPU, so on a Mac "
               "this is the CPU."),
    Param("double_precision", "Double precision", kind="bool",
          default=True,
          help="Leave this on for geometry optimisation: in single "
               "precision the model's own noise is a noticeable part "
               "of the energy differences an optimiser reads.  Off is "
               "about 1.5 times faster."),
)


# ======================================================================
#  THE MODEL, LOADED ONCE
# ======================================================================

_MODELS = ModelCache()


def _torch_device(wanted: str) -> str:
    """CUDA if asked for or there, otherwise the CPU -- never mps."""
    return torch_device(wanted, allow_mps=False)


#: A module global, as MACE's and ORB's are, so the tests answer "cpu"
#: without importing torch.
_device = _torch_device


def _load_model(options: MatterSimOptions):
    """An ASE calculator for these options, built once and kept.

    **This is the seam the tests use**, as in
    :mod:`xtal.ff.mace.calculator`.
    """
    key = (options.model, options.device, options.double_precision)
    return _MODELS.get(key, lambda: _build_model(options))


def _build_model(options: MatterSimOptions):
    """Load the model :func:`_load_model` found no cached copy of."""
    device = _device(options.device)
    if device == "mps":
        # Asked for by name.  Refused here because MatterSim's own
        # answer, on a Mac without the backend, is to kill the process.
        raise CalculatorError(
            "MatterSim cannot run on the Apple GPU; choose the CPU")
    try:
        from mattersim.forcefield import MatterSimCalculator as _Model
    except ImportError as exc:
        raise CalculatorError(
            f"MatterSim is not installed -- {install_command()} "
            f"({exc})") from None
    # Double precision needs the graph built in it.  MatterSim's default
    # path makes positions and the cell with torch.FloatTensor and only
    # then upcasts them to the model's dtype, which cannot put back the
    # digits float32 dropped: a 20 A coordinate is good to about 2e-6 A,
    # and along the force on MOF-74 the energy's slope disagreed with
    # the force by 3e-3 at a 1e-4 A step, against 6e-9 through
    # ``direct_graph``, which builds them in the model's dtype.  Same
    # energies otherwise: 8e-7 eV apart, the float32 truncation.
    kwargs = {"dtype": "float32"}
    if options.double_precision:
        kwargs = {"dtype": "float64", "direct_graph": True}
    try:
        return _Model(load_path=options.model, device=device, **kwargs)
    except Exception as exc:                        # noqa: BLE001
        raise CalculatorError(
            f"the MatterSim model could not be loaded "
            f"({options.model}): {exc}") from None


def forget_models() -> None:
    """Drop the loaded models.  For the tests."""
    _MODELS.clear()


# ======================================================================
#  THE CALCULATOR
# ======================================================================

class MatterSimCalculator(ASECalculator):
    """A MatterSim model over a structure's P1 cell."""

    name = "mattersim"
    label = "MatterSim"
    install = INSTALL

    def __init__(self, structure, options: MatterSimOptions | None = None):
        super().__init__(structure, options or MatterSimOptions())

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

def build(structure, **options) -> MatterSimCalculator:
    """Registry entry point: keyword options in, calculator out."""
    return MatterSimCalculator(structure, MatterSimOptions(**options))


ENGINES.register(Engine(
    name="mattersim",
    label="MatterSim (machine-learned)",
    description="Microsoft's universal potential, an M3GNet trained "
                "across temperature and pressure.  Like MACE it needs "
                "no parameters assigning, and it is the fastest of "
                "the three.  Its authors note relatively low accuracy "
                "for organic polymeric systems, which is the linker "
                "half of a framework; run here without a dispersion "
                "correction.",
    build=build,
    order=32,
    provides=frozenset({"forces", "stress", "periodic"}),
    options=OPTIONS,
    check=available,
    references=(
        arxiv("MatterSim: Yang et al., 2024", "2405.04967"),
        github("microsoft/mattersim"),
    ),
))
