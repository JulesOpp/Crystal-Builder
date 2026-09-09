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
| `xtal/mof/`, `xtal/build/` | PORMAKE frameworks, and SMILES to a molecule. **PORMAKE is vendored** at `xtal/mof/pormake/` — MIT, trimmed of `jax`, `pymatgen` and `networkx`; see its `PROVENANCE.md`, and do not reformat it. The MOF builder needs the `ase` extra, the molecule builder the `build` one; the check is `find_spec` and never an import, and the entries grey out naming the extra. |
| `xtalapp/` | The Qt/PySide6 + VTK GUI shell. Holds no crystallography of its own. |
| `xtalapp/mainwindow.py` | The shell: menus, docks, tabs. Large; see "Working in mainwindow" below. |
| `xtalapp/document.py` | `Document` — a structure plus its undo stack. The GUI asks the Document to change things; it does not edit structures directly. |

## Commands

```bash
python -m pytest -q                    # full suite, serial, ~155 s
python -m pytest -q tests/test_bonding.py    # while iterating
python -m pytest -q -m "not slow"      # ~99 s; skips the 35 slow ones
python -m pytest -q --durations=20     # what the run is actually spending
ruff check .                           # lint (check only — see below)
crystal-builder                        # launch the GUI
```

**Serial is the default and it is not an oversight** — see the note in
`pyproject.toml`. `-n auto` finishes in 25 s and wedged four runs out
of eight; the deadlock behind that is described below. Prefer a
**targeted file** while iterating and the full suite once before
committing; the whole suite is 2000+ tests and running it after every
edit is the single most expensive habit in this repo, and more so now.

**No single test should take anything like a minute**, whatever the
suite as a whole costs. `--durations` is how to check that rather than
assume it. Two tests have been fixed rather than tolerated — the RCSR
expansion (45 s → 9 s, `_Sites` in `analysis/rcsr.py`) and the MFU-4l
cell relaxation (16 s → 6 s, `_scatter` in `ff/uff/terms.py`) — and
both fixes made the application faster by the same factor, which is
the only kind of test-speed fix worth making. The slowest test left is
about nine seconds.

The suite's own 155 s is the price of running serially, not of any one
test; getting it back means fixing the deadlock, not trimming tests.

It was 92 s before the MOF builder was vendored. Most of the increase
is that the builds in `tests/test_mof_builder.py` and
`tests/test_mof_vendored.py` now *run* — they used to skip on a
machine without PORMAKE and be ten seconds of import on one with it.
The slowest single test is the expansion-speed comparison in
`tests/test_mof_vendored.py`, at about 10 s, and it is 10 s because it
reads two large nets twice — once through the real PORMAKE.

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

**The startup chooser is the one dialog the suite never meets**, and
that is why it is called from `xtalapp/main.py` rather than from
`MainWindow.__init__`. `tests/test_workspace_chooser.py` builds the
widget and calls its methods; it never calls `exec`. Moving the
chooser into the constructor would fail every widget test at once.

**Settings go to a scratch directory, never to the real ones.**
`tests/conftest.py` points the INI backend at a temp directory of the
process's own, at import, before any `AppSettings` exists. On macOS
`QSettings` *is* CFPreferences, so without this every window fixture --
each naming its domain after `tmp_path` -- leaves a permanent plist in
the developer's own ~/Library/Preferences. The suite had left 278 of
them behind before anybody noticed. Do not give a window test a real
preferences domain.

**A full run wedges roughly one time in four, and it is a real
application bug rather than a test one.** `xtalapp/workers.py`
connects `worker.finished` to `thread.quit`; a bound method owns the
Python wrapper of the object it is bound to, so when nothing else
owns it, PySide6 frees a `QThread` wrapper *inside* signal delivery --
while Qt holds the connection mutex, calling back into Python for
`disconnectNotify`, which wants the GIL. Any thread holding the GIL
and asking Qt to connect something then waits for that mutex forever,
which is why every dump lands in `MainWindow.__init__` at a different
line. The same race can hang the shipped application when a module
run finishes. **Unfixed** -- holding the pair alive from Python is the
obvious remedy and it is not enough on its own; it broke
`test_modules_ui` outright.

