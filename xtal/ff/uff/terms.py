"""
xtal.ff.uff.terms
=================
The UFF energy expressions and their analytic gradients.

One class per term of the force field.  Each holds the atoms it acts
on as index arrays and its parameters as parallel arrays, so a term
evaluates the whole crystal at once rather than a Python loop over
thousands of bonds.  Each one answers the same question --
``energy_and_gradient(positions, matrix)`` -> ``(E, dE/dx)`` -- and
every one of them is checked against a finite difference of its own
energy in the tests, which is the only way to be sure a gradient is
the gradient of the energy that was actually written.

**Everything is a function of a cosine.**  UFF's angle, torsion and
inversion terms are all naturally written in the angle itself, and
every one of them then has a 1/sin singularity at the geometry it is
most likely to meet -- a linear angle, a planar torsion.  Written in
cos(theta) instead, using the Chebyshev expansion of cos(n theta),
they are polynomials: smooth everywhere, no special cases, no atoms
flying apart when a nitrile passes through 180 degrees.

That removes the singularity from the *energy*.  It does not remove
the one underneath it: a torsion and an inversion both reach the
coordinates through a cross product, and going from the angle to the
atoms still divides by a sine.  Nothing rewrites that away, because a
dihedral about three collinear atoms genuinely does not exist -- so
those terms are dropped when the geometry is that degenerate, and
:data:`MIN_SINE` is where the line is drawn.

**Periodic images are carried, not recomputed.**  Every term stores an
integer lattice translation per participating atom, fixed when the
topology was built.  A bond that crosses a cell boundary is then just
a bond, and stays the same bond while the geometry moves under it.

Units: Angstrom, degrees on the way in, radians internally, kcal/mol
and kcal/mol/Angstrom out.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from xtal.core import elements as el
from xtal.ff.uff import params
from xtal.ff.uff.params import FORCE_CONSTANT, LAMBDA

# Below this the geometry is degenerate -- two atoms on top of each
# other, or three in a line where a plane was needed -- and the term
# has no defined direction.  Dropping it is right: the other terms
# still hold the atom, and a NaN would end the optimisation.
EPS = 1e-9

# The same idea for a torsion or an inversion, and it has to be a
# *sine* rather than a length.  Both of those terms reach the
# coordinates through a cross product, and the chain rule from the
# angle down to the atoms carries a 1/sin(theta) with it -- so an
# i-j-k that is straight does not merely have an undefined dihedral,
# it has an infinite derivative.  Testing |b1 x b2| against a small
# number instead tests an *area*, which is 1e-9 A^2 for two 2 A bonds
# at a millionth of a degree from straight: the term switches on with
# a gradient of thousands and the optimiser chases it forever.
#
# 1e-2 is sin(0.57 degrees).  A torsion that close to straight is not
# a torsion; dropping it costs at most one barrier, and keeping it
# costs the geometry.
MIN_SINE = 1e-2

# Group 16, which UFF singles out in the torsion rules.
GROUP_16 = frozenset({"O", "S", "Se", "Te", "Po"})
# The sp3 group-16 torsional barriers of eq 18: oxygen alone, then
# everything below it.
GROUP_16_BARRIER = {"O": 2.0}
GROUP_16_BARRIER_HEAVY = 6.8


# ======================================================================
#  PAIR PARAMETERS
# ======================================================================

def natural_bond_length(a: str, b: str, order: float = 1.0) -> float:
    """UFF's equilibrium bond length, eq 2-4.

        r_ij = r_i + r_j + r_BO - r_EN

    The bond-order term shortens a multiple bond; the electronegativity
    term shortens a polar one.  The paper prints the second with a plus
    sign, which is a known slip -- with it, C-H comes out at 1.113 A
    instead of the 1.109 the paper itself quotes, and every polar bond
    is too long.  Subtracted, the table's own worked examples come
    back.
    """
    pi, pj = params.get(a), params.get(b)
    total = pi.r1 + pj.r1
    r_bo = -LAMBDA * total * np.log(max(float(order), 1e-6))
    numerator = pi.r1 * pj.r1 * (np.sqrt(pi.chi) - np.sqrt(pj.chi)) ** 2
    r_en = numerator / (pi.chi * pi.r1 + pj.chi * pj.r1)
    return float(total + r_bo - r_en)


def bond_force_constant(a: str, b: str, r0: float) -> float:
    """UFF's bond force constant, eq 6: ``664.12 Z*_i Z*_j / r_ij^3``,
    in kcal/mol/Angstrom^2."""
    pi, pj = params.get(a), params.get(b)
    return float(FORCE_CONSTANT * pi.z1 * pj.z1 / r0 ** 3)


def vdw_pair(a: str, b: str) -> tuple[float, float]:
    """``(x_ij, D_ij)`` for the LJ 12-6 term -- geometric means of the
    two atoms' well positions and depths, eq 22."""
    pi, pj = params.get(a), params.get(b)
    return (float(np.sqrt(pi.x1 * pj.x1)),
            float(np.sqrt(pi.d1 * pj.d1)))


