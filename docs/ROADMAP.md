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
| **Phase 1 — Styles, Preferences and the chooser** | Style panel in headed, reflowing groups; Preferences without stale settings and with one Engines page; a chooser with a side panel and Open Sample; the net preview turns; the status-bar message | `xtalapp/docks/style_panel.py`, `xtalapp/dialogs/preferences.py`, `xtalapp/dialogs/workspace_chooser.py`, `xtalapp/dialogs/mof_preview.py` | L |
| **Phase 2 — Text pass** | Every visible string in the user's own words, missing tips and help first | `.claude/skills/ui-text/uitext.py`, then the app a window at a time | M |
| **Phase 3 — Help is the manual** | A "?" on every panel and dialog opening the manual at its anchor; the manual's skeleton and generated reference | `xtalapp/help_links.py`, `.claude/skills/manual-writing/reference.py`, `packaging/bundle.py` | M |
| **Phase 4 — User manual** | The manual, one chapter (or page group) per session, M0-M11 | `docs/manual/` | L |

**Before phase 1**: commit or stash what the last session left
uncommitted, so each phase's diff is only its own.

Every phase runs targeted test files while iterating and the full suite
once, in the background, with `sysctl vm.swapusage` looked at first.

---

## Phase 1 — Styles, Preferences and the chooser

Six steps, one commit each.  If the session runs short, the break is
after 1.4; 1.5 and 1.6 carry over unchanged.  **Take before-and-after
grabs of every panel and dialog touched** (`run-app --scratch DIR
--grab ...`) and show them side by side.

Measured when planning: the Style panel's contents are 406 × 747
(minimum 406 × 629) on MOF-5, one column; two columns need about 460 px;
the right-hand column opens at 515 px.  The chooser is 460 × 382.

Decided with the user:

1. The Style panel **reflows**: two columns when there is room, one
   below it, never a horizontal scroll bar.
2. Depth cue is **collapsible, collapsed unless on** for the document;
   a click holds until the document changes.
3. Preferences **drops** "Make a workspace beside a structure opened
   without one" and the redraw rate (the calculation panels keep it).
4. External tools and Optional features become one **Engines** page,
   with a **Test** button per row that really runs the program.
5. The two PORMAKE folders go in a closing "Your own nets and blocks"
   group on that page.
6. Chooser: a **left side panel** (icon, name, version, a framework
   picture that is a **shipped PNG**), and **Open Sample** into the
   **selected** workspace.
7. Out-of-date text is corrected for fact only; the replacement
   sentence is shown to the user before it is committed.

### 1.1 Style panel in headed groups

- `StylePanelDock._build_global` splits into one `QGroupBox` per
  group: **Drawing** (style, atom size, bond radius, ellipsoids +
  octants), **Transparency** (polyhedra, pores), **Scene** (background,
  labels, legend), **Show** (cell, axes, net, all pore nodes),
  **Colours** (the `FLAT_COLORS` swatches), **Depth cue** (switch, the
  three `PercentControl`s, `CuePreview`).  Every attribute name stays,
  so `test_appearance_ui.py` does not change; everything still writes
  through `Document.update_view`.
- New `xtalapp/docks/columns.py`: `ReflowColumns` (two columns when
  `width()` allows, else one; `minimumSizeHint` is the one-column
  minimum; height-for-width) and `Collapsible` (arrow header + body).
- The element table and Reset go last, full width, at a fixed eight
  rows that scroll inside the table.  The dock uses `docks.scrolling`.
- Keeps *a panel never holds its column open*.
- Tests (`test_appearance_ui.py`):
  `test_the_style_panel_is_headed_groups_in_the_agreed_order`,
  `test_a_wide_style_panel_puts_its_groups_side_by_side`,
  `test_a_narrow_style_panel_stacks_its_groups_instead_of_scrolling_sideways`,
  `test_depth_cue_opens_itself_for_a_document_that_has_it_on`,
  `test_the_element_table_keeps_its_height_when_the_panel_grows`.

### 1.2 The status-bar message

