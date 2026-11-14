"""Undo-stack memory and scene-build cost, in the real window."""
import gc, sys, time
import numpy as np, psutil
from PySide6.QtCore import QEventLoop
from xtal.core import p1
from xtalapp.viewport import builder
from xtal.commands.atoms import MoveSites
from xtal.commands.cell import Supercell

P = psutil.Process()
def drain(b=30000):
    app.processEvents(QEventLoop.AllEvents, b)

cell = p1.expand(doc.structure)
print(f"{len(doc.structure.sites)} sites, {cell.n_atoms} P1 atoms")

ts = []
for _ in range(3):
    t = time.perf_counter()
    model = builder.build_scene(doc.structure, doc.view,
                                selection=doc.selection,
                                planes=doc.planes_to_draw(),
                                pores=doc.pores, charges=doc.charges,
                                orbital=doc.orbital)
    ts.append(time.perf_counter() - t)
t = time.perf_counter(); viewport.scene.set_model(model)
setm = time.perf_counter() - t
t = time.perf_counter(); viewport.scene.set_positions(model)
setp = time.perf_counter() - t
print(f"build_scene {min(ts)*1000:7.1f} ms | scene.set_model "
      f"{setm*1000:6.1f} ms | scene.set_positions {setp*1000:6.1f} ms")
print(f"   model: {len(model.atom_positions) if hasattr(model,'atom_positions') else '?'} atom points")

gc.collect(); r0 = P.memory_info().rss / 2**20
print(f"stack: done={len(doc.stack._done)} undone={len(doc.stack._undone)} "
      f"RSS {r0:.1f} MB")
t = time.perf_counter()
for n in range(50):
    doc.run(MoveSites({0: np.array([1e-5, 0.0, 0.0])}))
    doc.break_merge()
dt = time.perf_counter() - t
drain(); gc.collect(); r1 = P.memory_info().rss / 2**20
print(f"50 x MoveSites: {dt:.3f} s ({dt/50*1000:.1f} ms each)  "
      f"done={len(doc.stack._done)}  RSS {r1:.1f} MB (+{r1-r0:.1f}, "
      f"{(r1-r0)*1024/50:.0f} KB/step)")
t = time.perf_counter()
for _ in range(50):
    doc.undo()
drain()
print(f"50 undos: {time.perf_counter()-t:.3f} s  "
      f"RSS {P.memory_info().rss/2**20:.1f} MB")
for _ in range(50):
    doc.redo()
drain()
# a whole-structure command: how much does one undo step hold?
gc.collect(); r2 = P.memory_info().rss / 2**20
from xtal.commands.symmetry import ReduceToP1
t = time.perf_counter(); doc.run(ReduceToP1()); dt = time.perf_counter()-t
drain(); gc.collect(); r3 = P.memory_info().rss / 2**20
print(f"ReduceToP1 (one StructureOperation undo step): {dt*1000:.0f} ms "
      f"RSS +{r3-r2:.1f} MB, structure now {len(doc.structure.sites)} sites")
t = time.perf_counter(); doc.run(Supercell(2, 2, 2)); dt = time.perf_counter()-t
drain(); gc.collect(); r4 = P.memory_info().rss / 2**20
print(f"Supercell(2,2,2): {dt*1000:.0f} ms  RSS +{r4-r3:.1f} MB, "
      f"{len(doc.structure.sites)} sites")
ts = []
for _ in range(2):
    t = time.perf_counter()
    model = builder.build_scene(doc.structure, doc.view,
                                selection=doc.selection)
    ts.append(time.perf_counter() - t)
t = time.perf_counter(); viewport.scene.set_model(model)
print(f"build_scene on {len(doc.structure.sites)} sites: "
      f"{min(ts)*1000:.0f} ms, set_model {(time.perf_counter()-t)*1000:.0f} ms")
print(f"final RSS {P.memory_info().rss/2**20:.0f} MB, "
      f"threads {P.num_threads()}")
