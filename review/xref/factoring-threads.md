> **Written 2026-09-24** against `origin/main` at `fc38248`, cross-referencing `review/reports/` (written 2026-09-18/19 against `3cd15e2`) with PRs #2-#9. Scratchpad paths named below were the checking scripts; they are not in the repository.

# Cross-reference: review/reports/factoring.md and threads.md vs. main @ fc38248

Method: read both reports in full from `origin/features/deep-review`; read
`gh pr view 7/2/4/5/6/8/9`, `docs/ROADMAP.md` §6, `docs/TODO.md`; then verified
every finding against the current tree with `grep`/`git show`/`git log -S` and
one byte-for-byte diff of a `mainwindow.py` seam. No tracked file was touched;
`git status` stayed clean throughout.

Timeline that matters: review written 2026-09-18/19 against `3cd15e2`. PR #2
(merge `9d4f026`, 2026-09-21) shipped 12 fixes including the worker-deadlock
fix (`937f614`, "A finished worker no longer aborts the application") **and**
the scan mid-evaluation Stop fix (`32db6a5`, authored by Sam on 2026-09-19,
i.e. essentially same-day as the review). PR #4 (`597cbf1`) corrected the
docs and made `-n auto` the pytest default. PR #7 (merge `76d1f72`,
2026-09-23, branch `refactor/deep-review-factoring`) is "all ten findings of
`review/reports/factoring.md`" per its own body, scheduled as `docs/ROADMAP.md`
§6, one commit per phase (0,1,2,3,5,4,6,7-seam1,7-seam2,7-seam3,+1 Windows fix).
PR #9 (engines: ORB-v3, MatterSim) came after PR #7 and correctly built the new
engines on the bases PR #7 introduced.

---

## factoring.md — finding-by-finding