- Planning did **not** reproduce the overprint: after opening MOF-5
  twice, `status_label` is hidden while the message shows and a
  status-bar grab is clean.  Try the TODO's route with a whole-window
  `--shot`, and across a tab switch.  Overprints: `show_message` shows
  its text in the summary's place and restores the summary on a
  single-shot timer
  (`test_a_passing_message_replaces_the_summary_and_then_gives_it_back`).
  Does not: delete the TODO entry, naming the routes tried.
- Either way, fix what the same route did show: "MOF-5.cif is already
  open, as MOF-5.cif".  `DocumentSet.open_path` compares resolved paths
  and the tab follows the workspace copy; add "as {title}" only when the
  title differs from `path.name`
  (`test_reopening_a_file_does_not_name_a_tab_spelled_the_same`).

### 1.3 Preferences: what is out of date

- Remove `auto_workspace` (page checkbox, `AppSettings` property, and
  the branch in `WorkspaceShell._offer_workspace`, keeping its
  message).  Keeps *the degraded window survives*.
- Remove the "While a calculation runs" box and the page's and dialog's
  `previewIntervalChanged`; the Force Field and DFTB+ combos stay.
- Correct two facts: the Saving hint on conversion to a project, and
  the `mof/bb_dir` hint ("where Save as a building block writes" -- it
  writes to `<workspace>/blocks/`).
- Tests: delete the two tests of the removed controls (check
  `test_ff_ui.py` covers the redraw rate);
  `test_a_structure_opened_with_no_workspace_says_so_and_makes_none`,
  `test_preferences_has_no_second_redraw_control`.

### 1.4 The Engines page