def hybridisation(type_name: str) -> str:
    """``"sp"``, ``"sp2"``, ``"sp3"`` or ``""`` for a type name.

    Read straight off the geometry character, which is what it is for.
    Anything without one -- a halogen, an octahedral metal -- has no
    hybridisation in the sense the torsion rules mean, and gets ``""``.
    """
    geometry = params.get(type_name).geometry
    return {"1": "sp", "2": "sp2", "R": "sp2", "3": "sp3"}.get(
        geometry, "")


# ======================================================================
#  A SHARED BASE
# ======================================================================

@dataclass
class Term:
    """Common shape: index arrays, parameter arrays, one answer."""

    def __len__(self) -> int:                   # pragma: no cover
        raise NotImplementedError

    def energy_and_gradient(self, positions, matrix):
        """``(energy, dE/dpositions)``.  ``matrix`` is the (3,3) cell,
        rows being the lattice vectors."""
        raise NotImplementedError               # pragma: no cover

    def energy(self, positions, matrix) -> float:
        return self.energy_and_gradient(positions, matrix)[0]


def _sine(cross_norm, u, v):
    """``sin(angle between u and v)``, from a cross product already
    taken.

    Both callers have the cross product in hand and want the angle it
    encodes without a second trigonometric step; dividing by the two
    lengths is what turns an area into the dimensionless quantity the
    degeneracy test needs.
    """
    lengths = (np.linalg.norm(u, axis=1) * np.linalg.norm(v, axis=1))
    return cross_norm / np.maximum(lengths, EPS)


#: Terms evaluated per pass.  A 5184-atom framework has half a million
#: van der Waals pairs, and evaluating them in one pass held some
#: fifteen (n, 3) temporaries at once -- 66 MB, every step.  In blocks
#: the transient is a few megabytes and the time is the same.
_TERM_BLOCK = 65536


def _blocks(n: int):
    """Slices covering ``range(n)``, ``_TERM_BLOCK`` at a time."""
    for start in range(0, n, _TERM_BLOCK):
        yield slice(start, min(start + _TERM_BLOCK, n))


def _scatter(grad, indices, values) -> None:
    """``grad[indices] += values``, with repeated indices accumulating.

    Plain fancy-index assignment silently keeps only the last write,
    and every atom here appears in many terms, so this is the whole
    correctness of the gradient.

    ``np.bincount`` and not ``np.add.at``, which is the obvious
    spelling and is unbuffered: it walks the index array one element
    at a time in Python-level C and was, on its own, forty-five
    percent of the time in a cell relaxation of MFU-4l.  One bincount
    per column does the same accumulation as a single vectorised pass
    and gives the identical answer -- the finite-difference gradient
    tests are what say so.
    """
    indices = np.asarray(indices)
    values = np.asarray(values, dtype=float)
    if not indices.size:
        return
    length = grad.shape[0]
    for axis in range(grad.shape[1]):
        grad[:, axis] += np.bincount(indices, weights=values[:, axis],
                                     minlength=length)


# ======================================================================
#  BOND STRETCH
# ======================================================================

@dataclass
class BondTerm(Term):
    """Harmonic stretch, eq 1a: ``E = 1/2 k (r - r0)^2``."""

    i: np.ndarray
    j: np.ndarray
    shift: np.ndarray               # lattice translation applied to j
    r0: np.ndarray
    k: np.ndarray

    def __len__(self) -> int:
        return len(self.i)

    def energy_and_gradient(self, positions, matrix):
        grad = np.zeros_like(positions)
        if not len(self):
            return 0.0, grad
        d = (positions[self.j] + self.shift @ matrix
             - positions[self.i])
        r = np.linalg.norm(d, axis=1)
        good = r > EPS
        delta = r - self.r0
        energy = float(0.5 * np.sum(self.k * delta ** 2))
        scale = np.where(good, self.k * delta / np.where(good, r, 1.0),
                         0.0)
        force = scale[:, None] * d
        _scatter(grad, self.j, force)
        _scatter(grad, self.i, -force)
        return energy, grad


