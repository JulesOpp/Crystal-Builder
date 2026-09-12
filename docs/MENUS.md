# The menu bar and the toolbar

**Approved and built**, all four sections, in the same phase that
wrote it.  It stays here as the record of *why* each bar reads the way
it does — the "Today" tables below describe what was replaced, not
what is there now.  What was built:

| Section | What changed | Where |
|---|---|---|
| § 1 | `build_menus` creates the Window menu; `build_docks` fills it | `menus.py:533`, `layout.py:162` |
| § 2 | Structure · Symmetry · Cell, then Measure · View, then Modules · Window · Help; the mouse modes are a submenu; Open Recent moved up | `menus.py:build_menus` |
| § 3 | The element combo sits with Add atom; Reset view and the axis views close the bar | `menus.py:build_toolbar` |
| § 4 | Nothing renamed, so nothing in the six files changed | — |

Nothing was renamed, which is why § 4 cost nothing: every registry key
is the key it was, and the seven new tests in
`tests/test_app_shell.py` assert the new order rather than replacing
an old assertion.

One thing in it was not a matter of taste, and § 1 is that.

---

## 1. The defect: Window sat after Help

The menu bar read

> File · Edit · Select · Structure · Measure · Symmetry · Cell ·
> Modules · View · **Help** · **Window**

and the TODO entry asks for Help to be last.  It was not last, and no
file said to put Window after it.  The order was a side effect of the
construction order in `MainWindow.__init__`:

```python
menus.build_menus(self)          # mainwindow.py:132 -- through Help
menus.build_toolbar(self)
layout.build_docks(self)         # mainwindow.py:134 -- adds Window
```

`build_docks` ended with `menuBar().addMenu("&Window")`, because the Window menu is one toggle per dock and
the docks do not exist until it has built them.  `addMenu` appends, so
Window lands after everything `build_menus` had added — Help included.

That makes the menu bar's order a property of two files' *call order*
rather than of either file's contents, which is why it can be wrong
without any line looking wrong.

**Two ways to fix it.**

* **Insert Help last** — `build_docks` uses `insertMenu` to put Window
  before it, or `build_menus` re-inserts Help at the end.  Two lines,
  and it leaves the same trap: the next menu added by a third file
  lands after Help again.
* **`build_menus` owns the order; `build_docks` fills the menu.**
  ✅ *taken.*  `build_menus` creates every top-level menu,
  Window among them, in the order the bar should read:

  ```python
  window.window_menu = bar.addMenu("&Window")     # empty for now
  help_menu = bar.addMenu("&Help")
  ```

  and `build_docks` keeps the loop it already has, adding the dock
  toggles into `window.window_menu` instead of into a menu of its own.
  It is the same number of lines and it puts the whole order in one
  readable place — which is the property that was missing, not the
  position of one menu.

**Cost: none in the suite.**  Nothing asserted menu *order*.
`tests/test_ff_ui.py:171` asserts membership (`"&Modules" in titles`)
and `tests/test_modules_ui.py:107` asserts the Modules submenu list
equals the registry's labels; both survived the rearrangement
unchanged.  There is an order assertion now --
`test_the_menu_bar_ends_with_window_and_help` -- because the whole
point of § 1 is that the order should be something a file states
rather than something two files happen to produce.

---

## 2. The menu bar

### Before

| # | Menu | What is in it |
|---|---|---|
| 1 | File | new/open/samples, save file, export, workspaces, close, close all, recent, preferences, quit |
| 2 | Edit | undo/redo, clipboard, delete, change element |
| 3 | Select | all/none/invert, same element, by element, grow |
| 4 | Structure | add atom/centroid/hydrogens/molecule, fill pores, mark connection points, bonds, bond type, **and the six mouse modes** |
| 5 | Measure | measure selection, planes |
| 6 | Symmetry | find, set group, subgroup, standardise, primitive, Wyckoff, merge, invert, P1 |
| 7 | Cell | edit cell, supercell, Niggli, Delaunay, wrap |
| 8 | Modules | one submenu per registered module |
| 9 | View | style, show, background, display range, boundary, projection, axis views |
| 10 | Help | log, about |
| 11 | Window | one toggle per dock, reset layout |

### Now

> File · Edit · Select · **Structure · Symmetry · Cell** ·
> **Measure · View** · Modules · Window · Help

Three moves, and one rule behind all of them: **the menus that change
the crystal are together, the menus that change the picture are
together, and the menus that are about the application come last.**

* **Symmetry and Cell join Structure.**  All three edit the structure
  and land on the undo stack; Measure sits between them today and
  changes nothing.  A user who has just added an atom and wants to
  re-find the symmetry crosses one menu instead of three.
* **Measure joins View.**  Neither modifies the crystal: a distance,
  a plane, a style and a background are all things drawn on top of it.
  It is also where a user looks for Measure once they stop thinking of
  it as an edit.
