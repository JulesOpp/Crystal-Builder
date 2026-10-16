"""Does a project with real bonds cost O(n^2) to open?"""
import tempfile, time, os
from xtal.io import FORMATS, project as proj
from xtal.core import bonding, p1, symmetry
from xtal import Bond

tmp = tempfile.mkdtemp(prefix="projperf")
for name in ("MOF-5", "MFU4l", "HKUST1"):
    s = FORMATS.read(f"resources/samples/{name}.cif")
    cell = p1.expand(s)
    # store the perceived graph as explicit bonds, the way an edited
    # document ends up carrying them
    bonds = [Bond(b.i, b.j, b.image) for b in bonding.perceive(s)
             if b.i != b.j or b.image != (0, 0, 0)]
    p1s = symmetry.reduce_to_p1(s)
    try:
        p1s.set_bonds(bonds)
    except Exception as e:
        print(f"{name}: set_bonds failed {e}")
        continue
    path = os.path.join(tmp, f"{name}.xtalproj")
    t = time.perf_counter(); proj.write_project(p1s, path)
    w = time.perf_counter() - t
    t = time.perf_counter(); proj.read_project(path)
    r = time.perf_counter() - t
    size = os.path.getsize(path) / 1024
    print(f"{name:10s} {len(p1s.sites):5d} sites {len(bonds):5d} bonds  "
          f"write {w*1000:8.1f} ms  read {r*1000:9.1f} ms  {size:7.0f} KB")

print("\nreduce_to_p1 WITH stored bonds (the add_bond loop at symmetry.py:243):")
for name in ("MOF-5", "MFU4l", "HKUST1", "UIO66"):
    s = FORMATS.read(f"resources/samples/{name}.cif")
    bonds = [Bond(b.i, b.j, b.image) for b in bonding.perceive(s)]
    s.set_bonds(bonds[:len(s.sites) * 4])
    n = len(s.bonds)
    t = time.perf_counter()
    out = symmetry.reduce_to_p1(s)
    dt = time.perf_counter() - t
    print(f"{name:10s} {len(s.sites):4d} asym sites, {n:5d} stored bonds "
          f"-> {len(out.sites):5d} sites, {len(out.bonds):6d} bonds  "
          f"{dt*1000:9.1f} ms")
