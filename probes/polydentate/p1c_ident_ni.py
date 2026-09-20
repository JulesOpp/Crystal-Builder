"""Environments in Ni3(HITP)2, and whether the blocks come out right."""
from collections import Counter, defaultdict
import sys
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from common import load, env, unwrap   # noqa: E402

s, cell, g, el = load("resources/samples/NiHITP.cif")
print("cell   :", cell.lattice.parameters)
print("atoms  :", cell.n_atoms, dict(Counter(el)))
kinds = defaultdict(list)
for i in range(cell.n_atoms):
    kinds[(el[i], env(g, el, i))].append(i)
for (e, sig), v in sorted(kinds.items(), key=lambda kv: (kv[0][0], -len(kv[1]))):
    print(f"  {e:3s} {len(v):4d}  bonded to {sig}")