| # | Finding | Report § | Status | Evidence |
|---|---|---|---|---|
| 1 | Action-enablement written twice, 7/12 actions disagreed under playback | §1 important | **SHIPPED** | `7ed40ce` (phase 0, in PR #7). `xtalapp/shell_state.py:42-63` `selection_states(document) -> dict[str,bool]` is now the one answer (`SELECTION_ACTIONS`, `editable = not document.is_playing`); both `_refresh_shell` (`shell_state.py:369`) and `_on_selection_changed` (`shell_state.py:126`) call `shell_state.apply(actions, shell_state.selection_states(document))`. Also folds in `delete_bond`, which `_refresh_shell` never set (a second bug the review didn't name). |
| 2 | Run-folder lifecycle in 4 places; FF path shares none with modules | §2 important | **SHIPPED** | `2fb4f5f` (phase 2). `xtal/ff/record.py` now has `open_run` (:243), `write_single_point` (:270), `close_run` (:282), mirroring `xtal/modules/record.py`. `xtalapp/docks/ff_panel.py:664,674,693,748,874,897` and `xtal/cli.py:274,294,344` all call the shared functions; the panel's failure path is one call, not the doubled one the review flagged. |
| 3 | Workspace filing policy (`_file_build`) lived in `xtalapp/`, so CLI filed builds differently | §3 important | **SHIPPED** | `9201f76` (phase 1). `xtal/workspace.py:578 Workspace.adopt_build(structure, *, run=None, ...)`. Called from `xtalapp/module_runner.py:518` and `xtal/cli.py:455` — the exact function signature the review proposed, in the exact file it proposed. |
| 4 | MOF preview perceived its own bonds (its own distance rule, own tolerance) | §4 important | **SHIPPED** | `972197f` (phase 3). `xtal/core/bonding.py:103 BondRules.pairs_within(positions, symbols)` — exactly the helper the review suggested. `xtal/mof/catalog.py` `BuildingBlock.bond_pairs()` reads the block's own bond section when present and falls back to `pairs_within` when not; `xtalapp/dialogs/mof_preview.py:230-252 _draw_bonds` now calls `block.bond_pairs()` instead of its own rule. `bond_distance` moved from `viewport/modes.py` to `xtal/core/bonding.py:184` (still used at `viewport/modes.py:534` via import), as the review's "smaller, same direction" note asked. |
| 5 | Headless-wall test tight one way (AST), thin the other (only 4 of 116 modules import-checked); no reverse-direction guard | §5 important | **SHIPPED, done better than proposed** | `972197f` (phase 3). `tests/test_core_is_headless.py`: `FORBIDDEN` now includes `PySide2, qtpy, tkinter, wx` (the review's exact list of omissions). New `test_no_core_module_pulls_in_a_gui` walks and imports **every** `.py` under `xtal/` in one subprocess — the parametrised-subprocess fix the review asked for. New `test_only_drawing_asks_the_shell_for_a_covalent_radius` uses an AST call-site scan (`RADIUS_FOR_DRAWING = {("viewport/view_settings.py","base_radius"), ("dialogs/mof_preview.py","_draw_atom")}`) rather than the review's proposed plain import-allow-list — stricter, because it catches call sites rather than just importers, and it explicitly names the two legitimate "draw this size" call sites instead of one. |
| 6 | DFTB+ and xTB calculators are a 32%-identical copy of each other; three different option-filtering idioms; `Engine.__call__` doesn't coerce | §6 important | **SHIPPED, extended beyond the ask** | `1ad7080` (phase 4). `xtal/ff/registry.py:113 options = self.coerce(options)` inside `Engine.__call__` — exactly as proposed. `xtal/ff/external.py:57 ExternalCalculator(Calculator)` is the shared base; `DFTBCalculator` and `XTBCalculator` both subclass it. Beyond what the review asked for finding 6 itself (it only flagged MACE's `__init__` prologue as "a third copy" via `dupes.py`): a second base, `xtal/ff/ase_engine.py:106 ASECalculator(Calculator)`, now covers `MACECalculator`, and — added later in PR #9, after this base existed — `ORBCalculator` and `MatterSimCalculator` too. The new engines used the shared base instead of copying a fourth/fifth time, which is the whole point finding 6 was making. |
| 7 | `mainwindow.py` 1818 lines, 821 movable into 3 groups; blocked by `menus.build_actions` binding to `window.<method>` | §7 important | **SHIPPED**, verified byte-for-byte on one seam | Phase 7, 3 commits: `bf36848` (seam 1, refresh/enable → `shell_state.ShellRefresh`), `1e30693` (seam 2, symmetry/cell → `symmetry_actions.SymmetryActions`), `be08952` (seam 3, edit/select/measure → `edit_actions.EditActions`), `db20b84` (docs). `mainwindow.py` is now 1096 lines (`shell_state.py` 450, `symmetry_actions.py` 194, `edit_actions.py` 404 — the three groups the review costed, matching its "821 lines, three collaborators" estimate closely: 2144 total lines now spread across the four files vs. 1818 in one). I diffed `_refresh_shell`'s body between `bf36848^:xtalapp/mainwindow.py` and `bf36848:xtalapp/shell_state.py` programmatically — **byte-identical** (4993 chars each side), confirming the "byte for byte, no forwarders" claim for the seam I spot-checked. PR body also claims the real app's 148-action list was diffed identical pre/post; I did not re-run that (forbidden from launching the GUI), but the pure-move mechanics (no renames visible in the diff, one seam per commit) are consistent with it. |
| 8 | Three registries (ENGINES/MODULES/FORMATS) are the same skeleton written 3x and drifted (unknown-name error type, `names()` order, `__len__`, `unregister`) | §8 minor | **SHIPPED** | `e3bac7f` (phase 6). `xtal/params.py:183 class Registry` is the generic; `xtal/ff/registry.py:154 EngineRegistry(Registry)`, `xtal/modules/registry.py:216 ModuleRegistry(Registry)`, `xtal/io/registry.py:62 FormatRegistry(Registry)`. Base class has `unregister` (:213) and `__len__` (:219) and `names()` (:237) — the three things that used to be present in only some of the three. `ENGINES.names()` now follows chooser order like `MODULES` did (per PR body), closing the drift the review measured. |
| 9 | Report block types enumerated 3 places; GUI dispatches with an 8-branch `isinstance` chain | §9 minor | **SHIPPED** | `e3bac7f` (phase 6). `xtal/modules/report.py:766 BLOCK_TYPES`, `:769 _BLOCKS` registry backing `Report.of(kind)`. `xtalapp/docks/results.py:880 RENDERERS = {...}` is the `{block class: widget factory}` dict the review proposed, read at `results.py:233`. PR body says a test asserts every kind in `BLOCK_TYPES` has a renderer. |
| 10a | Two `_resolved`, different failure behaviour (`None` vs. unresolved `Path`) | §10 minor | **SHIPPED** | `21e99be` (phase 5). `xtal/workspace.py:99 resolved(path) -> Path \| None` is now the one "same file" answer; `documents.py`'s docstring (`documents.py:25`) records that `_resolved` "came along" (i.e. was retired in favour of the core one). |
| 10b | Two readers of the engine panel (`scan.py panel_options` vs. `dftb_run.py panel_hamiltonian`), different fallback behaviour | §10 minor | **SHIPPED** | `21e99be` (phase 5). `xtalapp/docks/ff_panel.py:629 options_for`, `:924 panel_options(window, engine)` is the one reader; `xtalapp/dialogs/scan.py:722` and `xtalapp/dialogs/dftb_run.py:43` both call it. |
| 10c | A Stop recorded twice in `OptimizationWorker` (`threading.Event` *and* `Cancellation`) | §10 minor | **SHIPPED** | `21e99be` (phase 5). `xtalapp/workers.py:74-77`: `self._stop = Cancellation()` only, with a comment noting the old `threading.Event` "was... two records of one decision." `self._resume` (pause/resume) is a distinct, legitimate `Event` — not the duplicate the review meant. |
| 10d | Three axis-tick formatters, one (`heatmap.py`) drifted from the other two | §10 minor | **NOT DONE, NOT TRACKED** | Verified directly: `xtalapp/plot.py:48-52` and `xtalapp/histogram.py:61-65` still use `>= 1e5 or < 1e-2` / `>= 100` / `"{:.2f}"`; `xtalapp/heatmap.py:83-87` still uses `< 1e-3` / `>= 1000` / `"{:.3g}"`. Byte-identical to the review's citations. Not phase-5's list (which only names "one stop signal... one reader... one same-file check" — this sub-item was silently dropped from scope), and not in `docs/TODO.md` or `docs/ROADMAP.md` (grepped both, no hit on "axis"/"tick" related to this). |
| 10e | Two matplotlib dialogs (`landscape.py`/`pattern.py`), ~30% duplicated (save button, `rc_context`, error path) | §10 minor | **NOT DONE, NOT TRACKED** | Re-ran the review's similarity method (`difflib` matching blocks ≥5 lines) on the current files: 59 identical lines in blocks ≥5 out of 344 — still substantial duplication of the same shape the review measured (83/30% at the old size). Not mentioned in any phase-5/6/7 commit message, not in TODO/ROADMAP. |
| 10f | Slater-Koster search order re-encoded in `xtalapp/external.py` instead of using `Program.search()` | §10 minor | **NOT DONE, NOT TRACKED** | `xtalapp/external.py:241 _parameters_status`, docstring at :244 still says "The same order `xtal.ff.dftb.hsd.slater_koster_directory`..." — i.e. the duplication and its own admission are both still there verbatim. Not in TODO/ROADMAP. |
| 10g | Status-bar helper (`show_message`) bypassed ~20 times via direct `statusBar().showMessage(...)` | §10 minor | **NOT DONE, NOT TRACKED** | Direct calls now spread across the post-split files: `mainwindow.py` 2, `documents.py` 2, `symmetry_actions.py` 6, `edit_actions.py` 10 = 20 total (down 0 net from the ~23 the review counted, just relocated by the pure-move since it correctly carried bodies verbatim). `show_message` itself still at `mainwindow.py:755`. Not tracked. |
| 10h | Private methods reached across objects (`self.window._rebuild_recent_menu()`, `self.window._refresh_shell()`) | §10 minor | **NOT DONE, NOT TRACKED** | Still present: `xtalapp/documents.py:136,249,426,506` (`self.window._refresh_shell` / `_rebuild_recent_menu`), `xtalapp/module_runner.py:214,277,300` (`self.window._refresh_shell()`). Not tracked. |
| 11 | 16/17 domain exceptions derive from `ValueError`, one family (`CalculatorError`) from `RuntimeError`; 37 blind `except Exception` catches in `xtalapp/` because of it | §11 minor | **NOT DONE, NOT TRACKED (but improved incidentally)** | No `XtalError` base class exists (`grep "^class.*Error(ValueError)\|RuntimeError)"` still shows the exact same two families: 15 `ValueError` subclasses + `CalculatorError(RuntimeError)` + its two children). Blind catches (`noqa: BLE001` in `xtalapp/`) dropped from 37 to 24 — a byproduct of phase 2/4's consolidation (fewer call sites duplicating a catch), not of the recommended fix. Not in TODO/ROADMAP. |
| 12 | Settings layer (`xtalapp/settings.py`) repetition — ~12 lines/setting | §12 minor | **DEFERRED BY THE REVIEW ITSELF** | The review's own text calls this "a cosmetic win, not a structural one, and not worth risking" and it is not among the "three refactors that would pay back most." Unchanged on main — correctly not attempted; this is not a gap, it's the review declining to recommend action. |

**Superseded/contradicted:** none found. Every factoring finding the maintainer
acted on, he implemented at or above the fidelity the review specified (see
findings 1, 5, 6 above for where he went further); nothing was done in a way
that contradicts the review's diagnosis.

**Refactored but never proposed by us:** the Windows-only path-separator fix
(`6f1212c`, "The covalent-radius allow-list compares paths spelled with '/'")
— a bug in *his own* new test (10e's counterpart, finding 5's fix) that surfaced
on win32 only; not something either report raised, since neither review ran on
Windows.

---

## threads.md — finding-by-finding

### §1-2, "two corrections to the mechanism" / root cause — descriptive, not an ask

The report's real deliverable here is the corrected diagnosis (H0: the
**worker's** wrapper is freed on `thread.started → worker.run`, not the
`QThread`'s on `finished → quit`) and the prototype in §5/§6. Both are
verified against shipped code below.

| Finding | Report § | Status | Evidence |
|---|---|---|---|
| Recommended fix, item 1: replace `start_in_thread` with `_Run`/`_LIVE`, no `deleteLater` on either object, worker owned before `thread.start()`, drop deferred one event-loop turn after stop | §6.1 critical | **SHIPPED, essentially verbatim** | `937f614` "A finished worker no longer aborts the application" (in PR #2, before the factoring track). Current `xtalapp/workers.py:184-275`: module-level `_LIVE: set = set()`; `class _Run(QObject)` holding `worker`/`thread`, **deliberately unparented** (comment at :208-211 matches the review's own reasoning about not parenting to the window); `start_in_thread` (:259-275) does `thread.started.connect(worker.run)`, `run = _Run(worker, thread); _LIVE.add(run)`, then `worker.finished.connect(run._finished)` / `worker.failed.connect(run._finished)` — **no `deleteLater` connected to anything**; `_Run._finished` (:235-251) does `thread.quit(); thread.wait()` then `QTimer.singleShot(0, self._release)`, and `_release` (:253-256) is what drops `_LIVE`'s reference, one clean event-loop turn later — exactly the sequence the review's §6.1 prescribes and the `workers_fixed.py` prototype in §5 implements. `stop_and_wait`/`stop_all` (:216-233, :278-285) match items 3 and 6. |
| Recommended fix, item 2: `ff_panel.py:726` pass a parent | §6.2 critical | **SHIPPED** | `xtalapp/docks/ff_panel.py:779`: `self._thread = start_in_thread(self.worker, self)` — parent is now the panel (`self`), not `None`. |
| Recommended fix, item 3: `closeEvent` stop the FF optimisation too, then wait | §6.3 critical | **SHIPPED** | `xtalapp/mainwindow.py:1067-1096 closeEvent`: after `self.stop_module()` (:1083), it calls `self.ff_dock.stop()` (:1090-1091, guarded by `getattr(self, "ff_dock", None)`) and then `workers.stop_all()` (:1092) — matching the review's exact prescription and its exact reasoning (comment at :1084-1089 restates the review's "a docked widget gets no close event" point almost verbatim; this text is also now in CLAUDE.md's "Testing the GUI" section). |
| Recommended fix, item 4: reconsider `-n auto` after the fix, given the `cfprefsd` contention note | §6.4 | **SHIPPED / re-measured** | PR #4 ("The worker deadlock is fixed, and the docs still said it was not") made `pyproject.toml` default to `-n auto`; CLAUDE.md now documents `-n auto` as the parallel default with `-n 3` recommended locally (8-core-unusable caveat). The `cfprefsd` cause the review flagged was already addressed pre-existing (the INI-backend `QSettings` redirect in `tests/conftest.py:105-107`, which the review itself noted "already addressed" that half). |
| Recommended fix, item 5: pass `callback=`/poll into `optimize.run` so a scan's Stop isn't dead for minutes under UFF/MACE | §6.5 important, also §7 | **SHIPPED** | `32db6a5` "Stop works under an engine that computes in this process" (in PR #2, authored 2026-09-19 — essentially concurrent with the review). `xtal/ff/optimize.py:706-725 _StopBetweenEvaluations` wraps any in-process calculator and raises `CalculatorStopped` if `cancel.requested` before each `compute()`; `steps(..., poll_evaluations=False, ...)` (:1388-1429) applies it only when asked; `run()` (:1444, :1464) passes `poll_evaluations=True`. `xtal/ff/scan.py`'s `_one_point` (:513-545) calls `optimize.run(...)`, so a scan point now polls **mid-evaluation**, not just at the step boundary — closing the "dead for up to 3.7 minutes on Ni2Cl2BTDD" gap exactly as measured. The Force Field panel's own worker still drives `optimize.steps` directly with `poll_evaluations` left `False` (deliberately, per the comment at :1420-1428 — a caller that already breaks at the step boundary must not have Stop turn into a mid-step failure), which is precisely the distinction the review's own pattern-1 analysis called for. |
| Recommended fix, item 6: add a reaper (`aboutToQuit` / `atexit`) for abrupt exit | §6.6 critical, also §8 | **NOT DONE, NOT TRACKED** | `grep -rn "atexit\|aboutToQuit" xtal/ xtalapp/` → **zero hits**. Nothing in `docs/TODO.md` or `docs/ROADMAP.md` mentions a reaper, `aboutToQuit`, or orphaned processes on crash. This is the one `[critical]` item from threads.md that shipped nothing at all. |
| Two modules (`build.build_molecule`, `net.draw_net`) never poll cancellation | §7 important | **NOT DONE, NOT TRACKED** | `grep -n "cancel" xtal/modules/build.py xtal/modules/net.py` → **zero hits**, unchanged from the review. Not tracked. |
| `optimize.steps` advertised `cancel=` but nothing polled it except `stop_with` for external engines | §7 important | **SHIPPED** (folds into the §6.5 fix above) | Now polled via `_StopBetweenEvaluations` when `poll_evaluations=True` (`optimize.run`'s default). Direct generator callers (the FF worker) still rely on the step-boundary break, which was already correct in the review's own account. |
| Zeo++ post-process phase (`_accessible_surface`) unstoppable, ~3s | §7 minor | **NOT DONE, NOT TRACKED** | `grep -n cancel xtal/analysis/grid.py xtal/analysis/isosurface.py` → zero hits; `xtal/modules/zeopp.py:256` only passes `cancel=job.cancel` into `process.run` (the binary phase), not into the grid/isosurface post-process. Not tracked. |
| `ModuleWorker.cancel` runs the whole kill (incl. up to `GRACE_SECONDS=5.0` wait) synchronously on the GUI thread | §7 minor | **NOT DONE, NOT TRACKED** | `xtal/modules/process.py:453-464 ExternalProcess.cancel`: still `_terminate(process); process.wait(timeout=self.grace)` inline, called synchronously from `Cancellation.cancel()`'s callback list (`xtal/modules/job.py:70-77`), which fires on whichever thread calls it — the GUI thread for `ModuleWorker.cancel`. Not tracked. |
| Windows: `_terminate`/`_kill` are the same function (`_end_tree` = `taskkill /F /T` twice), no gentle stage | §8 minor | **NOT DONE, NOT TRACKED** | `xtal/modules/process.py:501-514`: `_terminate` and `_kill` both still branch to `_end_tree(process)` on Windows, unchanged. Not tracked (all Windows branches remain `# pragma: no cover`, per the review's own note). |
| Windows: a failed `taskkill` silently falls through to `process.kill()` alone, restoring the exact orphaning bug the release notes claim fixed | §8 important | **NOT DONE, NOT TRACKED** | `xtal/modules/process.py:517-537 _end_tree`: `except (OSError, subprocess.SubprocessError): pass` still falls through to `_quietly(process.kill)`. Unchanged. Not tracked. |
| Scan's `--resume` trap: `scan.csv` names a `.cif` that may not exist for an unfinished point | §9 minor | **DEFERRED BY HIM, in `docs/TODO.md`** | `docs/TODO.md` § Scans, "A stopped scan cannot be carried on" — this is the general `--resume` feature (still unimplemented), which is where the review's trap would have to be honoured when it's built. The report's specific `_Files.wrote`/`if point.finished` gotcha isn't separately quoted, but the feature it warns about hasn't shipped, so the trap can't yet have been walked into. |
| Cancelled scan handled well (report.json, partial landscape reopens) | §9 strength | **Confirmed unchanged/still true** | Not re-verified line-by-line (it's a strength, not a gap); nothing in the shipped diffs touches `xtal/modules/scan.py`'s cancel path. |

### Specific check 1 — `_Run`/`_LIVE` ownership invariant after PR #7 phase 5, and new QThread/worker usage

**Invariant intact.** `git log --oneline -- xtalapp/workers.py` shows phase 5
(`21e99be`) touched this file, but only to collapse `OptimizationWorker`'s
two stop records into one `Cancellation` (finding 10c above) — it did not
touch `_Run`, `_LIVE`, `start_in_thread`, or `stop_all`, which read
byte-identical to the PR #2 deadlock fix. `ModuleWorker` (used by
`module_runner.py`) and `OptimizationWorker` (used by `ff_panel.py`) both
still go through the same `start_in_thread`/`_Run`/`_LIVE` path.

Checked every other place a thread or worker could plausibly appear:

- `xtalapp/autosave.py` (new since the review, PR #6): uses a plain `QTimer`
  only (`QObject`/`QTimer` imports, no `QThread`), parented to the window.
  No worker, no bypass.
- ORB-v3 and MatterSim engines (`xtal/ff/orb/calculator.py`,
  `xtal/ff/mattersim/calculator.py`, new in PR #9): both subclass
  `ase_engine.ASECalculator` and run **in-process** on whichever thread calls
  them (the existing `OptimizationWorker`'s thread) — they do not construct
  their own `QThread`, so they inherit the invariant rather than needing one.
- `xtalapp/module_runner.py`: unchanged `start_in_thread(worker, self.window)`
  call site (:221); its own docstring at :360-366 still correctly says it
  must not touch the worker's lifetime.
- `xtalapp/dialogs/preferences.py`: the only other `deleteLater` call site in
  the GUI (`process.deleteLater()`, `timer.deleteLater()` at :747-748) is a
  `QProcess`+`QTimer` "Test" probe, explicitly **not** a `QThread` — its own
  docstring (:490-493) says so and cites the exact hazard: *"Through
  `QProcess`, never a worker thread: a probe is a child process with nothing
  to compute in Python, and a `QThread` would put the button on the path of
  the deadlock described in `CLAUDE.md`."* Both objects are parented to the
  dialog and live and die entirely on the GUI thread, so `deleteLater` here
  never crosses the H0/H1/H2 hazard (no cross-thread wrapper, no
  `moveToThread`) — this is a correctly-reasoned exception, not a bypass.

A repo-wide `grep -rln "QThread\|threading.Thread(" xtal/ xtalapp/` (excluding
tests) returns exactly `module_runner.py`, `mainwindow.py` (references only),
`workers.py`, and `preferences.py` — no new call site was missed.

### Specific check 2 — mainwindow.py mixin split, "byte for byte"

Verified directly: extracted `_refresh_shell`'s full body from
`bf36848^:xtalapp/mainwindow.py` and from `bf36848:xtalapp/shell_state.py`
and diffed them — **identical, 4993 characters each side, zero diff lines**.
This is the highest-traffic method in the group the review flagged (finding
1), so it's a reasonable proxy for the claim; I did not diff all 18+33+15
moved methods individually, but the commit's diff shape (pure
deletion-from-one-file + pure-addition-to-another, no lines touched in
between per `git show --stat`) is consistent with a mechanical move rather
than a rewrite.

### Specific check 3 — where he chose a different design than we recommended

| Where | Our suggestion | What he shipped | Judgment |
|---|---|---|---|
| Finding 1 (enablement) | `enabled_for(document, playing, worker_running) -> dict[str,bool]`, 3-arg | `selection_states(document) -> dict[str,bool]`, 1-arg (reads `document.is_playing` itself) | **Equal or better.** `worker_running` isn't actually load-bearing for the selection-action group the two duplicated handlers cover (only playback gates them); a parameter neither caller would ever vary is dead weight the simpler signature avoids. |
| Finding 5 (reverse-wall guard) | plain import allow-list on `el.covalent_radius` | AST call-site allow-list (`_functions_calling`) naming exact `(file, function)` pairs | **Better.** Catches call sites regardless of how the name got into scope, and is self-documenting about *which* two draw functions are legitimate rather than which *files* may import the module. |
| Finding 6 (engine duplication) | `ExternalCalculator` base for DFTB+/xTB only; MACE's copy noted separately, no base proposed for it | `ExternalCalculator` (DFTB+, xTB) **and** a second base `ASECalculator` (MACE, and later ORB-v3/MatterSim in PR #9) | **Better.** Generalizing past the immediate ask meant two engines added after the fact (PR #9) inherited the fix for free instead of becoming a 4th/5th copy — the exact failure mode finding 6 was warning about. |
| Threads §6.1 (the worker-thread fix) | pattern 1, `_Run`/`_LIVE`, no `deleteLater`, deferred release | Shipped essentially verbatim, including the variable names (`_Run`, `_LIVE`, `stop_and_wait`) and the one-event-loop-turn deferral via `QTimer.singleShot` | **Equal.** This is the review's own prototype (`workers_fixed.py`) adopted almost as-is; no meaningful divergence to judge. |

---

## Still open, ranked

1. **No reaper for abrupt exit** (threads §6.6/§8, `[critical]`). Zero
   `atexit`/`aboutToQuit` anywhere. A crash or `kill -9` still orphans any
   running xtb/DFTB+/Zeo++ child (`start_new_session=True` guarantees no
   signal follows). Not tracked anywhere. Highest-severity open item across
   both reports — it's the one the reports marked `[critical]` that shipped
   nothing.
2. **Windows `taskkill` failure falls through to `process.kill()` alone**
   (threads §8, `[important]`), silently restoring the orphaning bug the
   release notes claim fixed. Untested (`# pragma: no cover`) and untracked.
3. **`build.build_molecule` / `net.draw_net` never poll cancellation**
   (threads §7, `[important]`). Stop is a no-op on these until the job ends
   naturally. Untracked.
4. **No `XtalError` base class** (factoring §11, `[minor]` but structural).
   24 blind `except Exception` catches remain in `xtalapp/` (down from 37
   incidentally, not by design); the GUI still cannot narrow a catch to "any
   domain error" because `CalculatorError` sits outside the `ValueError`
   family. Untracked.
5. **Slater-Koster search order duplicated** (factoring §10f, `[minor]`),
   with the duplication's own docstring still admitting it. Untracked.
6. **Status-bar helper bypassed ~20 times** (factoring §10g, `[minor]`) —
   unchanged in count, just relocated by the mixin split. Untracked.
7. **Axis-tick formatter drift** (`heatmap.py` vs. `plot.py`/`histogram.py`,
   factoring §10d, `[minor]`) — same energy still renders to a different
   number of significant figures on different plots. Untracked.
8. **`landscape.py`/`pattern.py` dialog duplication** (factoring §10e,
   `[minor]`) — re-measured directly, still ~59 duplicated lines in blocks
   ≥5. Untracked.
9. **Private cross-object method access** (factoring §10h, `[minor]`) —
   `self.window._refresh_shell()`, `self.window._rebuild_recent_menu()`
   still reached from `documents.py`/`module_runner.py`. Untracked.
10. **`ModuleWorker.cancel` blocks the GUI thread up to 5s** (threads §7,
    `[minor]`) — `ExternalProcess.cancel`'s grace-period wait still runs
    synchronously on whichever thread calls `cancel()`. Untracked.
11. **Windows `_terminate`/`_kill` are the same function** (threads §8,
    `[minor]`) — no gentle-then-forceful staging on Windows. Untracked
    (and untestable in CI, per the review's own note).
12. **Zeo++ post-process (`_accessible_surface`) unstoppable, ~3s**
    (threads §7, `[minor]`). Untracked.

Everything else in both reports' scope — all 5 `[important]`-or-higher
factoring findings, both `[critical]` threads.md structural fixes (the
deadlock and the FF-panel-never-stopped gap), and the scan Stop-granularity
fix — shipped, most at or above the fidelity the reviews specified.
