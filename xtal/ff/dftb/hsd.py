"""
xtal.ff.dftb.hsd
================
Writing ``dftb_in.hsd``, and refusing before the run rather than
inside it.

HSD is DFTB+'s input language: nested blocks of ``Key = Value`` with
braces.  It is written here as text rather than through a library
because what this application needs of it is a single point with
forces and nothing else -- the geometry moves under
:mod:`xtal.ff.optimize`, so DFTB+'s own driver is never asked for --
and a hundred lines of formatting is cheaper than a dependency.

**The Slater-Koster check is the important half of this module.**  The
parameter files are separate downloads, they are per element *pair*,
and a run that is missing one fails several seconds in with a message
naming a file rather than a problem.  Every pair present in the
structure is therefore checked before anything is launched, and the
missing ones are named -- which is the difference between "download
the 3ob set and point at it" and "Error: could not open Zn-N.skf".
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from itertools import product
from pathlib import Path

from xtal.ff.dftb import params

#: The environment variable DFTB+ users conventionally set to the
#: directory holding their Slater-Koster sets.  Read as a default so
#: that a machine set up for DFTB+ needs no preference filled in.
ENV_VAR = "DFTB_PREFIX"

#: Where a Slater-Koster set bundled with the source tree would be, the
#: same way :data:`xtal.modules.zeopp.BUNDLED` finds Zeo++'s binary --
#: checked last, after the preference and the environment variable, so
#: a user who has pointed at their own set gets it rather than the one
#: that ships in ``resources/``.
BUNDLED = ("resources", "PTBP")


def bundled() -> Path | None:
    """The set in ``resources/PTBP``, if this is a source checkout and
    it is actually there.

    It is gitignored -- 3ob-sized Slater-Koster sets do not belong in
    history -- so this is ``None`` on a checkout that has not had it
    dropped in, and that is a normal, supported state: ``check`` below
    says so in a sentence rather than pretending the folder exists.
    """
    import xtal
    candidate = Path(xtal.__file__).resolve().parent.parent.joinpath(
        *BUNDLED)
    return candidate if candidate.is_dir() else None

#: HSD's parser version.  Pinned rather than omitted, and pinned to a
#: *current* one rather than an old one: DFTB+ converts an older input
#: forward and prints a warning per keyword it renames while doing it,
#: which on a two-hundred-step relaxation is two hundred copies of the
#: same paragraph in the log.  Checked against DFTB+ 24.1, which reads
#: this without converting anything.
#:
#: An older DFTB+ than the rename below needs this lowered, and that is
#: the only change it needs -- which is why the keyword is derived from
#: it rather than written twice.
PARSER_VERSION = 14

#: ``Analysis/CalculateForces`` became ``PrintForces`` at parser
#: version 14, and the old spelling is *rejected* by a parser reading
#: at 14 rather than accepted quietly: it is reported as an ignored
#: node and the run then halts.  So the two travel together.
FORCES_RENAMED_AT = 14

SUFFIX = ".skf"


def slater_koster_directory(given: str = "") -> Path | None:
    """Where the parameter files are, or ``None``.

    The preference first, then ``DFTB_PREFIX``, then the set bundled
    in ``resources/PTBP`` on a source checkout that has one -- checked
    last, so a preference or an environment variable pointed
    somewhere else always wins over the bundled default rather than
    being silently overridden by it.  Nothing else is guessed from the
    filesystem: a directory found by searching would silently become
    part of the model.
    """
    for candidate in (given, os.environ.get(ENV_VAR, "")):
        text = str(candidate or "").strip()
        if text:
            path = Path(text).expanduser()
            if path.is_dir():
                return path
    return bundled()


def missing_parameters(symbols, directory) -> list[str]:
    """The ``A-B.skf`` files that are not there, in order.

    Both orders of every pair, because DFTB+ reads both and a set that
    ships only one is a set that will fail half way.
    """
    if directory is None:
        return []
    directory = Path(directory)
    wanted = [f"{a}-{b}{SUFFIX}"
              for a, b in product(sorted(set(symbols)), repeat=2)]
    return [name for name in wanted
            if not (directory / name).is_file()]


def check(symbols, given: str = "") -> str:
    """Why this cannot run, or ``""``.

    Called before the run folder is opened and before anything is
    launched, which is the whole point: the answer is a sentence about
    what to download, not an exit status.
    """
    directory = slater_koster_directory(given)
    if directory is None:
        return (
            "DFTB+ needs a directory of Slater-Koster parameter files "
            "and has not been given one.  They are separate downloads "
            "from dftb.org -- 3ob for organics, matsci for inorganic "
            "solids -- and the folder they unpack into is what goes "
            "in 'Parameter directory', or in the DFTB_PREFIX "
            "environment variable.")
    missing = missing_parameters(symbols, directory)
    if missing:
        shown = ", ".join(missing[:6])
        more = "" if len(missing) <= 6 else f" and {len(missing) - 6} more"
        return (
            f"{directory.name} has no parameters for "
            f"{len(missing)} of the element pairs in this structure "
            f"({shown}{more}).  DFTB+ would fail several seconds into "
            f"the run naming one file; a set that covers every "
            f"element present is what it needs.")
    return ""


# ======================================================================
#  THE INPUT
# ======================================================================

def hsd_string(symbols, options, geometry: str = "geo.gen",
               read_charges: bool = False,
               k_points=(1, 1, 1), periodic: bool = True,
               driver=None, analysis=None, detailed_xml: bool = False,
               eigenvectors: bool = False,
               max_scc: int | None = None) -> str:
    """One input: a single point with forces unless told otherwise.

    ``options`` is a :class:`~xtal.ff.dftb.calculator.DFTBOptions`.
    The geometry is referenced rather than inlined so that a step of
    an optimisation rewrites one small file and leaves this one alone
    -- which also makes the last input in the scratch directory the
    one somebody can run by hand.

    The rest is for the runs that are DFTB+'s own rather than one
    evaluation of ours: ``k_points`` as :class:`KLines` for a band
    structure, a ``driver`` (:class:`Relax`, :class:`Dynamics`,
    :class:`SecondDerivatives`), an :class:`Analysis`, the detailed
    XML and eigenvectors ``waveplot`` reads, and ``max_scc`` to cap the
    cycle -- at one, for a band structure read from converged charges.
    """
    directory = slater_koster_directory(options.parameter_directory)
    prefix = f"{directory}{os.sep}" if directory is not None else ""
    analysis = analysis if analysis is not None else Analysis()
    if eigenvectors:
        # Under Analysis and not Options, where DFTB+ 24.1 reports it
        # as an ignored node and halts.
        analysis = replace(analysis, eigenvectors=True)
    lines = [
        "Geometry = GenFormat {",
        f'  <<< "{geometry}"',
        "}",
        "",
    ]
    if driver is not None:
        lines += driver.lines() + [""]
    lines.append("Hamiltonian = DFTB {")
    lines += _hamiltonian(symbols, options, prefix, read_charges,
                          k_points, periodic, max_scc)
    lines += ["}", ""]
    lines += analysis.lines() + [""]
    lines += ["Options {", "  WriteChargesAsText = No"]
    if detailed_xml:
        lines.append("  WriteDetailedXML = Yes")
    lines += [
        "}",
        "",
        f"ParserOptions {{ ParserVersion = {PARSER_VERSION} }}",
        "",
    ]
    return "\n".join(lines)


def _hamiltonian(symbols, options, prefix, read_charges, k_points,
                 periodic, max_scc=None) -> list[str]:
    scc = options.method != "non-scc"
    out = [
        f"  Scc = {_yes(scc)}",
    ]
    if scc:
        cycles = options.max_scc if max_scc is None else max_scc
        out += [
            f"  SccTolerance = {options.scc_tolerance:g}",
            f"  MaxSccIterations = {int(cycles)}",
        ]
        if read_charges:
            # Every step of a relaxation starts from the last step's
            # charges, which is most of the cost of an SCC cycle and
            # the reason a DFTB+ optimisation is affordable at all.
            out.append("  ReadInitialCharges = Yes")
    out += [
        "  SlaterKosterFiles = Type2FileNames {",
        f'    Prefix = "{prefix}"',
        '    Separator = "-"',
        f'    Suffix = "{SUFFIX}"',
        "  }",
        "  MaxAngularMomentum {",
    ]
    overrides = params.parse_overrides(options.angular_momentum)
    for symbol in sorted(set(symbols)):
        shell = overrides.get(symbol) or \
            params.angular_momentum(symbol)[0]
        out.append(f'    {symbol} = "{shell}"')
    out.append("  }")

    if options.method == "dftb3":
        out += ["  ThirdOrderFull = Yes",
                "  HubbardDerivs {"]
        for symbol in sorted(set(symbols)):
            # Zero for an element 3ob publishes no derivative for, which
            # is what treating it at second order means -- and what the
            # calculator's warning says happens.  Leaving the element
            # out is not the same thing: DFTB+ halts on the missing
            # child before it reads anything else.
            value = params.HUBBARD_DERIVS.get(symbol, 0.0)
            out.append(f"    {symbol} = {value}")
        out += ["  }",
                "  HCorrection = Damping { Exponent = 4.05 }"]
    if options.charge:
        out.append(f"  Charge = {float(options.charge):g}")
    if options.temperature > 0:
        out.append("  Filling = Fermi {")
        out.append(f"    Temperature [K] = {options.temperature:g}")
        out.append("  }")
    if periodic:
        out += _k_points(k_points)
    out += _dispersion(options)
    return out


def _k_points(mesh) -> list[str]:
    """A Monkhorst-Pack mesh, shifted where the count is even -- or a
    path, when it is :class:`KLines`.

    The shift is the half-grid offset that makes an even mesh sample
    the Brillouin zone symmetrically; an odd mesh already contains
    Gamma and must not be shifted off it.
    """
    if isinstance(mesh, KLines):
        return mesh.lines()
    a, b, c = (max(1, int(v)) for v in mesh)
    shifts = " ".join("0.0" if n % 2 else "0.5" for n in (a, b, c))
    return [
        "  KPointsAndWeights = SupercellFolding {",
        f"    {a} 0 0",
        f"    0 {b} 0",
        f"    0 0 {c}",
        f"    {shifts}",
        "  }",
    ]


def _dispersion(options) -> list[str]:
    if options.dispersion == "d3":
        return [
            "  Dispersion = DftD3 {",
            "    Damping = BeckeJohnson {",
            "      a1 = 0.5719",
            "      a2 = 3.6017",
            "    }",
            "    s6 = 1.0",
            "    s8 = 0.5883",
            "  }",
        ]
    if options.dispersion == "lj":
        return [
            "  Dispersion = LennardJones {",
            "    Parameters = UFFParameters {}",
            "  }",
        ]
    return []


# ======================================================================
#  WHAT A RUN OF DFTB+'S OWN ASKS FOR
# ======================================================================
#
# Each of these is the block it writes and nothing more.  Checked
# against DFTB+ 24.1 on silicon and carbon dioxide before a test was
# written: the relaxation is the *legacy* ``LBFGS`` driver because
# ``GeometryOptimization`` at parser version 14 refuses ``Pressure``,
# which a lattice relaxation cannot do without.


@dataclass(frozen=True)
class KLines:
    """A path through the Brillouin zone, as DFTB+ reads one.

    ``segments`` is ``(count, (k1, k2, k3))`` per line, in fractions of
    the reciprocal lattice vectors: the first is the start point with a
    count of one, and each after it is that many points ending at its
    k.  ``labels`` names each segment's end point, for the plot.
    """

    segments: tuple = ()
    labels: tuple = ()

    @property
    def n_points(self) -> int:
        return sum(int(count) for count, _k in self.segments)

    def lines(self) -> list[str]:
        out = ["  KPointsAndWeights = Klines {"]
        for count, k in self.segments:
            out.append(f"    {int(count)} " + " ".join(
                f"{float(v):.8f}" for v in k))
        out.append("  }")
        return out


@dataclass(frozen=True)
class Analysis:
    """The ``Analysis`` block.

    ``regions`` is one projected density of states per element, by
    symbol, written as ``dos_<symbol>`` -- or, shell resolved, as one
    file per shell.
    """

    forces: bool = True
    mulliken: bool = False
    regions: tuple = ()
    shell_resolved: bool = False
    eigenvectors: bool = False

    def lines(self) -> list[str]:
        out = ["Analysis {", f"  {forces_keyword()} = {_yes(self.forces)}"]
        if self.mulliken:
            out.append("  MullikenAnalysis = Yes")
        if self.eigenvectors:
            out.append("  WriteEigenvectors = Yes")
        if self.regions:
            out.append("  ProjectStates {")
            for symbol in self.regions:
                out += ["    Region {",
                        f"      Atoms = {symbol}",
                        f"      ShellResolved = "
                        f"{_yes(self.shell_resolved)}",
                        f'      Label = "{region_label(symbol)}"',
                        "    }"]
            out.append("  }")
        out.append("}")
        return out


def region_label(symbol: str) -> str:
    return f"dos_{symbol}"


@dataclass(frozen=True)
class Relax:
    """DFTB+'s own relaxation: atoms, and the cell when asked."""

    lattice: bool = False
    pressure: float = 0.0               # Pa
    moved: tuple | None = None          # 1-based atoms; None is all
    max_force: float = 1e-4             # Hartree/Bohr
    max_steps: int = 200
    optimiser: str = "lbfgs"            # or "cg"

    def lines(self) -> list[str]:
        name = "ConjugateGradient" if self.optimiser == "cg" else "LBFGS"
        out = [f"Driver = {name} {{",
               f"  MovedAtoms = {moved_atoms(self.moved)}",
               f"  MaxForceComponent = {self.max_force:g}",
               f"  MaxSteps = {int(self.max_steps)}",
               '  OutputPrefix = "geo_end"']
        if self.lattice:
            out += ["  LatticeOpt = Yes",
                    f"  Pressure [Pa] = {float(self.pressure):g}"]
        out.append("}")
        return out


