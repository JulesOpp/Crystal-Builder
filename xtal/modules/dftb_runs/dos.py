"""
xtal.modules.dftb_runs.dos
==========================
The density of states, projected onto each element.

One SCC run on a mesh denser than the one charges need -- a density of
states is an integral over the zone and a coarse mesh is a comb of
spikes however it is broadened -- with a ``ProjectStates`` region per
element, shell-resolved when asked.  DFTB+ writes each state's share of
each region; it does **not** broaden, which is dptools' job and here
is ours (:func:`xtal.ff.dftb.outputs.broaden`, a Gaussian of the width
the dialog gives).

Counted per cell and with both spins: an unpolarised run's states each
hold two electrons, so the curve integrates to the number of electrons
up to the Fermi level, which is the check anybody reading one makes.
"""

from __future__ import annotations

import re

import numpy as np

from xtal.ff.dftb import hsd, outputs
from xtal.modules.dftb_runs import common
from xtal.modules.job import JobResult
from xtal.modules.report import Dos, Report, Row, Table

#: Shell index to letter, in the order DFTB+ numbers a species' shells
#: -- which is ascending angular momentum for every set this reads.
SHELLS = "spdf"

#: Points per eV of the broadened curve.
POINTS_PER_EV = 50


@common.guarded
def density_of_states(job) -> JobResult:
    structure = job.structure
    options = common.options_of(job)
    common.refuse(structure, options)
    spacing = float(job.param("spacing", 0.1))
    sigma = float(job.param("sigma", 0.1))
    shells = bool(job.param("shells", False))
    symbols = sorted(set(common.symbols_of(structure)))
    mesh = common.mesh(structure, options, spacing)

    with common.folder(job) as directory:
        job.say(f"projecting the states on a "
                f"{'x'.join(str(n) for n in mesh)} mesh")
        common.invoke(job, directory, structure, hsd.hsd_string(
            symbols, options, k_points=mesh,
            analysis=hsd.Analysis(forces=False, regions=tuple(symbols),
                                  shell_resolved=shells)))
        fermi = outputs.fermi_level(common.read(directory,
                                                "detailed.out")) or 0.0
        block = projected(directory, symbols, fermi, sigma, shells)
        (directory / "dos.dat").write_text(block.as_dat())

    rows = [Row.number("Fermi level", fermi, "eV"),
            Row("k-point mesh", "x".join(str(n) for n in mesh)),
            Row.number("Broadening", sigma, "eV")]
    return JobResult(
        message=f"density of states on a "
                f"{'x'.join(str(n) for n in mesh)} mesh",
        report=Report(title="DFTB+ density of states",
                      blocks=(Table("Summary", tuple(rows)), block)))


def projected(directory, symbols, fermi: float, sigma: float,
              shells: bool = False) -> Dos:
    """Read every region's file in ``directory`` and broaden it.

    Also what the band structure calls on its mesh run, which is how a
    band structure gets its density of states beside it without a
    third invocation.
    """
    states = []
    for symbol in symbols:
        label = hsd.region_label(symbol)
        if shells:
            files = sorted(directory.glob(f"{label}.*.out"),
                           key=lambda p: int(p.suffixes[-2][1:]))
            for path in files:
                shell = int(re.search(r"\.(\d+)\.out$", path.name)[1])
                name = SHELLS[shell - 1] if shell <= len(SHELLS) \
                    else str(shell)
                states.append((f"{symbol} {name}",
                               *outputs.read_dos(path.read_text())))
        else:
            path = directory / f"{label}.out"
            states.append((symbol, *outputs.read_dos(
                common.read(directory, path.name))))
    if not states:
        raise common.RunFailed(JobResult.failure(
            "DFTB+ finished without writing a projected density of "
            "states"))
    everything = np.concatenate([e for _l, e, _w in states])
    low = float(everything.min() - fermi) - 5 * sigma
    high = float(everything.max() - fermi) + 5 * sigma
    grid = np.linspace(low, high,
                       max(200, int((high - low) * POINTS_PER_EV)))
    partial = tuple(
        (label, 2.0 * outputs.broaden(energies - fermi, weights, grid,
                                      sigma))
        for label, energies, weights in states)
    total = np.sum([y for _label, y in partial], axis=0)
    return Dos(title="Density of states", energies=grid, total=total,
               partial=partial, fermi=fermi, sigma=sigma,
               note="States per eV per cell, both spins, Gaussian "
                    f"broadening of {sigma:g} eV.")