# ======================================================================
#  ANGLE BEND
# ======================================================================

# How the cosine expansion is evaluated.  The general three-term form
# is what UFF uses for anything without a special geometry; the others
# are its periodic special cases (eq 12), where a single cosine of a
# multiple of the angle has the right minima and, unlike the general
# form, does not also invent a spurious one.
GENERAL, LINEAR, TRIGONAL, SQUARE = 0, 1, 3, 4


def angle_form(theta0_degrees: float) -> int:
    """Which expansion an equilibrium angle asks for."""
    for form, ideal in ((LINEAR, 180.0), (TRIGONAL, 120.0),
                        (SQUARE, 90.0)):
        if abs(theta0_degrees - ideal) < 1e-6:
            return form
    return GENERAL


def angle_force_constant(a: str, b: str, c: str, theta0: float,
                         order_ab: float = 1.0,
                         order_bc: float = 1.0) -> float:
    """UFF's angle force constant, eq 13.

    It is the second derivative of the energy at the equilibrium
    angle, and it is built out of the two bond lengths and the 1-3
    distance they imply -- so a wide angle between long bonds comes out
    soft without anyone having fitted it.
    """
    r_ab = natural_bond_length(a, b, order_ab)
    r_bc = natural_bond_length(b, c, order_bc)
    cos0 = np.cos(np.radians(theta0))
    r_ac2 = r_ab ** 2 + r_bc ** 2 - 2 * r_ab * r_bc * cos0
    r_ac = np.sqrt(r_ac2)
    za, zc = params.get(a).z1, params.get(c).z1
    return float(FORCE_CONSTANT * za * zc / r_ac ** 5
                 * (3 * r_ab * r_bc * (1 - cos0 ** 2)
                    - r_ac2 * cos0))


@dataclass
class AngleTerm(Term):
    """Bend about atom ``j``, in the two-term cosine expansion of eq 11
    or one of the periodic special cases of eq 12."""

    i: np.ndarray
    j: np.ndarray
    k: np.ndarray
    shift_i: np.ndarray             # translation applied to i
    shift_k: np.ndarray             # translation applied to k
    force: np.ndarray
    c0: np.ndarray
    c1: np.ndarray
    c2: np.ndarray
    form: np.ndarray                # GENERAL / LINEAR / TRIGONAL / ...

    def __len__(self) -> int:
        return len(self.j)

    def _energy_of_cos(self, c):
        """``(E, dE/dcos)``, one branch per expansion.

        Every branch is a polynomial in the cosine -- cos(n theta) is
        the Chebyshev polynomial T_n(cos theta) -- so a linear angle
        passing exactly through 180 degrees is an ordinary point and
        not a division by zero.
        """
        energy = np.zeros_like(c)
        derivative = np.zeros_like(c)

        general = self.form == GENERAL
        if general.any():
            cc = c[general]
            energy[general] = (self.c0[general]
                               + self.c1[general] * cc
                               + self.c2[general] * (2 * cc ** 2 - 1))
            derivative[general] = (self.c1[general]
                                   + 4 * self.c2[general] * cc)

        linear = self.form == LINEAR
        if linear.any():
            energy[linear] = 1.0 + c[linear]
            derivative[linear] = 1.0

        trigonal = self.form == TRIGONAL
        if trigonal.any():                      # (1 - cos 3t) / 9
            cc = c[trigonal]
            energy[trigonal] = (1.0 - (4 * cc ** 3 - 3 * cc)) / 9.0
            derivative[trigonal] = -(12 * cc ** 2 - 3) / 9.0

        square = self.form == SQUARE
        if square.any():                        # (1 - cos 4t) / 16
            cc = c[square]
            cos4 = 8 * cc ** 4 - 8 * cc ** 2 + 1
            energy[square] = (1.0 - cos4) / 16.0
            derivative[square] = -(32 * cc ** 3 - 16 * cc) / 16.0

        return self.force * energy, self.force * derivative

    def energy_and_gradient(self, positions, matrix):
        grad = np.zeros_like(positions)
        if not len(self):
            return 0.0, grad
        u = (positions[self.i] + self.shift_i @ matrix
             - positions[self.j])
        v = (positions[self.k] + self.shift_k @ matrix
             - positions[self.j])
        nu = np.linalg.norm(u, axis=1)
        nv = np.linalg.norm(v, axis=1)
        good = (nu > EPS) & (nv > EPS)
        safe_u = np.where(good, nu, 1.0)
        safe_v = np.where(good, nv, 1.0)
        cos = np.clip(np.einsum("ij,ij->i", u, v)
                      / (safe_u * safe_v), -1.0, 1.0)

        energies, dcos = self._energy_of_cos(cos)
        energy = float(np.sum(np.where(good, energies, 0.0)))
        dcos = np.where(good, dcos, 0.0)

        du = (v / (safe_u * safe_v)[:, None]
              - (cos / safe_u ** 2)[:, None] * u)
        dv = (u / (safe_u * safe_v)[:, None]
              - (cos / safe_v ** 2)[:, None] * v)
        gi = dcos[:, None] * du
        gk = dcos[:, None] * dv
        _scatter(grad, self.i, gi)
        _scatter(grad, self.k, gk)
        _scatter(grad, self.j, -(gi + gk))
        return energy, grad


