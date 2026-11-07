"""One optimiser step on Ni2Cl2BTDD: time, thread count, CPU parallelism."""
import cProfile, os, pstats, sys, threading, time, resource
import numpy as np, psutil
from xtal.io import FORMATS
from xtal.core import p1, bonding
from xtal.ff.registry import ENGINES
from xtal.ff import optimize

name = sys.argv[1] if len(sys.argv) > 1 else "Ni2Cl2BTDD"
relax_cell = "--cell" in sys.argv
s = FORMATS.read(f"resources/samples/{name}.cif")
cell = p1.expand(s)
print(f"{name}: {cell.n_atoms} atoms, {len(bonding.perceive(s))} bonds, "
      f"relax_cell={relax_cell}")
calc = ENGINES.build("uff", s)
P = psutil.Process()
peak_threads = [threading.active_count()]
stop = [False]
def watch():
    while not stop[0]:
        peak_threads[0] = max(peak_threads[0], P.num_threads())
        time.sleep(0.02)
w = threading.Thread(target=watch, daemon=True); w.start()

def n_steps(n):
    c0 = P.cpu_times()
    t = time.perf_counter()
    k = 0
    for _ in optimize.steps(calc, s, relax_cell=relax_cell):
        k += 1
        if k >= n: break
    dt = time.perf_counter() - t
    c1 = P.cpu_times()
    cpu = (c1.user - c0.user) + (c1.system - c0.system)
    print(f"{n:3d} steps: {dt:6.3f} s wall  {dt/n:6.3f} s/step  "
          f"CPU {cpu:6.3f} s  parallelism {cpu/dt:4.2f}x  "
          f"OS threads {P.num_threads()}")
    return dt / n

n_steps(3)
per = n_steps(10)
stop[0] = True
print(f"peak OS threads: {peak_threads[0]}  "
      f"max RSS {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/2**20:.0f} MB")
pr = cProfile.Profile(); pr.enable()
k = 0
for _ in optimize.steps(calc, s, relax_cell=relax_cell):
    k += 1
    if k >= 5: break
pr.disable()
st = pstats.Stats(pr)
print("--- tottime, top 20 ---")
st.sort_stats("tottime").print_stats(20)
