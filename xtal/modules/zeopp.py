"""
xtal.modules.zeopp
==================
Zeo++, as a registry entry.

Three entries, which are the three questions asked of a porous
crystal: how big are the pores (``-res``), how much surface does a gas
molecule see (``-sa``), and what is the spread of pore sizes
(``-psd``).  Everything about launching, streaming, cancelling and
recording is :mod:`xtal.modules.process` and
:mod:`xtal.modules.record`, written once in Phase D; what is here is
only what is true of Zeo++ in particular.

Four things are, and each of them is a decision rather than a detail.

**The input is written in P1, by us.**  Zeo++ reads CIF, and its
reader is not this application's -- it has its own ideas about
symmetry operators, about occupancy and about what a label means, and
a disagreement between the two would show up as a porosity that does
not match the crystal on screen.  So the P1 expansion is written out as
CSSR (:mod:`xtal.io.cssr`) and Zeo++ is given a box of explicit atoms
with nothing left to interpret.

**The radii are the whole calculation.**  Every number Zeo++ returns is
a function of how big it thinks the atoms are, and its built-in table
is not the one every paper used.  So the table is a parameter with the
alternatives named, and whichever was used is written into the log and
into the result -- an area quoted without its radii and its probe is
not reproducible.

**A partially occupied site is refused, not averaged.**  Zeo++ cannot
express half an atom; handed one it returns a confident number for a
crystal that does not exist.  :func:`xtal.analysis.porosity.refuse` is
the check, and it runs before the run folder is opened.

**It works without a workspace.**  A run with nowhere to write still
answers -- into a temporary directory that goes away afterwards --
because the answer is a table on screen and not only a file on disk.
The status line says the files were not kept.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from xtal.analysis import porosity
from xtal.modules.job import JobResult
from xtal.modules.process import ExternalProcess, MissingProgram, Program
from xtal.modules.registry import MODULES, Action, Availability, Module, Param
from xtal.modules.report import Histogram, Report, Row, Table

#: The binary.  ``network`` is a very ordinary name for a program, so
#: the environment variable is offered first and the bundled copy is
#: the last resort rather than the first.
PROGRAM = Program(
    name="network", label="Zeo++", env_var="XTAL_ZEOPP",
    url="https://www.zeoplusplus.org/")

#: Where a copy that ships with the source tree would be.  Checked
#: after PATH, so a user who has installed Zeo++ properly gets theirs.
BUNDLED = ("resources", "zeo++-0.3", "network")

INPUT_NAME = "structure.cssr"
RADII_NAME = "radii.rad"

#: Radii tables, as the question a user is really being asked.  The
#: built-in one is Zeo++'s own and is the default because it is what
#: the numbers in the Zeo++ papers were computed with.
RADII_SOURCES = (
    ("builtin", "Zeo++'s own table (what its papers used)"),
    ("vdw", "Van der Waals radii (this application's table)"),
    ("covalent", "Covalent radii (this application's table)"),
)

#: Lines of Zeo++'s output that are worth a status bar.  It prints
#: tens of thousands of lines of voro++ housekeeping, all of which
#: belong in the log and none of which belong on a status line that
#: is meant to say what stage the run has reached.
_NOISE = ("vertex memory", "order 3 vertex", "va=(", "vb=(",
          "vc=(", "internal grid", "total domain volume",
          "total voronoi volume", "box dimensions", "volume check")


def bundled() -> Path | None:
    """The copy in ``resources/``, if this is a source checkout."""
    import xtal
    candidate = Path(xtal.__file__).resolve().parent.parent.joinpath(
        *BUNDLED)
    return candidate if candidate.is_file() else None


def binary() -> Path | None:
    """Where ``network`` is, or ``None``."""
    return PROGRAM.locate() or bundled()


def available() -> Availability:
    """The registry's answer, consulted every time the tree is built."""
    found = binary()
    if found is not None:
        return Availability(True, str(found))
    return PROGRAM.availability()


# ======================================================================
#  PARAMETERS
# ======================================================================

def _shared() -> tuple[Param, ...]:
    """The parameters every entry has, in the order they are read.

    Radii and accuracy are not per-question: they describe the model
    of the crystal, and a surface area computed with one table and a
    pore diameter computed with another cannot be quoted side by side.
    """
    return (
        Param("radii", "Atom radii", kind="choice",
              choices=RADII_SOURCES, default="builtin",
              help="Every number Zeo++ returns is a function of how "
                   "big it thinks the atoms are.  Whichever is chosen "
                   "is written into the log."),
        Param("radii_file", "Radii file", kind="path",
              help="Your own two-column table (element, radius in A), "
                   "which overrides the choice above when it is set"),
        Param("high_accuracy", "High accuracy", kind="bool",
              default=True,
              help="Zeo++'s -ha: add Voronoi vertices so that atoms "
                   "of different radii are treated properly.  Slower, "
                   "and what the documentation recommends."),
    )


