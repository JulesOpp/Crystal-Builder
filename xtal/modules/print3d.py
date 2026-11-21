"""
xtal.modules.print3d
====================
File > Export for Two-Colour Printing: one unit cell as two printable
bodies, colour 1 and colour 2, in a 3MF a slicer opens as one object
of two parts, with an STL of each body beside it.

**Ours, not Blender's.**  Export as STL welds the model into one solid
in Blender, and one solid has one colour.  Two colours are two bodies
that must meet exactly, which is :mod:`xtal.printing`'s whole job, so
this export needs no Blender and is greyed for nothing.

**Which atom is which colour** is an element table (``Zn=2``, every
element not named is colour 1) and then, over it, a list of P1 atoms
(``17=2 18=1``): the window fills the second from the atom groups
ticked in its form, so a person can colour by element and still pick
out one linker.  Bonds are all colour 1, all colour 2, or half and half
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
#: MFU-4l and 5.2-5.3 on MOF-5, Zn colour 2 and half bonds.
TRIANGLES_PER_AREA = 5.5

BOND_CHOICES = (("half", "Half and half"), ("1", "Colour 1"),
                ("2", "Colour 2"))


def _params() -> tuple[Param, ...]:
    return (
        Param("output", "Save as", kind="path", default="",
              help="Where the 3MF goes.  An STL of each colour is "
                   "written beside it, and a copy of all three stays "
                   "in the run folder"),
        Param("bonds", "Bonds", kind="choice", default="half",
              choices=BOND_CHOICES,
              help="Half and half changes colour halfway between the "
                   "two balls' surfaces, each half its atom's"),
        Param("element_colours", "Colour 2 elements", kind="text",
              default="",
              help="Elements printed in colour 2, as Zn=2 Cu=2; any "
                   "element not named is colour 1"),
        Param("atom_colours", "Atoms by index", kind="text", default="",
              help="P1 atoms whose colour overrides their element's, "
                   "as 17=2 18=1.  The window fills this from the "
                   "atom groups"),
        Param("bonded_partners", "Complete bonds across the cell faces",
              kind="bool", default=False,
              help="Bring in the atom at the far end of every bond "
                   "that leaves the cell, so a linker cut by a face "
                   "prints with both its ends"),
        Param("ball_scale", "Ball scale", kind="float", default=0.8,
              minimum=0.1, maximum=5.0, step=0.1, decimals=2,
              help="Atomic radii times this, as Export as STL"),
        Param("h_scale", "Hydrogen scale", kind="float", default=2.0,
              minimum=0.1, maximum=10.0, step=0.1, decimals=2,
              help="Hydrogens again times this: at atomic radii they "
                   "are too small to print"),
        Param("stick_radius", "Stick radius", kind="float",
              default=0.4, minimum=0.05, maximum=3.0, step=0.05,
              decimals=2, suffix=" A"),
        Param("voxel_size", "Voxel size", kind="float", default=0.10,
              minimum=0.02, maximum=2.0, step=0.01, decimals=3,
              suffix=" A",
              help="The grid both colours are marched on.  Smaller "
                   "keeps more detail; the triangles go as one over "
                   "its square"),
        Param("max_tris", "Triangle budget", kind="int",
              default=1000000, minimum=0, maximum=100000000,
              step=100000,
              help="Both colours together.  The grid is coarsened "
                   "until the model fits; 0 is no budget"),
        Param("target_size", "Longest side", kind="float", default=0.0,
              minimum=0.0, maximum=10000.0, step=10.0, decimals=1,
              suffix=" mm",
              help="Scale the model so its longest side is this.  0 "
                   "leaves one Angstrom as one millimetre"),
    )


class ColourError(ValueError):
    pass


def parse_colours(text: str, key=str) -> dict:
    """``"Zn=2 O=1"`` (commas or spaces) as ``{"Zn": 2, "O": 1}``;
    ``key`` turns the left side into what it names."""
    out = {}
    for item in str(text or "").replace(",", " ").split():
        name, sep, value = item.partition("=")
        if not sep or value.strip() not in ("1", "2"):
            raise ColourError(f"{item!r}: write a colour as NAME=1 or "
                              f"NAME=2")
        try:
            out[key(name.strip())] = int(value)
        except ValueError as exc:
            raise ColourError(f"{item!r}: {exc}") from None
    return out


def _element(text: str) -> str:
    symbol = el.canonical_symbol(text)
    if symbol is None:
        raise ValueError(f"{text!r} is not an element")
    return symbol


def image_colours(cut, by_element: dict, by_atom: dict) -> np.ndarray:
    """Each image's colour: its P1 atom's if named, else its
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


def export_two_colour(job) -> JobResult:
    output = str(job.param("output", "") or "").strip()
    if not output:
        return JobResult.failure("choose where the 3MF should be saved")
    destination = Path(output).expanduser()
    if destination.suffix.lower() != ".3mf":
        destination = destination.with_name(destination.name + ".3mf")
    try:
        by_element = parse_colours(job.param("element_colours", ""),
                                   _element)
        by_atom = parse_colours(job.param("atom_colours", ""), int)
    except ColourError as exc:
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
    colours = image_colours(cut, by_element, by_atom)
    prims = primitives.build(
        cut, colours, bonds,
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
            f"bonds; {int((colours == 2).sum())} atoms in colour 2")
    bodies = mesh.two_bodies(prims, voxel, between=job.cancel.check)

    scale = _scale(bodies.vertices, float(job.param("target_size", 0)))
    vertices = (bodies.vertices * scale).astype(np.float32)
    parts = []
    for colour in (1, 2):
        triangles = bodies.bodies[colour - 1]
        if not len(triangles):
            continue
        report = check.report(vertices.astype(float), triangles)
        if not report.ok:
            return JobResult.failure(
                f"colour {colour} did not come out a closed solid "
                f"({report.says()}); nothing was written.  Try a "
                f"smaller voxel")
        parts.append(Part(f"colour {colour}", vertices, triangles,
                          extruder=colour))
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


def stl_path(destination: Path, colour: int) -> Path:
    return destination.with_name(f"{destination.stem}_colour{colour}"
                                 f".stl")


def _write(job, parts, folder: Path, destination: Path,
           voxel: float) -> JobResult:
    destination.parent.mkdir(parents=True, exist_ok=True)
    written = []
    for target in (folder / destination.name, destination):
        write_3mf(target, parts, name=destination.stem)
        for part in parts:
            colour = part.extruder
            write_stl(stl_path(target, colour), part.vertices,
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
        message += f"; nothing is colour {missing[0]}"
    return JobResult(message=message, artifacts=tuple(written))


EXPORT_TWO_COLOUR = Action(
    name="export-two-colour", label="Export for Two-Colour Printing...",
    tip="One unit cell as two bodies, one per colour, that meet "
        "exactly: a 3MF of one object in two parts, and an STL of each",
    params=_params(), run=export_two_colour, dialog="stl-two-colour",
    kind="print", keeps_markers=True, listed=False)

PRINT3D = Module(
    name="print3d", label="3D printing",
    description="A structure as a model to 3D print in two colours.",
    order=81, group="export", actions=(EXPORT_TWO_COLOUR,))


def register(registry=MODULES) -> Module:
    return registry.register(PRINT3D)
