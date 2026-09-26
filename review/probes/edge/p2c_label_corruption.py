"""Area 2c: does a real foreign CIF with an awkward label survive a
read -> save round trip?"""
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))

from xtal.io import read_cif, write_cif  # noqa: E402
from xtal.io.project import read_project_structure, write_project  # noqa: E402

FOREIGN = """data_foreign
_cell_length_a 6.0
_cell_length_b 6.0
_cell_length_c 6.0
_cell_angle_alpha 90.0
_cell_angle_beta 90.0
_cell_angle_gamma 90.0
_space_group_name_H-M_alt 'P 1'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
'Na 1' Na 0.0 0.0 0.0
'Cl 1' Cl 0.5 0.5 0.5
"""

HANDEDITED = """data_handedited
_cell_length_a 6.0
_cell_length_b 6.0
_cell_length_c 6.0
_cell_angle_alpha 90.0
_cell_angle_beta 90.0
_cell_angle_gamma 90.0
_space_group_name_H-M_alt 'P 1'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Na1 Na 0.0 0.0 0.0
Cl1 Cl 0.5 0.5 0.5

loop_
_geom_bond_atom_site_label_1
_geom_bond_atom_site_label_2
_geom_bond_site_symmetry_2
_geom_bond_distance
_xtal_bond_image
_xtal_bond_order
_xtal_bond_kind
_xtal_bond_stated
Na1 Cl1 9_555 2.8200  0,0,0  1.000 explicit    no
"""


def run(tag, text):
    tmp = Path(tempfile.mkdtemp(prefix="xtalprobe-"))
    try:
        src = tmp / "in.cif"
        src.write_text(text, encoding="utf-8")
        print("=" * 66)
        print(f"CASE {tag}")
        s = read_cif(src)
        print(f"  read  -> labels={[x.label for x in s.sites]} "
              f"bonds={[(b.i, b.j, b.op) for b in s.bonds]}")
        out = tmp / "out.cif"
        try:
            write_cif(s, out)
            print("  write_cif ok")
        except Exception:
            print("  write_cif RAISED "
                  + traceback.format_exc().strip().splitlines()[-1])
            out = None
        if out is not None:
            try:
                back = read_cif(out)
                print(f"  re-read -> n_sites={len(back.sites)} "
                      f"labels={[x.label for x in back.sites]} "
                      f"bonds={len(back.bonds)}")
            except Exception:
                print("  re-read RAISED "
                      + traceback.format_exc().strip().splitlines()[-1])
                print("  ---- what was written ----")
                print("  " + out.read_text(encoding="utf-8")
                      .replace("\n", "\n  "))
        proj = tmp / "out.xtalproj"
        try:
            write_project(s, proj)
            back = read_project_structure(proj)
            print(f"  project -> n_sites={len(back.sites)}")
        except Exception:
            print("  project RAISED "
                  + traceback.format_exc().strip().splitlines()[-1])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    run("foreign CIF, label 'Na 1'", FOREIGN)
    run("hand-edited CIF, bond op 9_555 in P1", HANDEDITED)
    run("label with a leading #", FOREIGN.replace("'Na 1'", "'#Na1'")
        .replace("'Cl 1'", "Cl1"))
