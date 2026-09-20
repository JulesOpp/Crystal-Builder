# Crystal Builder — delivery plan for the TODO

[docs/PLAN.md](PLAN.md) is the architecture and the roadmap that got
the application built; [docs/TODO.md](TODO.md) is everything that came
out of using it and has never been scheduled.  This file schedules it:
what order, what each phase delivers, and what it is allowed to touch.

Every phase ends with something runnable and a green suite, which is
the same rule [docs/PLAN.md](PLAN.md) § 16 works to.  Sizes are orders
of magnitude, not estimates: **S** is a day or less, **M** a few days,
**L** a week or more.

A phase ships and its entries are deleted from
[docs/TODO.md](TODO.md); a phase that has shipped is deleted from here.
What follows is everything still owed.

---

## 1. The order

The interface stretch, planned 2026-09-13: one phase per session, in
this order, because each one changes what the next one photographs,
names or links to.  Phases 1 and 2 change what is on screen and what it
is called; phase 3 anchors help to those names, and phase 4 writes and
photographs them.  The full plan, with its measurements, is
`~/.claude/plans/interface-stretch.md`; the sections below are enough to
start a phase from its name.

| Phase | Delivers | Main files | Size |
|---|---|---|---|
| **Phase 2 — Text pass** | Every visible string in the user's own words, missing tips and help first | `.claude/skills/ui-text/uitext.py`, then the app a window at a time | M |
| **Phase 3 — Help is the manual** | A "?" on every panel and dialog opening the manual at its anchor; the manual's skeleton and generated reference | `xtalapp/help_links.py`, `.claude/skills/manual-writing/reference.py`, `packaging/bundle.py` | M |
| **Phase 4 — User manual** | The manual, one chapter (or page group) per session, M0-M11 | `docs/manual/` | L |

Phase 1 (Styles, Preferences and the chooser) shipped on 2026-09-14;
`git log -- docs/ROADMAP.md` has what it delivered.  **Before each
phase**: commit or stash what the last session left uncommitted, so
each phase's diff is only its own.

Every phase runs targeted test files while iterating and the full suite
once, in the background, with `sysctl vm.swapusage` looked at first.

---

## Phase 2 — Text pass

The user rewrites the text; this phase is the plumbing either side.
**No string is reworded by us.**  Phase 1 has landed, so its new
strings -- the Style groups, the Engines page, the chooser -- are in
the sheet.

1. ~~Missing text gets rows~~ -- done 2026-09-14 (c90c6ea).  The
   sheet has **33** `tip= (missing)` and **17** `help= (missing)`
   rows at the top: the 12 module settings planned, plus five engine
   options (xTB and DFTB+ charge and iteration limits), which
   `reference.py` now counts too.  `where` names them as
   `key (label)` or `TABLE.param (label)`, not `module.action.param`,
   because extract never imports.
2. ~~Hand over the sheet~~ -- `build/ui-text-2026-09.csv`, 1316 rows,
   given to the user 2026-09-14 with the batch order: missing tips and
   help; menus and toolbar; Preferences; Style; chooser; each dock;
   dialogs; module and engine settings; status and error sentences.
   **Waiting on the user's first batch.**
3. **Apply each batch as it comes back**: `--dry-run`, apply, fix the
   tests that quote old wording in the same commit, grab the windows
   touched and report anything clipped or newly scrolling, commit as
   *Reword the <window>*, re-extract.
4. **Close**: `reference.py` reports 0 commands and 0 settings
   missing; `docs/MENUS.md`
   updated; full suite once.

Registry keys and `Param` names never change: phase 3's anchors are
built from them.

---

## Phase 3 — Help is the manual

The help a "?" opens is the manual's own content, never a second copy.
Decided with the user: the **Sphinx HTML is built into the bundle and
opened in the system browser** at the anchor; a panel's "?" is a
**small flat button at the top right of its contents**, plus F1;
dialogs get `QDialogButtonBox.Help`.

1. **Skeleton.**  Ask before `pip install sphinxcontrib-bibtex furo`
   (Sphinx 8.2.3 and MyST 5.1.0 are present).  `docs/manual/conf.py`,
   `index.md`, stubs for the agreed outline, empty `references.bib`,
   the generated `reference/`; `sphinx-build -W` clean.
