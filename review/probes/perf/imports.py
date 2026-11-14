import subprocess, sys, statistics
PY = ".venv/bin/python"
mods = ["numpy", "scipy.spatial", "spglib", "PySide6.QtWidgets",
        "vtkmodules.vtkRenderingOpenGL2", "xtal", "xtal.core.bonding",
        "xtalapp.mainwindow", "xtalapp.viewport.widget", "xtalapp.main",
        "rdkit.Chem", "matplotlib.pyplot", "ase"]
import time
for m in mods:
    ts = []
    for _ in range(3):
        t = time.perf_counter()
        r = subprocess.run([PY, "-c", f"import {m}"], capture_output=True)
        ts.append(time.perf_counter() - t)
    ok = "" if r.returncode == 0 else "  (FAILED)"
    print(f"{m:35s} {min(ts):6.3f} s (min of 3){ok}")
