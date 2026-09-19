"""Line and method counts per banner section of a large file."""
import ast
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
lines = path.read_text().splitlines()
banners = [(i + 1, re.sub(r"^\s*#\s*", "", ln).strip())
           for i, ln in enumerate(lines)
           if re.match(r"^\s*#\s{2}[A-Z][A-Z ]+$", ln)]
bounds = [(0, "(head)")] + banners + [(len(lines) + 1, "(end)")]
tree = ast.parse(path.read_text())
defs = []
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        defs.append((node.lineno, node.end_lineno, node.name))
print(f"{path}  {len(lines)} lines")
for (start, name), (nxt, _) in zip(bounds, bounds[1:]):
    span = nxt - start
    inside = [d for d in defs if start <= d[0] < nxt]
    body = sum(d[1] - d[0] + 1 for d in inside if d[1] - d[0] + 1 < span)
    print(f"{span:>5} lines  {len(inside):>3} defs   {name}")
