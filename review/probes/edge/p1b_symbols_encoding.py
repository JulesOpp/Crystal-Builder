"""Area 1b: type symbols one at a time, and text encodings."""
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import gemmi  # noqa: E402

from xtal.core.spacegroup import SpaceGroup  # noqa: E402
from xtal.io.cif_reader import read_cif  # noqa: E402

HEAD = """data_probe
_cell_length_a 5.0
_cell_length_b 5.0
_cell_length_c 5.0
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
"""


def one_symbol(tmp, sym):
    text = HEAD + f"A1 {sym} 0.1 0.2 0.3\n"
    p = tmp / "s.cif"
    p.write_text(text, encoding="utf-8")
    try:
        s = read_cif(p)
        site = s.sites[0]
        print(f"  {sym:<6} -> element={site.element!r} "
              f"label={site.label!r} charge={site.charge!r}")
    except Exception as exc:
        print(f"  {sym:<6} -> {type(exc).__name__}: {exc}")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="xtalprobe-"))
    try:
        print("--- _atom_site_type_symbol values ---")
        for sym in ("Zn2+", "O2-", "D", "X", "Q", "Zz", "Uuo", "Og",
                    "Zn2", "Zn+2", "H_", "CA", ""):
            one_symbol(tmp, sym)

        print()
        print("--- text encodings ---")
        base = HEAD + "Na1 Na 0.0 0.0 0.0\n"
        titled = base.replace("data_probe", "data_café")
        variants = {
            "LF utf-8": base.encode("utf-8"),
            "CRLF utf-8": base.replace("\n", "\r\n").encode("utf-8"),
            "CR only": base.replace("\n", "\r").encode("utf-8"),
            "utf-8 BOM": b"\xef\xbb\xbf" + base.encode("utf-8"),
            "utf-8 accent in title": titled.encode("utf-8"),
            "latin-1 accent in title": titled.encode("latin-1"),
            "latin-1 in a comment": (
                "# résolu\n" + base).encode("latin-1"),
        }
        for name, data in variants.items():
            p = tmp / "e.cif"
            p.write_bytes(data)
            try:
                s = read_cif(p)
                print(f"  {name:<24} -> ok sites={len(s.sites)} "
                      f"title={s.meta.get('title')!r} "
                      f"a={s.lattice.parameters[0]}")
            except Exception:
                line = traceback.format_exc().strip().splitlines()[-1]
                print(f"  {name:<24} -> {line}")

        print()
        print("--- space-group settings ---")
        for name in ("R -3 c", "R -3 c :H", "R -3 c :R", "R-3c", "H-3c",
                     "F d -3 m :1", "F d -3 m :2", "Fd-3m",
                     "P n m a", "P 1 21/c 1", "C 1 2/c 1"):
            try:
                g = SpaceGroup.from_name(name)
                print(f"  {name:<12} -> short={g.short_name!r} "
                      f"hm={g.hm!r} hall={g.hall!r} #{g.number} "
                      f"ops={g.order}")
            except Exception as exc:
                print(f"  {name:<12} -> {type(exc).__name__}: {exc}")
        gs = gemmi.find_spacegroup_by_name("R -3 c :H")
        print(f"  gemmi R-3c:H  -> xhm={gs.xhm()!r} "
              f"short={gs.short_name()!r}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
