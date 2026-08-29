"""The core must stay importable on a machine with no GUI stack.

Principle 1 of the plan: nothing under ``xtal/`` may import Qt or VTK,
directly or transitively.  This test is the guard that keeps a stray
convenience import from quietly making the library un-installable in
CI, in a notebook, or on a cluster node.
"""

import ast
import pathlib
import subprocess
import sys

FORBIDDEN = {"PySide6", "PyQt5", "PyQt6", "vtk", "vtkmodules",
             "matplotlib", "pyqtgraph", "xtalapp"}

CORE = pathlib.Path(__file__).resolve().parent.parent / "xtal"


def _imported_modules(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            if node.module:
                names.add(node.module.split(".")[0])
    return names


def test_no_gui_imports_anywhere_in_the_core():
    offenders = {}
    for path in sorted(CORE.rglob("*.py")):
        bad = _imported_modules(path) & FORBIDDEN
        if bad:
            offenders[str(path.relative_to(CORE.parent))] = sorted(bad)
    assert not offenders, f"GUI imports leaked into the core: {offenders}"


def test_importing_the_core_does_not_pull_in_qt_or_vtk():
    code = (
        "import sys; import xtal; "
        "bad = sorted(m for m in sys.modules "
        "if m.split('.')[0] in "
        f"{sorted(FORBIDDEN - {'xtalapp'})!r}); "
        "print(bad)"
    )
    out = subprocess.run([sys.executable, "-c", code], check=True,
                         cwd=CORE.parent, capture_output=True,
                         text=True).stdout.strip()
    assert out == "[]", f"core import loaded {out}"
