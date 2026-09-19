# Crystal Builder — deep review, 2026-09-18

**Subject:** `JulesOpp/Crystal-Builder` at `3cd15e2` (v0.2.1, main, 2026-09-17).
**Method:** eight focused reviews, each by a separate agent with its own
brief, each producing a report under `reports/` with reproductions under
`probes/` and screenshots under `shots/`. Nothing tracked was modified; the
suite was run in full twice (3008 passed, 8 skipped, 0 failed, both times).
This file is the synthesis; every claim below links to the report that
carries the evidence.

| Report | Lines | What it answers |
|---|--:|---|
| [invariants-tests](reports/invariants-tests.md) | 417 | Do the ~33 product invariants in CLAUDE.md have functional tests? |
| [coverage](reports/coverage.md) | 626 | What does the suite cover, what can it not reach, what does CI run? |
| [factoring](reports/factoring.md) | 792 | Are the workflows and code paths well factored? |
| [edge-cases](reports/edge-cases.md) | 668 | What inputs does the headless core and CLI mishandle? |
| [threads](reports/threads.md) | 926 | The worker-thread deadlock, cancellation, process lifecycle |
| [ui-ux](reports/ui-ux.md) | 609 | Does the interface meet day-one expectations? (23 screenshots) |
| [performance](reports/performance.md) | — | CPU, memory, startup, responsiveness, why this machine is contended |
| [research](reports/research.md) | — | The field: competitors, MOF tooling, standards, expectations, distribution |

---

## 1. The verdict in five lines

1. **This is an unusually well-built and well-tested one-person codebase.** 94% line / 86% branch coverage of the core, 26 of 33 product invariants pinned by *functional* tests that were proven to fail when the regression is reintroduced, a headless wall that holds across all 116 core modules, `ruff` clean, and design decisions written down with the bug that motivated each.
2. **The one documented-but-unfixed bug is worse than documented.** The worker deadlock reproduces, was sampled live, and in a stress harness the shipped `workers.py` fails 31 runs in 45 — mostly segfaults, not hangs. The author's diagnosis is right in mechanism and wrong in two details that decide the fix; a 110-line prototype goes 50/50 clean.
3. **The silent-wrong-answer class the author most cares about has three live members.** Two of nine shipped samples expand with atoms at 0 Å and nothing says "press Merge Duplicates"; `asymmetrize` hands MFU-4l back as Pmmm/87 sites instead of Fm-3m/10 with `ok=True`; and a label containing a space or `#` corrupts the saved file.
4. **The UI's content is better than its shell.** Live previews, units everywhere, honest progress, macOS conventions stated not guessed — but the 3-D view gets 352 px of a 1249 px first-run window, the empty window offers no next step, greyed modules give no reason, and there is no autosave.
5. **The recurring structural fault is one decision written twice**, and every such pair has drifted: action enablement, the run-folder lifecycle (×4), workspace filing in the GUI vs the CLI, bond perception re-implemented in the MOF preview with a different radius.

---

## 2. Scorecard by NFR

| NFR | Grade | One line |
|---|:-:|---|
| Test coverage of invariants | **A−** | 26/33 pinned functionally; the five gaps are real (settings guard, metric-normalised strain, PySide6 cap + `--selftest`, unsaved-on-switch, ZEO_RADII skip) |
| Test coverage, measured | **A−** | xtal/ 94.4/86.1, xtalapp/ 89.6/74.5; unreachable-by-design areas documented; CI misses `sketch`/`pxrd` extras (~65 tests always skip) and `--selftest` never runs on a PR |
| Factoring / architecture | **B+** | Seams are right and verified; duplication-with-drift in five places; `mainwindow.py` has an 821-line costed split available |
| Edge cases (core + CLI) | **B−** | Round-trips, process runner, encodings and UFF warnings are solid; two criticals (segfault on `--symprec -1`, label quoting) and a silent-wrong-answer class |
| Reliability (threads, cancel, exit) | **C** | The deadlock is a use-after-free with a lock inversion on top; FF thread parentless and never stopped on close; no reaper; Stop dead on UFF/MACE scans |
| UI/UX | **B** | Content A−, shell C+; ten sized improvements outside the roadmap |
| Performance | *pending* | |
| Packaging / CI | **B** | Three-platform matrix, honest selftest — gated post-merge only |