#: Thermostats, as the dialog offers them.
THERMOSTATS = (("none", "None (constant energy)"),
               ("berendsen", "Berendsen"),
               ("nose-hoover", "Nose-Hoover"))


@dataclass(frozen=True)
class Dynamics:
    """Velocity Verlet molecular dynamics."""

    steps: int = 100
    time_step: float = 1.0              # fs
    temperature: float = 300.0          # K
    thermostat: str = "nose-hoover"
    #: Berendsen's coupling strength, or Nose-Hoover's in cm^-1.
    coupling: float = 3200.0
    write_every: int = 10
    moved: tuple | None = None

    def lines(self) -> list[str]:
        out = ["Driver = VelocityVerlet {",
               f"  MovedAtoms = {moved_atoms(self.moved)}",
               f"  Steps = {int(self.steps)}",
               f"  TimeStep [fs] = {float(self.time_step):g}",
               f"  MDRestartFrequency = {max(1, int(self.write_every))}",
               '  OutputPrefix = "geo_end"']
        if self.thermostat == "berendsen":
            out += ["  Thermostat = Berendsen {",
                    f"    Temperature [K] = {self.temperature:g}",
                    "    CouplingStrength = "
                    f"{min(max(self.coupling, 1e-6), 1.0):g}",
                    "  }"]
        elif self.thermostat == "nose-hoover":
            out += ["  Thermostat = NoseHoover {",
                    f"    Temperature [K] = {self.temperature:g}",
                    f"    CouplingStrength [cm^-1] = {self.coupling:g}",
                    "  }"]
        else:
            out += ["  Thermostat = None {",
                    f"    InitialTemperature [K] = {self.temperature:g}",
                    "  }"]
        out.append("}")
        return out


