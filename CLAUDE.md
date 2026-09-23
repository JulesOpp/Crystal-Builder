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
| `xtal/ff/`, `xtal/modules/` | Calculators (UFF with UFF4MOF, xTB, DFTB+, MACE) and the module/job registry (Zeo++). MACE is the one that runs in process rather than as a binary; it needs the `mace` extra, and `_load_model` is the seam its tests replace. |
| `xtal/mof/`, `xtal/build/` | PORMAKE frameworks (`orient.py` is which way round a node goes), and SMILES to a molecule. **PORMAKE is vendored** at `xtal/mof/pormake/` — MIT, trimmed of `jax`, `pymatgen` and `networkx`; see its `PROVENANCE.md`, and do not reformat it. The MOF builder needs the `ase` extra, the molecule builder the `build` one; the check is `find_spec` and never an import, and the entries grey out naming the extra. |
| `xtalapp/` | The Qt/PySide6 + VTK GUI shell. Holds no crystallography of its own. |
| `xtalapp/mainwindow.py` | The shell: menus, docks, tabs, and three mixins it inherits -- `shell_state.ShellRefresh` (refreshing and enabling), `symmetry_actions.SymmetryActions`, `edit_actions.EditActions`. See "Working in mainwindow" below. |
| `xtalapp/document.py` | `Document` — a structure plus its undo stack. The GUI asks the Document to change things; it does not edit structures directly. |

## Commands

```bash
python -m pytest -q -n 3               # full suite, three workers, ~2 min
python -m pytest -q -n0 tests/test_bonding.py  # while iterating
python -m pytest -q -n 3 -m "not gui"  # headless core only, ~1 min
python -m pytest -q -m "not slow"      # skips the ones marked slow
python -m pytest -q --durations=20     # what the run is actually spending
ruff check .                           # lint (check only — see below)
crystal-builder                        # launch the GUI
```

**`pyproject.toml` defaults to `-n auto`; pass `-n 3`.** The default
was made parallel once the worker deadlock below was fixed, and a plain
`pytest` now starts a worker per core -- eight here, which leaves the
machine unusable while it runs. Three workers finish the suite in about
two minutes and leave the rest of the cores free. `-n0` for a targeted
file, where starting workers costs more than it saves. CI runs serial.
Prefer a **targeted file** while iterating and the full suite once
before committing; the whole suite is 3000+ tests and running it after
every edit is the single most expensive habit in this repo.

**`-m "not gui"` is the headless half**: `conftest.py` marks every
module that imports `xtalapp` or `PySide6`, which is 1500 of the 3360
tests and every window the suite builds. Building windows is a quarter
of the suite's time -- about 80 ms each, a thousand of them -- so a
change under `xtal/` is checked in half the time the whole suite
takes. Memory is not what that saves: a window is 25 MB, freed at the
end of its test, and a worker's 200-600 MB is the transients of the
tests it runs rather than windows piling up.

**No single test should take anything like a minute**, whatever the
suite as a whole costs. `--durations` is how to check that rather than
assume it. Two tests have been fixed rather than tolerated — the RCSR
expansion (45 s → 9 s, `_Sites` in `analysis/rcsr.py`) and the MFU-4l
cell relaxation (16 s → 6 s, `_scatter` in `ff/uff/terms.py`) — and
both fixes made the application faster by the same factor, which is
the only kind of test-speed fix worth making. A third is the net
reader: `read_cgd`'s overlap check was ase's neighbour list, 3.9 s of
the 4.0 s `naz-x` took, and is now a KD-tree (see
`xtal/mof/pormake/PROVENANCE.md`), which took `test_mof_vendored.py`
from 42 s to 11 s and every MOF build with it. The slowest tests left
are about eleven seconds: the RCSR coordination sweep and descending
MFU-4l through all 237 of its subgroups.

The suite's time is the price of running serially, not of any one
test; getting it back means fixing the deadlock, not trimming tests.
It crept from about three minutes to eight or nine, and is 235-330 s
after the fixes below -- the spread is the machine's memory pressure,
not the code.

