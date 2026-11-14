# Test coverage and suite characterisation

> **Written 2026-09-18** against `Crystal-Builder` at commit `3cd15e2` (v0.2.1), the base of branch `features/deep-review`. `origin/main` has since moved to `fb38d25`. Line numbers, measurements and code references below were true at `3cd15e2` — re-verify before acting on one if the file has changed since.


**Summary.** The suite is large (2,794 test functions in source, ~3,016
collected after parametrisation), well-organised around four shared
fixtures and three autouse guards, and lands at 89% combined statement
coverage / ~80% combined branch coverage across `xtal/` + `xtalapp/`
(94.4%/86.1% for `xtal/` alone, 89.6%/74.5% for `xtalapp/`; the vendored
`xtal/mof/pormake/` sits at 67.6%/59.5% and should be judged separately
— it is exercised only through what the MOF builder actually calls, by
design). The real gaps cluster exactly where CLAUDE.md and the test
files themselves say they would: `xtalapp/main.py`'s entry-point
wiring (35%), `xtalapp/selftest.py` (15%, unreachable by pytest at
all), the one dialog the suite is built to never open
(`WorkspaceChooser.ask`), and the real VTK widget class (42%) that a
stub replaces everywhere else. One of the brief's supplied facts does
not hold for the run performed here: only 3 of the 14 warnings are the
zipfile duplicate-name ones; the other 11 are an unrelated scipy
rotation warning from the MOF builder. `.coverage` did land in the
repo root and has been moved into `review/probes/`; `git status` is
clean.

---

## Run record

- Command: the exact one in the brief, `-o faulthandler_timeout=120`,
  `--cov=xtal --cov=xtalapp --cov-branch`, three report formats, run
  serially in the background with output to
  `review/probes/coverage-run.log`.
- `sysctl vm.swapusage` before the run: `total = 10240.00M used =
  9346.06M free = 893.94M` (91.3% used). After: `total = 15360.00M
  used = 14642.25M free = 717.75M` (95.3% used) — macOS grew the swap
  file during the run rather than the run stalling on it.
- Result: **3008 passed, 8 skipped, 14 warnings in 332.42s (0:05:32)**.
  No `Fatal Python error`, no wedge, no faulthandler dump — a clean
  run, and considerably faster than the plain serial run the brief
  reports (819s) despite `--cov`'s instrumentation overhead, which is
  consistent with CLAUDE.md's own note that the spread is memory
  pressure, not the code.
- `review/coverage.json` (3.4 MB), `review/coverage-html/index.html`,
  and this log are all in place. `.coverage` was written to the repo
  root by the run (predictable — coverage.py always writes its data
  file to the current directory) and has been moved to
  `review/probes/.coverage`; `git status` now reports a clean tree.

### Correction to a supplied fact: the 14 warnings are not all zipfile

The brief states "14 warnings, all `zipfile UserWarning: Duplicate
name`". In the run actually performed, the warnings summary
(`review/probes/coverage-run.log:43-59`) is:

```
tests/test_block_writer.py: 1 warning
tests/test_mof_builder.py: 7 warnings
tests/test_mof_vendored.py: 3 warnings
  .../scipy/spatial/transform/_rotation.py:2576: UserWarning: Optimal
  rotation is not uniquely or poorly defined for the given sets of vectors.

tests/test_project.py::test_a_project_from_a_later_version_still_gives_up_its_crystal
  .../zipfile/__init__.py:1625: UserWarning: Duplicate name: 'view.json'

tests/test_project.py::test_a_bond_that_no_longer_fits_is_dropped_not_fatal
tests/test_stored_bonds.py::test_an_unreadable_stored_graph_is_a_warning_not_a_lost_crystal
  .../zipfile/__init__.py:1625: UserWarning: Duplicate name: 'bonds.json'