def _probe(default_gas: str, default_radius: float,
           label: str) -> tuple[Param, ...]:
    return (
        Param("gas", "Probe", kind="choice",
              choices=[(k, v) for k, v, _r in porosity.PROBES],
              default=default_gas,
              help=f"{label}  A radius quoted without the probe it "
                   f"was measured with means nothing."),
        Param("probe_radius", "Probe radius", kind="float",
              default=default_radius, minimum=0.0, maximum=10.0,
              step=0.05, decimals=2, suffix=" A",
              help="Used only when the probe above is set to "
                   "'Use the radius below'"),
        Param("channel_radius", "Channel radius", kind="float",
              default=0.0, minimum=0.0, maximum=10.0, step=0.05,
              decimals=2, suffix=" A",
              help="Which channels count as reachable.  Zero means "
                   "'the same as the probe', which is what makes the "
                   "answer the one the probe would measure."),
    )


# ======================================================================
#  RUNNING ONE
# ======================================================================

def _prepare(job):
    """Write the input, and say where the run is happening.

    Returns ``(directory, cleanup)``.  A run with no workspace gets a
    temporary directory, because the answer is a table on screen and
    not only a file on disk -- and losing the files is better than
    refusing to answer.
    """
    refusal = porosity.refuse(job.structure)
    if refusal:
        raise ValueError(refusal)
    if job.folder is not None:
        return Path(job.folder.path), None
    holder = tempfile.TemporaryDirectory(prefix="zeopp-")
    job.note("no workspace open, so this run is happening in a "
             "temporary folder and its files will not be kept")
    return Path(holder.name), holder


def _write_input(job, directory: Path) -> Path:
    from xtal.io.cssr import write_cssr

    name = str(job.structure.meta.get("title", "") or "structure")
    path = write_cssr(job.structure, directory / INPUT_NAME, name=name)
    job.note(f"wrote {path.name}: {len(job.structure.sites)} sites "
             f"expanded to the whole cell")
    return path


def _write_radii(job, directory: Path) -> tuple[Path | None, str]:
    """The radii table, and the sentence that says which it was.

    ``None`` for Zeo++'s built-in table, which is the default and is
    what its own papers used -- passing ``-r`` with no file would also
    get it, and not passing the flag at all is the same thing said
    more plainly.
    """
    given = str(job.param("radii_file", "") or "").strip()
    if given:
        path = Path(given).expanduser()
        if not path.is_file():
            raise ValueError(
                f"the radii file {path} is not there, and every "
                f"number Zeo++ returns depends on it -- so this run "
                f"would silently be a different calculation")
        return path, f"radii from {path.name}"

    source = str(job.param("radii", "builtin"))
    if source == "builtin":
        return None, "radii from Zeo++'s own table"

    from xtal.core import elements

    radius = (elements.vdw_radius if source == "vdw"
              else elements.covalent_radius)
    symbols = sorted({site.element for site in job.structure.sites})
    path = directory / RADII_NAME
    path.write_text("".join(f"{s} {radius(s):.3f}\n" for s in symbols))
    kind = "van der Waals" if source == "vdw" else "covalent"
    return path, (f"radii from this application's {kind} table, "
                  f"written to {path.name}")


def _argv(job, directory: Path, radii: Path | None, tail) -> list:
    found = binary()
    if found is None:
        raise MissingProgram(PROGRAM.title, searched=(PROGRAM.name,),
                             url=PROGRAM.url)
    argv = [str(found)]
    if job.param("high_accuracy", True):
        argv.append("-ha")
    if radii is not None:
        argv += ["-r", str(radii)]
    argv += [str(t) for t in tail]
    argv.append(INPUT_NAME)
    return argv


def _run(job, directory: Path, argv) -> object:
    process = ExternalProcess(argv, cwd=directory, log=job.log,
                              on_line=_progress(job))
    return process.run(cancel=job.cancel, program=None)


def _progress(job):
    """Forward the lines worth reading and log all of them.

    The log already has every line -- ``ExternalProcess`` writes it --
    so this only decides what reaches the status bar.
    """
    if job.on_progress is None:
        return None

    def line(text: str) -> None:
        lowered = text.strip().lower()
        if lowered and not any(n in lowered for n in _NOISE):
            job.on_progress(text.strip()[:120])
    return line


