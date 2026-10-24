# Written 2026-09-19 against Crystal-Builder 3cd15e2 (v0.2.1).
"""How many points does one MFU-4l linker end actually attach at?"""
import numpy as np
from collections import defaultdict, Counter
from xtal.io import FORMATS
from xtal.core import bonding, p1

s = FORMATS.read("resources/samples/MFU4l.cif")
cell, lat = p1.expand(s), s.lattice
frac, el = cell.frac, [str(e) for e in cell.elements]
g = bonding.graph(s)
adj = defaultdict(list)
for b in g.bonds:
    im = np.array([int(v) for v in b.image])
    adj[b.i].append((b.j, im)); adj[b.j].append((b.i, -im))

def cart(a, off=np.zeros(3)):
    return lat.to_cart(frac[a] + off)

centres = [a for a in range(cell.n_atoms) if int(cell.site_idx[a]) == 2]

# one organic fragment
seen, comp = set(), {}
start = next(a for a in range(cell.n_atoms) if el[a] == "O")
stack = [(start, np.zeros(3, int))]
while stack:
    x, off = stack.pop()
    if x in comp: continue
    comp[x] = off
    for y, im in adj[x]:
        if el[y] != "Zn" and y not in comp:
            stack.append((y, off + im))
print("one linker: %d atoms, %s" % (len(comp),
      Counter(el[a] for a in comp)))

# its contacts with metal
contacts = []
for x, off in comp.items():
    for y, im in adj[x]:
        if el[y] == "Zn":
            contacts.append((x, off, y, off + im))
print("\nZn contacts of this one linker: %d" % len(contacts))
for x, off, y, yoff in contacts:
    d = np.linalg.norm(cart(x, off) - cart(y, yoff))
    site = s.sites[int(cell.site_idx[y])].label
    print("   %s%-3d -- %s(%s)  %.3f A"
          % (el[x], x, el[y], site, d))

# group by SBU
def sbu_of(zn, zoff):
    best = None
    for c in centres:
        for dx in ((0,0,0),(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),
                   (0,0,-1),(1,1,0),(1,0,1),(0,1,1),(-1,-1,0),(-1,0,-1),
                   (0,-1,-1),(1,-1,0),(-1,1,0),(1,0,-1),(-1,0,1),
                   (0,1,-1),(0,-1,1),(1,1,1),(-1,-1,-1)):
            d = np.linalg.norm(cart(zn, zoff) - cart(c, np.array(dx)))
            if best is None or d < best[0]:
                best = (d, c, dx)
    return best

by_sbu = defaultdict(list)
for x, off, y, yoff in contacts:
    d, c, dx = sbu_of(y, yoff)
    by_sbu[(c, dx)].append((x, off, y, yoff))
print("\nthis linker touches %d SBUs; contacts per end: %s"
      % (len(by_sbu), [len(v) for v in by_sbu.values()]))

for (c, dx), group in by_sbu.items():
    ccart = cart(c, np.array(dx))
    pts = np.array([cart(x, off) for x, off, _, _ in group])
    mid = pts.mean(axis=0)
    axis = mid - ccart
    axis /= np.linalg.norm(axis)
    print("\n  SBU centre at %s" % np.round(ccart, 2))
    print("    %d attachment atoms, spread %.3f A"
          % (len(pts), max(np.linalg.norm(p - q) for p in pts
                           for q in pts)))
    print("    their centroid is %.3f A from the SBU centre"
          % np.linalg.norm(mid - ccart))
    for p, (x, off, _, _) in zip(pts, group):
        v = p - ccart
        ang = np.degrees(np.arccos(np.dot(v / np.linalg.norm(v), axis)))
        print("      %s%-3d  %.3f A from centre, %.2f deg off the axis"
              % (el[x], x, np.linalg.norm(v), ang))
    break

# the dioxin cut: how many bonds cross it?
print("\n--- the other place to cut: the C-O bonds of the dioxin ---")
ox = [a for a in comp if el[a] == "O"]
print("O atoms in the linker:", len(ox))
for o in ox:
    nb = [(y, im) for y, im in adj[o] if el[y] == "C"]
    print("   O%-3d bonds to %d carbons" % (o, len(nb)))
