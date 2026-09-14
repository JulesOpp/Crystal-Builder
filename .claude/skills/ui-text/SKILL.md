---
name: ui-text
description: Pull every user-visible string in Crystal Builder (labels, buttons, tooltips, hints, menu entries, dialog titles, status messages, module parameter labels and help) into a CSV for a person to rewrite, then apply the edited CSV back into the source safely, re-wrapped to 79 columns, with the tests that quote old wording listed. Use when the user wants to review, reword, rename or tailor the app's text, tooltips or help strings in bulk, or asks for the text spreadsheet.
---

# The app's text, as a spreadsheet

The user is rewriting the application's text themselves. Your job is
the plumbing either side of that: produce the sheet, apply it without
breaking anything, and fix what the new wording breaks. **Do not
reword strings yourself** unless asked; the point is their voice.

## 1. Extract

```bash
python .claude/skills/ui-text/uitext.py extract            # -> build/ui-text.csv
python .claude/skills/ui-text/uitext.py extract -o build/ui-text-2026-09.csv
```

About 1,320 strings from about 80 files (`/build/` is gitignored). It
parses the source and never imports it. Columns:

| Column | For the person | Notes |
|---|---|---|
| `id` | ✓ | row number |
| `file`, `line`, `where` | ✓ | `where` is `Class.method`, the best clue to which window it is |
| `kind` | ✓ | `menu entry`, `tip=`, `QLabel`, `addRow`, `_hint`, `status`, `Param`, `help=`, `constant`, ... |
| `text` | ✓ | the current wording |
| `new_text` | **edit this** | leave empty to keep |
| `col`, `end_line`, `end_col`, `fstring`, `source` | ✗ | used by apply; **do not edit** |

**Missing rows come first.** A registry `add(...)` in `menus.py` with
no `tip=` gets a row of kind `tip= (missing)`, and a `Param(...)` with
no `help=` (a module's or an engine's) one of kind `help= (missing)`:
commands, then settings, then everything else in file order. Their
`text` is empty and `where` names the thing instead -- the registry
key and its label (`select_same (Select same &element)`), or the
table and the setting (`ORBITAL_PARAMS.kpoint (k-point)`). The row
spans the whole call; apply inserts `tip="..."` / `help="..."` on a
line of its own at the arguments' column. `reference.py` (the
manual-writing skill) prints the same two lists, and both reaching 0
is how to know every command and setting is described.

Tell the user, with the sheet:

- Open it in Numbers or Excel, fill `new_text` only, and **save back
  as CSV (UTF-8)**. Filtering by `file` or `kind` is the easy way to
  work one window at a time.
- `&` before a letter is the keyboard mnemonic (`&Open` shows Open,
  Alt+O on Windows). Keep one per menu entry and avoid clashes within
  a menu.
- `...` at the end of a menu entry means it opens a dialog. Keep that
  convention.
- `{name}` in a row whose `fstring` is 1 is filled in by the program
  (`{count} atoms`). Keep every `{...}` exactly; a literal brace is
  `{{` or `}}`.
- `kind = constant` rows are table entries (optimiser names, column
  headers, choices). A few tables may be *matched against* rather than
  shown; if unsure, ask before changing one.
- The rows at the top are text that does not exist yet; a blank
  `new_text` there leaves the command or setting undescribed.
- Very short rows (`OK`, `Add`) and `help=`/`tip=` rows are the ones
  worth the most attention: the tips are the Help page and the future
  manual's reference chapters.

**What is not in the sheet**: exception messages (`raise
ValueError(...)`), strings built by `.format` or concatenation at run
time, text inside `.ui`-free custom painting (`QPainter.drawText`),
and anything under `xtal/mof/pormake/`. If the user finds a string on
screen that is not in the sheet, find it with
`grep -rn 'the words' xtalapp xtal` and edit it by hand.

## 2. Apply

Work in **batches** (a window or a file at a time is easiest to
review), and re-extract after each applied batch so positions are
fresh.

```bash
python .claude/skills/ui-text/uitext.py apply build/ui-text.csv --dry-run   # review the diff
python .claude/skills/ui-text/uitext.py apply build/ui-text.csv
```

What apply does, per changed row:

1. Finds the literal at its recorded position and checks it is still
   the recorded `source`; if the file has moved, finds it by content
   (skipped and reported if absent or ambiguous).
2. Writes a new literal at the same column: one line if it fits,
   otherwise implicitly concatenated pieces each ending in its space,
   the house style. Only pieces containing a `{hole}` are f-strings
   (keeps ruff's F541 quiet).
3. Compiles each file before writing it; a file that would not compile
   is left untouched and its rows reported.
4. Runs `ruff check` on changed files.
5. Lists **tests that quote the old wording**, and **other places the
   old literal still appears** in the app (a label compared elsewhere,
   e.g. `findText("Custom...")`).

A non-zero exit means rows were skipped; read the SKIPPED lines.

**Before applying**, check `git status` on the files the sheet
touches. Apply writes files in place, and a file with the user's own
uncommitted work is fine to write but harder to review. Say which files
are already modified.

## 3. After applying

1. **Tests**: for each listed test, open the assertion. Some hits are
   only a docstring mentioning the words; leave those. Update literal
   assertions to the new text **in the same commit**. Label text is
   asserted in `test_app_shell.py`, `test_reset_bonds.py`,
   `test_context_menu.py`, `test_ff_ui.py`, `test_modules_ui.py` and
   others (docs/MENUS.md § 4).
2. **Other uses**: a comparison against the old literal gets the new
   one; a second, separate label with the same words is the user's
   call. Ask.
3. Run the affected test files, then the full suite once:
   `python -m pytest -q tests/test_app_shell.py tests/test_help_ui.py ...`
4. **Look at it**: longer text changes layouts. Grab the windows the
   batch touched with `run-app`:
   `--grab style_dock "$SCRATCH/style.png" 420x800`. Report anything
   clipped, elided (`Force Fi...`) or forcing a scroll bar.
5. Keep registry keys (`add("recompute_bonds", ...)`); only labels
   change.

One commit per batch, message naming the area: *Reword the Preferences
dialog*.

## Changing the script

Its tests live beside it, outside the suite's `testpaths`, and build a
small tree of their own rather than touching the app:
`python -m pytest -q .claude/skills/ui-text/test_uitext.py`.
