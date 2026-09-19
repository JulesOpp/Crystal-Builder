# Written 2026-09-19 against Crystal-Builder 3cd15e2 (v0.2.1).
"""Orientation of every node PORMAKE places on a 2x2x2 pcu cell."""
import numpy as np
from xtal.mof.build import import_pormake
from xtal.mof import catalog

pm = import_pormake()
c = catalog.Catalog.default()
topo = pm.Topology(str(c.topology("pcu").path)) * (2, 2, 2)
bb = pm.BuildingBlock(str(c.building_block("N457").path))
bbs = [None] * topo.n_slots
for i in topo.node_indices:
    bbs[i] = bb
fw = pm.Builder().build(topo, bbs)

at = fw.atoms
pos, sym, cellm = at.get_positions(), at.get_chemical_symbols(), at.get_cell()[:]
def mic(a, b):
    d = pos[a] - pos[b]
    f = np.linalg.solve(cellm.T, d)
    return cellm.T @ (f - np.round(f))

zn = [i for i, s in enumerate(sym) if s == "Zn"]
clusters, left = [], set(zn)
while left:
    seed = left.pop(); grp = [seed]
    for j in list(left):
        if np.linalg.norm(mic(seed, j)) < 7.0:
            grp.append(j); left.discard(j)
    clusters.append(grp)

def tetra(g):
    d = {a: sum(np.linalg.norm(mic(a, b)) for b in g) for a in g}
    ctr = min(d, key=d.get)
    v = np.array([mic(a, ctr) for a in g if a != ctr])
    u = v / np.linalg.norm(v, axis=1)[:, None]
    return ctr, np.array(sorted(map(tuple, np.round(u, 2))))

print("PORMAKE's 8 placed nodes, peripheral-Zn unit vectors (cartesian):")
sets = []
for g in sorted(clusters, key=lambda g: min(g)):
    ctr, u = tetra(g)
    key = tuple(map(tuple, u))
    sets.append(key)
    print("  centre %4d  centroid frac %s" %
          (ctr, np.round(np.linalg.solve(cellm.T, pos[ctr]) % 1, 2)),
          u.tolist())

uniq = list(dict.fromkeys(sets))
print("\ndistinct orientations PORMAKE produced:", len(uniq))
if len(uniq) == 2:
    A, B = np.array(uniq[0]), np.array(uniq[1])
    print("second is the inversion of the first?",
          np.allclose(np.array(sorted(map(tuple, np.round(-A, 2)))), B, atol=0.03))
