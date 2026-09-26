# Written 2026-09-19 against Crystal-Builder source commit 3cd15e2 (v0.2.1).
# How much of xtal/ff/mace/calculator.py is about MACE, and how much
# is "drive an ASE calculator"?  The split decides whether a shared
# ASECalculatorEngine base would serve ORB-v3 / SevenNet / UMA /
# MatterSim, or whether each needs its own module.
# Run with .venv/bin/python.
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "xtal/ff/mace/calculator.py"
tree = ast.parse(SRC.read_text())
lines = SRC.read_text().splitlines()

# Named by reading each one: would this line be identical for a
# different ASE-calculator-backed model?
GENERIC = {
    "installed", "implements_stress", "forget_models", "_device",
    "MACECalculator._make_atoms", "MACECalculator.n_atoms",
    "MACECalculator.compute", "MACECalculator.__init__",
    "build",
}
SPECIFIC = {"_load_model", "available", "MACECalculator.summary"}


def span(node):
    return node.end_lineno - node.lineno + 1


rows = []
for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef):
        for child in node.body:
            if isinstance(child, ast.FunctionDef):
                rows.append((f"{node.name}.{child.name}", span(child)))
    elif isinstance(node, ast.FunctionDef):
        if not any(node is c for cls in tree.body
                   if isinstance(cls, ast.ClassDef)
                   for c in cls.body):
            rows.append((node.name, span(node)))

seen, g, s, u = set(), 0, 0, 0
for name, n in rows:
    if name in seen:
        continue
    seen.add(name)
    bucket = ("generic" if name in GENERIC else
              "MACE-only" if name in SPECIFIC else "?")
    print(f"  {n:4d} lines  {bucket:10s} {name}")
    g += n if bucket == "generic" else 0
    s += n if bucket == "MACE-only" else 0
    u += n if bucket == "?" else 0

print(f"\n{SRC.relative_to(ROOT)}: {len(lines)} lines total")
print(f"  generic (any ASE calculator): {g}")
print(f"  MACE-only:                    {s}")
print(f"  unclassified:                 {u}")
print(f"  module-level data + docstring: "
      f"{len(lines) - g - s - u}  (MODEL_CHOICES, ASL_MODELS, "
      f"OPTIONS, the ENGINES.register call, the 55-line docstring)")
