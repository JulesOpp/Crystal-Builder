# Written 2026-09-19 against Crystal-Builder 3cd15e2 (v0.2.1).
"""Is every other Kuratowski node the inversion of its neighbour?"""
import numpy as np
from collections import defaultdict
from xtal.io import FORMATS
from xtal.core import bonding, p1

s = FORMATS.read("resources/samples/MFU4l.cif")
cell, lat = p1.expand(s), s.lattice
frac, el = cell.frac, [str(e) for e in cell.elements]
centres = [a for a in range(cell.n_atoms) if int(cell.site_idx[a]) == 2]

def offset(a, c):
    d = frac[a] - frac[c]
    return lat.to_cart(d - np.round(d))

# peripheral Zn (site 0) and Cl (site 1) around each centre
around = defaultdict(lambda: {"Zn": [], "Cl": []})
for a in range(cell.n_atoms):
    if el[a] not in ("Zn", "Cl"):
        continue
    best = min(centres, key=lambda c: np.linalg.norm(offset(a, c)))
    v = offset(a, best)
    r = np.linalg.norm(v)
    if 0.1 < r < 6.5:
        around[best][el[a]].append(v)

print("centre  frac(centre)          Zn1 tetrahedron unit vectors (sorted)")
sign = {}
for c in sorted(centres):
    v = np.array(around[c]["Zn"])
    u = np.round(v / np.linalg.norm(v, axis=1)[:, None], 3)
    u = np.array(sorted(map(tuple, u)))
    # signature: product of signs of the 4 vertices' (x*y*z)
    s_ = tuple(int(np.sign(np.prod(row))) for row in u)
    sign[c] = s_
    print("%4d  %s  %s  signs=%s" % (c, np.round(frac[c], 3), u.tolist(), s_))

print()
print("Two distinct orientations?", len(set(sign.values())))
groups = defaultdict(list)
for c, s_ in sign.items():
    groups[s_].append(c)
for k, v in groups.items():
    print("  orientation %s : centres %s, frac %s"
          % (k, v, [tuple(np.round(frac[a], 2)) for a in v]))

# Are the two orientations inversions of each other?
ks = list(groups)
if len(ks) == 2:
    A = np.array(sorted(map(tuple, np.round(
        np.array(around[groups[ks[0]][0]]["Zn"])
        / np.linalg.norm(around[groups[ks[0]][0]]["Zn"], axis=1)[:, None], 3))))
    B = np.array(sorted(map(tuple, np.round(
        np.array(around[groups[ks[1]][0]]["Zn"])
        / np.linalg.norm(around[groups[ks[1]][0]]["Zn"], axis=1)[:, None], 3))))
    print("\norientation A:", A.tolist())
    print("orientation B:", B.tolist())
    print("B == -A (as sets)?",
          sorted(map(tuple, np.round(-A, 3))) == sorted(map(tuple, B)))

# Neighbour relation: are adjacent SBUs (a/2 apart) always opposite?
print("\nneighbour check (SBUs 15.5 A apart):")
for c in sorted(centres)[:2]:
    for d in sorted(centres):
        if d == c:
            continue
        v = offset(d, c)
        if abs(np.linalg.norm(v) - lat.lengths[0] / 2) < 0.5:
            print("   %3d -> %3d  dist %.2f  same orientation? %s"
                  % (c, d, np.linalg.norm(v), sign[c] == sign[d]))
