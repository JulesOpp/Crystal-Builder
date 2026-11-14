import cProfile, pstats, io, time
import numpy as np
from PySide6.QtCore import QEventLoop
from xtal.commands.atoms import MoveSites
app.processEvents(QEventLoop.AllEvents, 5000)
pr = cProfile.Profile(); pr.enable()
for n in range(10):
    doc.run(MoveSites({0: np.array([1e-5, 0.0, 0.0])}))
    doc.break_merge()
pr.disable()
app.processEvents(QEventLoop.AllEvents, 5000)
s = io.StringIO(); pstats.Stats(pr, stream=s).sort_stats("tottime").print_stats(12)
print("\n".join(s.getvalue().splitlines()[4:22]))
