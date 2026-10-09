# Written 2026-09-19 against Crystal-Builder 3cd15e2 (v0.2.1).
"""Try to build MFU-4l on pcu with the catalogue's best node block."""
import sys, tempfile, numpy as np
from pathlib import Path
from xtal.mof import catalog
from xtal.mof.build import BuildRequest, build as do_build


c = catalog.Catalog.default()
topo = c.topology("pcu")
print("topology:", topo.name, topo.summary())
print("slots:", [(s.label, s.token, s.coordination) for s in topo.slots()])

bb = c.building_block("N457")
print("\nN457:", bb.formula, bb.n_connections, "connections")
xs = np.array([bb.positions[i] for i in bb.connections])
body = np.array([bb.positions[i] for i in range(len(bb.symbols))
                 if i not in set(bb.connections)])
centre = body.mean(axis=0)
u = (xs - centre) / np.linalg.norm(xs - centre, axis=1)[:, None]
print("X directions from body centroid:")
for v in np.round(u, 3):
    print("   ", v)
print("|X - centroid| =", np.round(np.linalg.norm(xs - centre, axis=1), 3))
# nearest body atom to each X
for k, i in enumerate(bb.connections):
    d = np.linalg.norm(body - bb.positions[i], axis=1)
    print("  X%d nearest body atom at %.3f A" % (k, d.min()))

req = BuildRequest.parse("pcu", sys.argv[1] if len(sys.argv) > 1
                               else "N457", "")
print("\nrequest:", req.spelled(), "->", req.title())
with tempfile.TemporaryDirectory() as d:
    out = do_build(req, d, c, log=print, trace=None)
    print("\n--- OUTCOME ---")
    print("atoms:", out.n_atoms)
    print("max_rmsd:", out.max_rmsd, "mean_rmsd:", out.mean_rmsd)
    print("objective:", out.objective)
    print("joints:", out.joints)
    print("verdict:", out.verdict())
    print("net:", out.net_name, "agrees:", out.net_agrees)
    from collections import Counter
    from xtal.core import p1
    cell = p1.expand(out.structure)
    print("P1 atoms:", cell.n_atoms,
          Counter(str(e) for e in cell.elements))
    print("lattice:", out.structure.lattice)

print("\nangles between X directions (deg):")
import itertools
ang = [np.degrees(np.arccos(np.clip(np.dot(a, b), -1, 1)))
       for a, b in itertools.combinations(u, 2)]
print(np.round(sorted(ang), 1))