def _probes_of(job) -> tuple[float, float, str]:
    """``(probe, channel, label)`` from the three probe parameters."""
    gas = str(job.param("gas", porosity.DEFAULT_PROBE))
    custom = float(job.param("probe_radius", 0.0) or 0.0)
    probe = porosity.probe_radius(gas, custom)
    if probe <= 0:
        raise ValueError(
            "a probe radius of zero measures nothing -- pick a gas, "
            "or set a radius of your own")
    channel = float(job.param("channel_radius", 0.0) or 0.0) or probe
    return probe, channel, porosity.probe_label(gas, custom)


def _failed(result) -> JobResult | None:
    if result.cancelled:
        return JobResult.stopped(result.message())
    if not result.ok:
        return JobResult.failure(result.message(),
                                 detail=result.detail())
    return None


def _read(path: Path, what: str) -> str:
    if not path.is_file():
        raise ValueError(
            f"Zeo++ finished without writing {path.name}, so there "
            f"is no {what} to read -- the log says why")
    return path.read_text()


def _keep(directory: Path, job, *names) -> tuple:
    """The artefacts, when there is a run folder to have kept them."""
    if job.folder is None:
        return ()
    return tuple(directory / n for n in names
                 if (directory / n).is_file())


def _answer(job, message: str, report, artifacts) -> JobResult:
    """One result, with the report also written into the log.

    The log is what is left after the window has been closed, and a
    run folder holding Zeo++'s raw output and no statement of what it
    came to is a run somebody has to redo to read.
    """
    job.note("")
    job.note(report.as_text())
    return JobResult(message=message, report=report,
                     artifacts=artifacts)


# ======================================================================
#  THE THREE ENTRIES
# ======================================================================

def pore_diameters(job) -> JobResult:
    """``-res``: the largest included and free spheres."""
    directory, holder = _prepare(job)
    try:
        _write_input(job, directory)
        radii, said = _write_radii(job, directory)
        job.say(f"Zeo++: pore diameters, {said}")
        output = "diameters.res"
        result = _run(job, directory,
                      _argv(job, directory, radii, ["-res", output]))
        stopped = _failed(result)
        if stopped is not None:
            return stopped
        found = porosity.parse_res(
            _read(directory / output, "diameter"))
        return _answer(job, found.summary(),
                       _diameter_report(found, said),
                       _keep(directory, job, output, INPUT_NAME))
    finally:
        if holder is not None:
            holder.cleanup()


def surface_area(job) -> JobResult:
    """``-sa``: the area a probe of that size can touch."""
    directory, holder = _prepare(job)
    try:
        _write_input(job, directory)
        radii, said = _write_radii(job, directory)
        probe, channel, gas = _probes_of(job)
        samples = int(job.param("samples", 2000))
        job.say(f"Zeo++: surface area to {gas}, {said}")
        output = "surface.sa"
        result = _run(job, directory, _argv(
            job, directory, radii,
            ["-sa", channel, probe, samples, output]))
        stopped = _failed(result)
        if stopped is not None:
            return stopped
        found = porosity.SurfaceArea.parse(
            _read(directory / output, "surface area"), probe)
        return _answer(job, f"{found.summary()} to {gas}",
                       _area_report(found, gas, probe, samples, said),
                       _keep(directory, job, output, INPUT_NAME))
    finally:
        if holder is not None:
            holder.cleanup()


def pore_size_distribution(job) -> JobResult:
    """``-psd``: how much of the pore space sits at each diameter."""
    directory, holder = _prepare(job)
    try:
        _write_input(job, directory)
        radii, said = _write_radii(job, directory)
        probe, channel, gas = _probes_of(job)
        samples = int(job.param("samples", 20000))
        job.say(f"Zeo++: pore size distribution, {samples} samples "
                f"to {gas}, {said}")
        output = "distribution.psd_histo"
        result = _run(job, directory, _argv(
            job, directory, radii,
            ["-psd", channel, probe, samples, output]))
        stopped = _failed(result)
        if stopped is not None:
            return stopped
        found = porosity.parse_psd(
            _read(directory / output, "distribution"), probe)
        return _answer(job, found.summary(),
                       _psd_report(found, gas, probe, said),
                       _keep(directory, job, output, INPUT_NAME))
    finally:
        if holder is not None:
            holder.cleanup()


# ======================================================================
#  WHAT COMES BACK
# ======================================================================

def _diameter_report(found, said: str) -> Report:
    return Report(
        title="Pore diameters",
        blocks=(Table(
            title="",
            rows=tuple(
                Row.number(label, value, "A", meaning, symbol)
                for label, value, symbol, meaning in found.rows()),
            note="D_f is the one that decides what the framework will "
                 "admit, and it is always the smallest of the three."),),
        note=said)


