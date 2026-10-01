"""
xtal.modules.blender
====================
File > Export as STL: one unit cell, as a mesh a 3D printer can take;
and File > Render in Blender: the same cell in Julius's scene, saved as
``scene.blend`` and rendered to ``render.png``.

The work is Blender's, and ours is to hand it the right thing.  A
crystal has no edges, so the cell is cut out first -- faces and
corners included, and the bonds the document has rather than any a
reader might guess (:func:`xtal.core.cellcut.cut_cell`) -- and written
as a PDB with a CONECT record for every bond
(:mod:`xtal.io.pdb`).  Blender then runs ``pdb_to_printable_stl.py``
headless, through ``printable_stl.py`` beside it: the Atomic Blender
add-on imports balls and sticks, the instances are baked into one
mesh, and a voxel remesh welds it into a single watertight solid.

**The script is somebody else's, and ships unchanged** in
``xtal/modules/data/``.  It is excluded from this project's lint for
the reason the vendored PORMAKE is: it is a tool with its own
conventions and its own command line, and a copy reformatted to 79
columns is one that can no longer be compared with the one its author
keeps.  What this project needs of it that its author's command line
does not offer -- the importer told not to centre the PDB, which is
written already centred off the origin (:data:`OFF_CENTRE`) -- is
``printable_stl.py``, ours and linted, which loads it and replaces
that one function before running its ``main``.

**A run like any other module run**, which is what gives it a run
folder holding the PDB, the log and the STL, a Stop that reaches
Blender, and a greyed entry that says Blender was not found.  The STL
is then copied to where the user asked for it.

Two exit statuses mean something.  0 is a mesh.  2 is the script
saying it could not enable Atomic Blender, which it prints -- and its
own sentence, naming where the add-on lives in each Blender version,
is a better message than any we could write.  ``--python-exit-code``
makes a Python exception inside Blender a failure rather than the
exit status 0 Blender otherwise gives it.

**The render's script is ours** (``render_scene.py``), and linted.
Where its camera stands is ``render_framing.py`` beside it, loaded
here by path: Blender imports it from the same folder with a Python
that has no ``xtal``, and a frozen build ships the folder as data
rather than as a package, so a path is the one way both find it.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import shutil
import tempfile
from pathlib import Path

import numpy as np

from xtal.core import cellcut
from xtal.io.pdb import write_pdb
from xtal.modules.job import JobResult
from xtal.modules.process import ExternalProcess, Program
from xtal.modules.registry import MODULES, Action, Module, Param

PROGRAM = Program(
    name="blender", label="Blender", env_var="XTAL_BLENDER",
    url="https://www.blender.org/", setting="tools/blender",
    known=("/Applications/Blender.app/Contents/MacOS/Blender",))

DATA = Path(__file__).resolve().parent / "data"
VENDORED = DATA / "pdb_to_printable_stl.py"
SCRIPT = DATA / "printable_stl.py"
RENDER_SCRIPT = DATA / "render_scene.py"

INPUT_NAME = "structure.pdb"
OUTPUT_NAME = "structure.stl"
SCENE_NAME = "scene.blend"
IMAGE_NAME = "render.png"

#: Where both PDBs put the cut's mean, in Angstrom: near enough the
#: origin for the render's light at z = 25 to mean what it says, and
#: far enough off every symmetry line that no stick's line passes
#: through the origin, which Atomic Blender divides by zero on (see
#: ``render_scene.import_pdb`` and ``printable_stl.py``).  Three
#: decimals, as the PDB writes.
OFF_CENTRE = (0.013, 0.029, 0.047)


def _load_framing():
    spec = importlib.util.spec_from_file_location(
        "render_framing", DATA / "render_framing.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: The camera's arithmetic, the same file Blender runs.
framing = _load_framing()

#: The script's status for "Atomic Blender could not be enabled".
ADDON_MISSING = 2

#: What the scripts prefix every line they print with.
_PREFIX = "[mol2stl]"
_RENDER_PREFIX = "[render]"


def available():
    return PROGRAM.availability()


def _params() -> tuple[Param, ...]:
    """The script's own knobs, at the script's own defaults -- see its
    CONFIG block.  Only the ones that change what comes out of the
    printer; the rest are the script's business."""
    return (
        Param("output", "Save as", kind="path", default="",
              help="Where the STL goes.  A copy also stays in the run "
                   "folder, beside the PDB it was made from"),
        Param("bonded_partners", "Complete bonds across the cell faces",
              kind="bool", default=False,
              help="Bring in the atom at the far end of every bond "
                   "that leaves the cell, so a linker cut by a face "
                   "prints with both its ends"),
        Param("ball_scale", "Ball scale", kind="float", default=0.8,
              minimum=0.1, maximum=5.0, step=0.1, decimals=2,
              help="Atomic radii times this"),
        Param("h_scale", "Hydrogen scale", kind="float", default=2.0,
              minimum=0.1, maximum=10.0, step=0.1, decimals=2,
              help="Hydrogens again times this: at atomic radii they "
                   "are too small to print"),
        Param("stick_radius", "Stick radius", kind="float",
              default=0.4, minimum=0.05, maximum=3.0, step=0.05,
              decimals=2, suffix=" A"),
        Param("remesh", "Remesh into one solid", kind="bool",
              default=True,
              help="Weld the balls and sticks into one watertight "
                   "mesh.  Off leaves overlapping pieces, which most "
                   "slicers refuse"),
        Param("voxel_size", "Voxel size", kind="float", default=0.10,
              minimum=0.01, maximum=2.0, step=0.01, decimals=3,
              suffix=" A",
              help="The remesh grid.  Smaller keeps more detail and "
                   "costs memory as the cube of it"),
        Param("max_tris", "Triangle budget", kind="int",
              default=1000000, minimum=0, maximum=100000000,
              step=100000,
              help="The remesh is coarsened until the mesh fits.  0 "
                   "is no budget; a binary STL is about 50 bytes a "
                   "triangle"),
        Param("target_size", "Longest side", kind="float", default=0.0,
              minimum=0.0, maximum=10000.0, step=10.0, decimals=1,
              suffix=" mm",
              help="Scale the model so its longest side is this.  0 "
                   "leaves one Angstrom as one millimetre"),
    )