**Upstream PORMAKE and MACE never load into the test process.** The
comparison against the real PORMAKE reads a recording,
`tests/data/pormake_upstream.json`, written by the script beside it;
one slow test re-derives a sample in a subprocess. The two MACE tests
that need mace run it in a fresh interpreter. Keep it that way: see
"Aborted runs" below for what loading them mid-run costs.

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

A context menu waits the same way, and **`QMenu.exec` cannot be
patched** -- PySide resolves it in C++ and an override on the class is
ignored, unlike `QDialog.exec`. So every context menu is raised
through `xtalapp.menus.popup`, and that is what the guard replaces; a
test that means to open one patches it itself. The gap cost three CI
jobs 30 minutes each, cancelled at 98 % with nothing in the log saying
which test it was, which is also why CI now caps at 12 minutes and
dumps stacks at `faulthandler_timeout=180`.

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

**A test's windows are deleted when it ends** (`pytest_runtest_teardown`
in `conftest.py`). pytest-qt closes each registered widget and calls
`deleteLater`, but `processEvents` does not deliver a deferred delete
outside a running event loop, so no window was ever freed: 74 live
`MainWindow`s, 68 000 widgets, 86 threads and 1.2 GB a third of the way
through. Do not remove it.

**Aborted runs** (`Fatal Python error: Aborted` or `Segmentation
fault` with a stack ending in `dlopen`, and no pytest failure line)
are macOS 13.2's dynamic loader failing under memory pressure — the
crash report's `ktriageinfo` says "pmap_enter retried due to resource
shortage". They happened when a heavy stack (mace's 227 libraries,
upstream PORMAKE's pymatgen and jax) was loaded half way through a
process already holding ~750, on a machine with 10 GB of its 11 GB
swap in use. Reports are in `~/Library/Logs/DiagnosticReports`. The
cure is to load less in the test process, not to retry: run a test that
needs a large optional stack in a subprocess, as `test_mace.py` does.
Check `sysctl vm.swapusage` before trusting a run's timing.

**A full run used to wedge roughly one time in four, and it was a
real application bug rather than a test one. Fixed 2026-09-21.**
`xtalapp/workers.py` wired `finished` to `deleteLater` on both the
worker and its thread, which put the destruction of two Python
wrappers at two moments nobody chose. A Python wrapper cannot be
destroyed without the GIL, and `~QObject` severing its connections
holds Qt's connection lock while calling back into Python for
`disconnectNotify` -- Qt documents that hazard on `disconnectNotify`
itself. A thread holding the GIL and asking Qt to connect anything
then waits on that lock forever, which is why every dump landed in
`MainWindow.__init__` at a different line, and the same race could
hang the shipped application when a module run finished.

Nothing is deleted by Qt now: both objects are owned from Python, on
the GUI thread, by a `_Run` held in a module-level set, and dropped
one clean event-loop turn after the thread has stopped. The set is
module level and **not** an attribute of the caller on purpose --
holding them in `module_runner.module_worker` or `FFPanel.worker` is
what `test_modules_ui` waits on going `None`, and is why the earlier
attempt at this broke it. `MainWindow.closeEvent` stops the Force
Field worker as well as the module one and then waits; a docked
widget gets no close event when its window closes, which is why
`FFPanel.closeEvent` was never covered.

Measured across five configurations, 150 jobs a run, three runs each:
the old arrangement aborted every run of three of them (the two with
an unparented thread, and a second run overlapping the first);
this one was clean in all fifteen.
`review/probes/` in the `features/deep-review` branch has the harness
(`stress_workers.py`, `matrix.sh`) if it is ever worth re-checking.