* **Modules, Window, Help last.**  Modules is this application's
  Tools menu — it runs something and leaves a folder behind rather
  than editing what is open — and Tools · Window · Help is where every
  desktop application of this shape ends.  Help last is the entry's
  own requirement and § 1 is what makes it hold.

### Two moves inside a menu, worth taking with it

* **The six mouse modes leave Structure for a submenu.**  Select, Box
  select, Add atom, Add bond, Draw net and Measure are what the *mouse*
  does; they are checkable, they are already the middle of the toolbar,
  and as six flat entries under the bond commands they make Structure
  read as though a mode were an edit.  `Structure ▸ Mouse mode ▸ …`
  keeps the keyboard shortcuts, keeps the registry keys, and gives
  Structure a bottom that is all edits.  (`View` is the other candidate
  home and is worse: a mode decides what a click *does to the
  structure*, not how it is drawn.)
* **Open Recent moves up beside Open Sample.**  It is below Close
  today, at the far end of a menu whose top is where somebody opening
  a file is looking.

### Not done, and not owed

**Item 21, the Supercell rename, is withdrawn** rather than deferred.
`Cell ▸ Supercell...` builds a genuinely periodic supercell — a real
`na × nb × nc` cell, output in P1 (`xtal/commands/cell.py:71`) — so
"Non-periodic supercell" would name it for what the *other* control
does.  The non-periodic replication is the toolbar's a/b/c spins,
and those now read `cells a [1] b [1] c [1]`, which is the label the
entry was really asking for.

---

## 3. The toolbar

### Before

> Open · Save ║ Undo · Redo ║ Reset view ║ Select · Box select ·
> Add atom · Add bond · Draw net · Measure ║ Recalculate bonds ·
> `[element ▾]` ║ cells a `[1]` b `[1]` c `[1]`

Text buttons, eleven of them plus two widgets.  Two things are in the
wrong group and one thing that belongs on a toolbar is missing.

### Now

> Open · Save ║ Undo · Redo ║ **Select · Box select · Add atom ·
> `[element ▾]` · Add bond · Draw net · Measure** ║ Recalculate bonds
> ║ cells a `[1]` b `[1]` c `[1]` ║ **Reset view · a · b · c**

* **The element combo moves next to Add atom.**  Its own tooltip says
  "Element placed by Add atom" and it sits two controls away from that
  button, on the other side of a separator, beside Recalculate bonds —
  which it has nothing to do with.
* **Reset view moves to the right end, and brings the axis views with
  it.**  It is grouped with Undo and Redo today, which reads as though
  it undid something; Along a / b / c are the three commands a user
  presses as often as Reset view and they are on no toolbar at all.
  At the right end, next to the cell spins, the whole right-hand third
  of the bar is "what you are looking at" — which is also what the
  cell spins are.
* **Nothing is added or removed otherwise.**  A toolbar of eleven text
  buttons is already at the width where Qt starts folding the end of
  it into a chevron menu on a narrow window; the answer to that is
  icons, which is a separate piece of work with a separate cost (an
  icon set, and a decision about what happens to the labels).

**Width.**  The bar's size hint went from 1074 pt to 1214 pt, which
still fits a maximised window on a 15-inch screen (1512 pt) with room
to spare; below about 1214 pt Qt folds the right-hand end into a
chevron menu, as it already did below 1074.  The axis buttons are a
letter wide because a toolbar button shows the action's *icon text*:
`setIconText("a")` on the bar, `Along &a` still in the View menu.

**Cost: one line in the suite.**  `tests/test_reset_bonds.py:304`
reads the toolbar's actions and asserts `"&Recalculate bonds" in
on_bar` — membership, not position.  `tests/test_app_shell.py`'s new
label test finds the axis labels by their text.  Both survive any
reordering.

---

## 4. What renaming would cost, if any of this ever grows one

Rearranging is free.  **Renaming is the expensive half**, and it is
worth knowing which half of a rename is expensive before proposing
one.

Six test files assert on actions, and they split cleanly:

| Asserted | Where | What breaks |
|---|---|---|
| Action **text** | `test_reset_bonds.py:305` (`"&Recalculate bonds"`), `test_ff_ui.py:172` (`"&Modules"`), `test_modules_ui.py:107` (submenu labels = module labels), `test_context_menu.py:74`, `:143`, `:214` | A rename is the rename plus the literal in each of these |
| Action **keys** | `test_symmetry_ui.py:389` (`actions_["supercell"]`), `test_applog.py:188` (`"show_log"`) | Nothing, as long as the key stays |

So the rule for anything built from this document: **keep the registry
key when the label changes.**  A key is the name the whole application
uses — menus, toolbar, context menus, the log, saved shortcuts — and a
label is what one user reads.  `test_modules_ui.py:107` is the one to
watch, because it ties a *module's* label to the registry rather than
to a literal: renaming a module there is one edit and no test change.
