"""Is Structure.add_bond quadratic?  Reduce to P1 adds every bond."""
import time
from xtal.io import FORMATS
from xtal.core import symmetry, bonding, p1

for name in ("MOF-5", "MFU4l", "HKUST1", "Ni2Cl2BTDD"):
    s = FORMATS.read(f"resources/samples/{name}.cif")
    cell = p1.expand(s)
    n_bonds = len(bonding.perceive(s))
    s.recompute_bonds = None
    t = time.perf_counter()
    out = symmetry.reduce_to_p1(s)
    bare = time.perf_counter() - t
    # now with the bonds present, as the GUI has them
    s2 = FORMATS.read(f"resources/samples/{name}.cif")
    bonding.perceive(s2)
    from xtal.commands.symmetry import ReduceToP1
    t = time.perf_counter()
    try:
        out2 = ReduceToP1().apply_to(s2)
        withb = time.perf_counter() - t
        nb = len(out2.bonds) if hasattr(out2, "bonds") else "?"
    except Exception as e:
        withb, nb = float("nan"), f"{type(e).__name__}"
    print(f"{name:12s} {cell.n_atoms:5d} atoms {n_bonds:5d} bonds  "
          f"reduce_to_p1 bare {bare*1000:8.1f} ms   "
          f"ReduceToP1 cmd {withb*1000:8.1f} ms  -> {nb} bonds")

print()
print("add_bond scaling, synthetic (P1 chain):")
from xtal import Structure, Site, Lattice, Bond
import numpy as np
for n in (200, 400, 800, 1600, 3200):
    lat = Lattice.from_parameters(200.0, 200.0, 200.0, 90, 90, 90)
    sites = [Site("C", (0.001 * i, 0.0, 0.0)) for i in range(n)]
    st = Structure(lattice=lat, sites=sites)
    t = time.perf_counter()
    for i in range(n - 1):
        st.add_bond(Bond(i, i + 1))
    dt = time.perf_counter() - t
    print(f"  n={n:5d} bonds: {dt*1000:8.1f} ms  "
          f"({dt/ (n-1) * 1e6:7.1f} us/bond)")
