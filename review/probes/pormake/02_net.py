# Written 2026-09-19 against Crystal-Builder 3cd15e2 (v0.2.1).
"""Contract MFU-4l's SBUs to vertices and ask the app what net it is."""
import numpy as np
from collections import defaultdict
from xtal.io import FORMATS
from xtal.core import bonding, p1
from xtal.analysis.topology import Edge, Net
from xtal.analysis import rcsr

s = FORMATS.read("resources/samples/MFU4l.cif")
cell = p1.expand(s)
g = bonding.graph(s)
lat = s.lattice
frac = cell.frac
el = [str(e) for e in cell.elements]

# --- the SBU: central Zn (site 2) plus everything reachable without
#     leaving metal/Cl/N-bound-to-metal.  Simpler: cluster = Zn + Cl.
centres = [a for a in range(cell.n_atoms) if int(cell.site_idx[a]) == 2]
print("central Zn (site 2) count:", len(centres))

# Map each Zn1/Cl to its nearest central Zn via bond graph BFS through
# Zn-N-Zn? No: Zn1 and Zn2 are not bonded.  Use geometry: assign each
# Zn1 to the nearest Zn2 image.
def nearest_centre(a):
    best, bi, bimg = 1e9, None, None
    fa = frac[a]
    for c in centres:
        d = fa - frac[c]
        img = np.round(d)
        v = lat.to_cart(d - img)
        r = np.linalg.norm(v)
        if r < best:
            best, bi, bimg = r, c, -img
    return bi, bimg, best

sbu = defaultdict(list)          # centre atom -> members
for a in range(cell.n_atoms):
    if el[a] in ("Zn", "Cl"):
        c, img, r = nearest_centre(a)
        sbu[c].append((a, img, r))
for c in sorted(sbu):
    rs = sorted(round(r, 3) for _, _, r in sbu[c])
    print("SBU at atom %3d: %d members, radii %s" % (c, len(sbu[c]), rs))
    break
print("number of SBUs:", len(sbu))

# --- edges: a linker joins two SBUs.  Walk the organic part.
centre_of = {}
for c, mem in sbu.items():
    for a, img, _ in mem:
        centre_of[a] = (c, img)

# an edge exists wherever a triazolate N binds a Zn; group the N by
# linker fragment (carbon skeleton)
# organic atoms = C,N,O,H
organic = [a for a in range(cell.n_atoms) if el[a] in ("C", "N", "O", "H")]
# build sub-graph of organic atoms with images
adj = defaultdict(list)
for b in g.bonds:
    i, j, im = b.i, b.j, tuple(int(v) for v in b.image)
    adj[i].append((j, np.array(im)))
    adj[j].append((i, -np.array(im)))

seen = set()
linkers = []
for a in organic:
    if a in seen:
        continue
    stack = [(a, np.zeros(3, int))]
    comp = {}
    while stack:
        x, off = stack.pop()
        if x in comp:
            continue
        comp[x] = off
        seen.add(x)
        for y, im in adj[x]:
            if el[y] in ("C", "N", "O", "H") and y not in comp:
                stack.append((y, off + im))
    linkers.append(comp)
print("organic fragments:", len(linkers),
      "sizes:", sorted({len(c) for c in linkers}))

edges = []
vid = {c: k for k, c in enumerate(sorted(sbu))}
for comp in linkers:
    ends = []
    for x, off in comp.items():
        for y, im in adj[x]:
            if el[y] == "Zn":
                c, cimg = centre_of[y]
                # image of the SBU centre relative to the linker's frame
                ends.append((vid[c], tuple((off + im + cimg).astype(int))))
    uniq = sorted(set(ends))
    if len(uniq) == 2:
        (u, iu), (v, iv) = uniq
        edges.append(Edge(u, v, tuple(np.array(iv) - np.array(iu))))
    else:
        print("  linker with %d distinct SBU contacts: %s"
              % (len(uniq), uniq))
    # how many Zn contacts per linker end?
    per = defaultdict(int)
    for e in ends:
        per[e] += 1
    if len(edges) == 1:
        print("  contacts per (SBU, image) for one linker:", dict(per))

print("edges:", len(edges))
net = Net(len(vid), tuple(edges))
print("degrees:", sorted({net.degree(v) for v in range(net.n_vertices)}))
report = rcsr.describe(net, rcsr.catalogue())
print("NET IDENTIFICATION:", report.sentence())
for ident in report.parts:
    print("   ", ident.verdict)
