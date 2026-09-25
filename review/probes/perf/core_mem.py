"""RSS and wall time of the headless core, step by step."""
import gc, os, sys, time
import psutil

P = psutil.Process(os.getpid())
_last = [0.0]


def mark(label):
    gc.collect()
    rss = P.memory_info().rss / 2**20
    print(f"{label:38s} RSS {rss:8.1f} MB   (+{rss - _last[0]:7.1f})")
    _last[0] = rss
    return rss


def timed(label, fn):
    gc.collect()
    before = P.memory_info().rss / 2**20
    t = time.perf_counter()
    out = fn()
    dt = time.perf_counter() - t
    gc.collect()
    after = P.memory_info().rss / 2**20
    print(f"{label:38s} {dt:8.3f} s   RSS {after:8.1f} MB  (+{after - before:7.1f})")
    _last[0] = after
    return out


path = sys.argv[1] if len(sys.argv) > 1 else "resources/samples/MFU4l.cif"
mark("interpreter")
import numpy  # noqa
mark("import numpy")
import xtal  # noqa
mark("import xtal")
from xtal.io import FORMATS
from xtal.core import bonding, p1, symmetry, supercell
from xtal.ff.registry import ENGINES
mark("import io/core/ff")

s = timed(f"FORMATS.read {os.path.basename(path)}", lambda: FORMATS.read(path))
print(f"   sites={len(s.sites)}  group={getattr(s.space_group, "hm", s.space_group)}")
cell = timed("p1.expand", lambda: p1.expand(s))
print(f"   P1 atoms={cell.n_atoms}")

try:
    info = timed("symmetry.detect", lambda: symmetry.detect(s))
    print("   " + info.summary()[:70])
except Exception as e:
    print(f"symmetry.detect                          FAILED: {e}")
g = timed("bonding.graph", lambda: bonding.graph(s))
b = timed("bonding.perceive (cold-ish)", lambda: bonding.perceive(s))
print(f"   bonds={len(b)}")
eng = timed('ENGINES.build("uff")', lambda: ENGINES.build("uff", s))
sc = timed("supercell 2x2x2", lambda: supercell.supercell(s, 2, 2, 2))
print(f"   supercell sites={len(sc.sites)}")
cell2 = timed("p1.expand(supercell)", lambda: p1.expand(sc))
print(f"   P1 atoms={cell2.n_atoms}")
cp = timed("50 x Structure.copy()", lambda: [s.copy() for _ in range(50)])
mark("end")
