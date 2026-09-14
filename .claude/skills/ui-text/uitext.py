"""Every piece of text a user reads, out to a spreadsheet and back.

    uitext.py extract [-o build/ui-text.csv]
    uitext.py apply build/ui-text.csv [--dry-run]

``extract`` walks the source -- never importing it -- and writes one row
per user-visible string: labels, buttons, group titles, tooltips, hints,
menu entries, dialog titles, status sentences, a module's parameter
labels and help.  Each row says where it is and what kind of widget it
feeds.  The ``new_text`` column is left empty for a person to fill in.

``apply`` puts every changed row back into its file: at the recorded
position, checked against the source it was taken from, re-wrapped to
the 79-column layout as implicitly concatenated literals, and compiled
before the file is written.  A row whose source has moved is found by
its text; one that cannot be found unambiguously is reported and left
alone.  Afterwards it lists the tests that quote the old wording,
because a label is asserted in more places than it is defined.

Standard library only.
"""

from __future__ import annotations

import argparse
import ast
import csv
import difflib
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WIDTH = 79

#: Where user-visible text is written.  ``xtal/modules`` and ``xtal/ff``
#: are in it because a module's Param labels and help *are* its form
#: and its Help page.
SOURCES = ("xtalapp", "xtal/modules", "xtal/ff", "xtal/params.py")
#: The stub module is registered only for tests and never shipped.
SKIP = ("xtal/mof/pormake/", "__pycache__", "xtal/modules/stub.py",
        "xtal/modules/data/")          # a script Blender runs

#: Constructors whose first argument is the text drawn.
FIRST_ARG = {"QLabel", "QCheckBox", "QPushButton", "QGroupBox",
             "QRadioButton", "QToolButton", "QAction", "_hint",
             "setText", "setToolTip", "setStatusTip", "setWindowTitle",
             "setPlaceholderText", "setWhatsThis", "setTitle",
             "setLabelText", "setIconText", "setSpecialValueText",
             "setSuffix", "setPrefix", "showMessage", "show_status",
             "show_message", "addRow", "addItem", "addAction",
             "addMenu", "failure", "emit", "Extra"}
#: Callables whose text is at another position, or at several.
POSITIONS = {"addTab": (1,), "insertItem": (1,), "insertTab": (2,),
             "submenu": (1,), "Param": (1,), "Tool": (1, 3),
             "Extra": (0, 3), "question": (1, 2), "warning": (1, 2),
             "information": (1, 2), "critical": (1, 2),
             "getOpenFileName": (1,), "getSaveFileName": (1,),
             "getExistingDirectory": (1,), "getText": (1, 2),
             "getItem": (1, 2), "getDouble": (1, 2), "getInt": (1, 2)}
#: Keyword arguments that are text wherever they appear.
KEYWORDS = {"tip", "help", "label", "description", "title", "text",
            "message", "tooltip", "hint", "powers"}
#: ``add(name, text, slot, ...)`` in menus.py is the action registry.
ACTION_ADD = ("xtalapp/menus.py", "add", 1)
#: Capitalised tables that are *matched against* something rather than
#: shown: rewording one breaks what reads it.  ``_NOISE`` is Zeo++'s
#: own output, ``STYLE`` is a stylesheet.  Add to this, not to a sheet.
NOT_TEXT = {"_NOISE", "STYLE"}
#: Methods whose returned strings are status-bar sentences.
STATUS_FILES = ("xtalapp/document.py", "xtalapp/documents.py")
#: Text that should exist and does not: a command with no ``tip=`` and
#: a setting with no ``help=`` are what the Help page and the manual's
#: reference print as "no description", and a string that is not
#: there has no row unless it is given one.  ``(callable, keyword,
#: its positional index or None)``; a ``Param``'s ``help`` is its
#: eleventh field.
MISSING = {"add": ("tip", None), "Param": ("help", 10)}
MISSING_SUFFIX = " (missing)"

COLUMNS = ["id", "file", "line", "where", "kind", "text", "new_text",
           "col", "end_line", "end_col", "fstring", "source"]


@dataclass
class Found:
    file: str
    line: int
    col: int          # characters, not bytes
    end_line: int
    end_col: int
    where: str
    kind: str
    text: str
    fstring: bool
    source: str


# ---------------------------------------------------------------- extract

