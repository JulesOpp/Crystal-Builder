"""
xtal.ff.infrared
================
An IR spectrum from a Gamma Hessian: the engine's frequencies, a
charge model's intensities.

An intensity is how much a mode moves the dipole,
``I_k ∝ |Σ_i Z*_i · e_ik / √m_i|²``, and that needs the Born effective
charges Z* -- how the dipole changes as each atom moves.  **None of
the machine-learned engines gives a charge or a dipole** (MACE's
``get_dipole_moment`` needs a dipole-trained model, and MACE-MP is
not one), so the charges come from a model, and the spectrum says
which:

* ``fixed`` -- Z*_i = q_i I, with q from EQeq, or the force field's
  own when the engine is UFF with its electrostatics on.  No extra
  evaluations, and blind to a polar bond's charge moving as it
  stretches;
* ``flux`` -- EQeq solved again at each displaced geometry, and Z* the
  central difference of the dipole.  One solve per displacement, and
  better on polar bonds.

Only Gamma: light has no momentum to speak of, so an IR spectrum is
q = 0 and needs no supercell even where the thermochemistry used one.

**Z* sums to zero over the cell before it is used** (the acoustic sum
rule), so a uniform translation moves no dipole and the acoustic
modes carry no intensity.  A correction over 0.05 e is said, because
it means the charges did not add up to the cell's.

Raman is not here: it needs the polarisability's derivatives, which
no engine provides.
"""

from __future__ import annotations

import dataclasses

import numpy as np

from xtal.core import elements as el
from xtal.core import p1
from xtal.ff import thermo

#: (e / amu^1/2)^2 to km/mol: 42.2561 (D/A)^2/amu to km/mol, times
#: 4.80320 D per e A, squared.
TO_KM_PER_MOL = 42.2561 * 4.80320 ** 2

#: A sum-rule correction above this, in e, is said in the note.
SUM_RULE_SAID = 0.05

#: The broadening the panel opens with, cm^-1.
FWHM = 10.0

MODELS = ("fixed", "flux")


def born_charges(structure, vib, model: str = "fixed",
                 calculator=None) -> tuple[np.ndarray, str]:
    """``(Z*, source)``: ``(n_atoms, 3, 3)`` Born charges over the
    whole P1 cell, ``Z[i, a, b] = d mu_b / d r_ia`` in e, and the
    sentence saying where they came from.  A marker's is zero."""
    if model not in MODELS:
        raise ValueError(f"charges are {' or '.join(MODELS)}, "
                         f"not {model!r}")
    cell = p1.expand(structure)
    real = np.array([not el.is_dummy(e) for e in cell.elements])
    charges, said = _fixed_charges(structure, cell, real, calculator)
    born = np.zeros((cell.n_atoms, 3, 3))
    born[:] = charges[:, None, None] * np.eye(3)
    if model == "flux":
        born = _flux(structure, cell, real, vib, born)
        said = ("EQeq solved again at each displacement (charge flux); "
                "the frequencies are the engine's")
    else:
        said = f"{said}, fixed; the frequencies are the engine's"
    mean = born[real].mean(axis=0)
    born[real] -= mean
    correction = float(np.abs(mean).max()) if real.any() else 0.0
    if correction > SUM_RULE_SAID:
        said += (f"; the charges were shifted by up to "
                 f"{correction:.3f} e to sum to zero")
    return born, said


def _fixed_charges(structure, cell, real, calculator):
    """Per P1 atom: the engine's own charges where it has them and
    uses them, EQeq's otherwise."""
    own = _engine_charges(calculator, cell.n_atoms)
    if own is not None:
        return own, "UFF's own charges"
    clean_cell, kept = _clean_cell(structure, cell, real)
    from xtal.ff.charges import eqeq
    solved, _note = eqeq.equilibrate(clean_cell)
    charges = np.zeros(cell.n_atoms)
    charges[kept] = solved
    return charges, "EQeq charges"


def _engine_charges(calculator, n_atoms):
    if calculator is None:
        return None
    inner = getattr(calculator, "_inner", calculator)
    options = getattr(inner, "options", None)
    charges = getattr(inner, "charges", None)
    if charges is None or not getattr(options, "coulomb", False):
        return None
    charges = np.asarray(charges, float)
    if not np.any(charges):
        return None
    kept = getattr(calculator, "_kept", None)
    if kept is None:
        return charges if len(charges) == n_atoms else None
    out = np.zeros(n_atoms)
    out[np.asarray(kept, int)] = charges
    return out


def _clean_cell(structure, cell, real):
    """The P1 cell without its markers, and which atoms it kept."""
    kept = np.flatnonzero(real)
    if real.all():
        return cell, kept
    return dataclasses.replace(
        cell, frac=cell.frac[kept], site_idx=cell.site_idx[kept],
        op_idx=cell.op_idx[kept], tau=cell.tau[kept],
        elements=tuple(cell.elements[i] for i in kept),
        occupancy=cell.occupancy[kept],
        labels=tuple(cell.labels[i] for i in kept), _index={}), kept


def _flux(structure, cell, real, vib, born):
    """Z* of the displaced atoms by central differences of the EQeq
    dipole; the others keep their fixed charge."""
    from xtal.ff.charges import eqeq

    clean, kept = _clean_cell(structure, cell, real)
    position = {int(full): k for k, full in enumerate(kept)}
    matrix = np.asarray(structure.lattice.matrix, float)
    inverse = np.linalg.inv(matrix)
    cart = clean.lattice.to_cart(clean.frac)
    delta = 0.01
    for atom in vib.free:
        k = position[int(atom)]
        # Every other atom as the nearest image of itself to this one,
        # so the dipole is of a cluster round the moving atom rather
        # than of wherever the cell's faces happen to cut.
        d = clean.frac - clean.frac[k]
        d -= np.round(d)
        relative = d @ matrix
        for axis in range(3):
            dipoles = []
            for sign in (1.0, -1.0):
                moved = cart.copy()
                moved[k, axis] += sign * delta
                charges, _note = eqeq.equilibrate(dataclasses.replace(
                    clean, frac=moved @ inverse, _index={}))
                where = relative.copy()
                where[k, axis] += sign * delta
                dipoles.append(charges @ where)
            born[int(atom), axis, :] = (dipoles[0] - dipoles[1]) \
                / (2.0 * delta)
    return born


def intensities(vib, born) -> np.ndarray:
    """km/mol per mode, in the order of ``vib.frequencies``."""
    if vib.vectors is None:
        raise ValueError("these modes carry no eigenvectors")
    free = np.asarray(vib.free, int)
    root = np.sqrt(np.repeat(vib.masses[free], 3))
    cartesian = vib.vectors / root[:, None]          # (3 free, mode)
    z = born[free].reshape(3 * len(free), 3)          # rows: (i, a)
    dmu = z.T @ cartesian                             # (3, mode)
    return TO_KM_PER_MOL * np.sum(dmu ** 2, axis=0)


def spectrum_block(vib, intensity, source: str, fwhm: float = FWHM):
    """The report's :class:`Spectrum`: one stick per real mode, with
    each stick's row in the :class:`Modes` table beside it."""
    from xtal.modules.report import Spectrum

    keep = np.flatnonzero(vib.frequencies > thermo.ZERO_BELOW)
    return Spectrum(
        title="IR spectrum",
        frequencies=np.asarray(vib.frequencies, float)[keep],
        intensities=np.asarray(intensity, float)[keep],
        modes=tuple(int(i) for i in keep), fwhm=float(fwhm),
        note=f"Intensities from {source}.  Gamma only; imaginary and "
             f"zero modes are not drawn.")
