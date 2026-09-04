"""
xtal.ff.dftb.calculator
=======================
DFTB+ as an energy engine, one subprocess per evaluation.

UFF is in-process and answers in milliseconds; DFTB+ is a binary and
answers in seconds to minutes.  Everything else about them is the
same shape, and that is deliberate: a :class:`~xtal.ff.api.Calculator`
is built for a structure and then asked for the energy and the forces
at a geometry, so DFTB+ implementing that interface gets the optimiser,
the symmetry projection, the worker thread, the live plot, the
trajectory, the frozen selection and the single undoable command at
the end without any of them learning what DFTB+ is.

Four things are particular to it.

**The scratch directory persists for the calculator's life.**  Not one
temporary directory per evaluation: the charges from the last step are
the starting guess for this one (``ReadInitialCharges``), which is most
of the cost of an SCC cycle, and they live in a file in that directory.
It goes away when the calculator does.

**No analytic stress is claimed.**  DFTB+ prints one, and the sign and
volume conventions of that block are not something to guess at: a
stress read with the wrong sign relaxes a cell in the wrong direction
and reports converging while it does it.  So
:meth:`~xtal.ff.api.Calculator.numeric_stress` is used, at twelve
evaluations a step -- which is expensive and honest, and is exactly
what UFF does.

**A failure is a sentence, not an exit status.**  An SCC that will not
converge, a parameter file that is missing, a binary that is not
installed: each of them is caught and turned into a
:class:`~xtal.ff.api.CalculatorError` naming what happened and what to
do, because the panel puts it in front of the user unmodified.

**Nothing is guessed silently.**  A maximum angular momentum this
application had to derive rather than look up, a Hubbard derivative
DFTB3 wanted and 3ob does not carry -- both are answers that change
the number without failing, so both are collected in
:attr:`DFTBCalculator.warnings` and shown.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import weakref
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from xtal.core import p1
from xtal.ff.api import Calculator, CalculatorError, Result
from xtal.ff.dftb import hsd, params
from xtal.ff.registry import ENGINES, Engine
from xtal.io.gen import gen_string
from xtal.modules.process import ExternalProcess, MissingProgram, Program
from xtal.params import Availability, Param

#: DFTB+ works in Hartree and Bohr; everything above this works in
#: kcal/mol and Angstrom.
HARTREE = 627.5094740631
BOHR = 0.52917721090380

GEOMETRY_NAME = "geo.gen"
INPUT_NAME = "dftb_in.hsd"
OUTPUT_NAME = "detailed.out"
LOG_NAME = "dftb.out"

PROGRAM = Program(
    name="dftb+", label="DFTB+", env_var="XTAL_DFTB",
    url="https://dftbplus.org  (conda install 'dftbplus=*=nompi_*' "
        "-c conda-forge)", setting="tools/dftb")

_ENERGY = re.compile(
    r"Total (?:Mermin free )?energy:\s*(-?\d+\.\d+)\s*H",
    re.IGNORECASE)
_FORCES = re.compile(r"Total Forces", re.IGNORECASE)
_NUMBER = re.compile(r"-?\d+\.\d+(?:[eEdD][-+]?\d+)?")


def available(parameter_directory: str = "", **_rest) -> Availability:
    """Installed, and pointed at a parameter set.

    Takes the options and ignores all but one of them, because the
    registry hands the whole set: which directory the parameters are
    in is a field in the form, and a check that ignored it would
    report the engine unavailable while the user was looking at the
    box that makes it available.
    """
    directory = parameter_directory
    found = PROGRAM.locate()
    if found is None:
        return PROGRAM.availability()
    if hsd.slater_koster_directory(directory) is None:
        return Availability(
            False,
            f"DFTB+ is installed at {found}, but no Slater-Koster "
            f"parameter directory has been set.  They are separate "
            f"downloads from dftb.org; point 'Parameter directory' or "
            f"the {hsd.ENV_VAR} environment variable at the folder "
            f"they unpack into.")
    return Availability(True, str(found))


# ======================================================================
#  OPTIONS
# ======================================================================

@dataclass(frozen=True)
class DFTBOptions:
    """Everything about the calculation that is not the structure."""

    #: The nearest thing DFTB has to a functional -- see
    #: :data:`xtal.ff.dftb.params.METHODS`.
    method: str = "dftb3"
    parameter_directory: str = ""
    dispersion: str = "none"
    charge: float = 0.0
    scc_tolerance: float = 1e-5
    max_scc: int = 250
    #: Electronic temperature in Kelvin.  Not zero by default: a
    #: metallic framework at exactly zero has no gap to fill and the
    #: SCC cycle oscillates for ever rather than failing.
    temperature: float = 300.0
    #: Reciprocal-space sampling density; 0 means the Gamma point
    #: alone, which is what a large cell wants.
    k_spacing: float = hsd.DEFAULT_SPACING
    #: ``"Cl=d, Zn=d"`` -- see
    #: :func:`xtal.ff.dftb.params.parse_overrides`.
    angular_momentum: str = ""

    def to_dict(self) -> dict:
        return {"method": self.method,
                "dispersion": self.dispersion,
                "charge": self.charge,
                "scc_tolerance": self.scc_tolerance,
                "temperature": self.temperature,
                "k_spacing": self.k_spacing}


#: The same options as a declaration, for the generated form.  Written
#: once here rather than twice, so a field cannot exist in the dialog
#: and not in the calculation.
OPTIONS = (
    Param("method", "Hamiltonian", kind="choice",
          choices=params.METHODS, default="dftb3",
          help="The nearest thing DFTB has to a functional.  DFTB3 is "
               "third order and is what the 3ob set was fitted for; "
               "SCC-DFTB is second order and works with any set; "
               "non-SCC has no charge transfer at all and is for a "
               "first look."),
    Param("parameter_directory", "Parameter directory", kind="path",
          help="The folder of Slater-Koster .skf files.  They are "
               "separate downloads from dftb.org -- 3ob for organics, "
               "matsci for inorganic solids.  Left empty, the "
               f"{hsd.ENV_VAR} environment variable is used."),
    Param("dispersion", "Dispersion", kind="choice",
          choices=params.DISPERSIONS, default="none",
          help="DFTB has no dispersion of its own, and a framework's "
               "pore size is a dispersion-bound number -- so for a "
               "porous solid this is not an optional refinement."),
    Param("charge", "Total charge", kind="float", default=0.0,
          minimum=-20.0, maximum=20.0, step=1.0, decimals=1,
          suffix=" e"),
    Param("temperature", "Electronic temperature", kind="float",
          default=300.0, minimum=0.0, maximum=10000.0, step=50.0,
          decimals=1, suffix=" K",
          help="Fermi filling.  Not zero by default: a metallic "
               "framework at exactly zero has no gap to fill and the "
               "SCC cycle oscillates for ever rather than failing."),
    Param("k_spacing", "K-point spacing", kind="float",
          default=hsd.DEFAULT_SPACING, minimum=0.0, maximum=2.0,
          step=0.05, decimals=2, suffix=" 1/A",
          help="The mesh is worked out from the cell: a cell twice as "
               "long gets half as many k-points along it.  Zero is "
               "the Gamma point alone, which is what a large cell "
               "wants."),
    Param("scc_tolerance", "SCC tolerance", kind="float",
          default=1e-5, minimum=1e-9, maximum=1e-2, step=1e-5,
          decimals=8),
    Param("max_scc", "Max SCC iterations", kind="int", default=250,
          minimum=1, maximum=10000),
    Param("angular_momentum", "Angular momentum overrides",
          kind="text",
          help="Per element, as 'Cl=d, Zn=d'.  The built-in table "
               "follows 3ob; a set that disagrees with it gives a "
               "number rather than an error, which is why this is "
               "here."),
)


# ======================================================================
#  THE CALCULATOR
# ======================================================================

class DFTBCalculator(Calculator):
    """DFTB+ over a structure's P1 cell."""

    name = "dftb"
    label = "DFTB+"
    provides_forces = True
    #: See the module docstring: DFTB+ prints a stress and its
    #: conventions are not something to guess at.
    provides_stress = False

    def __init__(self, structure, options: DFTBOptions | None = None):
        self.options = options or DFTBOptions()
        self.structure = structure
        self.cell = p1.expand(structure)
        if self.cell.n_atoms == 0:
            raise CalculatorError(
                "there are no atoms to compute an energy for")
        self.symbols = tuple(self.cell.elements)
        self.warnings: list[str] = []

        self.binary = self._resolve()
        refusal = hsd.check(self.symbols,
                            self.options.parameter_directory)
        if refusal:
            raise CalculatorError(refusal)

        self.k_points = ((1, 1, 1) if self.options.k_spacing <= 0
                         else hsd.mesh_for(structure.lattice,
                                           self.options.k_spacing))
        self._note_guesses()
        self.directory = Path(tempfile.mkdtemp(prefix="dftb-"))
        # Cleaned when this object goes, not at interpreter exit: a
        # long session doing twenty single points would otherwise keep
        # twenty scratch directories of charges and outputs.
        self._cleanup = weakref.finalize(
            self, shutil.rmtree, self.directory, True)
        self._have_charges = False
        self.calls = 0
        self.seconds = 0.0

    # -- what the panel asks about -------------------------------------

    @property
    def n_atoms(self) -> int:
        return self.cell.n_atoms

    def summary(self) -> str:
        method = dict(params.METHODS).get(self.options.method,
                                          self.options.method)
        mesh = "x".join(str(k) for k in self.k_points)
        directory = hsd.slater_koster_directory(
            self.options.parameter_directory)
        return (f"{self.n_atoms} atoms, {method.split(' (')[0]}, "
                f"{mesh} k-points, parameters from "
                f"{directory.name if directory else '?'}")

    def _resolve(self) -> str:
        try:
            return str(PROGRAM.resolve())
        except MissingProgram as exc:
            raise CalculatorError(
                f"{exc}.  On this machine the usual way in is "
                f"conda: install it with "
                f"\"conda install 'dftbplus=*=nompi_*' -c "
                f"conda-forge\", or set {PROGRAM.env_var} to the "
                f"binary.") from None

    def _note_guesses(self) -> None:
        """Say what had to be assumed, before any number is believed.

        Neither of these fails: DFTB+ takes what it is given, so a
        guess that is wrong comes back as a plausible energy.
        """
        overrides = params.parse_overrides(
            self.options.angular_momentum)
        guessed = [s for s in sorted(set(self.symbols))
                   if s not in overrides
                   and not params.angular_momentum(s)[1]]
        if guessed:
            self.warnings.append(
                f"No angular momentum is tabulated for "
                f"{', '.join(guessed)}, so one was derived from the "
                f"row of the periodic table.  Check it against your "
                f"parameter set and override it if it disagrees -- "
                f"DFTB+ takes what it is given.")
        if self.options.method == "dftb3":
            unfitted = [s for s in sorted(set(self.symbols))
                        if s not in params.HUBBARD_DERIVS]
            if unfitted:
                self.warnings.append(
                    f"DFTB3 needs a Hubbard derivative per element "
                    f"and 3ob publishes none for "
                    f"{', '.join(unfitted)}.  Those elements are "
                    f"being treated at second order, which is a "
                    f"different model rather than a coarser one -- "
                    f"SCC-DFTB is the honest choice if that is most "
                    f"of the structure.")

    # -- the evaluation -------------------------------------------------

    def compute(self, positions, matrix) -> Result:
        """Energy and forces at these cartesian positions.

        Blocking, and one whole DFTB+ run.  There is no way to
        interrupt it: the optimiser's Stop is honoured between steps,
        which on a slow SCC cycle means Stop takes until the end of
        the current evaluation.
        """
        from xtal.core.lattice import Lattice
        from xtal.core.site import Site
        from xtal.core.spacegroup import SpaceGroup
        from xtal.core.structure import Structure

        positions = np.asarray(positions, dtype=float).reshape(-1, 3)
        matrix = np.asarray(matrix, dtype=float).reshape(3, 3)
        if len(positions) != self.n_atoms:
            raise CalculatorError(
                f"this calculator was built for {self.n_atoms} atoms "
                f"and was handed {len(positions)}")
        lattice = Lattice(matrix)
        frac = positions @ np.linalg.inv(matrix)
        moved = Structure(
            lattice=lattice,
            sites=[Site(symbol, f) for symbol, f
                   in zip(self.symbols, frac, strict=True)],
            space_group=SpaceGroup.p1())

        (self.directory / GEOMETRY_NAME).write_text(gen_string(moved))
        (self.directory / INPUT_NAME).write_text(hsd.hsd_string(
            self.symbols, self.options, GEOMETRY_NAME,
            read_charges=self._have_charges, k_points=self.k_points))
        result = self._launch()
        energy, forces = self._read(result)
        self._have_charges = self.options.method != "non-scc"
        return Result(energy=energy, forces=forces,
                      terms={"dftb": energy})

    def _launch(self):
        log = _Log(self.directory / LOG_NAME)
        process = ExternalProcess([self.binary], cwd=self.directory,
                                  log=log)
        outcome = process.run()
        self.calls += 1
        self.seconds += outcome.seconds
        log.close()
        if not outcome.ok:
            raise CalculatorError(_why(outcome, self.directory))
        return outcome

    def _read(self, outcome):
        path = self.directory / OUTPUT_NAME
        if not path.is_file():
            raise CalculatorError(
                f"DFTB+ exited without writing {OUTPUT_NAME}.  Its "
                f"own output is in {self.directory / LOG_NAME}.")
        text = path.read_text()
        energy = parse_energy(text)
        if energy is None:
            raise CalculatorError(
                "DFTB+ finished without a total energy, which nearly "
                "always means the SCC cycle did not converge.  Raise "
                "the electronic temperature or the iteration limit, "
                f"or read {self.directory / LOG_NAME}.")
        forces = parse_forces(text, self.n_atoms)
        if forces is None:
            raise CalculatorError(
                "DFTB+ printed an energy and no forces.  The "
                "optimiser needs both; this usually means the input "
                "lost its Analysis block.")
        return energy * HARTREE, forces * (HARTREE / BOHR)


