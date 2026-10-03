"""Every dialog the application opens is deleted on the GUI thread
once it has answered (:mod:`xtalapp.dialogs.answered`)."""

import ast
from pathlib import Path

#: The ``exec`` calls that are not a dialog answering, each with why.
NOT_DIALOGS = {
    # The application's own event loop.
    ("main.py", "app"),
    # A context menu, which is raised through ``menus.popup`` so that
    # the suite can replace it -- see CLAUDE.md, Testing the GUI.
    ("menus.py", "menu"),
}


def _bare_execs():
    """``file:line`` of every ``x.exec(...)`` under ``xtalapp`` that is
    not inside a ``with answered(...)`` block."""
    for path in sorted(Path("xtalapp").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        guarded = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.With) and any(
                    isinstance(item.context_expr, ast.Call)
                    and getattr(item.context_expr.func, "id", "")
                    == "answered"
                    for item in node.items):
                guarded.update(id(inner) for inner in ast.walk(node))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "exec"):
                continue
            owner = getattr(node.func.value, "id", "")
            if (path.name, owner) in NOT_DIALOGS or id(node) in guarded:
                continue
            yield f"{path.relative_to('xtalapp')}:{node.lineno}"


def test_every_dialog_is_opened_through_answered():
    """``exec`` leaves a dialog owned by Python, and one held in a
    cycle is freed by whichever thread next runs the collector: the
    polymer and MOF builders' dialogs were destroyed on the build's
    worker and segfaulted.  A dialog opened any other way -- in an
    ``ask`` or not, as Preferences, Export and Find Symmetry were --
    brings that back the first time its callbacks close a cycle."""
    assert list(_bare_execs()) == []


def test_the_sweep_finds_a_bare_exec_where_there_is_one(tmp_path,
                                                       monkeypatch):
    """A sweep that cannot fail proves nothing: one bare call in a
    scratch tree is found, and the same call inside ``answered`` is
    not."""
    package = tmp_path / "xtalapp"
    package.mkdir()
    (package / "bare.py").write_text(
        "def f(d):\n    d.exec()\n", encoding="utf-8")
    (package / "held.py").write_text(
        "def f(d):\n    with answered(d) as dialog:\n"
        "        dialog.exec()\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert list(_bare_execs()) == ["bare.py:2"]