2. **One list of topics.**  `xtalapp/help_links.py` `TOPICS` maps
   every dock (`panel-<attr>`), every dialog with a Help button
   (`dlg-<key>`, including Preferences pages) and every module action
   (`mod-...`) to its anchor.  `reference.py` reads it and writes
   `reference/dialogs.md`, so an anchor the app opens is one the
   generator wrote.
3. **Opening it.**  `open_help(parent, anchor)` finds the built manual
   (`_internal/docs/manual/html` in a bundle, `build/manual/html` in a
   checkout), maps the anchor to its page through
   `reference/inventory.json`, and opens `file://...#anchor`.  With no
   built manual it opens `HelpWindow` and scrolls to the same anchor,
   which its generated pages now carry, plus a Panels tab.
4. **Buttons.**  `docks.help_corner(dock, anchor)` is an overlay that
   adds nothing to any minimum; dialogs connect `helpRequested`; a
   registry action `help_on_panel` on F1.  `bundle.py` requires the
   built manual and ships it.
- Tests (`tests/test_help_links.py`): `test_every_dock_has_a_help_topic`,
  `test_every_help_topic_is_an_anchor_the_reference_wrote`,
  `test_help_opens_the_built_manual_at_the_anchor`,
  `test_without_a_built_manual_help_scrolls_the_generated_window_there`,
  `test_the_help_corner_adds_nothing_to_a_panel_s_minimum`,
  `test_f1_opens_help_for_the_panel_with_focus`,
  `test_a_dialog_s_help_button_opens_its_own_topic`;
  `test_the_generated_help_carries_the_manual_s_anchors`
  (`test_help_ui.py`); `test_a_bundle_carries_the_built_manual`
  (`test_packaging.py`).
- Docs: CLAUDE.md gains the invariant *help is the manual*
  (`TOPICS` is the one list, anchors are registry keys); the
  manual-writing, add-action and add-module skills say a new panel or
  dialog needs a topic; `PACKAGING.md` says the manual is built first.

---

## Phase 4 — User manual

Written with the `manual-writing` skill, which holds the outline, the
layout, the screenshot script and the style.  One session each; a
top-level chapter too large for one session is split by page.
Installed first: phase 3's toolchain.  TeX is at `/Library/TeX/texbin`
(check `latexmk` in M0).  `ase`, `rdkit`, `rdeditor`, `mace` and
`matplotlib` import; DFTB+ 24.1 and tblite are on PATH; **xTB is not**,
so ask in M6 whether GFN-FF gets figures.

| Session | Delivers |
|---|---|
| M0 | `tutorial_check.py` proving the MIL-88b build (acs, N134, drawn `*c1ccc(*)cc1`; UFF4MOF, relax cell, Smart; P6₃/mmc; acs, then ssa) and the `shots.py` skeleton.  No prose; a wrong answer stops the session. |
| M1 | Quickstart ▸ Your first crystal build |
| M2 | Quickstart ▸ About, Installation, The GUI |
| M3 | Essentials ▸ File, Edit, Select |
| M4 | Essentials ▸ Structure, Symmetry, Cell |
| M5 | Essentials ▸ Measure, View, Window, mouse modes, shortcuts |
| M6 | Modules ▸ Force field (UFF/UFF4MOF, xTB, MACE) |
| M7 | Modules ▸ Zeo++, PXRD |
| M8 | Modules ▸ MOF builder, Molecule builder, Net builder |
| M9 | Modules ▸ Energy scan (landscapes, held coordinates, reading a heat map), Blender export; Quickstart ▸ Recommendations, Troubleshooting |
| M10 | Front matter, Glossary, Bibliography, Index, PDF |
| M11 | Modules ▸ DFTB+ -- only after the postponed DFTB+ phase (§ 2) |

Each session regenerates the reference, builds with `-W` clean, and
reports its word count and open `TODO-cite`s.

---

## 2. The MOF builder: polydentate connections and orientation

Planned 2026-09-20 on `features/mof-polydentate`, from Julius's four
block definitions.  The full plan is
`~/.claude/plans/read-through-the-discussions-validated-floyd.md`.
Targets: **MFU-4l** first, then **Ni3(HITP)2**; Cu-HHTP by hand.
**No vendored file is edited** — every lever already exists in
PORMAKE's public API, so `xtal/mof/pormake/PROVENANCE.md` stays a
clean diff against upstream 0.2.3.