@dataclass(frozen=True)
class SecondDerivatives:
    """The Hessian by finite differences: 6N evaluations."""

    delta: float = 1e-4                 # Bohr
    moved: tuple | None = None

    def lines(self) -> list[str]:
        return ["Driver = SecondDerivatives {",
                f"  Atoms = {moved_atoms(self.moved)}",
                f"  Delta = {self.delta:g}",
                "}"]


def moved_atoms(atoms) -> str:
    """DFTB+'s atom list: ``1:-1`` for all, else ranges like
    ``1:4 7 9:12`` -- one-based, which is the whole difficulty."""
    if atoms is None:
        return "1:-1"
    chosen = sorted({int(a) for a in atoms})
    if not chosen:
        raise ValueError("no atom is free to move")
    runs = [[chosen[0], chosen[0]]]
    for atom in chosen[1:]:
        if atom == runs[-1][1] + 1:
            runs[-1][1] = atom
        else:
            runs.append([atom, atom])
    return " ".join(str(a) if a == b else f"{a}:{b}" for a, b in runs)


def forces_keyword(version: int = PARSER_VERSION) -> str:
    """What ``Analysis`` calls "print the forces" at this version."""
    return ("PrintForces" if version >= FORCES_RENAMED_AT
            else "CalculateForces")


