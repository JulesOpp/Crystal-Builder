"""
xtal.modules.print3d
====================
File > Export as STL: one unit cell as a model to 3D print, in one
color or in two.

**One form, two makers.**  In one color the model is Blender's, as it
always was (:func:`xtal.modules.blender.export_stl`, run unchanged,
and refused with Blender's own reason when it is not installed).  With
*Two-color printing* ticked it is ours: two printable bodies, color 1
and color 2, in a 3MF a slicer opens as one object of two parts, with
an STL of each body beside it.  Blender cannot make that -- its remesh
welds everything into one solid, and one solid has one color -- and
two colors are two bodies that must meet exactly, which is
:mod:`xtal.printing`'s whole job, so the two-color export needs no
Blender.  The settings the two share (the cut, the balls and sticks,
the voxel, the budget, the size) are the same parameters, so turning
the box on and off keeps them.

**Which atom is which color** is an element table (``Zn=2``, every
element not named is color 1) and then, over it, a list of P1 atoms
(``17=2 18=1``): the window fills the second from the atom groups
ticked in its form, so a person can color by element and still pick
out one linker.  Bonds are all color 1, all color 2, or half and half
(each half its atom's, changing at the middle of the visible stick).

**Nothing a slicer would have to repair is written.**  Each body is
checked closed, consistently wound, free of zero-area triangles and
enclosing a positive volume (:mod:`xtal.printing.check`) after it is
scaled and rounded to the float32 the files hold; a body that fails is
a failure naming what was wrong, never a file.

**The triangle budget is met by the grid, never by decimating.**
Decimating the two bodies apart would move the interface in one and
not the other.  The triangles are estimated from the balls' and
sticks' area before anything is built, and the voxel is coarsened
until the estimate fits; the run says so when it does.
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import numpy as np

from xtal.core import cellcut, limits
from xtal.core import elements as el
from xtal.io.stl import write_stl
from xtal.io.threemf import Part, write_3mf
from xtal.modules.job import JobResult
from xtal.modules.registry import MODULES, Action, Module, Param
from xtal.printing import check, mesh, primitives

#: Triangles a mesh comes out with per square Angstrom of the
#: primitives' area bound, over the voxel squared.  Measured 5.0 on
#: MFU-4l and 5.2-5.3 on MOF-5, Zn color 2 and half bonds.
TRIANGLES_PER_AREA = 5.5

BOND_CHOICES = (("half", "Half and half"), ("1", "Color 1"),
                ("2", "Color 2"))


def _params() -> tuple[Param, ...]:
    return (
        Param("output", "Save as", kind="path", default="",
              help="Where the model goes: an STL, or with two colors "
                   "a 3MF with an STL of each color beside it.  A copy "
                   "also stays in the run folder"),
        Param("two_color", "Two-color printing", kind="bool",
              default=False,
              help="Two bodies, one per filament, that meet exactly, "
                   "in a 3MF Bambu Studio and Orca open as one object "
                   "of two parts.  Needs no Blender"),
        Param("bonds", "Bonds", kind="choice", default="half",
              choices=BOND_CHOICES,
              help="Half and half changes color halfway between the "
                   "two balls' surfaces, each half its atom's"),
        Param("element_colors", "Color 2 elements", kind="text",
              default="",
              help="Elements printed in color 2, as Zn=2 Cu=2; any "
                   "element not named is color 1"),
        Param("atom_colors", "Atoms by index", kind="text", default="",
              help="P1 atoms whose color overrides their element's, "
                   "as 17=2 18=1.  The window fills this from the "
                   "atom groups"),
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
              help="One color only: weld the balls and sticks into one "
                   "watertight mesh.  Off leaves overlapping pieces, "
                   "which most slicers refuse.  Two colors are always "
                   "welded"),
        Param("voxel_size", "Voxel size", kind="float", default=0.10,
              minimum=0.01, maximum=2.0, step=0.01, decimals=3,
              suffix=" A",
              help="The grid the model is meshed on.  Smaller keeps "
                   "more detail; the triangles go as one over its "
                   "square"),
        Param("max_tris", "Triangle budget", kind="int",
              default=1000000, minimum=0, maximum=100000000,
              step=100000,
              help="Both colors together.  The grid is coarsened "
                   "until the model fits; 0 is no budget; a binary "
                   "STL is about 50 bytes a triangle"),
        Param("target_size", "Longest side", kind="float", default=0.0,
              minimum=0.0, maximum=10000.0, step=10.0, decimals=1,
              suffix=" mm",
              help="Scale the model so its longest side is this.  0 "
                   "leaves one Angstrom as one millimetre"),
    )


class ColorError(ValueError):
    pass


def parse_colors(text: str, key=str) -> dict:
    """``"Zn=2 O=1"`` (commas or spaces) as ``{"Zn": 2, "O": 1}``;
    ``key`` turns the left side into what it names."""
    out = {}
    for item in str(text or "").replace(",", " ").split():
        name, sep, value = item.partition("=")
        if not sep or value.strip() not in ("1", "2"):
            raise ColorError(f"{item!r}: write a color as NAME=1 or "
                              f"NAME=2")
        try:
            out[key(name.strip())] = int(value)
        except ValueError as exc:
            raise ColorError(f"{item!r}: {exc}") from None
    return out


def _element(text: str) -> str:
    symbol = el.canonical_symbol(text)
    if symbol is None:
        raise ValueError(f"{text!r} is not an element")
    return symbol


def image_colors(cut, by_element: dict, by_atom: dict) -> np.ndarray:
    """Each image's color: its P1 atom's if named, else its
    element's, else 1."""
    out = np.array([by_element.get(e, 1) for e in cut.elements],
                   dtype=int)
    for k, site in enumerate(cut.sites):
        if site in by_atom:
            out[k] = by_atom[site]
    return out


