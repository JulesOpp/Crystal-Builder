---
name: pure-move
description: Move code between modules without changing behaviour - splitting mainwindow.py, extracting a dock or a dialog, lifting logic out of xtalapp into xtal. Use when asked to split, extract, move or reorganise a module, or when a file has grown too large to work in. Enforces one seam per commit and a green suite between steps.
---

# Moving code, and only moving code

`mainwindow.py` is ~1800 lines and nearly every change touches it, so
a split is worth doing — and is the change most likely to be smuggled
in alongside a bug fix, after which neither can be reviewed. The rule
is the whole skill: **a pure move changes no behaviour.**

## The two phases, never merged

**1. Propose, do not edit.** Read the file and report the seams that
already exist before proposing new ones. In `mainwindow.py` they are:
the menu/action wiring, the module-run plumbing, the document/tab
management, the three refresh paths. For each candidate module say
what moves, what it depends on, what stays behind, and what cannot
move cleanly. Ask before touching anything.

**2. Execute one seam at a time**, each its own commit. Not two
because they are small, not "while I'm here".

## What "pure" rules out

No renames. No signature changes. No reordering of methods for
tidiness. No fixing the bug you noticed on the way — write it in
`docs/TODO.md` and keep going. No `ruff format` (line length 79 is
hand-maintained; `ruff check` only). Imports and `__all__` may change,
because that is what moving *is*.

If a move genuinely cannot be pure — a circular import that has to be
broken, a method that needs a parameter it used to read off `self` —
stop and say so before doing it, and make that its own commit with
nothing else in it.

## Between every step

```bash
python -m pytest -q
```

Green before the commit, not once at the end. The suite is the only
thing standing between a pure move and a silent behaviour change, and
it is worth its three minutes (serial; see CLAUDE.md) here even though
it is the wrong habit while iterating. Run it in the background and
read the result when it lands. A test that needed editing to keep
passing means the move was not pure — say so rather than editing the
test.

Find the seams by outline, not by reading the file:
`python .claude/skills/code-map/outline.py xtalapp/mainwindow.py`.

Add the new module to `packages` in `pyproject.toml` if it is a new
package rather than a module in an existing one.

## The seam that matters most

The three refresh paths are the easiest thing to flatten by accident
and the most expensive to get wrong — collapsing them is how a large
structure loses interactivity:

- `_update_ui` rebinds panels when the current **document** changes
- `_on_structure_changed` refreshes what those panels **show**
- `_on_view_changed` touches only the shell's **own** widgets

Whatever moves, those three stay three, called from the same places
for the same reasons.

## Verify it still runs

The suite stubs the viewport, so it will not notice a menu that no
longer builds or an action whose connection was lost in the move.
After the move, launch it — see the `run-app` skill:

```bash
python .claude/skills/run-app/drive.py --open resources/samples/MOF-5.cif --list-actions
```

An action that has gone missing, or come back `[disabled]`, is the
failure a pure move produces and the suite does not catch.
