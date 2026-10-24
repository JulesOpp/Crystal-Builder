"""List the longest functions/methods in xtal/ and xtalapp/.

Reports line count and a cyclomatic-ish branch count (1 + number of
decision nodes) so "long" and "complicated" can be told apart.
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRANCH = (
    ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler,
    ast.With, ast.AsyncWith, ast.Assert, ast.IfExp, ast.comprehension,
    ast.BoolOp, ast.Match,
)


def branches(node):
    n = 1
    for sub in ast.walk(node):
        if isinstance(sub, BRANCH):
            n += 1
        elif isinstance(sub, ast.match_case):
            n += 1
    return n


def main(argv):
    top = int(argv[0]) if argv else 30
    rows = []
    for pkg in ("xtal", "xtalapp"):
        for path in sorted((ROOT / pkg).rglob("*.py")):
            if "pormake" in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text())
            except SyntaxError:
                continue
            stack = [(tree, None)]
            while stack:
                node, cls = stack.pop()
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, ast.ClassDef):
                        stack.append((child, child.name))
                    elif isinstance(
                        child, (ast.FunctionDef, ast.AsyncFunctionDef)
                    ):
                        lines = child.end_lineno - child.lineno + 1
                        name = (
                            f"{cls}.{child.name}" if cls else child.name
                        )
                        rows.append((
                            lines, branches(child),
                            str(path.relative_to(ROOT)),
                            child.lineno, name,
                        ))
                        stack.append((child, cls))
    rows.sort(reverse=True)
    print(f"{'lines':>5} {'br':>4}  location")
    for lines, br, path, lineno, name in rows[:top]:
        print(f"{lines:>5} {br:>4}  {path}:{lineno} {name}")
    print()
    print(f"total functions/methods: {len(rows)}")
    over = [r for r in rows if r[0] > 50]
    print(f"over 50 lines: {len(over)}")
    print(f"over 100 lines: {len([r for r in rows if r[0] > 100])}")


main(sys.argv[1:])
