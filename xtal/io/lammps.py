"""
xtal.io.lammps
==============
A LAMMPS data file, ``atom_style full``: the box, the masses, every
atom with its molecule and charge, and the bonds.

**The bonds are the ones on screen, and so the writer is handed the
document and not the cleaned copy.**  :func:`xtal.io.export.for_export`
drops the ``suppressed`` records, and a graph read after that is
perceived again -- every bond the user took away would come back in
the file.  So the format is registered with ``settles_bonds`` and this
reads :func:`xtal.core.bonding.graph` itself, dropping the markers and
anything bonded to one exactly as :func:`xtal.core.cellcut.cut_cell`
does.  Nothing is perceived here.

**No coefficients.**  Atom types are elements and bond types element
pairs, each named in a comment, and choosing a force field for them is
the input script's business.  A coefficient written here would be a
force field chosen on the user's behalf.

**The box is LAMMPS's restricted triclinic one** -- *a* along x, *b*
in the xy plane -- and its tilts are folded into half the box by adding
lattice vectors, which LAMMPS asks for and which moves no atom: it is
the same lattice on another basis.  A left-handed cell turns *c*
round, for the same reason.

**A bond whose partner is not the closest image of it is refused.**
LAMMPS finds a bond's partner at the closest image, so in a cell that
small it would bond the wrong copy and say nothing.  A supercell is
the answer, and the message says so.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from xtal.core import bonding, elements, p1
from xtal.core.structure import Structure
from xtal.io import atomic


def write_lammps_data(structure: Structure, path) -> Path:
    path = Path(path)
    atomic.write_text(path, lammps_data_string(structure), encoding="utf-8")
    return path


def lammps_data_string(structure: Structure) -> str:
    """The data file, as text."""
    cell = p1.expand(structure)
    kept = [k for k in range(cell.n_atoms)
            if not elements.is_dummy(cell.elements[k])]
    if not kept:
        raise ValueError(
            "a LAMMPS data file needs at least one atom that is not a "
            "marker")
    number = {k: n + 1 for n, k in enumerate(kept)}

    box, rotation = lammps_box(structure.lattice.matrix)
    cart = structure.lattice.to_cart(cell.frac[kept]) @ rotation
    frac = cart @ np.linalg.inv(box)
    cart = (frac - np.floor(frac)) @ box

    graph = bonding.graph(structure)
    bonds = [b for b in graph.bonds
             if b.i in number and b.j in number]
    _refuse_long_bonds(bonds, cell, structure.lattice)

    species = list(dict.fromkeys(cell.elements[k] for k in kept))
    atom_type = {symbol: n + 1 for n, symbol in enumerate(species)}
    pairs = list(dict.fromkeys(_pair(cell, b) for b in bonds))
    bond_type = {pair: n + 1 for n, pair in enumerate(pairs)}
    molecule = _molecules(graph, number)
    charges = [cell_site_charge(structure, cell, k) for k in kept]
    charged = any(q is not None for q in charges)

    lx, ly, lz = box[0, 0], box[1, 1], box[2, 2]
    xy, xz, yz = box[1, 0], box[2, 0], box[2, 1]
    title = structure.meta.get("title") or "structure"
    lines = [f"LAMMPS data file written by Crystal Builder: {title}",
             ""]
    if not charged:
        lines.append("# No charges were set; every atom is written "
                     "with q = 0")
    for pair, n in bond_type.items():
        lines.append(f"# bond type {n}: {pair[0]}-{pair[1]}")
    lines += ["",
              f"{len(kept)} atoms",
              f"{len(bonds)} bonds",
              "",
              f"{len(species)} atom types",
              f"{len(pairs)} bond types",
              "",
              f"0.0 {lx:.10f} xlo xhi",
              f"0.0 {ly:.10f} ylo yhi",
              f"0.0 {lz:.10f} zlo zhi"]
    if not np.allclose((xy, xz, yz), 0.0, atol=1e-10):
        lines.append(f"{xy:.10f} {xz:.10f} {yz:.10f} xy xz yz")
    lines += ["", "Masses", ""]
    lines += [f"{atom_type[s]} {elements.mass(s):.6f}  # {s}"
              for s in species]
    lines += ["", "Atoms  # full", ""]
    for n, k in enumerate(kept):
        x, y, z = cart[n]
        lines.append(
            f"{n + 1} {molecule[k]} {atom_type[cell.elements[k]]} "
            f"{charges[n] or 0.0:.6f} {x:.10f} {y:.10f} {z:.10f}")
    if bonds:
        lines += ["", "Bonds", ""]
        lines += [f"{n + 1} {bond_type[_pair(cell, b)]} "
                  f"{number[b.i]} {number[b.j]}"
                  for n, b in enumerate(bonds)]
    return "\n".join(lines) + "\n"


def lammps_box(matrix) -> tuple[np.ndarray, np.ndarray]:
    """``(box, rotation)``: the box's three vectors as rows, lower
    triangular with its tilts folded into half the box, and the
    rotation that takes a cartesian position into its frame.

    The rotation is proper -- a left-handed cell has *c* turned round
    first -- because a reflection would write the other enantiomer.
    """
    m = np.array(matrix, dtype=float)
    if np.linalg.det(m) < 0:
        m[2] = -m[2]
    a, b, c = np.linalg.norm(m, axis=1)
    cos_alpha = m[1] @ m[2] / (b * c)
    cos_beta = m[0] @ m[2] / (a * c)
    cos_gamma = m[0] @ m[1] / (a * b)
    lx = a
    xy = b * cos_gamma
    ly = np.sqrt(b * b - xy * xy)
    xz = c * cos_beta
    yz = (b * c * cos_alpha - xy * xz) / ly
    lz = np.sqrt(c * c - xz * xz - yz * yz)
    box = np.array([[lx, 0.0, 0.0], [xy, ly, 0.0], [xz, yz, lz]])
    rotation = np.linalg.solve(m, box)

    # The same lattice on a basis LAMMPS accepts: b less whole a's,
    # c less whole b's and then whole a's.
    box[1] -= np.round(box[1, 0] / lx) * box[0]
    box[2] -= np.round(box[2, 1] / ly) * box[1]
    box[2] -= np.round(box[2, 0] / lx) * box[0]
    return box, rotation


def cell_site_charge(structure, cell, k):
    """The charge of P1 atom ``k``, from the site it came from."""
    return structure.sites[int(cell.site_idx[k])].charge


def _pair(cell, bond) -> tuple[str, str]:
    return tuple(sorted((cell.elements[bond.i], cell.elements[bond.j]),
                        key=elements.atomic_number))


def _molecules(graph, number) -> dict:
    """A molecule ID for every written atom: its connected component,
    numbered in the order the atoms are."""
    molecule = {}
    for fragment in sorted(graph.fragments(), key=lambda f: f.atoms[0]):
        members = [k for k in fragment.atoms if k in number]
        if not members:
            continue
        n = len({*molecule.values()}) + 1
        for k in members:
            molecule[k] = n
    return molecule


def _refuse_long_bonds(bonds, cell, lattice) -> None:
    """Refuse a bond whose partner is not the closest image of it.

    That, and not "longer than half the box", is what LAMMPS gets
    wrong: it takes a bond's partner at the closest image, so a bond
    in the plane of a sheet 3.2 A thick is still found correctly and a
    bond across it is not.
    """
    matrix = np.asarray(lattice.matrix, dtype=float)
    shifts = np.array([(i, j, k) for i in (-1, 0, 1) for j in (-1, 0, 1)
                       for k in (-1, 0, 1) if (i, j, k) != (0, 0, 0)],
                      dtype=float) @ matrix
    for bond in bonds:
        vector = (cell.frac[bond.j] + np.asarray(bond.image)
                  - cell.frac[bond.i]) @ matrix
        length = float(np.linalg.norm(vector))
        nearest = float(np.linalg.norm(vector + shifts, axis=1).min())
        if nearest <= length + 1e-6:
            raise ValueError(
                f"the {cell.elements[bond.i]}{bond.i + 1}-"
                f"{cell.elements[bond.j]}{bond.j + 1} bond is "
                f"{length:.2f} A, and another image of the same atom "
                f"is {nearest:.2f} A away -- LAMMPS takes a bond's "
                f"partner at the closest image, so it would bond that "
                f"one.  Make a supercell first")
