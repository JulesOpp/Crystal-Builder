# Hit list — after the four tracks shipped

> **Written 2026-09-24** against `origin/main` at `fc38248` (the merge of
> PR #9). It supersedes the ordering in [PLAN.md](PLAN.md) for everything
> that has since shipped; PLAN.md's measurements still stand where the code
> has not moved. Every "verified" claim below was reproduced on this
> checkout on 2026-09-24, not read off a diff. The five cross-reference
> reports this rests on are in [xref/](xref/); their tables are the
> evidence.

## What happened between 2026-09-21 and 2026-09-24

Julius merged seven PRs (#3–#9, 225 files, +19 348 / −2 660), five of them
planned directly from `review/` and scheduled as `docs/ROADMAP.md` §§ 5–7:

| PR | Track | Source |
|---|---|---|
| #5 | Performance, 9 commits | `reports/performance.md` |
| #6 | Shell: start pane, autosave, quit order, dark mode, eight silent failures | `reports/ui-ux.md`, `reports/edge-cases.md` |
| #7 | Factoring, 8 phases, `mainwindow.py` 2014 → 1093 lines | `reports/factoring.md`, "all ten findings" |
| #8 | Occupancy pies on the GPU, 154 → 2.3 ms/frame | not ours |
| #9 | ORB-v3, MatterSim, EQeq, 16 COD samples | PLAN.md Phase 2 |

`main` has been green on all three CI platforms for six merges under
`-n auto`. No CI failure in that window was a hang.

**The scorecard.** Every `[critical]` and `[important]` finding in the
performance, factoring, UI/UX and edge-case reports got at least a verified
partial fix. His engines phase 0 pinned four of the five invariant gaps we
ranked. All six "decisions that gate work" were answered. What follows is
the remainder — ordered by how much it matters, not by how much work it is.

---

## 0. Fix first: two things in PR #9 are scientifically wrong

These are the only items in this file where a user gets a wrong number
with no warning. Both need Julius's call on the science before code.

### 0.1 EQeq gives impossible charges for every metal outside a seven-element list

`xtal/ff/charges/eqeq.py:62` `CHARGE_CENTRES` is the paper's 2012 file —
Mg, V, Co, Ni, Cu, Zn, Zr. Every other element is expanded about the
neutral atom, and the charge runs away. **Verified on this checkout:**

| Structure | Element | Shipped | With a centre |
|---|---|---|---|
| `cod/Al-soc-MOF-1.cif` (his own sample) | Al | **+6.33** | +2.40 (centre 3) |
| rock salt | Na | **+1.78** | — |
| AlF₃, ReO₃-type, small cell | Al | **+96** | — |

Aluminium has three valence electrons; sodium one. About half the COD
library — the Al, Cr, Fe, Mn and Eu frameworks — is affected, and the only
caveat shown is the generic *"an estimate to look over"*. The user cannot
set a centre; the authors' program read an editable file. Everything else
in the implementation checks out: the formulas, the −2 eV hydrogen, λ = 1.2,
the halved Coulomb term, the overlap term and the ionisation indexing all
match the authors' `main.cpp` and Open Babel; the Ewald pair matrix is
split-independent to 1e-13 and reproduces the simple-cubic and BCC
Madelung constants.

**Steps.**
1. Extend `CHARGE_CENTRES` to Open Babel's ~65-element table (Al 3, Ti 3,
   Cr 2, Mn 2, Fe 3, Eu 3, In 3, Cd 2, Na 1, …). Open Babel is GPL, but a
   table of common oxidation states is a fact, not code; regenerate it
   from a stated rule and cite the source in the docstring the way the
   NIST table is cited.
2. `parameters()` refuses, or warns through the existing `note`, for any
   element with no centre whose charge would exceed its group valence.
3. Let the user override a centre per element from the Force Field panel
   (a `Param`, so the CLI gets it free).
4. Tighten the MOF-5 validation: it compares two *different* geometries
   at ±0.05 e. On the same geometry the port matches the authors'
   algorithm to 1.5e-4 e, so pin the authors' `IRMOF-1.cif` (or COD
   1516287) and compare at ±2e-3. Fix the docstring, which attributes the
   0.05 e to "the converged Ewald sum and a newer NIST table" — it is the
   geometry.
