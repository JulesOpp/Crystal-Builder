# Written 2026-09-19 against Crystal-Builder 3cd15e2 (v0.2.1).
"""Prototype: choose the node orientation per vertex, from outside the
vendored code, using Builder.build's existing ``permutations`` argument.

Rule used here: on pcu, alternate the two orientation classes by the
parity of the vertex's integer position -- the checkerboard MFU-4l has.
"""
import itertools, numpy as np
from xtal.mof.build import import_pormake
from xtal.mof import catalog
from xtal.mof.pormake.locator import Locator

pm = import_pormake()
c = catalog.Catalog.default()
topo = pm.Topology(str(c.topology("pcu").path)) * (2, 2, 2)
bb = pm.BuildingBlock(str(c.building_block("N457").path))
loc = Locator()

def tetra(lb, frame=np.eye(3)):
    """The peripheral-Zn unit vectors of a located block, sorted."""
    p = lb.atoms.get_positions()
    zn = [k for k, s in enumerate(lb.atoms.get_chemical_symbols())
          if s == "Zn"]
    ctr = p[zn].mean(axis=0)
    cen = min(zn, key=lambda a: np.linalg.norm(p[a] - ctr))
    v = np.array([p[a] - p[cen] for a in zn if a != cen])
    u = v / np.linalg.norm(v, axis=1)[:, None]
    return tuple(sorted(map(tuple, np.round(u @ frame, 1))))

best = loc.calculate_rmsd(topo.local_structure(topo.node_indices[0]),
                          bb, max_n_slices=6)
print("minimum RMSD for this (slot, block): %.6f" % best)

# --- per slot: every permutation that ties for the minimum ----------
choices = {}
for i in topo.node_indices:
    target = topo.local_structure(i)
    got = {}
    for perm in itertools.permutations(range(6)):
        lb, r = loc.locate_with_permutation(target, bb, np.array(perm))
        if r < best * 1.0001:
            got.setdefault(tetra(lb), []).append(perm)
    choices[i] = got
    print("slot %2d: %d tied permutations, %d distinct orientations"
          % (i, sum(len(v) for v in got.values()), len(got)))

# --- the orientation classes, and a parity rule over them -----------
allo = sorted({k for g in choices.values() for k in g})
print("\norientation classes seen across all slots:", len(allo))

frac = np.array([np.linalg.solve(topo.atoms.get_cell()[:].T,
                                 topo.atoms.positions[i])
                 for i in topo.node_indices])
parity = {i: int(round(sum(f * 2))) % 2
          for i, f in zip(topo.node_indices, frac)}
print("vertex parities:", {int(k): v for k, v in parity.items()})

perms = {}
for i in topo.node_indices:
    want = allo[0] if parity[i] == 0 else allo[1]
    if want in choices[i]:
        perms[int(i)] = list(choices[i][want][0])
    else:                                   # fall back to any tie
        perms[int(i)] = list(next(iter(choices[i].values()))[0])
        print("  slot %d cannot reach class %d" % (i, parity[i]))
print("\nchosen permutations:", perms)

bbs = [None] * topo.n_slots
for i in topo.node_indices:
    bbs[i] = bb
fw = pm.Builder().build(topo, bbs, permutations=perms)

at = fw.atoms
pos, sym, cellm = at.get_positions(), at.get_chemical_symbols(), at.get_cell()[:]
def mic(a, b):
    d = pos[a] - pos[b]
    f = np.linalg.solve(cellm.T, d)
    return cellm.T @ (f - np.round(f))
zn = [i for i, s in enumerate(sym) if s == "Zn"]
clusters, left = [], set(zn)
while left:
    s0 = left.pop(); g = [s0]
    for j in list(left):
        if np.linalg.norm(mic(s0, j)) < 7.0:
            g.append(j); left.discard(j)
    clusters.append(g)

print("\nbuilt framework, orientation of each node:")
seen = {}
for g in sorted(clusters, key=min):
    d = {a: sum(np.linalg.norm(mic(a, b)) for b in g) for a in g}
    cen = min(d, key=d.get)
    v = np.array([mic(a, cen) for a in g if a != cen])
    u = tuple(sorted(map(tuple, np.round(
        v / np.linalg.norm(v, axis=1)[:, None], 1))))
    f = np.round(np.linalg.solve(cellm.T, pos[cen]) % 1, 2)
    cls = seen.setdefault(u, len(seen))
    print("   node at frac %s  ->  orientation class %d" % (f, cls))
print("\ndistinct orientations in the built framework:", len(seen))
