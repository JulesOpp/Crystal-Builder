"""
xtal.ff.xtb.calculator
======================
The GFN family as an energy engine, one subprocess per evaluation.

GFN1-xTB and GFN2-xTB are semiempirical tight binding and GFN-FF is a
generic force field fitted over the same reference data.  All three sit
between UFF and DFTB+ in every dimension that matters: they need no
parameter set to be downloaded and no atom typing to be got right,
they cost seconds rather than milliseconds or minutes, and they will
answer for a metal node that UFF has to be extended to describe at all.

Three things are particular to this engine.

**Two binaries, one entry.**  ``tblite`` and ``xtb`` are separate
programs, and under a cell they divide the family cleanly between
them: the two tight-binding methods are tblite's and GFN-FF is xtb's
(see :data:`METHODS` for what was measured to establish that).
Rather than two engines a user would have to know the difference
between, this is one engine whose *method* is the choice and whose
availability is answered per method -- so on a machine with only
tblite, GFN2 runs and GFN-FF greys out naming xtb.  There is
deliberately no control for picking the program: the method already
decides, and a chooser could only ever narrow it to nothing.

**The scratch directory persists for the calculator's life.**  GFN-FF
spends its first call working out a topology and writes it to
``gfnff_topo``; every later call in the same directory reads it back.
That is the same bargain :mod:`xtal.ff.dftb.calculator` makes with SCC
charges, and it is worth more here, because the topology is most of
what a GFN-FF step costs.

**No analytic stress is claimed, and that was measured rather than
assumed.**  tblite writes a virial and xtb a lattice derivative, and
both are tempting: a claimed stress makes variable-cell relaxation
twelve times cheaper.  The obvious conversion of tblite's virial --
divide by the cell volume -- was checked against
:meth:`~xtal.ff.api.Calculator.numeric_stress` on quartz under
GFN1-xTB, and it disagrees: 0.874 against 0.972 kcal/mol/A^3 on the
two equal diagonal components, with numeric stress stable to four
decimals from a 1e-3 strain down to 1e-5.  Ten per cent is not noise
and not a sign convention; it is a normalisation this code does not
understand.  A stress that is quietly wrong relaxes a cell to the
wrong volume and reports converging while it does it, so
``numeric_stress`` is used and the twelve evaluations are paid --
which is exactly what DFTB+ does, for exactly the same reason.
"""

from __future__ import annotations

import json
import re
import shutil
import signal
import tempfile
import weakref
from dataclasses import dataclass, fields
from pathlib import Path

import numpy as np

from xtal.core import p1
from xtal.ff.api import Calculator, CalculatorError, Result
from xtal.ff.registry import ENGINES, Engine
from xtal.io.gen import gen_string
from xtal.modules.process import ExternalProcess, MissingProgram, Program
from xtal.params import Availability, Param

#: Both programs work in Hartree and Bohr; everything above this works
#: in kcal/mol and Angstrom.
HARTREE = 627.5094740631
BOHR = 0.52917721090380

GEOMETRY_NAME = "geo.gen"
LOG_NAME = "xtb.out"
JSON_NAME = "tblite.json"
ENGRAD_NAME = "geo.engrad"

TBLITE = Program(
    name="tblite", label="tblite", env_var="XTAL_TBLITE",
    url="https://github.com/tblite/tblite  (conda install tblite "
        "-c conda-forge)", setting="tools/tblite")

XTB = Program(
    name="xtb", label="xTB", env_var="XTAL_XTB",
    url="https://github.com/grimme-lab/xtb  (conda install xtb "
        "-c conda-forge)", setting="tools/xtb")

#: Both, for :mod:`xtalapp.external` to offer a path for.
PROGRAMS = (TBLITE, XTB)

#: Method -> (label, the programs that can run it *under periodic
#: boundary conditions*, best first).  Everything this application
#: computes has a cell, so that qualifier is the whole story and not
#: a footnote:
#:
#: * GFN-FF is xtb's alone -- tblite is the tight-binding half of the
#:   family and has no force field in it;
#: * GFN2 is tblite's alone -- xtb's GFN2 has multipole electrostatics
#:   that its periodic code does not implement, and asking for it
#:   stops with "Multipoles not available with PBC" after the geometry
#:   has been written and the process launched;
#: * GFN1 is tblite's alone as well.  xtb nominally has it under a
#:   cell and it does not work: 6.7.1 fails to diagonalise a 2-atom
#:   silicon cell and segfaults on MOF-5 *after* reporting its own SCC
#:   converged, with or without ``--grad`` and with none of our flags
#:   involved.  Offering it means offering a crash.
#:
#: So the split is the clean one it looks like: tblite is the
#: tight-binding half of the family and xtb is the force field.
METHODS = {
    "gfn2": ("GFN2-xTB", ("tblite",)),
    "gfn1": ("GFN1-xTB", ("tblite",)),
    "gfnff": ("GFN-FF", ("xtb",)),
}

