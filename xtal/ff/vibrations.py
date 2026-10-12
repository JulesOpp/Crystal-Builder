"""
xtal.ff.vibrations
==================
Vibrational frequencies at Gamma, by finite differences of forces.

Every engine answers :meth:`Calculator.compute` with forces, so a
Hessian built from them works under UFF, xTB, MACE, ORB-v3 and
MatterSim without any of them knowing: each free atom is moved
``delta`` both ways along each axis, ``6 x free`` evaluations and one
more at the reference, and a column is the central difference of the
forces.  It is symmetrised, mass-weighted and diagonalised.  phonopy
(:mod:`xtal.ff.phonons`) does the same with fewer displacements where
the crystal has symmetry, and a q-mesh; this path needs nothing, can
hold atoms still, and is what a molecule always uses.

**The rigid motions are projected out, not left to finite
differences.**  A crystal's three uniform translations are zero
exactly (the acoustic sum rule); a molecule's three rotations are too.
Differences put a relaxed molecule's rotations tens of wavenumbers
either side of zero -- CO2 gave -39 in the DFTB+ work -- and a
rotation counted as a soft vibration would be counted again by the
ideal gas.  With any atom frozen nothing is projected: holding an
atom is what takes those freedoms away.

**The mass is the site's, the energy surface the element's.**  The
engine is built over hydrogen where a site says deuterium
(:mod:`xtal.ff.isotopes`), but the mass matrix uses 2.014, which is
the whole difference a deuterated framework makes.  A marker has no
mass and no mode: it is never displaced, and its rows are zero.

Stop is checked before every evaluation, and raises: a Hessian with
some of its columns is not one.  ``record`` hears each displacement as
it finishes, so the run can keep what it reached on disk.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from xtal.core import elements as el
from xtal.core import p1
from xtal.ff.api import CalculatorStopped

#: Displacement, A.  Small enough that the force is linear in it and
#: large enough that a single-precision ML engine's noise stays below
#: the difference; 0.01 is what phonopy and ase both default to.
DELTA = 0.01

#: kcal/mol/A^2/amu to s^-2, and on to wavenumbers.
_TO_SI = 4184.0 / 1e-20 / 1e-3
_C_CM = 2.99792458e10

#: Below this (in the eigenvalue's own frequency, cm^-1) a projected
#: rigid motion is reported as exactly zero rather than as the
#: round-off of a projection.
_RIGID = 1e-6


@dataclass(frozen=True)
class Vibrations:
    """What a Hessian gave: frequencies (cm^-1, negative imaginary)
    with their weights, and at Gamma the modes themselves."""

    frequencies: np.ndarray
    weights: np.ndarray
    #: ``(mode, atom, 3)`` over the whole P1 cell, cartesian, each
    #: mode's largest atom displacement one; a frozen atom or a marker
    #: is zero in every mode.
    displacements: np.ndarray
    masses: np.ndarray              # amu per P1 atom, 0 for a marker
    elements: tuple
    cart: np.ndarray
    lattice: np.ndarray
    kind: str                       # "crystal" or "molecule"
    free: np.ndarray                # the displaced P1 atoms
    energy: float                   # kcal/mol at the reference
    hessian: np.ndarray             # kcal/mol/A^2 over free coords
    evaluations: int
    method: str = "gamma"
    supercell: tuple | None = None
    q_mesh: tuple | None = None

    def to_modes_block(self, title: str = "Vibrational modes",
                       note: str = ""):
        """The Results panel's :class:`report.Modes`, so the table,
        *Animate mode* and *Export modes...* need nothing new."""
        from xtal.modules.report import Modes

        return Modes(title=title, frequencies=self.frequencies,
                     displacements=self.displacements,
                     elements=tuple(self.elements),
                     cart=np.asarray(self.cart, float),
                     lattice=np.asarray(self.lattice, float),
                     note=note)


def masses_of(elements) -> np.ndarray:
    """amu per atom: the isotope's own (D is 2.014), a marker none."""
    return np.array([0.0 if el.is_dummy(e) else el.mass(e)
                     for e in elements])


def evaluations(structure, frozen=()) -> int:
    """How many energy evaluations :func:`hessian` will make."""
    return 6 * len(_free_atoms(p1.expand(structure), frozen)) + 1


def _free_atoms(cell, frozen) -> np.ndarray:
    held = {int(i) for i in frozen}
    return np.array([i for i in range(cell.n_atoms)
                     if i not in held
                     and not el.is_dummy(cell.elements[i])], dtype=int)