# ======================================================================
#  TORSION
# ======================================================================

def torsion_parameters(type_j: str, type_k: str, order: float,
                       n_neighbors_j: int,
                       n_neighbors_k: int) -> tuple[float, int, float]:
    """``(barrier, periodicity, cos(n phi0))`` for a bond j-k, eq 16-18.

    UFF decides the whole torsion from the hybridisation of the two
    atoms *in the middle*, which is why this takes the bond and not the
    four atoms: every torsion about the same bond shares a barrier, and
    that barrier is then split between them.

    A barrier of zero means "no torsion here" -- around a bond to a
    metal, to a terminal atom, or to an sp centre, where a dihedral is
    either undefined or has nothing to say.
    """
    hj, hk = hybridisation(type_j), hybridisation(type_k)
    if hj not in ("sp2", "sp3") or hk not in ("sp2", "sp3"):
        return 0.0, 1, 1.0
    if n_neighbors_j < 2 or n_neighbors_k < 2:
        return 0.0, 1, 1.0

    pj, pk = params.get(type_j), params.get(type_k)
    ej, ek = pj.element, pk.element

    # The metal half of "no torsion here", which the hybridisation
    # test above does not catch.  UFF has one type per metal and names
    # it for the commonest geometry, so Zn3+2 says "tetrahedral" and
    # reads as sp3 -- and then MFU-4l's octahedral zinc, which is that
    # same type, collects torsions about every Zn-N bond.  They are
    # meaningless (a dihedral about a bond to a six-coordinate centre
    # says nothing) and they are where N-Zn-N sits at exactly 180
    # degrees, which is the one geometry the torsion gradient cannot
    # be written at.
    if el.element(ej).is_metal or el.element(ek).is_metal:
        return 0.0, 1, 1.0

    if hj == "sp3" and hk == "sp3":
        if ej in GROUP_16 and ek in GROUP_16:
            # Two group-16 sp3 centres: a 2-fold barrier with its
            # minimum at 90 degrees, which is what makes hydrogen
            # peroxide and the disulfide bridge come out skewed
            # instead of planar.
            vj = GROUP_16_BARRIER.get(ej, GROUP_16_BARRIER_HEAVY)
            vk = GROUP_16_BARRIER.get(ek, GROUP_16_BARRIER_HEAVY)
            return float(np.sqrt(vj * vk)), 2, -1.0
        return float(np.sqrt(pj.vi * pk.vi)), 3, -1.0

    if hj == "sp2" and hk == "sp2":
        barrier = 5.0 * np.sqrt(pj.uj * pk.uj) * (
            1.0 + 4.18 * np.log(max(float(order), 1e-6)))
        return float(barrier), 2, 1.0

    # sp2 against sp3.
    sp3_element = ej if hj == "sp3" else ek
    if sp3_element in GROUP_16:
        barrier = 5.0 * np.sqrt(pj.uj * pk.uj) * (
            1.0 + 4.18 * np.log(max(float(order), 1e-6)))
        return float(barrier), 2, -1.0
    return 1.0, 6, 1.0