def _area_report(found, gas: str, probe: float, samples: int,
                 said: str) -> Report:
    rows = [
        Row.number("Accessible surface area",
                   found.accessible_per_gram, "m^2/g",
                   f"what a {gas} isotherm measures", "ASA",
                   decimals=1),
        Row.number("Accessible, per volume",
                   found.accessible_per_volume, "m^2/cm^3", "", "",
                   decimals=1),
        Row.number("Accessible, in the cell", found.accessible_area,
                   "A^2", "", "", decimals=1),
        Row.number("Non-accessible surface area",
                   found.inaccessible_per_gram, "m^2/g",
                   "pockets a probe cannot reach from outside -- a "
                   "framework whose area is mostly this will not "
                   "reproduce in an experiment", "NASA", decimals=1),
        Row("Channels", str(found.channels), "",
            "connected to the outside"),
        Row("Pockets", str(found.pockets), "", "closed voids"),
        Row.number("Density", found.density, "g/cm^3", "", "",
                   decimals=4),
        Row.number("Cell volume", found.volume, "A^3", "", "",
                   decimals=1),
    ]
    return Report(
        title=f"Surface area to {gas}",
        blocks=(Table(rows=tuple(rows),
                      note=f"{samples} Monte Carlo samples per "
                           f"atom, at a probe radius of "
                           f"{probe:.2f} A."),),
        note=said)


def _psd_report(found, gas: str, probe: float, said: str) -> Report:
    window = found.window()
    table = Table(rows=(
        Row.number("Peak pore diameter", found.mode(), "A",
                   "the bin the most sample points landed in", "",
                   decimals=2),
        Row.number("Mean pore diameter", found.mean(), "A", "", "",
                   decimals=2),
        Row.number("Accessible fraction of samples",
                   found.accessible_fraction * 100, "%",
                   f"{found.accessible_samples} of "
                   f"{found.total_samples} sample points were inside "
                   f"the pore space", "", decimals=1),
        Row.number("Bin size", found.bin_size, "A", "", "",
                   decimals=2),
    ), note=f"Sampled with {gas}.")
    histogram = Histogram(
        title="Pore size distribution",
        x=window.diameters + window.bin_size / 2,
        y=window.counts,
        x_label="pore diameter (A)",
        y_label="sample points",
        curve=window.derivative,
        curve_label="dV/dD",
        # A pore narrower than the probe is one the sampling could
        # never have found, so the rule says where the picture stops
        # being a measurement and starts being a blind spot.
        markers=((2 * probe, f"probe, {2 * probe:.2f} A across"),),
        note="The bars are where the sample points landed; the line "
             "is the derivative of the cumulative distribution, "
             "which is the distribution as a paper plots it.  Only "
             "the occupied range is drawn -- Zeo++ writes a thousand "
             "bins and nearly all of them are empty.")
    return Report(title=f"Pore size distribution to {gas}",
                  blocks=(table, histogram), note=said)


# ======================================================================
#  THE MODULE
# ======================================================================

ZEOPP = Module(
    name="zeopp",
    label="Zeo++",
    description="Pore diameters, accessible surface area and the pore "
                "size distribution of a periodic structure, by "
                "Voronoi decomposition.",
    order=30,
    check=available,
    provides=frozenset({"porosity", "table", "histogram"}),
    actions=(
        Action(name="diameters", label="Pore diameters...",
               tip="The largest included and free spheres -- D_i, D_f "
                   "and D_if",
               kind="diameters",
               params=_shared(), run=pore_diameters),
        Action(name="surface-area", label="Surface area...",
               tip="The area a gas molecule can touch, which is what "
                   "a BET measurement sees",
               kind="surface-area",
               params=(*_probe(porosity.DEFAULT_PROBE, 1.86,
                               "Nitrogen is what a BET surface area "
                               "is measured with."),
                       Param("samples", "Samples per atom", kind="int",
                             default=2000, minimum=100,
                             maximum=100000,
                             help="Monte Carlo points per atom.  More "
                                  "is slower and less noisy; 2000 is "
                                  "the usual choice."),
                       *_shared()),
               run=surface_area),
        Action(name="psd", label="Pore size distribution...",
               tip="How much of the pore space sits at each diameter, "
                   "as a histogram",
               kind="psd",
               params=(*_probe("custom", 1.2,
                               "A small probe resolves narrow pores; "
                               "a large one only sees what it fits "
                               "into, which is why this one defaults "
                               "to a radius rather than to a gas."),
                       Param("samples", "Samples", kind="int",
                             default=20000, minimum=1000,
                             maximum=1000000,
                             help="Monte Carlo points across the "
                                  "whole cell, and the one parameter "
                                  "that decides how long this takes: "
                                  "20000 is minutes on a framework "
                                  "and enough to see the shape; the "
                                  "published figures use 50000."),
                       *_shared()),
               run=pore_size_distribution),
    ),
)


def register(registry=MODULES) -> Module:
    return registry.register(ZEOPP)