**If you run `-n auto` and it hangs**, kill the orphaned xdist
workers before believing anything you measure next. They survive
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
- **A site is on a special position when its coordinates say it is,
  to the precision they were written at.** `p1.SPECIAL_POSITION_TOL`
  is 0.05 A and is not a numerical tolerance: four decimal places on a
  thirty-Angstrom cell is 0.003 A, and an optimiser step or a drag is
  larger still. It was 1e-3, and a site a rounding place off its
  mirror was then generated by every operation that should have mapped
  it onto itself — `CFA1.cif` put three Zn 0.0018 A apart on the
  3-fold axis, `Ni2Cl2BTDD.cif` gave a BTDD linker four bridging
  oxygens where it has two, and one 0.02 A drag of Zn1 in MFU-4l took
  the cell from 648 atoms to 712. Nothing reported it: duplicate
  merging compares a site against *other* sites' images and never
  against its own, so Merge Duplicates said "no duplicates" and
  **Reduce to P1 was the first thing that drew them** — and got the
  blame. The optimiser's site projectors (`SymmetryDOF._projectors`)
  use the same tolerance: at 1e-6, MFU-4l's Cl1, written 0.0006 A off
  its three-fold axis, got only the mirror, and a held Cl–Cl distance
  walked it off the axis and tripled the chlorides. The count is flat from 0.01 A to 0.2 A on every structure in
  `resources/samples`, and no two real atoms are that close. Where the
  atom *goes* is unchanged: the first operation to reach a point still
  wins, which near a special position is the identity. Snapping a site
  onto the position is idealisation, and Standardize is where that
  lives.
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
- **A drag moves the copy the cursor has hold of.** Move mode displaces
  *sites*, but the delta it is given is the one the drawn atom sees, so
  the site moves by the inverse of the operation that generated it
  (`MoveSites.by_image_delta` / `by_image_rotation`,
  `p1.parent_coordinates`) and the atom under the cursor follows the
  cursor in every space group. Handing the parent the cursor's travel —
  which is right for a number typed into the Move dock — slides the
  atom sideways in everything but P1. One image per site is all it can
  promise; where two images of one site are selected, the first wins.
- **Alt claims a Move drag, and shift is then read inside it.** Plain
  drag translates in the plane facing the camera, alt turns the
  selection about its own middle (a trackball, one radius of travel to
  the radian), shift-alt moves along the view axis. Shift means
  "extend the selection" only when Alt is not held — a gesture that
  turns a fragment is not one in which adding an atom to it means
  anything.
- **A click inside a net edge is the net edge**, whatever chemistry
  crosses under it: within `picking.TOPOLOGY_CORE_FRACTION` of the
  axis the edge wins, outside it whatever is behind it does, and an
  atom always does. Depth alone was the old rule and it meant a click
  aimed at the net selected the bond beneath — with `Del` then
  suppressing that bond and its whole orbit, 96 chemical bonds on
  MOF-5 with the net still on screen.
- **A connection point is 0.75 A from the centroid of the atoms it
  hangs off**, not a bond length — `mof.block.CONNECTION_DISTANCE`,
  measured over the 867 blocks PORMAKE ships. A block written at 1.4 A
  builds a framework with every linker bond twice too long and nothing
  reports it. It is an `X`, so everything that holds a marker back at
  the door already holds these back too, and there is no *Unmark*: an
  `X` does not remember what it was, so the way back is Ctrl+Z.
  It said *the atom* until 2026-09-20, and that is why MFU-4l and
  Ni3(HITP)2 could not be built: a chelate meets its metal through two
  atoms, and marked one at a time those blocks come out with twice the
  coordination number they have and fit no net in the catalogue.
  **An attachment is one `X` plus the *distinct* body atoms bonded to
  it** — `xtal/mof/attach.py`. The bond block said so all along and
  PORMAKE has always read it, so nothing new enters the `.xyz`.
  Distinct and never the bond count: 54 shipped points carry more than
  one bond *record* and 52 name one partner twice, across 26 blocks.
  With one member the centroid is that atom, so every single-point
  block is written byte for byte as it was, pinned by a test rather
  than argued. Two bonds are no longer refused; what is, is a point
  bonded to another point, members further apart than
  `attach.MAX_ATTACHMENT_SPAN`, and a point facing back into the
  molecule — judged one bond in and never against the block's middle,
  because a node's arms are concave and 77 of the 4256 shipped points
  face their own centroid. *Mark as one connection point* is the
  gesture that makes one, and the grouping is the structure's own
  bonds rather than new state on a marker, which is why there is
  still no *Unmark*. **A joint is as many bonds as the two ends have
  members**, paired by rectangular assignment on distance so that
  every member arrives bonded: PORMAKE writes one bond per joint and
  which member it keeps is an accident, so `build._joints_of`
  enumerates them from `info` instead and the enumeration owns the
  joint. MFU-4l on `pcu` goes from 6 joints to 12.
