"""
xtal.ff.charges.eqeq
====================
Extended charge equilibration -- QEq's idea with measured atoms.

EQeq (Wilmer, Kim and Snurr, *J. Phys. Chem. Lett.* **2012**, 3, 2506)
keeps QEq's energy,

    E(Q) = sum_i (chi_i Q_i + 1/2 J_i Q_i^2)
         + sum_{i<j} J_ij(r_ij) Q_i Q_j,

and changes where chi and J come from.  QEq's are fitted parameters
about the neutral atom, and a zinc in a framework is nowhere near
neutral: expanded about Q = 0, its energy curve is the wrong curve by
the time it reaches +1.2, and QEq's metal charges are where it fails
worst.  EQeq expands each element about a **charge centre** c instead
-- the charge it usually carries -- and reads the curve there off the
atom's own ionisation energies:

    chi = (IE_{c+1} + IE_c) / 2 - c J,     J = IE_{c+1} - IE_c,

with ``IE_0`` the electron affinity.  The ``- c J`` moves the
expansion back to Q = 0, so the solver is QEq's own
(:func:`xtal.ff.uff.qeq._solve`) and the charges it returns are the
atoms' charges, not offsets from c.

Between atoms the interaction is Coulomb screened by a dielectric
constant lambda, plus a Gaussian overlap term that takes 1/r to the
finite ``lambda sqrt(J_i J_j)`` as two atoms merge.  The Coulomb half
is summed by Ewald (:func:`xtal.ff.ewald.pair_matrix`), converged,
where the authors' program truncates it at two cells either way.
That, and a newer NIST table, are the differences from the published
program: on MOF-5 zinc comes out at +1.210 against its +1.211, and
no atom moves by more than 0.05 e (the carboxylate carbon).

**What the table is.**  Ionisation energies from NIST's Atomic Spectra
Database, electron affinities from PubChem, both written into
``data/ionization.csv`` by ``scripts/eqeq_table.py`` -- never copied
from the GPL-licensed table the published implementations carry.

Charges are in units of e; energies in eV.
"""

from __future__ import annotations

import csv
import io
import itertools
from functools import cache
from importlib import resources

import numpy as np

from xtal.core import elements as el
from xtal.ff import ewald
from xtal.ff.uff import qeq

#: The charge each element is expanded about, where it is not zero --
#: the paper's own defaults, the common oxidation states of the metals
#: it was tested on.  Every other element is expanded about the neutral
#: atom, as QEq expands everything.
CHARGE_CENTRES = {
    "Mg": 2, "V": 4, "Co": 2, "Ni": 2, "Cu": 2, "Zn": 2, "Zr": 4,
}

#: The paper's dielectric screening of every Coulomb interaction.
DIELECTRIC = 1.2

#: Hydrogen's electron affinity, as the paper sets it.  The measured
#: 0.754 eV makes hydrogen far too ready to take an electron -- the
#: hydride is not what a C-H or O-H hydrogen is -- and -2 eV is the
#: value the authors fitted in its place.  It is a parameter of the
#: method, not a property of the atom, which is why it is here and not
#: in the table.
HYDROGEN_AFFINITY = -2.0

#: The overlap term is a Gaussian in r, so it is summed only as far as
#: it matters: out to where ``exp(-(a r)^2)`` has fallen below this.
_OVERLAP_TOLERANCE = 1e-12


@cache
def table() -> dict[str, tuple[float, ...]]:
    """``{symbol: (EA, IE1, IE2, ...)}`` in eV, with NaN where the
    sources have nothing.

    An electron affinity the table leaves blank is an anion that is
    not bound, and it is read as zero: that is the energy an extra
    electron gives back when it does not stay.
    """
    text = (resources.files("xtal.ff.charges") / "data"
            / "ionization.csv").read_text(encoding="utf-8")
    rows = csv.reader(line for line in io.StringIO(text)
                      if not line.startswith("#"))
    next(rows)
    energies = {}
    for row in rows:
        affinity = float(row[2]) if row[2] else 0.0
        energies[row[1]] = (affinity,) + tuple(
            float(v) if v else float("nan") for v in row[3:])
    return energies