5. A small-cell test (quartz, halite) with the physically expected sign
   and magnitude, so a table regression cannot pass on MOF-5 alone.

**Open questions for Julius.** Which oxidation state when an element has
several common ones (Fe 2 vs 3, Cu 1 vs 2)? Open Babel picks one; the
right answer for a MOF is usually the crystallographer's, so is the
override in step 3 enough, or should the reader take
`_atom_site_oxidation_number` / `_atom_type_oxidation_number` from the CIF
when present? And should EQeq refuse (like the coincidence guard) or warn
(like the subgroup ladder) when a centre is missing?

### 0.2 ORB-v3 and MatterSim run without D3 dispersion but cite a D3 benchmark

`xtal/ff/orb/calculator.py:8` and the engine's description rely on
MOFSimBench's "89 % volume accuracy vs UFF4MOF's 62 %". MOFSimBench ran
every model with D3(BJ), either baked in or via `torch-dftd` at inference.
The shipped engines — and MACE — are bare PBE(+U) models, so relaxed cells
will come out systematically large. Our
[registry-and-interpenetration.md](design/registry-and-interpenetration.md)
raised this as decision 4; it did not make it into PLAN.md's decision
list, so Julius never saw it. That omission is ours.

**Steps.**
1. Measure it: relax MOF-5 and UiO-66 with and without `torch-dftd` D3(BJ)
   on ORB-v3 and MatterSim; compare the volume against the COD cell.
   Two structures, four runs — an afternoon.
2. If the volumes move by the expected 2–5 %, add `dispersion` as a
   `Param` on `ASECalculator` so all three engines get it once
   (`ase_engine.py` is the seam factoring phase 4 built for this). MACE
   already has `mace_mp(dispersion=True)` hidden.
3. Either way, rewrite the ORB docstring and the engine description so
   the benchmark claim names the configuration it was measured in.

**Open questions.** Does an `ENGINES` entry own its dispersion correction,
or is it a separate `ENGINES` entry ("ORB-v3 + D3")? The former keeps the
chooser short; the latter keeps a result's provenance in one word. Is
`torch-dftd` an acceptable extra (it is MIT, CPU-capable)? And should the
default be D3 *on*, since that is what the benchmark measured?

### 0.3 ORB's "double precision" may be float64 weights on float32 geometry (unconfirmed)

orb-models 0.7.0 builds its graph in `torch.get_default_dtype()` at call
time. `xtal/ff/orb/calculator.py` `_build_model` restores torch's global
default after loading, so the float64 model then receives float32
positions. MACE's loader sets the global to float64 and never restores
it, so ORB's precision depends on **which engine loaded first**. Neither
package is installed here. One check on a machine with `orb-models`:
compare the finite-difference energy error with the default restored and
not restored; the 4e-7 eV figure in the docstring should reproduce only in
one of the two.

---

## 1. Code review of what he shipped, by PR

What is incomplete or thin in each track, with the fix where it is
obvious. Items already in his `docs/TODO.md` are marked *tracked*; the
others are not written down anywhere.

### PR #9 — engines, EQeq, COD

- §0.1–0.3 above.
- **Stress guards are vacuous.** ORB, MatterSim and MACE each check
  analytic against numeric stress on one water molecule in a 30 Å box at
  `abs=2e-3`; the whole stress on that system is below the tolerance
  (planar, so `zz` = 0). A sign or factor-2 error passes. Use a strained
  dense crystal. The upstream code, read directly, does use the ASE sign
  and units, so this is a missing guard, not a bug.