def arguments(job, pdb: Path, stl: Path) -> list[str]:
    """Blender's command line, the program itself left for
    :class:`ExternalProcess` to resolve."""
    argv = [PROGRAM.name, "--background", "--factory-startup",
            "--python-exit-code", "1", "--python", str(SCRIPT), "--",
            "--input", str(pdb), "--output", str(stl),
            "--ball-scale", _number(job.param("ball_scale", 0.8)),
            "--h-scale", _number(job.param("h_scale", 2.0)),
            "--stick-radius", _number(job.param("stick_radius", 0.4)),
            "--voxel-size", _number(job.param("voxel_size", 0.10)),
            "--max-tris", str(int(job.param("max_tris", 1000000))),
            "--target-size", _number(job.param("target_size", 0.0))]
    if not job.param("remesh", True):
        argv.append("--no-remesh")
    return argv


def export_stl(job) -> JobResult:
    output = str(job.param("output", "") or "").strip()
    if not output:
        return JobResult.failure("choose where the STL should be saved")
    destination = Path(output).expanduser()
    if destination.suffix.lower() != ".stl":
        destination = destination.with_name(destination.name + ".stl")

    cut = cellcut.cut_cell(job.structure,
                           bool(job.param("bonded_partners", False)))
    if not cut.n_atoms:
        return JobResult.failure("there are no atoms in the cell to "
                                 "export")
    if job.path is not None:
        return _export(job, cut, job.path, destination)
    with tempfile.TemporaryDirectory(prefix="xtal-stl-") as scratch:
        return _export(job, cut, Path(scratch), destination)


def centred(cut):
    """The cut with its mean at :data:`OFF_CENTRE`."""
    if not cut.n_atoms:
        return cut
    cart = np.asarray(cut.cart, dtype=float)
    return dataclasses.replace(
        cut, cart=cart - cart.mean(axis=0) + np.asarray(OFF_CENTRE))


def _export(job, cut, directory: Path, destination: Path) -> JobResult:
    directory.mkdir(parents=True, exist_ok=True)
    pdb = write_pdb(centred(cut), directory / INPUT_NAME)
    stl = directory / OUTPUT_NAME
    job.say(f"cut one cell: {cut.n_atoms} atoms, {len(cut.bonds)} "
            f"bonds")
    process = ExternalProcess(arguments(job, pdb, stl), cwd=directory,
                              log=job.log, on_line=_progress(job))
    result = process.run(cancel=job.cancel, program=PROGRAM)
    failed = _blender_failure(result, stl, "an STL")
    if failed is not None:
        return failed
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(stl, destination)
    megabytes = destination.stat().st_size / 1e6
    return JobResult(
        message=f"wrote {destination.name} ({megabytes:.1f} MB): "
                f"{cut.n_atoms} atoms, {len(cut.bonds)} bonds",
        artifacts=(destination,))


def _render_params() -> tuple[Param, ...]:
    """What changes the picture and not the scene: the light and the
    camera's lens and angle are the scene, and are constants of
    ``render_scene.py``."""
    return (
        Param("output", "Save as", kind="path", default="",
              help="Where the PNG goes.  The run folder keeps a copy, "
                   "and the scene.blend it was rendered from, to open "
                   "in Blender and take further"),
        Param("bonded_partners", "Complete bonds across the cell faces",
              kind="bool", default=False,
              help="Bring in the atom at the far end of every bond "
                   "that leaves the cell, so a linker cut by a face "
                   "is drawn with both its ends"),
        Param("width", "Width", kind="int", default=1920, minimum=16,
              maximum=16384, step=10, suffix=" px",
              help="The picture's width.  The camera's 40 mm lens "
                   "spans the longer side"),
        Param("height", "Height", kind="int", default=1080,
              minimum=16, maximum=16384, step=10, suffix=" px",
              help="The picture's height"),
        Param("samples", "Render samples", kind="int", default=50,
              minimum=1, maximum=10000,
              help="Cycles' samples a pixel for the picture.  More is "
                   "less noise, and time in proportion"),
        Param("viewport_samples", "Viewport samples", kind="int",
              default=10, minimum=1, maximum=10000,
              help="Cycles' samples in Blender's own rendered view, "
                   "for when scene.blend is opened"),
        Param("frame", "Frame the whole structure", kind="bool",
              default=True,
              help="Move the camera along its view until every atom "
                   "is in the picture.  Off stands it at the scene's "
                   "fixed place, which suits a cell of MOF-5's size"),
    )


