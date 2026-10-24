import cProfile, pstats, sys, time, gc
import numpy as np, psutil
from xtal.io import FORMATS
from xtal.core import p1, bonding
from xtal.ff.registry import ENGINES

name = sys.argv[1]
s = FORMATS.read(f"resources/samples/{name}.cif")
cell = p1.expand(s)
b = bonding.perceive(s)
calc = ENGINES.build("uff", s)
print(f"{name}: {cell.n_atoms} atoms, {len(b)} bonds")
for attr in dir(calc):
    if attr.startswith("__"): continue
    v = getattr(calc, attr, None)
    if isinstance(v, (list, tuple, np.ndarray)) and len(v) > 50:
        print(f"  calc.{attr:24s} len {len(v):>9,}  "
              f"{getattr(v,'nbytes',0)/2**20:8.1f} MB" if hasattr(v, "nbytes")
              else f"  calc.{attr:24s} len {len(v):>9,}")
pos, mat = cell.cart, np.asarray(s.lattice.matrix, float)
P = psutil.Process()
calc.compute(pos, mat)                              # warm
gc.collect(); r0 = P.memory_info().rss/2**20
ts = []
for _ in range(3):
    t = time.perf_counter(); calc.compute(pos, mat); ts.append(time.perf_counter()-t)
peak = P.memory_info().rss/2**20
print(f"compute: {min(ts):.3f} s (min of 3)   RSS {r0:.0f} -> {peak:.0f} MB")
pr = cProfile.Profile(); pr.enable(); calc.compute(pos, mat); pr.disable()
st = pstats.Stats(pr)
print("--- by cumulative ---"); st.sort_stats("cumulative").print_stats(14)
print("--- by tottime ---"); st.sort_stats("tottime").print_stats(12)
