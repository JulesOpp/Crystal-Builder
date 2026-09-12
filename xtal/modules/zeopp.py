"""
xtal.modules.zeopp
==================
Zeo++, as a registry entry.

Four entries, which are the four questions asked of a porous crystal:
how big are the pores (``-res`` and ``-chan``), how much surface does
a gas molecule see (``-sa``), how much room is there for it
(``-vol``), and what is the spread of pore sizes (``-psd``).
Everything about launching, streaming, cancelling and recording is
:mod:`xtal.modules.process` and :mod:`xtal.modules.record`, written
once in Phase D; what is here is only what is true of Zeo++ in
particular.

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
    url="https://www.zeoplusplus.org/", setting="tools/zeopp")

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


def _argv(job, directory: Path, radii: Path | None,
          commands) -> list:
    """One argv, from a list of command groups.

    **Several commands in one invocation, deliberately.**  Zeo++ reads
    the structure and builds the Voronoi decomposition once and then
    runs every command over it, and that decomposition is the whole
    cost of a run -- ``-res -chan -visVoro`` together take a second on
    MFU-4l where the same structure with ``-ha`` takes minutes.  So a
    picture and the numbers beside it come out of one run, which is
    also what makes it impossible for them to disagree about the
    radii.
    """
    found = binary()
    if found is None:
        raise MissingProgram(PROGRAM.title, searched=(PROGRAM.name,),
                             url=PROGRAM.url)
    argv = [str(found)]
    if job.param("high_accuracy", True):
        argv.append("-ha")
    if radii is not None:
        argv += ["-r", str(radii)]
    for command in commands:
        argv += [str(t) for t in command]
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


#: What ``-visVoro`` writes.  It is the one flag in this module whose
#: output name is not ours to choose: it takes no filename and names
#: six files after the *input* stem, so these follow INPUT_NAME.
VORO_NAMES = (f"{Path(INPUT_NAME).stem}_voro_accessible.xyz",
              f"{Path(INPUT_NAME).stem}_voro_accessible.vtk")


def _accessible_surface(job, probe: float):
    """The boundary of the volume this run just measured.

    **Computed here rather than read from Zeo++**, because Zeo++ 0.3
    cannot supply it: ``-gridGAI`` aborts on MFU-4l and ``-gridG`` ran
    for six minutes on the same file without writing anything.  See
    :mod:`xtal.analysis.grid`.

    Which makes the radii the thing to get right, and they are: the
    grid is built with Zeo++'s own table when that is what the run
    used, and with whichever of ours was chosen otherwise, so the
    drawn surface and the quoted volume are one measurement.  A run
    given a radii *file* is the one case that cannot be matched, and
    it says so rather than drawing a surface off somebody else's
    table.

    A surface that could not be built is not a failed run -- the
    volume is already read and correct.
    """
    from xtal.analysis import grid as grids
    from xtal.analysis import isosurface as iso

    radius_of, why = _radius_function(job)
    if radius_of is None:
        job.note(f"no surface drawn: {why}")
        return None
    spacing = float(job.param("spacing", grids.DEFAULT_SPACING))
    field = grids.distance_grid(job.structure, radius_of,
                                spacing=spacing)
    points, faces = iso.isosurface(field, job.structure.lattice, probe)
    if not len(faces):
        job.note("nothing to draw: no point in the cell is further "
                 "than the probe radius from an atom")
        return None
    network = porosity.PoreNetwork(surface_points=points,
                                   surface_faces=faces,
                                   probe=float(probe))
    job.note(f"{network.summary()}, on a "
             f"{'x'.join(str(n) for n in field.shape)} grid")
    return network


def _radius_function(job):
    """``(radius_of, why not)`` for the grid the surface is marched on.

    The same choice the run was given, so that the picture and the
    number cannot be drawn from different tables -- which is the
    disagreement the whole module is written to avoid.
    """
    if str(job.param("radii_file", "") or "").strip():
        return None, ("this run used a radii file of its own, and a "
                      "surface drawn from a different table would "
                      "not be the volume above")
    source = str(job.param("radii", "builtin"))
    if source == "builtin":
        return porosity.zeo_radius, ""

    from xtal.core import elements
    if source == "vdw":
        return elements.vdw_radius, ""
    return elements.covalent_radius, ""


def _read_network(job, directory: Path, channels, probe: float):
    """The accessible pore network, as something the viewport can draw.

    Only the *accessible* half is read.  ``-visVoro`` also writes the
    whole Voronoi diagram and the non-accessible pockets, and neither
    is what the question was: a node a probe cannot reach is not a
    pore, and drawing the full diagram over a framework is a picture
    of the algorithm rather than of the crystal.

    A run that could not be drawn is not a run that failed.  The three
    diameters are already read and correct, and refusing the whole
    answer because the drawing is missing would be the tail wagging
    the dog -- so this says so in the log and hands back ``None``.
    """
    nodes, edges = (directory / n for n in VORO_NAMES)
    if not nodes.is_file():
        job.note(f"Zeo++ wrote no {nodes.name}, so there is nothing "
                 f"to draw -- the numbers above are unaffected")
        return None
    lattice = job.structure.lattice
    frac, radii = porosity.parse_voro_nodes(nodes.read_text(), lattice)
    # The skeleton is optional in a way the nodes are not: without it
    # the largest pore is still drawn where it sits, which is most of
    # the answer.
    segments = {}
    if edges.is_file():
        starts, ends = porosity.parse_voro_edges(edges.read_text(),
                                                 lattice)
        segments = {"edge_starts": starts, "edge_ends": ends}
    network = porosity.PoreNetwork(
        nodes=frac, radii=radii, probe=float(probe),
        channels=tuple(channels), **segments)
    job.note(network.summary())
    return network


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


def _answer(job, message: str, report, artifacts,
            overlay=None) -> JobResult:
    """One result, with the report also written into the log.

    The log is what is left after the window has been closed, and a
    run folder holding Zeo++'s raw output and no statement of what it
    came to is a run somebody has to redo to read.
    """
    job.note("")
    job.note(report.as_text())
    return JobResult(message=message, report=report,
                     artifacts=artifacts, overlay=overlay)


# ======================================================================
#  THE THREE ENTRIES
# ======================================================================

def pore_diameters(job) -> JobResult:
    """``-res``: the largest included and free spheres, and ``-chan``:
    the channels they run through.

    ``-chan`` is run every time and is not a choice.  The
    decomposition is already paid for by ``-res``, and channel
    dimensionality -- whether a probe can cross the crystal in one
    direction, in a plane, or in any -- is a number every porous
    materials paper reports and the one no other Zeo++ output carries.
    """
    directory, holder = _prepare(job)
    try:
        _write_input(job, directory)
        radii, said = _write_radii(job, directory)
        _probe_radius, reach, gas = _probes_of(job)
        job.say(f"Zeo++: pore diameters and channels to {gas}, {said}")
        output, chan = "diameters.res", "channels.chan"
        drawing = bool(job.param("draw", True))
        commands = [["-res", output], ["-chan", reach, chan]]
        if drawing:
            commands.append(["-visVoro", reach])
        result = _run(job, directory,
                      _argv(job, directory, radii, commands))
        stopped = _failed(result)
        if stopped is not None:
            return stopped
        found = porosity.parse_res(
            _read(directory / output, "diameter"))
        channels = porosity.parse_chan(
            _read(directory / chan, "channel"))
        network = (_read_network(job, directory, channels, reach)
                   if drawing else None)
        return _answer(
            job,
            f"{found.summary()}; "
            f"{porosity.dimensionality(channels)}",
            _diameter_report(found, channels, gas, said),
            _keep(directory, job, output, chan, *VORO_NAMES,
                  INPUT_NAME),
            overlay=network)
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
            [["-sa", channel, probe, samples, output]]))
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


def accessible_volume(job) -> JobResult:
    """``-vol``: the volume a probe of that size can occupy.

    ``-volpo`` is the same measurement asked a different way, and it
    is a checkbox rather than a fourth entry because the difference is
    one word: ``-vol`` reports the volume the probe's *centre* can
    reach, which is what a simulation samples over; ``-volpo`` reports
    the volume it *occupies*, which is the pore volume a paper quotes
    and is always the larger of the two.  Quoting one for the other is
    the mistake this parameter exists to make impossible, so the row
    says which was measured.
    """
    directory, holder = _prepare(job)
    try:
        _write_input(job, directory)
        radii, said = _write_radii(job, directory)
        probe, channel, gas = _probes_of(job)
        samples = int(job.param("samples", 50000))
        occupiable = bool(job.param("occupiable", True))
        flag = "-volpo" if occupiable else "-vol"
        job.say(f"Zeo++: accessible volume to {gas}, {said}")
        output = "volume.vol"
        result = _run(job, directory, _argv(
            job, directory, radii,
            [[flag, channel, probe, samples, output]]))
        stopped = _failed(result)
        if stopped is not None:
            return stopped
        found = porosity.Volume.parse(
            _read(directory / output, "volume"), probe)
        surface = (_accessible_surface(job, probe)
                   if job.param("draw", True) else None)
        return _answer(job, f"{found.summary()} to {gas}",
                       _volume_report(found, gas, probe, samples,
                                      occupiable, said),
                       _keep(directory, job, output, INPUT_NAME),
                       overlay=surface)
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
            [["-psd", channel, probe, samples, output]]))
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

def _diameter_report(found, channels, gas: str,
                     said: str) -> Report:
    """The three diameters, and what they run through.

    The diameters themselves do not depend on the probe -- ``-res``
    measures the crystal.  Which channels *count* does, so the probe
    is named on the rows it decides and nowhere else.
    """
    rows = [Row.number(label, value, "A", meaning, symbol)
            for label, value, symbol, meaning in found.rows()]
    rows += [
        Row("Channels", str(len(channels)), "",
            f"pore networks a {gas} probe can reach from outside"),
        Row("Dimensionality", porosity.dimensionality(channels), "",
            "whether that probe can cross the crystal along one "
            "axis, within a plane, or in any direction"),
    ]
    blocks = [Table(
        rows=tuple(rows),
        note="D_f is the one that decides what the framework will "
             "admit, and it is always the smallest of the three.  "
             "Where D_f sits is not something Zeo++ reports: it is "
             "the width of a bottleneck along a channel, and no "
             "output carries it.")]
    if len(channels) > 1:
        blocks.append(_channel_table(channels))
    return Report(title="Pore diameters and channels",
                  blocks=tuple(blocks), note=said)


def _channel_table(channels) -> Table:
    """One row per channel, when there is more than one.

    A single channel is already described by the rows above it, and a
    second table saying the same three numbers again would be noise.
    Several are not: a framework with a wide 1D channel and a narrow
    3D one is two different materials to a gas, and the maximum over
    them -- which is all the .res file reports -- describes neither.
    """
    return Table(
        title="Channels",
        columns=("Channel", "Runs", "D_i (A)", "D_f (A)",
                 "D_if (A)"),
        rows=tuple(
            Row.of(channel.index, channel.label(),
                   f"{channel.included:.3f}",
                   f"{channel.free:.3f}",
                   f"{channel.included_along_free:.3f}")
            for channel in channels))


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


def _volume_report(found, gas: str, probe: float, samples: int,
                   occupiable: bool, said: str) -> Report:
    measured = ("the volume the probe occupies -- the pore volume a "
                "paper quotes" if occupiable else
                "the volume the probe's centre can reach -- what a "
                "simulation samples over")
    # The symbol follows which was measured: POAV and AV are the two
    # Zeo++ spellings and a paper quoting one of them means that one.
    symbol = "POAV" if found.occupiable else "AV"
    rows = [
        Row.number("Accessible volume", found.accessible_per_gram,
                   "cm^3/g", measured, symbol, decimals=4),
        Row.number("Accessible fraction of the cell",
                   found.accessible_fraction * 100, "%", "", "",
                   decimals=2),
        Row.number("Accessible volume in the cell",
                   found.accessible_volume, "A^3", "", "", decimals=1),
        Row.number("Non-accessible volume",
                   found.inaccessible_per_gram, "cm^3/g",
                   "pockets a probe cannot reach from outside",
                   f"N{symbol}" if not found.occupiable else "PONAV",
                   decimals=4),
    ]
    if found.counted:
        # -volpo writes no counts at all, and a row saying "0
        # channels" over a framework with one is worse than no row.
        rows += [
            Row("Channels", str(found.channels), "",
                "connected to the outside"),
            Row("Pockets", str(found.pockets), "", "closed voids"),
        ]
    rows += [
        Row.number("Density", found.density, "g/cm^3", "", "",
                   decimals=4),
        Row.number("Cell volume", found.volume, "A^3", "", "",
                   decimals=1),
    ]
    return Report(
        title=f"Accessible volume to {gas}",
        blocks=(Table(rows=tuple(rows),
                      note=f"{samples} Monte Carlo samples across the "
                           f"cell, at a probe radius of "
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
        Action(name="diameters",
               label="Pore diameters and channels...",
               tip="The largest included and free spheres -- D_i, D_f "
                   "and D_if -- and the channels they run through",
               kind="diameters",
               params=(*_probe(porosity.DEFAULT_PROBE, 1.86,
                               "Which channels count as reachable.  "
                               "The three diameters do not depend on "
                               "it; the number of channels and their "
                               "dimensionality do."),
                       Param("draw", "Draw the pore network",
                             kind="bool", default=True,
                             help="Put the largest pore and the "
                                  "channels it belongs to into the "
                                  "3D view, as well as into the "
                                  "table.  Zeo++'s -visVoro, over "
                                  "the decomposition this run has "
                                  "already paid for."),
                       *_shared()),
               run=pore_diameters),
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
        Action(name="volume", label="Accessible volume...",
               tip="How much of the cell a gas molecule can occupy, "
                   "which is the pore volume a paper quotes",
               kind="volume",
               params=(*_probe(porosity.DEFAULT_PROBE, 1.86,
                               "Nitrogen is what a pore volume is "
                               "usually quoted to."),
                       Param("occupiable", "Probe-occupiable volume",
                             kind="bool", default=True,
                             help="Zeo++'s -volpo: the volume the "
                                  "probe occupies rather than the "
                                  "volume its centre can reach.  The "
                                  "larger of the two, and the one a "
                                  "paper means by pore volume."),
                       Param("samples", "Samples", kind="int",
                             default=50000, minimum=1000,
                             maximum=1000000,
                             help="Monte Carlo points across the "
                                  "whole cell.  50000 is what the "
                                  "published figures use."),
                       Param("draw", "Draw the accessible surface",
                             kind="bool", default=True,
                             help="Put the boundary of that volume "
                                  "into the 3D view: the surface a "
                                  "probe of this radius can push its "
                                  "centre up to.  Computed here and "
                                  "not by Zeo++, at the same probe "
                                  "and the same radii."),
                       Param("spacing", "Surface detail", kind="float",
                             default=0.5, minimum=0.2, maximum=2.0,
                             step=0.1, decimals=2, suffix=" A",
                             help="Grid spacing for the surface.  "
                                  "Smaller is finer and slower: 0.5 A "
                                  "is a second and 190 000 triangles "
                                  "on MFU-4l, 0.3 A is eight times "
                                  "that."),
                       *_shared()),
               run=accessible_volume),
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
