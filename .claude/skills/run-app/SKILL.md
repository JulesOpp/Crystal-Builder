---
name: run-app
description: Launch the real Crystal Builder GUI and drive it - open a structure, trigger a toolbar or menu action, screenshot the 3D viewport, one dock or one dialog - to confirm a change works when a person clicks it. Use whenever asked to run, start, launch or screenshot the app or any of its panels or dialogs, to show a feature working, to judge a layout change, or to check a button that "does nothing". The suite cannot press buttons; this can.
---

# Running Crystal Builder

The 2000+ tests cannot tell you a button does nothing: widget tests
inject a stub `QWidget` in place of the VTK viewport and call methods
directly, so a broken `triggered` connection passes everything. Three
phases of "Add bond doesn't work" came from that gap. Close it by
building the window the entry point builds and pressing the thing.

## The driver

`.claude/skills/run-app/drive.py` launches a real `MainWindow` — real
VTK viewport, real plugins, real `ActionRegistry` — runs steps **in
command-line order**, and exits non-zero if a step fails.

```bash
python .claude/skills/run-app/drive.py --open resources/samples/MOF-5.cif --viewport-shot /tmp/view.png
```

It sets `QT_API=pyside6` and `XTAL_NO_CONFIRM_CLOSE=1` itself, so no
wrapper env is needed.

| Step | Does |
|---|---|
| `--open PATH` | open a structure; prints site and tab count |
| `--action NAME` | trigger a registered action, **failing if it is disabled** |
| `--eval CODE` | exec Python with `win`, `doc`, `app`, `tabs`, `viewport`, `settle()`, `imp()` |
| `--script PATH` | exec a Python file in that same scope, for a probe too long to quote in a shell |
| `--shot PATH` | PNG of the window chrome — toolbar, docks, tabs, status bar |
| `--viewport-shot PATH` | PNG of the 3D view, via VTK |
| `--grab EXPR PATH [WxH]` | PNG of **one dock or dialog**, shown or not |
| `--settle MS` | pump the event loop (worker threads, animations) |
| `--list-actions` | every action name, its menu text, and whether it is enabled |
| `--list-docks` | every dock's attribute name, title, and whether it is shown |
| `--scratch DIR` | preferences and default workspace in DIR, not the real ones |
| `--keep` | hand the running window to the user (blocks in `app.exec()`) |

Then `Read` the PNG. **Three kinds of screenshot**: `--shot` uses
`QWidget.grab()`, which cannot see into a native GL surface, so the
viewport comes out black; `--viewport-shot` goes through
`vtkWindowToImageFilter` and shows the crystal but no interface;
`--grab` is one panel or dialog on its own. Take whichever answers the
question.

## Panels and dialogs

Interface work is judged by looking at one panel, not the whole
window at the width of the right-hand column. `--grab` does it:

```bash
python .claude/skills/run-app/drive.py --scratch "$SCRATCH/drv" \
  --open resources/samples/MOF-5.cif \
  --grab style_dock "$SCRATCH/style.png" 420x800 \
  --grab 'imp("xtalapp.dialogs.preferences.PreferencesDialog")(win.settings, win)' "$SCRATCH/prefs.png"
```

- A bare identifier is a dock attribute (`--list-docks` names them).
  The dock is floated at `WxH` for the shot, then docked and hidden
  again as it was, so a tabbed-away panel still comes out.
- Anything else is a Python expression. `imp("pkg.module.Class")`
  imports one name. A dialog it builds is `show()`n, never `exec()`d,
  and closed after the shot. Constructors differ: read the dialog's
  `__init__` signature first (`code-map --find ClassName`).
