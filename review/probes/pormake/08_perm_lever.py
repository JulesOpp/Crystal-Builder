# Written 2026-09-19 against Crystal-Builder 3cd15e2 (v0.2.1).
"""Every connection-point permutation that fits a pcu vertex, and how
many distinct node orientations they reach."""
import itertools, numpy as np
from xtal.mof.build import import_pormake
from xtal.mof import catalog

pm = import_pormake()
from xtal.mof.pormake.locator import Locator

c = catalog.Catalog.default()
topo = pm.Topology(str(c.topology("pcu").path))
target = topo.local_structure(0)
bb = pm.BuildingBlock(str(c.building_block("N457").path))
loc = Locator()

best = loc.calculate_rmsd(target, bb, max_n_slices=6)
print("best RMSD from the Euler scan: %.6f" % best)

def tetra_of(lb):
    p = lb.atoms.get_positions()
    zn = [k for k, s in enumerate(lb.atoms.get_chemical_symbols())
          if s == "Zn"]
    ctr = p[zn].mean(axis=0)
    cen = min(zn, key=lambda a: np.linalg.norm(p[a] - ctr))
    v = np.array([p[a] - p[cen] for a in zn if a != cen])
    u = v / np.linalg.norm(v, axis=1)[:, None]
    return tuple(sorted(map(tuple, np.round(u, 1))))

hits = {}
for perm in itertools.permutations(range(6)):
    lb, r = loc.locate_with_permutation(target, bb, np.array(perm))
    if r < best * 1.01:
        hits[perm] = (r, tetra_of(lb))
print("permutations within 1%% of the best: %d of 720" % len(hits))
orients = {}
for perm, (r, t) in hits.items():
    orients.setdefault(t, []).append((perm, round(r, 6)))
print("distinct node-body orientations they reach:", len(orients))
for k, v in orients.items():
    print("\n  orientation", np.array(k).tolist())
    print("    reached by %d permutation(s), e.g. %s (rmsd %.6f)"
          % (len(v), v[0][0], v[0][1]))