def hessian(calculator, structure, *, kind: str = "crystal",
            delta: float = DELTA, frozen=(), cancel=None,
            progress=None, record=None) -> Vibrations:
    """The Gamma-point modes of ``structure`` under ``calculator``.

    ``calculator`` is built over ``structure`` (through the engine
    registry, which holds the markers back); ``frozen`` are P1 atom
    indices that are not displaced; ``kind`` decides which rigid
    motions are projected out.  ``progress(done, total)`` is called
    after each evaluation and ``record(atom, axis, plus, minus)``
    after each pair, with the two force arrays."""
    if kind not in ("crystal", "molecule"):
        raise ValueError(f"kind is crystal or molecule, not {kind!r}")
    cell = p1.expand(structure)
    matrix = np.asarray(structure.lattice.matrix, float)
    cart = np.asarray(cell.cart, float)
    masses = masses_of(cell.elements)
    free = _free_atoms(cell, frozen)
    total = 6 * len(free) + 1
    done = 0

    def evaluate(positions):
        nonlocal done
        if getattr(cancel, "requested", False):
            raise CalculatorStopped("stopped between displacements")
        result = calculator.compute(positions, matrix)
        done += 1
        if progress is not None:
            progress(done, total)
        return result

    reference = evaluate(cart)
    n = len(free)
    block = np.zeros((3 * n, 3 * n))
    for column, atom in enumerate(free):
        for axis in range(3):
            moved = cart.copy()
            moved[atom, axis] += delta
            plus = np.asarray(evaluate(moved).forces, float)
            moved[atom, axis] -= 2.0 * delta
            minus = np.asarray(evaluate(moved).forces, float)
            if record is not None:
                record(int(atom), axis, plus, minus)
            block[:, 3 * column + axis] = -(
                plus[free] - minus[free]).ravel() / (2.0 * delta)
    block = 0.5 * (block + block.T)

    m = np.repeat(masses[free], 3)
    weighted = block / np.sqrt(np.outer(m, m))
    if len(free) == cell.n_atoms - _n_markers(cell):
        rigid = _rigid_motions(structure, cell, free, masses, kind)
        if rigid is not None:
            projector = np.eye(3 * n) - rigid @ rigid.T
            weighted = projector @ weighted @ projector
    eigenvalues, vectors = np.linalg.eigh(0.5 * (weighted + weighted.T))
    frequencies = np.sign(eigenvalues) * np.sqrt(
        np.abs(eigenvalues) * _TO_SI) / (2.0 * np.pi * _C_CM)
    frequencies[np.abs(frequencies) < _RIGID] = 0.0

    displacements = np.zeros((len(frequencies), cell.n_atoms, 3))
    shaped = (vectors / np.sqrt(m)[:, None]).T.reshape(-1, n, 3)
    largest = np.linalg.norm(shaped, axis=2).max(axis=1)
    largest[largest == 0.0] = 1.0
    displacements[:, free, :] = shaped / largest[:, None, None]

    return Vibrations(
        frequencies=frequencies, weights=np.ones(len(frequencies)),
        displacements=displacements, masses=masses,
        elements=tuple(cell.elements), cart=cart, lattice=matrix,
        kind=kind, free=free, energy=float(reference.energy),
        hessian=block, evaluations=done)


def _n_markers(cell) -> int:
    return sum(1 for e in cell.elements if el.is_dummy(e))


def _rigid_motions(structure, cell, free, masses, kind):
    """Orthonormal mass-weighted translations (and, for a molecule,
    rotations) over the free atoms, as columns; ``None`` if none."""
    n = len(free)
    root = np.sqrt(masses[free])
    vectors = []
    for axis in range(3):
        t = np.zeros((n, 3))
        t[:, axis] = root
        vectors.append(t.ravel())
    if kind == "molecule":
        from xtal.core import molecule

        _elements, whole = molecule.whole(structure)
        # whole() lists the real atoms in P1 order, which is ``free``
        # here: nothing is frozen when this is asked.
        r = whole - (masses[free][:, None] * whole).sum(axis=0) \
            / masses[free].sum()
        for axis in range(3):
            e = np.zeros(3)
            e[axis] = 1.0
            vectors.append((np.cross(e, r) * root[:, None]).ravel())
    basis = np.array(vectors).T
    u, s, _vt = np.linalg.svd(basis, full_matrices=False)
    keep = s > 1e-8 * s.max()
    return u[:, keep] if keep.any() else None