- **Deuterium and disorder break the COD samples for computation.**
  `cod/MIL-53.cif` (neutron, `D`) is refused by every engine; UFF's
  message says it "covers hydrogen to lawrencium", which is misleading,
  and ASE's `Atoms('D')` is a raw `KeyError` not wrapped in
  `CalculatorError`. Eleven of sixteen COD files have partial-occupancy
  sites, and `xtal/ff` treats every split site as a full atom: UiO-66
  EQeq then puts an oxygen at **+0.66 e**. Nothing says so before Relax
  or Equilibrate. See § 3.3 for the feature this wants.
- **MatterSim's model card** says it "has relatively low accuracy for
  organic polymeric systems", which is the linker half of every MOF.
  Belongs in the engine description beside the speed number.
- **MACE-MP-MOF0**: decision 2 was "Yes we want them"; it is not in
  `MODEL_CHOICES`, the ROADMAP or the TODO. Now that `ASECalculator`
  exists it is one entry in a list. See § 3.2.
- `resources/samples/MIL53.cif` is, by its own provenance, a PORMAKE build
  on `acs` (the MIL-88/MIL-100 net); MIL-53 is a rod MOF. Unreachable
  from the UI, so low impact, but the name is wrong. `MIL53`, `UIO66` and
  `NiHITP` still ship in every bundle and appear in no menu.
- The CCDC-headed files are kept *knowingly* (PROVENANCE.md, 2026-09-23).
  That is his decision, recorded; CFA1's header does say "may not be
  copied or further disseminated", so it is worth one more look before a
  public release.

### PR #6 — shell

- **Find symmetry's Return key closes the dialog instead of adopting the
  group.** `xtalapp/dialogs/find_symmetry.py:114` calls
  `setDefault(True)` *before* `addButton(..., AcceptRole)`, and the button
  box resets it. **Verified headless**: `Close isDefault=True`,
  `Adopt this group isDefault=False`. Predates the review (`4f28eb4`);
  reads as fixed from the source; no test. One-line move plus a test that
  asks the box which button is default.
- **`tests/test_tone.py::test_a_toned_widget_is_restyled_when_the_theme_changes`
  fails on a Mac already in dark mode** (verified here: this machine is).
  It assumes the starting palette is light, so "before" and "after" are
  the same amber. CI runners are light, so CI never sees it. Set the
  light palette explicitly at the top of the test.
- **Toolbar overflow got slightly worse**: `sizeHint()` 1342 → 1356 pt
  from the new engine entries; the default-window formula is unchanged,
  so on the review's screen the chevron is still there. Not tracked.
  `docs/MENUS.md` § 3 already priced icon-only axis buttons.
- Trajectory-panel overlap, Style-only reflow, live Move buttons, screen
  readers — *tracked* in TODO § Interface, quoted from our report.
- "Log" naming two things and ASCII units — deferred in spirit to the
  text pass, but no TODO entry.

### PR #7 — factoring

