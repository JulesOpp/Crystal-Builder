import cProfile, pstats, sys, io, time, os, gc
import psutil
from xtal.io import FORMATS
from xtal.core import bonding
from xtal.ff.registry import ENGINES

path = sys.argv[1]
s = FORMATS.read(path)
b = bonding.perceive(s)
from xtal.core import p1
cell = p1.expand(s)
print(f"{os.path.basename(path)}: {cell.n_atoms} P1 atoms, {len(b)} bonds, "
      f"{2*len(b)/cell.n_atoms:.2f} avg degree")
P = psutil.Process()
gc.collect(); r0 = P.memory_info().rss/2**20
t = time.perf_counter()
calc = ENGINES.build("uff", s)
dt = time.perf_counter() - t
gc.collect(); r1 = P.memory_info().rss/2**20
print(f"build: {dt:.3f} s  RSS +{r1-r0:.1f} MB")
for attr in ("terms", "_terms", "bonds", "angles", "torsions", "inversions"):
    o = getattr(calc, attr, None)
    if o is not None:
        try: print(f"  calc.{attr}: {len(o)}")
        except TypeError: print(f"  calc.{attr}: {type(o).__name__}")
t = getattr(calc, "terms", None) or getattr(calc, "_terms", None)
if t is not None:
    for n in dir(t):
        if n.startswith("_"): continue
        v = getattr(t, n, None)
        if hasattr(v, "__len__") and not isinstance(v, str):
            print(f"  terms.{n}: {len(v)}")
pr = cProfile.Profile(); pr.enable()
ENGINES.build("uff", s)
pr.disable()
st = pstats.Stats(pr); st.sort_stats("cumulative")
st.print_stats(22)
