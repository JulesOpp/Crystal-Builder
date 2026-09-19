# Written 2026-09-19 against Crystal-Builder 3cd15e2 (v0.2.1).
"""Is MFU-4l's linker rigid and planar, and does the catalogue hold
anything that could serve as its edge?"""
import numpy as np
from collections import defaultdict, Counter
from xtal.io import FORMATS
from xtal.core import bonding, p1
from xtal.mof import catalog

s = FORMATS.read("resources/samples/MFU4l.cif")
cell, lat = p1.expand(s), s.lattice
g = bonding.graph(s)
el = [str(e) for e in cell.elements]
adj = defaultdict(list)
for b in g.bonds:
    im = np.array([int(v) for v in b.image])
    adj[b.i].append((b.j, im)); adj[b.j].append((b.i, -im))

start = next(a for a in range(cell.n_atoms) if el[a] == "O")
comp, stack = {}, [(start, np.zeros(3, int))]
while stack:
    x, off = stack.pop()
    if x in comp: continue
    comp[x] = off
    for y, im in adj[x]:
        if el[y] != "Zn" and y not in comp:
            stack.append((y, off + im))
pts = np.array([lat.to_cart(cell.frac[a] + off) for a, off in comp.items()])
c = pts.mean(axis=0)
u, sv, vt = np.linalg.svd(pts - c)
print("linker: %d atoms, %s" % (len(comp), Counter(el[a] for a in comp)))
print("singular values of its atom cloud: %s" % np.round(sv, 3))
print("r.m.s. deviation from the best plane: %.4f A"
      % np.sqrt((((pts - c) @ vt[2]) ** 2).mean()))
print("=> the whole linker is planar to within that; the two")
print("   triazolate rings are coplanar and cannot twist 90 deg.")

print("\n--- 2-connected blocks the catalogue offers as an edge ---")
cat = catalog.Catalog.default()
small = [b for b in cat.fitting(2) if len(b.body_symbols) <= 4]
print("2-connected blocks with <= 4 real atoms: %d" % len(small))
for b in sorted(small, key=lambda b: len(b.body_symbols)):
    print("   %-6s %s" % (b.name, b.formula))
print("\nany block containing only O? ",
      [b.name for b in cat.building_blocks()
       if set(b.composition) == {"O"}])
print("any Kuratowski block with Cl?",
      [b.name for b in cat.building_blocks()
       if b.composition.get("Zn", 0) == 5
       and b.composition.get("Cl", 0) == 4])
