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

**Not a registered format.**  :mod:`xtal.io.registry` writes a
*structure*, through :func:`xtal.io.export.for_export`, which strips
suppressions -- and the bond graph of what comes out would then be
perceived again, bringing back every bond the user took away.  What
this writes is a :class:`~xtal.core.cellcut.CellCut`, whose bonds were
settled before it was made.  There is no CRYST1 either: the cell has
been cut out of the crystal, and a reader that saw a cell would put
the periodicity back.
"""

from __future__ import annotations

from pathlib import Path

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


def write_pdb(cut, path) -> Path:
    path = Path(path)
    path.write_text(pdb_text(cut), encoding="utf-8")
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
