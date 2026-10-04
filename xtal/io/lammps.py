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

**Read back** (:func:`read_lammps_data`) for the result of a run: the
box, the atoms and their charges in P1, the element of each type from
the comment this writer puts after its mass or else the element of
that mass, and the bonds stated as the graph at the closest image --
the image LAMMPS bonded -- so nothing is perceived on open.  Any
``atom_style`` with the columns of ``full``, ``charge``, ``molecular``
or ``atomic``, named in the Atoms header or told apart by count.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from xtal.core import bonding, elements, p1
from xtal.core.lattice import Lattice
from xtal.core.site import Site
from xtal.core.structure import CellBond, Structure
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


#: Where x, y, z and the charge are in an Atoms row, by atom style
#: (columns counted from 0; ``None``, no charge column).
_STYLES = {"full": (4, 3), "charge": (3, 2), "molecular": (3, None),
           "atomic": (2, None)}
#: The style a row of so many columns is, without a header naming it
#: (image flags add three).  Six is ``charge`` or ``molecular`` and
#: cannot be told apart, so it is the one with a charge.
_BY_COUNT = {7: "full", 6: "charge", 5: "atomic"}


def read_lammps_data(path) -> Structure:
    path = Path(path)
    structure = lammps_data_from_string(
        path.read_text(encoding="utf-8", errors="replace"))
    structure.meta["source"] = str(path)
    structure.meta.setdefault("title", path.stem)
    return structure


def lammps_data_from_string(text: str) -> Structure:
    """A LAMMPS data file as a P1 structure with its bonds stated."""
    lines = text.splitlines()
    box = np.zeros((3, 3))
    origin = np.zeros(3)
    sections: dict[str, tuple[str, list[list[str]]]] = {}
    n = 1
    while n < len(lines):
        body, _, comment = lines[n].partition("#")
        words = body.split()
        if len(words) == 4 and words[2:] in (["xlo", "xhi"],
                                             ["ylo", "yhi"],
                                             ["zlo", "zhi"]):
            axis = "xyz".index(words[2][0])
            origin[axis] = float(words[0])
            box[axis, axis] = float(words[1]) - float(words[0])
        elif len(words) == 6 and words[3:] == ["xy", "xz", "yz"]:
            box[1, 0], box[2, 0], box[2, 1] = map(float, words[:3])
        elif (len(words) == 1 and words[0].isalpha()) or (
                len(words) == 2 and words[1] == "Coeffs"):
            name = body.strip()
            rows = []
            n += 1
            while n < len(lines) and not lines[n].strip():
                n += 1
            while n < len(lines) and lines[n].strip():
                row_body, _, row_comment = lines[n].partition("#")
                rows.append(row_body.split() + (
                    ["#", row_comment.strip()] if row_comment.strip()
                    else []))
                n += 1
            sections[name] = (comment.strip(), rows)
            continue
        n += 1
    if "Atoms" not in sections:
        raise ValueError("a LAMMPS data file with no Atoms section")
    if not np.all(np.diag(box) > 0):
        raise ValueError("a LAMMPS data file with no box")

    symbols = _type_symbols(sections.get("Masses", ("", []))[1])
    header, rows = sections["Atoms"]
    atoms = [r[:r.index("#")] if "#" in r else r for r in rows]
    style = header.split()[0] if header.split() else None
    if style not in _STYLES:
        style = _BY_COUNT.get(len(atoms[0]) if len(atoms[0]) in _BY_COUNT
                              else len(atoms[0]) - 3)
    if style not in _STYLES:
        raise ValueError(
            f"cannot tell the atom style of a row of {len(atoms[0])} "
            f"columns; name it after Atoms, as in 'Atoms  # full'")
    at, q_at = _STYLES[style]
    type_at = 2 if style in ("full", "molecular") else 1
    atoms.sort(key=lambda r: int(r[0]))
    inverse = np.linalg.inv(box)
    sites, index = [], {}
    for k, row in enumerate(atoms):
        symbol = symbols.get(row[type_at])
        if symbol is None:
            raise ValueError(f"atom type {row[type_at]} has no mass")
        cart = np.array([float(v) for v in row[at:at + 3]]) - origin
        frac = cart @ inverse
        sites.append(Site(symbol, frac - np.floor(frac),
                          charge=(float(row[q_at]) if q_at is not None
                                  else None)))
        index[row[0]] = k
    structure = Structure(lattice=Lattice(box), sites=sites)
    structure.ensure_labels()
    _state_bonds(structure, sections.get("Bonds", ("", []))[1], index)
    return structure


def _type_symbols(masses) -> dict[str, str]:
    """Each atom type's element: the comment after its mass, which is
    where this writer and most others name it, else the element whose
    mass it is."""
    table = [(elements.mass(s), s) for s in elements.all_symbols()
             if not elements.is_dummy(s)]
    found = {}
    for row in masses:
        named = (elements.canonical_symbol(row[row.index("#") + 1])
                 if "#" in row else None)
        if named is None:
            mass = float(row[1])
            named = min(table, key=lambda m: abs(m[0] - mass))[1]
        found[row[0]] = named
    return found


def _state_bonds(structure, rows, index) -> None:
    """The file's bonds as the stored graph, each at its closest
    image -- the one LAMMPS bonds."""
    if not rows:
        return
    from xtal.core.bonding import BondRules

    cell = p1.expand(structure)
    matrix = structure.lattice.matrix
    bonds = []
    for row in rows:
        i, j = index[row[2]], index[row[3]]
        image = -np.round(cell.frac[j] - cell.frac[i]).astype(int)
        length = float(np.linalg.norm(
            (cell.frac[j] + image - cell.frac[i]) @ matrix))
        bonds.append(CellBond(i, j, tuple(int(v) for v in image),
                              length))
    rules = BondRules.from_dict(structure.bond_rules)
    structure.set_perceived(bonds, rules.signature(), cell)
