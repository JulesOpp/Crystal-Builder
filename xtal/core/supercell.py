"""
xtal.core.supercell
===================
Cell-changing operations: supercells, general cell transformations,
lattice reduction, and origin shifts.

All of them produce **P1** structures.  A supercell of a symmetric
crystal generally does not keep its space group in the same setting,
and quietly carrying the old group forward would be wrong in a way
that is hard to notice.  The user can always re-detect symmetry on the
result (``symmetry.detect``), which is the honest path back.

Conventions match ``Lattice.transform``: P is an integer matrix whose
ROWS give the new lattice vectors in units of the old ones, so the new
cell is ``P @ M`` and a coordinate transforms as ``x' = x @ inv(P)``.
"""

from __future__ import annotations

import itertools

import numpy as np
import spglib

from xtal.core import p1
from xtal.core.lattice import Lattice
from xtal.core.spacegroup import SpaceGroup
from xtal.core.structure import Structure

POSITION_TOL = 1e-6


def supercell(structure: Structure, na: int, nb: int, nc: int
              ) -> Structure:
    """Build an na x nb x nc supercell.  The result is in P1."""
    for name, n in (("na", na), ("nb", nb), ("nc", nc)):
        if int(n) < 1:
            raise ValueError(f"{name} must be >= 1, got {n}")
    na, nb, nc = int(na), int(nb), int(nc)
    cell = p1.expand(structure)
    lattice = structure.lattice.transform(np.diag([na, nb, nc]))
    counts = np.array([na, nb, nc], dtype=float)

    sites = []
    for shift in itertools.product(range(na), range(nb), range(nc)):
        offset = np.array(shift, dtype=float)
        for k in range(cell.n_atoms):
            parent = structure.sites[int(cell.site_idx[k])]
            s = parent.copy()
            s.frac = (cell.frac[k] + offset) / counts
            s.label = ""
            s.wyckoff = None
            sites.append(s)

    out = Structure(lattice=lattice, sites=sites,
                    space_group=SpaceGroup.p1(),
                    bond_rules=dict(structure.bond_rules),
                    meta=dict(structure.meta))
    out.ensure_labels()
    return out


def transform_cell(structure: Structure, p_matrix) -> Structure:
    """Apply a general integer cell transformation P.

    ``|det P|`` must be a positive integer: > 1 builds a supercell,
    = 1 re-expresses the same cell in a different basis.  Sub-cells
    (|det P| < 1) are not supported here -- that is a symmetry
    operation, not a basis change, and it belongs with the primitive
    reduction below.
    """
    p_arr = np.asarray(p_matrix, dtype=float)
    if p_arr.shape != (3, 3):
        raise ValueError("transformation matrix must be 3x3")
    if not np.allclose(p_arr, np.round(p_arr), atol=1e-9):
        raise ValueError("transformation matrix must be integer-valued")
    p_arr = np.round(p_arr)
    det = float(np.linalg.det(p_arr))
    if det < 1 - 1e-9:
        raise ValueError(
            f"determinant must be a positive integer, got {det:g}")
    multiplier = int(round(det))

    lattice = structure.lattice.transform(p_arr)
    inv_p = np.linalg.inv(p_arr)
    cell = p1.expand(structure)

    # Old-lattice translations that can land inside the new cell: the
    # bounding box of the new cell's corners, expressed in old units.
    corners = np.array(list(itertools.product((0, 1), repeat=3)),
                       dtype=float) @ p_arr
    lo = np.floor(corners.min(axis=0)).astype(int) - 1
    hi = np.ceil(corners.max(axis=0)).astype(int) + 1
    shifts = np.array(list(itertools.product(
        range(lo[0], hi[0] + 1), range(lo[1], hi[1] + 1),
        range(lo[2], hi[2] + 1))), dtype=float)

    sites, seen = [], []
    for k in range(cell.n_atoms):
        new_positions = (cell.frac[k] + shifts) @ inv_p
        wrapped = p1._wrap(new_positions)
        for pos in wrapped:
            if any(np.allclose(pos, q, atol=POSITION_TOL)
                   for q in seen):
                continue
            seen.append(pos)
            parent = structure.sites[int(cell.site_idx[k])]
            s = parent.copy()
            s.frac = pos
            s.label = ""
            s.wyckoff = None
            sites.append(s)

    expected = cell.n_atoms * multiplier
    if len(sites) != expected:
        raise ValueError(
            f"cell transformation produced {len(sites)} atoms, "
            f"expected {expected} -- the matrix is probably not a "
            f"valid lattice transformation")

    out = Structure(lattice=lattice, sites=sites,
                    space_group=SpaceGroup.p1(),
                    bond_rules=dict(structure.bond_rules),
                    meta=dict(structure.meta))
    out.ensure_labels()
    return out


