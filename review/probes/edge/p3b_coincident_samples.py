"""Area 3b: two shipped samples expand with atoms at zero distance."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))

import numpy as np  # noqa: E402

from xtal.core import p1  # noqa: E402
from xtal.core.symmetry import (  # noqa: E402
    assign_wyckoff,
    detect,
    duplicate_groups,
    preview_merge,
    standardize,
)
from xtal.io import read_cif  # noqa: E402

ROOT = HERE.parents[3]


def zero_pairs(cell, lattice, tol=1e-6):
    frac = np.asarray(cell.frac)
    out = []
    for i in range(len(frac)):
        d = frac[i + 1:] - frac[i]
        d -= np.round(d)
        dist = np.linalg.norm(d @ lattice.matrix, axis=1)
        for k in np.nonzero(dist < tol)[0]:
            j = i + 1 + int(k)
            out.append((i, j, float(dist[k]),
                        cell.elements[i], cell.elements[j],
                        int(cell.site_idx[i]), int(cell.site_idx[j])))
    return out


for name in ("CFA1", "Ni2Cl2BTDD", "MFU4l", "HKUST1"):
    s = read_cif(ROOT / "resources" / "samples" / f"{name}.cif")
    cell = p1.expand(s)
    pairs = zero_pairs(cell, s.lattice)
    print("=" * 66)
    print(f"{name}: {s.space_group.short_name}, {len(s.sites)} sites, "
          f"{cell.n_atoms} atoms in the cell")
    print(f"  atom pairs closer than 1e-6 A: {len(pairs)}")
    for p in pairs[:6]:
        i, j, d, ei, ej, si, sj = p
        print(f"    atoms {i}/{j}  {ei}/{ej}  d={d:.3e}  "
              f"from sites {si} ({s.sites[si].label}) and "
              f"{sj} ({s.sites[sj].label})")
        print(f"      site {si} frac={s.sites[si].frac}")
        print(f"      site {sj} frac={s.sites[sj].frac}")
    for fn, label in ((detect, "detect"), (assign_wyckoff, "wyckoff"),
                      (standardize, "standardize")):
        try:
            fn(s)
            print(f"  {label:<12} ok")
        except Exception as exc:
            print(f"  {label:<12} {type(exc).__name__}: {exc}")
    groups = duplicate_groups(s, 0.05)
    print(f"  duplicate_groups(0.05) -> {groups}")
    print(f"  preview_merge(0.05)    -> {preview_merge(s, 0.05).message()}")