- **Which way round a symmetric node goes is a tie, and the default
  breaks it so that the faces across every edge agree.** An
  octahedral node fits its slot 24 ways at the same RMSD while its
  body moves 8.2 A between them. `xtal/mof/orient.py` enumerates that
  tie set — the block's rotation group from ordered *pairs* of
  connection directions and the normal they span, never triples,
  because three directions of a planar block span no volume and
  triples would call a trigonal node unsymmetric — and `consistent`,
  **the default since 2026-09-21**, minimises `attach.pair_cost` over
  the two nodes each edge joins; it is what builds MOF-5 with its
  clusters alternating. It was `as-found` until then, and what made
  the change safe is structural: the search **starts from the fit**
  (`orient._admit` -- the fit need not be in the tie set `tie_set`
  locates afresh), moves a node only where it is *strictly* cheaper,
  and a second pass is **thrown away** if its `max_rmsd` is worse
  than the first's by more than `orient.FIT_SLACK` or its cell is not
  the first's to `orient.CELL_SLACK` (0.5 %): a tie cannot move the
  cell, and `dia` on N623 turned collapsed *b* to 0.007 A with every
  block "fitting" to 1e-4. `build._build` returns
  at pass 1 unless some *node* presents a frame -- several atoms at a
  point, or a face -- so a build of faceless nodes is what PORMAKE
  made. `as-found` stays, one down in the form, and is byte for byte
  PORMAKE's build; the upstream comparison in `test_mof_vendored.py`
  asks for it by name. The results table's *Joint twist left* is
  what the rule could not fix: `pcu` x 1x1x1 on N16 is 6.0 over 3,
  because one slot cannot alternate.
- **A face is scored, never bonded.** A connection point standing for
  one atom presents the plane of that atom and its two other
  neighbours (`attach.face_of`): a carboxylate on N16, a ring on E14.
  That is why MOF-5's clusters alternate -- a Td node's opposite
  carboxylates are a quarter turn apart, so neighbours the same way
  round meet with the two carboxylates on each linker at 90 degrees,
  against 0 in the crystal. The plane is the atom's and its
  neighbours', never where the `X` was written (2045 of 3899 shipped
  faces have it off the plane); one neighbour (linear) or three
  (a rotor, a metal) is no face. A face never enters `members_of`,
  so joints and bond counts are what they were: `bond_joints` still
  asks `_is_polydentate`, and MOF-5 has its 48 joints.
- **A linker's angle about its own axis is not "as found", because
  the fit never found it.** Placing a two-connected block is Kabsch
  on two vectors — "not uniquely defined", as scipy says out loud —
  so `orient.align_edges` settles it in closed form after every
  build, whatever `orientation` asked for, and that is not a hole in
  the rule above: there is no earlier decision there to be faithful
  to. It is a refinement and not a second fit because **both
  connection points are on the axis** and a turn about it moves
  neither, so the RMSD, the relaxed cell and every X-to-X
  coincidence stay true. `phi* = -arg(sum z_here conj(z_there))`
  over the unit laterals, the pairing re-solved once at `phi*`; the
  cost is `attach.pair_cost`, the same one the discrete rule
  minimises. What turns is asked of the **block** — two points and a
  face at one of them — and never of the slot, so a two-connected
  *node* turns too. **Faces count only under `consistent`**
  (`align_edges(faces=...)`) -- the default, so E14 turns until its
  ring lies flat on both carboxylates it meets; under `as-found` no
  shipped block is on that list. Ni3(HITP)2's own blocks come back
  wanting 6e-08 radians, which is the crystal's angle and below
  `_STILL`.
