"""P2/P3/P5: the permutation lever, the tie set, and scaling.

P5  derive G from the X directions by Kabsch on ordered triples and
    check it against brute force over all n! permutations.
P2  every tied permutation must give the SAME rmsd and a DIFFERENT
    body placement, or the lever is inert.
P3  the ties must still be ties against the SCALED topology, which is
    what builder.py:392 relocates against.
"""
import itertools, logging, math, sys, warnings
import numpy as np
D = __file__.rsplit("/", 1)[0]
logging.disable(logging.CRITICAL)
warnings.filterwarnings("ignore")
from xtal.mof.pormake import BuildingBlock, Topology, Builder     # noqa: E402
from xtal.mof.pormake.locator import Locator                      # noqa: E402
from xtal.mof.catalog import database_root                        # noqa: E402

topo = Topology(str(database_root() / "topologies" / "pcu.cgd"))
node = BuildingBlock(f"{D}/blocks/MFU4l_node.xyz")
loc = Locator()
slot = int(topo.node_indices[0])
target = topo.local_structure(slot)
q = node.local_structure().atoms.positions
n = len(q)


def rotation_group(q, tol=1e-3):
    """Proper rotations that map the X direction set onto itself.

    Found by Kabsch on ordered triples -- n^3 candidates, never n!.
    The tolerance is not cosmetic: a block cut from a real crystal is
    octahedral to about a thousandth of a degree, not to machine
    precision, and at 1e-6 this returns only the identity.
    """
    n = len(q)
    base = next(t for t in itertools.permutations(range(n), 3)
                if abs(np.linalg.det(q[list(t)])) > 0.3)
    A = q[list(base)]
    out, seen = [], set()
    for t in itertools.permutations(range(n), 3):
        B = q[list(t)]
        if abs(np.linalg.det(B)) < 0.3:
            continue
        R = np.linalg.solve(A, B)
        if not np.allclose(R.T @ R, np.eye(3), atol=tol):
            continue
        if np.linalg.det(R) < 0:
            continue
        turned = q @ R
        g = []
        for k in range(n):
            d = np.linalg.norm(q - turned[k], axis=1)
            if d.min() > tol:
                g = None
                break
            g.append(int(np.argmin(d)))
        if g is None or len(set(g)) != n:
            continue
        if tuple(g) not in seen:
            seen.add(tuple(g))
            out.append((R, np.array(g)))
    return out


G = rotation_group(q)
print(f"P5: |G| from Kabsch-on-triples = {len(G)}  "
      f"(candidates examined: {n * (n - 1) * (n - 2)}, not {math.factorial(n)})")

rms_all = {p: loc.locate_with_permutation(target, node, np.array(p))[1]
           for p in itertools.permutations(range(n))}
best = min(rms_all.values())
vals = np.array(sorted(rms_all.values()))
print(f"    all {len(rms_all)} permutations: best {best:.3e}, "
      f"worst {vals[-1]:.3e}")
gaps = np.diff(vals)
k = int(np.argmax(gaps))
print(f"    biggest gap after rank {k + 1}: {vals[k]:.3e} -> {vals[k+1]:.3e}")
brute = {p for p, r in rms_all.items() if r <= vals[k] + 1e-12}
print(f"    permutations below that gap: {len(brute)}")

_, p0, r0 = loc.locate(target, node)
p0 = np.asarray(p0)
composed = {tuple(np.asarray(g)[p0]) for _, g in G}
print(f"    G composed with the baseline == brute-force tie set? "
      f"{composed == brute}")

# ---- P2 -----------------------------------------------------------
body = [i for i in range(node.n_atoms)
        if i not in set(node.connection_point_indices)]
rms, bodies = [], []
for _, g in G:
    placed, r = loc.locate_with_permutation(target, node,
                                            np.asarray(g)[p0])
    rms.append(r)
    bodies.append(placed.atoms.positions[body].copy())
rms = np.array(rms)
print(f"\nP2: baseline {list(p0)}  rmsd {r0:.3e}")
print(f"    rmsd spread over the {len(G)} candidates: "
      f"{rms.max() - rms.min():.3e}")
print(f"    max body displacement between candidates: "
      f"{max(np.abs(a - b).max() for a in bodies for b in bodies):.3f} A")
def key(b):
    """A placement's identity: its atom positions as an ordered set.

    Sorting each coordinate column on its own would destroy the atom
    correspondence and make every symmetry-related placement look the
    same, which is the opposite of what is being measured.
    """
    return tuple(sorted(tuple(np.round(r, 2)) for r in b))


classes = {}
for b in bodies:
    classes.setdefault(key(b), []).append(b)
print(f"    distinct body placements: {len(classes)}   "
      f"sizes {sorted(len(v) for v in classes.values())}")

# ---- P3 -----------------------------------------------------------
edge = BuildingBlock(f"{D}/blocks/MFU4l_linker.xyz")
fw = Builder().build_by_type(topo, {0: node}, {(0, 0): edge})
st = fw.info["topology"].local_structure(slot)
rms2 = np.array([loc.locate_with_permutation(st, node, np.asarray(g)[p0])[1]
                 for _, g in G])
others = np.array([r for p, r in
                   {pp: loc.locate_with_permutation(st, node, np.array(pp))[1]
                    for pp in itertools.permutations(range(n))}.items()
                   if tuple(p) not in composed])
print(f"\nP3: against the SCALED topology")
print(f"    the 24 candidates span {rms2.min():.3e} - {rms2.max():.3e}")
print(f"    everything else starts at {others.min():.3e}")
gap = others.min() / max(rms2.max(), 1e-15)
print(f"    separation {gap:.0f}x  -> ties "
      f"{'SURVIVE' if gap > 100 else 'BREAK'}")
