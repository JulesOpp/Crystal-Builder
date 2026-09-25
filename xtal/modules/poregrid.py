"""
xtal.modules.poregrid
=====================
Surface area and pore volume off the distance grid: the "(faster)"
twins of Zeo++'s ``-sa`` and ``-vol``/``-volpo``.

**Why a second way to the same number.**  iRASPA answers these
instantly because it reads every one of them off a single grid, and
this application already builds that grid to draw the pore surface.
Zeo++'s ``-volpo`` took 68-108 s on every sample here; the grid gives
MFU-4l's in about 1.5 s, grid and all.  Zeo++ stays beside it, because
the grid has a resolution and Zeo++'s Voronoi decomposition does not:
a window within half a grid step of the probe is flagged
(:attr:`xtal.analysis.voids.Voids.borderline`) and the report says
Zeo++'s pore diameters are how to settle it.

**The same report, so the two can be read side by side.**  The records
are :class:`~xtal.analysis.porosity.SurfaceArea` and
:class:`~xtal.analysis.porosity.Volume` and the tables are
:mod:`xtal.modules.zeopp`'s, with a note saying how the numbers were
got.  Measured against Zeo++ on the samples: surface area within 1 %,
AV within 0.0035 of the cell where the grid resolves the windows, and
POAV *above* Zeo++'s by up to 0.026 -- which is Zeo++ falling short of
the union of probe spheres, not this overshooting it; see
:func:`xtal.analysis.voids.volume`.

**A radii file is read, not refused.**  Zeo++ reads it for its own
entries; the grid is ours, so it reads it too, and an element the file
does not name is refused by name rather than guessed.

Nothing is launched and nothing needs Zeo++ installed, which is why
these entries stay available when the Zeo++ ones are greyed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from xtal.analysis import grid as grids
from xtal.analysis import porosity, voids
from xtal.modules import zeopp
from xtal.modules.job import JobResult
from xtal.modules.report import Row


def surface_area(job) -> JobResult:
    """The accessible and non-accessible surface, off the grid."""
    setup = _prepare(job)
    samples = int(job.param("samples", 1000))
    job.say(f"surface area to {setup.gas}, {setup.said}")
    found = voids.surface_area(job.structure, setup.split,
                               setup.radius_of, samples=samples)
    how = (f"{samples} points per atom on the spheres; which of them a "
           f"probe of {setup.probe:.2f} A reaches is decided on a "
           f"{setup.spacing:g} A grid.")
    report = zeopp._area_report(found, setup.gas, setup.probe, samples,
                                setup.said, how=how,
                                first=_warning(setup))
    return zeopp._answer(job, f"{found.summary()} to {setup.gas}",
                         report, ())


def volume(job) -> JobResult:
    """The accessible (or probe-occupiable) volume, off the grid."""
    setup = _prepare(job)
    occupiable = bool(job.param("occupiable", True))
    job.say(f"accessible volume to {setup.gas}, {setup.said}")
    found = voids.volume(job.structure, setup.field, setup.split,
                         occupiable=occupiable)
    how = (f"The fraction of a {setup.spacing:g} A grid at a probe "
           f"radius of {setup.probe:.2f} A.")
    if occupiable:
        how += ("  This reads up to 0.03 of the cell above Zeo++'s "
                "-volpo: probe spheres centred on real probe positions "
                "cover at least this much, so the shortfall is Zeo++'s.")
    job.check()
    overlay = (zeopp.channel_overlay(job, setup.field, setup.split)
               if job.param("draw", True) else None)
    report = zeopp._volume_report(found, setup.gas, setup.probe, 0,
                                  occupiable, setup.said, how=how,
                                  first=_warning(setup))
    return zeopp._answer(job, f"{found.summary()} to {setup.gas}",
                         report, (), overlay=overlay)


@dataclass(frozen=True)
class _Setup:
    """What both entries start from: the grid, split, at the probe."""

    radius_of: Callable[[str], float]
    said: str
    probe: float
    gas: str
    spacing: float
    field: np.ndarray
    split: voids.Voids


def _prepare(job) -> _Setup:
    refusal = porosity.refuse(job.structure)
    if refusal:
        raise ValueError(refusal)
    radius_of, said = _radii(job)
    probe, _channel, gas = zeopp._probes_of(job)
    spacing = float(job.param("spacing", grids.DEFAULT_SPACING))
    field = grids.distance_grid(job.structure, radius_of, spacing=spacing)
    job.check()
    split = voids.classify(job.structure, field, radius_of, probe)
    job.check()
    job.note(f"{split.summary()} on a "
             f"{'x'.join(str(n) for n in field.shape)} grid"
             + (", borderline" if split.borderline else ""))
    return _Setup(radius_of=radius_of, said=said, probe=probe, gas=gas,
                  spacing=spacing, field=field, split=split)


def _warning(setup) -> tuple:
    if not setup.split.borderline:
        return ()
    return (Row("Resolution", "borderline", "",
                f"a window is within half a grid step "
                f"({setup.spacing / 2:g} A) of the probe's size, so "
                f"whether it is open is a matter of the grid.  Pore "
                f"diameters (Zeo++) settles it exactly."),)


def _radii(job):
    """``(radius_of, the sentence that says which table)``."""
    given = str(job.param("radii_file", "") or "").strip()
    if not given:
        radius_of, _why = zeopp._radius_function(job)
        source = str(job.param("radii", "builtin"))
        return radius_of, {
            "builtin": "radii from Zeo++'s own table",
            "vdw": "radii from this application's van der Waals table",
            "covalent": "radii from this application's covalent table",
        }.get(source, f"radii: {source}")

    path = Path(given).expanduser()
    if not path.is_file():
        raise ValueError(
            f"the radii file {path} is not there, and every number "
            f"this run returns depends on it")
    table = read_radii(path.read_text(encoding="utf-8", errors="replace"))
    missing = sorted({site.element for site in job.structure.sites}
                     - set(table))
    if missing:
        raise ValueError(
            f"{path.name} gives no radius for {', '.join(missing)}, and "
            f"guessing one would make this a different crystal")
    return table.__getitem__, f"radii from {path.name}"


def read_radii(text: str) -> dict:
    """A two-column radii table -- element, radius in A -- as Zeo++
    reads one: blank lines and ``#`` comments skipped."""
    table = {}
    for number, line in enumerate(text.splitlines(), 1):
        words = line.split("#", 1)[0].split()
        if not words:
            continue
        try:
            table[words[0]] = float(words[1])
        except (IndexError, ValueError):
            raise ValueError(
                f"line {number} of the radii file is not 'element "
                f"radius': {line.strip()!r}") from None
    return table
