"""
xtal.modules.dftb_runs.bands
============================
A band structure: converged charges on a mesh, then eigenvalues along a
path.

Two invocations in one run folder, which is DFTB+'s own recipe.  The
charges are converged on a Monkhorst-Pack mesh first (``scc/``) --
charges converged on a path through the zone would be charges of a
crystal sampled along one line.  Then ``bands/`` reads them, takes one
SCC iteration so nothing is re-converged, and asks for the eigenvalues
at the path's k-points.  A non-SCC Hamiltonian has no charges to
converge and goes straight to the path.

The Fermi level is the mesh run's, for the same reason: a Fermi level
filled from states along a path is not the crystal's.  Energies are
reported relative to it.

``bands.dat`` and ``bands.csv`` are written into the run folder, so the
numbers outlive the panel; the zone picture is drawn by the panel and
saved beside them.
"""

from __future__ import annotations

import shutil

import numpy as np

from xtal.analysis import kpath
from xtal.ff.dftb import hsd, outputs
from xtal.modules.dftb_runs import common, dos
from xtal.modules.job import JobResult
from xtal.modules.report import Bands, Report, Row, Table, Zone


@common.guarded
def band_structure(job) -> JobResult:
    structure = job.structure
    options = common.options_of(job)
    common.refuse(structure, options)
    path = kpath.band_path(structure.lattice)
    text = str(job.param("path", "") or "").strip()
    if text:
        try:
            path = path.with_text(text)
        except ValueError as exc:
            return JobResult.failure(str(exc))
    lines = kpath.klines(path, structure.lattice,
                         float(job.param("density",
                                         kpath.DEFAULT_DENSITY)))
    symbols = sorted(set(common.symbols_of(structure)))
    scc = options.method != "non-scc"

    with common.folder(job) as directory:
        fermi, density = 0.0, None
        if scc:
            job.say("converging the charges on a mesh")
            mesh = common.mesh(structure, options)
            regions = tuple(symbols) if job.param("dos", True) else ()
            common.invoke(job, directory / "scc", structure,
                          hsd.hsd_string(symbols, options,
                                         k_points=mesh,
                                         analysis=hsd.Analysis(
                                             forces=False,
                                             regions=regions)))
            fermi = outputs.fermi_level(
                common.read(directory / "scc", "detailed.out")) or 0.0
            if regions:
                density = dos.projected(
                    directory / "scc", symbols, fermi,
                    float(job.param("sigma", 0.1)))
                (directory / "dos.dat").write_text(density.as_dat())
            (directory / "bands").mkdir(exist_ok=True)
            shutil.copy(directory / "scc" / "charges.bin",
                        directory / "bands" / "charges.bin")
        job.say(f"eigenvalues at {lines.n_points} k-points along "
                f"{path.text}")
        common.invoke(job, directory / "bands", structure,
                      hsd.hsd_string(symbols, options, k_points=lines,
                                     read_charges=scc,
                                     max_scc=1 if scc else None,
                                     analysis=hsd.Analysis(
                                         forces=False)))
        eigen = outputs.read_bands(
            common.read(directory / "bands", "band.out"))
        if not scc:
            fermi = _midgap(eigen)
        x, ticks = kpath.positions(lines, structure.lattice)
        block = Bands(
            title="Band structure", x=x,
            energies=eigen.energies - fermi, ticks=tuple(ticks),
            fermi=fermi, kpoints=_kpoints(lines),
            note="Energies relative to the Fermi level of the run on "
                 "the mesh.")
        (directory / "bands.dat").write_text(block.as_dat())
        (directory / "bands.csv").write_text(block.as_csv())

    gap = block.gap()
    rows = [Row.number("Fermi level", fermi, "eV"),
            Row.number("Band gap", gap[1] - gap[0], "eV") if gap
            else Row("Band gap", "none", "",
                     note="A band crosses the Fermi level."),
            Row("Path", path.text),
            Row("k-points", str(lines.n_points))]
    zone = Zone(title="Brillouin zone",
                lattice=np.asarray(structure.lattice.matrix, float),
                points=tuple(sorted(path.points.items())),
                runs=path.runs)
    message = (f"band structure along {path.text}: "
               + (f"gap {gap[1] - gap[0]:.3f} eV" if gap else "no gap"))
    return JobResult(message=message, report=Report(
        title="DFTB+ band structure",
        blocks=(Table("Summary", tuple(rows)), block)
        + ((density,) if density is not None else ()) + (zone,)))


def _kpoints(lines) -> np.ndarray:
    """Each sampled k in reciprocal fractions, in the order DFTB+
    visits them."""
    out, previous = [], None
    for count, k in lines.segments:
        k = np.array(k, dtype=float)
        if previous is None or count == 1:
            out.append(k)
        else:
            out.extend(previous + (k - previous) * (i + 1) / count
                       for i in range(count))
        previous = k
    return np.array(out)


def _midgap(eigen) -> float:
    """Where the Fermi level sits without an SCC run to say: between
    the highest occupied state and the lowest empty one."""
    occupied = eigen.energies[eigen.occupations > 1e-3]
    empty = eigen.energies[eigen.occupations <= 1e-3]
    if not len(occupied) or not len(empty):
        return 0.0
    return 0.5 * (float(occupied.max()) + float(empty.min()))
