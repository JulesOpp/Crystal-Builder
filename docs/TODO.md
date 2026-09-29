# TODO

Everything still owed, in one place: the work that is scheduled, in
the order it is to be done, and then everything that came up while
using the application and has not been scheduled.
[docs/PLAN.md](PLAN.md) holds the architecture and the phases that
built it.  An entry is **deleted when it ships, not ticked**; a
scheduled phase that ships is deleted with it.  What shipped is in
`git log -- docs/TODO.md docs/ROADMAP.md` (the roadmap was folded in
here on 2026-09-28).

Sizes are orders of magnitude, not estimates: **S** is a day or less,
**M** a few days, **L** a week or more.  Every phase ends with
something runnable and a green suite, the rule
[docs/PLAN.md](PLAN.md) § 16 works to.

---

# Scheduled

## The interface stretch

Planned 2026-09-13: one phase per session, in
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

### Phase 2 — Text pass

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

### Phase 3 — Help is the manual

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

### Phase 4 — User manual

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
| M11 | Modules ▸ DFTB+ -- only after the postponed DFTB+ phase (*What is deliberately not scheduled*, at the end) |

Each session regenerates the reference, builds with `-W` clean, and
reports its word count and open `TODO-cite`s.

---

## An AI assistant drives the builder: what is still owed

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
  `docs/manual/` exists (interface stretch, phase 4).

---

## The TODO of 2026-09-26 and 2026-09-28

Planned 2026-09-28 on `features/todo-0928`, after the substituted
linkers (A1-A4), which shipped first and are in `git log`.  The full plan, with its measurements, is
`~/.claude/plans/make-a-plan-to-structured-treasure.md`.  Six entries
that were unscheduled, moved here with Julius's answers; *No Close
All* was dropped, because `close_all_tabs` (Ctrl+Shift+W) has existed
since 2026-09-08.

| Phase | Delivers | Main files | Size |
|---|---|---|---|
| **C3 — Save as a building block goes to `blocks/`** | The folder Draw writes to, and no write-back to `mof_bb_dir` | `xtalapp/dialogs/save_block.py`, `xtalapp/edit_actions.py` | S |
| **B4 — Zeo++ from GitHub** | Measured against the reference, then found beside 0.3 or replacing it | `xtal/modules/zeopp.py` | S-M |

### C3 — One folder for blocks

Cutting a node out of a crystal -- the manual's recipe, which since C1
and C2 (2026-09-28) centres a cluster a face cuts through with *Cell ▸
Move origin…* -- ends by saving it as a building block.

*Draw…* in the MOF builder writes to `<workspace>/blocks/`; *Save as a
building block…* defaulted to `settings.mof_bb_dir` and would not save
until a folder was typed.  Decided: it defaults to `blocks/` and no
longer writes `mof_bb_dir` back.

### B4 — Zeo++ from its GitHub source

The Porosity module looks for one program, `network` (`XTAL_ZEOPP`,
Preferences, PATH, then `resources/zeo++-0.3/network`).  Zeo++ 0.3 is
built by hand, and has faults this application works around:
`-gridGAI` aborts on MFU-4l, and `-gridG` writes nothing.