@dataclass
class TorsionTerm(Term):
    """``E = V/2 [1 - cos(n phi0) cos(n phi)]``, eq 15.

    Written in cos(phi) through the Chebyshev expansion, so a torsion
    passing through planarity -- which is where the minima are -- costs
    nothing special.
    """

    i: np.ndarray
    j: np.ndarray
    k: np.ndarray
    l: np.ndarray
    shift_i: np.ndarray             # all translations are relative to j
    shift_k: np.ndarray
    shift_l: np.ndarray
    barrier: np.ndarray             # V, already split between torsions
    n: np.ndarray                   # periodicity, 2 / 3 / 6
    cos_n_phi0: np.ndarray          # +1 or -1

    def __len__(self) -> int:
        return len(self.j)

    @staticmethod
    def _chebyshev(c, n):
        """``(T_n(c), T_n'(c))`` for the three periodicities UFF
        uses."""
        value = np.zeros_like(c)
        slope = np.zeros_like(c)
        for order in (2, 3, 6):
            mask = n == order
            if not mask.any():
                continue
            cc = c[mask]
            if order == 2:
                value[mask] = 2 * cc ** 2 - 1
                slope[mask] = 4 * cc
            elif order == 3:
                value[mask] = 4 * cc ** 3 - 3 * cc
                slope[mask] = 12 * cc ** 2 - 3
            else:
                value[mask] = (32 * cc ** 6 - 48 * cc ** 4
                               + 18 * cc ** 2 - 1)
                slope[mask] = (192 * cc ** 5 - 192 * cc ** 3
                               + 36 * cc)
        return value, slope

    def energy_and_gradient(self, positions, matrix):
        grad = np.zeros_like(positions)
        energy = 0.0
        for part in _blocks(len(self)):
            energy += self._block(positions, matrix, grad, part)
        return energy, grad

    def _block(self, positions, matrix, grad, part) -> float:
        i, j, k, l = self.i[part], self.j[part], self.k[part], self.l[part]
        barrier = self.barrier[part]
        cos_n_phi0 = self.cos_n_phi0[part]
        pj = positions[j]
        pk = positions[k] + self.shift_k[part] @ matrix
        b1 = pj - (positions[i] + self.shift_i[part] @ matrix)
        b2 = pk - pj
        b3 = (positions[l] + self.shift_l[part] @ matrix) - pk

        n1 = np.cross(b1, b2)
        n2 = np.cross(b2, b3)
        m1 = np.linalg.norm(n1, axis=1)
        m2 = np.linalg.norm(n2, axis=1)
        # |b1 x b2| is |b1||b2| sin(theta_ijk), so the test that says
        # "this dihedral is defined" is on the sine and not on the
        # cross product itself -- see MIN_SINE.
        good = ((_sine(m1, b1, b2) > MIN_SINE)
                & (_sine(m2, b2, b3) > MIN_SINE))
        s1 = np.where(good, m1, 1.0)
        s2 = np.where(good, m2, 1.0)
        cos = np.clip(np.einsum("ij,ij->i", n1, n2) / (s1 * s2),
                      -1.0, 1.0)

        value, slope = self._chebyshev(cos, self.n[part])
        amplitude = 0.5 * barrier * cos_n_phi0
        energies = 0.5 * barrier - amplitude * value
        energy = float(np.sum(np.where(good, energies, 0.0)))
        dcos = np.where(good, -amplitude * slope, 0.0)

        w1 = (n2 / (s1 * s2)[:, None]
              - (cos / s1 ** 2)[:, None] * n1)
        w2 = (n1 / (s1 * s2)[:, None]
              - (cos / s2 ** 2)[:, None] * n2)
        # n1 = b1 x b2 and n2 = b2 x b3, so the derivative with
        # respect to each bond vector is a cross product with the
        # other one.
        db1 = np.cross(b2, w1)
        db2 = np.cross(w1, b1) + np.cross(b3, w2)
        db3 = np.cross(w2, b2)

        gi = -dcos[:, None] * db1
        gj = dcos[:, None] * (db1 - db2)
        gk = dcos[:, None] * (db2 - db3)
        gl = dcos[:, None] * db3
        _scatter(grad, i, gi)
        _scatter(grad, j, gj)
        _scatter(grad, k, gk)
        _scatter(grad, l, gl)
        return energy


