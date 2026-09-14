"""The sheet's rows for text that does not exist yet.

Run explicitly -- it lives beside the skill, outside ``testpaths``:

    python -m pytest -q .claude/skills/ui-text/test_uitext.py

Each test builds a small tree of its own and points the script at it,
so nothing here reads or writes the application's source.
"""

import csv
import textwrap

import pytest
import uitext

MENUS = '''\
def build_actions(window):
    add = window.actions_.add
    add("new", "&New", window.new_document, "Ctrl+N")
    add("show_axes", "Cell axes",
        lambda v: window.set_view(show_axes=v), checkable=True,
        tip="The triad in the corner of the view")
'''

PARAMS = '''\
from xtal.params import Param

DOS_PARAMS = (
    Param("sigma", "Broadening", kind="float", default=0.1,
          help="This Gaussian width is ours"),
    Param("shells", "Resolve s, p and d", kind="bool", default=False),
)
'''


@pytest.fixture
def tree(tmp_path, monkeypatch):
    (tmp_path / "xtalapp").mkdir()
    (tmp_path / "xtal" / "modules").mkdir(parents=True)
    (tmp_path / "xtalapp" / "menus.py").write_text(MENUS)
    (tmp_path / "xtalapp" / "dialog.py").write_text(textwrap.dedent('''\
        from PySide6.QtWidgets import QLabel

        def build():
            return QLabel("Some words on screen")
        '''))
    (tmp_path / "xtal" / "modules" / "dftb.py").write_text(PARAMS)
    monkeypatch.setattr(uitext, "ROOT", tmp_path)
    monkeypatch.setattr(uitext, "SOURCES", ("xtalapp", "xtal/modules"))
    return tmp_path


def _rows(tree):
    sheet = tree / "build" / "ui-text.csv"
    uitext.extract(sheet)
    with sheet.open(newline="") as handle:
        return sheet, list(csv.DictReader(handle))


def _fill(sheet, rows, where, new_text):
    for row in rows:
        if row["where"].startswith(where):
            row["new_text"] = new_text
    with sheet.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, uitext.COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def test_a_command_without_a_tip_gets_a_missing_row(tree):
    """Without it a command with no tip has no row, so nobody writes
    one, and the Help page goes on saying it has no description."""
    _sheet, rows = _rows(tree)
    missing = [r for r in rows if r["kind"] == "tip= (missing)"]
    assert [r["where"] for r in missing] == ["new (&New)"]
    assert missing[0]["text"] == ""
    help_missing = [r for r in rows if r["kind"] == "help= (missing)"]
    assert [r["where"] for r in help_missing] == [
        "DOS_PARAMS.shells (Resolve s, p and d)"]


def test_applying_a_missing_tip_inserts_the_keyword(tree):
    """The keyword goes in on a line of its own at the arguments'
    column, and the call still means what it did."""
    sheet, rows = _rows(tree)
    _fill(sheet, rows, "new ", "Start an empty structure in a tab of "
          "its own, in the current workspace, named untitled")
    _fill(sheet, rows, "DOS_PARAMS.shells", "One curve per shell")
    assert uitext.apply(sheet, dry_run=False) == 0

    menus = (tree / "xtalapp" / "menus.py").read_text()
    assert ('    add("new", "&New", window.new_document, "Ctrl+N",\n'
            '        tip="Start an empty structure in a tab of its own, '
            'in the current "\n'
            '            "workspace, named untitled")\n') in menus
    params = (tree / "xtal" / "modules" / "dftb.py").read_text()
    assert ('    Param("shells", "Resolve s, p and d", kind="bool", '
            'default=False,\n'
            '          help="One curve per shell"),\n') in params
    assert all(len(line) <= uitext.WIDTH
               for line in menus.splitlines() + params.splitlines())

    _sheet, again = _rows(tree)
    assert not [r for r in again if r["kind"].endswith("(missing)")]
    tips = {r["text"] for r in again if r["kind"] == "tip="}
    assert "Start an empty structure in a tab of its own, in the " \
        "current workspace, named untitled" in tips


def test_a_missing_tip_and_a_new_label_on_one_call_both_apply(tree):
    """Both edits are inside one call; made in the wrong order the
    second lands at an offset the first has moved."""
    sheet, rows = _rows(tree)
    for row in rows:
        if row["kind"] == "menu entry" and row["text"] == "&New":
            row["new_text"] = "&New structure"
    _fill(sheet, rows, "new ", "Start an empty structure")
    assert uitext.apply(sheet, dry_run=False) == 0
    menus = (tree / "xtalapp" / "menus.py").read_text()
    assert ('    add("new", "&New structure", window.new_document, '
            '"Ctrl+N",\n'
            '        tip="Start an empty structure")\n') in menus


def test_missing_rows_come_first(tree):
    """Commands, then settings, then everything else in file order:
    the missing text is what the Help page is short of."""
    _sheet, rows = _rows(tree)
    kinds = [r["kind"] for r in rows]
    assert kinds[:2] == ["tip= (missing)", "help= (missing)"]
    assert not any(k.endswith("(missing)") for k in kinds[2:])
    assert [r["id"] for r in rows] == [str(n) for n in
                                       range(1, len(rows) + 1)]
    assert "Some words on screen" in [r["text"] for r in rows[2:]]