The candidates:
- [lsmo-epfl/zeopp-lsmo](https://github.com/lsmo-epfl/zeopp-lsmo),
  the maintained fork, on conda-forge as `zeopp-lsmo` and still a
  `network` binary.
- [nomad-coe/pyzeo](https://github.com/nomad-coe/pyzeo), bindings with
  wheels.

Measure each in a scratch environment against
`tests/data/zeopp_reference.json` and the two faults, and check that
`porosity.ZEO_RADII` matches what it compiles in.  Then either have
`binary()` find either one, saying which in the greyed entry and
Preferences ▸ Engines, or replace 0.3.  Bindings only if the numbers
favour them clearly.

---

# Not scheduled

Raised while using the application; no phase yet.

## Interface

### A dark mode in Preferences

The viewport's background already follows the system theme (*View ▸
Background ▸ Follow the system*), and every tone nobody chose is worked
out from the palette (`xtalapp.widgets.tone`), so the application is
readable in either theme -- but which theme it is in is the system's
choice alone.  Wanted: a Preferences setting for light, dark or follow
the system, applied to the whole application and restyled live through
`tone.retone`, without overwriting a colour chosen by hand.

### Dragging a panel has not been tried with a real mouse

The dividers were measured through `QMainWindow.resizeDocks`, which is
what a drag ends up calling, and the causes found that way are fixed:
per-panel minimums, the tab bar's width, and every dock being a native
window (`xtalapp.application.keep_siblings_non_native`).  Nothing has
driven an actual pointer, because run-app cannot without taking over
the user's.  If a drag still misbehaves -- especially one that ends
over the 3D view, which is still a native window -- that is the next
place to look.

### Four things the deep review's UI pass found and phase 5 left

From `review/reports/ui-ux.md`, written 2026-09-18 against v0.2.1 and
still true.  None was in the shell track's plan; each is small and
none is urgent.

* **The Move panel's buttons are live with nothing selected** --
  Apply, Apply -, Mirror and Make planar all invite a click while the
  panel's own header says `Nothing selected`.  Measure and Inspector
  disable correctly, so this is an inconsistency rather than a house
  rule.  `Edit > Paste` is the same with an empty clipboard.  And
  `Apply -` is not a label anybody reads correctly.
* **The Trajectory panel's labels overlap at 440 px** -- `Loop` and
  `Speed` paint over each other, and `No trajectory open` over the
  Adopt button.  The dock's minimum is small because the scroll area
  has one of its own; what is missing is a sensible `minimumWidth` on
  the *inner* widget, so it scrolls instead of being squeezed 485 px
  below its hint.
* **Only the Style panel reflows.**  Force Field, Move, Measure and
  Trajectory sprout a horizontal scroll bar at 240 px and hide half
  their controls off the right edge.  `docks.columns.ReflowColumns`
  is the machinery and it works.
* **Screen readers have nothing to read** -- 173 input widgets, zero
  `accessibleName`, no `setBuddy` anywhere, so VoiceOver says "text
  field" for a cell length.  The 142 tooltips are most of the text
  already.  Keyboard-only navigation could not be judged through the
  driver either, the same gap as the panel-drag entry above.

### A drag and a Supercell still rebuild from scratch

Measured on MFU-4l in the real window, 2026-09-21. A single-atom drag
is 65 ms a step (15 fps): 20 ms is VTK's `Render`, which is the floor,
and most of the rest is re-expanding the whole P1 cell (11 ms, in
`p1._distinct`), repainting the Sites table and re-emitting every bond
-- for one site that moved. Supercell 2x2x2 is 1.2 s on the UI
thread, now with a wait cursor. Both want the same thing: an
expansion and a scene that update the atoms that changed rather than
being rebuilt. That is a real change to `p1.expand` and
`viewport/builder.py`, not a tweak, and it has not been designed.

Measured again 2026-09-28 on COD MIL-101 in P1 (16 000 atoms), after
Change element was brought from 4.1-5.1 s to about 1.0 s: Delete of
200 sites 1.1 s, its undo 1.0 s, an occupancy or label edit of one
site 1.4-1.8 s, Set Bond Type on 6528 C-C bonds 2.0 s.  A property
edit is `Change.TOPOLOGY`, so the scene re-derives every bond order
(0.47 s, half of it the ring search) and VTK uploads the whole scene
again (0.35 s) -- for a number that changes neither.

## Symmetry

### Merge duplicates cannot see a site duplicated by its own group

`symmetry.duplicate_groups` compares a site against *other* sites'
images and never against its own, so a site far enough off a special
position for the group to generate two of it is invisible to Merge
Duplicates at any tolerance.  Raising `p1.SPECIAL_POSITION_TOL` to
0.05 A closed this at the tolerance the dialog opens on -- the
expansion now collapses anything the default merge would have wanted
to -- but a user who drags the tolerance to 0.2 A can still be told
"no duplicates" about images 0.1 A apart.

It is a *reporting* gap rather than a merging one: merging drops whole
sites and a site's own orbit cannot be half-dropped, so the honest fix
is for the preview to say "Zn1 is 0.06 A off its mirror and the group
is making three of it" and point at Standardize, not to offer a merge
that cannot happen.  Wanted with whatever finally reports a site
sitting just off a special position, which nothing does today.

## Force fields

### DFTB+'s k-point spacing oversamples frameworks

`hsd.DEFAULT_SPACING` is 0.25 A^-1.  Measured with DFTB+ 25.1 and
3ob-3-1 (DFTB3, 300 K), against a denser mesh at the same geometry,
four threads on an M2:

| framework | mesh at 0.25 | time | mesh at 0.35 | time | largest force error at 0.35 |
|---|---|---|---|---|---|
| MOF-74, 54 atoms | 4x4x4 | 5.9 s | 3x3x3 | 2.8 s | 0.0009 kcal/mol/A |
| MOF-5, 106 atoms | 2x2x2 | 3.1 s | Gamma | 0.9 s | 0.003 kcal/mol/A |
| ZIF-8, 138 atoms | 2x2x2 | 3.7 s | 2x2x2 | 3.4 s | 0 |

Energies agree to 1e-4 kcal/mol per atom in every row.  0.35 would
cost nothing measurable and halve to quarter a small framework's
evaluations; anything coarser is not safe -- MOF-74 on Gamma alone is
off by 3.3 kcal/mol/A in a force.  A numerical default, so it is
Julius's to change or not.

### UFF4MOF's O_2_z has no rule behind it

The type is in the table and is reachable only through the per-atom
override.  The obvious reading of it -- the carboxylate oxygen on a
framework metal -- was tried and measured: relaxing MOF-5 with it puts
Zn-O(carboxylate) at 1.834 A against an experimental 1.941, where
leaving those oxygens as `O_3` gives 1.891.  It makes the one number
it is supposed to fix worse, so `xtal/ff/uff/typer.py`'s `_oxygen`
deliberately does not assign it and says so.

What is wanted is the environment the 2014 paper actually fitted it
for.  Its parameters are an sp2 oxygen with `O_3_z`'s shortened radius,
which is a clue and not an answer.

### Neither tblite nor xtb gives a stress this application can use

`xtal/ff/xtb/calculator.py` sets `provides_stress = False` and pays
`numeric_stress`'s twelve evaluations a step, which is the same price
DFTB+ pays and for a better-measured reason: tblite writes a virial,
and dividing it by the cell volume disagrees with a numeric stress by
ten per cent on quartz under GFN1-xTB -- 0.874 against 0.972
kcal/mol/A^3 on the two equal diagonal components, with the numeric
one stable to four decimals from a 1e-3 strain down to 1e-5.

Ten per cent is not noise and not a sign convention.  Finding the
normalisation makes variable-cell relaxation twelve times cheaper for
both external engines.  The measurement above is the whole method:
build the engine over quartz, compare `Result.stress` against
`Calculator.numeric_stress`, and vary the strain to show which of the
two is the unreliable one.  `tests/test_xtb.py` asserts only that no
stress is claimed, which is today's behaviour and not the wanted one.

The DFTB+ panel's own variable-cell relaxation has the same gap:
DFTB+'s printed stress tensor has never been checked against a numeric
one, so the panel pays for a numeric stress.  The native driver
(*Optimise with DFTB+'s driver*) sidesteps it, because LatticeOpt uses
DFTB+'s stress inside DFTB+.

### The GFN methods are one binary each, and it is not by choice

`xtal/ff/xtb/calculator.py`'s `METHODS` routes GFN1 and GFN2 to tblite
and GFN-FF to xtb, and offers no control over it, because measurement
left nothing to choose:

| | tblite 0.3.0 | tblite 0.6.0 | xtb 6.7.1 |
|---|---|---|---|
| GFN2, periodic | works | **SIGSEGV** | refuses: "Multipoles not available with PBC" |
| GFN1, periodic | works | works | **SIGSEGV** |
| GFN-FF, periodic | — | — | works |

Both crashes are the program's and not this application's.  tblite
0.6.0 segfaults on a two-atom silicon cell as readily as on MOF-5's
424, right after printing its repulsion energy; xtb's periodic GFN1
fails to diagonalise the silicon cell and segfaults on MOF-5 *after*
reporting its own SCC converged, with or without `--grad` and with
none of our flags involved.

So GFN2 needs a tblite that works, and this application cannot tell
which one it has been pointed at short of running it.  What would help
is a cheap self-test -- a two-atom cell through the chosen binary,
once, when the path preference changes -- which is the same shape as
the Slater-Koster check DFTB+ does before it launches.

### EQeq's charge centres: three questions from #21

EQeq now centres every metal on its common oxidation state
(`xtal/ff/charges/eqeq.py`), and `equilibrate(centres=...)` overrides
it, but three things were left for a decision:

* The values agree with Open Babel's EQeq table, which is GPL.  They
  are a list of oxidation states rather than code; say whether they
  should be regenerated from another source.
* The override has no place in the Force Field panel yet.  MIL-88B is
  Cr(III) and the table's +2 gives Cr +1.24 where +3 gives +1.59, so
  it matters for shipped samples.
* Whether a CIF's `_atom_site_oxidation_number`, when present, should
  win over the table.

### No dispersion on the machine-learned engines

ORB-v3, MatterSim and MACE run the bare model.  The benchmark their
descriptions cite ran every model with D3(BJ), and on ORB-v3 D3 moves
a relaxed framework's volume by 1-3 % (MOF-74 +0.66 % to -2.02 %,
MOF-5 +2.80 % to +2.17 %) -- not always towards experiment.  Wanted:
a decision on D3 as an option of the ASE engines, and on whether it is
on by default.  `torch-dftd` is what the benchmark used and pulls in
pymatgen; `tad-dftd3` is torch-only.  **MACE-MP-MOF0 already has D3
inside and must never get it twice.**

### UFF4MOF-II redefines Pt4+2 and the table does not

The machine-readable UFF4MOF table carries a second `Pt4+2` with
`r1 = 1.125` where Rappe's is 1.364, under the same name -- so it is a
replacement and not an addition, and there is no way to hold both.
`xtal/ff/uff/params.py` keeps Rappe's and skips it, because changing a
row the 1992 paper prints is a different decision from adding ninety-one
new ones, and `tests/test_uff_params.py` asserts the published value.

## Modules

### A crash of the application still leaves its program running

Since #22 a run's program ends with Stop, Ctrl+C, SIGTERM and a normal
exit of the interpreter.  A crash or SIGKILL of the application itself
runs nothing in-process, so the program survives it.  Closing that
needs a watcher outside the process -- a lifeline pipe per run, or a
Job Object on Windows -- which is an extra process per run.  Wanted:
whether that is worth it.

### The pore surface is not a contour of anything but distance

The accessible surface ships: `xtal/analysis/grid.py` samples the
distance to the nearest atom surface over the cell and its periodic
images, `xtal/analysis/isosurface.py` marches it, and the
accessible-volume run draws the boundary of the volume it just
reported, channels only (`xtal/analysis/voids.py`).  Two things it
does not do, and neither blocks anything:

* **One colour for every channel.**  `voids.classify` labels each
  component, so the surface could be coloured per channel, and pockets
  drawn in a second tone rather than not at all.
* **Nothing welds the vertices.**  Marching tetrahedra emits six per
  cut cell and shares none between them, so MFU-4l's surface is
  567 000 points for 189 000 triangles.  It renders, and the mesh is
  thrown away on the next run, so this is only worth doing if the
  surface ever needs to be *written* -- an STL for a figure, or the
  project file it is deliberately kept out of.

### Where D_f is, measured on our own grid

The Style panel draws D_i or D_if, each exactly at its Voronoi node.
It cannot draw D_f, because Zeo++ writes no edge radii, and the user
postponed this on 2026-09-29. It could be measured on the distance
grid `xtal/analysis/voids.py` already builds:

- The widest probe that still percolates is D_f.
- The link whose removal stops it percolating is the bottleneck, so
  the sphere goes at that link's middle.
- It is the maximin path over `_links`, with union-find carrying the
  cell offsets as `_split` does.

The drawn diameter would be the grid's value, which is within a grid
step of Zeo++'s. The number beside the sphere has to say that.

### A chelate's joint comes out 0.3 A long, and the cell with it

Measured in Phase 8, 2026-09-21.  Ni3(HITP)2 built on `hcb` has the
crystal's Ni-N to the thousandth (1.836-1.840 A against 1.838) and
the crystal's bite angle, 88.2 degrees -- and the N-C bond across
every cut is **1.606 A against the crystal's 1.294**.  Two such
joints on every path from one triphenylene to the next make *a*
**22.731 A against 21.552, +5.5 %**; MFU-4l's +3.9 % on `pcu` is
the same thing at a C-C cut.

The cause is the invariant, not a bug in applying it.  A connection
point is `CONNECTION_DISTANCE` = 0.75 A from the centroid of the
atoms it stands for, so two ends meet with their centroids **1.5 A
apart** -- right for one atom onto one atom, which is what the
number was measured over.  A chelate's bonds lean inwards: two
nitrogens 2.56 A apart bonded to two carbons 1.42 A apart put the
centroids **1.16 A** apart along the axis, and the 0.34 A difference
is what every joint carries.

Two ways out, neither taken because both change a product decision:

* **Write the point where the crystal has it.**  A block cut from a
  real crystal knows its own bond: the point could sit half the
  measured centroid-to-centroid distance out rather than 0.75 A, and
  *Mark as one connection point* would record it.  That makes the
  distance a property of the block, which the invariant exists to
  stop -- a block written at a bond length builds every linker twice
  too long with nothing reporting it.
* **Leave it and say so.**  The build places blocks and stops;
  relaxation is the user's, in the Force Field panel, and a UFF
  relaxation will pull a 1.6 A C-N back.  The report could name the
  longest joint against a typical bond for the pair, so the number
  that is already measured reads as a warning rather than a figure.

`test_nihitp_builds_with_the_cell_the_crystal_has` pins 22.731 and
1.606, so either change has to move a test and say why.

## Scans

The relaxed scan shipped on 2026-09-15
([docs/PLAN.md](PLAN.md) § 12a).  What it deliberately left out:

### A stopped scan cannot be carried on

`scan.csv` is written a row at a time and already holds everything
needed -- the targets, what was achieved, the branch, and the file each
point left behind -- so a run that was stopped at point 60 of 144 could
be resumed rather than restarted.  It is not, and on an overnight job
that is the difference between losing an evening and losing nothing.
The shape is a `--resume` that reads the CSV, drops the finished
indices from the raster, and seeds the first new point from the last
finished one.

### A sweep still starts at the end of its range, not at the crystal

The two branches of a scan now form a loop -- the way back starts
where the way out finished -- but the loop's *first* point is still
reached from the input structure by one jump, and that jump can be the
whole width of the scan.  Measured on `MIL53.cif`, a volume scan from
50% to 120% of the deposited cell: the forward branch opens at 1511
A^3 having been handed a geometry relaxed at 3023, lands in a poor
basin, and stays 318-435 kcal/mol above the reverse branch for three
points before it recovers.  The lower envelope hides it, which is why
this is not urgent, but the numbers on that branch are still wrong.

The fix is to sweep *outward from the crystal*: begin at the grid
point nearest the structure's own value for that axis, walk to one
end, then return to the start and walk to the other, so no point is
ever seeded by more than one step.  It changes what "forward" and
"reverse" traverse, which is why it is written down rather than done
in passing.

### E(V) is not F(V)

A scan is at zero kelvin and the report says so, but for the flexible
frameworks it was built for that is the whole question: MIL-53(Al)'s
large- and narrow-pore difference runs 18.67 / 9.74 / -0.67 kJ/mol at
100 / 300 / 500 K, so entropy decides which phase is stable and the
landscape cannot see it.  The cheapest honest route is **quasi-harmonic
F(V,T)**: phonons at each scanned volume, which is what Cockayne did
for MIL-53(Cr) (*J. Phys. Chem. C* **2017**, *121*, 4312).  Affordable
with MACE, where the Hessians are seconds rather than hours.  It needs
a phonon calculation this application does not have.

### The scan has never been run on a real framework end to end

Every test is on quartz, zinc acetate or a fixture, because the point
was the machinery.  Ni2Cl2BTDD is the structure it was asked for -- H-3m,
a and c its only free parameters, 1152 atoms, 0.44 s an optimiser step
under UFF -- and a 7x7 grid of it is about two and a half hours.  Run
one overnight with MACE and keep the landscape beside the tests; UFF4MOF
was never fitted to reproduce a breathing double well, and whether it
shows one at all is unknown.

Pre-relaxation has been measured once, small: `MIL53.cif` (104 atoms),
volume at 90% and 80%, MACE-MPA-0 to 0.1 kcal/mol/A, forward only.
MACE alone took 467 s; UFF4MOF first (80 and 73 steps) then MACE took
196 s, and landed 0.02 and 0.08 kcal/mol lower.  Whether that holds on
a 7x7 grid of a 1152-atom framework, where the neighbour it starts from
is already close, is the thing the overnight run should also answer.

## Powder refinement

### Pawley over a long 2θ range is minutes, and no better a cell

Measured 2026-09-26 on a 14 x 17 Å hexagonal cell (Cu Kα, the cell
started 0.3 % off, 13 GB of swap in use): 4-30° is 35 reflections and
1.3 s, 4-45° 97 and 19 s, 4-60° 199 and 144 s -- and the widest put
*a* 0.04 Å further from the truth.  Every reflection is a free
intensity, so the Jacobian and the solve grow faster than the count.
The workbench says so under Pawley and on *2θ to*.  Le Bail is now
the Pawley step's second *Method* (2026-09-26), over the same plan --
fine on rutile, but that plan in Le Bail mode diverged on the wide
range above (a → -59 885 Å) when tried once, so offering it is not
the fix.  Ways to make it fast, none tried: Le Bail with
a plan of its own for the wide range, or refine the cell at low angle
and extend with the cell held.

### Rietveld with energy: the pattern's gradient could be one reverse pass

`bridge.PatternTerm` builds the whole Jacobian with RietX's numpy code
to take one gradient, `2 J^T r`.  On ZIF-8 in P1 (306 free
coordinates) that is 2.75 s an evaluation, against 8 ms for UFF's
energy and 5 ms for the residual alone.  Torch's reverse mode over
RietX's own traced residual (`backend.torch_backend`,
`make_traced_residual`) gives the same gradient to 1e-12 in 0.48 s.
Torch is not in the `refine` extra, and loading it into a process is
what CLAUDE.md's "Aborted runs" warns about, so it would be an option
used when installed and tested in a subprocess.  A framework in its
own space group has tens of variables, not hundreds, and does not
need it.

