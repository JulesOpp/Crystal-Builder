"""Write the crystalline polymers of Open Sample that need hydrogens.

    python scripts/polymer_samples.py            # write them
    python scripts/polymer_samples.py --check    # exit 1 if it would change

A polymer crystal is a fibre-diffraction model, and the classic ones
locate the carbons only: Bunn's polyethylene (1939) was two numbers,
and Mencik's isotactic polypropylene, as the COD holds it (1552371),
is nine carbons.  A polymer sample without its hydrogens is a chain of
under-coordinated carbons that a force field cannot type and a
porosity run measures as empty space, so each is written here with
them -- the carbons exactly as published, the hydrogens placed by
geometry and said so in the file.

**The hydrogens are placed by this script and not by Add hydrogens.**
The valence planner types a two-neighbour carbon from its bond angle,
and above 114 degrees it reads sp2: Mencik's backbone CH2 at C9 is
114.09 degrees, so the planner gave it one hydrogen where it has two.
Here every carbon is sp3 by construction -- these are saturated
chains -- and the count is fixed by valence, which is what the
crystal is.  Tetrahedral angles, C-H :data:`CH` long, a methyl
staggered against the backbone.

Cellulose, the third polymer, comes from the COD with its C-H already
placed (``scripts/fetch_cod_samples.py``).
"""

from __future__ import annotations

import argparse
import itertools
import re
import sys
from pathlib import Path

import gemmi
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TARGET = ROOT / "resources" / "samples" / "polymer"

#: C-H, from neutron structures of alkanes.
CH = 1.09
TETRAHEDRAL = np.degrees(np.arccos(-1.0 / 3.0))
#: Two carbons this close are bonded; the next carbon of a chain or of
#: its neighbour is never under 2.4 A.
CC = 1.75


def _ops(name: str) -> tuple[str, ...]:
    """The group's operations as gemmi writes them, so that no
    hand-typed triplet can be wrong."""
    return tuple(op.triplet() for op in
                 gemmi.find_spacegroup_by_name(name).operations())


def _polyethylene():
    return dict(
        file="polyethylene.cif",
        block="polyethylene",
        name="polyethylene",
        header="""\
# Polyethylene: orthorhombic PE, written for Crystal Builder.
#
# Carbons: C. W. Bunn, Trans. Faraday Soc. 35, 482 (1939),
# doi:10.1039/TF9393500482 -- the cell and the one carbon site of
# Pnam, at room temperature.  Two planar zigzag chains through the
# cell along c, set at about 42 degrees to b.  Hydrogens: placed by
# scripts/polymer_samples.py at C-H 1.09 A and tetrahedral angles,
# since the fibre pattern located none.  Public domain.""",
        group="P n a m", number=62, ops=_ops("P n a m"),
        cell=(7.40, 4.93, 2.534, 90.0, 90.0, 90.0),
        carbons=[("C1", (0.038, 0.065, 0.25))])


def _polypropylene():
    return dict(
        file="isotactic-polypropylene.cif",
        block="iPP_alpha",
        name="isotactic polypropylene, alpha form",
        header="""\
# Isotactic polypropylene, alpha form, written for Crystal Builder.
#
# Carbons: Z. Mencik, J. Macromol. Sci. B 6, 101 (1972), as COD
# 1552371 holds them -- nine carbons, three monomers of a 3_1 helix,
# in P2_1/c with four chains in the cell, up and down.  Hydrogens:
# placed by scripts/polymer_samples.py at C-H 1.09 A and tetrahedral
# angles, each methyl staggered against the backbone, since the
# deposition has none.  Public domain, as the COD's data are.""",
        group="P 1 21/c 1", number=14, ops=_ops("P 1 21/c 1"),
        cell=(6.63, 20.78, 6.504, 90.0, 99.5, 90.0),
        carbons=[("C1", (0.262, 0.485, 0.201)),
                 ("C2", (0.214, 0.415, 0.265)),
                 ("C3", (0.214, 0.415, 0.502)),
                 ("C4", (0.950, 0.328, 0.482)),
                 ("C5", (0.165, 0.349, 0.590)),
                 ("C6", (0.165, 0.349, 0.827)),
                 ("C7", (0.538, 0.321, 0.914)),
                 ("C8", (0.371, 0.369, 0.958)),
                 ("C9", (0.371, 0.369, 0.195))])


SAMPLES = (_polyethylene(), _polypropylene())


def _operations(ops):
    """``(rotation, translation)`` for each ``x, y, z`` string."""
    out = []
    for op in ops:
        rotation = np.zeros((3, 3))
        translation = np.zeros(3)
        for row, term in enumerate(op.split(",")):
            for sign, token in re.findall(r"([+-]?)([xyz]|\d+/\d+)",
                                          term.replace(" ", "")):
                value = -1.0 if sign == "-" else 1.0
                if token in "xyz":
                    rotation[row, "xyz".index(token)] = value
                else:
                    top, bottom = token.split("/")
                    translation[row] += value * float(top) / float(bottom)
        out.append((rotation, translation))
    return out