# ======================================================================
#  INVERSION
# ======================================================================

# sp2 centres: a total barrier shared by the three inversions at the
# atom.  The large one is UFF's special case for a carbon carrying a
# carbonyl oxygen, where planarity is enforced much harder.
SP2_INVERSION = 6.0
SP2_INVERSION_WITH_O2 = 50.0
SP2_INVERSION_TYPES = frozenset({"C_2", "C_R", "N_2", "N_R",
                                 "O_2", "O_R"})
# Pyramidal group-15 centres: equilibrium out-of-plane angle in
# degrees, and the barrier, from the paper's discussion of eq 19.
GROUP_15_INVERSION = {
    "P_3+3": (84.4339, 22.0),
    "As3+3": (86.9735, 22.0),
    "Sb3+3": (87.7047, 22.0),
    "Bi3+3": (90.0000, 22.0),
}


def inversion_parameters(centre: str,
                         neighbours) -> tuple[float, float, float,
                                              float]:
    """``(K, C0, C1, C2)`` for one three-coordinate centre, eq 19.

    ``K`` is already divided by three: UFF gives the barrier for the
    centre, and each of its three neighbours takes a turn as the atom
    out of the plane.
    """
    if centre in SP2_INVERSION_TYPES:
        total = (SP2_INVERSION_WITH_O2 if "O_2" in neighbours
                 else SP2_INVERSION)
        return total / 3.0, 1.0, -1.0, 0.0
    if centre in GROUP_15_INVERSION:
        omega0, total = GROUP_15_INVERSION[centre]
        w = np.radians(omega0)
        c2 = 1.0
        c1 = -4.0 * np.cos(w)
        c0 = -(c1 * np.cos(w) + c2 * np.cos(2 * w))
        return total / 3.0, float(c0), float(c1), float(c2)
    return 0.0, 0.0, 0.0, 0.0


@dataclass
class InversionTerm(Term):
    """Out-of-plane bend at a three-coordinate centre, eq 19.

    ``omega`` is the angle between the bond to atom ``l`` and the plane
    of ``i``, ``j``, ``k`` -- zero when the centre is flat.  The energy
    is written in sin(omega), which is the quantity the geometry
    actually gives (the normal of the plane dotted into the bond), and
    cos(omega) and cos(2 omega) follow from it.
    """

    centre: np.ndarray
    j: np.ndarray
    k: np.ndarray
    l: np.ndarray
    shift_j: np.ndarray
    shift_k: np.ndarray
    shift_l: np.ndarray
    force: np.ndarray
    c0: np.ndarray
    c1: np.ndarray
    c2: np.ndarray

    def __len__(self) -> int:
        return len(self.centre)

    def energy_and_gradient(self, positions, matrix):
        grad = np.zeros_like(positions)
        if not len(self):
            return 0.0, grad
        origin = positions[self.centre]
        a = positions[self.j] + self.shift_j @ matrix - origin
        b = positions[self.k] + self.shift_k @ matrix - origin
        c = positions[self.l] + self.shift_l @ matrix - origin

        normal = np.cross(a, b)
        nn = np.linalg.norm(normal, axis=1)
        nc = np.linalg.norm(c, axis=1)
        # The plane has to be a plane: two collinear bonds give a
        # normal of length zero and a 1/|n| in the gradient, the same
        # trap the torsion has.
        good = (_sine(nn, a, b) > MIN_SINE) & (nc > EPS)
        sn = np.where(good, nn, 1.0)
        sc = np.where(good, nc, 1.0)
        sin = np.clip(np.einsum("ij,ij->i", normal, c) / (sn * sc),
                      -1.0, 1.0)

        # cos(omega) = sqrt(1 - sin^2); the square root is only ever
        # differentiated away from +-90 degrees, and a centre exactly
        # perpendicular to its own plane is caught by the guard.
        cos2 = np.clip(1.0 - sin ** 2, 0.0, 1.0)
        cos = np.sqrt(cos2)
        energies = (self.c0 + self.c1 * cos
                    + self.c2 * (2 * cos2 - 1))
        energy = float(np.sum(np.where(good, self.force * energies,
                                       0.0)))
        safe_cos = np.where(cos > EPS, cos, 1.0)
        dsin = self.force * (-self.c1 * sin / safe_cos
                             - 4 * self.c2 * sin)
        dsin = np.where(good & (cos > EPS), dsin, 0.0)

        # sin = (n . c) / (|n| |c|), with n = a x b.
        dn = (c / (sn * sc)[:, None] - (sin / sn ** 2)[:, None] * normal)
        dc = (normal / (sn * sc)[:, None] - (sin / sc ** 2)[:, None] * c)
        da = np.cross(b, dn)
        db = np.cross(dn, a)

        ga = dsin[:, None] * da
        gb = dsin[:, None] * db
        gc = dsin[:, None] * dc
        _scatter(grad, self.j, ga)
        _scatter(grad, self.k, gb)
        _scatter(grad, self.l, gc)
        _scatter(grad, self.centre, -(ga + gb + gc))
        return energy, grad