def estimated_triangles(prims, voxel: float) -> int:
    return int(TRIANGLES_PER_AREA * prims.area() / voxel ** 2)


def voxel_for(prims, voxel: float, budget: int) -> float:
    """``voxel``, or the finer of the coarser ones the budget allows,
    to a thousandth of an Angstrom."""
    if budget <= 0 or estimated_triangles(prims, voxel) <= budget:
        return voxel
    need = math.sqrt(TRIANGLES_PER_AREA * prims.area() / budget)
    return math.ceil(need * 1000) / 1000


def check_size(prims, voxel: float, profile=None) -> limits.Verdict:
    def fits(limit):
        finer = math.sqrt(TRIANGLES_PER_AREA * prims.area() / limit)
        return f"a voxel of {math.ceil(finer * 100) / 100:.2f} A fits"
    return limits._judge("print", estimated_triangles(prims, voxel),
                         profile, "the model would have {} triangles",
                         fits)


def export(job) -> JobResult:
    """One color through Blender, two through :func:`export_two_color`.

    The path is given the suffix of what is made -- the dialog swaps it
    as the box is ticked, but a command line or a remembered value may
    still name the other one, and an STL written as ``model.3mf`` is a
    file nothing opens."""
    two = bool(job.param("two_color", False))
    output = str(job.param("output", "") or "").strip()
    if output:
        job.params = {**job.params,
                      "output": str(with_suffix(output, two))}
    if two:
        return export_two_color(job)
    from xtal.modules import blender

    available = blender.available()
    if not available:
        return JobResult.failure(
            f"{available.reason}.  Two-color printing needs no Blender")
    return blender.export_stl(job)


def with_suffix(path, two_color: bool) -> Path:
    """``path`` ending ``.3mf`` for two colors and ``.stl`` for one;
    the other suffix is swapped, anything else kept and added to."""
    path = Path(path).expanduser()
    wanted, other = (".3mf", ".stl") if two_color else (".stl", ".3mf")
    suffix = path.suffix.lower()
    if suffix == wanted:
        return path
    if suffix == other:
        return path.with_suffix(wanted)
    return path.with_name(path.name + wanted)


