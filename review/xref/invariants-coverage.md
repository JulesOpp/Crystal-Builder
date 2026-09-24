> **Written 2026-09-24** against `origin/main` at `fc38248`, cross-referencing `review/reports/` (written 2026-09-18/19 against `3cd15e2`) with PRs #2-#9. Scratchpad paths named below were the checking scripts; they are not in the repository.

# Cross-reference: `review/reports/invariants-tests.md` + `coverage.md` vs. what shipped

Review written 2026-09-18/19 against `3cd15e2`. Checked here against `origin/main` = `fc38248`
(PR #2 `9d4f026`, #3 `aa933f0`, #4 `597cbf1`, #5 `3b57645`, #6 `ec27388`, #7 `76d1f72`, #8 `cc14429`,
#9 `fc38248`, whose "phase 0" pinning commit is `970343e`). Read-only cross-reference; no files
changed, `git status` stays clean throughout.

---

## 1. The five ranked gaps in `invariants-tests.md`

All five are named, in the same order, in `970343e`'s commit message ("Engines phase 0: pin the
invariants the review found unpinned") — four were actually fixed there; the fifth (PySide6/`--selftest`)
was not touched by any PR.

| # | Gap (review's ranking) | Verdict now | Evidence |
|---|---|---|---|
| 1 | QSettings scratch-directory guard (`G3`) — no test, 278→374-plist history | **NOW PINNED** | `tests/test_suite_guards.py::test_no_window_settings_reach_the_real_preferences` — builds an `AppSettings` the way a window fixture does and asserts **both** `store.format() == QSettings.IniFormat` **and** `scratch in Path(store.fileName()).parents`. This is exactly the two-part fix the review itself proposed (format alone "is what looked right for years"). Added in `970343e`. |
| 2 | Metric-normalised strain subspace untested (invariant #26) — √2 removed, 51 tests still passed | **NOW PINNED** | `tests/test_cell_freedom.py::test_what_holding_b_takes_away_is_perpendicular_to_what_it_leaves` — holds *b* of quartz reduced to P1 (a cell whose held quantity mixes a stretch with a shear, which the review's own probe identified as the only case that can tell scaled from unscaled) and asserts the rejected/kept strain are orthogonal to `abs=1e-9`. Docstring records the same numbers the review's probe did: "1e-14 scaled, 6.2 unscaled." Added in `970343e`. |
| 3 | PySide6 `<6.10` cap and `--selftest` untested (`P1`/`P2`) | **STILL UNPINNED** | `grep -rn "6.10\|PySide6<" tests/*.py` → 0 hits; no test parses `pyproject.toml`'s `gui` extra. `grep -rn "check_window" tests/*.py` → 0 hits; `xtalapp/selftest.py`'s `run`/`check_window` (the two functions that open a real window and draw the viewport) are still exercised only by CI's `build` job, which is still `if: github.event_name == 'push'` (`.github/workflows/ci.yml:114`) — never on a PR. **Partial, unrelated progress**: `tests/test_mof_targets.py::test_the_bundles_mof_self_check_passes_from_a_checkout` now calls `selftest.check_mof_builder` directly at the pytest level (added between #7 and #9) — a real instance of the review's own suggested remedy ("a cheaper pytest-level substitute"), but only for one of `selftest.py`'s eight `check_*` functions, not for the cap or for `check_window`/`run`. Not mentioned in `docs/TODO.md`. |
| 4 | Unsaved question on workspace switch never asked in any test (invariant #14) | **NOW PINNED** | `tests/test_workspace_ui.py::test_switching_workspace_asks_once_about_unsaved_tabs` — `monkeypatch.delenv("XTAL_NO_CONFIRM_CLOSE")`, modifies two open documents, asserts the question is asked **exactly once** for the window (not once per tab), that a **No** leaves `window.workspace.root` and `window.tabs.count()` unchanged, and that a **Yes** proceeds and closes the tabs. This is the review's suggested fix almost verbatim, and goes further (also covers the "once for the window" clause). Added in `970343e`. |
| 5 | `ZEO_RADII` transcription test skips in every clean checkout and CI (invariant #19b) | **NOW PINNED** | `tests/test_porosity.py::test_the_transcribed_radii_still_match_the_vendored_source` now falls back to `tests/data/zeo_radii.cc` (a new 166-line excerpt of Zeo++'s `networkinfo.cc`, BSD notice included) when `resources/zeo++-0.3` is absent, and only prefers the live vendored source when it exists. Ran it: no skip. Exactly the review's suggested fix ("commit the extracted dict... as a small JSON/text fixture"). Added in `970343e`. |

**Net effect of `970343e`**: 4 of 5 ranked gaps closed with tests that match or exceed the review's
own suggested fix. The 5th — PySide6 cap / `--selftest` — is untouched and is now the single
most consequential unpinned invariant left in the file (packaging decision whose removal ships an
app that cannot draw, per CLAUDE.md's own words, still guarded only by a post-merge CI step).

---

## 2. Everything else `invariants-tests.md` flagged as less than fully pinned

| Invariant / finding | Review's verdict | Now | Evidence |
|---|---|---|---|
| #5 A force field/optimiser never changes bonding | weak | **UNCHANGED — still weak** | `grep -rn "structure.bonds" tests/test_optimize.py` shows no direct bonds-unchanged assertion; `ApplyRelaxation` still reaches the structure through `MoveSites`. No new test found. |
| #18b Porosity report text carries D_f's meaning | weak (`assert label and symbol and meaning`) | **UNCHANGED — still weak** | `grep -n "bottleneck" tests/test_porosity.py` → 0 hits; the review's suggested one-line fix (`assert "bottleneck" in ...`) was not applied. |
| #22 `Document.apply(...)` convention enforced only by review | untested (by design — a convention) | **UNCHANGED** | No lint/AST guard added (contrast the new `test_suite_guards.py`, which could have grown this but didn't). |
| #26 metric normalisation | weak | **NOW PINNED** (see §1.2) | |
| #27b A scan is one job, one thread | untested | **UNCHANGED — still untested** | `grep -n "thread\|worker" tests/test_scan_module.py tests/test_scan.py` finds nothing asserting single-worker behaviour. |
| G1 `XTAL_NO_CONFIRM_CLOSE` guard | partly pinned | **UNCHANGED** | Still pinned the same way (`test_no_confirm_close.py`, opt-outs in `test_quit.py`/`test_workspace_ui.py`/`test_app_shell.py`). |
| G2 `_no_blocking_modal` / `QMenu.exec` guard install itself | untested | **UNCHANGED — still untested**, and the surface it guards *grew*: CLAUDE.md's diff (§3 below) adds that `QMenu.exec` cannot be patched and is now routed through `xtalapp.menus.popup`, after "three CI jobs cost 30 minutes each" finding this the hard way — but nothing asserts the guard/`popup` redirection is actually installed. |
| G4 Teardown guard (`pytest_runtest_teardown` pumping `DeferredDelete`) leaves no live windows | untested | **UNCHANGED — still untested** | The review's suggested fix (`test_a_window_a_test_built_is_gone_before_the_next_one`, a cross-test `weakref` check in `test_window_layout.py`) was not added — `git diff 9d4f026 origin/main -- tests/test_window_layout.py` only adds an unrelated layout-share test. |
| Finding 6 (minor) `CFA1.cif` not itself a regression test | minor | **UNCHANGED** | `grep -rn CFA1 tests/test_p1.py` → 0 hits; still only `Ni2Cl2BTDD.cif` and MFU-4l's Cl1 are pinned by name. |
| Finding 7 (minor) neither `_no_blocking_modal` nor the teardown guard self-checks | minor | **UNCHANGED** | Same as G2/G4 above. |
| Finding 8 (minor) two named regressions pinned by stand-ins, not the named structures | minor | **UNCHANGED** | Same MIL-53/MFU-4l and MOF-5/synthetic mismatches remain; not something a later PR would incidentally fix. |
| Finding 9 (minor) docstrings promising more than the assertion checks | minor | **UNCHANGED** | The three named cases (`test_move_mode.py:258`, `test_porosity.py:52`, `conftest.py:62`) are untouched by `git diff` for those files/lines. |

---

## 3. `coverage.md`'s five ranked findings

| # | Finding | Verdict now | Evidence |
|---|---|---|---|
| 1 | `selftest.py`/packaged-build gate fires only after merge, never on a PR (important) | **PARTIAL** | CI's `build` job condition is unchanged (`push`/tag only, `.github/workflows/ci.yml:114`). One pytest-level substitute landed for one check function (`test_the_bundles_mof_self_check_passes_from_a_checkout` → `selftest.check_mof_builder`), added because a Ni3(HITP)2 c-axis check "failed macOS arm64, Intel and Windows alike... found twenty minutes into CI rather than here" — precisely the failure mode Finding 1 describes, now caught at the pytest level for that one check. `check_window`/`run` (the viewport-drawing half, and the actual `--selftest` CLI flag) remain PR-blind. |
| 2 | `WorkspaceChooser.ask()` zero coverage of any kind | **STILL UNPINNED** | `grep -rn "\.ask(" tests/test_workspace_chooser.py` shows no direct call to `WorkspaceChooser.ask`; the review's own suggested one-line test (patch `QDialog.exec`, call `ask()` directly) was not added, though the file did gain other, unrelated tests (a `QMenu` submenu-walk fix for `test_open_sample_offers_every_sample_that_is_installed`). Confirmed by design intent (CLAUDE.md still calls this the one deliberately-unreachable dialog), but the specific low-cost fix suggested was not taken. |
| 3 | `xtalapp/documents.py::save_document_as` effectively untested (63% missed, error branch and CIF-conversion message both unreached) | **STILL UNPINNED** | `grep -rn "save_document_as" tests/*.py` → 0 hits (down from the review's "four files, none driving the method" — now literally zero references). The method itself is unchanged in shape (still in `xtalapp/documents.py:488`, still writes the "has not been touched" message and the `except (ValueError, OSError)` warning branch) despite `documents.py` being touched for 80 lines and `edit_actions.py`/`shell_state.py` being split out of `mainwindow.py` in the same window (PR #7). Only its private helper `_suggested_project` gained a test (`test_workspace_ui.py::test_save_offers_the_project_inside_the_entry`). This is the most concrete "still open" item in the whole cross-reference: a File ▸ Save As invariant CLAUDE.md itself calls out by name, refactored around repeatedly, never exercised end-to-end. |
| 4 | CI's `test` job never installs `sketch`/`pxrd`, ~65 tests silently skip on every run | **STILL UNPINNED** | `.github/workflows/ci.yml:71` is unchanged: `pip install -e ".[gui,build,ase,test]"` — no `sketch,pxrd`. Not mentioned in `docs/TODO.md`. |
| 5 | 11/14 warnings are an unexplained scipy `align_vectors` non-uniqueness, not zipfile | **PARTIAL / substantively addressed at the design level** | PR #3 ("Four orientation tests asserted a fit that is not the same twice") is a direct, dated investigation of exactly this warning: it identifies the same non-unique-rotation warning as the tie `xtal/mof/orient.py` exists to break, measures that results move but "do not move the wrong way" across three CI platforms, and rewrites four tests to assert the *property* the tie-break rule produces rather than a machine-specific number. The warning itself is still unsuppressed/uncommented at `xtal/mof/pormake/locator.py:87` (the narrow fix the review suggested — a scoped `filterwarnings` with a comment, or an explicit test of the tie — was not taken in that exact form), but the underlying "is the rotation still geometrically correct" question was answered and is now load-bearing product behaviour (see the new "which way round a symmetric node goes" invariant, §4). |

---

## 4. New invariants added to `CLAUDE.md` since `3cd15e2` — tested or not?

`git diff 3cd15e2 origin/main -- CLAUDE.md` (via `git show <ref>:CLAUDE.md`) shows several genuinely
new invariants beyond wording/number corrections. Wording-only fixes (the "MFU-4l 190k triangles" →
"307k triangles" number update, the mainwindow-mixin refactor note, the mof-orientation prose that
documents PR #2's `attach.py`/`orient.py`/`interpenetrate.py`/`layers.py` — all four files new since
`3cd15e2` but landed *in* PR #2 before `9d4f026`, with their own dedicated test files
`test_mof_orientation.py`, `test_interpenetration.py`, `test_interpenetration_ui.py`,
`test_mof_rcsr_layers.py`) are noted but not re-litigated line by line here; they are the subject of
PR #2's own 95-new-tests claim and were spot-checked as present and passing.

The invariants below are the ones that changed *behaviour*, not just prose, since the review's base:

| New invariant | Where | Test? |
|---|---|---|
| **An autosave is a side file, never the document** — written every N minutes to `<workspace>/.autosave/`, never where Save writes; deleted when clean; offered back via `NoticeBar`, never auto-applied | `xtalapp/autosave.py` (new file) | **NOW PINNED.** `tests/test_autosave.py` (279 lines) — writing (`test_a_modified_document_is_autosaved_beside_the_workspace`, asserting the original file's bytes are untouched), re-write-only-after-edit, removal on save/undo-to-clean/deliberate discard. Targeted coverage run: `xtalapp/autosave.py` 90% line coverage (12/116 lines missed, mostly minor branches at lines 66, 103, 105-106, 193-195, 211, 214-218). |
| **Quitting asks before it stops anything** — a running calculation is asked about first, the unsaved question second, and the run is stopped only once both are yes | `xtalapp/mainwindow.py` (`closeEvent`/`confirm_quit`/`may_discard_unsaved`), `xtalapp/application.py` | **NOW PINNED, thoroughly.** `tests/test_quit.py` (new file, ~20 tests) — `test_the_run_is_asked_about_before_the_unsaved_work` asserts the literal order (`"running" in answers[0][2]`, `"unsaved" in answers[1][2]`); `test_a_no_to_the_unsaved_question_keeps_the_run_too` and `test_cancelling_the_quit_leaves_the_run_running` cover both refusal branches; plus the modal-in-front-of-quit bug (`test_the_dialog_in_front_is_closed_before_the_question`) and "asked once however it arrives" (menu vs. desktop Cmd-Q) get their own tests. One of the best-covered new invariants in the diff. |
| **A colour a person did not choose is worked out from the palette** — `tone.retone` restyles hint/warning/warning-box text on theme change; a hand-chosen colour is never overwritten | `xtalapp/widgets/tone.py` (new file) | **NOW PINNED.** `tests/test_tone.py` (new file) — `test_no_widget_styles_a_warning_by_hand` is a source-sweep guard (greps `xtalapp/**/*.py` for the old literals `#8a5a00`/`#fdf3e0`/`palette(mid)`), plus behavioural tests for light/dark styling and retoning on theme change, and (separately, view-background side) `test_a_theme_change_leaves_a_chosen_colour_alone`. **Caveat found while verifying**: `test_a_toned_widget_is_restyled_when_the_theme_changes` fails on this machine because the sandbox's default Qt palette is already dark (`is_dark(QApplication().palette())` → `True`) — the test never forces a light starting palette before asserting a change, so it is environment-fragile rather than actually broken. Confirmed reproducible in isolation; not a maintainer regression, but worth a bug report upstream. |
| **A connection point's distance is measured from the centroid of the atoms it hangs off, not from a single atom**; **an attachment is one X plus the distinct body atoms bonded to it** | `xtal/mof/attach.py` (new since `3cd15e2`, landed in PR #2) | **NOW PINNED** — `test_mof_orientation.py`/`test_mof_builder.py` exercise `attach.py`; MFU-4l and Ni3(HITP)2 (the two structures the invariant says could not previously be built) are named test fixtures. |
| **Which way round a symmetric node goes is a tie; `consistent` (the new default) breaks it by minimising `pair_cost` across each edge**, with a fit-then-move-only-if-strictly-cheaper search and a second-pass rollback (`FIT_SLACK`/`CELL_SLACK`) | `xtal/mof/orient.py` (new) | **NOW PINNED** — `tests/test_mof_orientation.py` (extended +90 lines since `9d4f026`), rewritten by PR #3 to assert the tie-break property rather than platform-specific numbers (see §3 Finding 5). |
| **A face is scored, never bonded** (`attach.face_of`) | `xtal/mof/attach.py` | Exercised transitively through the orientation/build tests above; no test isolates `face_of` by name — **PARTIAL**. |
| **A layer net is stacked after it is built, never by the builder** (`xtal/mof/layers.restack`) | `xtal/mof/layers.py` (new) | **NOW PINNED** — `tests/test_mof_rcsr_layers.py` (new file, 139 lines). |
| **An interpenetrated framework carries the bonds its copies had; the detector enumerates rather than theorises** | `xtal/analysis/interpenetrate.py` (new) | **NOW PINNED** — `tests/test_interpenetration.py` + `tests/test_interpenetration_ui.py` (both new). |
| Worker deadlock: **now fixed** (2026-09-21) — both thread and worker owned from Python via a module-level `_Run` set, never `deleteLater` | `xtalapp/workers.py` | Reasonably pinned per CLAUDE.md's own text ("measured across five configurations... clean in all fifteen"); the review's separate, still-open ask (#27b, "one job on one thread") is a different claim about scan parallelism and remains untested (§2). |
| `-n auto` is now the pytest default; `-m "not gui"` marks the headless half; `QMenu.exec` cannot be patched, routed through `xtalapp.menus.popup` | test infrastructure, not a product invariant | Infrastructure-level; the `popup` redirection itself has no self-check (folded into G2 above). |

**Answer to the explicit ask ("name any new invariant with no test")**: `face_of` (scored-never-bonded)
is the one new invariant whose own rule is not isolated by any test name — it rides along inside the
larger orientation/build tests. Everything else new in this diff (autosave, quit-order, palette
colours, attach/orient/layers/interpenetrate) has a dedicated test file.

---

## 5. Coverage of the new modules since `9d4f026`

New/changed modules named in the brief, measured with a targeted `pytest --cov` run
(`COVERAGE_FILE` redirected into the scratchpad; `-n0 -p no:cacheprovider`; nothing written to the
repo — `git status` confirmed clean after). Two runs were needed: the first (only the modules'
"own" test files) understated `record.py`/`external.py` because those are exercised mainly through
force-field run plumbing tests (`test_modules.py`, `test_variable_cell.py`, `test_workspace.py`,
`test_dftb_bands.py`, `test_xtb.py`), not their own dedicated file — a reminder that "map tests to
modules by reading" (the brief's fallback) can undercount real coverage if the mapping is wrong.

| Module | Line cov. | Missed (of total) | What's missing | Note |
|---|---:|---:|---|---|
| `xtal/io/text.py` | **100%** | 0/12 | — | Both the BOM-strip path and the non-UTF-8 error-naming path are pinned functionally in `tests/test_io.py` (`test_a_file_with_a_byte_order_mark_opens`, parametrised over every text format; `test_a_file_that_is_not_utf8_is_named_in_the_error`, asserting the exact message). Best-covered new module in the set. |
| `xtal/ff/charges/eqeq.py` | 96% | 3/72 | lines 116, 134, 136 (minor branch tails) | `tests/test_eqeq.py` (146 lines) — solid. |
| `xtal/ff/ewald.py` (`pair_matrix`) | 92% | 10/126 | lines 117-125, 227 | `tests/test_ewald.py` (51 lines). |
| `xtalapp/widgets/notice.py` | 96% | 2/51 | lines 66, 86 | No dedicated test file, but exercised via `test_autosave.py`'s restore-offer path. |
| `xtalapp/widgets/tone.py` | 98% | 1/42 | line 71 | See the environment-fragility caveat above (§4). |
| `xtalapp/widgets/start_pane.py` | 93% | 4/61 | lines 110-113 | `tests/test_start_pane.py` (113 lines, new file). |
| `xtalapp/autosave.py` | 90% | 12/116 | lines 66, 103, 105-106, 193-195, 211, 214-218 | See §4. |
| `xtal/ff/external.py` | 96% | 3/68 | line 75 (`n_atoms == 0` guard), 114 (atom-count-mismatch guard in `_write_geometry`), 143 (`CalculatorStopped` branch of `_run`) | Measured with `test_engine_plumbing.py` + `test_dftb_bands.py` + `test_xtb.py`. The three misses are all error/guard paths — thin but each is a single defensive line, not an unexercised feature. |
| `xtal/ff/record.py` | 91% | 14/157 | lines 92-95 (typing-assignment exception path), 101, 116, 121, 149, 206-207 (final-structure-write exception path), 273, 325, 338-339 | Measured with `test_modules.py`/`test_variable_cell.py`/`test_workspace.py`/`test_pxrd.py`. The two exception branches (92-95, 206-207) are the ones worth a look — a broken UFF typer or a final-CIF write failure during a real run would go unexercised, though both degrade gracefully by design (log a line, keep going) rather than crash. |
| `xtal/ff/mattersim/calculator.py` | 88% | 9/72 | lines around the real-import `_build_model` try-block and the two subprocess-based tests (`test_the_real_model_s_stress_agrees_with_a_numeric_one`, `test_every_model_offered_is_a_name_mattersim_resolves`) that run in a fresh interpreter and so don't register in this process's coverage | Mirrors the MACE precedent the original review already endorsed: `_load_model` is the seam tests replace; `mattersim` is not installed in this venv (by design, matching the `mace` exclusion from `[dev]`). The mps-refusal branch (`_build_model`'s `if device == "mps": raise`) **is** unit-tested (`test_an_apple_gpu_asked_for_by_name_is_a_sentence_not_a_crash`), just not counted as "hit" in a coverage sense worth flagging as a false negative rather than a real gap. |
| `xtal/ff/orb/calculator.py` | 76% | 18/74 | the real `_build_model` import/load try-block (`orb_models` not installed here either) | Same MACE-precedent shape as MatterSim: `_load_model` seam mocked in `test_orb.py` (224 lines) for the arithmetic/registry paths; real-model load untested locally by design, consistent with project convention. |
| `xtalapp/main.py`, `xtalapp/dialogs/workspace_chooser.py::ask`, `xtalapp/documents.py::save_document_as` | unchanged from the review (35%, `ask` 50% missed, `save_document_as` 63% missed) | — | — | Not new modules, but explicitly asked about — see §3, unchanged. |

---

## Gaps that matter, ranked

1. **`xtalapp/documents.py::save_document_as` is still completely untested end-to-end** (coverage.md
   Finding 3). This is the single most concrete regression risk in the whole cross-reference: the
   method is unchanged in shape, the codebase around it was refactored twice in the meantime
   (mainwindow split into mixins in PR #7; `documents.py` itself touched 80 lines), and it is the
   CLAUDE.md-named home of a user-visible behaviour-change message ("wrote X; the file you opened
   has not been touched"). Zero test references the function name at all, down from the review's
   "four files, none driving it" — the surface area shrank to nothing rather than growing.

2. **The PySide6 `<6.10` cap and `--selftest`'s real window-drawing check remain the least-defended
   invariant in the codebase** (invariants-tests.md's own #1 ranking by damage, unaddressed by the
   one PR that explicitly went and fixed everything else the review flagged). Both the cap
   (`pyproject.toml`) and `check_window`/`run` have zero pytest coverage, and CI's `build` job — the
   only thing that ever runs `--selftest` for real — is still gated to `push`, never `pull_request`.
   A PR that widens the PySide6 range or breaks the real viewport path still shows all-green.

3. **`WorkspaceChooser.ask()` remains the one code path nothing in the suite, CI, or `--selftest`
   ever calls**, unchanged since the review, despite the review supplying a one-test fix
   (monkeypatch `QDialog.exec`, call `ask()` directly) that would have cost almost nothing.

4. **CI's `test` job still installs neither `sketch` nor `pxrd`**, so ~65 tests keep silently
   self-skipping on every run, on every OS, with no record of the gap in `docs/TODO.md` — unchanged,
   minor but a standing blind spot rather than a one-off.

5. **Two of the guard-of-guards (`_no_blocking_modal`/`QMenu.popup` install, and the
   `pytest_runtest_teardown` window-leak fix) are still not self-checking**, and the modal-guard
   surface actually *grew* in this window (the new `QMenu.exec`-cannot-be-patched problem, discovered
   the hard way at a cost of "three CI jobs, 30 minutes each"). The asymmetry the review noted still
   holds: losing the teardown guard is a *silent* regression (slow suite, eventual abort with a stack
   that names nothing), not a loud one.

6. **`face_of` (a face is scored, never bonded) is the one genuinely new invariant with no test
   naming it directly** — low severity, since it is exercised transitively by the orientation/build
   suite, but worth a name if anyone goes looking for "where is this rule pinned."

7. **Minor, unchanged since the review and low cost to fix**: `CFA1.cif` still isn't its own
   regression test; `test_every_diameter_carries_what_it_means` still only checks truthiness, not
   the word "bottleneck"; the three docstrings that promise more than their assertions check
   (`test_move_mode.py:258`, `test_porosity.py:52`, `conftest.py:62`) are untouched; and `#27b`
   ("a scan is one job on one thread") and `#5`/`#22` (bonds-unchanged-by-relax, `Document.apply`
   convention) remain exactly as untested as the review found them.

**What genuinely got fixed, for balance**: the QSettings scratch-directory guard (the review's
single "critical" finding, with a documented history of silent real-world damage), the metric
normalisation of `CellFreedom`, the `ZEO_RADII` transcription skip, and the unsaved-question-on-
workspace-switch gap were all closed in one commit (`970343e`), each with a test that matches or
exceeds the review's own suggested fix and is verified here to actually assert the failure mode
(not just re-run the happy path). Two new large invariants (autosave, quit-question ordering) landed
with unusually thorough test files. The scipy `align_vectors` warning was investigated properly
(PR #3) rather than silenced or ignored, and turned into load-bearing, tested product behaviour
(`orient.py`'s tie-breaking).
