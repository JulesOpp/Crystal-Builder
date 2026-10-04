"""
xtal.io.pdb
===========
A finite set of atoms and bonds as PDB: HETATM lines and CONECT records.

Written for one reader above all, Blender's *Atomic Blender* importer,
which is what turns a cell into a printable mesh.  It reads the
element from the atom-name columns before the element columns, reads
CONECT as fixed five-character fields, takes a ``TER`` anywhere in a
line as the end of a chain, and draws sticks only from CONECT -- it
never works a bond out for itself.  So the atom name is the element
spelled the standard way, nothing else is written that could contain
``TER``, and every bond is a CONECT.

:func:`pdb_text` is that file, from a
:class:`~xtal.core.cellcut.CellCut` whose bonds were settled before it
was made, with no CRYST1: the cell has been cut out of the crystal,
and a reader that saw a cell would put the periodicity back.

:func:`periodic_pdb_text` is the registered *PDB* export, for PyMOL,
VMD and Mercury: CRYST1, the P1 cell's atoms in the frame CRYST1
implies (*a* along x, *b* in the xy plane -- LAMMPS's box, so
:func:`xtal.io.lammps.lammps_box` turns the cell), and a CONECT for
every stored bond inside the cell.  A bond through a cell face is left
out, since CONECT joins two serials and has no image to say which copy
is meant; a viewer drawing it would draw it across the cell.  Like
the LAMMPS file it is registered with ``settles_bonds`` and reads the
graph on screen itself, markers dropped.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from xtal.io import atomic

#: The widest serial five columns hold.
MAX_ATOMS = 99999

#: CONECT holds four partners a line; more continue on a line of their
#: own for the same atom.
PARTNERS_PER_LINE = 4


def pdb_text(cut) -> str:
    """The PDB, as text."""
    if cut.n_atoms > MAX_ATOMS:
        raise ValueError(
            f"{cut.n_atoms} atoms is more than a PDB can number "
            f"({MAX_ATOMS})")
    lines = []
    for serial, (symbol, (x, y, z)) in enumerate(
            zip(cut.elements, cut.cart, strict=True), start=1):
        lines.append(_hetatm(serial, symbol, x, y, z))
    partners: dict[int, list[int]] = {}
    for i, j, _order in cut.bonds:
        partners.setdefault(i + 1, []).append(j + 1)
        partners.setdefault(j + 1, []).append(i + 1)
    for serial in sorted(partners):
        bonded = sorted(partners[serial])
        for start in range(0, len(bonded), PARTNERS_PER_LINE):
            chunk = bonded[start:start + PARTNERS_PER_LINE]
            lines.append(f"CONECT{serial:5d}"
                         + "".join(f"{p:5d}" for p in chunk))
    lines.append("END")
    return "\n".join(lines) + "\n"


def periodic_pdb_text(structure) -> str:
    """The P1 cell as a PDB with its CRYST1 and its bonds."""
    from xtal.core import bonding, elements, p1
    from xtal.io.lammps import lammps_box

    cell = p1.expand(structure)
    kept = [k for k in range(cell.n_atoms)
            if not elements.is_dummy(cell.elements[k])]
    if not kept:
        raise ValueError("a PDB needs at least one atom that is not a "
                         "marker")
    if len(kept) > MAX_ATOMS:
        raise ValueError(
            f"{len(kept)} atoms is more than a PDB can number "
            f"({MAX_ATOMS})")
    serial = {k: n + 1 for n, k in enumerate(kept)}
    box, rotation = lammps_box(structure.lattice.matrix)
    frac = cell.frac[kept]
    wrap = np.floor(frac).astype(int)
    cart = structure.lattice.to_cart(frac - wrap) @ rotation
    a, b, c, alpha, beta, gamma = structure.lattice.parameters
    lines = [f"CRYST1{a:9.3f}{b:9.3f}{c:9.3f}{alpha:7.2f}{beta:7.2f}"
             f"{gamma:7.2f} P 1           1"]
    for n, k in enumerate(kept):
        lines.append(_hetatm(n + 1, cell.elements[k], *cart[n]))
    shift = dict(zip(kept, wrap, strict=True))
    partners: dict[int, list[int]] = {}
    for bond in bonding.graph(structure).bonds:
        if bond.i not in serial or bond.j not in serial:
            continue
        image = np.asarray(bond.image) + shift[bond.j] - shift[bond.i]
        if np.any(image):
            continue                    # through a face: see above
        i, j = serial[bond.i], serial[bond.j]
        partners.setdefault(i, []).append(j)
        partners.setdefault(j, []).append(i)
    for i in sorted(partners):
        bonded = sorted(partners[i])
        for start in range(0, len(bonded), PARTNERS_PER_LINE):
            chunk = bonded[start:start + PARTNERS_PER_LINE]
            lines.append(f"CONECT{i:5d}"
                         + "".join(f"{p:5d}" for p in chunk))
    lines.append("END")
    return "\n".join(lines) + "\n"


def write_periodic_pdb(structure, path) -> Path:
    path = Path(path)
    atomic.write_text(path, periodic_pdb_text(structure),
                      encoding="utf-8")
    return path


def write_pdb(cut, path) -> Path:
    path = Path(path)
    atomic.write_text(path, pdb_text(cut), encoding="utf-8")
    return path


def _hetatm(serial: int, symbol: str, x: float, y: float,
            z: float) -> str:
    """One atom, in the columns the standard fixes.

    The name is the element right-justified into columns 13-14, which
    is how the standard tells calcium (``CA``) from an alpha carbon
    (`` CA``) -- and it is the only thing Atomic Blender reads the
    element from when it is not in its table under the element
    columns.
    """
    element = symbol.upper()
    name = f"{element:>2s}  "
    return (f"HETATM{serial:5d} {name:4s} UNL A   1    "
            f"{x:8.3f}{y:8.3f}{z:8.3f}{1.0:6.2f}{0.0:6.2f}"
            f"          {element:>2s}")
