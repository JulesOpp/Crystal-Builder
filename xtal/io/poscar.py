"""
xtal.io.poscar
==============
VASP's POSCAR and CONTCAR.

The format is positional: no tags, no keys, and the meaning of a line
is where it is.  Line 1 is a comment, line 2 a scale, lines 3-5 the
cell vectors as rows, then the species and their counts, then a word
saying whether the coordinates that follow are Direct (fractional) or
Cartesian.

Two things about it are worth knowing before reading the code.

**The species line is optional, and a file without one is refused.**
VASP 4 wrote the counts alone and took the names from the POTCAR
beside it.  There is no POTCAR here, and the alternative -- reading
the atoms as ``X`` -- would be worse than refusing, because ``X`` in
this application is a *marker* and not an element: every force field
holds one back at the door, so a whole crystal would arrive as dummy
atoms and quietly weigh nothing. Naming the reason is more use than a
structure that is not the one in the file.

**A negative scale is a volume, not a length.**  VASP reads it as the
cell volume in cubic angstroms and scales the vectors to match, which
is a convenience for anyone typing a cell by hand and a trap for
anybody reading one.

Symmetry is not in the file at all.  A POSCAR is P1 by construction,
and :func:`xtal.core.symmetry.detect` is how a group is found again.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from xtal.core.lattice import Lattice
from xtal.core.site import Site
from xtal.core.structure import Structure

#: The file names VASP uses.  A POSCAR is the input and a CONTCAR the
#: relaxed output; they are the same format and differ only in which
#: end of a calculation they came from.
FILENAMES = ("POSCAR", "CONTCAR")


def read_poscar(path) -> Structure:
    """Read a POSCAR or CONTCAR."""
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) < 8:
        raise ValueError(f"{path.name} is too short to be a POSCAR")

    title = lines[0].strip()
    try:
        scale = float(lines[1].split()[0])
    except (ValueError, IndexError):
        raise ValueError(
            f"{path.name}: line 2 should be the scale factor") from None

    vectors = np.array([[float(v) for v in lines[i].split()[:3]]
                        for i in range(2, 5)], dtype=float)
    if scale < 0:
        # Negative means "make the volume this many cubic angstroms".
        volume = abs(float(np.linalg.det(vectors)))
        scale = (abs(scale) / volume) ** (1.0 / 3.0) if volume else 1.0
    vectors = vectors * scale

    index = 5
    species = lines[index].split()
    if species and all(_is_int(tok) for tok in species):
        raise ValueError(
            f"{path.name} lists atom counts with no species, the way "
            f"VASP 4 wrote them: the element names live in the POTCAR "
            f"beside it, and there is nothing in this file to say what "
            f"the atoms are. Add a species line above the counts.")
    index += 1
    counts = [int(tok) for tok in lines[index].split()]
    index += 1

    if lines[index][:1] in ("S", "s"):          # selective dynamics
        index += 1
    mode = lines[index].strip()[:1].lower()
    cartesian = mode in ("c", "k")
    index += 1

    lattice = Lattice(vectors)
    sites = []
    for element, count in zip(species, counts):
        for _ in range(count):
            values = [float(v) for v in lines[index].split()[:3]]
            index += 1
            frac = (lattice.to_frac(np.array(values))
                    if cartesian else np.array(values))
            sites.append(Site(element=_element(element), frac=frac))

    structure = Structure(lattice=lattice, sites=sites)
    structure.meta.update({"title": title or path.stem,
                           "source": str(path), "format": "poscar"})
    structure.ensure_labels()
    return structure


def write_poscar(structure: Structure, path, **_ignored) -> Path:
    """Write a POSCAR, in Direct coordinates and P1.

    Atoms are grouped by element because the format has nowhere else
    to say which is which: the counts line is the only species
    information in the file, so the order of the atoms below it *is*
    the assignment.
    """
    from xtal.core import p1
    path = Path(path)
    cell = p1.expand(structure)

    order: dict[str, list[int]] = {}
    for index, element in enumerate(cell.elements):
        order.setdefault(element, []).append(index)

    lines = [str(structure.meta.get("title") or path.stem),
             "1.0"]
    for row in structure.lattice.matrix:
        lines.append("  {: .16f}  {: .16f}  {: .16f}".format(*row))
    lines.append("  " + "  ".join(order))
    lines.append("  " + "  ".join(str(len(v)) for v in order.values()))
    lines.append("Direct")
    for indices in order.values():
        for index in indices:
            x, y, z = cell.frac[index]
            lines.append(f"  {x: .16f}  {y: .16f}  {z: .16f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _is_int(token: str) -> bool:
    try:
        int(token)
    except ValueError:
        return False
    return True


def _element(name: str) -> str:
    """``Zn2+`` or ``Fe_pv`` as VASP writes them, down to the element."""
    cleaned = name.split("_")[0].split("/")[0].strip()
    letters = "".join(c for c in cleaned if c.isalpha())
    return letters[:2].capitalize() if letters else "X"
