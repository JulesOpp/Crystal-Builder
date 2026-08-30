"""
xtal.ff.uff.qeq
===============
Charge equilibration -- charges from the geometry, when the file does
not carry any.

QEq (Rappe and Goddard, *J. Phys. Chem.* **1991**, 95, 3358) says that
charge flows between atoms until every atom has the same
electronegativity, subject to the whole system staying neutral.  Write
the energy as

    E(Q) = sum_i (chi_i Q_i + 1/2 J_ii Q_i^2)
         + sum_{i<j} J_ij(r_ij) Q_i Q_j

and the condition is that every ``dE/dQ_i`` is equal.  That is a linear
system, and its solution is the charges.

**What this is not.**  The paper computes ``J_ij(r)`` as the Coulomb
integral between two Slater orbitals, with a further charge-dependent
correction for hydrogen.  Here ``J_ij`` is the Ohno-Klopman shielded
form, which has the same two limits that matter -- it tends to the
combined hardness as the atoms merge and to a bare ``1/r`` when they
separate -- but is not the same function in between.  Charges from it
are close to QEq's and are meant as a starting point the user can look
at and edit, not as a published result.  The Force Field panel says so
where it offers them.

Charges are in units of e; chi and J are in eV, which is what the
parameter table stores.
"""

from __future__ import annotations

import itertools

import numpy as np

from xtal.core import neighbors
from xtal.ff.uff import params

# e^2 / (4 pi eps0) in eV Angstrom -- the unit that makes chi and J,
# which are in eV, and r, which is in Angstrom, work together.
COULOMB_EV = 14.399645

# Above this the dense N x N system is the wrong tool and the wait
# would be measured in minutes.  Refusing is better than appearing to
# hang.
MAX_ATOMS = 2000

# UFF's table stores *half* the QEq idempotential: its ``Hard`` column
# is 6.9452 for hydrogen where the QEq paper's J is 13.8904, 5.063 for
# carbon where QEq's is 10.126, and so on for every element checked.
# The table is written for the energy as ``chi Q + Hard Q^2``, whose
# second derivative is 2 Hard.  Using the column as J directly halves
# every diagonal, leaves the matrix nearly singular against its own
# off-diagonals, and hands back charges of several electrons per atom.
HARDNESS_TO_J = 2.0


def equilibrate(cell, types, cutoff: float = 12.0,
                total_charge: float = 0.0) -> tuple[np.ndarray, str]:
    """``(charges, note)`` for a P1 cell.

    ``note`` is the caveat to show beside the numbers.  There is always
    one: these are an approximation to QEq and the panel should never
    present them as anything else.
    """
    n = cell.n_atoms
    if n == 0:
        return np.zeros(0), ""
    if n > MAX_ATOMS:
        raise ValueError(
            f"charge equilibration solves a dense {n} x {n} system; "
            f"this cell is too big for it. Set charges on the sites "
            f"instead, or turn electrostatics off")

    chi = np.array([params.get(t).chi for t in types])
    hardness = HARDNESS_TO_J * np.array(
        [params.get(t).hard for t in types])
    coulomb = _interaction_matrix(cell, hardness, cutoff)

    charges = _solve(chi, coulomb, total_charge)
    note = ("equilibrated charges use a shielded Coulomb integral in "
            "place of QEq's Slater integrals; treat them as an "
            "estimate to look over, not a published result")
    if "H_" in types:
        note += (". Hydrogen has no charge-dependent hardness here, "
                 "which is what keeps QEq's O-H and C-H charges "
                 "smaller than these")
    return charges, note


def _interaction_matrix(cell, hardness, cutoff: float) -> np.ndarray:
    """``J_ij``, summed over the periodic images inside ``cutoff``.

    The diagonal is the atom's own hardness.  Off it, the shielded
    integral is summed over every image of ``j``, because in a small
    cell an atom sees several copies of its neighbour and each of them
    is a real interaction.
    """
    combined = np.sqrt(np.outer(hardness, hardness))
    # The distance at which the shielded form crosses over from
    # hardness to 1/r, per pair.
    screening = COULOMB_EV / np.maximum(combined, 1e-6)

    matrix = np.diag(hardness).astype(float)
    lattice = cell.lattice
    cart = cell.cart
    na, nb, nc = neighbors.image_range(lattice, cutoff)
    shifts = np.array(list(itertools.product(
        range(-na, na + 1), range(-nb, nb + 1), range(-nc, nc + 1))),
        dtype=float)

    for shift in shifts:
        offset = shift @ lattice.matrix
        d = cart[None, :, :] + offset - cart[:, None, :]
        r = np.linalg.norm(d, axis=2)
        contribution = COULOMB_EV / np.sqrt(r ** 2 + screening ** 2)
        contribution[r > cutoff] = 0.0
        if not shift.any():
            np.fill_diagonal(contribution, 0.0)
        matrix = matrix + contribution
    return matrix


def _solve(chi, coulomb, total_charge: float) -> np.ndarray:
    """Every atom at the same electronegativity, total charge fixed.

    Rows are differences between successive atoms -- "these two have
    equal electronegativity" -- and the last row is the constraint.
    Written that way the system is square and needs no Lagrange
    multiplier, and the multiplier (the system's electronegativity) is
    not something anyone asks for.
    """
    n = len(chi)
    if n == 1:
        return np.array([total_charge])

    left = np.zeros((n, n))
    right = np.zeros(n)
    left[:n - 1] = coulomb[:n - 1] - coulomb[1:]
    right[:n - 1] = -(chi[:n - 1] - chi[1:])
    left[n - 1] = 1.0
    right[n - 1] = total_charge
    return np.linalg.solve(left, right)