# ======================================================================
#  READING WHAT IT WROTE
# ======================================================================

def parse_energy(text: str) -> float | None:
    """The total energy in Hartree, or ``None``.

    The Mermin free energy is what DFTB+ calls the total once there is
    a finite electronic temperature, and it is the one whose gradient
    the forces are -- so it is taken when it is there, which the
    regular expression does by matching either spelling and the last
    match winning.
    """
    found = _ENERGY.findall(text)
    return float(found[-1]) if found else None


def parse_forces(text: str, n_atoms: int) -> np.ndarray | None:
    """The force on every atom in Hartree/Bohr, or ``None``."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not _FORCES.search(line):
            continue
        rows = []
        for row in lines[index + 1:]:
            numbers = _NUMBER.findall(row)
            if len(numbers) < 3:
                break
            rows.append([float(v.replace("D", "E").replace("d", "E"))
                         for v in numbers[-3:]])
            if len(rows) == n_atoms:
                break
        if len(rows) == n_atoms:
            return np.array(rows, dtype=float)
    return None


def _why(outcome, directory) -> str:
    """A failed run, as something to act on."""
    tail = [line for line in outcome.lines if line.strip()]
    said = "\n".join(f"    {line}" for line in tail[-6:])
    return (f"DFTB+ exited with status {outcome.returncode}.  Its "
            f"last output was:\n{said}\n"
            f"The whole run is in {directory}.")


class _Log:
    """The tiny bit of :class:`xtal.workspace.RunLog` that
    :class:`ExternalProcess` uses.

    A calculator has no run folder -- the Force Field panel owns the
    one for the whole optimisation -- so DFTB+'s own output goes into
    the scratch directory, where a failure message can point at it.
    """

    def __init__(self, path):
        self.path = Path(path)
        self._handle = self.path.open("w")

    def write(self, text: str) -> None:
        self._handle.write(f"{text}\n")
        self._handle.flush()

    def close(self) -> None:
        if not self._handle.closed:
            self._handle.close()


# ======================================================================
#  THE ENGINE
# ======================================================================

def build(structure, **options) -> DFTBCalculator:
    """Registry entry point: keyword options in, calculator out."""
    known = {p.name for p in OPTIONS}
    return DFTBCalculator(structure, DFTBOptions(
        **{k: v for k, v in options.items() if k in known}))


ENGINES.register(Engine(
    name="dftb",
    label="DFTB+",
    description="Density-functional tight binding, through the DFTB+ "
                "binary -- DFT-like and fast enough to relax a "
                "framework UFF can only approximate.",
    build=build,
    provides=frozenset({"forces", "periodic"}),
    options=OPTIONS,
    check=available,
))