def render_arguments(job, pdb: Path, blend: Path,
                     image: Path) -> list[str]:
    """Blender's command line for the render, the program itself left
    for :class:`ExternalProcess` to resolve."""
    argv = [PROGRAM.name, "--background", "--factory-startup",
            "--python-exit-code", "1", "--python", str(RENDER_SCRIPT),
            "--", "--input", str(pdb), "--blend", str(blend),
            "--image", str(image),
            "--width", str(int(job.param("width", 1920))),
            "--height", str(int(job.param("height", 1080))),
            "--samples", str(int(job.param("samples", 50))),
            "--viewport-samples",
            str(int(job.param("viewport_samples", 10)))]
    if not job.param("frame", True):
        argv.append("--no-frame")
    return argv


def render(job) -> JobResult:
    output = str(job.param("output", "") or "").strip()
    if not output:
        return JobResult.failure("choose where the picture should be "
                                 "saved")
    destination = Path(output).expanduser()
    if destination.suffix.lower() != ".png":
        destination = destination.with_name(destination.name + ".png")

    cut = cellcut.cut_cell(job.structure,
                           bool(job.param("bonded_partners", False)))
    if not cut.n_atoms:
        return JobResult.failure("there are no atoms in the cell to "
                                 "render")
    if job.path is not None:
        return _render(job, cut, job.path, destination)
    with tempfile.TemporaryDirectory(prefix="xtal-render-") as scratch:
        return _render(job, cut, Path(scratch), destination)


def _render(job, cut, directory: Path, destination: Path) -> JobResult:
    directory.mkdir(parents=True, exist_ok=True)
    pdb = write_pdb(centred(cut), directory / INPUT_NAME)
    blend = directory / SCENE_NAME
    image = directory / IMAGE_NAME
    job.say(f"cut one cell: {cut.n_atoms} atoms, {len(cut.bonds)} "
            f"bonds")
    process = ExternalProcess(render_arguments(job, pdb, blend, image),
                              cwd=directory, log=job.log,
                              on_line=_progress(job))
    result = process.run(cancel=job.cancel, program=PROGRAM)
    failed = _blender_failure(result, image, "a picture")
    if failed is not None:
        return failed
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(image, destination)
    kept = (destination, blend) if blend.is_file() else (destination,)
    return JobResult(
        message=f"rendered {destination.name}: {cut.n_atoms} atoms, "
                f"{len(cut.bonds)} bonds",
        artifacts=kept)


def _blender_failure(result, written: Path, what: str):
    """The failure a finished Blender run amounts to, or None when it
    wrote ``written``."""
    if result.cancelled:
        return JobResult.stopped("Blender was stopped")
    if result.returncode == ADDON_MISSING:
        said = [_unprefixed(line) for line in result.lines
                if line.strip()]
        return JobResult.failure(
            "Blender could not enable the Atomic Blender add-on, "
            "which reads the PDB",
            detail="\n".join(said) or result.detail())
    if not result.ok or not written.is_file():
        return JobResult.failure(
            result.message() if not result.ok
            else f"Blender finished without writing {what}",
            detail=result.detail())
    return None


def _unprefixed(line: str) -> str:
    for prefix in (_PREFIX, _RENDER_PREFIX):
        line = line.replace(prefix, "")
    return line.strip()


def _progress(job):
    """The script's own lines, without its prefix, onto the status
    bar; Blender's housekeeping into the log only."""
    if job.on_progress is None:
        return None

    def line(text: str) -> None:
        for prefix in (_PREFIX, _RENDER_PREFIX):
            if prefix in text:
                said = text.split(prefix, 1)[1].strip()
                if said and not set(said) <= {"="}:
                    job.on_progress(said[:120])
                return
    return line


def _number(value) -> str:
    return f"{float(value):g}"


EXPORT_STL = Action(
    name="export-stl", label="Export as STL...",
    tip="One unit cell with its bonds, turned into a printable mesh "
        "by Blender",
    params=_params(), run=export_stl, dialog="stl-export", kind="stl",
    keeps_markers=True, listed=False)

RENDER = Action(
    name="render", label="Render in Blender...",
    tip="One unit cell with its bonds, lit and rendered by Blender's "
        "Cycles; the scene is kept beside the picture",
    params=_render_params(), run=render, dialog="blender-render",
    kind="render", keeps_markers=True, listed=False)

BLENDER = Module(
    name="blender", label="Blender",
    description="Blender, run headless, for what it can make of a "
                "structure.",
    order=80, group="export", check=available, actions=(EXPORT_STL, RENDER))


def register(registry=MODULES) -> Module:
    return registry.register(BLENDER)