def parameters(element: str) -> tuple[float, float]:
    """``(chi, J)`` in eV for one element, about its charge centre and
    moved back to Q = 0."""
    energies = table().get(element)
    if energies is None or el.is_dummy(element):
        raise ValueError(
            f"EQeq has no ionisation energies for {element!r}")
    centre = CHARGE_CENTRES.get(element, 0)
    below, above = energies[centre], energies[centre + 1]
    if element == "H":
        below = HYDROGEN_AFFINITY
    if np.isnan(below) or np.isnan(above):
        raise ValueError(
            f"EQeq expands {element} about {centre:+d} and the NIST "
            f"table has no ionisation energy there")
    hardness = above - below
    return 0.5 * (above + below) - centre * hardness, hardness


def equilibrate(cell, total_charge: float = 0.0,
                dielectric: float = DIELECTRIC,
                setup_=None) -> tuple[np.ndarray, str]:
    """``(charges, note)`` for a P1 cell.

    ``note`` is the caveat to show beside the numbers, as
    :func:`xtal.ff.uff.qeq.equilibrate` gives one: EQeq is a better
    estimate than QEq for a framework, and an estimate all the same.
    """
    n = cell.n_atoms
    if n == 0:
        return np.zeros(0), ""
    if n > qeq.MAX_ATOMS:
        raise ValueError(
            f"EQeq solves a dense {n} x {n} system; this cell is too "
            f"big for it. Set charges on the sites instead, or turn "
            f"electrostatics off")

    chi, hardness = np.array(
        [parameters(e) for e in cell.elements]).T
    matrix = np.asarray(cell.lattice.matrix, dtype=float)
    coulomb = ewald.pair_matrix(cell.cart, matrix, setup_)
    coulomb += _overlap(cell.cart, matrix, hardness)
    # The paper's pair term is lambda k/2 per unit charge product --
    # half of Coulomb's law as well as screened -- and that is what its
    # published charges were fitted with.
    interaction = dielectric * qeq.COULOMB_EV / 2.0 * coulomb
    interaction += np.diag(hardness)

    charges = qeq._solve(chi, interaction, total_charge)
    note = ("EQeq charges (Wilmer, Kim and Snurr 2012) from NIST "
            "ionisation energies; an estimate to look over, not a "
            "published result")
    return charges, note


def _overlap(cart, matrix, hardness) -> np.ndarray:
    """The overlap correction to 1/r, summed over periodic images.

    ``exp(-(a r)^2) (2a - a^2 r - 1/r)`` with ``a = sqrt(J_i J_j)/k``:
    it cancels the 1/r as r goes to zero and leaves 2a, and it is gone
    by a few Angstrom.  An atom's overlap with *itself* is its
    hardness, on the diagonal already, so that one term is left out.
    """
    n = len(cart)
    a = np.sqrt(np.outer(hardness, hardness)) / qeq.COULOMB_EV
    reach = np.sqrt(-np.log(_OVERLAP_TOLERANCE)) / a.min()

    frac = cart @ np.linalg.inv(matrix)
    delta = frac[None, :, :] - frac[:, None, :]
    delta -= np.rint(delta)
    volume = abs(float(np.linalg.det(matrix)))
    widths = volume / np.linalg.norm(
        np.cross(matrix[[1, 2, 0]], matrix[[2, 0, 1]]), axis=1)
    images = np.ceil(reach / widths + 0.5).astype(int)

    result = np.zeros((n, n))
    for shift in itertools.product(*(range(-m, m + 1) for m in images)):
        d = (delta + np.array(shift, dtype=float)) @ matrix
        r = np.linalg.norm(d, axis=2)
        inside = (r < reach) & (r > 1e-9)
        if not inside.any():
            continue
        safe = np.where(inside, r, 1.0)
        term = np.exp(-(a * safe) ** 2) * (2 * a - a * a * safe
                                            - 1.0 / safe)
        result += np.where(inside, term, 0.0)
    return result