---

## 3. The findings that matter most, across all reports

Ranked by (damage × likelihood a user meets it). Each links to its evidence.

### 3.1 `[critical]` The worker teardown is a use-after-free, and the fix is known
[threads §2, §5, §6](reports/threads.md). Both workers are constructed
`parent=None` and both panels drop their only reference inside the finished
slot; the `QThread` at `ff_panel.py:726` is parentless too. The sampled
deadlock is `~QObject → disconnectNotify → PyGILState_Ensure` on the worker
thread against a main thread holding the GIL in `disconnectSlot`; the commoner
failure is `QThread: Destroyed while thread is still running → abort`. The
wrapper freed is the **worker's**, on `thread.started → worker.run`, so no
finished-slot change can defend it. PYSIDE-2367 fixed explicit
connect/disconnect in 6.6; destructors are not covered by any release.
**Fix:** `review/probes/workers_fixed.py` — worker owned from Python on the GUI
thread before `start()`, nothing deleted by Qt, drop one event-loop turn after
stop. Plus `start_in_thread(self.worker, self)` at `ff_panel.py:726` and
`ff_panel.stop(); workers.stop_all()` in `closeEvent`. Verify with
`review/probes/matrix.sh` (31/45 → 0/50) then ten full suite runs.

### 3.2 `[critical]` A label with a space or `#` corrupts the saved file
[edge-cases §2](reports/edge-cases.md). `cif_writer._quote` exists and is not
applied to `_atom_site_label` / `_atom_site_type_symbol`
(`cif_writer.py:136`). A space makes the CIF *and* `.xtalproj` unreadable; a
leading `#` comments the row out and the atom vanishes with rc 0. Reachable
from the Inspector's unvalidated `QLineEdit` and from a legal foreign CIF.

### 3.3 `[critical]` `xtal symmetry --symprec -1` segfaults
[edge-cases §1](reports/edge-cases.md). spglib is handed the value raw; the
only guard lives in the Qt dialog (`find_symmetry.py:156`), i.e. the headless
core — the half meant to run without Qt — is the unguarded door.

### 3.4 `[important]` Two shipped samples are wrong and nothing says so
[edge-cases §3](reports/edge-cases.md). `CFA1.cif` and `Ni2Cl2BTDD.cif`
expand with 18 and 360 coincident pairs. Every symmetry entry point then
raises "too close distance"; perception gives 6786 bonds and coordination 28;
UFF returns 6.28×10⁶ kcal/mol and — because `neighbors.py:156` drops pairs
under 1 µÅ — the optimiser reports `converged=True, |F|max = 0`. Merge
Duplicates fixes it in one click (1152 → 378 atoms). `Ni2Cl2BTDD` is the
structure CLAUDE.md's scan numbers are quoted for. **Fix:** run
`duplicate_groups` on open and put the answer in `meta["warnings"]`, the
channel space-group disagreements already use.