### Structure solution from the pattern alone (Superflip)

Charge flipping would take a Pawley cell and intensities to a density
map without a model.  Possible, but the way this application is meant
to reach a structure is by building one -- a net consistent with the
cell and group, the linker and SBU in the MOF builder, then Rietveld,
With energy, or a simulated pattern laid over the measured one -- so
it is not planned unless somebody asks for it.

## Testing

### CI never runs a test that needs mace, orb or mattersim

CI installs none of the machine-learned extras, so every test marked
for them is skipped there -- including the real-model checks #21 made
(sheared quartz, slope against force) and the model-name check that
failed on `mace-mp-mof0` only when the three PRs were merged on a
machine with mace.  Those tests run on this Mac and nowhere else.
Either a CI job with the extras (torch is gigabytes of wheel, and
mace and mattersim cannot share an environment -- see `pyproject.toml`)
or a stated rule that a change under `xtal/ff/` runs its engine's tests
locally before merging.

---

# What is deliberately not scheduled

* Nothing here touches the design principles in
  [docs/PLAN.md](PLAN.md) § 1.  Every phase keeps the core Qt-free,
  keeps every mutation a command, and adds capability through
  registries.
* Volumetric data and SHELX round-trips are
  [docs/PLAN.md](PLAN.md) § 12 and stay there until they are asked
  for.  Rietveld was asked for, and has shipped.
* The relaxed scan was built on 2026-09-15 and is
  [docs/PLAN.md](PLAN.md) § 12a.  What it left undone is in § Scans
  above, and M9 has a chapter for it.
* **DFTB+ — split, then merge** is postponed, not dropped.  The
  manual's DFTB+ chapter (M11) waits for it, because writing it first
  would photograph panels that phase changes.
* Dragging a panel with a real mouse (§ Interface above) needs a
  person's pointer.  The stretch's phase 3 leaves every dock title bar
  as Qt draws it, so as not to make it worse.
