"""
xtal.io.cssr
============
CSSR: cell parameters, then one line per atom.

It exists here for one reason -- it is what Zeo++ reads -- and it is
worth having anyway, because it is the smallest complete description of
a periodic crystal there is: six numbers for the cell, then an element
and three fractions per atom.

**It is written in P1, always.**  CSSR has a space-group field and
every writer that matters puts ``1 P 1`` in it, Zeo++ included; its
reader ignores the field entirely and treats what it is given as the
whole cell.  Writing an asymmetric unit into it would therefore not be
a lossy export, it would be a *wrong* one -- Zeo++ would compute the
porosity of two atoms in a box.  So the P1 expansion is written and the
symmetry is dropped honestly.

**Occupancy is not representable**, and neither are anisotropic
displacement parameters, labels or the bond graph.  A partially
occupied site is written as a whole atom, which is a lie a caller has
to have decided to tell -- :func:`xtal.analysis.porosity.refuse` is
what the Zeo++ module uses to stop before it does.

The format is fixed-ish but every reader in practice splits on
whitespace, which is what this one does too.  The eight zeros before
the charge on each atom line are the connectivity table CSSR was
designed to carry; nothing writes them any more and Zeo++ reads and
discards them, but they have to be *there* or the charge lands in the
wrong field.
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

#: The eight connectivity slots, kept as literal zeros.
_LINKS = " 0" * 8


def write_cssr(structure: Structure, path, name: str = "") -> Path:
    path = Path(path)
    path.write_text(cssr_string(structure, name or path.stem))
    return path


def cssr_string(structure: Structure, name: str = "structure") -> str:
    cell = expand(structure)
    a, b, c, alpha, beta, gamma = structure.lattice.parameters
    # The name goes on its own line and is read with getline, so a
    # newline in it would shift every atom by one line.
    title = " ".join(str(name).split()) or "structure"
    charges = _charges(structure, cell)
    lines = [
        f"\t\t\t\t{a:.4f}  {b:.4f}  {c:.4f}",
        f"\t\t{alpha:.3f}  {beta:.3f}  {gamma:.3f}"
        f"  SPGR =  1 P 1\t\t OPT = 1",
        # The second field is the "coordinates are cartesian" flag, and
        # it has to be there: the reader takes two tokens off this line
        # whatever they are.
        f"{cell.n_atoms}   0",
        f"0 {title}",
    ]
    for k in range(cell.n_atoms):
        x, y, z = cell.frac[k]
        lines.append(
            f" {k + 1} {cell.elements[k]:<3s} {x:9.5f} {y:9.5f} "
            f"{z:9.5f} {_LINKS} {charges[k]:8.4f}")
    lines.append("")
    return "\n".join(lines)


def _charges(structure: Structure, cell) -> np.ndarray:
    """One charge per atom of the P1 cell, from the sites it came
    from.

    Zeo++ does not use them and neither does anything else that reads
    this format today, but the field exists and writing a zero where a
    structure carries a charge throws away something the file has room
    for.
    """
    per_site = np.array([float(getattr(s, "charge", 0.0) or 0.0)
                         for s in structure.sites], dtype=float)
    if not len(per_site) or not cell.n_atoms:
        return np.zeros(cell.n_atoms)
    index = np.clip(np.asarray(cell.site_idx, dtype=int), 0,
                    len(per_site) - 1)
    return per_site[index]


# ======================================================================
#  READING
# ======================================================================

def read_cssr(path) -> Structure:
    path = Path(path)
    structure = read_cssr_string(path.read_text(), name=path.stem)
    structure.meta.update({"source": str(path), "format": "cssr"})
    return structure


def read_cssr_string(text: str, name: str = "structure") -> Structure:
    """Read a CSSR back, in P1 because that is what it says it is.

    Written to be forgiving in the two places real files differ: the
    atom count may be ``****`` when there are more atoms than the
    field was designed for, and the coordinates may be cartesian --
    both of which Zeo++ itself emits.
    """
    lines = [line for line in text.splitlines()]
    if len(lines) < 4:
        raise ValueError("a CSSR file has four header lines")
    try:
        a, b, c = (float(v) for v in lines[0].split()[:3])
        angles = lines[1].split()
        alpha, beta, gamma = (float(v) for v in angles[:3])
    except (ValueError, IndexError):
        raise ValueError(
            "the first two lines of a CSSR file are the cell: "
            "a b c, then alpha beta gamma") from None
    counted = lines[2].split()
    cartesian = len(counted) > 1 and counted[1].strip() == "1"
    title = lines[3].strip() or name

    lattice = Lattice.from_parameters(a, b, c, alpha, beta, gamma)
    inverse = np.linalg.inv(lattice.matrix)
    sites = []
    for line in lines[4:]:
        parts = line.split()
        if len(parts) < 5:
            continue
        symbol = parse_symbol(parts[1])
        if not symbol:
            continue
        coords = np.array([float(v) for v in parts[2:5]])
        frac = coords @ inverse if cartesian else coords
        charge = _trailing_charge(parts)
        sites.append(Site(symbol, frac % 1.0, charge=charge))
    structure = Structure(lattice=lattice, sites=sites,
                          space_group=SpaceGroup.p1())
    structure.meta["title"] = title
    structure.ensure_labels()
    return structure


def _trailing_charge(parts) -> float:
    """The charge, when the connectivity slots are there to place it.

    A file that omits them has no charge column at all rather than a
    charge in the wrong place, so anything short is read as zero.
    """
    if len(parts) < 14:
        return 0.0
    try:
        return float(parts[13])
    except ValueError:                              # pragma: no cover
        return 0.0
