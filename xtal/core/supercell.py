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

# Two generated positions closer than this (in Angstrom) are the same
# atom, written twice.  **Cartesian, and not 1e-6 fractional**, which
# is what this used to be and what made a real deposited structure come
# out with the wrong number of atoms: coordinates written to six
# decimals in a 31 A cell carry a rounding of about 1e-3 A, and a
# change of basis spreads that over several components -- so images
# that are the same atom land 4e-5 apart in fractional terms and a 1e-6
# comparison calls them different.  A hundredth of an Angstrom is two
# orders of magnitude below the shortest real interatomic distance and
# two above the noise, which is the gap this has to sit in.
POSITION_TOL = 0.01


def _unique_positions(frac, lattice, tol: float = POSITION_TOL):
    """Indices of the distinct atoms among ``frac``, comparing across
    the periodic boundary and in Angstrom.

    Two things this has to get right, and the obvious loop gets neither:
    a position at 0.999999 and one at 0.000001 are the same point, and
    an O(N^2) scan of ``np.allclose`` over the fifty thousand candidate
    images a change of basis generates is where a large structure stops
    responding.  A periodic KD-tree does both -- ``boxsize`` makes the
    wrap free, and the pair query is the only part that grows.
    """
    from scipy.spatial import cKDTree

    points = np.mod(np.asarray(frac, dtype=float), 1.0)
    # np.mod can return exactly 1.0 for a small negative input, which a
    # periodic tree rejects as outside the box.
    points[points >= 1.0] = 0.0
    if len(points) < 2:
        return np.arange(len(points))

    # A fractional radius that is ``tol`` Angstrom along the shortest
    # cell edge: isotropic in fractional space, so it is never smaller
    # than ``tol`` in any direction and at worst slightly generous in
    # the long ones.
    shortest = float(np.min(np.linalg.norm(lattice.matrix, axis=1)))
    radius = tol / shortest

    tree = cKDTree(points, boxsize=1.0)
    keep = np.ones(len(points), dtype=bool)
    for i, j in tree.query_pairs(radius, output_type="ndarray"):
        keep[max(int(i), int(j))] = False
    return np.flatnonzero(keep)


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

    lattice, sites, found = _fill_new_cell(structure, p_arr)
    expected = p1.expand(structure).n_atoms * multiplier
    if found != expected:
        raise ValueError(
            f"cell transformation produced {found} atoms, "
            f"expected {expected} -- the matrix is probably not a "
            f"valid lattice transformation")

    out = Structure(lattice=lattice, sites=sites,
                    space_group=SpaceGroup.p1(),
                    bond_rules=dict(structure.bond_rules),
                    meta=dict(structure.meta))
    out.ensure_labels()
    return out


def _fill_new_cell(structure: Structure, basis, origin_shift=None):
    """``(lattice, sites, count)`` for the crystal re-expressed on a new
    basis.

    The crystal is the parent cell plus every lattice translation, so
    filling a new cell means generating each atom under every old
    translation that can reach inside it and then keeping the distinct
    ones.  Both halves are done for all atoms at once: the candidate
    set for a 648-atom framework is fifty thousand positions, and
    growing a Python list while comparing each new position against
    every position already in it is quadratic in exactly the case that
    matters.
    """
    b = np.asarray(basis, dtype=float)
    shift = (np.zeros(3) if origin_shift is None
             else np.asarray(origin_shift, dtype=float).reshape(3))
    lattice = structure.lattice.transform(b)
    inv_b = np.linalg.inv(b)
    cell = p1.expand(structure)

    # Old-lattice translations that can land inside the new cell: the
    # bounding box of the new cell's corners, expressed in old units.
    corners = np.array(list(itertools.product((0, 1), repeat=3)),
                       dtype=float) @ b
    lo = np.floor(corners.min(axis=0)).astype(int) - 1
    hi = np.ceil(corners.max(axis=0)).astype(int) + 1
    shifts = np.array(list(itertools.product(
        range(lo[0], hi[0] + 1), range(lo[1], hi[1] + 1),
        range(lo[2], hi[2] + 1))), dtype=float)

    # Most of those translations are the *same* translation once the
    # new cell is divided out -- a face-centring vector and the lattice
    # vector twice it land on each other -- and generating an atom for
    # each of them is how a 648-atom framework turns eighty translations
    # into fifty thousand candidate positions that then have to be
    # compared with one another.  Reduce them first: what matters is
    # the distinct values of ``n . inv(basis)`` modulo one, of which
    # there are a handful.
    cosets = p1._wrap(shifts @ inv_b)
    cosets = cosets[_unique_positions(cosets, lattice)]

    moved = ((cell.frac - shift) @ inv_b)[:, None, :] + cosets[None]
    candidates = p1._wrap(moved.reshape(-1, 3))
    parents = np.repeat(np.arange(cell.n_atoms), len(cosets))

    keep = _unique_positions(candidates, lattice)
    sites = []
    for k in keep:
        parent = structure.sites[int(cell.site_idx[int(parents[k])])]
        s = parent.copy()
        s.frac = candidates[k]
        s.label = ""
        s.wyckoff = None
        sites.append(s)
    return lattice, sites, len(sites)


def change_setting(structure: Structure, basis, origin_shift=None
                   ) -> Structure:
    """Re-express a structure in another setting of the same lattice.

    The general form of :func:`transform_cell`: ``basis`` may be
    rational rather than integer, and the origin may move.  Rows of
    ``basis`` are the new lattice vectors in units of the old ones, so

        new lattice = basis @ old lattice
        x_new       = (x_old - origin_shift) @ inv(basis)

    and the new cell may hold more atoms than the old one (a
    rhombohedral cell described on hexagonal axes holds three times as
    many) or fewer (a body-centred tetragonal cell inside a
    face-centred cubic one holds half).  Either way the *crystal* is
    unchanged: every atom keeps its cartesian position, and the count
    comes out as the volume ratio demands or the transformation is
    rejected.

    This is what descending to a subgroup needs, because a subgroup's
    standard setting is generally not the parent's basis -- and it is
    also the reason the descent can be offered under a name at all.
    """
    b = np.asarray(basis, dtype=float)
    if b.shape != (3, 3):
        raise ValueError("basis must be 3x3")
    ratio = float(np.linalg.det(b))
    if ratio <= 1e-9:
        raise ValueError(
            f"basis determinant must be positive, got {ratio:g}")
    shift = (np.zeros(3) if origin_shift is None
             else np.asarray(origin_shift, dtype=float).reshape(3))

    lattice, sites, found = _fill_new_cell(structure, b, shift)

    expected = int(round(p1.expand(structure).n_atoms * ratio))
    if found != expected:
        raise ValueError(
            f"changing setting produced {found} atoms, expected "
            f"{expected} -- the basis is not a transformation of this "
            f"lattice")

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