| Phase | Delivers | Main files | Size |
|---|---|---|---|
| **1 — Probes** | Shipped 2026-09-20; numbers below | `probes/polydentate/` | S |
| **2 — The verdict** | Shipped 2026-09-20; a build reports what it measured, never a symmetry it did not check | `xtal/mof/build.py`, `xtal/modules/mof.py` | S |
| **3 — Attachments** | A connection point may stand for several atoms; *Mark as one connection point* | `xtal/mof/block.py`, `xtal/mof/catalog.py`, new `xtal/mof/attach.py`, `xtal/commands/connections.py` | M |
| **4 — Joints** | Every member of a polydentate end arrives bonded | `xtal/mof/build.py` | M |
| **5 — Node orientation** | The discrete tie-break, through `permutations=` | new `xtal/mof/orient.py`, `xtal/mof/build.py` | M-L |
| **6 — Linker orientation** | The continuous axial angle, in closed form | `xtal/mof/orient.py` | M |
| **7 — MFU-4l** | The four blocks shipped; MFU-4l built end to end | new `xtal/mof/library/`, `packaging/bundle.py` | M |
| **8 — Layer nets** | 2-periodic nets with a stacking spacing; Ni-HITP | new `xtal/mof/library/nets/` | M |
| **9 — Interpenetration** | Generated and verified against `Net.multiplicity()` | new `xtal/analysis/interpenetrate.py` | M-L |

### What Phase 2 changed

`BuildOutcome.verdict()` said `the framework is pcu, as asked` and
stopped, which reads like a pass and was true of a build with none of
MFU-4l's chlorides and a fifth of its atoms.  It now carries the fit,
the closest contact and the joint count, and it still says nothing
about the shape of the cell -- a test pins that, because the review's
own proposal (*"the relaxed cell is triclinic where pcu is cubic"*)
would fire on DMOF-1 and MIL-53.

The new measurement is `xtal.mof.build.closest_contact`: the shortest
distance between two atoms that are **not** bonded.  The plain
minimum was measured first and discarded -- it is the C-H bond every
time, 0.930 A in `MFU4l.cif`'s own refinement and 0.930 A in a
framework built out of it, so it separates nothing.  The unbonded
minimum does: every framework in `resources/samples` sits between
**1.996 A** (Ni3(HITP)2) and **2.170 A** (UiO-66), while `acs` built
on `N457` -- blocks that do not fit that net -- sits at **1.662 A**.
No threshold is applied: the bands are close enough that a constant
would be a guess, and `zn_oac.cif`, a molecular crystal, sits at 1.806
between them.  It costs 3-89 ms, the worst on Ni2Cl2BTDD's 1152 atoms.

Two shipped samples answer **0.000 A** -- `CFA1.cif` and
`Ni2Cl2BTDD.cif` -- which independently reproduces the coincident-atom
finding in `features/deep-review` item 1.2, from a different direction.

### What Phase 1 measured

Ten probes, all under `probes/polydentate/`.  The three that could
have killed the design did not.

* **The objective works, and its cost must compare directions, not
  offsets.**  One Zn5Cl4(N3C2)6 node scored against all 24 rotations
  that leave its six connection directions alone: the crystal's own
  orientation is a minimum, **12 of the 24 tie** (the T_d body's own
  rotations), so there are exactly **2 distinct orientations** — the
  measured flip, derived rather than observed.  Comparing raw lateral
  offsets leaves a floor of 0.53 A^2 that is nothing but the span
  difference (node members 1.405 A, linker members 2.861 A);
  normalising them to directions first gives **exactly 0.000000 for
  the crystal and 2.000000 for a 90-degree twist**.  On Ni3(HITP)2 the
  closed form `phi* = -arg(sum z_e conj(z_n))` returns **0.000 deg**,
  the experimental angle, with no scan.
* **The permutation lever moves the body.**  Over the 24 candidates
  the RMSD spread is 6.2e-08 while the body moves up to **8.239 A**,
  in **2 placements of 12** — and against the *scaled* topology the 24
  still stand at 2.2e-06 to 8.3e-06 while everything else starts at
  0.8165, a **98,189x** separation.
