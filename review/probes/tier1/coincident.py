# Written 2026-09-19 against Crystal-Builder e35ebe1 (base 3cd15e2, v0.2.1).
"""What a coincident-atom check on open would cost, and what it finds.

Three candidate detectors, timed against the cost of the read itself
on all nine shipped samples:
  A  neighbor_pairs over the P1 cell with min_distance=0 (a KD query)
  B  symmetry.duplicate_groups (orbit comparison, what Merge uses)
  C  symmetry.preview_merge    (what the dialog shows)
Plus what UFF does with an overlapped cell today.
"""
import time

import numpy as np

from xtal.core import neighbors, p1, symmetry
from xtal.io import FORMATS

SAMPLES = ["CFA1", "HKUST1", "MFU4l", "MIL53", "MOF-5",
           "Ni2Cl2BTDD", "UIO66", "ZIF-8", "zn_oac"]
ZERO = 1e-6


def coincident_pairs(structure, tol=ZERO):
    """Candidate A: every pair of cell atoms closer than ``tol``."""
    cell = p1.expand(structure)
    pairs = neighbors.neighbor_pairs(cell.frac, structure.lattice,
                                     cutoff=max(tol, 1e-6),
                                     min_distance=0.0)
    return int(np.count_nonzero(pairs.distance < tol)), cell.n_atoms


def ms(fn, *a):
    t = time.perf_counter()
    out = fn(*a)
    return (time.perf_counter() - t) * 1000.0, out


print(f"{'sample':12s} {'atoms':>6s} {'read ms':>8s} "
      f"{'A ms':>7s} {'pairs':>6s} {'B ms':>8s} {'dupgrp':>7s} "
      f"{'C ms':>8s} {'C says':>18s}")
for name in SAMPLES:
    path = f"resources/samples/{name}.cif"
    t_read, s = ms(FORMATS.read, path)
    t_a, (n_pairs, n_atoms) = ms(coincident_pairs, s)
    t_b, groups = ms(symmetry.duplicate_groups, s, 0.05)
    t_c, prev = ms(symmetry.preview_merge, s, 0.05)
    says = f"{prev.merged} sites"
    print(f"{name:12s} {n_atoms:6d} {t_read:8.1f} "
          f"{t_a:7.1f} {n_pairs:6d} {t_b:8.1f} {len(groups):7d} "
          f"{t_c:8.1f} {says:>18s}")

print("\n-- the check at a *chemical* floor rather than exactly zero --")
for tol in (1e-6, 0.05, 0.4):
    row = []
    for name in SAMPLES:
        s = FORMATS.read(f"resources/samples/{name}.cif")
        n, _ = coincident_pairs(s, tol)
        row.append(f"{name}={n}")
    print(f"  tol={tol:<8g} " + "  ".join(row))

print("\n-- what UFF does with one of them today --")
from xtal.ff.api import CalculatorError                      # noqa: E402
from xtal.ff.registry import ENGINES                         # noqa: E402

for name in ("Ni2Cl2BTDD", "MFU4l"):
    s = FORMATS.read(f"resources/samples/{name}.cif")
    engine = ENGINES.get("uff")
    try:
        t0 = time.perf_counter()
        calc = engine.build(s)
        built = (time.perf_counter() - t0) * 1000
        r = calc.compute(p1.expand(s).cart, s.lattice.matrix)
        print(f"  {name:12s} build {built:7.1f} ms  "
              f"E={r.energy:12.5g}  |F|max={r.max_force:9.2f}  "
              f"warnings={len(calc.warnings)}")
        for w in calc.warnings:
            print(f"      warning: {w[:78]}")
    except CalculatorError as exc:
        print(f"  {name:12s} refused: {exc}")
