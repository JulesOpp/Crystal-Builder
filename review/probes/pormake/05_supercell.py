# Written 2026-09-19 against Crystal-Builder 3cd15e2 (v0.2.1).
"""Does the builder ever place two nodes of one type differently?

Builds pcu as a 2x2x2 supercell -- 8 node slots, the same count MFU-4l
has in its conventional cell -- with the catalogue's Kuratowski-like
block N457, and reports each placed node's orientation.
"""
import numpy as np, tempfile
from xtal.mof.build import import_pormake
from xtal.mof import catalog

pm = import_pormake()
c = catalog.Catalog.default()
topo = pm.Topology(str(c.topology("pcu").path))
print("pcu:", topo)
print("node types:", topo.node_types[topo.node_indices],
      " unique:", topo.unique_node_types)

big = topo * (2, 2, 2)
print("\n2x2x2:", big)
print("node slots:", list(big.node_indices))
print("node types:", big.node_types[big.node_indices],
      " unique:", big.unique_node_types)
print("n_node_types:", big.n_node_types)

# every node's local structure, as seen by the locator
print("\nlocal structures the locator is given:")
for i in big.node_indices:
    ls = big.local_structure(i)
    print("  slot %2d:" % i,
          np.round(np.array(sorted(map(tuple, np.round(ls.positions, 3)))), 2)
          .tolist())
    if i == big.node_indices[1]:
        break

# are they all identical?
ref = np.array(sorted(map(tuple, np.round(
    big.local_structure(big.node_indices[0]).positions, 4))))
same = all(np.allclose(ref, np.array(sorted(map(tuple, np.round(
    big.local_structure(i).positions, 4))))) for i in big.node_indices)
print("\nevery node slot's local structure identical?", same)

bb = pm.BuildingBlock(str(c.building_block("N457").path))
bbs = [None] * big.n_slots
for i in big.node_indices:
    bbs[i] = bb
fw = pm.Builder().build(big, bbs)
print("\nbuilt:", fw)

# ---- orientation of each placed node -------------------------------
at = fw.atoms
pos, sym = at.get_positions(), at.get_chemical_symbols()
cellm = at.get_cell()[:]
zn = [i for i, s in enumerate(sym) if s == "Zn"]
print("Zn atoms:", len(zn), "expected", 5 * 8)

# group Zn into clusters of 5 by mutual distance (min image)
import itertools
def mic(a, b):
    d = pos[a] - pos[b]
    f = np.linalg.solve(cellm.T, d)
    return cellm.T @ (f - np.round(f))

clusters, left = [], set(zn)
while left:
    seed = left.pop()
    grp = [seed]
    for j in list(left):
        if np.linalg.norm(mic(seed, j)) < 7.0:
            grp.append(j); left.discard(j)
    clusters.append(grp)
print("clusters:", len(clusters), "sizes:", sorted(len(g) for g in clusters))

print("\norientation signature of each placed node "
      "(signs of x*y*z of the 4 peripheral Zn, in the cell frame):")
sigs = []
for g in clusters:
    if len(g) != 5:
        print("  cluster of", len(g), "- skipped"); continue
    # central Zn = the one with the smallest sum of distances
    d = {a: sum(np.linalg.norm(mic(a, b)) for b in g) for a in g}
    ctr = min(d, key=d.get)
    v = np.array([mic(a, ctr) for a in g if a != ctr])
    u = v / np.linalg.norm(v, axis=1)[:, None]
    # express in the cell's own basis directions
    f = np.array([np.linalg.solve(cellm.T, w) for w in u])
    s = tuple(sorted(int(np.sign(np.prod(np.round(row, 3)))) for row in f))
    sigs.append(s)
    print("   centre atom %3d  signature %s  unit vectors %s"
          % (ctr, s, np.round(np.sort(f, axis=0), 2).tolist()))

print("\ndistinct orientations among the 8 nodes:", len(set(sigs)))
print("counts:", {k: sigs.count(k) for k in set(sigs)})
