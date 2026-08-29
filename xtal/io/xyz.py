"""
xtal.io.xyz
===========
Extended XYZ: cartesian coordinates with the cell on the comment line.

Plain XYZ carries no cell, so round-tripping a crystal through it loses
the lattice.  The extended form (``Lattice="ax ay az bx by bz cx cy
cz"``) is what ASE, OVITO and VMD write, and it round-trips.  A file
without it is read into a P1 box padded around the atoms, which is the
only honest thing to do.

This is also the text format the clipboard uses, so copy/paste between
this application and any other atomistic tool works.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from xtal.core.lattice import Lattice
from xtal.core.p1 import expand
from xtal.core.site import Site
from xtal.core.spacegroup import SpaceGroup
from xtal.core.structure import Structure

PAD = 5.0                       # Angstrom of vacuum for cell-less files
_LATTICE_RE = re.compile(r'Lattice\s*=\s*"([^"]*)"')


def write_xyz(structure: Structure, path, comment: str = "") -> Path:
    path = Path(path)
    path.write_text(xyz_string(structure, comment))
    return path


def xyz_string(structure: Structure, comment: str = "") -> str:
    cell = expand(structure)
    cart = cell.cart
    flat = " ".join(f"{v:.8f}"
                    for v in structure.lattice.matrix.ravel())
    header = (f'Lattice="{flat}" '
              f'Properties=species:S:1:pos:R:3:occupancy:R:1')
    if comment:
        header += f' comment="{comment}"'
    lines = [str(cell.n_atoms), header]
    for k in range(cell.n_atoms):
        x, y, z = cart[k]
        lines.append(f"{cell.elements[k]:<4s} {x: 14.8f} {y: 14.8f} "
                     f"{z: 14.8f} {cell.occupancy[k]:6.3f}")
    lines.append("")
    return "\n".join(lines)


def read_xyz(path) -> Structure:
    return read_xyz_string(Path(path).read_text(), name=str(path))


def read_xyz_string(text: str, name: str = "<string>") -> Structure:
    lines = text.splitlines()
    if not lines:
        raise ValueError("empty XYZ file")
    try:
        n_atoms = int(lines[0].split()[0])
    except (ValueError, IndexError):
        raise ValueError("first line of an XYZ file must be an atom "
                         "count") from None
    comment = lines[1] if len(lines) > 1 else ""

    symbols, cart, occupancies = [], [], []
    for line in lines[2:2 + n_atoms]:
        parts = line.split()
        if len(parts) < 4:
            raise ValueError(f"malformed XYZ line: {line!r}")
        symbols.append(parts[0])
        cart.append([float(v) for v in parts[1:4]])
        occupancies.append(float(parts[4]) if len(parts) > 4 else 1.0)
    if len(symbols) != n_atoms:
        raise ValueError(
            f"file claims {n_atoms} atoms but lists {len(symbols)}")
    cart = np.array(cart, dtype=float).reshape(-1, 3)

    match = _LATTICE_RE.search(comment)
    if match:
        values = [float(v) for v in match.group(1).split()]
        if len(values) != 9:
            raise ValueError("Lattice=... needs nine numbers")
        lattice = Lattice(np.array(values).reshape(3, 3))
    else:
        span = (cart.max(axis=0) - cart.min(axis=0)) if len(cart) else \
            np.zeros(3)
        lattice = Lattice(np.diag(np.maximum(span + 2 * PAD, 1.0)))
        cart = cart - cart.min(axis=0) + PAD if len(cart) else cart

    frac = lattice.to_frac(cart) if len(cart) else np.zeros((0, 3))
    sites = [Site(sym, f, occupancy=occ)
             for sym, f, occ in zip(symbols, frac, occupancies,
                                    strict=True)]
    structure = Structure(lattice=lattice, sites=sites,
                          space_group=SpaceGroup.p1())
    structure.meta.update({"source": name, "format": "xyz"})
    if not match:
        structure.meta["warnings"] = [
            "no Lattice= in the comment line; atoms were placed in a "
            f"padded box with {PAD:g} A of vacuum"]
    structure.ensure_labels()
    return structure
