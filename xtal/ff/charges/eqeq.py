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
program, and on a framework's cell they are small: run on the same
MOF-5 atoms, the authors' program and this agree to 0.0002 e (see
``tests/data/eqeq``).  On a cell under about ten angstroms they are
not, because two cells either way is not a converged sum there; this
is the converged one.

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

#: The charge each element is expanded about, where it is not zero.
#:
#: **It decides the answer.**  EQeq's parabola is a finite difference
#: between the energies at c and c + 1, so it is only an approximation
#: near c; a metal expanded about the neutral atom has a soft curve
#: there and runs away -- Al-soc-MOF-1's aluminium came out +6.33, its
#: oxygens -3.57, with only the paper's seven metals in this table.
#: Ongari et al. (J. Chem. Theory Comput. 2019, 15, 382), comparing
#: EQeq with DDEC charges over 2338 MOFs, found it "heavily affected"
#: by the centre, and the common oxidation state necessary for alkali
#: metals and for aluminium.
#:
#: So every metal is expanded about its **common oxidation state** --
#: the values agree with Open Babel's EQeq (``eqeqIonizations.txt``),
#: which is where the authors' repository now sends its users -- and
#: nonmetals and metalloids about 0, as the paper does.  The paper's
#: own seven (Mg, V, Co, Ni, Cu, Zn, Zr) are kept as it gave them,
#: which leaves vanadium at +4 where Open Babel has +3.
#:
#: A common state is not every framework's: MIL-88B is chromium(III)
#: and the table's chromium is +2.  ``equilibrate(centres=...)`` is
#: how the framework in hand gets its own, and the note beside the
#: charges names the centres that were used.
PAPER_CENTRES = {
    "Mg": 2, "V": 4, "Co": 2, "Ni": 2, "Cu": 2, "Zn": 2, "Zr": 4,
}
CHARGE_CENTRES = {
    "Li": 1, "Be": 2, "Na": 1, "Mg": 2, "Al": 3, "K": 1, "Ca": 2,
    "Sc": 3, "Ti": 3, "V": 3, "Cr": 2, "Mn": 2, "Fe": 3, "Co": 2,
    "Ni": 2, "Cu": 2, "Zn": 2, "Ga": 3, "Ge": 4, "Rb": 1, "Sr": 2,
    "Y": 3, "Zr": 4, "Nb": 5, "Mo": 6, "Tc": 7, "Ru": 3, "Rh": 3,
    "Pd": 2, "Ag": 1, "Cd": 2, "In": 3, "Sn": 4, "Sb": 3, "Cs": 1,
    "Ba": 2, "La": 3, "Ce": 3, "Pr": 3, "Nd": 3, "Pm": 3, "Sm": 3,
    "Eu": 3, "Gd": 3, "Tb": 3, "Dy": 3, "Ho": 3, "Er": 3, "Tm": 3,
    "Yb": 3, "Lu": 3, "Hf": 4, "Ta": 5, "W": 6, "Re": 7, "Os": 4,
    "Ir": 4, "Pt": 4, "Au": 3, "Hg": 2, "Tl": 1, "Pb": 2, "Bi": 3,
    "Po": 2,
    **PAPER_CENTRES,
}

#: Atomic numbers of the noble gases: the closed shells a charge is
#: counted from in :func:`possible_charges`.
_NOBLE = (0, 2, 10, 18, 36, 54, 86, 118)

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


def parameters(element: str, centre: int | None = None
               ) -> tuple[float, float]:
    """``(chi, J)`` in eV for one element, about its charge centre and
    moved back to Q = 0.  ``centre`` overrides the table's."""
    energies = table().get(element)
    if energies is None or el.is_dummy(element):
        raise ValueError(
            f"EQeq has no ionisation energies for {element!r}")
    if centre is None:
        centre = CHARGE_CENTRES.get(element, 0)
    centre = int(centre)
    if not 0 <= centre < len(energies) - 1:
        raise ValueError(
            f"EQeq cannot expand {element} about {centre:+d}: the "
            f"table has its energies from 0 to +{len(energies) - 2}")
    below, above = energies[centre], energies[centre + 1]
    if element == "H":
        below = HYDROGEN_AFFINITY
    if np.isnan(below) or np.isnan(above):
        raise ValueError(
            f"EQeq expands {element} about {centre:+d} and the NIST "
            f"table has no ionisation energy there")
    hardness = above - below
    return 0.5 * (above + below) - centre * hardness, hardness