METHOD_CHOICES = tuple((key, label) for key, (label, _) in METHODS.items())


def _labelled() -> dict[str, Program]:
    """:data:`PROGRAMS`, keyed the way :data:`METHODS` names them.

    By ``setting`` and not by ``name``: ``name`` is what gets searched
    for on PATH, so it is the thing a test replaces to say "this is
    not installed anywhere", and a lookup through it would then fail
    to find the program at all and report the wrong thing entirely.
    """
    return {p.setting.rsplit("/", 1)[-1]: p for p in PROGRAMS}


def _programs_for(method: str) -> tuple[Program, ...]:
    """The programs that can run this method under a cell.

    One each, as :data:`METHODS` explains, which is why there is no
    control offering the choice: it could only ever narrow this to
    nothing.
    """
    _, names = METHODS.get(method, ("", ()))
    known = _labelled()
    return tuple(known[n] for n in names if n in known)


def available(method: str = "gfn2", **_rest) -> Availability:
    """Installed, for the method that is actually selected.

    Takes the whole option set and reads one of it, because the
    registry hands the lot and the answer genuinely differs between
    them: GFN-FF needs xtb and the other two need tblite, so on a
    machine with one of the two binaries some methods run and some do
    not, and a check that ignored the method would be wrong for half
    of them whatever it said.
    """
    wanted = _programs_for(method)
    if not wanted:
        return Availability(
            False, f"{method} is not a method this engine knows.")
    for program in wanted:
        found = program.locate()
        if found is not None:
            return Availability(True, str(found))
    return wanted[0].availability()


# ======================================================================
#  OPTIONS
# ======================================================================

@dataclass(frozen=True)
class XTBOptions:
    """Everything about the calculation that is not the structure."""

    method: str = "gfn2"
    charge: float = 0.0
    accuracy: float = 1.0
    temperature: float = 300.0
    max_iterations: int = 250


#: The same options as a declaration, for the generated form.  Written
#: once here rather than twice, so a field cannot exist in the dialog
#: and not in the calculation.
OPTIONS = (
    Param("method", "Method", kind="choice", choices=METHOD_CHOICES,
          default="gfn2",
          help="GFN2-xTB is the default and the most accurate of the "
               "three; GFN1-xTB is older and more robust for metals; "
               "GFN-FF is a force field and is orders of magnitude "
               "faster, which for a framework of a few thousand atoms "
               "is the difference between a relaxation and an "
               "afternoon.  The method decides which binary runs: "
               "tblite for the two tight-binding ones and xtb for "
               "GFN-FF."),
    Param("charge", "Total charge", kind="float", default=0.0,
          minimum=-20.0, maximum=20.0, step=1.0, decimals=1,
          suffix=" e"),
    Param("accuracy", "Accuracy", kind="float", default=1.0,
          minimum=0.01, maximum=1000.0, step=0.1, decimals=2,
          help="The SCF convergence criterion, as a multiplier: "
               "smaller is tighter and slower.  Ignored by GFN-FF, "
               "which has no SCF."),
    Param("temperature", "Electronic temperature", kind="float",
          default=300.0, minimum=0.0, maximum=10000.0, step=50.0,
          decimals=1, suffix=" K",
          help="Fermi filling.  Not zero by default, for the same "
               "reason DFTB+'s is not: a metallic framework at "
               "exactly zero has no gap to fill and the cycle "
               "oscillates rather than failing."),
    Param("max_iterations", "Max SCF iterations", kind="int",
          default=250, minimum=1, maximum=10000),
)


# ======================================================================
#  THE CALCULATOR
# ======================================================================