def _files():
    for spec in SOURCES:
        path = ROOT / spec
        paths = [path] if path.is_file() else sorted(path.rglob("*.py"))
        for p in paths:
            rel = p.relative_to(ROOT).as_posix()
            if not any(s in rel for s in SKIP):
                yield p, rel


def _char_col(lines, lineno, byte_col):
    return len(lines[lineno - 1].encode()[:byte_col].decode(
        errors="replace"))


def _display(node, text) -> str | None:
    """The string as a person reads it; f-string holes as ``{expr}``."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        out = []
        for part in node.values:
            if isinstance(part, ast.Constant):
                out.append(part.value.replace("{", "{{")
                           .replace("}", "}}"))
            else:
                hole = ast.get_source_segment(text, part.value) \
                    or ast.unparse(part.value)
                if part.conversion != -1:
                    hole += "!" + chr(part.conversion)
                if part.format_spec is not None:
                    hole += ":" + "".join(
                        v.value if isinstance(v, ast.Constant)
                        else "{" + ast.unparse(v.value) + "}"
                        for v in part.format_spec.values)
                out.append("{" + hole + "}")
        return "".join(out)
    return None


def _wanted(value: str) -> bool:
    """Words, not keys, paths, formats or single symbols."""
    stripped = re.sub(r"\{[^}]*\}", "", value)
    if not re.search(r"[A-Za-z]{2}", stripped):
        return False
    if re.fullmatch(r"[a-z0-9_.:/\-]+", value):      # a key or a path
        return value.count(" ") > 0
    return True


def _reads_as_words(value: str) -> bool:
    """A table entry a person reads, rather than a name the code uses.

    Stricter than :func:`_wanted`, because a capitalised constant is as
    often an environment variable, a class name, an element symbol or a
    shader as it is a label.  A phrase with a space in it, or one
    capitalised word ("General", "Sure?"); never code or a layout.
    """
    text = value.strip()
    if re.search(r"//|;\s*$|%\(|\s{3,}", text):
        return False
    if " " in text:
        return bool(re.search(r"[a-z]{2}", text))
    return bool(re.fullmatch(r"[A-Z][a-z]{2,}[?.]?|[A-Z][a-z]?\.", text))


class _Walker(ast.NodeVisitor):
    def __init__(self, rel, text):
        self.rel, self.text = rel, text
        self.lines = text.splitlines()
        self.stack: list[str] = []
        self.found: dict[tuple, Found] = {}
        self.assigning: str | None = None

    def _take(self, node, kind):
        for leaf in ([node.body, node.orelse]
                     if isinstance(node, ast.IfExp) else [node]):
            if isinstance(leaf, ast.IfExp):
                self._take(leaf, kind)
                continue
            shown = _display(leaf, self.text)
            if shown is None or not _wanted(shown):
                continue
            key = (leaf.lineno, leaf.col_offset)
            if key in self.found:
                continue
            self.found[key] = Found(
                self.rel, leaf.lineno,
                _char_col(self.lines, leaf.lineno, leaf.col_offset),
                leaf.end_lineno,
                _char_col(self.lines, leaf.end_lineno,
                          leaf.end_col_offset),
                ".".join(self.stack) or "<module>", kind, shown,
                isinstance(leaf, ast.JoinedStr),
                ast.get_source_segment(self.text, leaf))

    def _scope(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_ClassDef = visit_FunctionDef = visit_AsyncFunctionDef = _scope

    def visit_Call(self, node):
        f = node.func
        name = f.attr if isinstance(f, ast.Attribute) else \
            getattr(f, "id", "")
        if (self.rel, name) == ACTION_ADD[:2] and \
                len(node.args) > ACTION_ADD[2]:
            self._take(node.args[ACTION_ADD[2]], "menu entry")
            self._missing(node, name)
        elif name == "Param" and node.args:
            self._missing(node, name)
        positions = POSITIONS.get(name, (0,) if name in FIRST_ARG
                                  else ())
        for i in positions:
            if i < len(node.args):
                self._take(node.args[i], name)
        for kw in node.keywords:
            if kw.arg in KEYWORDS:
                self._take(kw.value, f"{kw.arg}=")
        self.generic_visit(node)

    def _missing(self, node, name):
        """A row for the ``tip=`` or ``help=`` this call does not have.

        The row spans the whole call, so ``apply`` can check it is
        still there and find it by content if it has moved; its text is
        empty, and ``where`` names the command or the setting, since
        nothing else in the row says which one it is.
        """
        keyword, position = MISSING[name]
        if any(kw.arg == keyword for kw in node.keywords) or \
                any(kw.arg is None for kw in node.keywords) or \
                (position is not None and len(node.args) > position):
            return
        key = _display(node.args[0], self.text) or \
            ast.unparse(node.args[0])
        label = _display(node.args[1], self.text) \
            if len(node.args) > 1 else None
        scope = self.stack + ([self.assigning] if self.assigning and
                              name == "Param" else [])
        where = ".".join(scope + [key]) if name == "Param" else key
        if label:
            where += f" ({label})"
        self.found[("missing", node.lineno, node.col_offset)] = Found(
            self.rel, node.lineno,
            _char_col(self.lines, node.lineno, node.col_offset),
            node.end_lineno,
            _char_col(self.lines, node.end_lineno, node.end_col_offset),
            where, keyword + "=" + MISSING_SUFFIX, "", False,
            ast.get_source_segment(self.text, node))

    def visit_Assign(self, node):
        # ``METHOD_LABELS = {"lbfgs": "L-BFGS (fast near a minimum)"}``
        # and the tuples of (label, value) pairs beside it: a table of
        # words at module or class level, named in capitals.  Dict keys
        # are internal names and are never taken.
        named = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if len(self.stack) <= 1 and named and all(
                n.isupper() and n not in NOT_TEXT for n in named):
            self._constants(node.value)
        self.assigning = named[0] if len(named) == 1 else None
        self.generic_visit(node)
        self.assigning = None

    def _constants(self, value):
        if isinstance(value, ast.Dict):
            for v in value.values:
                self._constants(v)
        elif isinstance(value, ast.Tuple | ast.List):
            for v in value.elts:
                self._constants(v)
        elif isinstance(value, ast.Constant | ast.JoinedStr):
            shown = _display(value, self.text)
            if shown and _reads_as_words(shown):
                self._take(value, "constant")

    def visit_Return(self, node):
        if self.rel in STATUS_FILES and node.value is not None:
            self._take(node.value, "status")
        self.generic_visit(node)


def extract(out: Path) -> int:
    rows = []
    for path, rel in _files():
        text = path.read_text()
        walker = _Walker(rel, text)
        walker.visit(ast.parse(text, rel))
        rows += sorted(walker.found.values(), key=lambda f: (f.line,
                                                             f.col))
    # The text that is not there yet goes first -- commands, then
    # settings -- because it is what the Help page is short of; the
    # sort is stable, so everything else keeps its file order.
    order = {"tip=" + MISSING_SUFFIX: 0, "help=" + MISSING_SUFFIX: 1}
    rows.sort(key=lambda f: order.get(f.kind, len(order)))
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for n, f in enumerate(rows, 1):
            writer.writerow([n, f.file, f.line, f.where, f.kind, f.text,
                             "", f.col, f.end_line, f.end_col,
                             int(f.fstring), f.source])
    files = len({f.file for f in rows})
    print(f"wrote {len(rows)} strings from {files} files to {out}")
    for kind in order:
        count = sum(f.kind == kind for f in rows)
        print(f"  {count} rows are {kind}")
    return 0


# ------------------------------------------------------------------ apply

def _pieces(text: str, fstring: bool):
    """``(chunk, is_hole)`` pieces; holes only for an f-string."""
    if not fstring:
        return [(text, False)]
    out, i, literal = [], 0, []
    while i < len(text):
        if text.startswith("{{", i) or text.startswith("}}", i):
            literal.append(text[i])
            i += 2
        elif text[i] == "{":
            depth, j = 1, i + 1
            while j < len(text) and depth:
                depth += {"{": 1, "}": -1}.get(text[j], 0)
                j += 1
            if literal:
                out.append(("".join(literal), False))
                literal = []
            out.append((text[i:j], True))
            i = j
        else:
            literal.append(text[i])
            i += 1
    if literal:
        out.append(("".join(literal), False))
    return out


def _quote_for(text: str) -> str:
    return "'" if '"' in text and "'" not in text else '"'


def _escape(literal: str, quote: str, fstring: bool) -> str:
    s = literal.replace("\\", "\\\\").replace("\n", "\\n") \
        .replace("\t", "\\t").replace(quote, "\\" + quote)
    return s.replace("{", "{{").replace("}", "}}") if fstring else s


def _tokens(text: str, fstring: bool):
    """Words with their trailing space, holes kept whole."""
    quote = _quote_for(text)
    tokens = []
    for chunk, hole in _pieces(text, fstring):
        if hole:
            tokens.append((chunk, True))
            continue
        for word in re.findall(r"\S*\s*", chunk):
            if word:
                tokens.append((_escape(word, quote, fstring), False))
    return tokens, quote


def literal_for(text: str, fstring: bool, col: int, tail: int) -> str:
    """A Python literal spelling *text*, wrapped to start at *col*.

    One literal when it fits; otherwise implicitly concatenated pieces,
    each ending in its space the way the rest of the code is written,
    continued at the same column.  Only a piece that holds a hole is an
    f-string, so ruff's F541 has nothing to say.
    """
    has_holes = fstring and any(h for _c, h in _pieces(text, True))
    tokens, quote = _tokens(text, has_holes)

    def render(group):
        body = "".join(t for t, _h in group)
        holes = any(h for _t, h in group)
        if has_holes and not holes:
            body = body.replace("{{", "{").replace("}}", "}")
        return ("f" if holes else "") + quote + body + quote

    whole = render(tokens)
    if col + len(whole) + tail <= WIDTH or len(tokens) <= 1:
        return whole
    room = max(24, WIDTH - col)
    lines, current = [], []
    for token in tokens:
        if current and len(render(current + [token])) > room:
            lines.append(current)
            current = []
        current.append(token)
    # The last piece shares its line with whatever closed the call --
    # ``, self)`` -- so words move down until that fits too.
    moved = []
    while len(current) > 1 and len(render(current)) + tail > room:
        moved.insert(0, current.pop())
    lines += [g for g in (current, moved) if g]
    return ("\n" + " " * col).join(render(group) for group in lines)


def _offset(lines, line, col):
    return sum(len(x) for x in lines[:line - 1]) + col


def _is_missing(row) -> bool:
    return row["kind"].endswith(MISSING_SUFFIX)


def _insert_keyword(src: str, start: int, end: int, row) -> str:
    """*src* with ``tip="..."`` added to the call at ``src[start:end]``.

    On a line of its own at the column of the call's first argument --
    how every ``tip=`` and ``help=`` already in the code is written --
    and wrapped under its own opening quote.
    """
    keyword = row["kind"][:-len(MISSING_SUFFIX)]       # "tip="
    call = ast.parse(src[start:end], mode="eval").body
    first = call.args[0]
    seg_lines = src[start:end].splitlines()
    col = _char_col(seg_lines, first.lineno, first.col_offset)
    if first.lineno == 1:
        col += start - (src.rfind("\n", 0, start) + 1)
    paren = end - 1
    before = src[:paren].rstrip()
    line_end = src.find("\n", end)
    if before.endswith(","):
        # A trailing comma, and the paren on a line of its own.
        tail = 1
    else:
        tail = len(src[paren:line_end if line_end >= 0 else None]
                   .rstrip())
    literal = literal_for(row["new_text"], False, col + len(keyword),
                          tail)
    if before.endswith(","):
        return (before + "\n" + " " * col + keyword + literal + ","
                + src[len(before):])
    return (before + ",\n" + " " * col + keyword + literal
            + src[paren:])


def apply(sheet: Path, dry_run: bool) -> int:
    with sheet.open(newline="") as handle:
        rows = [r for r in csv.DictReader(handle)
                if r["new_text"].strip() and r["new_text"] != r["text"]]
    if not rows:
        print("no row has a new_text different from its text")
        return 0

    by_file: dict[str, list] = {}
    for row in rows:
        by_file.setdefault(row["file"], []).append(row)

    changed, skipped, done = [], [], []
    for rel, edits in sorted(by_file.items()):
        path = ROOT / rel
        original = path.read_text()
        src = original
        lines = src.splitlines(keepends=True)
        placed = []
        for row in edits:
            start = _offset(lines, int(row["line"]), int(row["col"]))
            end = _offset(lines, int(row["end_line"]),
                          int(row["end_col"]))
            if src[start:end] != row["source"]:
                hits = [m.start() for m in
                        re.finditer(re.escape(row["source"]), src)]
                if len(hits) != 1:
                    skipped.append((row, f"source moved and found "
                                         f"{len(hits)} times"))
                    continue
                start, end = hits[0], hits[0] + len(row["source"])
            placed.append((start, end, row))
        # Back to front, so an edit never moves one still to be made.
        # A missing keyword goes in at its call's closing paren, which
        # is after any label inside the same call.
        for start, end, row in sorted(placed, key=lambda p: -(
                p[1] - 1 if _is_missing(p[2]) else p[0])):
            if _is_missing(row):
                src = _insert_keyword(src, start, end, row)
                done.append(row)
                continue
            line_start = src.rfind("\n", 0, start) + 1
            col = start - line_start
            line_end = src.find("\n", end)
            tail = len(src[end:line_end if line_end >= 0 else None]
                       .rstrip())
            new = literal_for(row["new_text"], row["fstring"] == "1",
                              col, tail)
            src = src[:start] + new + src[end:]
            done.append(row)
        try:
            compile(src, rel, "exec")
        except SyntaxError as exc:
            skipped += [(r, f"file would not compile: {exc}")
                        for _s, _e, r in placed]
            done = [r for r in done if r["file"] != rel]
            continue
        if src == original:
            continue
        if dry_run:
            sys.stdout.writelines(difflib.unified_diff(
                original.splitlines(keepends=True),
                src.splitlines(keepends=True), f"a/{rel}", f"b/{rel}"))
        else:
            path.write_text(src)
        changed.append(rel)

    verb = "would change" if dry_run else "changed"
    print(f"\n{verb} {len(done)} string(s) in {len(changed)} file(s)")
    for row, why in skipped:
        print(f"  SKIPPED {row['file']}:{row['line']} "
              f"{row['text'][:50]!r}: {why}")
    if changed and not dry_run:
        result = subprocess.run(["ruff", "check", *changed], cwd=ROOT,
                                capture_output=True, text=True)
        print(result.stdout.strip() or "ruff: clean")
    _tests_quoting(done)
    _other_uses(done, dry_run)
    return 1 if skipped else 0


def _other_uses(rows, dry_run) -> None:
    """The same literal somewhere else in the application.

    A label is sometimes *compared* as well as shown --
    ``combo.findText("Custom...")``, a status sentence a dock checks
    for -- and a rewording that changes one spelling and not the other
    breaks silently.  Not every hit is that; each is worth a look.
    """
    hits = []
    for row in rows:
        literal = row["source"]
        if len(row["text"]) < 4:
            continue
        for path, rel in _files():
            count = path.read_text().count(literal)
            # Before a real apply, the edited spot is still there.
            if rel == row["file"] and dry_run:
                count -= 1
            if count > 0:
                hits.append(f"  {rel}  ({count}x)  <- "
                            f"{row['text'][:60]!r}")
    if hits:
        print("\nthe old literal is still used elsewhere (a comparison "
              "would now fail):")
        print("\n".join(sorted(set(hits))))


def _tests_quoting(rows) -> None:
    """Tests that spell out the old wording, so they change with it."""
    hits = []
    for row in rows:
        old = row["text"].replace("&", "")
        needle = re.sub(r"\{[^}]*\}", "", old).strip()[:40]
        if len(needle) < 4:
            continue
        for test in sorted((ROOT / "tests").glob("test_*.py")):
            body = test.read_text()
            if needle in body or needle in body.replace("&", ""):
                hits.append(f"  {test.relative_to(ROOT)}  <- "
                            f"{row['text'][:60]!r}")
    if hits:
        print("\ntests quoting the old text (update them in the same "
              "commit):")
        print("\n".join(sorted(set(hits))))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    e = sub.add_parser("extract", help="write the spreadsheet")
    e.add_argument("-o", "--output", default="build/ui-text.csv")
    a = sub.add_parser("apply", help="write the new_text column back")
    a.add_argument("sheet")
    a.add_argument("--dry-run", action="store_true",
                   help="print the diff instead of writing")
    args = p.parse_args(argv)
    if args.command == "extract":
        return extract((ROOT / args.output).resolve())
    return apply(Path(args.sheet).resolve(), args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