**If you turn `-n auto` back on and a run hangs**, kill the orphaned
xdist workers before believing anything you measure next. They survive
`pkill -f pytest`, they wedge every later run, and a loop that
`kill -9`s the controller on a timeout manufactures a fresh one every
time -- which is how a hang rate of "one in six" grew to "one in two"
over an afternoon of measuring it:

```bash
pkill -f pytest; pkill -9 -f "stdin.readline"
```

To find a hang rather than guess at it, ask Python where it stopped:

```bash
python -m pytest -q -o faulthandler_timeout=40
```

Every thread's stack is dumped for any test that overruns, which is
what named the one above.

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
| `XTAL_WORKSPACE_ROOT` | Where the default workspace is made — the row the chooser offers on a first run, and what `restore_workspace` makes when a window is built without one. A test that let this answer with the real `~/Crystal Builder` would fill the developer's home folder, so `conftest.py` points it at a temp directory per test. |
| `DFTB_PREFIX` | Where the DFTB+ Slater-Koster parameters live |

## Invariants — these are product decisions, not implementation details

- **Bonds are recalculated only when the user presses Recalculate
  Bonds.** Not on cell edits, not on load, not after an optimisation,
  and **not when an atom is placed** — an atom arrives with the bonds
  the user gave it (Add atom draws one to its anchor) and no others.
  `AddSites(perceive=False)` and `bonding.hold_perception` are how;
  Add hydrogens is the deliberate exception, because bonding what it
  adds is the whole operation.
- **A dummy atom is a marker, not chemistry.** `X` — see
  `elements.DUMMY_ELEMENTS`. Perception never bonds one, and nothing
  that reasons chemically is ever handed one — it is **held back at
  the door** rather than refused, in three places that do the same
  thing: `markers.hold_back` for a force field (the engine is built
  over a structure with none, and `WithoutMarkers` presents the whole
  cell again with zero force on them), the same call in
  `hydrogens.plan`, and `job.without_dummies` / `restore_dummies` for
  a module run. Refusing was the old behaviour and it was wrong: a
  centroid is one click, and "delete the marker" throws away what the
  user added it for. Net edges and measurements take them, which is
  what they are for.
- **A force field or optimiser never changes the bonding or the
  atoms.** All structural changes are the user's, made explicitly.
- **Manually set bond types take precedence** over any distance-based
  determination.
- **A connection point is 0.75 A from the atom it hangs off**, not a
  bond length — `mof.block.CONNECTION_DISTANCE`, measured over the 867
  blocks PORMAKE ships. A block written at 1.4 A builds a framework
  with every linker bond twice too long and nothing reports it. It is
  an `X`, so everything that holds a marker back at the door already
  holds these back too, and there is no *Unmark*: an `X` does not
  remember what it was, so the way back is Ctrl+Z.
- **The workspace is asked for before anything opens, and everything
  lives in it.** `WorkspaceChooser` runs in `xtalapp/main.py` *before*
  `MainWindow` is built — recent workspaces listed, the last one
  selected, so Return is the answer for somebody with one. It is not
  in the constructor and must not move there: every widget test builds
  a window directly, and `conftest.py` patches `QDialog.exec` to
  raise. `MainWindow(workspace=...)` is how the answer gets in; with
  no answer, `restore_workspace` reopens the last one or makes the
  default, exactly as before. A file launched from Finder that is
  *already inside* a workspace skips the question (`Workspace.find`).
