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

The missing tips and help got rows at the top of the sheet
(2026-09-14, c90c6ea), and the sheet, `build/ui-text-2026-09.csv`,
went to the user the same day with the batch order: missing tips and
help; menus and toolbar; Preferences; Style; chooser; each dock;
dialogs; module and engine settings; status and error sentences.
**Waiting on the user's first batch.**  Then:

1. **Apply each batch as it comes back**: `--dry-run`, apply, fix the
   tests that quote old wording in the same commit, grab the windows
   touched and report anything clipped or newly scrolling, commit as
   *Reword the <window>*, re-extract.
2. **Close**: `reference.py` reports 0 commands and 0 settings
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
| M11 | Modules ▸ DFTB+ -- only after the postponed DFTB+ phase (§ 4) |

Each session regenerates the reference, builds with `-W` clean, and
reports its word count and open `TODO-cite`s.

---

## 2. An AI assistant drives the builder

Built 2026-09-26 on `claude/gallant-hawking-ml241m`, prompted by the
rietx skill: a protocol shipped in the wheel, over one typed API whose
answers carry coded diagnostics.  CLAUDE.md's invariant *An agent edits
through the same commands as a person* is the design.

It shipped: `xtal/agent/` (`Session`, `inspect`, `render`,
`capabilities`), the skill in the wheel, the `xtal` commands and
their `--json`.  **Still owed**, in this order:

- **A live link to the window**: a local MCP server inside a running
  window, turned on explicitly, whose tools are the same verbs over
  `Document.run` rather than a `Session` -- so the person watches each
  edit land as an undo step in the tab they have open.  The verbs need
  no change; what is new is marshalling every call onto the GUI thread
  and refusing while a trajectory plays.
- **A manual chapter**, *Working with an AI assistant*, once
  `docs/manual/` exists (Phase 4 above).

---

## 3. Substituted linkers: the builder's clashes, Substitute, counter-ions

Planned 2026-09-28.  Three gaps, one family:

- A linker with a group next to its connection point can build with
  atoms on top of the node, and the builder then bonds them.
- There is no command to put a group on a ring.  The route through the
  window, changing an H's element and adding atoms one at a time, cannot
  get past the first heavy atom of the group.
- There is none to put a charge-balancing ion beside each charged site
  of a framework: an anionic framework's cations, a cationic one's
  anions.

The full plan is `~/.claude/plans/substituted-linkers.md`.

**Measured before deciding.**  pcu on N16 (the Zn4O node MOF-5 is
built from), 1x1x1, with each linker made from SMILES through
`write_building_block` and built by `xtal.mof.build.build`:

| Linker | consistent (default) | as-found |
|---|---|---|
| BDC | 2.15 A | 2.15 A |
| 2-NH2, 2,5-Me2, 2-Br, 2-NO2 | 1.69-2.15 A, clean | 1.55-2.15 A, clean |
| 2-OMe | 1.34 A | 1.22 A |
| 2-tBu | 1.16 A | 1.25 A |
| 2-Ph | 0.98 A | 1.23 A, one H-H bond perceived |
| 2,5-(OMe)2 | **0.13 A**, two H bonded twice | 0.97 A, one H-H bond perceived |

Each value is the closest contact between atoms that are not bonded.

**The stray bonds are a symptom.**  `orient.align_edges` turns a
linker about its axis for face agreement alone, in closed form, and
never asks what the substituent lands on.  The CIF is then read back
and perceived by distance, which bonds whatever overlaps.  The verdict
line prints `closest contact 0.13 A` and nothing treats it as a
problem.

Decided:
- The twist is chosen by **clearance first, then faces**.
- A built framework's bonds are **its blocks' own and the joints'**,
  never perceived.
- Substitute works on **selected H atoms** and **one per ring**, and is
  also an **agent verb**.
- Counter-ions are **a mode of Fill Pores**.

The fragment library's Group category (`[*:1]C`) already has
attachment points, and `xtal/build/fill.py` already places guests
periodically, clash-tested and bonded to nothing, so phases 3 and 4
extend what is there.

