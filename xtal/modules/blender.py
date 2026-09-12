"""
xtal.modules.blender
====================
File > Export as STL: one unit cell, as a mesh a 3D printer can take.

The work is Blender's, and ours is to hand it the right thing.  A
crystal has no edges, so the cell is cut out first -- faces and
corners included, and the bonds the document has rather than any a
reader might guess (:func:`xtal.core.cellcut.cut_cell`) -- and written
as a PDB with a CONECT record for every bond
(:mod:`xtal.io.pdb`).  Blender then runs ``pdb_to_printable_stl.py``
headless: the Atomic Blender add-on imports balls and sticks, the
instances are baked into one mesh, and a voxel remesh welds it into a
single watertight solid.

**The script is somebody else's, and ships unchanged** in
``xtal/modules/data/``.  It is excluded from this project's lint for
the reason the vendored PORMAKE is: it is a tool with its own
conventions and its own command line, and a copy reformatted to 79
columns is one that can no longer be compared with the one its author
keeps.

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
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from xtal.core import cellcut
from xtal.io.pdb import write_pdb
from xtal.modules.job import JobResult
from xtal.modules.process import ExternalProcess, Program
from xtal.modules.registry import MODULES, Action, Module, Param

PROGRAM = Program(
    name="blender", label="Blender", env_var="XTAL_BLENDER",
    url="https://www.blender.org/", setting="tools/blender",
    known=("/Applications/Blender.app/Contents/MacOS/Blender",))

SCRIPT = Path(__file__).resolve().parent / "data" / \
    "pdb_to_printable_stl.py"

INPUT_NAME = "structure.pdb"
OUTPUT_NAME = "structure.stl"

#: The script's status for "Atomic Blender could not be enabled".
ADDON_MISSING = 2

#: What the script prefixes every line it prints with.
_PREFIX = "[mol2stl]"


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


def _export(job, cut, directory: Path, destination: Path) -> JobResult:
    directory.mkdir(parents=True, exist_ok=True)
    pdb = write_pdb(cut, directory / INPUT_NAME)
    stl = directory / OUTPUT_NAME
    job.say(f"cut one cell: {cut.n_atoms} atoms, {len(cut.bonds)} "
            f"bonds")
    process = ExternalProcess(arguments(job, pdb, stl), cwd=directory,
                              log=job.log, on_line=_progress(job))
    result = process.run(cancel=job.cancel, program=PROGRAM)
    if result.cancelled:
        return JobResult.stopped("Blender was stopped")
    if result.returncode == ADDON_MISSING:
        said = [line.replace(_PREFIX, "").strip()
                for line in result.lines if line.strip()]
        return JobResult.failure(
            "Blender could not enable the Atomic Blender add-on, "
            "which reads the PDB",
            detail="\n".join(said) or result.detail())
    if not result.ok or not stl.is_file():
        return JobResult.failure(
            result.message() if not result.ok
            else "Blender finished without writing an STL",
            detail=result.detail())
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(stl, destination)
    megabytes = destination.stat().st_size / 1e6
    return JobResult(
        message=f"wrote {destination.name} ({megabytes:.1f} MB): "
                f"{cut.n_atoms} atoms, {len(cut.bonds)} bonds",
        artifacts=(destination,))


def _progress(job):
    """The script's own lines, without its prefix, onto the status
    bar; Blender's housekeeping into the log only."""
    if job.on_progress is None:
        return None

    def line(text: str) -> None:
        if _PREFIX in text:
            said = text.split(_PREFIX, 1)[1].strip()
            if said and not set(said) <= {"="}:
                job.on_progress(said[:120])
    return line


def _number(value) -> str:
    return f"{float(value):g}"


EXPORT_STL = Action(
    name="export-stl", label="Export as STL...",
    tip="One unit cell with its bonds, turned into a printable mesh "
        "by Blender",
    params=_params(), run=export_stl, dialog="stl-export", kind="stl",
    keeps_markers=True)

BLENDER = Module(
    name="blender", label="Blender",
    description="Blender, run headless, for what it can make of a "
                "structure.",
    order=80, check=available, actions=(EXPORT_STL,))


def register(registry=MODULES) -> Module:
    return registry.register(BLENDER)
