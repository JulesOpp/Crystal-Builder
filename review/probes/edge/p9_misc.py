"""Leftovers: encodings in the other readers, multi-block, export."""
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))
sys.path.insert(0, str(HERE.parent))

from fixtures import quartz  # noqa: E402
from xtal.core.lattice import Lattice  # noqa: E402
from xtal.core.site import Site  # noqa: E402
from xtal.core.structure import TOPOLOGY, Bond, Structure  # noqa: E402
from xtal.io import (  # noqa: E402
    FORMATS,
    for_export,
    read_cif,
    what_is_dropped,
    write_cif,
)
from xtal.io.project import read_project, write_project  # noqa: E402


def last():
    return traceback.format_exc().strip().splitlines()[-1]


def main():
    tmp = Path(tempfile.mkdtemp(prefix="xtalprobe-"))
    try:
        print("### a BOM / latin-1 in front of every reader")
        q = quartz()
        for fmt, ext in (("cif", ".cif"), ("xyz", ".xyz"),
                         ("cssr", ".cssr"), ("gen", ".gen"),
                         ("xtalproj", ".xtalproj")):
            p = tmp / f"q{ext}"
            FORMATS.write(q, p, fmt)
            raw = p.read_bytes()
            for tag, data in (("plain", raw),
                              ("BOM", b"\xef\xbb\xbf" + raw),
                              ("CRLF", raw.replace(b"\n", b"\r\n")),
                              ("latin-1 byte",
                               raw.replace(b"Si", b"S\xe9", 1))):
                p.write_bytes(data)
                try:
                    s = FORMATS.read(p, fmt)
                    print(f"  {fmt:<9} {tag:<13} ok "
                          f"sites={len(s.sites)}")
                except Exception:
                    print(f"  {fmt:<9} {tag:<13} {last()[:90]}")
            p.write_bytes(raw)

        print()
        print("### a CIF value in latin-1")
        text = ("data_x\n_cell_length_a 5\n_cell_length_b 5\n"
                "_cell_length_c 5\n_cell_angle_alpha 90\n"
                "_cell_angle_beta 90\n_cell_angle_gamma 90\n"
                "_chemical_name_mineral 'quartz de café'\n"
                "loop_\n_atom_site_label\n_atom_site_type_symbol\n"
                "_atom_site_fract_x\n_atom_site_fract_y\n"
                "_atom_site_fract_z\nSi1 Si 0 0 0\n")
        p = tmp / "latin.cif"
        p.write_bytes(text.encode("latin-1"))
        try:
            s = read_cif(p)
            print(f"  read ok, mineral={s.meta.get('mineral')!r}")
            out = tmp / "latin-out.cif"
            write_cif(s, out)
            print(f"  rewritten as utf-8, "
                  f"re-read mineral="
                  f"{read_cif(out).meta.get('mineral')!r}")
        except Exception:
            print(f"  {last()}")

        print()
        print("### a multi-block CIF through the registry")
        two = (tmp / "q.cif").read_text(encoding="utf-8") if False else None
        write_cif(quartz(), tmp / "one.cif")
        block = (tmp / "one.cif").read_text(encoding="utf-8")
        multi = tmp / "multi.cif"
        multi.write_text(block + "\n"
                         + block.replace("data_one", "data_second")
                         .replace("4.913400", "9.913400"),
                         encoding="utf-8")
        first_a = FORMATS.read(multi).lattice.parameters[0]
        alls = [round(b.lattice.parameters[0], 3)
                for b in FORMATS.read_all(multi)]
        print(f"  FORMATS.read      -> a={first_a}")
        print(f"  FORMATS.read_all  -> {alls}")
        print(f"  warnings on the first block: "
              f"{FORMATS.read(multi).meta.get('warnings')}")

        print()
        print("### for_export with markers and net edges")
        s = Structure(
            lattice=Lattice.cubic(10.0), space_group="P1",
            sites=[Site(element="Zn", frac=[0, 0, 0], label="Zn1"),
                   Site(element="O", frac=[.2, 0, 0], label="O1"),
                   Site(element="X", frac=[.5, .5, .5], label="X1")])
        s.bonds.append(Bond(i=0, j=1, image=(0, 0, 0), order=1.0,
                            kind="explicit", op=0))
        s.bonds.append(Bond(i=2, j=0, image=(0, 0, 0), order=1.0,
                            kind=TOPOLOGY, op=0))
        s.bonds.append(Bond(i=0, j=1, image=(1, 0, 0), order=1.0,
                            kind="suppressed", op=0))
        print(f"  what_is_dropped: {what_is_dropped(s)}")
        ex = for_export(s)
        print(f"  before: {len(s.sites)} sites, "
              f"{[b.kind for b in s.bonds]}")
        print(f"  after:  {len(ex.sites)} sites, "
              f"{[b.kind for b in ex.bonds]}")
        out = tmp / "ex.cif"
        write_cif(ex, out)
        back = read_cif(out)
        print(f"  re-read: {len(back.sites)} sites, "
              f"{[b.kind for b in back.bonds]}")
        print(f"  original untouched? "
              f"{len(s.sites) == 3 and len(s.bonds) == 3}")

        print()
        print("### project round trip keeps meta / bonds")
        write_project(s, tmp / "s.xtalproj")
        doc = read_project(tmp / "s.xtalproj")
        st = doc.structure if hasattr(doc, "structure") else doc
        print(f"  project -> {type(doc).__name__}; "
              f"sites={len(st.sites)} bonds="
              f"{[b.kind for b in st.bonds]}")
        print(f"  meta kept: "
              f"{sorted(set(s.meta) & set(st.meta))}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
