# Crystal Builder

A desktop crystal structure builder: read/write CIF, edit symmetry and
bonding, run force field / DFTB+ / Zeo++ calculations on the result.

## Layout

| Package | What it is |
|---|---|
| `xtal/` | The headless core. **Imports no Qt.** Anything crystallographic lives here and is testable without a display. |
| `xtal/core/` | Structure, lattice, symmetry, subgroups, bonding |
| `xtal/io/` | CIF and project (`.xtalproj`) read/write |
| `xtal/commands/` | Undoable operations on a structure |
| `xtal/ff/`, `xtal/modules/` | Calculators (UFF, DFTB+) and the module/job registry (Zeo++) |
| `xtalapp/` | The Qt/PySide6 + VTK GUI shell. Holds no crystallography of its own. |
| `xtalapp/mainwindow.py` | The shell: menus, docks, tabs. Large; see "Working in mainwindow" below. |
| `xtalapp/document.py` | `Document` — a structure plus its undo stack. The GUI asks the Document to change things; it does not edit structures directly. |

## Commands

```bash
python -m pytest -q                    # full suite, parallel, ~35 s
python -m pytest -q tests/test_bonding.py    # while iterating
python -m pytest -q -m "not slow"      # skip the seconds-long relaxations
python -m pytest -q -n0                # serial, for a readable traceback
ruff check .                           # lint (check only — see below)
crystal-builder                        # launch the GUI
```

`-n auto` is the default via `addopts`. Prefer a **targeted file** while
iterating and the full suite once before committing; the whole suite is
1400+ tests and running it after every edit is the single most
expensive habit in this repo.

## Conventions

- **Line length 79.** The code is hand-formatted to it. Run `ruff
  check` only — **never `ruff format`**, it will fight the layout. CI
  runs `ruff check .` with `E, F, W, I, UP, B`.
- **Comments say why, not what.** Look at any existing file: the
  docstrings explain the failure the code is avoiding. Match that.
  Don't add narrating comments.
- **Test names are sentences** describing the behaviour, not the
  function: `test_a_modified_tab_closes_without_a_question`, not
  `test_close_document`. Docstrings say what breaks if it regresses.
- `filterwarnings = ["error::DeprecationWarning"]` — a new deprecation
  fails the suite rather than scrolling past.
- Mark anything that takes seconds with `@pytest.mark.slow`.

## Testing the GUI

Just run `pytest` — locally, on macOS, the widget tests work against
the normal display and that is the fastest path.

**Do not add `QT_QPA_PLATFORM=offscreen` locally.** It does not
suppress dialogs, it only stops them being drawn, so a test that opens
a modal hangs with nothing on screen to say why. Offscreen is for CI
(Linux, no display), where the workflow already sets it.

Two autouse guards in `tests/conftest.py` keep the suite from ever
waiting on a person, and both must stay:

- `XTAL_NO_CONFIRM_CLOSE=1` is set for the whole session, so tearing
  down a window with unsaved edits does not raise the quit prompt.
- `QDialog.exec` and the `QMessageBox` static helpers are patched to
  **raise**. Reaching one is a bug in the test: patch the dialog, or
  the classmethod above it (e.g. `ModuleDialog.ask`), as
  `tests/test_run_progress_ui.py` does for Zeo++ runs.

A test that is *about* a prompt opts out with
`monkeypatch.delenv("XTAL_NO_CONFIRM_CLOSE")` and patches
`QMessageBox.question` itself — see
`test_closing_a_modified_document_asks_first`.

**If a parallel run ever hangs**, it is almost always orphaned xdist
workers from a previous interrupted run. They survive `pkill -f
pytest` and wedge every later run:

```bash
pkill -f pytest; pkill -9 -f "stdin.readline"
```

`MainWindow` takes a `viewport_factory`, so widget tests inject a stub
`QWidget` in place of the VTK viewport and never open a real GL
context. Copy the `window` fixture from `tests/test_open_once.py`.

`tests/conftest.py` provides four real structures as fixtures —
`rutile`, `quartz`, `halite`, `dry_ice` — chosen so that tetragonal,
non-orthogonal, centred, and molecular cases are all covered. Use them
instead of inventing a structure. Bigger real files are in
`resources/test/` and `resources/samples/` (`MFU4l.cif` is the usual
stress case).

## Environment variables

| Variable | Effect |
|---|---|
| `QT_QPA_PLATFORM=offscreen` | Run Qt with no display. CI only — see above. |
| `QT_API=pyside6` | Must be set before VTK imports its Qt bridge |
| `XTAL_NO_CONFIRM_CLOSE=1` | Close windows without the unsaved-changes prompt. **Set this whenever launching the app for a screenshot or a smoke run** — otherwise a modal nobody answers hangs the run. The test suite sets it for itself. |
| `XTAL_STUB_MODULE=1` | Register a fake calculation module, for module-machinery tests |
| `DFTB_PREFIX` | Where the DFTB+ Slater-Koster parameters live |

## Invariants — these are product decisions, not implementation details

- **Bonds are recalculated only when the user presses Recalculate
  Bonds.** Not on cell edits, not on load, not after an optimisation.
- **A force field or optimiser never changes the bonding or the
  atoms.** All structural changes are the user's, made explicitly.
- **Manually set bond types take precedence** over any distance-based
  determination.
- Structure edits go through `Document.apply(...)` with a `Change`
  flag, so they land as one undo step and refresh only the panels that
  care. Do not mutate a structure behind the Document's back.
- A long operation over a whole selection is applied **in one batch**,
  not atom-by-atom with a redraw between — that is what made Select
  All → Set Bond Type stall on MFU-4l.

## Working in `mainwindow.py`

It is ~2400 lines and is touched by nearly every change. When editing
it, read the specific method rather than the whole file, and prefer a
targeted `Edit` over rewriting the file.

Refreshing is deliberately split three ways and the distinction
matters for responsiveness: `_update_ui` rebinds panels when the
current document changes; `_on_structure_changed` refreshes what they
show; `_on_view_changed` touches only the shell's own widgets.
Rebuilding a site table because a spinbox moved is how a large
structure loses interactivity.

## Skills

`.claude/skills/` holds the workflows that are worth not re-deriving:

- **run-app** — launch the real window and drive it.
  `python .claude/skills/run-app/drive.py --open FILE --action NAME
  --viewport-shot OUT.png`. The suite stubs the viewport and cannot
  press a button; this can. Use it whenever "it works" needs looking
  at, and `--list-actions` to find an action's registry name.
- **pure-move** — moving code between modules without changing
  behaviour. One seam per commit, green suite between steps.

## Planning documents

`docs/PLAN.md` is the phase roadmap, `docs/ROADMAP.md` the delivery
order, `docs/TODO.md` everything raised while using the app that is
not yet scheduled. An entry is **deleted when it ships, not ticked**.
Keep them current — they are how work survives between sessions.
