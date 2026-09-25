"""Methods that are nothing but a forward to a collaborator."""
import ast
import sys
from pathlib import Path

path = Path(sys.argv[1])
tree = ast.parse(path.read_text())
total = fwd = 0
targets = {}
for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
    for fn in cls.body:
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        total += 1
        body = [s for s in fn.body
                if not (isinstance(s, ast.Expr)
                        and isinstance(s.value, ast.Constant))]
        if len(body) != 1:
            continue
        stmt = body[0]
        call = None
        if isinstance(stmt, ast.Return) and isinstance(
                stmt.value, ast.Call):
            call = stmt.value
        elif isinstance(stmt, ast.Expr) and isinstance(
                stmt.value, ast.Call):
            call = stmt.value
        if call is None or not isinstance(call.func, ast.Attribute):
            continue
        owner = call.func.value
        if isinstance(owner, ast.Attribute) and isinstance(
                owner.value, ast.Name) and owner.value.id == "self":
            fwd += 1
            targets.setdefault(owner.attr, []).append(
                f"{fn.name}:{fn.lineno}")
print(f"{path}: {total} methods, {fwd} are a single forward "
      f"to self.<collaborator>")
for name, hits in sorted(targets.items(), key=lambda k: -len(k[1])):
    print(f"  self.{name:<18} {len(hits):>3}  {', '.join(h.split(':')[0] for h in hits)}")