def export_two_color(job) -> JobResult:
    output = str(job.param("output", "") or "").strip()
    if not output:
        return JobResult.failure("choose where the 3MF should be saved")
    destination = with_suffix(output, True)
    try:
        by_element = parse_colors(job.param("element_colors", ""),
                                   _element)
        by_atom = parse_colors(job.param("atom_colors", ""), int)
    except ColorError as exc:
        return JobResult.failure(str(exc))
    bonds = str(job.param("bonds", "half"))
    if bonds not in primitives.BONDS:
        return JobResult.failure(f"bonds must be one of "
                                 f"{', '.join(primitives.BONDS)}")

    cut = cellcut.cut_cell(job.structure,
                           bool(job.param("bonded_partners", False)))
    if not cut.n_atoms:
        return JobResult.failure("there are no atoms in the cell to "
                                 "export")
    colors = image_colors(cut, by_element, by_atom)
    prims = primitives.build(
        cut, colors, bonds,
        ball_scale=float(job.param("ball_scale", 0.8)),
        h_scale=float(job.param("h_scale", 2.0)),
        stick_radius=float(job.param("stick_radius", 0.4)))

    asked = float(job.param("voxel_size", 0.10))
    voxel = voxel_for(prims, asked, int(job.param("max_tris", 1000000)))
    if voxel != asked:
        job.say(f"a voxel of {voxel:.3f} A, coarser than the "
                f"{asked:.3f} A asked, to fit the triangle budget")
    verdict = check_size(prims, voxel)
    sentence = f"{verdict.sentence[:1].upper()}{verdict.sentence[1:]}"
    if verdict.refused:
        return JobResult.failure(sentence)
    if verdict.warned:
        job.note(sentence)
        job.say(sentence)
    job.say(f"cut one cell: {cut.n_atoms} atoms, {len(cut.bonds)} "
            f"bonds; {int((colors == 2).sum())} atoms in color 2")
    bodies = mesh.two_bodies(prims, voxel, between=job.cancel.check)

    scale = _scale(bodies.vertices, float(job.param("target_size", 0)))
    vertices = (bodies.vertices * scale).astype(np.float32)
    parts = []
    for color in (1, 2):
        triangles = bodies.bodies[color - 1]
        if not len(triangles):
            continue
        report = check.report(vertices.astype(float), triangles)
        if not report.ok:
            return JobResult.failure(
                f"color {color} did not come out a closed solid "
                f"({report.says()}); nothing was written.  Try a "
                f"smaller voxel")
        parts.append(Part(f"color {color}", vertices, triangles,
                          extruder=color))
    if not parts:
        return JobResult.failure("nothing came out of the mesh")

    if job.path is not None:
        return _write(job, parts, job.path, destination, voxel)
    with tempfile.TemporaryDirectory(prefix="xtal-print-") as scratch:
        return _write(job, parts, Path(scratch), destination, voxel)


def _scale(vertices, target: float) -> float:
    if target <= 0 or not len(vertices):
        return 1.0
    longest = float((vertices.max(axis=0) - vertices.min(axis=0)).max())
    return target / longest if longest > 0 else 1.0


def stl_path(destination: Path, color: int) -> Path:
    return destination.with_name(f"{destination.stem}_color{color}"
                                 f".stl")


def _write(job, parts, folder: Path, destination: Path,
           voxel: float) -> JobResult:
    destination.parent.mkdir(parents=True, exist_ok=True)
    written = []
    for target in (folder / destination.name, destination):
        write_3mf(target, parts, name=destination.stem)
        for part in parts:
            color = part.extruder
            write_stl(stl_path(target, color), part.vertices,
                      part.triangles, name=part.name)
        if target == destination:
            written = [target] + [stl_path(target, p.extruder)
                                  for p in parts]
    triangles = sum(len(p.triangles) for p in parts)
    missing = [c for c in (1, 2)
               if c not in {p.extruder for p in parts}]
    message = (f"wrote {destination.name}: {len(parts)} part"
               f"{'s' if len(parts) > 1 else ''}, "
               f"{limits.count(triangles)} triangles at {voxel:.3f} A")
    if missing:
        message += f"; nothing is color {missing[0]}"
    return JobResult(message=message, artifacts=tuple(written))


EXPORT = Action(
    name="export", label="Export as STL...",
    tip="One unit cell with its bonds as a model to 3D print: one "
        "color through Blender, or two colors as two bodies that meet "
        "exactly, in a 3MF and an STL of each",
    params=_params(), run=export, dialog="print-export", kind="stl",
    keeps_markers=True, listed=False)

PRINT3D = Module(
    name="print3d", label="3D printing",
    description="A structure as a model to 3D print, in one color or "
                "two.",
    order=81, group="export", actions=(EXPORT,))


def register(registry=MODULES) -> Module:
    return registry.register(PRINT3D)
