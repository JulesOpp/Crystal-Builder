"""Time every hot headless operation on one structure, with peak RSS."""
import gc, os, sys, time, tempfile
import numpy as np
import psutil

P = psutil.Process()
ROWS = []


def run(label, fn, note=""):
    gc.collect()
    r0 = P.memory_info().rss / 2**20
    t = time.perf_counter()
    try:
        out = fn()
        err = ""
    except Exception as exc:                       # noqa: BLE001
        out, err = None, f"{type(exc).__name__}: {exc}"[:70]
    dt = time.perf_counter() - t
    gc.collect()
    r1 = P.memory_info().rss / 2**20
    ROWS.append((label, dt, r1, r1 - r0, note or err))
    print(f"{label:34s} {dt:8.3f} s  RSS {r1:7.1f} (+{r1-r0:6.1f})  {note or err}")
    return out


name = sys.argv[1]
path = f"resources/samples/{name}.cif"
from xtal.io import FORMATS
from xtal.io.cif_writer import write_cif
from xtal.io import project as proj
from xtal.core import bonding, p1, symmetry, supercell
from xtal.commands.cell import Supercell
from xtal.ff.registry import ENGINES
from xtal.ff import optimize

s = run("FORMATS.read", lambda: FORMATS.read(path))
cell = run("p1.expand", lambda: p1.expand(s), f"{len(s.sites)} sites")
print(f"   -> {cell.n_atoms} P1 atoms")
run("p1.expand (memoised, 2nd)", lambda: p1.expand(s))
run("symmetry.detect", lambda: symmetry.detect(s))
p1s = run("symmetry.reduce_to_p1", lambda: symmetry.reduce_to_p1(s))
if p1s is not None:
    run("asymmetrize(from P1)", lambda: symmetry.asymmetrize(p1s))
g = run("bonding.graph", lambda: bonding.graph(s))
bonds = run("bonding.perceive", lambda: bonding.perceive(s))
print(f"   -> {len(bonds) if bonds else 0} bonds")
# cold perception: fresh structure so nothing is memoised
run("bonding.perceive (cold struct)",
    lambda: bonding.perceive(FORMATS.read(path)))
run("bonding.orders (cold struct)",
    lambda: bonding.orders(FORMATS.read(path)))
sc = run("supercell 2x2x2 (core)", lambda: supercell.supercell(s, 2, 2, 2))
run("Supercell(2,2,2).apply_to", lambda: Supercell(2, 2, 2).apply_to(s.copy()))
if sc is not None:
    run("p1.expand(supercell)", lambda: p1.expand(sc),
        f"{len(sc.sites)} sites")
    run("bonding.perceive(supercell)", lambda: bonding.perceive(sc))
calc = run('ENGINES.build("uff")', lambda: ENGINES.build("uff", s))
if calc is not None:
    run("uff compute (1 energy+forces)",
        lambda: calc.compute(p1.expand(s).cart, np.asarray(s.lattice.matrix, float)))
    def ten():
        n = 0
        for st in optimize.steps(calc, s, relax_cell=False):
            n += 1
            if n >= 10:
                break
        return n
    run("optimize 10 steps (atoms only)", ten)
tmp = tempfile.mkdtemp(prefix="perfprobe")
run("write_cif", lambda: write_cif(s, os.path.join(tmp, "o.cif")))
run("write_project (.xtalproj)",
    lambda: proj.write_project(s, os.path.join(tmp, "o.xtalproj")))
run("read_project", lambda: proj.read_project(os.path.join(tmp, "o.xtalproj")))
# Zeo++-free grid + isosurface, as the porosity run draws it
from xtal.analysis import grid as grids, isosurface as iso, porosity
shape = grids.shape_for(s.lattice)
print(f"   grid shape {shape} = {np.prod(shape):,} points")
field = run("grid.distance_grid", lambda: grids.distance_grid(
    s, porosity.zeo_radius), f"shape {shape}")
if field is not None:
    tri = run("isosurface march (probe 1.2)",
              lambda: iso.isosurface(field, s.lattice, 1.2))
    if tri:
        print(f"   -> {len(tri[1]):,} triangles")
from xtal.analysis import pxrd
run("PXRD reflections+pattern", lambda: pxrd.pattern(s)
    if hasattr(pxrd, "pattern") else pxrd.reflections(
        pxrd.to_small_structure(s), 1.5406, 5.0, 50.0, 0.0, None))
print()
print(f"| operation | {name} wall s | RSS after MB | dRSS MB | note |")
for label, dt, r1, dr, note in ROWS:
    print(f"| {label} | {dt:.3f} | {r1:.0f} | {dr:+.1f} | {note} |")
