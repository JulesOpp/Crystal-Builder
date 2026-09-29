"""
xtal.core.slab
==============
A slab cut along a lattice plane (hkl), with vacuum above it.

**The surface cell is the plane's own lattice.**  :func:`surface_basis`
finds two integer vectors spanning (hkl) and a third that climbs one
interplanar spacing, as a unimodular basis of the crystal's lattice --
so a layer is one d(hkl) and holds exactly the atoms of one cell.  The
slab is ``layers`` of them, its *c* is then turned to the plane normal
(which moves no atom: only which in-plane copy of an atom is the one
in the cell), and the vacuum is added above.

**The bonds are carried, never perceived.**  The structure is flattened
with its graph written down (:func:`~xtal.core.bonding.flat_with_graph`)
and every bond -- the stored graph, the explicit ones with their orders,
the suppressions, the net edges -- is taken to each copy of its first
atom in the slab and kept exactly when its partner is in the slab too.
A bond the cut severs has no partner and is gone; that is the cut, and
it is counted.  Perceiving the slab afresh would re-bond whatever the
user had taken away, which is what Recalculate Bonds is for.

The cut atoms are left as they are.  Capping them is chemistry, and
Add hydrogens is the user's call.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import gcd

import numpy as np

from xtal.core import bonding, elements, p1
from xtal.core.lattice import Lattice
from xtal.core.spacegroup import SpaceGroup
from xtal.core.structure import Structure

#: How far above the bottom of the cell the slab starts, in Angstrom.
SLAB_FLOOR = 0.5


@dataclass(frozen=True)
class Slab:
    """A slab and what it took to make it."""

    structure: Structure
    hkl: tuple[int, int, int]
    layers: int
    thickness: float            # Angstrom, layers x d(hkl)
    vacuum: float               # Angstrom above the slab
    cut: int                    # chemical bonds the surfaces severed


def surface_basis(hkl) -> np.ndarray:
    """Rows ``v1, v2, v3``: an integer basis of the lattice with
    ``v1`` and ``v2`` in the plane (hkl) and ``h . v3 = 1``.

    Unimodular and right-handed (determinant +1), so it is the same
    lattice on another basis.  A common factor is divided out: (220)
    is the (110) plane, and a layer is one spacing of it.
    """
    h = [int(v) for v in hkl]
    if len(h) != 3 or not any(h):
        raise ValueError("a plane needs a Miller index that is not "
                         "(0 0 0)")
    g = gcd(gcd(abs(h[0]), abs(h[1])), abs(h[2]))
    r = [v // g for v in h]

    # Column operations on the row h, carried into Q, until one entry
    # is left: Euclid on the three of them at once.
    q = np.eye(3, dtype=int)
    while sum(1 for v in r if v) > 1:
        pivot = min((k for k in range(3) if r[k]), key=lambda k: abs(r[k]))
        for k in range(3):
            if k != pivot and r[k]:
                m = r[k] // r[pivot]
                r[k] -= m * r[pivot]
                q[:, k] -= m * q[:, pivot]
    last = next(k for k in range(3) if r[k])
    if r[last] < 0:
        q[:, last] = -q[:, last]
    order = [k for k in range(3) if k != last] + [last]
    basis = q[:, order].T.copy()
    if round(np.linalg.det(basis)) < 0:
        basis[0] = -basis[0]
    return basis


def _reduce_in_plane(basis, matrix) -> np.ndarray:
    """``v1`` and ``v2`` made as short and as square as the plane
    allows (Gauss), keeping the determinant +1."""
    out = np.array(basis, dtype=int)
    metric = np.asarray(matrix, float) @ np.asarray(matrix, float).T

    def dot(u, v):
        return float(u @ metric @ v)

    for _ in range(100):
        v1, v2 = out[0].copy(), out[1].copy()
        if dot(v1, v1) > dot(v2, v2):
            v1, v2 = v2, v1
        mu = int(round(dot(v1, v2) / dot(v1, v1)))
        v2 = v2 - mu * v1
        out[0], out[1] = v1, v2
        if mu == 0 and dot(v1, v1) <= dot(v2, v2):
            break
    if round(np.linalg.det(out)) < 0:
        out[1] = -out[1]
    return out


def make_slab(structure: Structure, hkl, layers: int = 1,
              vacuum: float = 15.0, shift: float = 0.0) -> Slab:
    """``layers`` spacings of (hkl), with ``vacuum`` Angstrom above.

    ``shift`` moves the cut up the normal by that fraction of one
    layer, which is how a different termination is chosen.
    """
    layers = int(layers)
    if layers < 1:
        raise ValueError("a slab needs at least one layer")
    if vacuum < 0:
        raise ValueError("the vacuum cannot be negative")
    h = tuple(int(v) for v in hkl)
    one = bonding.flat_with_graph(structure)
    n = one.n_sites
    if not n:
        raise ValueError("there are no atoms to cut a slab from")
    matrix = np.asarray(one.lattice.matrix, dtype=float)
    basis = _reduce_in_plane(surface_basis(h), matrix)
    inverse = np.linalg.inv(basis)

    # Every atom in units of the surface basis: one layer is 1 along
    # the third.  ``whole`` is how far each is from its copy in the
    # first layer's cell.
    y = (one.frac - float(shift) * basis[2]) @ inverse
    whole = np.floor(y + 1e-9).astype(int)
    first = y - whole

    # c turned to the normal: the in-plane part of c comes off, and a
    # coordinate climbing c picks up that much of a and b.
    a, b, c = basis.astype(float) @ matrix
    normal = np.cross(a, b)
    normal /= np.linalg.norm(normal)
    rise = float(c @ normal)
    along = np.linalg.lstsq(np.array([a, b]).T, c - rise * normal,
                            rcond=None)[0]
    thickness = abs(rise) * layers
    height = thickness + float(vacuum)
    # Off the floor, by a little of the vacuum.  The cut plane passes
    # through atoms, and an atom on the face of the cell is drawn at
    # both faces -- the bottom layer again at the top of the vacuum.
    # Moving the origin is free: the gap between one slab and the
    # next is the vacuum asked for either way.
    floor = min(SLAB_FLOOR, float(vacuum) / 2) / height
    lattice = Lattice(np.array([a, b, normal * np.sign(rise) * height]))

    def place(k, m):
        """``(frac, in-plane cell)`` of atom ``k``'s copy in layer
        ``m``: its coordinate on the slab's lattice, and the whole
        cells folding it into the first one took off."""
        z = first[k, 2] + m
        plane = first[k, :2] + along * z
        cell = np.floor(plane + 1e-9).astype(int)
        return (np.array([*(plane - cell),
                          floor + z * abs(rise) / height]), cell)

    sites, cells = [], {}
    for m in range(layers):
        for k in range(n):
            frac, cell = place(k, m)
            site = one.sites[k].copy()
            site.frac = frac
            site.label = ""
            site.wyckoff = None
            sites.append(site)
            cells[(k, m)] = cell

    def carried(i, j, image, m):
        """``(i', j', image')`` for the copy of the bond ``i`` to
        ``j + image`` whose first atom is in layer ``m``, or ``None``
        when its partner is not in the slab.

        In surface units the partner is ``step`` whole cells from
        where ``j`` sits in the first layer: in-plane whole cells are
        the slab's own, and the third says which layer.
        """
        step = np.round(whole[j] - whole[i]
                        + np.asarray(image, dtype=float) @ inverse
                        ).astype(int)
        mj = m + int(step[2])
        if not 0 <= mj < layers:
            return None
        offset = step[:2] + cells[(j, mj)] - cells[(i, m)]
        return (m * n + i, mj * n + j,
                (int(offset[0]), int(offset[1]), 0))

    bonds = []
    for bond in one.bonds:
        for m in range(layers):
            moved = carried(bond.i, bond.j, bond.image, m)
            if moved is not None:
                i, j, image = moved
                bonds.append(replace(bond, i=i, j=j, image=image))

    stored = one.perceived
    zero = np.zeros((n, 3), dtype=int)
    base = bonding.rebase(stored.bonds, stored.tau, zero)
    dummy = [elements.is_dummy(site.element) for site in one.sites]
    perceived, cut = [], 0
    for bond in base:
        chemical = not (dummy[bond.i] or dummy[bond.j])
        back = tuple(-v for v in bond.image)
        for m in range(layers):
            moved = carried(bond.i, bond.j, bond.image, m)
            if moved is None:
                cut += chemical
            else:
                i, j, image = moved
                perceived.append(replace(bond, i=i, j=j, image=image))
            if chemical and carried(bond.j, bond.i, back, m) is None:
                cut += 1

    out = Structure(lattice=lattice, sites=sites,
                    space_group=SpaceGroup.p1(), bonds=bonds,
                    bond_rules=dict(one.bond_rules),
                    meta=dict(one.meta))
    out.ensure_labels()
    cell = p1.expand(out)
    out.set_perceived(
        bonding.rebase(perceived, np.zeros((len(sites), 3), dtype=int),
                       cell.tau),
        stored.signature, cell)
    g = gcd(gcd(abs(h[0]), abs(h[1])), abs(h[2]))
    return Slab(out, tuple(v // g for v in h), layers, thickness,
                float(vacuum), cut)
