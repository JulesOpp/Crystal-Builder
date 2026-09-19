# Written 2026-09-19 against Crystal-Builder 3cd15e2 (v0.2.1).
"""Both MFU-4l node orientations fit a pcu vertex equally well."""
import numpy as np
from xtal.mof.build import import_pormake
from xtal.mof import catalog

pm = import_pormake()
from xtal.mof.pormake.locator import Locator
from xtal.mof.pormake.local_structure import LocalStructure

c = catalog.Catalog.default()
topo = pm.Topology(str(c.topology("pcu").path))
target = topo.local_structure(0)
print("pcu vertex target directions:")
print(np.round(target.positions, 3))

bb = pm.BuildingBlock(str(c.building_block("N457").path))
loc = Locator()
r0 = loc.calculate_rmsd(target, bb, max_n_slices=6)
print("\nN457 best RMSD onto a pcu vertex          : %.6f" % r0)

# the same block turned 90 degrees about z -- for a Td body inside an
# octahedral connection frame this is the *other* orientation
def turned(bb, axis, deg):
    b = bb.copy()
    t = np.radians(deg)
    ax = np.array(axis, float); ax /= np.linalg.norm(ax)
    K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
    R = np.eye(3) + np.sin(t) * K + (1 - np.cos(t)) * (K @ K)
    p = b.atoms.get_positions()
    ctr = p.mean(axis=0)
    b.atoms.set_positions((p - ctr) @ R.T + ctr)
    return b

for axis, deg in [((0, 0, 1), 90), ((0, 0, 1), 180), ((1, 1, 1), 120)]:
    b = turned(bb, axis, deg)
    print("  turned %3d deg about %s -> RMSD %.6f"
          % (deg, axis, loc.calculate_rmsd(target, b, max_n_slices=6)))

inv = bb.make_chiral_building_block()
print("  inverted (make_chiral_building_block) -> RMSD %.6f"
      % loc.calculate_rmsd(target, inv, max_n_slices=6))

# ---- the ideal Kuratowski case, with no block distortion in the way
print("\n--- ideal Kuratowski SBU on an ideal octahedral vertex ---")
oct_ = np.array([[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1]],
                float)
tgt = LocalStructure(oct_, list(range(6)))
tet_a = np.array([[1,1,1],[1,-1,-1],[-1,1,-1],[-1,-1,1]], float)
tet_b = -tet_a
print("tetrahedron A:", tet_a.tolist())
print("tetrahedron B (the flip):", tet_b.tolist())
# the rotation that carries A to B while fixing the octahedron
R = np.array([[0,-1,0],[1,0,0],[0,0,1]], float)      # 90 deg about z
print("90 deg about z maps A onto B?",
      sorted(map(tuple, np.round(tet_a @ R.T, 6)))
      == sorted(map(tuple, np.round(tet_b, 6))))
print("and maps the octahedron onto itself?",
      sorted(map(tuple, np.round(oct_ @ R.T, 6)))
      == sorted(map(tuple, np.round(oct_, 6))))
print("=> both orientations have identical connection-point RMSD (0.0);"
      " the objective cannot tell them apart.")

# ---- can a per-slot permutation force the other orientation? -------
print("\n--- does the permutation lever reach the other orientation? ---")
big = topo * (2, 2, 2)
bbs = [None] * big.n_slots
for i in big.node_indices:
    bbs[i] = bb
base_bb, base_perm, base_rmsd = loc.locate(target, bb, max_n_slices=6)
print("locate() perm:", base_perm, "rmsd %.4f" % base_rmsd)
for perm in ([0,1,2,3,4,5], [1,0,2,3,4,5], [2,3,0,1,4,5], [0,1,4,5,2,3]):
    lb, r = loc.locate_with_permutation(target, bb, np.array(perm))
    p = lb.atoms.get_positions()
    zn = [k for k, s in enumerate(lb.atoms.get_chemical_symbols())
          if s == "Zn"]
    ctr = p[zn].mean(axis=0)
    d = {a: np.linalg.norm(p[a] - ctr) for a in zn}
    cen = min(d, key=d.get)
    v = np.array([p[a] - p[cen] for a in zn if a != cen])
    u = np.array(sorted(map(tuple, np.round(
        v / np.linalg.norm(v, axis=1)[:, None], 2))))
    print("  perm %s rmsd %.4f  tetra %s" % (perm, r, u.tolist()))
