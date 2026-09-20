"""P1 (Ni-HITP): does the experimental axial angle minimise the cost,
and does the closed form find it without a scan?"""
import sys
from collections import Counter
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from common import load, env, unwrap, laterals, direction_cost   # noqa: E402

s, cell, g, el = load("resources/samples/NiHITP.cif")
M = cell.lattice.matrix
CART = np.asarray(cell.cart, dtype=float)
E = {i: env(g, el, i) for i in range(cell.n_atoms)}
NI = [i for i in range(cell.n_atoms) if el[i] == "Ni"]
AMINE_N = {i for i in range(cell.n_atoms) if el[i] == "N"}
keep = lambda i: (el[i] == "Ni" or i in AMINE_N or                  # noqa: E731
                  (el[i] == "H" and E[i] == ("N",)))


def nbr(pos, i, j, im):
    return CART[j] + np.asarray(im, float) @ M + (pos[i] - CART[i])


pos = unwrap(g, cell, NI[0], keep)
print(f"Ni block: {len(pos)} atoms {dict(Counter(el[i] for i in pos))}")

ns = [i for i in pos if i in AMINE_N]
# Pair the four N by whether their carbon partners are bonded together.
carbon = {}
for n in ns:
    j, im = next((j, im) for j, im in g.neighbors_with_images(n)
                 if el[j] == "C")
    carbon[n] = (j, im)
pairs, used = [], set()
for a in ns:
    if a in used:
        continue
    ja = carbon[a][0]
    partners = {k for k, _ in g.neighbors_with_images(ja)}
    b = next(x for x in ns if x != a and carbon[x][0] in partners)
    used |= {a, b}
    pairs.append((a, b))
print(f"attachments: {len(pairs)}, denticity {sorted({len(p) for p in pairs})}")

att = []
for a, b in pairs:
    mem = np.array([pos[a], pos[b]])
    par = np.array([nbr(pos, a, *carbon[a]), nbr(pos, b, *carbon[b])])
    att.append((mem, par))
print(f"member span  {np.linalg.norm(att[0][0][0]-att[0][0][1]):.3f} A"
      f"   partner span {np.linalg.norm(att[0][1][0]-att[0][1][1]):.3f} A")

# The rotation axis: the line through the two attachment centroids.
c0, c1 = att[0][0].mean(axis=0), att[1][0].mean(axis=0)
axis = (c1 - c0) / np.linalg.norm(c1 - c0)
origin = pos[NI[0]]
print(f"the two attachment axes are antiparallel to "
      f"{np.degrees(np.arccos(abs(np.dot(*[(a[1].mean(0)-a[0].mean(0)) / np.linalg.norm(a[1].mean(0)-a[0].mean(0)) for a in att])))):.2f} deg")


def turn(p, phi):
    k, v = axis, p - origin
    return (origin + v * np.cos(phi) + np.cross(k, v) * np.sin(phi)
            + k * np.dot(v, k) * (1 - np.cos(phi)))


def total(phi):
    out = 0.0
    for mem, par in att:
        m = np.array([turn(x, phi) for x in mem])
        mid = 0.5 * (m.mean(axis=0) + par.mean(axis=0))
        ax = par.mean(axis=0) - m.mean(axis=0)
        ax = ax / np.linalg.norm(ax)
        out += direction_cost(laterals(m, mid, ax), laterals(par, mid, ax))
    return out / len(att)


grid = np.linspace(0, 2 * np.pi, 3601)
vals = np.array([total(p) for p in grid])
k = int(np.argmin(vals))
print(f"\nscan: min {vals[k]:.6f} at {np.degrees(grid[k]):7.2f} deg"
      f"   max {vals.max():.6f} at {np.degrees(grid[int(np.argmax(vals))]):.2f} deg")
print(f"      value at the experimental angle (0 deg): {total(0.0):.6f}")

# Closed form, with no scan.
e1 = np.cross(axis, [1.0, 0.0, 0.0])
if np.linalg.norm(e1) < 1e-6:
    e1 = np.cross(axis, [0.0, 1.0, 0.0])
e1 /= np.linalg.norm(e1)
e2 = np.cross(axis, e1)
acc = 0j
for mem, par in att:
    mid = 0.5 * (mem.mean(axis=0) + par.mean(axis=0))
    ax = par.mean(axis=0) - mem.mean(axis=0)
    ax = ax / np.linalg.norm(ax)
    lm, lp = laterals(mem, mid, ax), laterals(par, mid, ax)
    lm = lm / np.linalg.norm(lm, axis=1)[:, None]
    lp = lp / np.linalg.norm(lp, axis=1)[:, None]
    zm = lm @ e1 + 1j * (lm @ e2)
    zp = lp @ e1 + 1j * (lp @ e2)
    if abs(np.sum(zm * np.conj(zp))) < abs(np.sum(zm * np.conj(zp[::-1]))):
        zp = zp[::-1]
    acc += np.sum(zp * np.conj(zm))
phi = float(np.angle(acc))
print(f"\nclosed form phi* = {np.degrees(phi):8.3f} deg"
      f"   cost there {total(phi):.6f}")
ok = total(phi) < vals[k] + 1e-6 and total(0.0) < vals[k] + 1e-6
print(f"\nverdict: {'CLOSED FORM FINDS THE CRYSTAL' if ok else 'WRONG'}")