def _rebasis(structure: Structure, new_matrix) -> Structure:
    """Same crystal, new basis vectors: cartesian positions are kept
    and refolded into the new cell."""
    lattice = Lattice(new_matrix)
    cell = p1.expand(structure)
    cart = structure.lattice.to_cart(cell.frac)
    sites = []
    for k in range(cell.n_atoms):
        parent = structure.sites[int(cell.site_idx[k])]
        s = parent.copy()
        s.frac = p1._wrap(lattice.to_frac(cart[k]))
        s.label = ""
        s.wyckoff = None
        sites.append(s)
    out = Structure(lattice=lattice, sites=sites,
                    space_group=SpaceGroup.p1(),
                    bond_rules=dict(structure.bond_rules),
                    meta=dict(structure.meta))
    out.ensure_labels()
    return out


def niggli_reduce(structure: Structure, eps: float = 1e-5) -> Structure:
    """Niggli-reduce the cell (shortest, most orthogonal basis)."""
    reduced = spglib.niggli_reduce(structure.lattice.matrix, eps=eps)
    if reduced is None:
        raise ValueError("Niggli reduction failed")
    return _rebasis(structure, reduced)


def delaunay_reduce(structure: Structure, eps: float = 1e-5
                    ) -> Structure:
    """Delaunay-reduce the cell."""
    reduced = spglib.delaunay_reduce(structure.lattice.matrix, eps=eps)
    if reduced is None:
        raise ValueError("Delaunay reduction failed")
    return _rebasis(structure, reduced)


def shift_origin(structure: Structure, shift) -> Structure:
    """Move the origin by ``shift`` (fractional): every atom moves by
    ``-shift``.  Keeps the space group, which is only meaningful for a
    shift the group allows -- re-detect if in doubt."""
    delta = np.asarray(shift, dtype=float).reshape(3)
    out = structure.copy()
    for s in out.sites:
        s.frac = p1._wrap(s.frac - delta)
    out.touch()
    return out


def wrap_into_cell(structure: Structure) -> Structure:
    """Copy with every site folded into [0, 1)."""
    out = structure.copy()
    out.wrap_sites()
    return out


def add_vacuum(structure: Structure, thickness: float,
               axis: int = 2) -> Structure:
    """Extend one axis by ``thickness`` Angstrom without moving the
    atoms in cartesian space -- the starting point for a slab."""
    if axis not in (0, 1, 2):
        raise ValueError("axis must be 0, 1 or 2")
    if thickness < 0:
        raise ValueError("vacuum thickness must be >= 0")
    matrix = np.array(structure.lattice.matrix, dtype=float)
    vec = matrix[axis]
    length = np.linalg.norm(vec)
    matrix[axis] = vec * (length + thickness) / length
    lattice = Lattice(matrix)

    cell = p1.expand(structure)
    cart = structure.lattice.to_cart(cell.frac)
    sites = []
    for k in range(cell.n_atoms):
        parent = structure.sites[int(cell.site_idx[k])]
        s = parent.copy()
        s.frac = lattice.to_frac(cart[k])
        s.label = ""
        sites.append(s)
    out = Structure(lattice=lattice, sites=sites,
                    space_group=SpaceGroup.p1(),
                    meta=dict(structure.meta))
    out.ensure_labels()
    return out