### 3.5 `[important]` `asymmetrize` silently returns a subgroup
[edge-cases §5](reports/edge-cases.md). Reduce to P1 → Find Symmetry on
MFU-4l gives Pmmm (#47) with 87 sites, `ok=True`, same atom count. 0.01 Å
recovers Fm-3m. **Fix:** when the group found is a proper subgroup of the
one the file said, warn and name the symprec that recovers it.

### 3.6 `[important]` The settings scratch guard has no test — and a history of failing silently
[invariants §Finding 1](reports/invariants-tests.md). `conftest.py:62`'s own
docstring records it doing nothing for its entire life (278, then 374 plists
in `~/Library/Preferences`). No test asserts `XTAL_SETTINGS_DIR` / the INI
backend is in force.

### 3.7 `[important]` The metric normalisation of `CellFreedom` is untested
[invariants §Finding 2](reports/invariants-tests.md). With the √2 shear
scaling removed, all 51 tests pass — every fixture is quartz or halite, whose
allowed strains have no independent shear. Needs a monoclinic case.

### 3.8 `[important]` Stop is dead on a UFF/MACE scan; two modules never poll cancel
[threads §7](reports/threads.md). `optimize.steps` accepts `cancel=` and
never checks it; `scan.py:541` should pass a `callback=` as
`OptimizationWorker.run` does. `build.py` and `net.py` never poll at all.
No `atexit`/`aboutToQuit` reaper exists, so an abrupt exit orphans every
external child (`start_new_session=True` guarantees it).

### 3.9 `[important]` One decision written twice, five times over
[factoring §1–4, §6](reports/factoring.md). Action enablement in
`_refresh_shell` (`mainwindow.py:1535`) and `_on_selection_changed` (`:1273`)
— 7 of 12 shared actions disagree; Duplicate becomes enabled during playback
and raises. The run-folder lifecycle exists four times. Workspace filing lives
in `module_runner.py` so `xtal run mof.build --workspace` files differently
from the window. `mof_preview._draw_bonds` perceives with `r_i+r_j+0.45`
against the core's `(r_i+r_j)*1.15` — draws C–C 0.23 Å longer and Zn–Zn
bonds the core refuses. The three external-binary engines filter options
three different ways.

### 3.10 `[important]` The UI shell on day one
[ui-ux §1–6](reports/ui-ux.md). 3-D view 352 px wide at 1249 (133 px at
1024×700) from `info 380 + file 380 + sites 515` with nothing setting
initial proportions; empty central area with no affordance although
drag-drop works and seven samples ship; `Availability.reason` — an excellent
sentence naming what was searched and how to install — shown only for 6 s in
the status bar; Save File converts CIF → `.xtalproj` unannounced; no autosave;
`closeEvent` calls `stop_module()` *before* the unsaved question, so Cancel
does not bring an overnight run back; Find symmetry's default button is Close.

### 3.11 `[important]` CI gaps
[coverage §5](reports/coverage.md). `--selftest` — the only thing that
exercises the real VTK context and the bundled PORMAKE database — runs only
on push to `main`, never on a PR. The `test` job omits `sketch`/`pxrd`, so
62 PXRD tests and the rdeditor tests skip on every run, on every OS.
`WorkspaceChooser.ask()` and `main()` have no coverage of any kind.

### 3.12 `[important]` Smaller silent-wrong-answer cases
[edge-cases §6–13](reports/edge-cases.md). UTF-8 BOM defeats four of five
readers with four different messages (`utf-8` vs `utf-8-sig`); a multi-block
CIF reads block one in silence and `FORMATS.read_all` has no caller; a
typo'd `-p name=value` is dropped and the run succeeds; `xtal convert a.cif
a.cif` rewrites the input; `workspace.json` that is valid JSON but not an
object raises against its docstring; `session.open` with an absolute path
escapes the workspace; `Entry.next_run` is TOCTOU (5 of 6 concurrent runs
raise); the reader accepts a bond operation the writer refuses.

---

## 4. What is genuinely good — say this to Jules first

Specific, verified, and in several cases worth copying:

- **The tolerance invariants defend themselves.** Put `SPECIAL_POSITION_TOL`
  back to 1e-3: exactly six tests fail, all functional, on the deposited
  `Ni2Cl2BTDD.cif`, one asserting the published formula. Take the site
  projectors to 1e-6: exactly two fail, one with the application's own
  message *"the cell went from 648 atoms to 712"*. ([invariants](reports/invariants-tests.md))
- **`test_setting_every_bond_is_one_command_and_one_change`** pins a
  performance invariant as a *mechanism* assertion (one signal, one revision,
  one undo step) on the real structure that stalled — nothing flaky, nothing
  to tune. Best test in the repo.
- **The degraded-window sweep**: nine `workspace is None` tests across seven
  files, one per branch.
- **`test_no_panel_insists_on_more_room_than_a_column_can_spare`** sweeps
  every dock, so a new panel is caught without anyone remembering to add a test.
- **The headless wall holds in fact**: 116 modules imported, zero Qt/VTK/
  matplotlib in `sys.modules`. ([factoring §strengths](reports/factoring.md))
- **The three-way refresh split is honoured everywhere** and the costs are
  proportionate: 0.68 / 0.90 / 2.39 ms on MFU-4l.
- **`Engine.__call__` is a model seam** — one decision (hold markers back),
  made once, with a docstring saying why no engine may be trusted to do it.
- **The scan, the newest large feature, extended the machinery rather than
  forking it** — plugs into `optimize.run` as a `Holonomic` applied after
  the symmetry projectors, and is an ordinary `MODULES` entry.
- **`Action.shell` records an asymmetry instead of hiding it** — the best
  docstring in the repository.
- **The external process runner handled everything thrown at it**: missing
  binary, non-zero exit, stderr-only, mid-run cancel, a child ignoring
  SIGTERM, folders with spaces/accents/quotes/newlines. ([edge-cases §15](reports/edge-cases.md))
- **A cancelled scan is handled properly** and leaves a reopenable
  `report.json`. ([threads §9](reports/threads.md))
- **CIF and `.xtalproj` round-trip all 13 structures to `maxfrac = 0.0`**;
  the foreign `_geom_bond` rule holds exactly as documented; all 61 text
  call sites in `xtal/` name an encoding.
- **Live preview before committing** in Supercell, Set space group, Merge
  duplicates, Bond rules, Display range; the scan dialog costs the job
  ("14 points, up to about 19 minutes") before you press Run. Very few
  programs in this field tell you the answer before OK. ([ui-ux §15](reports/ui-ux.md))
- **Energy units are consistent across four engines** — converted at the
  boundary so the interface only ever says kcal/mol.
- **Selection is richer than VESTA's**: by element, grow to bonded /
  fragment / orbit, invert over orbits, box select, hover tooltip.
- **The comments made this review possible.** Duplication was findable
  because the comment was copied too.

---

## 5. Recommended order of work

Sized on ROADMAP's scale (S ≤ a day, M a few days, L a week+).

| # | Work | Size | Risk | Why first |
|---|---|:-:|:-:|---|
| 1 | Apply `workers_fixed.py`; parent the FF thread; stop+wait in `closeEvent`; add `aboutToQuit`/`atexit` reaper | S | low-med | Segfaults in the shipped app; gates `-n auto` and every overnight scan |
| 2 | Quote CIF labels; guard `symprec <= 0` in the core | S | low | Two criticals, two-line fixes each |
| 3 | Coincident-atom warning on open + subgroup warning in `asymmetrize` | S | low | Two of nine shipped samples are wrong today |
| 4 | Stop on a UFF/MACE scan (`callback=` into `optimize.run`); poll cancel in `build.py`/`net.py` | S | low | The one Stop bug a user will actually meet |
| 5 | Tests: settings-guard self-check; monoclinic `CellFreedom`; unsaved-on-switch; `selftest.run`; the eight in [coverage](reports/coverage.md#tests-worth-writing) | S–M | low | Closes the five invariant gaps |
| 6 | CI: run `--selftest` on PRs; add `sketch,pxrd` to the test extras | S | low | ~65 tests currently never run anywhere but a dev laptop |
| 7 | `ShellState` — one owner for action enablement (345 lines out of `mainwindow.py`) | S | low | First and safest slice of the split; removes the highest-traffic duplicated decision |
| 8 | First-run layout proportions; start pane in the empty window; reason on greyed modules; Save-converts notice | S each | low | Day-one impression, four small changes |
| 9 | Chemistry back behind the wall (`mof_preview`), `coerce()` in `Engine.__call__` | S–M | low | The only layering violation, and three drifted option filters |
| 10 | One run lifecycle + workspace filing into `xtal/` | M | med | CLI and window file builds identically; ten filing tests lose their `QMainWindow` |
| 11 | Autosave + crash recovery; "a run is going — stop and quit?" | M | med | The single biggest trust feature missing |
| 12 | BOM / multi-block / `-p` typo / convert-in-place / `next_run` TOCTOU | S each | low | The rest of the silent class |

---

## 6. Performance

Full report: [performance.md](reports/performance.md) (800 lines, probes in
`probes/perf/`).

**First, a correction to my own framing.** This machine is **8 GB, not 16**
(`hw.memsize`), with 1.67 GB wired and the compressor holding 19.9 GB of data
in 3.20 GB of pages — **4.87 GB gone before any application gets a page**, and
279 GB of lifetime swapins. That, not the application, is the 819 s vs 332 s
suite swing. The app is well-behaved; the machine is the contended resource.

**The application's own cost is three accidentally-quadratic paths:**

1. `[critical]` **`Structure.add_bond` is O(n²)** — `structure.py:538-541`
   calls `reverse` (`:140`) with a numpy matmul inside the comparison.
   Synthetic: 200 bonds 115 ms → 3200 bonds **29.8 s**. Real consequence:
   **opening a 21 KB MFU-4l `.xtalproj` takes 2.10 s**, with `cProfile`
   showing 360,824 `reverse` calls (= 848²/2). Six loop callers: Reduce to
   P1, project load, MOF build, SMILES, paste, connections. A `set` of bond
   identities fixes it.
2. `[important]` **`SpaceGroup._build_inverses`: 177 ms per fresh Fm-3m
   object**, O(192²) `np.allclose`, and the cache is per-instance so two
   `SpaceGroup(225)` objects each pay it. A third of Set Bond Type's cost.
3. `[important]` **`bonding._find_atom` linear-scans the cell** — 7296 calls
   × 648 atoms to place 19 bonds. Wants the KD-tree this repo already applied
   to `read_cgd`.

**Main-thread freezes with no busy cursor** (exactly **one**
`setOverrideCursor` in all of `xtalapp/`): Set Bond Type over a selection is
**740 ms on MFU-4l and 3207 ms on Ni2Cl2BTDD**; Supercell 2×2×2 is 1182 ms;
Reduce to P1 463 ms. The batching invariant *is* honoured (2 `Render()` calls
per recompute) — the cost is the batch itself, plus `_sync_bond_type_actions`
rebuilding a bond graph twice to tick a menu item.

**Cell relaxation costs 13 energy evaluations per step** (`numeric_stress` —
78 `compute` calls for 5 steps). MFU-4l 0.008 → 0.102 s/step; Ni2Cl2BTDD
0.297 → **3.88 s/step**. CLAUDE.md's "12×12 grid ≈ 2.6 hours" becomes
**23 hours** with the cell free. The code's own comment already names the
analytic virial as the fix — this is the single biggest win available to
anyone running the flexible-framework scans the app was built for.

**Why Ni2Cl2BTDD is expensive is not its atom count** — it is the disordered
solvent this review found unmerged ([§3.4](#34-important-two-shipped-samples-are-wrong-and-nothing-says-so)):
6786 bonds, average degree 11.78, max 28 → **526,176 torsion terms, 75 MB of
arrays, +298 MB for one energy evaluation**. Merging duplicates on open would
fix a correctness bug and a performance cliff at once.

**A theory I had, disproved:** BLAS thread contention inside `QThread` is not
happening here. numpy is on Apple Accelerate, nothing sets `*_NUM_THREADS`,
and a running job measures **0.99× parallelism on 2 OS threads** — one core
busy, seven idle. Ewald is confirmed default-off.

**Strengths, measured:** VTK is imported by name only (no `import vtk`;
`vtkmodules.all` excluded in packaging), rdkit/matplotlib/ase are all
function-level; the scene uses **19 fixed `vtkActor`s via glyph mappers at
both 648 and 5184 atoms**; `compute` is 823 Python calls for 1152 atoms; the
`pytest_runtest_teardown` leak fix holds (RSS oscillates 200–440 MB with no
trend); packaging is the best-documented NFR work in the project.

**The suite is memory-bound, not CPU-bound**: 481 tests in 46.8 s wall vs
35.5 s CPU (24 % off-CPU), peak 497 MB, extrapolating to 272 s — matching
CLAUDE.md's own figure. 36 files build a `MainWindow` 53 times; fewer full
windows is the real lever, ahead of `-n auto`.

**Three optimisations that pay back most** for a user with MFU-4l-sized
frameworks: the `add_bond` set (**S**, low risk — 2.10 s off every project
open); the analytic virial for cell relaxation (**M** — 23 h → hours on an
overnight scan); a busy cursor plus moving Set Bond Type off the main thread
(**S** — the app stops looking hung).

---

## 7. Feature ideas to put to Jules

Curated from [research.md](reports/research.md) (30 ranked ideas, each with
source, roadmap status and size) and cross-checked against what the code
reviews found. Ordered by how well each fits what the app already is:
a headless core, three registries, everything an undoable command. Phrased
as questions, because they are Jules's calls.

### Where the reviews and the field agree

1. **"Should the app check a structure the moment it opens?"** The field's
   loudest problem: 38 % of CoRE2014 and >40 % of 1.9 M structures across 14
   databases have errors (JACS 2025); "over half of top screening candidates"
   are structurally wrong (Israel J. Chem 2026). `mofchecker` does this as a
   library; nothing desktop does it at import. And this review found two of
   Jules's own nine samples expand with atoms at 0 Å with nothing saying so
   ([edge-cases §3](reports/edge-cases.md)). `duplicate_groups` exists;
   `meta["warnings"]` exists; PLAN §12 already sketches a validation panel.
   **M** — and the first step (coincident atoms on open) is **S**.

2. **"Is autosave the next trust feature?"** Named in the research as the
   single most critical showstopper for editing software, absent here
   ([ui-ux §5](reports/ui-ux.md)). A `<workspace>/.autosave/*.xtalproj`
   every N minutes, offered back from the chooser Jules already built. **M**.

3. **"Would you take the worker fix?"** Not a feature, but the reviews' top
   finding and the gate on `-n auto`, overnight scans, and every future
   engine ([threads §6](reports/threads.md)). The prototype is in
   `probes/workers_fixed.py`. **S**.

### Extending a registry (cheap, on-pattern)

4. **More ML potentials as `ENGINES` entries** — CHGNet, M3GNet, ORB-v3,
   SevenNet, UMA (Meta, June 2025), MatterSim. All ASE-calculator-shaped,
   the same seam MACE uses. MOFSimBench (npj 2025) showed none is uniformly
   reliable on MOFs — which is the argument for offering several. **S each**.
5. **MACE-MP-MOF0 as a checkpoint choice** — the MOF fine-tune of
   MACE-MP-0b, 10× more accurate on geometry/forces/stress. **S**.
6. **EQeq / EQeq+C beside QEq** — non-iterative Ewald charge equilibration,
   seconds not days; EQeq+C fixes high-oxidation-state metals. The Ewald sum
   is already there. **S**.
7. **Formats via `FORMATS`**: mmCIF/PDBx (gemmi already reads it — nearly
   free), POSCAR/CONTCAR, pymatgen `Structure` JSON, ASE `.traj`. **S each**.
8. **LAMMPS data export** — `lammps-interface` has "New maintainer wanted!"
   and Zr in UiO-66 gets 0 neighbours; `cif2lammps` was archived April 2024.
   Both reconstruct what Crystal Builder already holds: the bond graph and
   the UFF/UFF4MOF typer. A maintained GUI exporter fills a real hole. **M**.
9. **Framework-class force fields** — Dreiding, MZHB (zeolites), ZIFFF
   (ZIFs) as engines. **M each**.
10. **Zeo++ features the module does not yet expose** — per-channel
    dimensionality, blocking spheres for GCMC, probe-occupiable volume,
    `-ha`. Pockets are already in TODO. **M**.

### A database door

11. **"Would an OPTIMADE search dialog be worth one dependency?"** The
    `optimade` package queries COD, Materials Project, OQMD, AFLOW at once
    and has CIF adapters. Every neighbour (Mercury, Crystal Toolkit, COD)
    has a database door; this app has none. **M**.
12. **CoRE MOF 2025 / QMOF / CSD MOF collection** as import catalogues
    beside PORMAKE's 867 blocks. **M**.
13. **MOFid/MOFkey** for naming and deduplicating built frameworks. **S**.

### The MOF builder, where the field has gaps nobody fills

14. **Interpenetration** — no maintained open-source tool exists anywhere;
    the only method is a 2016 collision check. Genuine, field-wide. **M**.
15. **Missing-linker / missing-node defects** — MOFBuilder (npj 2026) and
    MOFun do it as libraries; UiO-66 is the testbed. **M**.
16. **Multi-linker and combinatorial generation** — PORMAKE's own open
    issues #32/#33; the vendored copy could go past upstream. **M**.
17. **Post-synthetic functionalisation** — PSYMOF (npj 2025): pick a site,
    grow a group, retype, re-relax. "Mark connection points" + Add hydrogens
    is adjacent machinery. **L**.
18. **GCMC input generation for RASPA3** — the research found no GUI does
    it and three hand-glue scripts (simple-adsorption-workflow, MatKit,
    CoRE-MOF-Tools) exist because of that. **L**.

### Output and reach

19. **Publication renders** — ray-traced / ambient-occlusion export (OVITO
    Pro, Avogadro 2, Diamond all have one). **M**.
20. **Web-shareable 3D** — glTF (ChimeraX does it at ~100 k triangles) or a
    3Dmol.js standalone HTML, extending the existing Blender/STL path. **M**.
21. **Vector export of the 3-D view** (VTK's gl2ps) to match what PXRD and
    bands already do through matplotlib. **S–M**.
22. **Energy units as a preference** — kcal/mol · kJ/mol · eV; the
    conversion layer already exists at the engine boundary
    ([ui-ux §7](reports/ui-ux.md)). **M**.
23. **Code signing and notarisation** — $99/yr, a few hours once, ten
    minutes per release in CI after that; 3D Slicer documents the process.
    Removes the right-click→Open dance the README apologises for. **S**.
24. **conda-forge feedstock, `CITATION.cff` + Zenodo DOI, a JOSS paper** —
    the suite, CI and CLAUDE.md would review well; pymatgen-analysis-defects
    (JOSS 2024) is a template. **S–M**.

### Already on Jules's own lists — worth asking "when?"

Scan `--resume` and sweep-from-the-crystal (TODO § Scans); dark mode
(TODO line 1); disorder / split sites, slab builder, embedded console
(PLAN §12); Rietveld and volumetric isosurfaces (PLAN §12 "Later" — the
marching-tetrahedra code already exists); quasi-harmonic F(V,T) (PLAN §12a).

### Three questions that are not features

- **"Which of the invariants in CLAUDE.md would you want a test to defend
  before the next refactor?"** — the review found five without one
  ([invariants](reports/invariants-tests.md)); the settings guard has
  already failed silently twice.
- **"Is the CLI meant to file a build the way the window does?"** — today
  it does not, because the policy lives in `module_runner.py`
  ([factoring §3](reports/factoring.md)).
- **"Do you want `--selftest` on pull requests?"** — it is the only thing
  that exercises the real VTK context, and it runs after merge only
  ([coverage §5](reports/coverage.md)).
