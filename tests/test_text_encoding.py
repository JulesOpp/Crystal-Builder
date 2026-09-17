"""Every text file the application reads or writes names its encoding.

Without one, Python uses the locale's: UTF-8 on macOS and Linux, and a
code page on Windows.  So a call that forgets is correct on every
machine this is developed on and wrong on the one it ships to -- the
Gamma in a band-structure tick label raised ``UnicodeEncodeError``
under cp1252, and a workspace in a folder named with an accent would
have written a ``workspace.json`` no other machine could read.
Checked by reading the source, because the suite runs on a Mac and
the behaviour it guards cannot fail there.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: The vendored PORMAKE is kept as it came -- see its PROVENANCE.md.
SKIPPED = ("pormake",)


def _unnamed(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)):
            continue
        if any(k.arg == "encoding" for k in node.keywords):
            continue
        name = node.func.attr
        if name in ("read_text", "write_text"):
            yield node.lineno, name
        elif name == "open" and _text_mode(node):
            yield node.lineno, name


def _text_mode(node) -> bool:
    """``path.open("w")`` and friends -- a literal text mode.

    ``Workspace.open(root)`` and ``Image.open(file)`` take a path, not
    a mode, which is why the first argument has to be one to count.
    """
    if not node.args or not isinstance(node.args[0], ast.Constant):
        return False
    mode = node.args[0].value
    return (isinstance(mode, str) and "b" not in mode
            and set(mode) <= set("rwax+t"))


def test_every_text_file_the_application_touches_names_its_encoding():
    found = []
    for package in ("xtal", "xtalapp"):
        for path in sorted((ROOT / package).rglob("*.py")):
            if any(part in SKIPPED for part in path.parts):
                continue
            found.extend(f"{path.relative_to(ROOT)}:{line} {name}"
                         for line, name in _unnamed(path))
    assert found == []


def test_the_check_would_notice_a_call_that_forgets(tmp_path):
    """Otherwise the test above passes by finding nothing to look at."""
    sample = tmp_path / "sample.py"
    sample.write_text(
        "p.write_text(s)\n"
        "p.read_text(encoding='utf-8')\n"
        "p.open('w')\n"
        "p.open('rb')\n"
        "Workspace.open(root)\n", encoding="utf-8")
    assert [name for _line, name in _unnamed(sample)] == [
        "write_text", "open"]
