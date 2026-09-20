"""P1 (MFU-4l): is the real node orientation the argmin of the joint cost?

Takes one Zn5Cl4(N3C2)6 node out of the crystal, applies each of the 24
proper rotations that leave its six connection directions alone, and
scores every one against the six linker ends the crystal actually gives
it.  If the identity is not among the minima, the objective is wrong.
"""
import itertools
import sys
from collections import Counter
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from common import load, env, unwrap, laterals, pair_cost   # noqa: E402

s, cell, g, el = load("resources/samples/MFU4l.cif")
M = cell.lattice.matrix
CART = np.asarray(cell.cart, dtype=float)
RING = {i for i in range(cell.n_atoms)
        if el[i] == "C" and env(g, el, i) == ("C", "C", "N")}
OCT = [i for i in range(cell.n_atoms)
       if el[i] == "Zn" and len(env(g, el, i)) == 6]
keep = lambda i: el[i] in ("Zn", "Cl", "N") or i in RING   # noqa: E731


def octahedral():
    """The 24 proper rotations of the cube: signed permutations, det +1."""
    out = []
    for perm in itertools.permutations(range(3)):
        for signs in itertools.product((1, -1), repeat=3):
            R = np.zeros((3, 3))
            for row, col in enumerate(perm):
                R[row, col] = signs[row]
            if np.linalg.det(R) > 0:
                out.append(R)
    return out


def attachments(pos):
    """[(members, partners)] for one node, as unwrapped positions."""
    out, done = [], set()
    for a in (i for i in pos if i in RING):
        if a in done:
            continue
        b = next(j for j, _ in g.neighbors_with_images(a)
                 if j in RING and j in pos and j != a)
        done |= {a, b}
        mem, par = [], []
        for c in (a, b):
            mem.append(pos[c])
            j, im = next((j, im) for j, im in g.neighbors_with_images(c)
                         if el[j] == "C" and j not in RING)
            par.append(CART[j] + np.asarray(im, float) @ M
                       + (pos[c] - CART[c]))
        out.append((np.array(mem), np.array(par)))
    return out


def cost(a, b):
    """Lateral mismatch of two member sets meeting across one joint."""
    mid = 0.5 * (a.mean(axis=0) + b.mean(axis=0))
    ax = b.mean(axis=0) - a.mean(axis=0)
    ax = ax / np.linalg.norm(ax)
    return pair_cost(laterals(a, mid, ax), laterals(b, mid, ax))


pos = unwrap(g, cell, OCT[0], keep)
centre = pos[OCT[0]]
att = attachments(pos)
print(f"node: {len(pos)} atoms {dict(Counter(el[i] for i in pos))}")
print(f"attachments: {len(att)}, denticity {sorted({len(m) for m, _ in att})}"
      f", span {np.linalg.norm(att[0][0][0] - att[0][0][1]):.3f} A")

# The linker ends are fixed: they belong to the linkers, not the node.
ends = [par for _, par in att]
dirs = [(p.mean(axis=0) - centre) / np.linalg.norm(p.mean(axis=0) - centre)
        for p in ends]

scores = []
for n, R in enumerate(octahedral()):
    turned = {i: centre + (p - centre) @ R.T for i, p in pos.items()}
    ta = attachments(turned)
    taxes = [(m.mean(axis=0) - centre) / np.linalg.norm(m.mean(axis=0) - centre)
             for m, _ in ta]
    total = 0.0
    for end, u in zip(ends, dirs):
        k = int(np.argmax([u @ t for t in taxes]))
        total += cost(ta[k][0], end)
    scores.append((total / len(ends), n, R))

scores.sort()
best = scores[0][0]
tied = [x for x in scores if x[0] < best + 1e-6]
worst = scores[-1][0]
identity = next(x for x in scores if np.allclose(x[2], np.eye(3)))

print(f"\n24 rotations scored (mean lateral mismatch per joint, A^2):")
for v, n, _ in scores[:3]:
    print(f"   best  {v:.6f}")
    break
print(f"   ...")
print(f"   worst {worst:.6f}")
print(f"\nrotations tied at the minimum : {len(tied)}")
print(f"identity's score              : {identity[0]:.6f}")
print(f"separation (worst / best)     : {worst / max(best, 1e-12):.1f}x")
ok = identity[0] < best + 1e-6
print(f"\nverdict: {'IDENTITY IS A MINIMUM' if ok else 'OBJECTIVE IS WRONG'}")