- A dialog with pages (Preferences' list, a tab widget) needs a
  `--script` that selects each page and calls `widget.grab().save()`.
  Grab the page, not a scaled screenshot of the screen.

## A clean window: `--scratch`

Without it the driver runs with **your real preferences**: the last
workspace, recent files and saved layout, and whatever it opens is
recorded there and copied into that workspace. The chooser then
offers the scratch run's folder next launch.

`--scratch DIR` sets `XTAL_SETTINGS_DIR` and `XTAL_WORKSPACE_ROOT`,
the two the suite sets, so the window is a first run: default layout,
a new workspace under `DIR/workspace`, nothing written anywhere else.
Use it for **every screenshot meant for a person or the manual**, and
for any smoke run. Leave it off only when the bug lives in the saved
state, such as a layout that restores wrongly.

## A verification, end to end

```bash
python .claude/skills/run-app/drive.py \
  --open resources/samples/MFU4l.cif \
  --action select_all \
  --action recompute_bonds \
  --eval 'from xtal.core import bonding; print(len(bonding.perceive(doc.structure)), "bonds")' \
  --viewport-shot /tmp/after.png
```

`--list-actions` first when you do not know the name — they are
registry keys (`recompute_bonds`, `mode_add_bond`, `style_polyhedra`),
not menu text. `[disabled]` in that listing is itself an answer: an
action greyed out with a structure open is a bug the screenshot would
not have shown you.

## Timing something

`--script` is how you find out why the window went away. Patch what
you want to measure, drive the run, then pump the loop and time *that*
too -- the cost of a big table or a rebuilt scene is paid in deferred
events, so a handler that returns in 50 ms can still cost twenty
seconds afterwards:

```python
t = time.perf_counter()
app.processEvents(QEventLoop.AllEvents, 60000)
print(f"drain {time.perf_counter() - t:.2f} s")
```

When the drain is the expensive half and Python profiling shows
nothing, the work is in Qt or VTK. Sample the process instead:
`subprocess.Popen(["sample", str(os.getpid()), "8", "5", "-f", out])`
just before the drain, and read the main thread's stack.

**Patch bound methods, not with lambdas.** Replacing a slot with a
plain lambda changes the connection: a signal connected to a bound
method of a QObject is queued across threads, and one connected to a
loose callable is direct, so the handler starts running on the worker
thread and Qt prints cross-thread warnings your probe invented. Wait
on `dock.is_running` instead, as the suite does.

## Things that will bite

- **A modal hangs the run.** `QDialog.exec` and the `QMessageBox`
  statics are patched to raise, exactly as `tests/conftest.py` does.
  To exercise a step that opens one, patch the classmethod above it in
  an `--eval` step — `SupercellDialog.ask`, `ModuleDialog.ask` — the
  way `tests/test_run_progress_ui.py` does. `--allow-dialogs` only
  makes sense with somebody at the keyboard.
- **Never `QT_QPA_PLATFORM=offscreen` here.** On macOS it does not
  suppress dialogs, only stops them being drawn, and VTK renders
  nothing worth looking at.
- **`structure.bonds` is not the bond count.** Recalculating *drops*
  the stored graph and perception happens lazily, so the list reads
  empty and nothing is wrong. Ask `bonding.perceive(structure)`, or
  read the status string `doc.recompute_bonds()` returns.
- **Let it settle.** A shot taken before the window is realised is of
  a window that has not drawn. `--open` and `--action` already settle;
  add `--settle 2000` after anything that starts a worker thread — a
  UFF optimisation, a Zeo++ run.
- **Opening a file copies it into the active workspace.** Without
  `--scratch` that is whatever workspace the app last had open, which
  may be in a folder the sandbox cannot write (the status bar then
  says "could not copy into the workspace"). Use `--scratch`; if you
  did not, check `git status` afterwards and remove what the run
  created.
- Big frameworks are slow to draw. `MFU4l.cif` is the stress case;
  `MOF-5.cif` (424 sites) is the quick one.

## When the user wants to look at it

`--keep` after the setup steps leaves the window open and interactive:

```bash
python .claude/skills/run-app/drive.py --open resources/samples/ZIF-8.cif --keep
```

That blocks until they close it, and it leaves dialogs working, so run
it only when handing over — never as the last step of your own check.