- **A layer net is stacked after it is built, never by the builder.**
  The layers are the RCSR's own: every 2-periodic net in its file
  that PORMAKE can build on (196 of 200; `catalog.PORMAKE_REJECTS`
  names the four), written flat in the plane group's layer group at
  c = 10 by `rcsr.as_layer` and held as text (`catalog.rcsr_layers`)
  -- PORMAKE is handed a file only when one is built on. `hcb` is,
  value for value, the hand-written file it replaced in
  `xtal/mof/library/nets/`, which is gone. PORMAKE's scaler multiplies
  *c* with everything else (10 → 107 A on Ni3(HITP)2), so `xtal/mof/layers.restack` rewrites it,
  moving framework, net and placed blocks together and putting the
  sheets' *mean planes* one spacing apart. A layer is known by its
  graph (`Topology.is_layer`), and a spacing or offset given for a
  3-periodic net is refused, never ignored. PORMAKE's own nets arrive
  already answered -- every one is 3-periodic, recorded by
  `catalog._record_pormake_dimensions` and re-derived by a slow test
  -- because asking 2400 graphs is ten seconds, and the picker's
  3D / 2D boxes need the answer for every row. The RCSR's layers are
  told the opposite, and re-derived the same way.
- **An interpenetrated framework carries the bonds its copies had,
  and the detector says whether it worked.**
  `xtal/analysis/interpenetrate.py` enumerates rather than theorises
  (there is no topological test for which nets self-interpenetrate):
  Class Ia translations from the index-*n* superlattices of the
  structure's lattice, and at two-fold the Class II inversions
  through eighth-cell points -- which for a centrosymmetric framework
  are translations, and are how 2-fold MOF-5 is found at ¼,¼,¼,
  which no half-vector of its F cell reaches. Rows a *detected*
  symmetry relates are one row. Each is scored by the closest contact
  between copies; one closer than the bond rules' criterion or
  `MIN_CONTACT` is refused by name. Copies carry explicit bonds, the
  stored perceived graph and the drawn net -- nothing is perceived --
  and the array is refused unless `copies()` (the sum of
  `Net.multiplicity` over components) counts *n* times the original.
  Same cell, P1. Two doors: Structure ▸ Interpenetrate… and the MOF
  builder's `interpenetration`.
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
  Open Sample on the chooser answers through `ask` too -- it returns
  `(workspace, sample)` and `main.open_window` opens the sample once
  the window exists, never the constructor.
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
  `Workspace.adopt_build`: one entry, **one** CIF written from the
  structure, the run's poorer copy dropped, the run moved underneath.
  It is the core's and not the window's, so `xtal run mof.build
  --workspace` files a build exactly as the window does.
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
- **An autosave is a side file, never the document.** Every two
  minutes (`settings.autosave_interval`, 0 is off) each tab edited
  since the last tick is written with `Document.write_project` to
  `<workspace>/.autosave/`, mirroring its place in the workspace
  (`Workspace.autosave_path`) -- never where Save writes, so *Save
  File converts* and silent overwriting keep meaning what they say. It
  is deleted when the document is clean again (saved, or undone to the
  file) and when unsaved work is deliberately discarded (a tab closed
  or a quit answered yes), so what is left is exactly the work nobody
  chose to lose. It is **offered back, never applied**: opening a file
  with a newer autosave puts a `NoticeBar` up, and Restore is
  `Document.recover` -- one undo step, the project's own bonds,
  nothing perceived. `xtalapp/autosave.py`.
- **Quitting asks before it stops anything.** `closeEvent` and
  `confirm_quit` ask *a calculation is running -- stop it?* first and
  the unsaved question second, and stop the run only once both are
  yes; a No to either leaves the window, the edits and the run as they
  were. It used to stop the run and then ask, so a No lost an
  overnight scan anyway.