def _matrix(a, b, c, alpha, beta, gamma):
    alpha, beta, gamma = np.radians([alpha, beta, gamma])
    vx = c * np.cos(beta)
    vy = c * (np.cos(alpha) - np.cos(beta) * np.cos(gamma)) / np.sin(
        gamma)
    return np.array([[a, 0, 0],
                     [b * np.cos(gamma), b * np.sin(gamma), 0],
                     [vx, vy, np.sqrt(c * c - vx * vx - vy * vy)]])


def _unit(v):
    return v / np.linalg.norm(v)


def hydrogens(sample) -> list[tuple[str, np.ndarray]]:
    """``(label, frac)`` of every hydrogen of the asymmetric unit."""
    matrix = _matrix(*sample["cell"])
    inverse = np.linalg.inv(matrix)
    ops = _operations(sample["ops"])
    images = [np.array(t) for t in itertools.product((-1, 0, 1),
                                                       repeat=3)]
    # A site on a mirror is its own image, and counted twice it would
    # be two neighbours.
    cell = []
    for label, f in sample["carbons"]:
        for r, t in ops:
            frac = np.mod(r @ np.asarray(f, float) + t, 1.0)
            if not any(np.allclose(frac, g) for _, g in cell):
                cell.append((label, frac))

    def neighbours(cart, skip=None):
        found = []
        for label, frac in cell:
            for image in images:
                other = (frac + image) @ matrix
                d = np.linalg.norm(other - cart)
                if 0.1 < d < CC and (skip is None or
                                     np.linalg.norm(other - skip) > 0.1):
                    found.append((label, other))
        return found

    out = []
    for label, frac in sample["carbons"]:
        here = np.asarray(frac, float) @ matrix
        bonded = neighbours(here)
        bonds = [_unit(cart - here) for _, cart in bonded]
        missing = 4 - len(bonds)
        if missing == 1:
            directions = [_unit(-sum(bonds))]
        elif missing == 2:
            bisector = _unit(-(bonds[0] + bonds[1]))
            normal = _unit(np.cross(bonds[0], bonds[1]))
            half = np.radians(TETRAHEDRAL / 2)
            directions = [np.cos(half) * bisector + s * np.sin(half)
                          * normal for s in (1, -1)]
        elif missing == 3:
            axis = bonds[0]
            # Staggered: a hydrogen anti to a substituent of the
            # carbon it hangs from.
            parent = bonded[0][1]
            far = [cart for _, cart in neighbours(parent, skip=here)]
            lateral = far[0] - parent
            lateral = _unit(lateral - (lateral @ axis) * axis)
            side = np.cross(axis, lateral)
            theta = np.radians(TETRAHEDRAL)
            directions = [np.cos(theta) * axis + np.sin(theta) * (
                np.cos(phi) * -lateral + np.sin(phi) * side)
                for phi in np.radians([0.0, 120.0, 240.0])]
        else:
            directions = []
        letters = "ABC" if len(directions) > 1 else ""
        for k, direction in enumerate(directions):
            name = "H" + label[1:] + (letters[k] if letters else "")
            out.append((name, (here + CH * direction) @ inverse))
    return out


def text(sample) -> str:
    a, b, c, alpha, beta, gamma = sample["cell"]
    lines = ["#" + "-" * 78, sample["header"], "#" + "-" * 78,
             f"data_{sample['block']}",
             f"_chemical_name_common            "
             f"'{sample['name']}'",
             f"_space_group_IT_number           {sample['number']}",
             f"_symmetry_space_group_name_H-M   '{sample['group']}'",
             f"_cell_length_a                   {a}",
             f"_cell_length_b                   {b}",
             f"_cell_length_c                   {c}",
             f"_cell_angle_alpha                {alpha}",
             f"_cell_angle_beta                 {beta}",
             f"_cell_angle_gamma                {gamma}",
             "loop_", "_symmetry_equiv_pos_as_xyz"]
    lines += [f"'{op}'" for op in sample["ops"]]
    lines += ["loop_", "_atom_site_label", "_atom_site_type_symbol",
              "_atom_site_fract_x", "_atom_site_fract_y",
              "_atom_site_fract_z", "_atom_site_occupancy"]
    for label, (x, y, z) in sample["carbons"]:
        lines.append(f"{label:<4} C {x:.3f} {y:.3f} {z:.3f} 1.0")
    for label, (x, y, z) in hydrogens(sample):
        lines.append(f"{label:<4} H {x:.5f} {y:.5f} {z:.5f} 1.0")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if a file would change")
    args = parser.parse_args(argv)
    changed = []
    for sample in SAMPLES:
        target = TARGET / sample["file"]
        written = text(sample)
        if target.is_file() and target.read_text("utf-8") == written:
            continue
        changed.append(target.name)
        if not args.check:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(written, "utf-8")
    if args.check and changed:
        print("would change: " + ", ".join(changed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
