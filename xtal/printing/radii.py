"""
xtal.printing.radii
===================
The ball radii of the one-color export, so the two exports print the
same model.

Transcribed from Atomic Blender (``io_mesh_atomic/pdb_import.py``,
``ELEMENTS_DEFAULT``, as shipped with Blender 3.4).  The one-color
export asks it for radius type ``'1'``, "atomic", and the importer
reads that as index 1 of ``[used, covalent, atomic]`` -- the
*covalent* column, which is what is transcribed here.  The add-on is
not ours to import (it needs ``bpy``), and a test re-reads it when
Blender is installed.
"""

from __future__ import annotations

#: Radius in Angstrom by element symbol, before the ball scale.
RADII = {
    "H": 0.32, "He": 0.93, "Li": 1.23, "Be": 0.90, "B": 0.82, "C": 0.77,
    "N": 0.75, "O": 0.73, "F": 0.72, "Ne": 0.71, "Na": 1.54, "Mg": 1.36,
    "Al": 1.18, "Si": 1.11, "P": 1.06, "S": 1.02, "Cl": 0.99, "Ar": 0.98,
    "K": 2.03, "Ca": 1.74, "Sc": 1.44, "Ti": 1.32, "V": 1.22, "Cr": 1.18,
    "Mn": 1.17, "Fe": 1.17, "Co": 1.16, "Ni": 1.15, "Cu": 1.17, "Zn": 1.25,
    "Ga": 1.26, "Ge": 1.22, "As": 1.20, "Se": 1.16, "Br": 1.14, "Kr": 1.31,
    "Rb": 2.16, "Sr": 1.91, "Y": 1.62, "Zr": 1.45, "Nb": 1.34, "Mo": 1.30,
    "Tc": 1.27, "Ru": 1.25, "Rh": 1.25, "Pd": 1.28, "Ag": 1.34, "Cd": 1.48,
    "In": 1.44, "Sn": 1.41, "Sb": 1.40, "Te": 1.36, "I": 1.33, "Xe": 1.31,
    "Cs": 2.35, "Ba": 1.98, "La": 1.69, "Ce": 1.65, "Pr": 1.65, "Nd": 1.64,
    "Pm": 1.63, "Sm": 1.62, "Eu": 1.85, "Gd": 1.61, "Tb": 1.59, "Dy": 1.59,
    "Ho": 1.58, "Er": 1.57, "Tm": 1.56, "Yb": 1.74, "Lu": 1.56, "Hf": 1.44,
    "Ta": 1.34, "W": 1.30, "Re": 1.28, "Os": 1.26, "Ir": 1.27, "Pt": 1.30,
    "Au": 1.34, "Hg": 1.49, "Tl": 1.48, "Pb": 1.47, "Bi": 1.46, "Po": 1.46,
    "At": 1.45, "Rn": 1.00, "Fr": 1.00, "Ra": 1.00, "Ac": 1.00, "Th": 1.65,
    "Pa": 1.00, "U": 1.42, "Np": 1.00, "Pu": 1.00, "Am": 1.00, "Cm": 1.00,
    "Bk": 1.00, "Cf": 1.00, "Es": 1.00, "Fm": 1.00, "Md": 1.00, "No": 1.00,
    "Lr": 1.00,
}

#: An element the table does not name: Atomic Blender's "Default".
DEFAULT = 1.0


def radius(symbol: str) -> float:
    return RADII.get(symbol, DEFAULT)
