"""
xtal.modules.dftb_runs.electronic
=================================
Where the electrons are: Mulliken charges on the atoms, and one orbital
as a pair of lobes.

**Charges** are one SCC run with ``MullikenAnalysis``, read per atom of
the cell.  They come back twice: as a table per site -- an orbit's
atoms carry one charge, and when they do not the spread is shown
beside it, because that is a run whose SCC broke the symmetry -- and as
an overlay that colours every atom by its charge, blue to white to red.
The overlay lives on the document the way a pore network does; see
:mod:`xtal.analysis.overlays`.

**An orbital** is two programs.  DFTB+ writes its eigenvectors and the
detailed XML ``waveplot`` reads; ``waveplot`` puts one state on a grid
over the unit cell as a cube; the cube is marched at plus and minus the
isovalue.  ``waveplot`` needs the parameter set's ``wfc.*.hsd`` -- the
radial parts of the basis, which Slater-Koster files do not carry --
and a set without one (the bundled PTBP is one) is refused by name
before anything runs.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np

from xtal.analysis import overlays
from xtal.core import p1
from xtal.ff.dftb import hsd, outputs
from xtal.io.cube import read_cube
from xtal.modules.dftb_runs import common
from xtal.modules.job import JobResult
from xtal.modules.process import ExternalProcess, Program
from xtal.modules.report import Report, Row, Table

WAVEPLOT = Program(
    name="waveplot", label="waveplot", env_var="XTAL_WAVEPLOT",
    url="https://dftbplus.org (it ships with DFTB+)",
    setting="tools/waveplot")

WAVEPLOT_INPUT = "waveplot_in.hsd"

#: Grid points per Angstrom along each cell vector.
DEFAULT_RESOLUTION = 4.0


# ======================================================================
#  CHARGES
# ======================================================================

@common.guarded
def charges(job) -> JobResult:
    structure = job.structure
    options = common.options_of(job)
    common.refuse(structure, options)
    symbols = sorted(set(common.symbols_of(structure)))
    with common.folder(job) as directory:
        common.invoke(job, directory, structure, hsd.hsd_string(
            symbols, options, k_points=common.mesh(structure, options),
            analysis=hsd.Analysis(forces=False, mulliken=True)))
        values = outputs.mulliken_charges(
            common.read(directory, "detailed.out"))
        cell = p1.expand(structure)
        if values is None or len(values) != cell.n_atoms:
            return JobResult.failure(
                "DFTB+ finished without a Mulliken charge for every atom")
        (directory / "charges.dat").write_text(
            "# atom  element  site  charge(e)\n" + "".join(
                f"{k + 1:6d}  {cell.elements[k]:<3s}  "
                f"{structure.sites[int(cell.site_idx[k])].label:<8s}  "
                f"{values[k]: .5f}\n" for k in range(cell.n_atoms)),
            encoding="utf-8")

    table = _site_table(structure, cell, values)
    overlay = overlays.AtomCharges(np.asarray(values, float))
    return JobResult(
        message=f"Mulliken charges from {values.min():+.3f} to "
                f"{values.max():+.3f} e -- the atoms are coloured by "
                f"them",
        overlay=overlay,
        report=Report(title="DFTB+ Mulliken charges", blocks=(table,),
                      note="Positive is electrons lost.  The atoms are "
                           "coloured blue (negative) to red "
                           "(positive) until the structure changes."))


def _site_table(structure, cell, values) -> Table:
    rows = []
    for index, site in enumerate(structure.sites):
        atoms = cell.indices_of_site(index)
        if not len(atoms):
            continue
        here = values[atoms]
        spread = float(here.max() - here.min())
        rows.append(Row.of(
            site.label or f"{site.element}{index + 1}", site.element,
            len(atoms), f"{here.mean():+.4f}",
            f"{spread:.4f}" if spread > 1e-4 else "",
            note="" if spread <= 1e-4 else
            "The atoms of this orbit came back with different charges: "
            "the SCC broke the symmetry."))
    return Table("Charges per site", tuple(rows),
                 columns=("Site", "Element", "Atoms", "Charge (e)",
                          "Spread"))


# ======================================================================
#  ORBITALS
# ======================================================================

def basis_file(directory) -> Path | None:
    """The ``wfc.*.hsd`` of a parameter set, when it has one."""
    if directory is None:
        return None
    found = sorted(Path(directory).glob("wfc*.hsd"))
    return found[0] if found else None


def electrons(detailed: str) -> float | None:
    found = {spin: float(value) for spin, value in re.findall(
        r"Nr\. of electrons \((up|down)\):\s*(\S+)", detailed)}
    if "up" not in found:
        return None
    # An unpolarised run prints only "(up)", and it is the total.
    return found["up"] + found.get("down", 0.0)


def chosen_level(job, detailed: str) -> int:
    """The one-based state ``waveplot`` is asked for."""
    which = str(job.param("state", "homo"))
    if which == "index":
        return max(1, int(job.param("index", 1)))
    total = electrons(detailed)
    if total is None:
        raise common.RunFailed(JobResult.failure(
            "DFTB+ did not say how many electrons there are, so the "
            "highest occupied state is not known; choose it by index"))
    homo = max(1, math.ceil(total / 2.0 - 1e-6))
    offset = int(job.param("offset", 0))
    return max(1, homo - offset if which == "homo" else homo + 1 + offset)


@common.guarded
def orbital(job) -> JobResult:
    structure = job.structure
    options = common.options_of(job)
    common.refuse(structure, options)
    available = WAVEPLOT.availability()
    if not available:
        return JobResult.failure(available.reason)
    parameters = hsd.slater_koster_directory(options.parameter_directory)
    basis = basis_file(parameters)
    if basis is None:
        return JobResult.failure(
            f"{parameters.name if parameters else 'The parameter set'} "
            f"has no wfc.*.hsd, which waveplot needs: the radial parts "
            f"of the basis are not in the Slater-Koster files.  The 3ob "
            f"and mio downloads include one.")
    symbols = sorted(set(common.symbols_of(structure)))
    kpoint = int(job.param("kpoint", 1))
    spin = int(job.param("spin", 1))

    with common.folder(job) as directory:
        job.say("writing the eigenvectors")
        common.invoke(job, directory, structure, hsd.hsd_string(
            symbols, options, k_points=common.mesh(structure, options),
            analysis=hsd.Analysis(forces=False), detailed_xml=True,
            eigenvectors=True))
        detailed = common.read(directory, "detailed.out")
        level = chosen_level(job, detailed)
        points = _grid(structure.lattice,
                       float(job.param("resolution",
                                       DEFAULT_RESOLUTION)))
        (directory / WAVEPLOT_INPUT).write_text(waveplot_input(
            level, kpoint, spin, points, basis), encoding="utf-8")
        job.say(f"state {level} on a "
                f"{'x'.join(str(n) for n in points)} grid")
        process = ExternalProcess([WAVEPLOT.name], cwd=directory,
                                  log=job.log)
        result = process.run(cancel=job.cancel, program=WAVEPLOT)
        if result.cancelled:
            return JobResult.stopped("waveplot was stopped")
        if not result.ok:
            return JobResult.failure(
                f"waveplot exited with status {result.returncode}",
                detail=result.detail())
        name = f"wp-{spin}-{kpoint}-{level}-real.cube"
        if not (directory / name).is_file():
            return JobResult.failure(f"waveplot did not write {name}")
        cube = read_cube(directory / name)
        energy = _energy(directory, kpoint, spin, level)

    isovalue = float(job.param("isovalue", 0.02))
    label = f"state {level}" + (f", {energy:.3f} eV" if energy is not None
                                else "")
    surface = overlays.orbital_surface(cube, structure.lattice, isovalue,
                                       label)
    rows = [Row("State", str(level)),
            Row.number("Energy", energy, "eV") if energy is not None
            else Row("Energy", "?"),
            Row("k-point, spin", f"{kpoint}, {spin}"),
            Row.number("Isovalue", isovalue, "", decimals=4,
                       note="Red is where the orbital is positive, blue "
                            "where it is negative."),
            Row("Triangles", str(surface.n_faces))]
    return JobResult(
        message=f"orbital {label}, drawn at +/-{isovalue:g}",
        overlay=surface,
        report=Report(title="DFTB+ orbital",
                      blocks=(Table("Orbital", tuple(rows)),)))


def waveplot_input(level: int, kpoint: int, spin: int, points,
                   basis) -> str:
    """``waveplot_in.hsd`` for one state over the unit cell.  Checked
    against waveplot 0.3 from DFTB+ 24.1."""
    return "\n".join([
        "Options {",
        "  TotalChargeDensity = No",
        "  TotalChargeDifference = No",
        "  ChargeDensity = No",
        "  RealComponent = Yes",
        "  ImagComponent = No",
        f"  PlottedSpins = {spin}",
        f"  PlottedLevels = {level}",
        f"  PlottedKPoints = {kpoint}",
        "  PlottedRegion = UnitCell {}",
        f"  NrOfPoints = {' '.join(str(n) for n in points)}",
        "  NrOfCachedGrids = -1",
        "  Verbose = Yes",
        "}",
        'DetailedXml = "detailed.xml"',
        'EigenvecBin = "eigenvec.bin"',
        "Basis {",
        "  Resolution = 0.01",
        f'  <<+ "{basis}"',
        "}",
        ""])


def _grid(lattice, per_angstrom: float) -> tuple:
    lengths = np.linalg.norm(np.asarray(lattice.matrix, float), axis=1)
    return tuple(max(8, int(round(length * per_angstrom)))
                 for length in lengths)


def _energy(directory, kpoint, spin, level) -> float | None:
    path = directory / "band.out"
    if not path.is_file():
        return None
    bands = outputs.read_bands(path.read_text(
        encoding="utf-8", errors="replace"))
    try:
        return float(bands.energies[spin - 1, kpoint - 1, level - 1])
    except IndexError:
        return None
