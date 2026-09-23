---
name: code-map
description: Find where something lives in Crystal Builder without reading whole files - outline a module's classes and methods with line numbers and one-line docstrings, or find where a name is defined. Use before opening any large file (document.py, mainwindow.py, vtk_scene.py, ff_panel.py, builder.py, topology.py), when asked "where is X", when planning a change, or whenever you are about to cat, sed or grep a file to understand its shape.
---

# Finding code without reading it

Over fifteen sessions, reading files through the shell (`cat`,
`sed -n`, broad `grep`) put about **2.5 MB** of output into context,
more than the tests, the edits and the screenshots together. Most of
it answered "which method, and where", which does not need the method
bodies. Answer that first, then `Read` only the lines that matter.

## The outline

```bash
python .claude/skills/code-map/outline.py xtalapp/document.py
python .claude/skills/code-map/outline.py xtalapp/docks          # a folder
python .claude/skills/code-map/outline.py xtalapp/document.py --grep 'bond|select'
python .claude/skills/code-map/outline.py --find merge_atoms     # definitions only
python .claude/skills/code-map/outline.py --find Document --in xtalapp
```

One line per class, method and function: line number, signature,
the docstring's first sentence. `--grep` filters names and prefixes
each method with its class. `--no-docs` for signatures alone.
It parses rather than imports, so it is instant on Qt and VTK modules,
and it skips the vendored `xtal/mof/pormake/`.

The outline of `document.py` is about 4 KB against 80 KB for the file.

## The habit

1. **Shape first.** `outline.py FILE` (or `--grep`) before any file
   over ~300 lines. The `wc -l` is printed in the header.
2. **Then read the span.** `Read` with `offset` at the line number
   and a `limit` that covers the method, typically 40-80 lines. Not
   the whole file, and not `sed -n 1,400p`.
3. **Who calls it** is a text search, and that is still grep. Keep it
   narrow and counted:
   ```bash
   grep -rn --include='*.py' 'merge_atoms' xtal xtalapp tests | head -20
   grep -rln 'ForceFieldDock' xtalapp        # which files, not every line
   ```
   Always bound with `| head` or `-l`, and never grep `xtal/mof/pormake`
   unless the question is about PORMAKE.
4. **Before editing a file you have not read**, `Read` the method
   you are changing. The Edit tool requires it, and it is what keeps an
   edit matched to the surrounding comments.

## Where things are, quickly

The layout table in `CLAUDE.md` names the packages. Beyond it:

| Question | Start at |
|---|---|
| What a menu entry does | `xtalapp/menus.py` `build_actions` (the `add(...)` calls), then the `MainWindow` method named as its slot |
| What a structure edit does | `xtalapp/document.py` (the verb), then `xtal/commands/` (the undoable command) |
| When an action is enabled | `shell_state.selection_states` for the selection's actions, then `_refresh_shell` and `_on_selection_changed` in `xtalapp/shell_state.py` (`ShellRefresh`, a mixin of `MainWindow`) |
| A module's settings | `xtal/modules/<name>.py`, the `Param(...)` tuples |
| A module's custom dialog | `xtalapp/dialogs/__init__.py` `_BY_NAME` |
| A force-field engine | `xtal/ff/registry.py`, `xtal/ff/<engine>/` |
| What is drawn and how | `xtalapp/viewport/builder.py` (model), `vtk_scene.py` (actors) |
| Preferences | `xtalapp/settings.py` (stored), `xtalapp/dialogs/preferences.py` (shown) |
| Which tests cover X | `ls tests \| grep -i X`, then `outline.py tests/test_X.py --no-docs` |

A test file's outline doubles as a specification: the test names are
sentences describing behaviour.
