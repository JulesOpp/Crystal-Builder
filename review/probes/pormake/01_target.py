# Written 2026-09-19 against Crystal-Builder 3cd15e2 (v0.2.1).
"""What MFU-4l is, according to the app."""
import numpy as np
from collections import Counter, defaultdict
from xtal.io import FORMATS
from xtal.core import bonding, p1

s = FORMATS.read("resources/samples/MFU4l.cif")
print("space group :", s.space_group)
print("lattice     :", s.lattice)
print("sites (asym):", len(s.sites))
for i, st in enumerate(s.sites):
    print("   site %2d  %-4s %-3s  frac=%s  occ=%s" % (
        i, st.label, st.element, np.round(st.frac, 5), getattr(st, "occupancy", 1)))

cell = p1.expand(s)
print("P1 atoms    :", cell.n_atoms)
print("P1 formula  :", Counter([str(e) for e in cell.elements]))

g = bonding.graph(s)
print("bonds in P1 :", len(g.bonds))
coord = g.coordination()
by_site = defaultdict(list)
for a in range(cell.n_atoms):
    by_site[int(cell.site_idx[a])].append(int(coord[a]))
print("\ncoordination by site:")
for k in sorted(by_site):
    st = s.sites[k]
    nb = Counter()
    for a in cell.indices_of_site(k)[:1]:
        for j in g.neighbors(int(a)):
            nb[str(cell.elements[j])] += 1
    print("  site %2d %-5s %-3s  mult=%3d  CN=%s  neighbours of one=%s"
          % (k, st.label, st.element, len(by_site[k]),
             sorted(set(by_site[k])), dict(nb)))

frags = g.fragments()
print("\nfragments:", len(frags))
kinds = Counter()
for f in frags:
    kinds[(f.kind, len(f))] += 1
print(kinds)
