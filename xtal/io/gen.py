"""
xtal.io.gen
===========
DFTB+'s ``.gen``: an atom count, a species list, and coordinates.

The simplest complete crystal format there is, and worth having for
its own sake as well as for DFTB+.  Three letters decide everything:

* ``C`` -- a cluster.  No cell at all, cartesian coordinates.
* ``S`` -- a supercell, cartesian coordinates, with the lattice at the
  bottom.
* ``F`` -- a supercell, *fractional* coordinates.

Atoms are numbered from 1 and name their element by index into the
species line, which is what makes the format compact and is the one
place a reader can go quietly wrong: an index is one-based, and an
off-by-one turns every carbon into a hydrogen without failing.

**Written in P1**, like CSSR and for the same reason: the format has
no room for a space group and DFTB+ treats what it is given as the
whole cell.  ``F`` is what this writes -- fractional coordinates are
what the rest of the application stores, and round-tripping them
through cartesian and back is a source of drift in the last digit that
shows up as a structure that will not compare equal to itself.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from xtal.core.elements import parse_symbol
from xtal.core.lattice import Lattice
from xtal.core.p1 import expand
from xtal.core.site import Site
from xtal.core.spacegroup import SpaceGroup
from xtal.core.structure import Structure
from xtal.io.text import read_text


def write_gen(structure: Structure, path, fractional: bool = True) -> Path:
    path = Path(path)
    path.write_text(gen_string(structure, fractional), encoding="utf-8")
    return path


def gen_string(structure: Structure, fractional: bool = True) -> str:
    cell = expand(structure)
    if not cell.n_atoms:
        # The species line would be empty, and a reader that skips
        # blank lines -- this one, rightly -- takes the origin for it.
        # DFTB+ cannot run a cell with nothing in it either.
        raise ValueError(
            "a .gen file cannot hold a structure with no atoms; add "
            "some, or export to CIF, which can")
    species = list(dict.fromkeys(cell.elements))
    index = {symbol: n + 1 for n, symbol in enumerate(species)}
    kind = "F" if fractional else "S"
    lines = [f"{cell.n_atoms} {kind}", " ".join(species)]
    coords = cell.frac if fractional else cell.cart
    for n in range(cell.n_atoms):
        x, y, z = coords[n]
        lines.append(f"{n + 1:6d} {index[cell.elements[n]]:3d} "
                     f"{x: 20.12f} {y: 20.12f} {z: 20.12f}")
    # The origin, then the three lattice vectors as rows -- which is
    # how Lattice stores them, so no transpose is involved anywhere.
    lines.append(f"{0.0: 20.12f} {0.0: 20.12f} {0.0: 20.12f}")
    for vector in structure.lattice.matrix:
        lines.append(" ".join(f"{v: 20.12f}" for v in vector))
    lines.append("")
    return "\n".join(lines)


def read_gen(path) -> Structure:
    path = Path(path)
    structure = read_gen_string(read_text(path))
    structure.meta.update({"source": str(path), "format": "gen"})
    return structure


def read_gen_string(text: str) -> Structure:
    """Read a ``.gen``, in P1 because that is what it holds.

    This is also how a DFTB+ relaxation comes back: ``geo_end.gen`` is
    the final geometry, in the same format as the input.
    """
    rows = [line.split("#", 1)[0].strip() for line in text.splitlines()]
    rows = [row for row in rows if row]
    if len(rows) < 3:
        raise ValueError("a .gen file needs a count line, a species "
                         "line and at least one atom")
    head = rows[0].split()
    try:
        n_atoms = int(head[0])
    except (ValueError, IndexError):
        raise ValueError(
            "the first line of a .gen file is the atom count and the "
            "kind: 'C', 'S' or 'F'") from None
    kind = (head[1] if len(head) > 1 else "C").upper()
    if kind not in ("C", "S", "F"):
        raise ValueError(
            f"{kind!r} is not a .gen geometry kind; it is C (cluster), "
            f"S (supercell) or F (fractional)")

    species = [parse_symbol(s) for s in rows[1].split()]
    coords = np.zeros((n_atoms, 3))
    elements = []
    for n in range(n_atoms):
        parts = rows[2 + n].split()
        if len(parts) < 5:
            raise ValueError(
                f"atom {n + 1} of a .gen file needs an index, a "
                f"species number and three coordinates")
        # One-based into the species line.  An off-by-one here turns
        # every carbon into a hydrogen and raises nothing, which is
        # why it is checked rather than clamped.
        which = int(parts[1]) - 1
        if not 0 <= which < len(species):
            raise ValueError(
                f"atom {n + 1} names species {which + 1}, and the "
                f"file lists {len(species)}")
        elements.append(species[which])
        coords[n] = [float(v) for v in parts[2:5]]

    lattice = _lattice(rows[2 + n_atoms:], kind, coords)
    frac = coords if kind == "F" else coords @ np.linalg.inv(
        lattice.matrix)
    structure = Structure(
        lattice=lattice,
        sites=[Site(symbol, f % 1.0)
               for symbol, f in zip(elements, frac, strict=True)],
        space_group=SpaceGroup.p1())
    structure.ensure_labels()
    return structure


#: Vacuum around a cluster, which has no cell of its own.  Made
#: obvious rather than plausible, like the XYZ reader's.
PAD = 5.0


def _lattice(rows, kind: str, coords) -> Lattice:
    if kind == "C":
        # A cluster has no cell.  Padding one around it is the only
        # honest thing to do and the box is made obvious rather than
        # plausible -- the same rule as the XYZ reader's.
        if not len(coords):                         # pragma: no cover
            return Lattice(np.eye(3))
        span = coords.max(axis=0) - coords.min(axis=0)
        return Lattice(np.diag(np.maximum(span + 2 * PAD, 1.0)))
    if len(rows) < 4:
        raise ValueError(
            f"a .gen file of kind {kind} ends with an origin and "
            f"three lattice vectors, and this one has "
            f"{len(rows)} line(s) after the atoms")
    # rows[0] is the origin, which DFTB+ writes and nothing uses: the
    # coordinates are already absolute.
    return Lattice(np.array([[float(v) for v in row.split()[:3]]
                             for row in rows[1:4]]))
