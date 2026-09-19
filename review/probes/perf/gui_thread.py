"""Main-thread cost of each GUI operation, via drive.py --script."""
import time
import psutil
from PySide6.QtCore import QEventLoop

P = psutil.Process()
ROWS = []


def drain(budget=60000):
    t = time.perf_counter()
    app.processEvents(QEventLoop.AllEvents, budget)
    return time.perf_counter() - t


def measure(label, fn):
    drain(2000)
    t = time.perf_counter()
    err = ""
    try:
        fn()
    except Exception as exc:                        # noqa: BLE001
        err = f"{type(exc).__name__}: {exc}"[:55]
    call = time.perf_counter() - t
    d = drain()
    rss = P.memory_info().rss / 2**20
    ROWS.append((label, call * 1000, d * 1000, rss, err))
    print(f"{label:36s} call {call*1000:8.1f} ms  drain {d*1000:7.1f} ms"
          f"  RSS {rss:6.0f} MB {err}")


def act(name):
    a = win.actions_[name]
    if not a.isEnabled():
        raise RuntimeError(f"{name} disabled")
    a.trigger()


scene = viewport.scene
rend = scene.renderer
rw = rend.GetRenderWindow()
from xtal.core import p1
print(f"structure: {len(doc.structure.sites)} sites, "
      f"P1 {p1.expand(doc.structure).n_atoms} atoms")
print(f"actors in renderer: {rend.GetActors().GetNumberOfItems()}  "
      f"props: {rend.GetViewProps().GetNumberOfItems()}")

measure("select_all", lambda: act("select_all"))
print(f"   selected {len(doc.selection.atoms)} atoms")
measure("recompute_bonds", lambda: act("recompute_bonds"))
measure("Set Bond Type: Single (whole sel)", lambda: act("bond_type_single"))
measure("Set Bond Type: Automatic", lambda: act("bond_type_automatic"))
measure("style -> polyhedra", lambda: act("style_polyhedra"))
measure("style -> wireframe", lambda: act("style_wireframe"))
measure("style -> ball and stick", lambda: act("style_ball_stick"))
measure("toggle dock (hide)", lambda: win.style_dock.setVisible(False))
measure("toggle dock (show)", lambda: win.style_dock.setVisible(True))
measure("select_none (partial refresh)", lambda: doc.select_none())
measure("select_all (partial refresh)", lambda: doc.select_all())

# scene rebuild, both halves
from xtalapp.viewport import builder
t = time.perf_counter()
model = builder.build_scene(doc, win.settings) if False else None
try:
    import inspect
    sig = inspect.signature(builder.build_scene)
    print(f"   build_scene{sig}")
except Exception as e:
    print(e)
measure("scene.set_model(current model)",
        lambda: scene.set_model(viewport.model))

# Render() counting
count = [0]
real = rw.Render
def counted(*a):
    count[0] += 1
    return real(*a)
rw.Render = counted
measure("recompute_bonds (Render counted)", lambda: act("recompute_bonds"))
print(f"   renderWindow.Render() calls: {count[0]}")
count[0] = 0
measure("select_none (Render counted)", lambda: doc.select_none())
print(f"   renderWindow.Render() calls: {count[0]}")
count[0] = 0
measure("select_all (Render counted)", lambda: doc.select_all())
print(f"   renderWindow.Render() calls: {count[0]}")
rw.Render = real

measure("Reduce to P1", lambda: act("reduce_p1"))
print(f"   now {len(doc.structure.sites)} sites, "
      f"actors {rend.GetActors().GetNumberOfItems()}")
from xtalapp.dialogs.supercell import SupercellDialog
SupercellDialog.ask = classmethod(lambda cls, *a, **k: (2, 2, 2))
measure("Supercell 2x2x2", lambda: win.supercell_dialog())
print(f"   now {len(doc.structure.sites)} sites, "
      f"P1 {p1.expand(doc.structure).n_atoms} atoms, "
      f"actors {rend.GetActors().GetNumberOfItems()}")
measure("select_all on supercell", lambda: doc.select_all())
measure("style -> polyhedra on supercell", lambda: act("style_polyhedra"))
measure("style -> ball+stick on supercell", lambda: act("style_ball_stick"))

print()
print("| operation | call ms | drain ms | total ms | RSS MB | note |")
for label, call, d, rss, err in ROWS:
    print(f"| {label} | {call:.1f} | {d:.1f} | {call+d:.1f} | {rss:.0f} | {err} |")
print(f"final RSS {P.memory_info().rss/2**20:.0f} MB")

import psutil as _ps
print(f"\nOS threads in the idle window: {_ps.Process().num_threads()}")