| Phase | Delivers | Main files | Size |
|---|---|---|---|
| **1 — Overlaps are warnings; built bonds come from the blocks** | The stored graph is `_intra_block_bonds` plus the joints, written with `set_perceived` and never re-perceived (`Workspace.adopt_build` writes it with `perception=True`); pairs under 1.0 A are a warning naming the blocks, a `_check` row, and `BUILD_OVERLAP` for an agent | `xtal/mof/build.py`, `xtal/workspace.py`, `xtal/agent/diagnostics.py` | M |
| **2 — The twist that clears** | `align_edges` samples the angle every 10 degrees, keeps those within 0.1 A of the best clearance, and takes the one nearest the closed-form angle; `_turnable` admits a faceless block with atoms off its axis, which is the substituted linker under `as-found`.  The clearance margin lives in `xtal/build/clearance.py` for phase 4 | `xtal/mof/orient.py`, `xtal/build/clearance.py` | M |
| **3 — Counter-ions beside each selected atom** | `fill.place(..., anchors=, near=(3.5, 5.0))`: one guest per anchor, drawn from a shell around it, clear of everything and of each other; an anchor with no room named in the message.  The Fill Pores dialog gains the mode; `Session.fill_pores` (no fill verb exists yet) | `xtal/build/fill.py`, `xtalapp/document.py`, `xtalapp/dialogs/fill_pores.py`, `xtal/agent/session.py` | S-M |
| **4 — Substitute H with a group** | `xtal/build/substitute.py` plans placements (the group's attaching atom on the old C-H direction at `bond_distance`, turned for the most room); `SubstituteHydrogens` is one undo step that removes the H sites, adds the group with its own bonds and the bond to its carbon, perceiving nothing.  Right-click on H ▸ *Replace with group*, Structure ▸ *Substitute rings…*, `Session.substitute`.  Group fragments gain NH2, OH, OMe, NO2, F, Br | `xtal/build/substitute.py`, `xtal/commands/atoms.py`, `xtalapp/menus.py`, `xtal/build/data/fragments.json` | L |

Counter-ions go before Substitute: small before large, and neither
needs the other.

### Invariants these come near

- **"A linker's angle about its own axis"** changes: the closed form
  becomes the tie-break among clear angles.  What made it safe is
  unchanged -- both points are on the axis, so no angle moves the RMSD,
  the cell or an X-to-X coincidence -- and a block with nothing off its
  axis is clear at every angle, so BDC builds **byte for byte** as
  before.  Phase 2 rewrites the paragraph in CLAUDE.md.
- **Bonds only on Recalculate Bonds.**  Phase 1 makes a build keep it
  better: the builder's bonds become its statement, not a distance
  guess at read time.  A substitution arrives with its own bonds and
  the one to its carbon (`AddSites(perceive=False)`,
  `hold_perception`), and a counter-ion with none.
- **One batch per selection.**  Substituting every ring of a large
  framework is one command and one expansion; phase 4 measures it on
  MFU-4l.
- **Symmetry.**  Substituting a site substitutes its orbit, which is
  right for selected H atoms.  *One per ring* where a ring's H atoms
  are copies of one site cannot keep the group, so it reduces to P1
  inside the same undo step and says so, as `fill_pores` does.  Letting
  the ring itself turn -- which a bulky group next to a carboxylate
  needs -- moves atoms nobody selected, so it is an option and off by
  default.
- **An agent edits through the same commands**: `fill_pores`,
  `substitute` and `BUILD_OVERLAP` enter the shipped skill in the
  commits that add them.

### Tests, by phase

Every test runs on MOF-5 (`resources/samples/MOF-5.cif`), a pcu/N16
build, or a conftest fixture.

1. `tests/test_mof_builder.py`:
   - `test_a_built_framework_bonds_only_what_its_blocks_and_joints_bonded`
     (2,5-dimethoxy-terephthalate on pcu/N16)
   - `test_an_overlapping_build_says_so_as_a_warning`
   - `test_a_clean_build_carries_the_same_bonds_perception_would`
2. `tests/test_mof_orientation.py`:
   - `test_an_ortho_substituted_linker_is_turned_clear_of_the_node`
     (2,5-dimethoxy and 2-phenyl, at least 1.5 A)
   - `test_an_unsubstituted_linker_turns_exactly_as_before` (Ni3(HITP)2
     still 6e-08 rad)
   - `test_clearance_breaks_ties_the_faces_cannot`

   `test_mof_vendored.py`'s upstream comparison stays green.
3. `tests/test_fill.py`, with Na+ beside selected O atoms:
   - `test_one_guest_is_placed_beside_each_anchor`
   - `test_a_guest_beside_an_anchor_bonds_to_nothing`
   - `test_an_anchor_with_no_room_is_named_not_skipped`
   - `test_guests_beside_anchors_keep_clear_of_each_other`

   `tests/test_fill_ui.py`: the mode greys the count and needs a
   selection.
4. `tests/test_substitute.py`, on MOF-5:
   - `test_a_substituted_hydrogen_becomes_the_group_bonded_to_its_carbon`
   - `test_a_substitution_is_one_undo_step_and_undo_restores_the_graph`
   - `test_one_per_ring_puts_exactly_one_group_on_every_ring`
   - `test_the_group_is_turned_to_the_angle_with_the_most_room`
   - `test_substituting_in_a_symmetric_cell_substitutes_the_orbit`
   - `test_one_per_ring_in_a_group_that_ties_the_ring_reduces_to_p1_and_says_so`
   - `test_nothing_is_perceived_the_group_bonds_only_as_built`

   `tests/test_substitute_ui.py`: the entry is enabled only on H,
   through a patched `menus.popup`.

### Done when

- The pcu/N16 table reruns with every linker at 1.5 A or more under
  both orientations, and BDC unchanged.
- In the window: MOF-5, *Substitute rings…* with NH2 one per ring,
  gives IRMOF-3's composition with every N bonded to its ring.
  Selecting atoms and choosing Fill Pores ▸ *one beside each selected
  atom* places one ion each, with no bond to anything.
- Then CLAUDE.md's builder invariants, docs/MENUS.md and the
  MOF-builder and editing chapters of the manual are brought up to
  date.

---

## 4. What this plan does not do

* It does not touch the design principles in
  [docs/PLAN.md](PLAN.md) § 1.  Every phase keeps the core Qt-free,
  keeps every mutation a command, and adds capability through
  registries.
* It does not schedule volumetric data or SHELX round-trips.  Those
  are [docs/PLAN.md](PLAN.md) § 12 and stay there until they are asked
  for.  Rietveld was asked for, and has shipped.
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
