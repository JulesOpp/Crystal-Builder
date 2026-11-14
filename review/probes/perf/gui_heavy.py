"""Profile the expensive main-thread operations, and time supercell."""
import cProfile, pstats, time, io
import psutil
from PySide6.QtCore import QEventLoop
from xtal.core import p1
from xtal.commands.cell import Supercell

P = psutil.Process()


def drain(b=60000):
    t = time.perf_counter(); app.processEvents(QEventLoop.AllEvents, b)
    return time.perf_counter() - t


def act(n):
    a = win.actions_[n]
    assert a.isEnabled(), f"{n} disabled"
    a.trigger()


def profiled(label, fn, top=12):
    drain(2000)
    pr = cProfile.Profile(); pr.enable()
    t = time.perf_counter(); fn(); call = time.perf_counter() - t
    pr.disable()
    d = drain()
    print(f"\n##### {label}: call {call*1000:.1f} ms  drain {d*1000:.1f} ms"
          f"  RSS {P.memory_info().rss/2**20:.0f} MB")
    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats("tottime").print_stats(top)
    print("\n".join(s.getvalue().splitlines()[4:top + 10]))


print(f"{len(doc.structure.sites)} sites, "
      f"P1 {p1.expand(doc.structure).n_atoms} atoms")
act("select_all")
drain()
profiled("recompute_bonds", lambda: act("recompute_bonds"))
profiled("Set Bond Type: Single over 648 atoms",
         lambda: act("bond_type_single"))
profiled("Reduce to P1", lambda: act("reduce_p1"), top=14)

# Supercell 2x2x2 via the document, the way ask() does
t = time.perf_counter()
msg = doc.operate(Supercell(2, 2, 2))
call = time.perf_counter() - t
d = drain()
print(f"\n##### Supercell 2x2x2 (doc.operate): call {call*1000:.1f} ms "
      f"drain {d*1000:.1f} ms -> {len(doc.structure.sites)} sites, "
      f"P1 {p1.expand(doc.structure).n_atoms} atoms, "
      f"RSS {P.memory_info().rss/2**20:.0f} MB")
profiled("select_all on the 5184-site supercell", lambda: doc.select_all())
profiled("style -> polyhedra on supercell",
         lambda: act("style_polyhedra"))
profiled("style -> ball+stick on supercell",
         lambda: act("style_ball_stick"))
profiled("recompute_bonds on supercell",
         lambda: act("recompute_bonds"), top=14)
# undo cost
hist = [c for c in dir(doc) if "undo" in c.lower()]
print("undo API:", hist)