class XTBCalculator(Calculator):
    """GFN1-xTB, GFN2-xTB or GFN-FF over a structure's P1 cell."""

    name = "xtb"
    label = "xTB"
    provides_forces = True
    #: See the module docstring: both programs report something that
    #: looks like a stress and neither agrees with a numeric one.
    provides_stress = False

    def __init__(self, structure, options: XTBOptions | None = None):
        self.options = options or XTBOptions()
        self.structure = structure
        self.cell = p1.expand(structure)
        if self.cell.n_atoms == 0:
            raise CalculatorError(
                "there are no atoms to compute an energy for")
        self.symbols = tuple(self.cell.elements)
        self.warnings: list[str] = []

        self.program, self.binary = self._resolve()

        self.directory = Path(tempfile.mkdtemp(prefix="xtb-"))
        # Cleaned when this object goes, not at interpreter exit --
        # and it is what makes GFN-FF's topology worth writing.
        self._cleanup = weakref.finalize(
            self, shutil.rmtree, self.directory, True)
        self.calls = 0
        self.seconds = 0.0

    # -- what the panel asks about -------------------------------------

    @property
    def n_atoms(self) -> int:
        return self.cell.n_atoms

    def summary(self) -> str:
        label = METHODS.get(self.options.method,
                            (self.options.method, ()))[0]
        return (f"{self.n_atoms} atoms, {label}, through "
                f"{self.program.label}")

    def _resolve(self) -> tuple[Program, str]:
        wanted = _programs_for(self.options.method)
        for program in wanted:
            found = program.locate()
            if found is not None:
                return program, str(found)
        if not wanted:
            raise CalculatorError(
                available(self.options.method).reason)
        try:
            wanted[-1].resolve()
        except MissingProgram as exc:
            raise CalculatorError(
                f"{exc}.  On this machine the usual way in is conda: "
                f"\"conda install {wanted[-1].name} -c conda-forge\", "
                f"or set {wanted[-1].env_var} to the binary."
            ) from None
        raise CalculatorError(                      # pragma: no cover
            f"{wanted[-1].label} could not be resolved")

    # -- the evaluation -------------------------------------------------

    def _argv(self) -> list[str]:
        """The command line, for whichever of the two is running."""
        o = self.options
        if self.program is TBLITE:
            return [self.binary, "run", "--method", o.method,
                    "--charge", f"{o.charge:g}",
                    "--acc", f"{o.accuracy:g}",
                    "--etemp", f"{o.temperature:g}",
                    "--iterations", str(o.max_iterations),
                    "--grad", "--json", JSON_NAME, GEOMETRY_NAME]
        method = ("--gfnff" if o.method == "gfnff"
                  else f"--gfn{o.method[-1]}")
        return [self.binary, GEOMETRY_NAME, method, "--grad",
                "--chrg", f"{o.charge:g}", "--acc", f"{o.accuracy:g}",
                "--etemp", f"{o.temperature:g}",
                "--iterations", str(o.max_iterations)]

    def compute(self, positions, matrix) -> Result:
        """Energy and forces at these cartesian positions."""
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
        self._launch()
        energy, gradient = self._read()
        return Result(energy=energy * HARTREE,
                      forces=-gradient * (HARTREE / BOHR),
                      terms={self.options.method: energy * HARTREE})

    def _launch(self):
        log = _Log(self.directory / LOG_NAME)
        process = ExternalProcess(self._argv(), cwd=self.directory,
                                  log=log)
        outcome = process.run()
        self.calls += 1
        self.seconds += outcome.seconds
        log.close()
        if not outcome.ok:
            raise CalculatorError(_why(outcome, self.program,
                                       self.directory,
                                       self.options.method))
        return outcome

    def _read(self):
        if self.program is TBLITE:
            return read_tblite_json(self.directory / JSON_NAME,
                                    self.n_atoms)
        return read_engrad(self.directory / ENGRAD_NAME, self.n_atoms)


# ======================================================================
#  READING WHAT THEY WROTE
# ======================================================================

def read_tblite_json(path, n_atoms: int):
    """``(energy, gradient)`` from tblite's JSON dump, in Hartree and
    Hartree/Bohr.

    tblite writes a ``virial`` beside them and it is deliberately not
    read -- see the module docstring for the measurement that decided
    that.
    """
    path = Path(path)
    if not path.is_file():
        raise CalculatorError(
            f"tblite exited without writing {path.name}, which it "
            f"only does when the run itself failed.  Its own output "
            f"is in {path.parent / LOG_NAME}.")
    try:
        data = json.loads(path.read_text())
    except ValueError as exc:
        raise CalculatorError(
            f"tblite wrote a {path.name} that is not JSON: {exc}"
        ) from None
    if "energy" not in data:
        raise CalculatorError(
            "tblite finished without a total energy, which nearly "
            "always means the SCF did not converge.  Raise the "
            "electronic temperature or the iteration limit, or read "
            f"{path.parent / LOG_NAME}.")
    gradient = data.get("gradient")
    if gradient is None or len(gradient) != 3 * n_atoms:
        raise CalculatorError(
            f"tblite printed an energy and no gradient for "
            f"{n_atoms} atoms.  The optimiser needs both.")
    return (float(data["energy"]),
            np.array(gradient, dtype=float).reshape(n_atoms, 3))


