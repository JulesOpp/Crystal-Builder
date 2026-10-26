"""
xtal.core.pyykko
================
Pyykkö and Atsumi's covalent radii, single- and double-bond, and the
aromatic bond the nanotube builder takes its default from.

The radii are as published, in pm:

- P. Pyykkö and M. Atsumi, "Molecular Single-Bond Covalent Radii for
  Elements 1-118", *Chem. Eur. J.* 15 (2009) 186-197,
  doi:10.1002/chem.200800987.
- P. Pyykkö and M. Atsumi, "Molecular Double-Bond Covalent Radii for
  Elements Li-E112", *Chem. Eur. J.* 15 (2009) 12770-12779,
  doi:10.1002/chem.200901472.

Transcribed from KnowledgeDoor's table of them and checked against
Wikipedia's: the 53 elements both give agree.  Written out as a
literal table, not read from a data file, so nothing has to be shipped
beside the code.  ``DOUBLE`` is None where the paper gives no
double-bond radius (H, He and some superheavies).

**The aromatic bond is Julius's rule** (2026-10-26): a honeycomb's
bond is of order 1.5, so each atom's radius is the mean of its single-
and double-bond radii and the bond is the sum of the two.  Carbon's is
2 x (75 + 67) / 2 pm = 1.42 A, graphite's to a hundredth; B-N's
(85 + 78) / 2 + (71 + 60) / 2 pm = 1.47 A.

Pure Python; no Qt.
"""

from __future__ import annotations

__all__ = ["SINGLE", "DOUBLE", "aromatic_radius", "aromatic_bond"]

#: Single-bond covalent radii, pm, in atomic-number order.
SINGLE = {
    "H": 32, "He": 46, "Li": 133, "Be": 102, "B": 85, "C": 75, "N": 71,
    "O": 63, "F": 64, "Ne": 67, "Na": 155, "Mg": 139, "Al": 126,
    "Si": 116, "P": 111, "S": 103, "Cl": 99, "Ar": 96, "K": 196,
    "Ca": 171, "Sc": 148, "Ti": 136, "V": 134, "Cr": 122, "Mn": 119,
    "Fe": 116, "Co": 111, "Ni": 110, "Cu": 112, "Zn": 118, "Ga": 124,
    "Ge": 121, "As": 121, "Se": 116, "Br": 114, "Kr": 117, "Rb": 210,
    "Sr": 185, "Y": 163, "Zr": 154, "Nb": 147, "Mo": 138, "Tc": 128,
    "Ru": 125, "Rh": 125, "Pd": 120, "Ag": 128, "Cd": 136, "In": 142,
    "Sn": 140, "Sb": 140, "Te": 136, "I": 133, "Xe": 131, "Cs": 232,
    "Ba": 196, "La": 180, "Ce": 163, "Pr": 176, "Nd": 174, "Pm": 173,
    "Sm": 172, "Eu": 168, "Gd": 169, "Tb": 168, "Dy": 167, "Ho": 166,
    "Er": 165, "Tm": 164, "Yb": 170, "Lu": 162, "Hf": 152, "Ta": 146,
    "W": 137, "Re": 131, "Os": 129, "Ir": 122, "Pt": 123, "Au": 124,
    "Hg": 133, "Tl": 144, "Pb": 144, "Bi": 151, "Po": 145, "At": 147,
    "Rn": 142, "Fr": 223, "Ra": 201, "Ac": 186, "Th": 175, "Pa": 169,
    "U": 170, "Np": 171, "Pu": 172, "Am": 166, "Cm": 166, "Bk": 168,
    "Cf": 168, "Es": 165, "Fm": 167, "Md": 173, "No": 176, "Lr": 161,
    "Rf": 157, "Db": 149, "Sg": 143, "Bh": 141, "Hs": 134, "Mt": 129,
    "Ds": 128, "Rg": 121, "Cn": 122, "Nh": 136, "Fl": 143, "Mc": 162,
    "Lv": 175, "Ts": 165, "Og": 157,
}

#: Double-bond covalent radii, pm; None where none is given.
DOUBLE = {
    "H": None, "He": None, "Li": 124, "Be": 90, "B": 78, "C": 67,
    "N": 60, "O": 57, "F": 59, "Ne": 96, "Na": 160, "Mg": 132,
    "Al": 113, "Si": 107, "P": 102, "S": 94, "Cl": 95, "Ar": 107,
    "K": 193, "Ca": 147, "Sc": 116, "Ti": 117, "V": 112, "Cr": 111,
    "Mn": 105, "Fe": 109, "Co": 103, "Ni": 101, "Cu": 115, "Zn": 120,
    "Ga": 117, "Ge": 111, "As": 114, "Se": 107, "Br": 109, "Kr": 121,
    "Rb": 202, "Sr": 157, "Y": 130, "Zr": 127, "Nb": 125, "Mo": 121,
    "Tc": 120, "Ru": 114, "Rh": 110, "Pd": 117, "Ag": 139, "Cd": 144,
    "In": 136, "Sn": 130, "Sb": 133, "Te": 128, "I": 129, "Xe": 135,
    "Cs": 209, "Ba": 161, "La": 139, "Ce": 137, "Pr": 138, "Nd": 137,
    "Pm": 135, "Sm": 134, "Eu": 134, "Gd": 135, "Tb": 135, "Dy": 133,
    "Ho": 133, "Er": 133, "Tm": 131, "Yb": 129, "Lu": 131, "Hf": 128,
    "Ta": 126, "W": 120, "Re": 119, "Os": 116, "Ir": 115, "Pt": 112,
    "Au": 121, "Hg": 142, "Tl": 142, "Pb": 135, "Bi": 141, "Po": 135,
    "At": 138, "Rn": 145, "Fr": 218, "Ra": 173, "Ac": 153, "Th": 143,
    "Pa": 138, "U": 134, "Np": 136, "Pu": 135, "Am": 135, "Cm": 136,
    "Bk": 139, "Cf": 140, "Es": 140, "Fm": None, "Md": 139, "No": 159,
    "Lr": 141, "Rf": 140, "Db": 136, "Sg": 128, "Bh": 128, "Hs": 125,
    "Mt": 125, "Ds": 116, "Rg": 116, "Cn": 137, "Nh": None, "Fl": None,
    "Mc": None, "Lv": None, "Ts": None, "Og": None,
}


def _aromatic_pm(symbol: str) -> float:
    double = DOUBLE[symbol]
    if double is None:
        return float(SINGLE[symbol])
    return (SINGLE[symbol] + double) / 2


def aromatic_radius(symbol: str) -> float:
    """The mean of ``symbol``'s single- and double-bond radii, in A;
    its single-bond radius where Pyykkö gives no double-bond one."""
    return _aromatic_pm(symbol) / 100


def aromatic_bond(a: str, b: str) -> float:
    """An aromatic (order 1.5) bond between ``a`` and ``b``, in A: the
    sum of their aromatic radii."""
    # Summed in pm and divided once: the two radii in A, each already
    # a division, add to 0.9750000000000001 for H-N, and a refusal or
    # note quoting the bond should quote the published figure.
    return (_aromatic_pm(a) + _aromatic_pm(b)) / 100