def possible_charges(element: str) -> tuple[int, int]:
    """The most negative and most positive charge an atom of
    ``element`` could carry.

    Out to the closed shells on either side: it cannot lose more than
    the electrons outside the noble-gas core beneath it, nor gain more
    than the next shell holds.  Generous for a transition metal (iron
    to +8) and exact where it matters most -- sodium +1, aluminium +3,
    oxygen -2 -- because what it is for is a charge that is not merely
    unusual but impossible.
    """
    z = el.atomic_number(element)
    below = max(n for n in _NOBLE if n < z)
    above = min(n for n in _NOBLE if n >= z)
    return -(above - z), z - below


def equilibrate(cell, total_charge: float = 0.0,
                dielectric: float = DIELECTRIC,
                setup_=None, centres=None) -> tuple[np.ndarray, str]:
    """``(charges, note)`` for a P1 cell.

    ``note`` is the caveat to show beside the numbers, as
    :func:`xtal.ff.uff.qeq.equilibrate` gives one: EQeq is a better
    estimate than QEq for a framework, and an estimate all the same.
    It names the charge centres the metals were expanded about, and
    any atom whose charge came out beyond what it could carry.

    ``centres`` is ``{element: charge}``, over the table's, for a
    framework whose metals are not in their common oxidation state.
    """
    n = cell.n_atoms
    if n == 0:
        return np.zeros(0), ""
    if n > qeq.MAX_ATOMS:
        raise ValueError(
            f"EQeq solves a dense {n} x {n} system; this cell is too "
            f"big for it. Set charges on the sites instead, or turn "
            f"electrostatics off")

    centres = {**CHARGE_CENTRES, **(centres or {})}
    chi, hardness = np.array(
        [parameters(e, centres.get(e, 0)) for e in cell.elements]).T
    matrix = np.asarray(cell.lattice.matrix, dtype=float)
    coulomb = ewald.pair_matrix(cell.cart, matrix, setup_)
    coulomb += _overlap(cell.cart, matrix, hardness)
    # The paper's pair term is lambda k/2 per unit charge product --
    # half of Coulomb's law as well as screened -- and that is what its
    # published charges were fitted with.
    interaction = dielectric * qeq.COULOMB_EV / 2.0 * coulomb
    interaction += np.diag(hardness)

    charges = qeq._solve(chi, interaction, total_charge)
    return charges, _note(cell.elements, charges, centres)


def _note(elements, charges, centres) -> str:
    present = sorted(set(elements), key=el.atomic_number)
    used = [f"{e} {centres[e]:+d}" for e in present if centres.get(e)]
    parts = ["EQeq charges (Wilmer, Kim and Snurr 2012) from NIST "
             "ionisation energies; an estimate to look over, not a "
             "published result"]
    if used:
        parts.append("metals expanded about " + ", ".join(used))
    elements = np.asarray(elements)
    beyond, causes = [], []
    for element in present:
        low, high = possible_charges(element)
        mine = charges[elements == element]
        if mine.max() > high:
            beyond.append(f"{element} {mine.max():+.2f} (at most "
                          f"{high:+d})")
            if not centres.get(element):
                causes.append(element)
        elif mine.min() < low:
            beyond.append(f"{element} {mine.min():+.2f} (at least "
                          f"{low:+d})")
    if beyond:
        # The runaway is a cation expanded about the neutral atom; the
        # anions beside it are only pushed there, and cannot be given
        # a centre below zero anyway.
        remedy = (f"expand {' and '.join(causes)} about a charge nearer "
                  f"its oxidation state" if causes else
                  "a different charge centre for the metals is the "
                  "place to start")
        parts.append(
            "beyond what any atom can carry: " + ", ".join(beyond)
            + ".  Those numbers mean nothing -- EQeq holds only near "
            "the charge each atom is expanded about -- and " + remedy)
    return "; ".join(parts)


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