- `EnginesPage` replaces `ExternalToolsPage` and `OptionalFeaturesPage`:
  **Programs** (Zeo++; DFTB+ with waveplot, modes and the Slater-Koster
  folder; tblite; xTB; Blender), **Python packages** (`extras.EXTRAS`
  and the frozen build's packages box), **Your own nets and blocks**.
- Test, headless: `xtal/modules/probe.py` says how each program is
  asked and what counts as found.  Measured: `tblite --version` exits 0
  in 0.01 s; `dftb+`, `waveplot` and `modes` take no `--version`, and
  run in an empty directory they print a banner (`DFTB+ release 24.1`)
  and exit 1; `network` with no arguments prints its usage and exits 0;
  `Blender --version` takes **3.2 s**; an extra is `import` in a
  subprocess (0.36 s), or a `--selftest-import` entry in a frozen build.
- Test, Qt: runs through **`QProcess`**, never `start_in_thread` (the
  `workers.py` deadlock), button disabled while it runs, the first
  useful lines or the error shown under the status line.
- Update the old page names in `menus.py`, `external.py`,
  `selftest.py`, `RELEASE_NOTES.md`, `PACKAGING.md`, `test_extras.py`.
- Tests: `tests/test_probe.py`
  (`test_a_dftb_banner_counts_as_found_whatever_the_exit_code`,
  `test_tblite_is_asked_its_version`,
  `test_a_probe_that_times_out_says_so_rather_than_found`,
  `test_a_missing_binary_is_named_not_found`); `test_preferences.py`
  (`test_every_tool_and_extra_has_a_row_on_the_engines_page`,
  `test_a_test_button_reports_what_the_program_printed`,
  `test_a_test_button_is_disabled_while_its_probe_runs`).

### 1.5 The workspace chooser

- A 220 px left side panel: `packaging/icons/app.svg`, the name,
  `xtal.__version__`, and `resources/chooser/framework.png`, made by
  `packaging/render_chooser_art.py` (a run-app script, scratch profile,
  `viewport.save_image`) and added to `bundle.py`'s travelling
  subtrees.
- Recent rows on one line (name bold, then time and folder muted)
  through a delegate; the path still elides in the middle.
- **Open Sample** menu button: `ask` returns `(workspace, sample)` and
  `xtalapp/main.py` calls `open_sample` once the window exists.  The
  chooser stays out of `MainWindow.__init__`; the sample is copied in
  like any other.  Disabled, with `samples.MISSING`, without samples.
- Tests (`test_workspace_chooser.py`, never `exec`ed):
  `test_a_recent_workspace_is_one_line_with_its_name_first`,
  `test_the_chooser_shows_the_version_it_will_open`,
  `test_open_sample_opens_the_selected_workspace_and_names_the_sample`,
  `test_open_sample_on_a_folder_that_cannot_be_made_keeps_asking`,
  `test_open_sample_is_disabled_without_the_samples`,
  `test_main_opens_the_sample_the_chooser_returned`; the existing
  `test_return_continues_rather_than_quitting` must still pass.

### 1.6 The net preview turns

- `NetPreview` keeps a 3×3 rotation, turned by drag (one radius to the
  radian, as Move's alt-drag) and reset by double-click and a Reset
  view button in `mof_build.py` and `net_draw.py`.  `_project` takes
  the view; `BlockPreview` is unchanged.  The fit is the bounding
  sphere, so turning does not rescale.  Still `QPainter`.
- Tests (`test_mof_ui.py`): `test_dragging_the_net_preview_turns_it`,
  `test_double_clicking_the_net_preview_puts_it_back`,
  `test_turning_the_net_does_not_rescale_it`,
  `test_a_new_topology_starts_from_the_default_view`.

### Verification and docs

Grabs, before and after: the Style dock at 520 × 900 and 220 × 900,
each Preferences page, the chooser, the MOF builder's net preview at
three angles, the whole window after a second open.  Test on DFTB+
reads "DFTB+ release 24.1".  TODO: delete the net-preview entry and the
status-bar entry.  CLAUDE.md: the column invariant names
`ReflowColumns`; the chooser invariant says Open Sample returns through
`ask`.

---

## Phase 2 — Text pass

The user rewrites the text; this phase is the plumbing either side.
**No string is reworded by us.**  Start it after phase 1 has landed,
so the new strings are in the sheet.

1. **Missing text gets rows.**  The reference generator reports **33
   commands with no tip** and **12 settings with no help** (11 DFTB+,
   one Blender), and a tip that does not exist has no row in the sheet.
   `uitext.py extract` emits `tip= (missing)` for a registry `add(...)`
   with no `tip=` and `help= (missing)` for a `Param` with no `help=`,
   sorted to the top; `apply` inserts the keyword.  Tests beside the
   skill: `test_a_command_without_a_tip_gets_a_missing_row`,
   `test_applying_a_missing_tip_inserts_the_keyword`,
   `test_missing_rows_come_first`.
2. **Hand over the sheet**
   (`uitext.py extract -o build/ui-text-2026-09.csv`) with the skill's
   instructions and a batch order: missing tips and help; menus and
   toolbar; Preferences; Style; chooser; each dock; dialogs; module and
   engine settings; status and error sentences.
3. **Apply each batch as it comes back**: `--dry-run`, apply, fix the
   tests that quote old wording in the same commit, grab the windows
   touched and report anything clipped or newly scrolling, commit as
   *Reword the <window>*, re-extract.
4. **Close**: `reference.py` reports 0 missing; `docs/MENUS.md`
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
| M9 | Modules ▸ Blender export; Quickstart ▸ Recommendations, Troubleshooting |
| M10 | Front matter, Glossary, Bibliography, Index, PDF |
| M11 | Modules ▸ DFTB+ -- only after the postponed DFTB+ phase (§ 2) |

Each session regenerates the reference, builds with `-W` clean, and
reports its word count and open `TODO-cite`s.

---

## 2. What this plan does not do

* It does not touch the design principles in
  [docs/PLAN.md](PLAN.md) § 1.  Every phase keeps the core Qt-free,
  keeps every mutation a command, and adds capability through
  registries.
* It does not schedule volumetric data, SHELX round-trips or Rietveld.
  Those are [docs/PLAN.md](PLAN.md) § 12 and stay there until they are
  asked for.
* It postpones **DFTB+ — split, then merge**; it is not dropped.  The
  manual's DFTB+ chapter (M11) waits for it, because writing it first
  would photograph panels that phase changes.
* It does not try dragging a panel with a real mouse
  ([docs/TODO.md](TODO.md) § Interface); that needs a person's pointer.
  Phase 3 leaves every dock title bar as Qt draws it, so as not to make
  it worse.
