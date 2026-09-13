"""Print the shape of a Python file without printing the file.

``document.py`` is 2000 lines and a question about it is usually "which
method, and where".  Reading it whole to answer that costs the whole
file; this prints one line per class, method and function -- line
number, signature, first sentence of the docstring -- so the answer is a
``Read`` with an offset.

    outline.py xtalapp/document.py              # one file
    outline.py xtalapp/docks                    # every file under a folder
    outline.py xtalapp/document.py --grep bond  # names matching a pattern
    outline.py --find merge_atoms               # where a name is defined
    outline.py --find Document --in xtalapp     # ... under one folder

Standard library only, and it never imports what it reads: an outline of
a module that would pull in Qt or VTK costs nothing and cannot hang.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
#: Never outlined or searched: vendored code has its own shape and is
#: not ours to navigate, and the rest is generated.
SKIP = ("xtal/mof/pormake/", "/build/", "/dist/", "__pycache__",
        ".claude/worktrees/", "archive/", ".venv")


def _python_files(target: Path):
    if target.is_file():
        yield target
        return
    for path in sorted(target.rglob("*.py")):
        rel = "/" + path.relative_to(ROOT).as_posix()
        if not any(s in rel for s in SKIP):
            yield path


def _first_sentence(node) -> str:
    doc = ast.get_docstring(node) or ""
    text = " ".join(doc.split("\n\n", 1)[0].split())
    match = re.match(r"(.+?[.!?])(\s|$)", text)
    text = match.group(1) if match else text
    return text if len(text) <= 90 else text[:87] + "..."


def _signature(node) -> str:
    args = node.args
    names = [a.arg for a in args.posonlyargs + args.args]
    if names and names[0] in ("self", "cls"):
        names = names[1:]
    if args.vararg:
        names.append("*" + args.vararg.arg)
    elif args.kwonlyargs:
        names.append("*")
    names += [a.arg for a in args.kwonlyargs]
    if args.kwarg:
        names.append("**" + args.kwarg.arg)
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"({', '.join(names)}){returns}"


def _decorations(node) -> str:
    names = []
    for d in node.decorator_list:
        name = ast.unparse(d)
        if name in ("property", "staticmethod", "classmethod") or \
                name.endswith(".setter"):
            names.append(name.split(".")[-1])
    return f"[{','.join(names)}] " if names else ""


def outline(path: Path, pattern=None, docs=True) -> list[str]:
    try:
        tree = ast.parse(path.read_text(), str(path))
    except SyntaxError as exc:
        return [f"  (does not parse: {exc})"]
    rows = []

    def emit(node, depth, owner=""):
        name = node.name
        if pattern and not pattern.search(name):
            return
        # Filtered, a method has lost the class line above it.
        shown = f"{owner}.{name}" if pattern and owner else name
        if isinstance(node, ast.ClassDef):
            bases = ", ".join(ast.unparse(b) for b in node.bases)
            head = f"class {shown}({bases})" if bases else f"class {shown}"
        else:
            head = f"{_decorations(node)}def {shown}{_signature(node)}"
        doc = _first_sentence(node) if docs else ""
        line = f"{node.lineno:>5}  {'    ' * depth}{head}"
        rows.append(f"{line}  # {doc}" if doc else line)

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            emit(node, 0)
            for child in node.body:
                if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef
                              | ast.ClassDef):
                    emit(child, 1, node.name)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            emit(node, 0)
    return rows


def find(name: str, where: Path) -> list[str]:
    """Every class, def or module-level assignment called ``name``."""
    hits = []
    for path in _python_files(where):
        try:
            tree = ast.parse(path.read_text(), str(path))
        except SyntaxError:
            continue
        rel = path.relative_to(ROOT)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef | ast.FunctionDef
                          | ast.AsyncFunctionDef) and node.name == name:
                kind = "class" if isinstance(node, ast.ClassDef) else "def"
                doc = _first_sentence(node)
                hits.append(f"{rel}:{node.lineno}  {kind} {name}"
                            + (f"  # {doc}" if doc else ""))
        for node in tree.body:
            targets = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            for t in targets:
                if isinstance(t, ast.Name) and t.id == name:
                    hits.append(f"{rel}:{node.lineno}  {name} = ...")
    return hits


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("paths", nargs="*", help="files or folders to outline")
    p.add_argument("--grep", metavar="REGEX",
                   help="only names matching this (case-insensitive)")
    p.add_argument("--find", metavar="NAME",
                   help="where a class, function or constant is defined")
    p.add_argument("--in", dest="where", default=".", metavar="DIR",
                   help="folder --find searches (default: the repo)")
    p.add_argument("--no-docs", action="store_true",
                   help="signatures only")
    args = p.parse_args(argv)

    if args.find:
        hits = find(args.find, (ROOT / args.where).resolve())
        print("\n".join(hits) if hits else f"no definition of {args.find}")
        return 0 if hits else 1
    if not args.paths:
        p.error("give a file or folder, or --find NAME")

    pattern = re.compile(args.grep, re.I) if args.grep else None
    for target in args.paths:
        target = Path(target)
        target = target if target.is_absolute() else Path.cwd() / target
        if not target.exists():
            print(f"{target}: no such file or folder", file=sys.stderr)
            return 1
        for path in _python_files(target):
            rows = outline(path, pattern, docs=not args.no_docs)
            if not rows and pattern:
                continue
            lines = len(path.read_text().splitlines())
            print(f"== {path.relative_to(ROOT)}  ({lines} lines)")
            print("\n".join(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
