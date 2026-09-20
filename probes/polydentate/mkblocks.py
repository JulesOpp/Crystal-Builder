"""Cut the four blocks out of the two crystals and write them as .xyz.

A headless rehearsal of the Phase 7 authoring recipe.  Which severed
bonds form one attachment is stated per block rather than inferred --
that grouping is the user's act, which is why the plan gives it its own
command instead of guessing.
"""
import os
import sys
from collections import Counter
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from common import load, env, unwrap   # noqa: E402

OUT = __file__.rsplit("/", 1)[0] + "/blocks"
DIST = 0.75


def block(cif, seed_kind, keeps, link, name):
    s, cell, g, el = load(cif)
    M = cell.lattice.matrix
    CART = np.asarray(cell.cart, dtype=float)
    E = {i: env(g, el, i) for i in range(cell.n_atoms)}
    keep = keeps(el, E)
    seed = next(i for i in range(cell.n_atoms) if seed_kind(el, E, i))
    pos = unwrap(g, cell, seed, keep)
    order = sorted(pos)
    at = {a: k for k, a in enumerate(order)}

    def outside(a):
        return [(j, im) for j, im in g.neighbors_with_images(a)
                if j not in pos]

    def place(a, j, im):
        return CART[j] + np.asarray(im, float) @ M + (pos[a] - CART[a])

    severed = [a for a in order if outside(a)]
    pairs, done = [], set()
    for a in severed:
        if a in done:
            continue
        b = link(g, el, pos, outside, a, [x for x in severed
                                          if x != a and x not in done])
        done |= {a, b}
        pairs.append((a, b))

    symbols = [el[a] for a in order]
    cart = [pos[a] for a in order]
    bonds = [(at[a], at[j], "S") for a in order
             for j, _ in g.neighbors_with_images(a)
             if j in pos and at[j] > at[a]]
    for a, b in pairs:
        mem = np.array([pos[a], pos[b]])
        par = np.array([place(c, j, im) for c in (a, b)
                        for j, im in outside(c)])
        u = par.mean(axis=0) - mem.mean(axis=0)
        cart.append(mem.mean(axis=0) + DIST * u / np.linalg.norm(u))
        symbols.append("X")
        k = len(symbols) - 1
        bonds += [(at[a], k, "S"), (at[b], k, "S")]

    body = len(order)
    centre = np.mean(cart[:body], axis=0)
    cart = [p - centre for p in cart]
    os.makedirs(OUT, exist_ok=True)
    lines = [str(len(symbols)),
             "".join(f"{i:5d}" for i in range(body, len(symbols)))]
    lines += [f"{sy:2s} {p[0]:14.8f} {p[1]:14.8f} {p[2]:14.8f}"
              for sy, p in zip(symbols, cart)]
    lines += [f"{i:5d} {j:5d} {t}" for i, j, t in bonds]
    open(f"{OUT}/{name}.xyz", "w", encoding="utf-8").write(
        "\n".join(lines) + "\n")
    formula = "".join(f"{k}{v}" for k, v in
                      sorted(Counter(symbols[:body]).items()))
    print(f"  {name:16s} {body:3d} body + {len(pairs)} X   {formula:24s}"
          f" denticity {sorted({2})}  {len(bonds)} bonds")


def bonded_members(g, el, pos, outside, a, rest):
    """The other member is bonded to this one."""
    near = {j for j, _ in g.neighbors_with_images(a)}
    return next(x for x in rest if x in near)


def bonded_partners(g, el, pos, outside, a, rest):
    """The two members' severed partners are bonded to each other."""
    mine = {j for j, _ in outside(a)}
    for x in rest:
        for j, _ in outside(x):
            if {k for k, _ in g.neighbors_with_images(j)} & mine:
                return x
    raise LookupError(a)


def shared_partner_neighbour(g, el, pos, outside, a, rest):
    """The two members' partners are bonded to one common atom.

    Ni3(HITP)2's chelate: two carbons hand their nitrogens to the same
    nickel, and those nitrogens are not bonded to one another.
    """
    def around(m):
        out = set()
        for j, _ in outside(m):
            out |= {k for k, _ in g.neighbors_with_images(j)
                    if k not in pos}
        return out

    mine = around(a)
    for x in rest:
        if mine & around(x):
            return x
    raise LookupError(a)


print("MFU-4l:")
block("resources/samples/MFU4l.cif",
      lambda el, E, i: el[i] == "Zn" and len(E[i]) == 6,
      lambda el, E: (lambda i: el[i] in ("Zn", "Cl", "N") or
                     (el[i] == "C" and E[i] == ("C", "C", "N"))),
      bonded_members, "MFU4l_node")
block("resources/samples/MFU4l.cif",
      lambda el, E, i: el[i] == "O",
      lambda el, E: (lambda i: el[i] in ("O", "H") or
                     (el[i] == "C" and E[i] != ("C", "C", "N"))),
      bonded_partners, "MFU4l_linker")

print("Ni-HITP:")
block("resources/samples/NiHITP.cif",
      lambda el, E, i: el[i] == "Ni",
      lambda el, E: (lambda i: el[i] in ("Ni", "N") or
                     (el[i] == "H" and E[i] == ("N",))),
      bonded_partners, "NiHITP_node")
block("resources/samples/NiHITP.cif",
      lambda el, E, i: el[i] == "C" and E[i] == ("C", "C", "C"),
      lambda el, E: (lambda i: el[i] == "C" or
                     (el[i] == "H" and E[i] == ("C",))),
      shared_partner_neighbour, "NiHITP_linker")