```

That is 1+7+3 = 11 scipy warnings and 1+2 = 3 zipfile warnings = 14.
The scipy one (`Rotation.align_vectors` finding a non-unique optimal
rotation) comes from vendored PORMAKE's `xtal/mof/pormake/locator.py:87`,
raised while orienting a building block with a symmetric set of
connection points. It is not caught by `filterwarnings =
["error::DeprecationWarning"]` (it's a `UserWarning`) so it does not
fail the suite, but it fires on most MOF-builder test runs and nobody
has looked at why the alignment is non-unique for that block — see
finding 6 below.

### The zipfile "duplicate name" warning is a test technique, not a writer bug

`[investigated — not the writer's fault]` **What**: the brief asks
whether the `.xtalproj` writer adds the same zip member twice and, if
so, whether a reader could get either copy. **Where**:
`xtal/io/project.py:86-104` (`write_project`) writes `STRUCTURE_PART`,
`CELL_PART`, `BONDS_PART`, `SITES_PART`, `VIEW_PART`, `SESSION_PART`
each exactly once, inside one `zipfile.ZipFile(path, "w", ...)`
context. There is no duplicate write anywhere in the writer.
**Evidence**: the only places `"view.json"` or `"bonds.json"` are
written a second time are the tests themselves —
`tests/test_project.py:135-137` (`write_project(...)` then
`zipfile.ZipFile(path, "a")` + `archive.writestr("view.json", "{ not
json at all")`), `tests/test_project.py:145-149` (same for
`bonds.json`), and `tests/test_stored_bonds.py:253-257` — all three
deliberately reopen an already-written project in **append** mode and
write a second copy of an existing member, to simulate a corrupted or
future-version part and assert `read_project` degrades gracefully
(`back.n_sites == rutile.n_sites`, `view == {}`, "unreadable bond" in
warnings, etc.). Python's `zipfile` module keeps both physical copies
in the archive but its `NameToInfo` index is a dict keyed by name, so
each `writestr` under the same name overwrites the index entry — which
is why `ZipFile.read()`/`.open()` deterministically returns the
**last-written** copy. That determinism is exactly what the three
tests rely on and assert against. **Why it matters**: it answers the
brief's question — no, a reader cannot get "either copy"; it reliably
gets the newer one, and this is test-only behaviour that will never
occur in a project written by the real application. **What a fix
would look like**: nothing to fix in the writer; if the warning noise
bothers a future maintainer, the three tests could open the archive
with `warnings.catch_warnings()` around the append, but that is
cosmetic.

---

## 1. Suite shape

- **137 test files**, 44,375 raw lines, **2,794 test functions**
  (`ast`-counted; `pytest`'s collected total is 3,016 = 3,008 passed +
  8 skipped, the ~222 gap being parametrised-test expansion).
- **64 parametrised functions**, **28 `@pytest.mark.slow`** tests.
- **Widget-touching tests**: 523 of 2,794 (18.7%) take a `qtbot` or
  `window` fixture argument directly (288 take `qtbot`, 332 take
  `window`, with overlap). No test file constructs a `QApplication`
  itself anywhere (`grep -rln "QApplication(" tests/*.py` — 0 hits),
  so nothing bypasses the shared `qapp_cls` fixture.
- **Real-structure fixtures**: 634 tests take `rutile`, `quartz`,
  `halite`, or `dry_ice` directly. 128 tests build their own
  `Structure(...)` inline instead (concentrated in
  `test_structure.py`, `test_occupancy_pies.py`, `test_topology.py`,
  `test_vtk_render.py`, `test_scene_builder.py`, `test_symmetry.py` —
  files that need a shape none of the four fixtures has). Most of the
  remainder go through format-specific helpers (`conftest_ff.py`'s
  `water`/`ethane`/`benzene`/... factories, or a CIF string parsed
  in-test) rather than either of the above two categories.
- **Largest files by test count**: `test_scene_builder.py` (70),
  `test_symmetry_ui.py` (65), `test_app_shell.py` (51),
  `test_add_atom.py` (48), `test_scan_module.py` (46),
  `test_workspace_ui.py` (46), `test_appearance_ui.py` (45),
  `test_build_ui.py` (43), `test_zeopp.py` (43).
- **Naming convention**: `[minor]` 42 of 2,794 test names (1.5%) do
  not read as behaviour sentences under a length/pattern heuristic
  (≤2 words after `test_`, or matching `basic|simple|\d+|misc|works`)
  — e.g. `test_element_record`, `test_cubic_volume`,
  `test_basic_editing`, `test_bond_gradient`, `test_wyckoff_assignment`
  (full list in the probe script's output, 42 lines). Small and
  concentrated in the oldest headless core tests
  (`test_structure.py`, `test_symmetry.py`, `test_selection.py`); the
  overwhelming majority of the suite does follow the convention.
- **Docstrings**: `[informational]` every one of the 137 files has a
  *module*-level docstring (0 missing). At the *function* level, 1,250
  of 2,794 tests (44.7%) have no docstring of their own, and 10 files
  have none on any test (`test_structure.py`, `test_site.py`,
  `test_elements.py`, `test_properties.py`, `test_core_is_headless.py`,
  `test_dftb_bands.py`, `test_dftb_electronic.py`,
  `test_dftb_modes.py`, `test_kpath.py`,
  `test_module_trajectory_ui.py`). Reading a sample
  (`tests/test_structure.py:20-99`) suggests this is by design rather
  than an oversight: CLAUDE.md's convention pairs "sentences
  describing the behaviour" and "docstrings say what breaks" in one
  breath, and files like `test_structure.py` use only the sentence —
  `test_remove_sites_renumbers_surviving_bonds`,
  `test_every_mutation_bumps_the_revision_with_a_hint` — with a
  docstring added only where the name alone would not carry the
  context (e.g. `test_a_project_survives_a_structure_it_cannot_simplify`
  in `tests/test_project.py:156` adds "A 192-operation group with a
  bond on a high-index operation is the case where an index-based bond
  is most likely to be mangled."). Reported as asked; not read as a
  gap against the letter of the convention.
- **Import-based module popularity** (how many test files import from
  each top-level package, not exclusive ownership — a rough proxy for
  "what the suite spends itself on"): `xtal.core` (in 2,017 tests'
  files by aggregate), `xtal.io` (1,336), `xtalapp.mainwindow` (884),
  `xtal.modules` (773), `xtal.ff` (716), `xtalapp.document` (701),
  `xtalapp.dialogs` (665), `xtalapp.viewport` (604).

## 2. Fixture architecture and the guards

`tests/conftest.py` (400 lines) does five things at **import time**,
before any fixture runs, because a fixture is too late for
module-level state Qt/QSettings/the workspace root need to see first:
points `XTAL_NO_CONFIRM_CLOSE`, `XTAL_LOG_DIR`, `XTAL_PACKAGES_DIR`,
`XTAL_WORKSPACE_ROOT` at scratch directories (`conftest.py:29-58`),
redirects `QSettings`'s INI backend off macOS's real CFPreferences
(`_settings_into_a_scratch_directory`, `:62-109` — this is the fix for
the 278-plist incident CLAUDE.md describes), and keeps a test window's
menu bar off the real macOS menu bar
(`_menus_out_of_the_system_menu_bar`, `:112-142`).

On top of that sit exactly **three** `@pytest.fixture(autouse=True)`
fixtures (`grep -n "autouse=True" tests/conftest*.py` — three hits,
all in `conftest.py`, none in `conftest_ff.py` / `conftest_zeo.py` /
`conftest_program.py`, which define no fixtures at all — see below):

1. `_no_blocking_modal` (`:240-278`) — patches `QDialog.exec` and the
   five `QMessageBox` static helpers to raise `AssertionError` instead
   of blocking.
2. `_a_default_workspace_of_this_test_own` (`:281-298`) — points
   `XTAL_WORKSPACE_ROOT` at `tmp_path` per test, on top of the
   session-wide default.
3. `_no_leftover_tool_hints` (`:301-315`) — clears
   `xtal.modules.process`'s module-level DFTB+/Zeo++ path hints before
   and after every test.

Plus a `pytest_runtest_teardown` hook (`:195-222`, not a fixture, runs
for every test unconditionally) that pumps `QEvent.DeferredDelete`
after pytest-qt's own teardown — the fix for the 74-live-`MainWindow`
leak CLAUDE.md describes. **CLAUDE.md calls "XTAL_NO_CONFIRM_CLOSE"
and the dialog patch "two autouse guards"**, and the brief refers to
"four autouse guards"; the literal count in the code is **three
`@pytest.fixture(autouse=True)` fixtures** plus the session-level
`os.environ.setdefault` at the top of the file, which behaves like a
fourth guard but is not implemented as a fixture. All four/five
mechanisms (env-var defaults, dialog patch, workspace isolation, tool
hints, and the teardown hook) do cover every test collected under
`tests/` — `pytest_runtest_teardown` and the three autouse fixtures
apply suite-wide with no opt-out mechanism other than the one
documented one (`monkeypatch.delenv("XTAL_NO_CONFIRM_CLOSE")`, used
by `test_closing_a_modified_document_asks_first`), and no test module
was found constructing its own `QApplication` or otherwise routing
around them.

`conftest_ff.py`, `conftest_zeo.py`, `conftest_program.py` are
deliberately **not** fixture modules (their own docstrings say so):
they export plain helper functions (`water`, `ethane`, `benzene`,
`salt`, ... ; `write_fake_network`; `write_program`) imported directly
by the handful of test files that want them, because a fixture defined
in one and imported into another is a name collision waiting to
happen under pytest's fixture resolution, not a share.
`conftest_program.py`'s `write_program` is the one piece of real
cross-platform plumbing in the stand-in machinery: on POSIX it writes
a `#!{sys.executable}` script and chmods it executable; on Windows it
writes a `.py` beside a `.bat` launcher, because `CreateProcess` refuses
to run a shebang script directly.

**33 test files define their own local `window` fixture** (`grep -rl
"^def window(" tests/*.py` — 33 hits) rather than sharing one from
`conftest.py`, exactly as CLAUDE.md instructs ("Copy the `window`
fixture from `tests/test_open_once.py`"). These are not blind copies:
each customises its `AppSettings` domain (`f"Edit{tmp_path.name}"`,
`f"Once{tmp_path.name}"`, ...) and often its `viewport_factory` stub
class (`_Stub`, `BuildViewport`, `StubViewport`, ...) for what that
file is testing. All of them still go through the session-level
`_settings_into_a_scratch_directory` guard, so none of the 33 escapes
isolation — this was checked, not assumed.

## 3. What the suite cannot reach by design

| Area | Stubbed/faked how | What exercises it today |
|---|---|---|
| VTK viewport widget (`xtalapp/viewport/widget.py`, the `QVTKRenderWindowInteractor` host) | `MainWindow(viewport_factory=Stub)` in every ordinary widget test | `--selftest`'s `check_window` (real window, real VTK, writes a PNG) — **only in CI's `build` job**, and only on push-to-`main` or a release tag, never on a PR; plus 4 test files gated by `needs_offscreen_gl` (`test_box_select.py`, `test_draw_styles.py`, `test_picking.py`, `test_vtk_render.py`) that probe a real (non-offscreen, per CLAUDE.md's rule against `QT_QPA_PLATFORM=offscreen` locally) GL context in a subprocess |
| `xtalapp/viewport/vtk_scene.py` (2,181 raw lines) | same stub | Coverage is 84% anyway, because the 4 real-GL files above call into it directly; but this is a machine with a real display — on CI (offscreen) these 4 files self-skip, so **CI's own coverage of `vtk_scene.py` is far lower than this run's** |
| Real subprocess engines (DFTB+, xTB, Zeo++) | `write_program` (`conftest_program.py`) writes a tiny stand-in binary/script per test that records argv and writes canned output; `conftest_zeo.py`'s `write_fake_network` is a full stand-in for the 9 MB `network` binary, keyed to captured real output | Every `test_dftb*.py`, `test_xtb.py`, `test_zeopp.py`, `test_probe.py` test; never the real binaries |
| MACE (in-process, not a subprocess) | `tests/test_mace.py` replaces `_load_model` with a cheap ASE calculator for all arithmetic tests; the 2 tests that need the real model run it `in_a_fresh_interpreter` via `subprocess.run([sys.executable, "-c", program])` | Neither this machine's dev venv nor CI installs `mace` (deliberately excluded from `[dev]` — "a contributor running the suite should not be made to download a deep learning framework", `pyproject.toml:99-106`), so **all MACE-specific tests skip everywhere this project is normally run**, including CI |
| Upstream PORMAKE | Never imported into the test process; `tests/data/pormake_upstream.json` is a recording made by `tests/data/record_pormake_upstream.py --check`, run by hand against the real `pormake` package | `tests/test_mof_vendored.py` compares the vendored code's output to the recording; a real re-derivation only happens when a developer reruns the recording script |
| `WorkspaceChooser.ask()` (`xtalapp/dialogs/workspace_chooser.py:421-430`) | Nothing — it is the one dialog CLAUDE.md says the suite must never call, because it's the only place `dialog.exec()` would actually run | **Nothing.** Confirmed by coverage: `ask` shows 50% of its lines missed — precisely the `dialog.exec()` call and the accepted-branch unpacking (the guard branches before it are hit transitively through `choose_workspace`'s own unit tests). No test, no `--selftest` check (which refuses dialogs the same way), and no CI step exercises this method. Only `.claude/skills/run-app/drive.py` (headed, manual) or a human can. |
| `xtalapp/main.py`'s `main()` | Nothing — needs a real `app.exec()` event loop | **Nothing pytest-based.** `choose_workspace` and `open_window`, the two helpers `main()` calls, are unit-tested directly (`tests/test_workspace_chooser.py:269-330`), but `main()` itself — plugin loading, `applog.start()`, the `--selftest`/`--selftest-import` argv branches, and the `if workspace is None: return 0` line — is never called by any test. Coverage: 35% (41 of 65 lines missed, effectively the whole function body past the `os.environ.setdefault` at import time). |
| `xtalapp/selftest.py` | Nothing — it exists to run inside a frozen build | **Nothing in the unit suite** (no `test_selftest.py`, no import of `xtalapp.selftest` from any test file). Coverage: 15% (123 of 152 lines). The only thing that runs it for real is CI's `build` job's "Selftest (macOS)" / "Selftest (Windows)" steps — gated to `push` on `main` or a version tag, so **a regression here is caught only after it has already landed on `main`**, never on a PR. |

## 4. Coverage numbers

Computed from `review/coverage.json` (authoritative; the terminal
table blends line+branch into one "Cover" percentage per file, so
totals below are recomputed separately for line and branch).

| Scope | Statements | Missed | Line % | Branches | Missed | Branch % |
|---|--:|--:|--:|--:|--:|--:|
| `xtal/` (excl. vendored PORMAKE) | 15,969 | 887 | **94.4%** | 4,468 | 622 | **86.1%** |
| `xtal/mof/pormake/` (vendored, judged separately) | 1,539 | 499 | 67.6% | 348 | 141 | 59.5% |
| `xtal/` incl. PORMAKE | 17,508 | 1,386 | 92.1% | 4,816 | 763 | 84.2% |
| `xtalapp/` | 16,445 | 1,705 | **89.6%** | 3,686 | 939 | **74.5%** |
| **Combined (as the terminal report blends it)** | 33,953 | 3,091 | — | 8,502 | 1,086 | 89% (blended) |

35 files reported 100% (line and branch both) and were skipped from
`term-missing`; 42 of 214 tracked files show zero missed *lines*
(branch-partial still possible on a few of those).

PORMAKE's low number is expected and should not be read the same way
as the rest of `xtal/` — it is third-party code (MIT, vendored,
`PROVENANCE.md`), compared against upstream via a recorded sample
rather than statement-covered directly, and only the code paths the
MOF builder's ~12 topologies/builds actually touch light up.
`xtal/mof/pormake/database.py` (22%) and `topology.py` (31%) are the
two driving that number down — both are large upstream modules with
many code paths (alternate database layouts, alternate topology
algorithms) this application never calls.

### The 25 least-covered modules, weighted by importance

Importance = (number of other `xtal`/`xtalapp` source files that
import from it, via static AST analysis) combined with a ×3 multiplier
for modules CLAUDE.md names explicitly in its invariants text. Score =
`missed_lines × (1 + import_count) × (3 if named in CLAUDE.md else 1)`.
This is a heuristic for *where a bug would be worst*, not a ranking of
"worst tested" alone — `xtal/core/lattice.py` (13 missed lines) ranks
above files with 10× as many missed lines because 35 other modules
import it.

| Score | Missed | Imports | CLAUDE.md | Cover | Module |
|--:|--:|--:|:--:|--:|---|
| 1608 | 134 | 3 | Y | 78.7% | `xtalapp/mainwindow.py` |
| 1008 | 28 | 11 | Y | 91.6% | `xtal/modules/report.py` |
| 792 | 66 | 3 | Y | 89.5% | `xtalapp/document.py` |
| 684 | 76 | 2 | Y | 80.2% | `xtal/analysis/rcsr.py` |
| 468 | 13 | 35 | | 93.5% | `xtal/core/lattice.py` |
| 432 | 216 | 1 | | 42.4% | `xtalapp/viewport/widget.py` |
| 408 | 24 | 16 | | 91.5% | `xtal/workspace.py` |
| 326 | 163 | 1 | | 84.1% | `xtalapp/viewport/vtk_scene.py` |
| 288 | 8 | 35 | | 95.9% | `xtal/core/structure.py` |
| 216 | 12 | 5 | Y | 97.2% | `xtal/ff/optimize.py` |
| 180 | 20 | 2 | Y | 80.6% | `xtalapp/workers.py` |
| 162 | 18 | 8 | | 88.4% | `xtal/io/trajectory.py` |
| 144 | 48 | 2 | | 89.7% | `xtal/analysis/topology.py` |
| 141 | 47 | 2 | | 76.0% | `xtalapp/dialogs/workspace_chooser.py` |
| 136 | 8 | 16 | | 95.4% | `xtal/core/spacegroup.py` |
| 136 | 68 | 1 | | 73.8% | `xtalapp/documents.py` |
| 123 | 41 | 0 | Y | 35.3% | `xtalapp/main.py` |
| 123 | 123 | 0 | | 14.6% | `xtalapp/selftest.py` |
| 120 | 40 | 2 | | 82.2% | `xtalapp/heatmap.py` |
| 115 | 23 | 4 | | 90.2% | `xtal/mof/catalog.py` |
| 110 | 11 | 9 | | 93.9% | `xtal/modules/process.py` |
| 96 | 6 | 15 | | 92.2% | `xtal/core/site.py` |
| 93 | 31 | 2 | | 72.2% | `xtal/ff/mace/calculator.py` |
| 88 | 44 | 1 | | 88.1% | `xtalapp/docks/results.py` |
| 87 | 29 | 2 | | 86.8% | `xtalapp/viewport/svg_export.py` |

Uncovered functions (by name, from AST × `missing_lines`) for the
modules above that matter most:

- **`xtalapp/mainwindow.py`**: `choose_background`, `add_atom_dialog`,
  `add_centroid_dialog`, `fill_pores_dialog`, `edit_bond_rules`,
  `add_hydrogens_dialog`, `edit_cell`, `dropEvent` — mostly dialog
  launchers (78-86% of each function's own lines missed) that open a
  real modal, which nothing patches per-test in these specific spots.
- **`xtalapp/documents.py`**: `save_document_as` — **63% of the
  function missed** (documents.py:439-467, every line past the early
  `document is None` return); `open_sample` (22% missed);
  `save_document` (15% missed). See finding below.
- **`xtalapp/dialogs/workspace_chooser.py`**: `ask` (50% missed —
  exactly `dialog.exec()` and the accept-branch unpack, discussed
  above), `paint` (68% missed, a `QListView` delegate paint method —
  cosmetic, not logic), `_new`/`_other` (75% missed each — the two
  handlers behind the "New..." / "Other..." buttons, unreachable for
  the same reason `ask` is).
- **`xtal/modules/process.py`**: `cancelled` property (line 475, 50%
  of its 2 lines missed — i.e. the property is defined but never read
  back in a test, even though `.cancel()` itself is exercised by
  `test_process_runner.py:131,197,237,244`); the four `if WINDOWS:`
  branches (`_isolation`, `_terminate`, `_kill`, `_command_line`) and
  `_end_tree` are all explicitly marked `# pragma: no cover`
  (`process.py:496,502,510,554,515`) — the author already excluded
  them from the coverage accounting rather than leaving them as a
  silent gap, which is the right call for code that can only run on
  Windows.
- **`xtalapp/selftest.py`**: every `check_*` function is 21-64%
  missed, and `check_window`/`run` (the two most consequential) are
  64%/44% missed respectively.
- **`xtalapp/workers.py`**: `run` (48% missed) — the worker-thread
  entry point at the center of the unfixed `workers.py` deadlock
  CLAUDE.md and `docs/TODO.md` § Testing and threads already document;
  not a new finding, flagged here only because it is also the
  lowest-branch-coverage function in a file CLAUDE.md names directly.

**Error / cancellation / encoding / Windows / `workspace is None`
paths, checked individually** (per the brief's specific ask):

- `workspace is None` occurs at 11 call sites across
  `xtalapp/module_runner.py` (2), `xtalapp/workspace_shell.py` (5),
  `xtalapp/main.py` (1), `xtalapp/dialogs/workspace_chooser.py` (1),
  `xtalapp/docks/workspace.py` (1) — 10 of these 11 are covered.
  **The one uncovered is `xtalapp/main.py:158`**, i.e. the *only*
  reason it's uncovered is that it lives inside the untestable
  `main()`; the underlying logic it guards (`choose_workspace`
  returning `(None, None)`) is itself well tested via
  `tests/test_workspace_chooser.py:313,329`.
- Encoding: every `encoding=`/`errors=` line touched by commit
  `e70fb86` across all 18 files it changed in `xtal/` is covered (0
  of ~39 such lines missed). But this confirms only that the keyword
  argument's *line* executes, which any read/write of that format
  already guarantees — it is not, on its own, proof that every
  codec is behaviorally correct. Only `tests/test_dftb_bands.py`
  actually round-trips a genuine non-ASCII character (`Γ`, U+0393,
  the literal Gamma-tick-label bug the commit fixed); the other 17
  changed files' tests are ASCII-only, so a wrong codec name (e.g.
  `"utf-8-sig"` typo'd for `"utf-8"`) would pass line coverage but
  might not be caught behaviourally. `tests/test_text_encoding.py`
  itself is a **static** AST guard over the source, not a runtime
  behavioural test, by its own docstring's design ("Checked by
  reading the source, because the suite runs on a Mac and the
  behaviour it guards cannot fail there").
- Windows-only paths: see `process.py` above — deliberately
  `# pragma: no cover`'d, and exercised for real only when CI's
  Windows leg runs `test_process_runner.py`'s cancellation tests
  (`SIGKILL` test is explicitly POSIX-only per commit `7b9985c`, so
  the Windows leg is running a different code path than the Mac/Linux
  legs there, correctly).
- Cancellation: `Cancellation`/`Cancelled` (`xtal/modules/job.py`) and
  `ExternalProcess.cancel()` (`xtal/modules/process.py`) are both
  exercised from `tests/test_add_atom.py`, `test_ff_ui.py`,
  `test_modules.py`, `test_process_runner.py`, `test_pxrd.py`,
  `test_scan.py`, `test_scan_module.py` — this path is in good shape.

## 5. CI

`.github/workflows/ci.yml` (380 lines) has four jobs:

- **`test`**: matrix of `macos-14` (Apple silicon), `macos-15-intel`,
  `windows-latest`, all Python 3.12 — "the three platforms we ship,
  and nothing else" (no Linux leg; one is kept dormant in a comment).
  30-minute timeout, explicitly because of the `workers.py` deadlock.
  Installs `pip install -e ".[gui,build,ase,test]"` and runs `python -m
  pytest -q` with `QT_QPA_PLATFORM=offscreen`. **The `test` extra now
  includes `pytest-qt`** (`pyproject.toml:111`), so the historical
  "GUI half was passing by not running" bug CLAUDE.md references is
  **fixed** — the widget half of the suite does run in CI today, just
  offscreen rather than headed.
- `[minor]` **CI's `test` job installs neither the `sketch`
  (`rdeditor`) nor the `pxrd` (`matplotlib`) extras** — compare
  `.[gui,build,ase,test]` (test job) against `.[gui,build,ase,test,
  sketch,pxrd]` (this machine's `[dev]`, which is what the coverage
  run above actually used). Concretely: all tests in `test_pxrd.py`
  and `test_pxrd_ui.py` (`pytest.importorskip("matplotlib")`, 62 tests
  total) and the `needs_rdeditor`-marked tests in `test_build_ui.py`
  (gated on `sketch.installed()`) silently self-skip on **every** CI
  run, on all three OSes, permanently — this is a standing gap in the
  install matrix, not a flake, and it is not mentioned in
  `docs/TODO.md`. What would catch a regression in the PXRD overlay
  window or the rdeditor sketch dialog: only a developer running the
  full `[dev]` suite locally, same as MACE.
- **`lint`**: `ruff check .` only, matching CLAUDE.md's "never `ruff
  format`" rule.
- **`build`**: builds the PyInstaller bundle on every push to `main`
  and on tags, runs `--selftest` against the actual frozen executable
  on macOS and Windows (grepping output rather than trusting the exit
  code alone — `packaging/release-macos.sh`'s lesson, per the
  comment), and only packages/releases on a tag. **Gated to `push`,
  never `pull_request`** — so `--selftest` (and therefore
  `xtalapp/selftest.py`, the one piece of code that exercises the real
  VTK viewport and the real vendored PORMAKE database end-to-end)
  never runs against a PR, only after merge to `main`.
- `git show 7b9985c --stat` / message: a cross-platform hardening pass
  ("CI red for a week behind the billing failures, and eight reasons
  why") fixing a 3.12-only f-string lint failure, a Windows `Stop`
  bug (taskkill /T), UTF-8 CIF/table writes under cp1252 (this is the
  commit that motivated `e70fb86`'s broader sweep), a workspace-panel
  height rounding difference, and five CI-environment-dependent test
  assumptions (tblite absence, scan-corner ties, offscreen Qt's 800px
  screen, macOS font metrics, `/bin/sleep` POSIX-only). All fixed at
  the line, none suppressed — consistent with the project's stated
  practice.

## Findings, ranked

1. **[important] `xtalapp/selftest.py` and the packaged-build regression gate only fire after merge, never on a PR.**
   Where: `.github/workflows/ci.yml:103-111` (`build` job's `if:` is
   `push` to `main` or a tag). Evidence: `xtalapp/selftest.py` has 15%
   pytest coverage (123/152 lines missed) and no `test_selftest.py`
   exists; the only thing that runs it is the `build` job's "Selftest
   (macOS)"/"Selftest (Windows)" steps, which the `if:` condition
   never triggers for a pull request. Why it matters: a PR that breaks
   packaging, the vendored PORMAKE database bundling, or the real VTK
   context (exactly the five things `selftest.py`'s docstring says it
   exists to catch) shows a green `test`+`lint` check and merges clean
   — the break is discovered only on the next push to `main`, by which
   point it is already on the branch everything else builds from.
   What a fix would look like: run the `build` job (or at least its
   `--selftest` step) on `pull_request` too, accepting the extra CI
   minutes, or add a cheaper pytest-level substitute for the
   import/resource-lookup checks that do not need a frozen bundle.

2. **[important] `WorkspaceChooser.ask()` has zero coverage of any
   kind, confirmed by exact line numbers, not just by CLAUDE.md's
   prose.** Where: `xtalapp/dialogs/workspace_chooser.py:421-430`.
   Evidence: coverage shows `ask` 50% missed — `dialog.exec()` itself
   and the post-accept unpacking. This matches CLAUDE.md's own
   statement that this is deliberate, so it is not a new problem, but
   the report was asked to check the guards actually cover everything,
   and this is the one classmethod that is *outside* all of them by
   construction — not autouse-guarded, not selftest-checked, not
   CI-checked. Why it matters: it is also the one piece of `main()`'s
   startup sequence a developer cannot verify without launching the
   real app. What a fix would look like: nothing needs to change in
   the code (the design is intentional and documented), but a test
   that calls `ask()` with `QDialog.exec` monkeypatched to return
   `QDialog.Accepted`/`Rejected` directly — the same opt-out pattern
   `test_closing_a_modified_document_asks_first` already uses for
   `QMessageBox.question` — would close the one remaining hole,
   verifying only the tuple-unpacking wiring rather than the dialog
   itself.

3. **[important] `xtalapp/documents.py::save_document_as` (File ▸ Save
   As...) is effectively untested — 63% of its own lines missed,
   including the error-handling branch and the CIF-conversion warning
   message.** Where: `xtalapp/documents.py:439-467`. Evidence:
   `review/coverage.json`, lines 440-460 all "MISS" except three
   early-return guard lines; `grep -rln "save_document_as"
   tests/*.py` finds four files, none of which drive the method's
   main body (they reference `getSaveFileName` for unrelated
   export flows). Why it matters: this is the method behind CLAUDE.md's
   own invariant text — "Only a document with no file at all still
   falls through to Save As" — and it is also where the CIF-conversion
   behaviour-change message lives ("wrote X; the file you opened has
   not been touched"), called out in the same invariant paragraph as
   something made visible on purpose. Neither the success message, the
   `except (ValueError, OSError)` warning dialog, nor the
   `opened_a_structure` branch is exercised. What a fix would look
   like: two widget tests — one driving a normal Save As to
   completion and asserting the shown message text, one monkeypatching
   `Document.save` to raise `OSError` and asserting `QMessageBox.warning`
   is invoked with the exception text (patched to record rather than
   raise, per the `_no_blocking_modal` convention).

4. **[minor] CI's `test` job never installs `sketch` or `pxrd`, so
   ~65+ tests always skip there, silently, on every run.** Where:
   `.github/workflows/ci.yml:70` (`pip install -e
   ".[gui,build,ase,test]"`) vs `pyproject.toml`'s `dev` extra (adds
   `sketch,pxrd`). Evidence: `pytest.importorskip("matplotlib")` in
   `test_pxrd.py`/`test_pxrd_ui.py` (35+27 tests), `needs_rdeditor`
   marker in `test_build_ui.py`. Why it matters: the PXRD overlay
   window and the rdeditor-backed sketch dialog have no CI signal at
   all, on any OS, and this is not recorded in `docs/TODO.md`. What a
   fix would look like: add `sketch,pxrd` to the `test` job's install
   line (both are pure-Python/no-compiled-core, unlike `mace`, so the
   cost argument that excludes `mace` from `dev` does not apply to
   them).

5. **[minor] The brief's stated warnings fact is wrong for the run
   performed; 11 of 14 warnings are a distinct, unexplained scipy
   issue in the MOF builder.** Where: `xtal/mof/pormake/locator.py:87`
   (`scipy.spatial.transform.Rotation.align_vectors`). Evidence: see
   the "Correction" section above — `review/probes/coverage-run.log:43-49`.
   Why it matters: "optimal rotation is not uniquely... defined" means
   the point sets `align_vectors` is asked to fit are degenerate
   (collinear or symmetric) for at least one building block exercised
   by `test_block_writer.py`, `test_mof_builder.py`,
   `test_mof_vendored.py`, and nobody has confirmed the rotation VTK
   /PORMAKE actually picks in that case is still geometrically
   correct rather than merely "a" valid answer among several. What a
   fix would look like: identify which block(s) trigger it (rerun one
   of the three test files with `-W error::UserWarning` to get a
   traceback naming the block), then either add an explicit
   `warnings.filterwarnings("ignore", ...)` scoped to that call with a
   comment explaining why non-uniqueness is harmless there (matching
   the project's own practice for the two other warnings it has
   chosen to ignore, in `pyproject.toml`), or confirm it's a
   genuinely arbitrary-but-fine tie and add the test suggested in item
   9 below.

6. **[strength]** The `.xtalproj` zip "duplicate name" warnings are
   not a writer defect — see the dedicated section above. Confirmed
   by reading both the writer and the three tests that produce them.

7. **[strength]** Cancellation, the four real autouse/session guards,
   and the `workspace is None` degraded path are all in genuinely good
   shape: 10 of 11 `workspace is None` branches covered, cancellation
   exercised from 7 different test files, and the one Windows-only
   process-killing code path is honestly `# pragma: no cover`'d rather
   than silently absent from the numbers.

8. **[informational]** Suite characterisation numbers (naming
   convention, docstrings, fixture architecture) are in §1-2 above;
   none of them rise to a finding on their own, but are reported as
   the brief asked.

## Tests worth writing

1. `test_main_returns_zero_and_opens_no_window_when_the_chooser_is_cancelled`
   — monkeypatch `xtalapp.main.choose_workspace` to return
   `(None, None)` and `xtalapp.main.open_window` to raise if called;
   assert `xtalapp.main.main([])` returns `0`.
2. `test_the_workspace_chooser_ask_returns_nothing_when_the_dialog_is_rejected`
   — monkeypatch `QDialog.exec` (opting out of the autouse guard, like
   `test_closing_a_modified_document_asks_first` does) to return
   `QDialog.Rejected`; assert `WorkspaceChooser.ask(settings) == (None, None)`.
3. `test_save_as_reports_the_original_cif_was_not_touched` —
   open a CIF-backed document, monkeypatch `getSaveFileName` to answer
   a `.xtalproj` path, call `save_document_as()`; assert the shown
   message contains "has not been touched".
4. `test_save_as_warns_instead_of_raising_when_the_write_fails` —
   monkeypatch `Document.save` to raise `OSError("disk full")`, call
   `save_document_as()`; assert `QMessageBox.warning` (patched to
   record, not raise) was called with that text.
5. `test_a_cancelled_process_reports_itself_cancelled` — call
   `process.cancel()` on a running `ExternalProcess`; assert
   `process.cancelled is True` (currently the property itself is never
   read back in any test, though `.cancel()` is called elsewhere).
6. `test_check_version_flags_the_metadata_fallback_string` —
   monkeypatch `xtal.__version__` to `"0.0.dev0"`; assert
   `xtalapp.selftest.check_version` raises `AssertionError`.
7. `test_check_samples_names_what_is_missing` — monkeypatch
   `xtalapp.samples.installed()` to return fewer than
   `len(samples.SAMPLES)`; assert the raised `AssertionError` names
   the missing sample file.
8. `test_a_project_reader_takes_the_later_of_two_same_named_zip_members`
   — write a `.xtalproj`, append a second differently-valued
   `bonds.json` in the same archive by hand, and assert
   `zipfile.ZipFile(path).read("bonds.json")` returns the **second**
   write verbatim — makes the "last write wins" assumption the two
   existing malformed-project tests rely on into an explicit,
   independently-checkable fact rather than an implicit one.

## What I did not get to

- Did not identify which specific PORMAKE building block triggers the
  11 scipy `align_vectors` warnings (finding 5) — would need a
  `-W error::UserWarning` rerun of `test_mof_builder.py` to get a
  traceback naming it, and I did not want to run a second full/partial
  suite pass under the current memory pressure.
- Did not check coverage under the CI matrix itself (Windows,
  offscreen Linux-less macOS) — everything above is from one macOS run
  with a real display; `xtalapp/viewport/*` and the Windows-only branches
  in `xtal/modules/process.py` will have different real coverage on
  CI's own runners than what `review/coverage.json` shows here, in
  both directions (offscreen loses the 4 real-GL test files; Windows
  gains the `_end_tree` path).
- Did not audit `xtal/mof/pormake/`'s 67.6%/59.5% itself function by
  function — it's vendored, and BRIEF instructs "do not reformat it";
  I judged it out of scope for a coverage review beyond reporting the
  number and noting the two modules (`database.py`, `topology.py`)
  driving it down.
- Did not attempt to reproduce the "1 in 4 wedges" `workers.py`
  deadlock or the three `test_draw_block.py` tests that overran the
  90s timeout in the brief's supplied facts — this run's
  `faulthandler_timeout=120` completed cleanly with no overruns, which
  is itself evidence of the flakiness (same suite, same machine,
  different run, different outcome) rather than something to chase
  further within this topic.
- Did not review the 65 other 100%-covered files individually, or
  spot-check the HTML report's per-line annotations beyond the modules
  named above.
