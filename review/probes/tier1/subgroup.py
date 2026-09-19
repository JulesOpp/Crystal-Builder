# Written 2026-09-19 against Crystal-Builder e35ebe1 (base 3cd15e2, v0.2.1).
"""Can asymmetrize know it returned a subgroup, and what would it cost?

Question 1: is the group it *should* have found available where the
warning would be raised?  (The input structure's own space_group, and
what reduce_to_p1 leaves behind.)
Question 2: what does a symprec ladder cost on MFU-4l and the rest,
against one detect() at the default?
"""
import time

from xtal.core import symmetry
from xtal.io import FORMATS

SAMPLES = ["CFA1", "HKUST1", "MFU4l", "MIL53", "MOF-5",
           "Ni2Cl2BTDD", "UIO66", "ZIF-8", "zn_oac"]
LADDER = (1e-5, 1e-3, 1e-2, 5e-2, 1e-1)

print("== 1. what survives Reduce to P1 ==")
s = FORMATS.read("resources/samples/MFU4l.cif")
print(f"  before: space_group={s.space_group.short_name} "
      f"sites={len(s.sites)}  meta keys={sorted(s.meta)}")
p1s = symmetry.reduce_to_p1(s)
print(f"  after : space_group={p1s.space_group.short_name} "
      f"sites={len(p1s.sites)}  meta keys={sorted(p1s.meta)}")
print("  -> the group the file said is "
      + ("still on the structure" if p1s.space_group.number != 1
         else "GONE: nothing on the P1 structure remembers it"))

print("\n== 2. the round trip, and what each end says ==")
for name in SAMPLES:
    s = FORMATS.read(f"resources/samples/{name}.cif")
    before = s.space_group
    p1s = symmetry.reduce_to_p1(s)
    try:
        out, rep = symmetry.asymmetrize(p1s)
    except ValueError as exc:
        print(f"  {name:12s} RAISED {exc}")
        continue
    got = out.space_group
    flag = "SAME" if got.number == before.number else "DIFF"
    print(f"  {name:12s} {flag}  file={before.short_name}"
          f"(#{before.number}) -> found={got.short_name}"
          f"(#{got.number})  ok={rep.ok}  "
          f"order {before.order}->{got.order}  "
          f"sites {len(s.sites)}->{len(out.sites)}  "
          f"warnings={len(rep.warnings)}")

print("\n== 3. cost of one detect(), and of the whole ladder ==")
print(f"{'sample':12s} {'1 detect ms':>12s} {'ladder ms':>10s} "
      f"{'x':>5s}  groups found along the ladder")
for name in SAMPLES:
    s = FORMATS.read(f"resources/samples/{name}.cif")
    p1s = symmetry.reduce_to_p1(s)
    t = time.perf_counter()
    try:
        symmetry.detect(p1s, 1e-5)
    except ValueError:
        pass
    one = (time.perf_counter() - t) * 1000
    found = []
    t = time.perf_counter()
    for tol in LADDER:
        try:
            info = symmetry.detect(p1s, tol)
            found.append(f"{tol:g}:{info.international}(#{info.number})")
        except ValueError as exc:
            found.append(f"{tol:g}:FAIL")
    ladder = (time.perf_counter() - t) * 1000
    print(f"{name:12s} {one:12.1f} {ladder:10.1f} "
          f"{ladder / max(one, 1e-9):5.1f}  {' '.join(found)}")

print("\n== 4. the cheap version: one extra detect at 100x symprec ==")
for name in ("MFU4l", "MIL53", "MOF-5", "HKUST1"):
    s = FORMATS.read(f"resources/samples/{name}.cif")
    p1s = symmetry.reduce_to_p1(s)
    t = time.perf_counter()
    a = symmetry.detect(p1s, 1e-5)
    b = symmetry.detect(p1s, 1e-3)
    c = symmetry.detect(p1s, 1e-2)
    dt = (time.perf_counter() - t) * 1000
    print(f"  {name:10s} 1e-5:{a.international}(#{a.number},{a.n_orbits}) "
          f"1e-3:{b.international}(#{b.number},{b.n_orbits}) "
          f"1e-2:{c.international}(#{c.number},{c.n_orbits})  "
          f"three detects = {dt:.1f} ms")