def read_engrad(path, n_atoms: int):
    """``(energy, gradient)`` from xtb's ``.engrad``.

    The format is a comment line, a blank-free block of numbers, and
    nothing that names what any of them is -- so it is read by
    position: the atom count, then the energy, then 3N gradient
    components.  xtb's lattice derivative goes to a separate file and
    is not read; see the module docstring for why neither program's
    is.
    """
    path = Path(path)
    if not path.is_file():
        raise CalculatorError(
            f"xtb exited without writing {path.name}.  Its own "
            f"output is in {path.parent / LOG_NAME}.")
    numbers = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            numbers.append(float(line))
        except ValueError:
            break                       # the coordinate block below
    if not numbers:
        raise CalculatorError(
            f"xtb's {path.name} holds no numbers at all")
    if int(numbers[0]) != n_atoms:
        raise CalculatorError(
            f"xtb answered for {int(numbers[0])} atoms and was asked "
            f"about {n_atoms}")
    if len(numbers) < 2 + 3 * n_atoms:
        raise CalculatorError(
            f"xtb's {path.name} holds {len(numbers)} numbers where "
            f"{2 + 3 * n_atoms} were expected for {n_atoms} atoms.")
    gradient = np.array(numbers[2:2 + 3 * n_atoms],
                        dtype=float).reshape(n_atoms, 3)
    return float(numbers[1]), gradient


#: How xtb says what went wrong: an ``[ERROR]`` banner and then a
#: numbered chain of ``-3- scc_core: ...`` lines, innermost last --
#: followed by a backtrace of bare hex addresses.  The tail of the
#: output is therefore the least informative part of it, which is why
#: this is picked out rather than the last few lines being taken.
_SPOKEN = re.compile(r"^\s*(?:\[ERROR\]|\[WARNING\]|-\d+-\s)")


def _how_it_died(returncode) -> str:
    """The exit status as a clause, and a signal as what it is.

    A negative status is Python's way of saying the process was
    killed by that signal, and "exited with status -11" is a sentence
    only somebody who already knows that can read.  It matters which
    it was: a non-zero status is the program rejecting what it was
    given, and a signal is the program falling over -- one of those is
    something the user can fix by changing an option and the other is
    not.
    """
    if returncode is None:                          # pragma: no cover
        return "ended without a status"
    if returncode >= 0:
        return f"exited with status {returncode}"
    try:
        name = signal.Signals(-returncode).name
    except ValueError:                              # pragma: no cover
        name = f"signal {-returncode}"
    return f"was killed by {name}"


def _why(outcome, program, directory, method="") -> str:
    """A failed run, as something to act on."""
    lines = [line for line in outcome.lines if line.strip()]
    spoken = [line for line in lines if _SPOKEN.match(line)]
    said = "\n".join(f"    {line.strip()}"
                      for line in (spoken or lines)[-6:])
    note = ""
    if (outcome.returncode or 0) < 0:
        note = (f"\nThat is a crash inside {program.label} and not "
                f"something this structure or these options did "
                f"wrong -- another method, or another build of the "
                f"same program, is worth trying before anything "
                f"else.")
        if method == "gfn2":
            # Measured: tblite 0.6.0 segfaults on periodic GFN2 for a
            # two-atom silicon cell as readily as for MOF-5, where
            # 0.3.0 runs both and GFN1 runs on either.  It is a bug in
            # that build, and the user cannot be expected to guess
            # that the method is what to change.
            note += ("  Some builds of tblite crash on GFN2 under a "
                     "cell whatever the structure is; GFN1-xTB "
                     "through the same binary is the quickest way to "
                     "tell that apart from a problem with this "
                     "crystal.")
    return (f"{program.label} {_how_it_died(outcome.returncode)}.  "
            f"It said:\n{said}{note}\n"
            f"The whole run is in {directory}.")


class _Log:
    """The tiny bit of :class:`xtal.workspace.RunLog` that
    :class:`ExternalProcess` uses.

    A calculator has no run folder -- the Force Field panel owns the
    one for the whole optimisation -- so the program's own output goes
    into the scratch directory, where a failure message can point at
    it.
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

def build(structure, **options) -> XTBCalculator:
    """Registry entry point: keyword options in, calculator out."""
    known = {f.name for f in fields(XTBOptions)}
    return XTBCalculator(structure, XTBOptions(
        **{k: v for k, v in options.items() if k in known}))


ENGINES.register(Engine(
    name="xtb",
    label="xTB (GFN)",
    description="Semiempirical tight binding and the GFN force "
                "field, through the tblite or xtb binary -- no "
                "parameter set to download and no atom typing to get "
                "right.",
    build=build,
    order=20,
    provides=frozenset({"forces", "periodic"}),
    options=OPTIONS,
    check=available,
))