All five `[important]` findings shipped, three of them beyond what we
asked (one enablement rule, an AST call-site guard instead of an import
allow-list, a second `ASECalculator` base that PR #9 then reused). The
`_refresh_shell` seam was byte-diffed across the split: identical.
Leftovers, none tracked:

- `XtalError` base (finding 11): `CalculatorError` still sits outside the
  `ValueError` family, so 24 blind `except Exception` remain in `xtalapp/`.
- Three axis-tick formatters still disagree (`heatmap.py:83` vs
  `plot.py:48`/`histogram.py:61`); `landscape.py`/`pattern.py` still share
  ~59 duplicated lines; the Slater-Koster search order is still
  re-encoded in `xtalapp/external.py:241` with its own docstring admitting
  it; `statusBar().showMessage` bypasses `show_message` 20 times;
  `documents.py`/`module_runner.py` still reach `self.window._refresh_shell()`.
- The `SELECTION AND EDITING` banner in `mainwindow.py` is stale — he
  says so in the PR body.

### PR #5 — performance

- Drag at 65 ms/step and Supercell at 1.2 s — *tracked* ("A drag and a
  Supercell still rebuild from scratch"). This is the report's one **L**.
- `_sync_bond_type_actions` still derives the bond graph on both refresh
  paths (`shell_state.py:127,382`); it is fast only because
  `bonding.graph` is memoised. An **S** cleanup that stops the next
  cache-busting edit from bringing the freeze back.

### PR #2 (ours) — what we left unfinished

- **The abrupt-exit reaper was never built.** PLAN.md 1.7 included an
  `aboutToQuit`/`atexit` reaper; PR #2 shipped the `closeEvent` half only.
  Zero `atexit` anywhere. A crash or `kill -9` still orphans a running
  xtb, DFTB+ or Zeo++ (they start with `start_new_session=True`, so no
  signal follows). The `[critical]` item in `threads.md` that shipped
  nothing.
- Windows: a `taskkill` failure falls through to `process.kill()` alone
  (`# pragma: no cover`); `_terminate` and `_kill` are the same function.
- `build.build_molecule` and `net.draw_net` never poll cancellation;
  `ModuleWorker.cancel` blocks the GUI thread for up to 5 s.

### Tests and CI — still unpinned after his phase 0

- **PySide6 `<6.10` cap and `--selftest`**: the fifth of our five ranked
  gaps, untouched. The `build` job is still `push`-only
  (`ci.yml:114`), so a PR cannot break the packaged app and know it.
  `test_the_bundles_mof_self_check_passes_from_a_checkout` shows the
  shape of the fix — do it for `check_window` and the cap.
- `save_document_as` (`xtalapp/documents.py:488`): zero test references,
  refactored around twice, and it carries a CLAUDE.md-named message.
- `WorkspaceChooser.ask()`: still no direct call in any test.
- CI still installs `.[gui,build,ase,test]` without `sketch,pxrd`, so
  ~65 tests skip every run.
- No test asserts bonds are unchanged after a force-field run (#5), nor
  that a scan is one thread (#27b), nor that the `_no_blocking_modal` /
  teardown guards are installed (G2, G4).

---

## 2. One small branch of one-liners

Each of these is under an hour, needs no decision, and closes a real
failure. Together they are one PR:

1. Find symmetry default button + test (§ 1, PR #6).
2. `test_tone.py` starting palette.
3. `.gen` writer refuses or warns on zero sites (File ▸ New → Export
   still produces a file nothing reads; verified).
4. `xtal/modules/process.py:366` `mkdir` inside the `try`, so a read-only
   workspace gets the sentence the rest of that file gives.
5. `safe_name` replaces non-ASCII instead of deleting it
   (`café`/`cafè` → `caf`, verified).
6. `--supercell` prints an atom-count estimate before a big one.
7. CSSR's `keeps` names the 4-dp cell rounding.
8. Wrap ASE's `KeyError` on `D` in `CalculatorError`, and make UFF's
   message say "no parameters for deuterium; rename it H".
9. `_sync_bond_type_actions`' double derivation (§ 1, PR #5).

---

## 3. Features that are cheaper or better-defined now

Each of these was in [REVIEW.md](REVIEW.md) § 7 or PLAN.md and was either
blocked or vague. Something he shipped since changed that. Sizes use
PLAN.md's scale.

### 3.1 Dispersion as a shared engine option — **S–M**, unlocked by `ASECalculator`

§ 0.2 is the science; this is the feature. One `Param` on the base gives
MACE, ORB and MatterSim the same D3 switch, recorded in `run.log` by
`record.py`. *Open:* default on or off; one entry or three.

### 3.2 MACE-MP-MOF0 — **S**, unlocked by `ASECalculator`

He said yes; it never got built. It is one line in `MODEL_CHOICES` plus
the caveat our research found: it is a phonon/QHA model with 28 of 100
MOFSimBench structures unsupported, so it belongs beside "E(V) is not
F(V)" (his TODO § Scans) more than beside relaxation. *Open:* does he
still want it once told that?

### 3.3 "Prepare for simulation" — **M**, unlocked by the COD library

Sixteen real experimental CIFs are now one click away, and eleven of them
cannot be relaxed as they stand: split sites, solvent, deuterium, no
hydrogens (MIL-88B, MIL-100, MIL-101), 16 000-atom P1 cells. Every
engine refuses or, worse, computes on a cell with two half-atoms in one
place. The pieces exist: `coincidence_warning`, `merge_duplicates`,
the interpenetration code's periodicity rank (which already separates
Ni₂Cl₂BTDD's 126 solvent molecules from the framework), `p1.expand`,
`niggli_reduce`.

**Steps.** (1) A report on open, beside the coincidence warning: *n split
sites, m solvent molecules, deuterium, no H, cell too big for X.*
(2) A Structure-menu dialog that offers, each as a separate undoable
command: keep the major occupancy component; drop molecules of
periodicity rank 0; D → H; primitive cell. (3) `Engine.__call__`
refuses a cell with partial occupancy the way it refuses a coincident
one, pointing at the dialog.

**Open questions.** Is dropping the minor component of a disorder the
right default, or should it be the component the user picks in the
viewport (the pies now draw it)? Should "prepare" write a new entry in
the workspace or edit in place? Does he want the missing-H case handled
(it is a real feature — adding H to carboxylates and μ-OH — or a refusal)?

### 3.4 Check on open, with charges — **M**, unlocked by EQeq

Idea 1 shipped its cheapest third (coincidence). The larger share of what
MOFChecker catches — charge imbalance, over/under-coordinated metals,
lone atoms, missing H — needs a charge estimate, and EQeq now provides
one in 0.5 s. *Open:* which checks are warnings on open and which live
in a dialog? MOFChecker's list is a starting point, not a spec.

### 3.5 Defects — **M**, was **L**, unlocked by the builder knowing its blocks

Idea 15 was "would require a definition of what the linker/nodes are".
A build now knows: `BuildRequest` names a block per node and edge type,
`structure.meta["mof"]` records the spelled recipe, and
`interpenetrate.py` shows the shape of a build parameter that edits the
placement. Missing-linker and missing-node defects on a *built*
structure are a per-instance omission — the same lever orientation
pulls through `permutations=`. *Open:* random at a fraction, or chosen
in the viewport? Should a defect's dangling connection points be capped
(with what — formate, water, OH?), and is that a build decision or a
prepare-for-simulation one (§ 3.3)? Does the built structure need to
carry block membership per atom (it does not today, as far as I can
see) for the viewport to offer "remove this linker"? Defects on an
*opened* structure still need deconstruction and stay **L**.

### 3.6 Multi-linker builds — **M**, unlocked by per-slot orientation

Idea 16's MFU-4l half shipped, and more than that: `BuildRequest` already
takes a different block per node *type* and per edge *type* (`0=N59`,
`0-1=E32`), so a net with two edge types builds with two linkers today.
What is missing is two linkers on **one** edge type — a block per
instance rather than per type, which is what orientation already does
for the *turn* of each instance through `permutations=`. *Open:* random
mixing at a ratio, ordered patterns (the checkerboard MFU-4l uses), or
both? How is the mix spelled in `meta["mof"]` and named in the
workspace?

### 3.7 A structure identifier for built structures — **S**, was blocked

PLAN.md 2.9 was blocked on deconstruction. A *built* structure does not
need deconstructing: `structure.meta["mof"]` already holds the spelled
recipe (`net + blocks per type + repeat + interpenetration`), and turning
that into a MOFkey-shaped string is `rcsr.describe()` for the net plus
RDKit's InChIKey for each block's SMILES. *Open:* is an identifier for
the builder's output only useful enough on its own, and does it survive
the user editing the structure afterwards (it should not — it is a
statement about a build, so it wants invalidating on the first edit)?

### 3.8 The chelate joint — **M**, the science question is now precise

His TODO names two options and rejects both. A third: keep the invariant
(a point 0.75 Å from its centroid) and change **where the two points are
fused**, not where each is written — the fuse distance becomes
`√(bond² − (half-bite)²)` from the pair's own geometry:
`√(1.294² − 0.57²) = 1.161 Å`, which matches his measured 1.16. Cost: the
builder consults a bond-length estimate. *Open:* which estimate
(covalent radii, UFF `r0`, the crystal's own value when the block was
cut)? `test_nihitp_builds_with_the_cell_the_crystal_has` pins 22.731 and
1.606 and has to move with a reason.

### 3.9 Energy units as a preference — **S–M**, was **M**

Was "no design work". Factoring phase 2 put every force-field number
through `xtal/ff/record.py`, so there is now one place to convert on the
way out and one `Param` to read. *Open:* kcal/mol stays the internal
unit (UFF's); is eV the display default for the ML engines, or one
preference for everything?

### 3.10 Scan resume — **M**, unlocked by `record.py`

His TODO: "A stopped scan cannot be carried on". `open_run`/`close_run`
now record every point in one shape, so resume is reading the run
folder back and skipping what is there. *Open:* resume into the same run
folder or a new one that references it?

### 3.11 LAMMPS data export — **M**, unchanged size, cheaper plumbing

`Registry` is generic and `Format` has `keeps`, so the registration is
cheap; the work is the file itself, and it still needs a decision on
which atom typing goes into it. *Open:* UFF types and parameters only
(what `xtal/ff/uff/typer.py` already assigns), or a choice?

### 3.12 RCSR transitivity — **S**, his own TODO

Vendor the r and s columns as JSON beside `rcsr-2019-06-01.json.gz` and
fill `NetFacts.transitivity`. No decisions.

### 3.13 Systre check for the `.cgd` writer — **S**, his own TODO

Run Systre once on MOF-5 and rutile, keep the output beside the tests.
Needs Systre installed (Java 8 is).

---

## 4. Still open from PLAN.md, nothing changed

- OPTIMADE dialog (idea 11), publication renders (19), glTF (20),
  RASPA3 input (18), conda-forge + `CITATION.cff` + Zenodo + JOSS (24),
  Dreiding/MZHB/ZIFFF (9, deprioritised), Zeo++ blocking spheres (10).
- Merge-duplicates preview pointing at Standardize — his TODO § Symmetry,
  and correctly left by our PR #4.
- Our review was wrong once: vector 3-D export (21) already existed
  (`svg_export.py`, 2026-09-04). Struck.

---

## 5. Suggested order

1. **§ 0.1 and § 0.2** — put the questions to Julius now; both are an
   afternoon of measurement each once answered. § 0.3 is one run on a
   machine with ORB.
2. **§ 2** — one branch, one PR, no decisions.
3. **The reaper and the test gaps** (§ 1, PR #2 and Tests) — ours to
   finish; no decisions.
4. **§ 3.3 Prepare for simulation** — the feature that makes his COD
   library usable, and the one every engine fix above is waiting on.
5. **§ 3.1, 3.2, 3.9, 3.10** — each small, each on a seam he just built.
6. **§ 3.5, 3.6, 3.7, 3.8** — the builder items, in that order; 3.8
   first if he takes the third option, because it moves a pinned number
   the others will build on.

---

## 6. Status — 2026-09-24, later the same day

**Review these as three PRs:** #21 engines and charges (the EQeq,
ORB, MatterSim, benchmark and MACE-MP-MOF0 rows below), #22
reliability (small fixes, orphaned programs, tests and CI), #23 nets
(transitivity, Systre).  They were first opened as ten (#10-#19) and
folded together with their commits unchanged; the branch names below
are those ten.

Ten branches off `main`, each its own PR.  All ten merged together in
order give 3605 passed, 0 failed, and `ruff check .` clean; the only
textual conflict between them is two adjacent `docs/TODO.md` deletions
(Systre and net-search).  Every scientific change was checked in a
scratch environment against the real package, never only in a stub.

| Hit list item | Branch | What happened |
|---|---|---|
| 0.1 EQeq centres | `fix/eqeq-charge-centres` | Every metal about its common oxidation state (agreeing with Open Babel's EQeq; the paper's seven kept, V +4); `centres=` override; impossible charges named with their cause.  Al-soc-MOF-1: Al +6.33 → +2.40.  MOF-5 now pinned against the **authors' own program**, compiled and run on the same cell: agreement 1.6e-4 e, test at 1e-3 catches a 0.8 % dielectric error the old ±0.05 missed. |
| 0.2 D3 | `fix/ml-benchmark-claims` | Measured: D3(BJ) moves ORB-v3's relaxed volume by −0.6 % (MOF-5) to −2.7 % (MOF-74), not always towards experiment.  Claims corrected; **the option and its default are Julius's call**. |
| 0.3 ORB precision | `fix/orb-double-precision` | Confirmed and fixed: float32 geometry into a float64 model (2e-3 → 6e-9).  **Correction to § 0.3 above:** it was not load-order dependent — current mace-torch restores the global dtype itself. |
| (new) MatterSim precision | `fix/mattersim-double-precision` | Found while checking 0.3: its default graph path builds positions in float32 and upcasts after (2.6e-3 → 5.6e-9 via its own `direct_graph`). |
| (new) MACE precision | — | Measured: true float64 (5.9e-9).  Nothing to fix. |
| 1 PR #9 stress guards | `fix/orb-…`, `fix/mattersim-…` | Real-model tests now sheared quartz with a slope check.  **Correction:** the `ASECalculator` conversion *was* guarded — the Lennard-Jones test's stress is 44 against a 1e-6 tolerance; only the real-model tests were weak. |
| 1 PR #9 deuterium | `fix/hitlist-small` | D is H at the engine door (Born–Oppenheimer: same surface), said in the run; MIL-53 now computes. |
| 1 PR #6 Find symmetry | `fix/hitlist-small` | Fixed; the cause was `setDefault` before the box joined the dialog. |
| 1 PR #6 dark-mode test | `fix/hitlist-small` | Fixed. |
| 1 PR #2 reaper | `fix/no-orphaned-programs` | Bigger than reported: Ctrl+C and SIGTERM on `xtal run` both orphaned the program.  Fixed, plus atexit reaper, non-blocking Stop, Windows taskkill failure logged. |
| 1 Tests | `test/hitlist-coverage` | Save As, `WorkspaceChooser.ask`, "a force field never changes the bonding", the D_f sentence, the modal guards, PySide6 cap; CI runs `--selftest` on macOS PRs and installs `sketch,pxrd`.  **Found on the way:** a stated bond order lost `stated` when an atom crossed a face, and the Inspector showed perception-time bond lengths (1.600 for a 0.990 bond) — both fixed. |
| 2 one-liners | `fix/hitlist-small` | `.gen` empty, `safe_name` accents (with old-spelling lookup), `--supercell` count.  **Dropped, measured:** read-only mkdir (the real doors already catch it), bond-type enabling (0.5 ms), CSSR `keeps` (nothing reads it), build/net cancellation (≤ 0.4 s). |
| 3.2 MACE-MP-MOF0 | `features/mace-mp-mof0` | Built.  **Correction to 3.2:** the custom-file path cannot load it — two heads, MACE will not guess.  Pinned by commit and SHA-256; 26 elements, refused by name otherwise; D3 already in it. |
| 3.12 RCSR transitivity | `features/rcsr-transitivity` | Built from the RCSR's own files; also corrects q on 18 nets. |
| 3.13 Systre | `test/systre-checks-cgd` | Systre names the exported MOF-5 net pcu and rutile rtl; kept as test data. |

**Left, each waiting on a decision:** D3 as an option and its
default; where the EQeq centre override lives in the panel; 3.3
prepare for simulation; 3.4 checks on open; 3.5 defects; 3.6
multi-linker; 3.7 identifier; 3.8 the chelate joint; 3.9 energy
units; 3.10 scan resume; 3.11 LAMMPS.  The factoring leftovers (tick
formatters, status-bar helper) were looked at and left: the heatmap's
format suits its coordinates, and the helper adds nothing a direct
call loses.