- **The degraded window survives.** Every `workspace is None` branch
  downstream is still reachable and still means what it said: it is
  the folder-could-not-be-made path, not the default. The chooser
  reports such a failure inline and goes on asking, because there is
  no window behind it to report into.
- **A porosity run draws where the pores are, and does not pretend
  to know where D_f is.** Zeo++'s `-visVoro` gives every accessible
  Voronoi node with the radius that fits at it, so the largest
  *included* sphere is drawn at its node exactly — twice that radius
  is the D_i in the table beside it. D_f is the width of a bottleneck
  on an *edge* and no Zeo++ output carries edge radii, so what is
  drawn for it is the path it travels along and the report says so.
  The network lives on the Document beside the planes: put there by a
  run (`JobResult.overlay`), not an edit, not on the undo stack, not a
  reason to mark the file modified, saved into the project's session,
  and **dropped the moment the arrangement it measured changes** —
  there is nothing to refit a Voronoi decomposition to. It goes to the
  document the run was *started from*, never the tab in front: a
  structure adopted into the wrong document is visibly the wrong
  crystal, and a pore network over the wrong one is a plausible
  picture of channels that are not there.
- **The pore surface is ours, and it is one measurement with the
  number beside it.** Zeo++ 0.3 cannot supply a distance grid —
  `-gridGAI` aborts on MFU-4l and `-gridG` runs for minutes writing
  nothing — so `xtal/analysis/grid.py` builds it by KD-tree over the
  cell and its 26 neighbours, and `xtal/analysis/isosurface.py`
  marches it (**tetrahedra, not cubes**: a cube has fourteen ambiguous
  sign patterns and a tetrahedron has none). The radii are whichever
  the run was given — `porosity.ZEO_RADII` is Zeo++'s own table,
  transcribed, because it is compiled into the binary and written
  nowhere it could be read back, and a test checks the transcription
  against the vendored source. **The surface is not written into the
  project**: MFU-4l's is 307 680 triangles and 96 MB of JSON against
  1.1 seconds to compute it again. The grid is float32 and the march
  goes a slab of cells at a time, so that second peaks at about 90 MB
  rather than 400.
- **The CIF carries the bonds; Export cleans.** `_geom_bond` says
  (site, site, operation, translation) and always could, so the
  workspace copy of a structure *is* the document: the markers the
  user placed and the net drawn over a framework are in the file. What
  a bond means here rides in `_xtal_bond_*` tags in the same loop, and
  **a foreign `_geom_bond` loop is not read as bonding** — it is
  nearly always a refinement's distance table, and reading one would
  bond a structure on open, which is what Recalculate Bonds exists to
  stay in charge of. `xtal.io.export.for_export` is the one door out:
  no dummy atoms, no net edges, no suppressions. **A scan point's CIF
  also carries the perceived graph** (`write_cif(perception=True)`,
  an `_xtal_perceived_bond_*` loop of P1 bonds), because its cell is
  not the one the bonds were perceived at and opening it would
  otherwise perceive again — MFU-4l at +15% on *a* opens with 560 of
  its 848 bonds. The reader takes it only if every bond is still the
  length it was written at; ordinary saves do not write it.
- **A building block drawn in the MOF builder goes to
  `<workspace>/blocks/`**, which the catalogue reads alongside
  PORMAKE's — `Workspace.blocks`, `Catalog.default(also_blocks=...)`.
  It is an ordinary directory of the workspace, so the tree shows it
  without being taught to; and because there is always a workspace,
  Draw no longer demands a folder be named before it will save.
- Structure edits go through `Document.apply(...)` with a `Change`
  flag, so they land as one undo step and refresh only the panels that
  care. Do not mutate a structure behind the Document's back.
