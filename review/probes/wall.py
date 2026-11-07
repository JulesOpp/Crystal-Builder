"""How tight is the xtal/ <-> xtalapp/ wall, in both directions?

(a) import every xtal submodule (not just the package) in one
    subprocess and report any Qt/VTK/matplotlib that arrived.
(b) list every xtal.* import made from xtalapp/, grouped, so the
    reverse direction (crystallography reasoning in the shell) can
    be judged.
"""
import ast
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = ["PySide6", "PyQt5", "PyQt6", "PySide2", "vtk",
             "vtkmodules", "matplotlib", "pyqtgraph", "xtalapp",
             "tkinter", "wx", "qtpy"]

mods = []
for path in sorted((ROOT / "xtal").rglob("*.py")):
    if "pormake" in path.parts or "modules/data" in str(path):
        continue
    rel = path.relative_to(ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    mods.append(".".join(parts))

code = (
    "import importlib, sys\n"
    f"mods = {mods!r}\n"
    "failed = []\n"
    "for m in mods:\n"
    "    try:\n"
    "        importlib.import_module(m)\n"
    "    except Exception as exc:\n"
    "        failed.append((m, type(exc).__name__))\n"
    f"bad = sorted(set(m.split('.')[0] for m in sys.modules) & set({FORBIDDEN!r}))\n"
    "print('MODULES', len(mods))\n"
    "print('FAILED', failed)\n"
    "print('FORBIDDEN_LOADED', bad)\n"
)
out = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                     capture_output=True, text=True)
print(out.stdout or out.stderr[-2000:])

print("=== xtal.* imports made from xtalapp/ ===")
counts = Counter()
where = {}
for path in sorted((ROOT / "xtalapp").rglob("*.py")):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        mod = None
        if isinstance(node, ast.ImportFrom) and node.module:
            mod = node.module
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("xtal.") or a.name == "xtal":
                    counts[a.name] += 1
                    where.setdefault(a.name, []).append(
                        f"{path.relative_to(ROOT)}:{node.lineno}")
            continue
        if mod and (mod == "xtal" or mod.startswith("xtal.")):
            counts[mod] += 1
            where.setdefault(mod, []).append(
                f"{path.relative_to(ROOT)}:{node.lineno}")
for mod, n in counts.most_common():
    print(f"{n:>3}  {mod}")
print(f"\n{len(counts)} distinct xtal modules imported by xtalapp")