* **The tie set is enumerable.**  `|G| = 24` from **120** Kabsch-on-
  triples candidates rather than 720 permutations, and composed with
  the baseline it **equals the brute-force tie set exactly**.  Two
  tolerances are not cosmetic: the group search needs **1e-3**, not
  1e-6, because a block cut from a real crystal is octahedral to a
  thousandth of a degree; and the tie criterion must be **gap-based**,
  not an absolute epsilon, because the block's own imperfection
  (~1e-5) is larger than any fixed threshold worth writing.
* **Unmodified PORMAKE reads a polydentate block and builds with it.**
  All four blocks load with two bonds per X and a silent
  `check_bonds`, and `pcu` comes out as **Zn5Cl4N18C36O6H12 — exactly
  MFU-4l's formula unit — in a cubic cell, 16.136 A, at max_rmsd
  0.000002**.  (The catalogue's own N457 gives 77 atoms, no chlorides
  and a triclinic 81.0/99.4/100.2 cell.)  Of its 100 bonds, 94 are
  intra-block and **6 are joints where 12 are needed** — one per
  joint, exactly the `builder.py:644-658` defect, which Phase 4
  repairs from our side.
* **Members must be the *distinct* partners of an X.**  No shipped
  block is polydentate by design, but **54 connection points carry
  more than one bond record** and 52 of those name the same partner
  twice, across **26 blocks**.  Counting records rather than partners
  would take 26 shipped blocks down the new path.  Two more — `N484`,
  whose X is bonded to a **hydrogen**, and `N684`, whose X sits 1.201
  and 0.613 A from its two partners against a `CONNECTION_DISTANCE` of
  0.75 — are upstream data errors.  They are **not** separable by a
  geometric tolerance (N684 sits 0.703 A from its members' centroid
  against our 0.750), so Phase 3 records them in a test rather than
  tuning a threshold to 0.047 A.
* **A supercell is cheap and our own code survives it.**  `pcu` x
  (2,2,2): 32 slots, 8 nodes, **648 atoms — MFU-4l's own P1 count — in
  0.03 s**, with `_edges_of` giving 24 edges and `_representatives` 8
  node slots, matching the crystal's 24 linkers and 8 SBUs.
* **A layer net does *not* keep its stacking axis, and that was
  predicted wrong.**  The scaler applies a global factor, so `hcb`'s
  c went 10 -> **107.154**.  The layer is flat to **0.0000 A**, so
  Phase 8 sets c *after* the build; doing that gives
  `[22.730, 22.731, 3.238, 90, 90, 120]` against the crystal's
  `[21.552, 21.552, 3.238, ...]`.  The build itself is already
  **75 atoms, C36H24N12Ni3** — exactly Ni3(HITP)2.
* **Idealised geometry costs a few percent.**  a is +3.9% on MFU-4l
  and +5.5% on Ni-HITP, which is what a builder that places blocks and
  stops is worth.  Relaxation is the user's, in the Force Field panel.
* **The mirror hazard did not fire** on these blocks (0 mirrored
  placements over `pcu` and `acs`) because the fit is near-exact, so
  the 1% chiral retry is never reached.  The guard stays: the sample is
  two nets.
* **Rewriting a placed block's positions before `write_cif` is safe** —
  file written, atom order unchanged, longest bond 2.607 A against the
  6.0 A ceiling that would have deleted the file.

---

## 3. What this plan does not do

* It does not touch the design principles in
  [docs/PLAN.md](PLAN.md) § 1.  Every phase keeps the core Qt-free,
  keeps every mutation a command, and adds capability through
  registries.
* It does not schedule volumetric data, SHELX round-trips or Rietveld.
  Those are [docs/PLAN.md](PLAN.md) § 12 and stay there until they are
  asked for.
* It does not schedule the relaxed scan: that was asked for and built
  on 2026-09-15, outside this plan, and is
  [docs/PLAN.md](PLAN.md) § 12a.  What it left undone is in
  [docs/TODO.md](TODO.md) § Scans, and M9 now has a chapter for it.
* It postpones **DFTB+ — split, then merge**; it is not dropped.  The
  manual's DFTB+ chapter (M11) waits for it, because writing it first
  would photograph panels that phase changes.
* It does not try dragging a panel with a real mouse
  ([docs/TODO.md](TODO.md) § Interface); that needs a person's pointer.
  Phase 3 leaves every dock title bar as Qt draws it, so as not to make
  it worse.
