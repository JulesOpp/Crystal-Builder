# Written 2026-09-19 against Crystal-Builder e35ebe1 (base 3cd15e2, v0.2.1).
"""Which fields of which writers a hostile label corrupts.

Answers three questions the tier-1 plan needs numbers for:
  1. does the *reader* round-trip a properly quoted label?
  2. which other fields of cif_writer are written unquoted?
  3. do the CSSR / gen / PDB / XYZ writers have the same hole, and is
     there one helper or several?
"""
import tempfile
import traceback
from pathlib import Path

from xtal.core.structure import Bond
from xtal.io import FORMATS
from xtal.io import cif_writer, project

HOSTILE = ["Na 1", "#Na1", "_Na1", "Na'1", "Na\"1", ";Na1", "[Na1]",
           "$Na1", "Na\t1", "'Na1'", "data_Na1", "loop_"]

TMP = Path(tempfile.mkdtemp(prefix="tier1-labels"))


def halite():
    from tests.conftest import _halite  # noqa: F401
    raise SystemExit


def base():
    s = FORMATS.read("resources/samples/zn_oac.cif")
    return s


def case(label):
    s = base()
    s.sites[0].label = label
    if len(s.sites) > 1:
        s.add_bond(Bond(0, 1))
    return s


def try_cif(s, tag):
    path = TMP / f"{tag}.cif"
    try:
        cif_writer.write_cif(s, path)
    except Exception as exc:                        # noqa: BLE001
        return f"write raised {type(exc).__name__}: {exc}"
    try:
        back = FORMATS.read(path)
    except Exception as exc:                        # noqa: BLE001
        return (f"re-read raised {type(exc).__name__}: "
                f"{str(exc).splitlines()[0][:70]}")
    return (f"n_sites={len(back.sites)} label={back.sites[0].label!r} "
            f"bonds={len(back.bonds)}")


def try_project(s, tag):
    path = TMP / f"{tag}.xtalproj"
    try:
        project.write_project(s, path)
        back = project.read_project(path)[0]
    except Exception as exc:                        # noqa: BLE001
        return (f"{type(exc).__name__}: "
                f"{str(exc).splitlines()[0][:70]}")
    return f"n_sites={len(back.sites)} label={back.sites[0].label!r}"


print("== 1. CIF write -> read, one hostile label on site 0 ==")
for label in HOSTILE:
    s = case(label)
    tag = "".join(c if c.isalnum() else "_" for c in label)
    print(f"  {label!r:12s} cif: {try_cif(s, tag):58s} "
          f"proj: {try_project(s, tag)}")

print("\n== 2. does the reader take a *correctly* quoted label? ==")
s = case("Na 1")
text = cif_writer.cif_string(s)
fixed = text.replace("Na 1     ", "'Na 1'   ")
p = TMP / "quoted.cif"
p.write_text(fixed, encoding="utf-8")
try:
    back = FORMATS.read(p)
    print(f"  hand-quoted label round trips -> {back.sites[0].label!r} "
          f"({len(back.sites)} sites)")
except Exception as exc:                            # noqa: BLE001
    print(f"  hand-quoted label FAILS: {exc}")

print("\n== 3. other writers, same hostile label ==")
for name, ext in (("cssr", ".cssr"), ("gen", ".gen"), ("pdb", ".pdb"),
                  ("xyz", ".xyz"), ("cgd", ".cgd")):
    for label in ("Na 1", "#Na1"):
        s = case(label)
        path = TMP / f"w{name}{ext}"
        try:
            FORMATS.write(s, path, name)
        except Exception as exc:                    # noqa: BLE001
            print(f"  {name:5s} {label!r:8s} write raised "
                  f"{type(exc).__name__}: {str(exc)[:50]}")
            continue
        head = [ln for ln in path.read_text().splitlines()
                if "Na" in ln or "#" in ln][:2]
        rt = "-"
        try:
            b = FORMATS.read(path)
            rt = f"re-read {len(b.sites)} sites"
        except Exception as exc:                    # noqa: BLE001
            rt = f"re-read {type(exc).__name__}"
        except SystemExit:
            rt = "n/a"
        print(f"  {name:5s} {label!r:8s} {rt:22s} | "
              f"{head[0][:60] if head else ''}")

print("\n== 4. every field cif_string writes, and whether it is quoted ==")
import inspect
src = inspect.getsource(cif_writer)
import re
quoted = set(re.findall(r'_quote\(([^)]*)\)', src))
print(f"  _quote is called on: {sorted(quoted)}")
print(f"  _quote definitions in xtal/io: "
      f"{src.count('def _quote')} in cif_writer.py")

print("\n== 5. what a label with an apostrophe becomes ==")
print(f"  _quote(\"Na'1\") = {cif_writer._quote(chr(78)+chr(97)+chr(39)+chr(49))!r}")
print(f"  temp dir: {TMP}")