- **A colour a person did not choose is worked out from the palette.**
  Hint text, a warning and a warning box are the three tones in
  `xtalapp.widgets.tone`; nothing styles one by hand, and
  `tone.retone` restyles them when the theme changes (a test sweeps
  the source for the old literals). The viewport follows too --
  *View ▸ Background ▸ Follow the system*, which is what a structure
  with no view of its own starts as -- while **a colour chosen by
  hand is never overwritten**, by a theme change or anything else.
- **A panel never holds its column open.** A dock area is as wide as
  the largest minimum of any dock shown in it, tabbed behind or not,
  so no dock may need more than `xtalapp.docks.MAXIMUM_MINIMUM`
  (200 px) either way: set no `setMinimumWidth` on dock contents, and
  put a tall or wide form inside `xtalapp.docks.scrolling`. Dock tab
  bars scroll rather than widen (`layout._ScrollingDockTabs`), and
  panels are not native windows (`keep_siblings_non_native`, called
  wherever a `QApplication` is made). `test_window_layout.py` holds
  all three. A panel of groups reflows rather than scrolling sideways:
  `xtalapp.docks.columns.ReflowColumns` puts them in two columns once
  no form row would wrap, and in one below that (the Style panel).
- A long operation over a whole selection is applied **in one batch**,
  not atom-by-atom with a redraw between — that is what made Select
  All → Set Bond Type stall on MFU-4l.
- **A scan holds a coordinate; it does not freeze the atoms that
  define it.** Freezing four atoms to hold one dihedral removes twelve
  degrees of freedom to constrain one, and the profile that comes back
  is the constraint's rather than the material's. `xtal/ff/
  constraints.py` projects the search direction off the coordinate's
  gradient and restores the point onto it by Newton — inside the line
  search, so the search walks *along* the constraint and the energy it
  compares belongs to a point that satisfies it. The projector is
  applied **after** the site-symmetry projectors and the frozen mask,
  so a constraint can only ever take freedom away: a site on a mirror
  stays on it, a frozen site stays frozen. A coordinate nothing may
  move — one the group ties, like every Na–Cl distance in Fm-3m — is
  refused before the first step, not discovered on the hundredth.
- **A held cell quantity is a strain subspace, not a check.**
  `CellFreedom` (`xtal/ff/optimize.py`) intersects the space group's
  allowed strains with the null space of whatever is held, in a
  metric-normalised coordinate — the shears scaled by √2, because only
  there is the group's average an orthogonal projector and only there
  does intersecting subspaces give the right subspace. Holding the
  **volume** with the shape free is the scan the flexible-framework
  literature actually runs; a profile at a frozen cell *shape* is a
  measurement of the shape that was frozen.
- **A scan point is written the moment it finishes.** Not gathered up
  and saved at the end. A scan is an overnight job — 0.44 s a step on
  Ni2Cl2BTDD's 1152 atoms under UFF, so a 12×12 grid is ~2.6 hours —
  and Stop, a crash or a full disk has to leave a landscape behind
  rather than lose one. It runs in **one job on one thread**, never
  one per point: `xtalapp/workers.py` has an unfixed teardown race
  (see § Testing and threads in `docs/TODO.md`) and multiplying it by
  144 would make an overnight scan a coin toss.
- **An unconverged scan point is not a number.** NaN, hatched on the
  heat map, outside the colour scale, crossed out in the contour
  window, `--` in the log. A hole plotted as a zero is the deepest
  point of every landscape it appears in, and a false minimum looks
  exactly like a real one. Measured: the same target cell relaxed from
  a neighbour and from the input differed by 2.60 kcal/mol at 300
  unconverged steps, which is why both scan directions are walked by
  default and drawn apart rather than averaged.
- **A scan refuses what it cannot hold, before the first point.**
  `scan.plan` runs the constraint check against the asymmetric unit,
  so a distance the group fixes is a message in the dialog, not a
  grid of holes. A point whose relaxed cell expands to a different
  atom count is a hole with the reason beside it, never a number for
  another crystal. Scanning with the symmetry broken is Reduce to P1
  first — the scan never drops the group on its own.
