---
name: add-action
description: Add a command to Crystal Builder's menus, toolbar or context menus - a new menu entry, a structure edit, a view toggle, an export - wired through the action registry, the Document, an undoable command, enabling rules and tests. Use when asked to add an option, entry, button or command to a menu or the toolbar (e.g. "add Merge atoms below Add centroid"), or to move or rename one.
---

# Adding a command

A command is defined **once**, in the action registry, and every menu,
toolbar button, context menu, shortcut and the generated Help page
reads it from there. Four places make a working command, plus the
tests. *Merge atoms* is the worked example throughout: it touched
exactly these files and nothing else.

## The chain

```
menus.build_actions  add("merge_atoms", "Mer&ge atoms", window.merge_atoms, tip=...)
        │
menus.build_menus    fill_menu(structure_menu, [..., "add_centroid", "merge_atoms", ...])
        │
MainWindow.merge_atoms          thin: current document, call it, show the sentence
        │
Document.merge_atoms -> str     the verb: validate, run commands in one transaction,
        │                       fix the selection, return a status sentence
xtal/commands/*                 the undoable change (reuse before writing a new one)
```

### 1. Register it — `xtalapp/menus.py`, `build_actions`

```python
add("merge_atoms", "Mer&ge atoms", window.merge_atoms,
    tip="Replace the selected atoms with one at their middle -- ...")
```

- **The key** (`merge_atoms`) is permanent: tests, the log, shortcuts
  and `run-app --action` use it. Snake case, a verb.
- **The label** carries a mnemonic `&` that does not clash within its
  menu, and ends in `...` only if it opens a dialog.
- **The tip** is the Help page's entry for the command, the tooltip,
  and the status-bar line. Write it for a user: what it does and the
  one thing that would surprise them. Without one, Help shows the name
  alone.
- `shortcut=` takes one key or a list of equivalent keys. Check for a
  clash first: `grep -n '"Ctrl+Shift+M"' xtalapp/menus.py`.
- `checkable=True` for a toggle; `group="..."` for mutually exclusive
  ones; `role=` for anything macOS moves into the app menu.
- Place the `add(...)` next to its neighbours in the file, which is
  in menu order.

### 2. Place it — `build_menus`, `build_toolbar`, `CONTEXT_MENUS`

- A menu: add the key to that menu's `fill_menu` list, where a user
  would look for it. `None` is a separator.
- The toolbar (`build_toolbar`): only for something pressed
  constantly; the bar already folds into a chevron below ~1214 pt.
- A right-click menu: `MainWindow.CONTEXT_MENUS` in
  `xtalapp/mainwindow.py`, keyed by `"atom"`, `"bond"`, `"view"`.
  `COUNTED_ACTIONS` gives an entry a "Delete 3 atoms" label.
- **Menu order is asserted** in `tests/test_app_shell.py`
  (`test_the_menu_bar_ends_with_window_and_help` and neighbours), so a
  new top-level menu or a moved group needs those updated in the same
  commit.

### 3. The window method — `xtalapp/mainwindow.py`

Thin. It finds the document, opens a dialog if the command asks for
values, calls the Document, and shows the sentence:

```python
def merge_atoms(self) -> None:
    document = self.current_document()
    if document is not None:
        self.show_status(document.merge_atoms())
```

A dialog is collected through a classmethod (`AddCentroidDialog.ask`)
so tests can patch it; `QDialog.exec` raises under the suite. Put the
method beside its siblings (`add_centroid_dialog`); read them with
`code-map` rather than the whole file.

### 4. The verb — `xtalapp/document.py`

All logic lives here or below it, never in the window:

- Validate and return a sentence instead of raising for user error
  ("select at least two atoms to merge").
- **One undo step**: several commands go inside
  `with self.transaction("Merge atoms"):`; a single one is
  `self.run(command)`. Never mutate `self._structure` directly.
- Reuse commands from `xtal/commands/` (`AddSites`, `DeleteSites`,
  `MoveSites`, ...). A new command belongs in `xtal/commands/`, imports
  no Qt, and gets a headless test.
- **Invariants** (CLAUDE.md): `AddSites(..., perceive=False)`, since
  placing an atom must not rebond; whole orbits, because symmetry ties
  images; a selection-wide change is one batch, not a loop of runs.
- Return the status sentence, in lowercase, the way its neighbours do.

A view-only command (style, visibility) goes to `document.view` or
`MainWindow.set_view` instead, and must not mark the document modified.

### 5. When it is enabled

Two places decide, and a command needs **both** or it goes stale:

- `MainWindow._refresh_shell`: on document or tab change; takes
  `editable` (false while a trajectory plays) into account.
- `MainWindow._on_selection_changed`: on every selection change.

```python
self.actions_.set_enabled(["add_centroid", "merge_atoms"],
                          len(document.selection.atoms) > 1 and editable)
```

Add the key to an existing list with the same rule rather than a new
call. An action that reads (export, measure) stays enabled while
playing; one that edits does not.

## Tests

- **The verb, headless-ish**: in the topic's test file
  (`tests/test_centroid.py` for merge), over a `Document` fixture.
  One test per behaviour, named as a sentence, docstring saying what
  breaks: `test_a_merge_is_one_undo_step`,
  `test_merging_fewer_than_two_atoms_does_nothing`. Cover undo.
- **The wiring**: build the `window` fixture (copy it from
  `tests/test_open_once.py`), open a real structure fixture (`rutile`,
  `quartz`, `halite`, `dry_ice`), then
  `window.actions_["merge_atoms"].trigger()` and check the effect, plus
  the enabled state before and after selecting.
- Nothing fails for an action registered but placed in no menu: the
  Help page lists it under **Elsewhere**. Check that section is not
  where yours landed, unless it really is reachable only from a context
  menu:
  `--eval 'from xtalapp.dialogs.help import command_sections; print(command_sections(win)[-1])'`.
- Run the files you touched, not the suite:
  `python -m pytest -q tests/test_centroid.py tests/test_app_shell.py tests/test_help_ui.py`.

## Verify with a click

```bash
python .claude/skills/run-app/drive.py --scratch "$SCRATCH/drv" \
  --open resources/samples/MOF-5.cif \
  --eval 'doc.select([0, 1])' --action merge_atoms \
  --eval 'print(doc.structure.n_sites, doc.undo_label)'
```

`--action` fails on a disabled action, which is itself the check that
step 5 is right.

## Renaming or moving one

- **Keep the key; change the label.** Then
  `grep -rn '"Old label"' tests` since a label is asserted in several
  tests (docs/MENUS.md § 4), and update them in the same commit.
- Moving between menus changes no test unless order is asserted.
- `docs/MENUS.md` is the record of the last menu redesign, not a live
  map; do not update it for one entry.