def _yes(value) -> str:
    return "Yes" if value else "No"


# ======================================================================
#  A K-POINT MESH FROM THE CELL
# ======================================================================

#: The sampling density, in reciprocal Angstrom.  The usual rule of
#: thumb: a cell twice as long needs half as many k-points along that
#: direction, and the product of the two is what stays fixed.
DEFAULT_SPACING = 0.25


def mesh_for(lattice, spacing: float = DEFAULT_SPACING) -> tuple:
    """A k-point mesh from the reciprocal cell.

    A default that is wrong in the safe direction: it errs towards
    more k-points on a small cell, where they are cheap, and reaches
    one -- the Gamma point alone -- on a cell big enough that the
    Brillouin zone is a point, which is nearly every framework this
    application is used on.

    **From the reciprocal vectors' lengths, not the real ones'.**  They
    agree for a rectangular cell and nowhere else: a sheared cell's
    reciprocal vector is longer than 2 pi over its edge, by one over the
    sine of the angle, and a mesh counted from the edges under-samples
    exactly the direction the shear shortened.
    """
    import numpy as np
    matrix = np.asarray(lattice.matrix, dtype=float)
    spacing = max(float(spacing), 1e-6)
    if abs(np.linalg.det(matrix)) < 1e-12:
        return (1, 1, 1)
    reciprocal = 2 * np.pi * np.linalg.inv(matrix).T
    return tuple(max(1, int(round(length / spacing)))
                 for length in np.linalg.norm(reciprocal, axis=1))
