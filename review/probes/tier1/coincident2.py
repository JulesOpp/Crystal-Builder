# Written 2026-09-19 against Crystal-Builder e35ebe1 (base 3cd15e2, v0.2.1).
"""Honest per-detector cost: each on a structure read fresh, so no
cached P1 expansion is shared between them."""
import time

import numpy as np

from xtal.core import neighbors, p1, symmetry
from xtal.io import FORMATS

SAMPLES = ["CFA1", "HKUST1", "MFU4l", "MIL53", "MOF-5",
           "Ni2Cl2BTDD", "UIO66", "ZIF-8", "zn_oac"]


def fresh(name):
    return FORMATS.read(f"resources/samples/{name}.cif")


def best(fn, name, reps=3):
    out = None
    t_best = float("inf")
    for _ in range(reps):
        s = fresh(name)
        t = time.perf_counter()
        out = fn(s)
        t_best = min(t_best, (time.perf_counter() - t) * 1000)
    return t_best, out


def expand_only(s):
    return p1.expand(s).n_atoms


def query_after_expand(s):
    cell = p1.expand(s)
    t = time.perf_counter()
    pairs = neighbors.neighbor_pairs(cell.frac, s.lattice,
                                     cutoff=1e-6, min_distance=0.0)
    query_after_expand.last = (time.perf_counter() - t) * 1000
    return int(np.count_nonzero(pairs.distance < 1e-6))


def a(s):
    return query_after_expand(s)


def b(s):
    return len(symmetry.duplicate_groups(s, 0.05))


print("each column is the best of 3, on a structure read fresh each time")
print(f"{'sample':12s} {'atoms':>6s} {'read':>7s} {'expand':>7s} "
      f"{'A tot':>7s} {'A query':>8s} {'pairs':>6s} "
      f"{'B tot':>7s} {'groups':>7s}")
for name in SAMPLES:
    t_read, s0 = best(lambda s: s, name)
    n_atoms = p1.expand(s0).n_atoms
    t_exp, _ = best(expand_only, name)
    t_a, n_pairs = best(a, name)
    t_b, n_groups = best(b, name)
    print(f"{name:12s} {n_atoms:6d} {t_read:7.2f} {t_exp:7.2f} "
          f"{t_a:7.2f} {query_after_expand.last:8.2f} {n_pairs:6d} "
          f"{t_b:7.2f} {n_groups:7d}")
