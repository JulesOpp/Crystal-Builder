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

FORBIDDEN = {"PySide6", "PySide2", "PyQt5", "PyQt6", "qtpy", "tkinter",
             "wx", "vtk", "vtkmodules", "matplotlib", "pyqtgraph",
             "xtalapp"}

CORE = pathlib.Path(__file__).resolve().parent.parent / "xtal"
SHELL = CORE.parent / "xtalapp"


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


def test_no_core_module_pulls_in_a_gui():
    """Every module, not just what ``import xtal`` reaches.

    ``xtal/__init__`` imports four modules, so the test above proves
    the transitive half of the rule for those four; a third-party
    dependency of ``xtal/analysis/pxrd.py`` pulling in matplotlib would
    pass it.  One subprocess imports them all.  A module whose
    optional extra is not installed is left out -- that is the extra
    being optional, not the wall leaking.
    """
    code = (
        "import importlib, pathlib, sys\n"
        "root = pathlib.Path('xtal')\n"
        "for path in sorted(root.rglob('*.py')):\n"
        "    parts = path.with_suffix('').parts\n"
        "    if parts[-1] == '__init__': parts = parts[:-1]\n"
        "    try: importlib.import_module('.'.join(parts))\n"
        "    except ImportError: pass\n"
        "print(sorted({m.split('.')[0] for m in sys.modules} & "
        f"set({sorted(FORBIDDEN - {'xtalapp'})!r})))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], check=True,
                         cwd=CORE.parent, capture_output=True,
                         text=True).stdout.strip()
    assert out.splitlines()[-1] == "[]", f"core modules loaded {out}"


#: Where the shell may ask for a covalent radius: to *draw* an atom
#: that size.  Anywhere else it is deciding what is bonded, which is
#: the core's job -- the MOF preview once did it with a rule of its
#: own and drew bonds the build would never make.
RADIUS_FOR_DRAWING = {
    ("viewport/view_settings.py", "base_radius"),
    ("dialogs/mof_preview.py", "_draw_atom"),
}


def _functions_calling(path: pathlib.Path, name: str) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found = set()
    for function in ast.walk(tree):
        if not isinstance(function,
                          ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for node in ast.walk(function):
            if isinstance(node, ast.Attribute) and node.attr == name:
                found.add(function.name)
    return found


def test_only_drawing_asks_the_shell_for_a_covalent_radius():
    # as_posix: the allow-list is written with "/", and on Windows a
    # relative path's str() has "\" -- which failed CI on win32 only.
    asked = {(path.relative_to(SHELL).as_posix(), function)
             for path in sorted(SHELL.rglob("*.py"))
             for function in _functions_calling(path, "covalent_radius")}
    assert asked <= RADIUS_FOR_DRAWING, \
        f"chemistry in the shell: {sorted(asked - RADIUS_FOR_DRAWING)}"
