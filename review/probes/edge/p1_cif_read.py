"""Area 1: CIF reading edge cases."""
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from xtal.io.cif_reader import read_cif, read_cif_all  # noqa: E402

HEAD = """data_probe
_cell_length_a 5.0
_cell_length_b 5.0
_cell_length_c 5.0
_cell_angle_alpha 90.0
_cell_angle_beta 90.0
_cell_angle_gamma 90.0
"""

SITES = """loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Na1 Na 0.0 0.0 0.0
Cl1 Cl 0.5 0.5 0.5
"""

CASES: dict[str, str] = {}

CASES["no symmetry at all"] = HEAD + SITES

CASES["H-M_alt only"] = (
    HEAD + "_space_group_name_H-M_alt 'F m -3 m'\n" + SITES)

CASES["Hall only"] = (
    HEAD + "_space_group_name_Hall '-F 4 2 3'\n" + SITES)

CASES["Hall with semicolons"] = (
    HEAD + "_space_group_name_Hall '-F 4;2;3'\n" + SITES)

CASES["origin choice 2 (Fd-3m #227:2)"] = """data_ochoice2
_cell_length_a 8.0
_cell_length_b 8.0
_cell_length_c 8.0
_cell_angle_alpha 90.0
_cell_angle_beta 90.0
_cell_angle_gamma 90.0
_space_group_name_H-M_alt 'F d -3 m :2'
_space_group_IT_number 227
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Si1 Si 0.125 0.125 0.125
"""

CASES["rhombohedral axes (R-3c :R)"] = """data_rhomb
_cell_length_a 6.0
_cell_length_b 6.0
_cell_length_c 6.0
_cell_angle_alpha 55.0
_cell_angle_beta 55.0
_cell_angle_gamma 55.0
_space_group_name_H-M_alt 'R -3 c :R'
_space_group_IT_number 167
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Al1 Al 0.3523 0.3523 0.3523
"""

CASES["hexagonal axes (R-3c :H)"] = """data_hex
_cell_length_a 4.76
_cell_length_b 4.76
_cell_length_c 12.99
_cell_angle_alpha 90.0
_cell_angle_beta 90.0
_cell_angle_gamma 120.0
_space_group_name_H-M_alt 'R -3 c :H'
_space_group_IT_number 167
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Al1 Al 0.0 0.0 0.3523
"""

CASES["partial occupancy / two atoms on one site"] = HEAD + """loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
_atom_site_occupancy
_atom_site_disorder_group
Na1 Na 0.0 0.0 0.0 0.6 1
K1  K  0.0 0.0 0.0 0.4 2
Cl1 Cl 0.5 0.5 0.5 1.0 .
"""

CASES["? and . values"] = HEAD + """_chemical_formula_sum ?
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
_atom_site_occupancy
_atom_site_U_iso_or_equiv
Na1 Na 0.0 0.0 0.0 ? ?
Cl1 Cl 0.5 0.5 0.5 . .
"""

CASES["type_symbol Zn2+ / D / X"] = HEAD + """loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Zn1 Zn2+ 0.0 0.0 0.0
D1  D    0.2 0.2 0.2
X1  X    0.4 0.4 0.4
Q1  Q    0.6 0.6 0.6
"""

CASES["two data blocks"] = (HEAD + SITES).replace("data_probe", "data_one") \
    + "\n" + (HEAD + SITES).replace("data_probe", "data_two").replace(
        "5.0", "6.0")

CASES["foreign _geom_bond loop"] = HEAD + SITES + """
loop_
_geom_bond_atom_site_label_1
_geom_bond_atom_site_label_2
_geom_bond_distance
_geom_bond_site_symmetry_2
Na1 Cl1 2.820 .
Na1 Cl1 2.820 2_555
"""

CASES["_xtal_bond_ loop naming a gone site"] = HEAD + SITES + """
loop_
_geom_bond_atom_site_label_1
_geom_bond_atom_site_label_2
_geom_bond_site_symmetry_2
_geom_bond_distance
_xtal_bond_image
_xtal_bond_order
_xtal_bond_kind
_xtal_bond_stated
Na1 Cl1 1_555 2.8200  0,0,0  1.000 explicit    no
Na1 Xx9 1_555 2.8200  0,0,0  1.000 explicit    no
Na1 Cl1 9_555 2.8200  0,0,0  1.000 net         no
"""

CASES["empty file"] = ""

CASES["XYZ named .cif"] = """2
a comment
Na 0.0 0.0 0.0
Cl 2.8 2.8 2.8
"""

CASES["no atom_site loop, cell only"] = HEAD


def describe(s):
    return (f"sg={s.space_group.short_name!r} (#{s.space_group.number}, "
            f"{s.space_group.order} ops) "
            f"n_sites={len(s.sites)} "
            f"elements={[x.element for x in s.sites]} "
            f"occ={[round(x.occupancy, 3) for x in s.sites]} "
            f"bonds={len(s.bonds)} "
            f"warnings={s.meta.get('warnings')}")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="xtalprobe-"))
    try:
        for name, text in CASES.items():
            path = tmp / "probe.cif"
            path.write_text(text, encoding="utf-8")
            print("=" * 68)
            print(f"CASE: {name}")
            try:
                blocks = read_cif_all(path)
                print(f"  read_cif_all -> {len(blocks)} block(s)")
                for b in blocks:
                    print("   ", describe(b))
                if blocks:
                    s = read_cif(path)
                    print(f"  read_cif     -> {describe(s)}")
                    if s.bonds:
                        for bd in s.bonds:
                            print(f"      bond {bd}")
            except Exception:
                print("  RAISED:")
                print("    " + traceback.format_exc().strip().replace(
                    "\n", "\n    "))
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