- **An axis is written `distance 32, 33`**: commas or spaces between
  anchors, `+` inside a centroid (`plane 0+1+2, 6+7+8`). The older
  `0,1,2 6,7,8` still parses when the new reading gives the wrong
  count, so old logs re-run.
- **A scan leaves `report.json`**, and double-clicking it in the
  workspace puts the landscape back in the Results panel
  (`xtal.modules.report.save` / `load`, surface paths relative to the
  run). Only modules whose report is small write one.
- **The atom types table is one widget** (`xtalapp/widgets/
  atom_types.py`), shown by the Force Field panel and by the scan
  dialog for any engine that `provides` types. An override made in
  either is `Document.set_atom_type` — one undoable edit both show.
- **A scan reads the engine; it does not configure one.** The Force
  Field panel is where an engine is set up, and
  `xtalapp/dialogs/scan.py` reads it — the same bargain
  `xtalapp/dialogs/dftb_run.py` strikes with the Hamiltonian. A scan
  returns **no structure**: the tab it ran on is the crystal the
  landscape is *of*, and the points are files to open.

## Working in `mainwindow.py`

It is ~1100 lines, and ~900 more are in three mixins `MainWindow`
inherits, split out by a pure move in 2026-09: `xtalapp/shell_state.py`
(`ShellRefresh` -- the refresh paths and every enabling decision),
`xtalapp/symmetry_actions.py` (the Symmetry and Cell commands) and
`xtalapp/edit_actions.py` (editing, selection, bonds, measurements).
A mixin's methods read the window through ``self`` like any other; put
a new command beside its siblings, wherever they are, and outline with
`code-map` rather than reading a file whole. A test that patches a
module-level name (``rdkit_installed``, a dialog class) patches it in
the module whose method looks it up. Prefer a targeted `Edit` over
rewriting the file.

Refreshing is deliberately split three ways and the distinction
matters for responsiveness: `_update_ui` rebinds panels when the
current document changes; `_on_structure_changed` refreshes what they
show; `_on_view_changed` touches only the shell's own widgets.
Rebuilding a site table because a spinbox moved is how a large
structure loses interactivity.

## Skills

`.claude/skills/` holds the workflows that are worth not re-deriving:

- **code-map**: outline a file (line, signature, first docstring
  sentence) or `--find` a definition, instead of reading the file.
  `python .claude/skills/code-map/outline.py xtalapp/document.py`.
  Use it before opening anything large.
- **plan-feature**: the shape a plan takes here: measure first, name
  the invariants, phases with files and test names, a run-app check,
  the docs to update. Planning only.
- **add-action**: a menu, toolbar or context-menu command, from
  `build_actions` to `Document` verb, enabling rules and tests.
- **add-module**: a calculation: a `MODULES` entry (runs and leaves a
  folder) or an `ENGINES` entry (energy and forces), with binaries,
  extras, dialogs, packaging and tests.
- **run-app**: launch the real window and drive it.
  `python .claude/skills/run-app/drive.py --scratch DIR --open FILE
  --action NAME --viewport-shot OUT.png`. The suite stubs the viewport
  and cannot press a button; this can. `--grab` screenshots one dock
  or dialog, `--list-actions` / `--list-docks` name things, and
  `--scratch` keeps your real preferences and workspaces out of it.
- **pure-move**: moving code between modules without changing
  behaviour. One seam per commit, green suite between steps.
- **ui-text**: every user-visible string out to a CSV for the user to
  reword, and applied back re-wrapped, with the tests that quote the
  old wording listed.
- **manual-writing**: the user manual in `docs/manual` (Sphinx +
  MyST): generated reference pages, scripted screenshots, one chapter
  per session.

## Planning documents

`docs/PLAN.md` is the phase roadmap, `docs/ROADMAP.md` the delivery
order, `docs/TODO.md` everything raised while using the app that is
not yet scheduled. An entry is **deleted when it ships, not ticked**.
Keep them current — they are how work survives between sessions.
