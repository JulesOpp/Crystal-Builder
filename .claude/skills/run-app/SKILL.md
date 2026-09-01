---
name: run-app
description: Launch the real Crystal Builder GUI and drive it - open a structure, trigger a toolbar or menu action, screenshot the 3D viewport - to confirm a change works when a person clicks it. Use whenever asked to run, start, launch or screenshot the app, to show a feature working, or to check a button that "does nothing". The suite cannot press buttons; this can.
---

# Running Crystal Builder

The 1400+ tests cannot tell you a button does nothing: widget tests
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
| `--eval CODE` | exec Python with `win`, `doc`, `app`, `tabs`, `viewport`, `settle()` |
| `--shot PATH` | PNG of the window chrome — toolbar, docks, tabs, status bar |
| `--viewport-shot PATH` | PNG of the 3D view, via VTK |
| `--settle MS` | pump the event loop (worker threads, animations) |
| `--list-actions` | every action name, its menu text, and whether it is enabled |
| `--keep` | hand the running window to the user (blocks in `app.exec()`) |

Then `Read` the PNG. **Two screenshots, not one**: `--shot` uses
`QWidget.grab()`, which cannot see into a native GL surface, so the
viewport comes out black; `--viewport-shot` goes through
`vtkWindowToImageFilter` and shows the crystal but no interface. Take
whichever answers the question, or both.

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
- **Opening a file copies it into the active workspace.** The
  workspace is whatever the app last had open (currently rooted at
  `resources/test/`), so a smoke run leaves a new folder behind. Check
  `git status` afterwards and remove what the run created.
- Big frameworks are slow to draw. `MFU4l.cif` is the stress case;
  `MOF-5.cif` (424 sites) is the quick one.

## When the user wants to look at it

`--keep` after the setup steps leaves the window open and interactive:

```bash
python .claude/skills/run-app/drive.py --open resources/samples/ZIF-8.cif --keep
```

That blocks until they close it, and it leaves dialogs working, so run
it only when handing over — never as the last step of your own check.
