"""Every dialog that answers through ``ask`` is deleted on the GUI
thread once it has (:mod:`xtalapp.dialogs.answered`)."""

import ast
from pathlib import Path


def _asks():
    for path in sorted(Path("xtalapp/dialogs").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if (isinstance(item, ast.FunctionDef)
                            and item.name == "ask"):
                        yield f"{path.name}:{node.name}", item


def test_every_ask_opens_its_dialog_through_answered():
    """``exec`` leaves a dialog owned by Python, and one held in a
    cycle is freed by whichever thread next runs the collector: the
    polymer and MOF builders' dialogs were destroyed on the build's
    worker and segfaulted.  A new ``ask`` that opens its dialog any
    other way brings that back the first time its callbacks close a
    cycle."""
    asks = dict(_asks())
    assert len(asks) > 20
    bare = [name for name, function in asks.items()
            if "answered(" not in ast.unparse(function)]
    assert bare == []