- **Every document has an entry, whichever of the four doors it came
  through.** A file opened from outside is copied in and **the tab
  follows the copy** (`place_in_workspace` → `Document.adopt`); where
  it came from stays in `structure.meta["source"]`, which is what
  still names the tab when that file is opened again
  (`DocumentSet._paths_naming`). File ▸ New makes `untitled` /
  `untitled-2` immediately, because a structure with nowhere to be is
  one whose first run has nowhere to land. Open Sample copies the
  bundled CIF in and opens the copy — that is what stopped Ctrl+S
  aiming inside a signed app bundle. A build is filed by
  `ModuleRunner._file_build`: one entry, **one** CIF written from the
  structure, the run's poorer copy dropped, the run moved underneath.
- **`add_structure` de-duplicates by content, never by name.** Two
  people's `MFU4l.cif` are two structures and get `MFU4l` and
  `MFU4l-2`. Deciding by name alone silently copied the second over
  the first. `filecmp.cmp(..., shallow=False)`; these are kilobytes.
- **Changing workspace closes every tab**, after the whole-window
  unsaved question asked *once* (`switch_workspace` →
  `may_discard_unsaved(question)` → `close_all_documents(force=True)`).
  A tab is a structure *of* the workspace it was opened in — its runs
  are filed there — so one carried across a switch files its next run
  into the folder the user walked away from, which was the behaviour
  and was a bug. The new workspace is opened **first**: a folder that
  turns out not to be one must not already have cost somebody the tabs
  they had. `set_workspace` is the swap alone, for construction.
- **A workspace remembers its own tabs.** `workspace.json` carries a
  `session` key of paths relative to the root — relative for the same
  reason `Workspace.find` walks upwards. It is advisory: a file that
  has gone is skipped in silence. Written whenever the tabs change,
  not at quit alone, and `WorkspaceShell._holding` is what stops a
  restore, or the closing half of a switch, recording itself. This
  replaced `startup_action` / `startup_sample`, which were a second
  and conflicting answer to "what is open when I start".
- **Save File converts, and never asks where.** `Ctrl+S` writes the
  session over the file the tab is. A document opened as a CIF becomes
  the `.xtalproj` of the same name beside it on its first save and the
  CIF is left exactly where it is — a conversion, because a CIF cannot
  hold a measurement, a plane, or the view it was being looked at in.
  Named after the *file* and not the entry (`_save_target`): two
  structures called MFU4l give entries `MFU4l` and `MFU4l-2` and both
  hold an `MFU4l.cif`, so asking the entry would send the second save
  somewhere the first did not. Overwriting is silent by default;
  `settings.confirm_overwrite` adds a confirmation, and only ever for
  a file that already exists. Only a document with no file at all
  still falls through to Save As, which outside the degraded path no
  longer happens.
- **The degraded window survives.** Every `workspace is None` branch
  downstream is still reachable and still means what it said: it is
  the folder-could-not-be-made path, not the default. The chooser
  reports such a failure inline and goes on asking, because there is
  no window behind it to report into.
- **The CIF carries the bonds; Export cleans.** `_geom_bond` says
  (site, site, operation, translation) and always could, so the
  workspace copy of a structure *is* the document: the markers the
  user placed and the net drawn over a framework are in the file. What
  a bond means here rides in `_xtal_bond_*` tags in the same loop, and
  **a foreign `_geom_bond` loop is not read as bonding** — it is
  nearly always a refinement's distance table, and reading one would
  bond a structure on open, which is what Recalculate Bonds exists to
  stay in charge of. `xtal.io.export.for_export` is the one door out:
  no dummy atoms, no net edges, no suppressions.
- **A building block drawn in the MOF builder goes to
  `<workspace>/blocks/`**, which the catalogue reads alongside
  PORMAKE's — `Workspace.blocks`, `Catalog.default(also_blocks=...)`.
  It is an ordinary directory of the workspace, so the tree shows it
  without being taught to; and because there is always a workspace,
  Draw no longer demands a folder be named before it will save.
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
