"""
xtal.ff.ewald
=============
Coulomb energy and forces under periodic boundary conditions.

A lattice sum of 1/r is only conditionally convergent: add the charges
up in a different order and you get a different answer, and truncating
at a cutoff gives an answer that depends on the cutoff rather than on
the crystal.  Ewald's trick splits each point charge into a screened
part that converges quickly in real space and a smooth part that
converges quickly in reciprocal space, and the sum of the two is the
lattice sum -- unambiguously, and to whatever accuracy is asked for.

Four pieces, and all four are needed:

* **real space** -- ``q_i q_j erfc(alpha r) / r`` over neighbours
  inside the cutoff;
* **reciprocal space** -- a sum over lattice vectors k of the structure
  factor;
* **self energy** -- each charge interacting with its own screening
  cloud, subtracted;
* **the background** -- a cell with a net charge is infinitely
  repulsive, so a uniform neutralising background is assumed and its
  energy removed.  A structure whose charges do not sum to zero gets an
  answer that is well defined rather than infinite, and the caller is
  told that is what happened.

Bonded pairs are excluded by subtracting their *full* interaction:
they are in the reciprocal sum whether they belong there or not, and
subtracting ``erf(alpha r)/r`` is what takes them back out again.

Energies are kcal/mol, positions Angstrom, charges in units of e.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np
from scipy.special import erf, erfc

from xtal.ff.uff.params import COULOMB

# Target relative accuracy of the split.  Both cutoffs are derived
# from it, so one number controls the cost and the error together.
DEFAULT_ACCURACY = 1e-6
DEFAULT_REAL_CUTOFF = 12.0


@dataclass(frozen=True)
class EwaldSetup:
    """The split, chosen once for a cell and reused."""

    alpha: float                # screening width, 1/Angstrom
    real_cutoff: float          # Angstrom
    k_vectors: np.ndarray       # (K,3) cartesian, 2 pi / Angstrom
    k_factor: np.ndarray        # (K,) exp(-k^2/4 alpha^2) / k^2
    volume: float

    @property
    def n_k(self) -> int:
        return len(self.k_vectors)


def setup(matrix, real_cutoff: float = DEFAULT_REAL_CUTOFF,
          accuracy: float = DEFAULT_ACCURACY) -> EwaldSetup:
    """Choose alpha and the reciprocal vectors for a cell.

    ``alpha`` follows from the real-space cutoff and the accuracy
    asked for; the reciprocal cutoff then follows from ``alpha``.  A
    caller who halves the real cutoff gets a wider screening and more
    k-vectors, and the same answer -- which is the property worth
    having, and the one the tests check.
    """
    matrix = np.asarray(matrix, dtype=float)
    volume = abs(float(np.linalg.det(matrix)))
    if volume <= 0:
        raise ValueError("the cell has no volume")

    tolerance = np.sqrt(abs(np.log(accuracy)))
    alpha = tolerance / real_cutoff
    k_cutoff = 2.0 * alpha * np.sqrt(abs(np.log(accuracy)))

    # Rows of the reciprocal matrix are b1, b2, b3 with the 2 pi in.
    reciprocal = 2.0 * np.pi * np.linalg.inv(matrix)
    lengths = np.linalg.norm(reciprocal, axis=0)
    limits = np.maximum(1, np.ceil(k_cutoff / lengths).astype(int))

    indices = np.array(list(itertools.product(
        *(range(-n, n + 1) for n in limits))))
    vectors = indices @ reciprocal.T
    k2 = np.einsum("ij,ij->i", vectors, vectors)
    keep = (k2 > 1e-12) & (k2 < k_cutoff ** 2)
    vectors, k2 = vectors[keep], k2[keep]
    factor = np.exp(-k2 / (4.0 * alpha ** 2)) / k2
    return EwaldSetup(float(alpha), float(real_cutoff), vectors,
                      factor, volume)


def energy_and_gradient(positions, matrix, charges, pairs,
                        excluded=None, setup_=None,
                        dielectric: float = 1.0):
    """``(energy, dE/dpositions)`` for a periodic set of charges.

    ``pairs`` is ``(i, j, shift)`` from :mod:`xtal.core.neighbors`,
    already cut off at ``setup_.real_cutoff``, **with the excluded
    pairs left out of it**.  ``excluded`` names those pairs separately,
    and they are handled by subtracting ``erf(alpha r) / r``: leaving a
    pair out of the real-space sum removes ``erfc(alpha r) / r``, and
    the two together are the whole ``1/r`` the reciprocal sum put in
    for a pair that has no business being there.

    Passing an excluded pair in both lists therefore counts it twice
    and is a caller error, not something to correct for here.
    """
    positions = np.asarray(positions, dtype=float)
    matrix = np.asarray(matrix, dtype=float)
    charges = np.asarray(charges, dtype=float)
    conf = setup_ or setup(matrix)
    prefactor = COULOMB / dielectric

    energy = 0.0
    grad = np.zeros_like(positions)

    energy += _real_space(positions, matrix, charges, pairs, conf,
                          grad, prefactor, erfc)
    if excluded is not None and len(excluded[0]):
        # The same sum with erf instead of erfc and a negated
        # prefactor, so both the energy and the gradient come back out
        # together.
        energy += _real_space(positions, matrix, charges, excluded,
                              conf, grad, -prefactor, erf)
    energy += _reciprocal(positions, charges, conf, grad, prefactor)
    energy += _self_and_background(charges, conf, prefactor)
    return energy, grad


def _real_space(positions, matrix, charges, pairs, conf, grad,
                prefactor, kernel) -> float:
    i, j, shift = pairs
    if not len(i):
        return 0.0
    d = positions[j] + np.asarray(shift, dtype=float) @ matrix \
        - positions[i]
    r = np.linalg.norm(d, axis=1)
    good = r > 1e-9
    safe = np.where(good, r, 1.0)
    qq = charges[i] * charges[j]
    screened = kernel(conf.alpha * safe)
    energies = prefactor * qq * screened / safe
    energy = float(np.sum(np.where(good, energies, 0.0)))

    # d/dr [k(a r)/r] with k = erfc is -(erfc/r^2 + 2a/sqrt(pi)
    # exp(-a^2 r^2)/r); with k = erf the exponential term flips sign,
    # because erf' = -erfc'.
    gauss = (2.0 * conf.alpha / np.sqrt(np.pi)
             * np.exp(-(conf.alpha * safe) ** 2))
    sign = 1.0 if kernel is erfc else -1.0
    derivative = -(screened / safe ** 2 + sign * gauss / safe)
    scale = np.where(good, prefactor * qq * derivative / safe, 0.0)
    force = scale[:, None] * d
    np.add.at(grad, j, force)
    np.add.at(grad, i, -force)
    return energy


def _reciprocal(positions, charges, conf, grad, prefactor) -> float:
    if not conf.n_k:
        return 0.0                              # pragma: no cover
    phase = positions @ conf.k_vectors.T         # (N, K)
    structure = charges @ np.exp(1j * phase)     # (K,)
    weight = 2.0 * np.pi / conf.volume * conf.k_factor
    energy = float(prefactor * np.sum(weight * np.abs(structure) ** 2))

    # d|S|^2/dr_i = -2 q_i k Im(exp(i k.r_i) conj(S))
    inner = np.exp(1j * phase) * np.conj(structure)[None, :]
    coefficient = -2.0 * charges[:, None] * np.imag(inner) * weight
    grad += prefactor * (coefficient @ conf.k_vectors)
    return energy


def _self_and_background(charges, conf, prefactor) -> float:
    """Neither term moves an atom, so neither has a gradient -- but
    both change the energy, and the background term is the difference
    between a defined number and an infinite one for a cell that is
    not charge balanced."""
    self_energy = (-conf.alpha / np.sqrt(np.pi)
                   * float(np.sum(charges ** 2)))
    net = float(np.sum(charges))
    background = -np.pi * net ** 2 / (2.0 * conf.alpha ** 2
                                      * conf.volume)
    return prefactor * (self_energy + background)


def madelung(positions, matrix, charges, pairs, setup_=None) -> float:
    """The Madelung energy per formula unit in units of e^2/(4 pi eps0
    r), for checking the sum against a textbook constant."""
    energy, _grad = energy_and_gradient(positions, matrix, charges,
                                        pairs, setup_=setup_)
    return energy / COULOMB