# ======================================================================
#  VAN DER WAALS
# ======================================================================

@dataclass
class VanDerWaalsTerm(Term):
    """Lennard-Jones 12-6, eq 20: ``E = D [(x/r)^12 - 2 (x/r)^6]``.

    The pair list is built once, with its periodic images, and reused
    while the geometry moves; the calculator rebuilds it when an atom
    has travelled far enough for the list to have gone stale.
    """

    i: np.ndarray
    j: np.ndarray
    shift: np.ndarray
    x: np.ndarray                   # well position, Angstrom
    d: np.ndarray                   # well depth, kcal/mol
    cutoff: float = 12.0
    # Energy at the cutoff, subtracted so the potential goes to zero
    # there.  Without it every rebuilt pair list moves the total energy
    # by a step, and an optimiser reads that step as progress.
    shift_energy: np.ndarray = field(default_factory=lambda:
                                     np.zeros(0))

    def __len__(self) -> int:
        return len(self.i)

    def energy_and_gradient(self, positions, matrix):
        grad = np.zeros_like(positions)
        energy = 0.0
        for part in _blocks(len(self)):
            energy += self._block(positions, matrix, grad, part)
        return energy, grad

    def _block(self, positions, matrix, grad, part) -> float:
        i, j = self.i[part], self.j[part]
        x, depth = self.x[part], self.d[part]
        d = positions[j] + self.shift[part] @ matrix - positions[i]
        r = np.linalg.norm(d, axis=1)
        inside = (r > EPS) & (r < self.cutoff)
        safe = np.where(inside, r, 1.0)
        ratio6 = (x / safe) ** 6
        ratio12 = ratio6 ** 2
        energies = depth * (ratio12 - 2.0 * ratio6)
        if len(self.shift_energy):
            energies = energies - self.shift_energy[part]
        energy = float(np.sum(np.where(inside, energies, 0.0)))
        scale = np.where(inside,
                         12.0 * depth * (ratio6 - ratio12) / safe ** 2,
                         0.0)
        force = scale[:, None] * d
        _scatter(grad, j, force)
        _scatter(grad, i, -force)
        return energy


# ======================================================================
#  ELECTROSTATICS (real space, for a finite cutoff)
# ======================================================================

@dataclass
class CoulombTerm(Term):
    """Point charges, eq 21, over an explicit pair list.

    Under periodic boundary conditions this is the wrong answer on its
    own -- the sum is only conditionally convergent -- and the
    calculator reaches for :mod:`xtal.ff.ewald` instead.  This is what
    runs for a molecule in a box big enough that periodicity is a
    fiction, and what the Ewald real-space part is checked against.
    """

    i: np.ndarray
    j: np.ndarray
    shift: np.ndarray
    qq: np.ndarray                  # q_i q_j, already multiplied
    dielectric: float = 1.0
    cutoff: float = 12.0

    def __len__(self) -> int:
        return len(self.i)

    def energy_and_gradient(self, positions, matrix):
        grad = np.zeros_like(positions)
        if not len(self):
            return 0.0, grad
        d = (positions[self.j] + self.shift @ matrix
             - positions[self.i])
        r = np.linalg.norm(d, axis=1)
        inside = (r > EPS) & (r < self.cutoff)
        safe = np.where(inside, r, 1.0)
        prefactor = params.COULOMB / self.dielectric
        energies = prefactor * self.qq / safe
        energy = float(np.sum(np.where(inside, energies, 0.0)))
        scale = np.where(inside, -prefactor * self.qq / safe ** 3, 0.0)
        force = scale[:, None] * d
        _scatter(grad, self.j, force)
        _scatter(grad, self.i, -force)
        return energy, grad
