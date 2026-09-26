import cProfile, pstats, io, time
from PySide6.QtCore import QEventLoop
app.processEvents(QEventLoop.AllEvents, 5000)
doc.select_all()
app.processEvents(QEventLoop.AllEvents, 5000)
print(f"{len(doc.selection.atoms)} atoms selected")
pr = cProfile.Profile(); pr.enable()
t = time.perf_counter(); doc.set_selected_bond_type(1.0)
dt = time.perf_counter() - t
pr.disable()
print(f"set_selected_bond_type(single): {dt*1000:.0f} ms (profiled)")
s = io.StringIO(); pstats.Stats(pr, stream=s).sort_stats("cumulative").print_stats(22)
print("\n".join(s.getvalue().splitlines()[4:30]))
