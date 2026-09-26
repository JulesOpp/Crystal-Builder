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
| **3 — Attachments** | Shipped 2026-09-20; a connection point may stand for several atoms, and *Mark as one connection point* makes one | `xtal/mof/attach.py`, `xtal/mof/block.py`, `xtal/mof/catalog.py`, `xtal/commands/connections.py` | M |
| **4 — Joints** | Shipped 2026-09-20; every member of a polydentate end arrives bonded | `xtal/mof/build.py`, `xtal/mof/attach.py`, `xtal/modules/mof.py` | M |
| **5 — Node orientation** | Shipped 2026-09-20; the discrete tie-break, through `permutations=`, and a net that can be repeated | new `xtal/mof/orient.py`, `xtal/mof/build.py`, `xtal/mof/catalog.py` | M-L |
| **6 — Linker orientation** | Shipped 2026-09-20; the continuous axial angle, in closed form | `xtal/mof/orient.py`, `xtal/mof/attach.py`, `xtal/mof/build.py` | M |
| **7 — MFU-4l** | Shipped 2026-09-21; the four blocks are package data and MFU-4l builds end to end | new `xtal/mof/library/`, `xtal/mof/catalog.py`, `packaging/bundle.py`, `xtalapp/selftest.py` | M |
| **8 — Layer nets** | Shipped 2026-09-21; `hcb`, `sql` and `kgm` stacked at a spacing and offset after the build, and Ni3(HITP)2 builds | new `xtal/mof/library/nets/`, new `xtal/mof/layers.py`, `xtal/mof/build.py`, `xtal/modules/mof.py`, `xtalapp/dialogs/mof_build.py` | M |
| **9 — Interpenetration** | Shipped 2026-09-21; generated, and verified against `Net.multiplicity()`, from a Structure-menu dialog and a build parameter | new `xtal/analysis/interpenetrate.py`, new `xtal/commands/interpenetrate.py`, new `xtalapp/dialogs/interpenetrate.py`, `xtal/mof/build.py`, `xtal/modules/mof.py` | M-L |

### What Phase 9 changed

One routine, two doors.  `xtal/analysis/interpenetrate.py` does the
work; **Structure ▸ Interpenetrate…** lists every placement it found
and applies the chosen one as one undo step
(`xtal/commands/interpenetrate.Interpenetrate`, through
`Document.operate`); the MOF builder's `interpenetration` parameter
(a spinbox in *How it is built*, `pcu-2fold-N59-E32` in the title)
takes the one with the most room after the joints are bonded and the
net drawn.

**Enumerated, not theorised**, as the plan's correction 2 said.
Class Ia: the Hermite forms of determinant *n* give every index-*n*
superlattice of the structure's lattice, and their coset
representatives are where the copies sit -- seven at two-fold,
thirteen at three-fold.  Class II, at two-fold: inversion through each
eighth-cell point.  Rows that a symmetry of the structure carries onto
each other are one row, and **that symmetry is detected** with spglib
on the P1 cell rather than read off the label, because a framework
straight out of the builder is labelled P1 and is cubic: the seven
half-vectors of a primitive cube come back as three rows, body, edge
and face.

**The plan's Class II was the wrong half.**  It named "supergroup
relations `subgroups.py` can supply", and there are none to supply --
that module goes down, not up.  What it missed is the case that
matters: **MOF-5 finds nothing among the half-vectors.**  In its
F-centred cell each one is either a centring or puts a node on a
node (0.00 A).  Its real second copy is a quarter of the cell along
the body diagonal, which has order four modulo the lattice and so is
not Class Ia at two-fold at all; it is the inversion through
(1/8, 1/8, 1/8), and for a centrosymmetric framework that inversion
*is* the translation by twice the point less the framework's own
centre.  So the inversion rows are offered as the translation they
amount to, labelled Class II.  Measured:

| Structure | Best 2-fold placement | Closest contact between copies |
|---|---|--:|
| hand-made pcu, a = 4 A | translation 1/2, 1/2, 1/2 (Ia) | 3.46 A |
| MOF-5 (`resources/samples`) | translation 1/4, 1/4, 1/4 (II) | 3.45 A, H...H |
| MFU-4l on `pcu`, built | translation 1/2, 1/2, 1/2 (Ia) | 4.83 A |
| MFU-4l (`resources/samples`, Fm-3m) | refused: Cl...Cl 2.02 A | -- |
| quartz | refused: O...O 1.31 A | -- |
| halite | refused: Na...Na 2.44 A, 0.00 on the half-vectors | -- |
| dry ice | refused: only molecules | -- |

MOF-5's candidate list is 0.4 s on the UI thread, with a wait cursor.

**A collision is the bond rules' own criterion, with a floor.**  A
cross-copy pair Recalculate Bonds would join has fused the copies,
and the count of copies would then be wrong; that is the first test.
It lets two hydrogens sit 0.7 A apart, so `MIN_CONTACT` = 1.5 A is
the second, below every sample framework's closest non-bonded contact
(1.996-2.170) and below the 1.66 of a misfit build.  A collision is
refused **by name** -- *puts Na1 of one copy 2.44 A from Na2 of
another* -- and the dialog keeps such rows, greyed, so a dense
framework says why it offers nothing.  A pair the rules never bond
(two sodiums) is worded as "closer than a bond between the two would
be" rather than blaming Recalculate Bonds.

**The copies carry what the original had, and nothing is
perceived.**  The structure is perceived once, reduced to P1 with the
graph carried (`reduce_to_p1`), and each copy takes the explicit
bonds, the stored perceived graph and the drawn net with its images
moved through `R` and the wrap.  MOF-5's 512 perceived bonds become
1024, and a fresh perception of the array finds exactly those.

**The detector is the check.**  The array is refused unless
`interpenetrate.copies` -- `Net.multiplicity()` summed over the
components of the chemical graph, and separately over the drawn net
-- counts *n* times the original.  The plan wrote
`net_of(result).multiplicity() == n`; in the cell the array is
written in, the copies are separate components of the quotient graph
and each has multiplicity one, so the count is the **sum**, which is
also what `NetReport.copies` already computes.  The RCSR report reads
a 2-fold build as *2-fold interpenetrated pcu*, and the build's
verdict now says so -- `net_agrees` also asks for the number of
copies that was requested.

**Same cell, P1, and no `Change.CELL`.**  The plan expected a Class
Ia offset to need a larger cell; it does not, because the offset has
order *n* modulo the structure's lattice and every copy is whole in
the cell it had.  The array's own smaller lattice is a symmetry on
top, which Find Symmetry looks for.  `TOPOLOGY | SYMMETRY`, the flags
Reduce to P1 uses, and `TOPOLOGY` drops a pore network as it should.

Not done: n > 2 is Class Ia only (the 3-fold rotations that relate
Class II copies are not enumerated), and inversion centres off the
eighth-cell grid are not sampled -- both would be rows, not a new
mechanism.  No test is marked slow: the whole file is 4 s.

### What Phase 8 changed

PORMAKE's 2403 nets are all 3-periodic, so a layered MOF had nothing
to be built on.  Three layers now ship as package data beside the
four blocks -- `xtal/mof/library/nets/hcb.cgd`, `sql.cgd`, `kgm.cgd`,
each in a 3-D cell with *c* = 10 and edges of length one -- and
`Catalog.default` reads them between PORMAKE's nets and the user's
own.  2406 nets where there were 2403.  All three identify against
the RCSR as themselves, before a build and read back off one.

**A layer is recognised by its graph, not by its folder.**
`Topology.is_layer` is `xtal.mof.layers.stacking_axis_is_free`: the
net's own lattice has rank two and no cycle of it closes along *c*.
So a layer somebody writes into their own topology folder is stacked
like ours, and `pcu` and `tbo` are not layers.

**The stacking is set after the build, not asked of it**, which is
what probe P9 said and the plan inherited.  The scaler hands `hcb`
back with *c* = 107.154 A, one global factor chosen for the in-plane
edges.  `layers.restack` throws that *c* away and writes the asked-for
one, moving the framework, the net and every placed block together
because `write_cif`, `draw_net` and `bond_joints` each read one of the
three afterwards.  Two things it had to be taught rather than
assumed:

* **Which sheet an atom is in is read off the *built* cell.**  A
  paddlewheel is 3.0 A thick and wrapped by PORMAKE, and in a new
  cell 3.4 A tall its top half already rounds into the next sheet.
  Read off the 107 A cell, nothing is ever half way.
* **The spacing is between the sheets' mean planes.**  PORMAKE does
  not put every sheet on its lattice plane: on `hcb` x (1,1,2) one is
  0.021 A above it and the other exactly on it, so carrying each
  sheet's own offset across made "3.3 A apart" 3.278.  Each sheet is
  now lifted as a whole until its middle is one spacing above the
  last one's, and its shape inside is untouched.

Two parameters, `spacing` (Angstrom; empty is
`layers.DEFAULT_SPACING` = 3.4) and `offset` (two fractions of the
net's own *a* and *b*, `1/3, 2/3` read as thirds; empty is
eclipsed).  **On a 3-periodic net either one is refused**, by name,
rather than dropped -- a command-line run would never notice a
number quietly ignored.  The dialog gains *Layer spacing* and
*Stacking offset* in *How it is built*, greyed for any net that is
not a layer and never handed to the run from one.  The log always
gives the sheet's thickness beside the spacing, with no threshold:
the closest contact in the verdict is the measurement of a collision.

Ni3(HITP)2, measured against `resources/samples/NiHITP.cif`:

* **75 atoms, C36H24N12Ni3**, the crystal's P1 composition, on
  **hcb** read back off the bonds; blocks fit to 0.000 A; **12**
  joints, one N-C bond per nitrogen and per carbon.  Hexagonal,
  *c* = 3.238 A as given (the vendored writer puts a cell length in
  the file to 0.001 A, which is as close as any build reads back).
* **The nickel lands the crystal's own way**: four nitrogens at
  1.836-1.840 A against 1.838, at 88.2 / 91.8 / 180 degrees -- the
  crystal's bite angle -- and in the sheet to 1e-4 A.  This is Phase
  6 doing its job on a two-connected *linker*: nothing discrete is
  chosen on `hcb` at all.
* ***a* is 22.731 A against 21.552, +5.5 %, and the whole of it is
  the joint.**  The N-C bond across every cut is **1.606 A against
  1.294**: two ends meet with their member centroids 1.5 A apart,
  which is `CONNECTION_DISTANCE` twice, where a chelate's lean-in
  bonds put them 1.16 A apart.  Two joints per triphenylene-to-
  triphenylene path is the 5.5 %; MFU-4l's 3.9 % is the same thing.
  It is a consequence of an invariant, not a bug in applying one, so
  it is pinned by `test_nihitp_builds_with_the_cell_the_crystal_has`
  and written up as *A chelate's joint comes out 0.3 A long* in
  [docs/TODO.md](TODO.md) § Modules rather than changed here.

The same machinery on PORMAKE's own blocks: `sql` and `kgm` on the
`N153` paddlewheel with `E14` identify as themselves, and at the
default 3.4 A the sheets collide -- closest contact 0.53 A, the log
saying the sheet is 3.00 A thick -- where at 7 A they do not (2.04).
That is what the thickness line is for.

`xtalapp/selftest.py` builds Ni3(HITP)2 after MFU-4l, for the reason
the MFU-4l build is there: the nets are a third `PACKAGE_DATA` glob,
and a bundle without them passes every other check.  The three
Ni3(HITP)2 tests are **not** marked slow, against the plan: the
build is 0.06 s, and CLAUDE.md keeps `slow` for tests that take
seconds.

### What Phase 7 changed

The four blocks Phases 3 to 6 were written for are now **package
data**, and MFU-4l builds out of them without a probe script.  There
is no new geometry in this phase: every lever it uses shipped in the
six before it, and what it adds is that they are reachable from a
menu and from a `.dmg`.

`xtal/mof/library/blocks/` rather than `resources/`, and that is the
whole of the placement argument: `packaging/bundle.py` collects
**package data**, so a folder outside a package has to be remembered
separately every time -- which is exactly how `MIL53.cif` became
unreachable in a shipped build.  `catalog.library_root()` finds it
the way `database_root()` finds PORMAKE's, with `find_spec` and never
an import, and `Catalog.default` reads it **second**: after PORMAKE's
`bbs/` because ours may replace one of theirs, before the user's own
folders because a block somebody drew must still win over a block
they were shipped.  871 blocks where there were 867.

Four things measured rather than assumed:

* **MFU-4l comes out as the crystal's own formula.**  One node and
  three linkers on `pcu` give 81 atoms, `Zn5Cl4N18C36O6H12` -- which
  is `_chemical_formula_sum` for one Kuratowski unit, so nothing was
  lost at a cut and nothing counted twice.  The net reads back as
  **pcu**, the blocks fit to 2.2e-06 A, the closest non-bonded
  contact is 2.05 A, and the four chlorides are 2.07 A from four
  *different* zincs with the central one bare.
* **Twelve joints, not six.**  The node's six triazolate arms are two
  carbons each and every one of the twelve arrives bonded, to twelve
  *distinct* linker carbons.  Six would be PORMAKE's one-bond-per-joint
  and no later perception recovers it: the carbons left over are 1.5 A
  apart with nothing between them.
* **`consistent` alternates the nodes, and only on a repeated cell.**
  Every edge of `pcu` joins a node to an image of itself, so on the
  single cell the discrete rule has nothing to choose between and
  `as-found` and `consistent` build the same file.  Repeat it and the
  eight slots are eight choices: the signed volume of each cluster's
  four zinc directions is **-0.77 eight times** as found and **four
  and four** under the rule, which is MOF-5's own +-0.770 measured on
  MFU-4l's node.  96 joints either way, longest **1.838 A -> 1.667**,
  the fit untouched.  That is the same number *A repeated net cannot
  be told to flip its neighbours* in [docs/TODO.md](TODO.md) § Modules
  reports, now reachable from a test rather than from a probe.
* **One picker default moved, and nothing else in the UI did.**  A
  6-connected node slot offered `N101` first and now offers
  `MFU4l_Kuratowski`: the rows are metals first and then by name, and
  `M` sorts before `N`.  The 2- and 3-connected defaults are
  unchanged (`E103` and `N117` both sort ahead of `NiHITP_*`), and a
  returning user sees what they picked last time either way.

Ni3(HITP)2's two blocks ship here and are **not built** here: they
want a layer net with a stacking spacing, which is Phase 8.  What
this phase says about them is that they read back off disk bidentate
at all three and both points respectively, which is the property no
file format records and no other check would catch.

`xtalapp/selftest.py` builds MFU-4l after `pcu-N59-E32` for the
reason the first build exists at all: four files against 3271 travel
by a different `PACKAGE_DATA` entry, and a bundle that dropped them
passes every other check and cannot build the material the feature
was written for.

One test from Phase 3 changed.
`test_only_two_shipped_blocks_read_as_bidentate_and_both_are_wrong`
asked the *default* catalogue which blocks read as polydentate and
named `N484` and `N684`, two upstream data errors.  Ours are
polydentate deliberately, so the question is now put to PORMAKE's
`bbs/` alone and the test is
`test_only_two_vendored_blocks_read_as_bidentate_and_both_wrong`.

### What Phase 6 changed

Everything Phase 5 does chooses between placements that differ
*discretely*, because a node's fit is over-determined and the only
freedom left in it is which of the block's own rotations was applied.
A two-connected block is the opposite case, and the difference is what
this phase is: its fit is Kabsch on two vectors, which scipy itself
warns is "not uniquely defined", so the angle about the line through
its two connection points is left **undetermined** rather than
decided.  There is no earlier answer there to be faithful to.

`orient.align_edges(framework)` settles it, and it is a refinement of
the fit rather than a second fit for one reason: **both connection
points are on the axis**, so a turn about it moves neither, and the
RMSD, the relaxed cell and every X-to-X coincidence the builder made
go on being true of what is written out.  It runs between `_build` and
`write_cif`, so `bond_joints`, `draw_net` and `_representatives` all
see the settled geometry.

The angle is **solved and not searched**: each member's unit lateral
written as a complex number in one basis across the axis -- the same
basis at both ends -- makes the cost `const - 2 Re(exp(i phi) S)`, so
`phi* = -arg(S)` with `S = sum over ends, sum over paired members
z_here conj(z_there)`.  The pairing is re-solved once at `phi*` and
the angle taken again, because the closed form is exact only for a
fixed pairing.  The cost is **the one Phase 5 minimises**,
`attach.pair_cost`, so the two levers are scored on one scale;
`attach.unit_laterals` and `attach.pairing` are that rule in one
place, read by both.

Four things measured rather than assumed:

* **What turns is asked of the *block*, never of the net.**
  `_turnable` takes any placed block with two connection points and a
  face at one of them, which covers the two-connected *node* -- and
  Ni3(HITP)2's NiN4H4 is one -- without naming either kind of slot.
  It is also the whole of the guarantee for the 867 shipped blocks:
  a point standing for one atom presents no face, so the list is
  empty and nothing runs.  Measured on `pcu`/N59/E32: the same 6
  joints and no length.
* **The closed form returns the crystal's own angle.**  Ni3(HITP)2's
  three NiN4H4 blocks on `hcb` come back wanting 1.5e-08, 6.1e-08 and
  4.2e-08 radians -- the same 1e-05-ish imperfection a block cut from
  a real crystal has everywhere else -- so the framework is left
  **atom for atom as it was placed** and `align_edges` reports 0.
  That is `_STILL` = 1e-6 rad doing its job: at that angle the widest
  attachment there is moves its furthest member 5e-06 A, below the
  figure a CIF is written to.
* **On MFU-4l the turn is real and the residual is somebody else's.**
  `pcu` goes from a joint disagreement of 5.999987 to **3.514719**
  and its longest joint from **2.188 A to 1.835**; `acs` goes 7.924843
  to 2.584810 and 2.235 A to 2.028.  On `acs` the two rules then
  *agree* -- `as-found` and `consistent` both settle to 2.584 and
  2.028 -- because with a linker between them the linker's own turn
  absorbs most of what the discrete choice was buying.  Where it
  cannot is `acs` with no linker at all, where nothing is
  two-connected and Phase 5 is still the whole answer (2.766 ->
  1.884 A).
* **What is left on `pcu` is the node flip, and it is now a TODO
  rather than a mystery.**  Every edge of `pcu` joins a node to an
  image of *itself*, so both ends of a linker meet the same
  orientation and, on MFU-4l, two faces a quarter turn apart.  One
  angle cannot satisfy both, so the closed form splits the difference
  at exactly **45 degrees** on all three linkers and every one of the
  six joints is left at **0.585786 = 2 - sqrt(2)**, the cost of a
  45-degree mismatch to seven figures.  Splitting the difference is
  the right answer to the question asked; the fix is an inverted
  neighbour rather than a better angle, and it is *A repeated net
  cannot be told to flip its neighbours* in
  [docs/TODO.md](TODO.md) § Modules.

On the synthetic blocks the fit leaves the three `pcu` linkers at
0.000000, 0.271226 and **2.000000** -- a dead quarter turn, which is
the square `test_the_two_ends_of_a_joint_are_paired_not_crossed` saw
as four equal distances of 1.797 A.  All three come back at zero and
the twelve joints become one length, **1.500 A**, twelve times; the
linker that was already right is left alone rather than turned by its
own rounding, so two of three move.  Those two pinned numbers are
this phase's only changes to an existing test.

### What Phase 5 changed

A symmetric node fits its slot a great many ways and `locate` takes
whichever its Euler grid reached first.  For an octahedral node that
is **24 fits, tied to 3.4e-08**, while the body of the block moves up
to 8.2 A between them -- so which face a node presents to its
neighbour was, until now, an accident.  It did not matter while a
connection point stood for one atom; it decides a bond as soon as one
stands for two.

`xtal/mof/orient.py` breaks that tie and only that tie.  **The default
rule is `as-found`, which is today's behaviour, and `build._build`
returns at pass 1 unless a block is polydentate *and* another rule was
asked for** -- so "nothing regresses" is structural rather than
argued, and a test pins that `pcu`/N59/E32 comes back byte for byte.

**The rotation group is enumerated from ordered *pairs*, not
triples.**  Two directions and the normal of the plane they span fix a
rotation, so a six-connected node is **24 candidates** rather than the
plan's 120 and never 720; composed with the primary fit it equals the
brute-force tie set over all 720 **exactly**, and the gap it has to
find is **4.21e-08 against 8.16e-01**, a factor of 1.9e7.  The change
from triples is not an optimisation: three directions of a *planar*
block never span a volume, so triples name no rotation of one at all
and return the identity alone -- **|G| = 1 where it is 6** for the
trigonal node Ni3(HITP)2 is built out of, which would have left Phase
8 with nothing to choose between and no sign of it.

Three things the phase measured rather than assumed:

* **Where the discrete choice bites is an edge joining two
  *different* node slots.**  On `pcu` -- and on `hcb` -- every edge
  joins a node to an image of *itself*, so its two ends are antipodal
  points of one block and agree by construction whatever the
  rotation.  MFU-4l on `pcu` is therefore **2.188 A before and after**,
  and Ni3(HITP)2 on `hcb` **1.606 A before and after**: MFU-4l's 2.19
  is the linker's own quarter turn and is Phase 6's, exactly as the
  plan says.  Where the two ends are different slots the rule does
  move: MFU-4l on `acs` goes **2.235 -> 2.146 A**, and the synthetic
  bidentate node on `acs` with no linker at all -- where the node-to-
  node joint is the whole of the geometry -- goes **2.766 -> 1.884 A**.
  Scored over the 33 six-connected nets small enough to sweep, **24
  have a strictly cheaper orientation available** than the fit chose;
  `acs` goes from 9.4029 to 2.8807.
* **The rule may only ever improve on the fit, never merely tie with
  it.**  `choose_permutations` is given pass 1's own permutations as
  its baseline and moves off them only where the cost is *strictly*
  lower; lowest-permutation tie-breaking decides between candidates
  and never against the placement in hand.  Without that, `pcu` --
  where every orientation costs the same -- came back re-oriented for
  no reason and `longest_joint` changed by luck, 1.797 to 1.544.  When
  nothing is better the second pass is not run at all.
* **Correction 3's hazard has a blind spot, and it is named rather
  than assumed away.**  A pinned slot `continue`s at `builder.py:266`
  before the chiral retries, so it never fights the fallback; the risk
  is that pass 1 mirrored a block at `:313` and pass 2 skips the
  substitution.  `orient.substitute_mirrored` catches that by the
  signed volume of three connection directions -- **0 substitutions
  over `pcu` and `acs`**, the guard staying because the sample is two
  nets.  But a located block **loses its `X` atoms** when exactly one
  slot is filled (the `sum(bb_atoms_list[1:], ...)` aliasing Phase 4
  found), so its handedness cannot be read at all; such a slot is
  **reported as unchecked** in the run log rather than silently
  passed.  Reaching it was a crash before it was a guard.

`catalog.Topology.expanded(nx, ny, nz)` is the one place a vendored
`pormake.Topology` is made, over `__mul__`; `(1, 1, 1)` hands back the
net itself and multiplies nothing, which is what makes a repeat of one
bit-identical.  `pcu` x (2,2,2) is 32 slots, and MFU-4l on it is
**648 atoms -- the crystal's own P1 count**, in 1.2 s under
`consistent` against 0.4 s under `as-found`.  `BuildRequest` gains
`repeat` and `orientation`; only the repeat is spelled into `title()`
(`pcu-2x2x2-N59-E32`), because the orientation changes which way round
a block went and never what the framework is made of.

`build.edge_ends` and `build.point_at` are the one walk over a net's
edges -- which node slot each end is and which of that node's own
edges it is, out of the topology alone.  `_joints_of` is now
`fused_points` mapped into the concatenated numbering, and the
orientation search reads the same walk without re-deriving it for
every one of the two dozen permutations it tries per slot.

### What Phase 4 changed

`builder.py:644-658` keeps **one partner per connection point** --
`X_neighbor_list[i] = j`, a scalar assigned into a list-valued map --
so a bidentate joint arrives with half its bonds and the framework's
own bond list is missing them rather than holding them wrongly.  No
amount of reading it back recovers them, so `_joints_of` **enumerates**
the fused pairs instead, restating `find_matched_atom_indices`
(`builder.py:441-469`) against `info["located_bbs"]` and
`info["permutations"]`.  The vendored file is still untouched.

Measured on the four probe blocks, through the ordinary `build()`
path:

| Framework | Net | Atoms | Joints before | Joints now | Longest joint |
|---|---|---|---|---|---|
| MFU-4l | `pcu` | 81 (Zn5Cl4N18C36O6H12) | 6 | **12** | 2.19 A |
| Ni3(HITP)2 | `hcb` | 75 (C36H24N12Ni3) | 6 | **12** | 1.61 A |

Three things the plan did not foresee, each measured rather than
argued:

* **The located blocks are not all in one cell.** Three of MFU-4l's
  six joints on `pcu` have their two ends a full **16.136 A** apart as
  placed, so the member-to-member distances are taken at their
  minimum image under the framework's own cell.  Without it the
  pairing is decided on distances of 14.7 A differing in the second
  decimal, and the number reported beside it is not a bond length.
* **PORMAKE's own joint bond must be dropped, not deduplicated.**
  Which member it kept is an accident of iteration order, and on
  MFU-4l **three of its six** are the pairing the assignment rejects
  -- so appending gave 15 bonds where 12 are right.  A joint the
  enumeration accounts for is now the enumeration's whole answer;
  `owned` is every member-to-member pair of that joint and the diff
  loop skips all of them.  For a monodentate joint the two agree atom
  for atom and nothing is dropped.
* **A net with no linker comes back without its connection points.**
  Upstream builds the framework's atoms as
  `sum(bb_atoms_list[1:], bb_atoms_list[0])` and then deletes the `X`;
  with exactly one filled slot that sum *is* its one argument, so the
  delete lands on the located block too (N59: 26 atoms -> 20).  Its
  `bonds` and `connection_point_indices` still name them, so
  `_placed_atoms` reads each block's extent from those rather than
  from `n_atoms`, and a bare `pcu` on a bidentate node goes from 3
  joints to **6**.

`_framework_indices` is now the one walk over the placed blocks --
PORMAKE's `index_offsets` and `new_indices`, neither of which reaches
`info` -- and `_intra_block_bonds`, `_block_of_atoms` and
`_joints_of` all read it instead of each repeating the arithmetic.
`attach.members_of` is the one distinct-partner rule, read off both
our `BuildingBlock` and PORMAKE's.

`bond_joints` returns `(count, longest joint)`; the length joins the
verdict and the report's fit table, and is **omitted** when nothing
measured it.  A test pins that `pcu`/N59/E32 still
makes its 6 and reports no length: no shipped block is polydentate,
so none of them opens the guard.

### What Phase 3 changed

A connection point stood for exactly one atom, and that is why
MFU-4l and Ni3(HITP)2 could not be built: their nodes meet a linker
through *two* atoms, and marked one at a time they come out with
twice the coordination number they have and fit no net in the
catalogue.  **An attachment is now one `X` plus the distinct body
atoms bonded to it** -- new `xtal/mof/attach.py`, which is numpy at
import and holds `Attachment`, `attachments_of`, `lateral`,
`pair_cost` and `MAX_ATTACHMENT_SPAN`.  Nothing new enters the
`.xyz`: the bond block always said which atoms a point hangs off and
PORMAKE has always read it, so no vendored file is touched and
`tests/test_mof_vendored.py` is green unchanged.

`block.pull_in` pulls a point in to `CONNECTION_DISTANCE` of its
members' **centroid**, and `block.problems` loosens from `n != 1` to
`n < 1`.  Two bonds are a bidentate attachment;
`test_a_connection_point_with_two_bonds_is_named` was rewritten
rather than deleted.  Three refusals replace it, and only the third
needed measuring:

* an `X` bonded to another `X`;
* members further apart than **`MAX_ATTACHMENT_SPAN = 5.0 A`** -- the
  four target blocks span 1.405, 1.408, 2.558 and 2.861, the mis-click
  it catches is two ends of a molecule, and half the shipped blocks
  are wider than **10.33 A** (821 of 867 wider than 5.0);
* an attachment pointing **inward**, judged against the atoms one
  bond further in.  Two global definitions were measured first and
  both discarded: against the block's own centroid, **77** of the
  4256 shipped points read as inward, and by what lies ahead along
  the axis, a quarter of them do -- a node's arms are concave.  The
  local reading fires on **0** of the 4202 shipped points that have a
  bond block, worst cosine **-0.032**, so the threshold is plain zero
  with no margin to tune.

`catalog.read_building_block` now parses the bond block with
PORMAKE's own tolerance (a line of fewer than three tokens is skipped
in silence), and `BuildingBlock` gains `bonds`, `members` and
`is_polydentate`.  All 867 shipped blocks still parse, in **0.158 s**
including the bonds.  `members` is the set of **distinct** partners:
counting records would take 26 shipped blocks down the new path.
Exactly two shipped blocks read as polydentate -- `N484` and `N684`,
both upstream data errors -- and they are **named in a test** rather
than separated by a tolerance that would have to be 0.047 A wide.

`MarkOneConnectionPoint` (`xtal/commands/connections.py`) collapses a
selection into one `X` carrying every bond the group had to atoms
outside it, add-then-delete exactly as Merge atoms does, in one undo
step; *Mark as &one connection point* sits beside *Mark connection
points* in the Structure menu, enabled on two or more atoms.  The
point is **pulled in** at the moment it is marked rather than left at
the group's middle: the sibling command does, and the invariant would
otherwise be false in an open document until the block was saved.

**The bit-identical guarantee is pinned, not argued.**
`test_a_single_point_block_is_written_byte_for_byte_as_before` fixes
the bytes, and the writer's output was diffed against `HEAD`'s for
both that block and the real RDKit phenylene before the test was
written.

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

## 3. MOF-5 from the builder: the face rule

Planned 2026-09-21 on `features/mof-polydentate`, for
[docs/TODO.md](TODO.md) § *A repeated net cannot be told to flip its
neighbours*.  The full plan, with every measurement, is
`~/.claude/plans/mof-face-rule.md`.  `pcu` x 2x2x2 on `N16` / `E14`
builds MOF-5's 424 atoms with all eight Zn4O the same way round; the
sample alternates, four and four.

**Why**: across every linker the two carboxylates are coplanar in the
sample (0 degrees x 24) and turned a quarter turn in the build (90 x
24), because a Td node's opposite carboxylates are perpendicular.
**The rule**: a connection point standing for one atom presents a
*face* -- the plane of that atom and its two other neighbours
(carboxylate on N16, ring on E14) -- and `consistent` scores it with
the `pair_cost` it already has.  Monkeypatched prototype: joints 24.0
-> 0.000000, parity four and four, rings flat on all 48 carboxylates,
**0.10 A RMS** onto `resources/samples/MOF-5.cif` (1.18 today), 2.1 s.

**Decided with Julius**: `consistent` becomes the default; faces feed
the linker spin only under `consistent`.  That reverses the CLAUDE.md
invariant *Which way round a symmetric node goes*, rewritten in
Phase 3.

| Phase | Delivers | Main files | Size |
|---|---|---|---|
| **0 — Clean tree** | Shipped 2026-09-21 (7689c37); the MOF dialog work left uncommitted, committed on its own | `xtalapp/dialogs/mof_build.py`, `xtal/mof/catalog.py` | S |
| **1 — A safe, fast search** | Shipped 2026-09-21; the search starts from the fit, a second pass that fits worse is discarded, each joint is scored once | `xtal/mof/orient.py`, `xtal/mof/build.py` | M |
| **2 — Faces** | Shipped 2026-09-21; `attach.face_of`, `attach.presents_face`; MOF-5 builds under `consistent` to 0.10 A of the sample, default still `as-found` | `xtal/mof/attach.py`, `xtal/mof/orient.py`, `xtal/mof/build.py` | M |
| **3 — `consistent` by default** | Shipped 2026-09-21; the default flips, a pass 2 that moves the cell is thrown away, "Joint twist left" in the results | `xtal/mof/build.py`, `xtal/modules/mof.py`, `xtal/mof/orient.py`, `xtalapp/dialogs/mof_build.py` | S-M |

### What Phase 1 changed

* **The search starts from the fit.**  `orient._start` assumed the
  fit's own permutation was in its tie set, and fell back to the
  lowest permutation when it was not -- and it is not, whenever
  `tie_set`'s fresh `locate` lands elsewhere on its Euler grid.
  Pinning such a slot was tried first and was wrong: on the synthetic
  node on `acs`, *both* slots' fits are outside their tie sets of 24,
  and pinning froze a real improvement.  `orient._admit` instead adds
  the fit to the candidates and starts there, so it is left only for
  something strictly cheaper.  The old `acs` figure was the bug at
  work: it logged the lowest permutation as "as found" (2.602) where
  the fit costs 9.693, and kept it for a 1e-5 gain.  Started honestly
  it reaches **2.191**, and the longest joint the test pins moves
  from 1.884 A to **1.931** (the joint length is not what the rule
  minimises).
* **A worse second pass is thrown away.**  `build._build` keeps pass
  1 when pass 2's `max_rmsd` is above it by more than
  `orient.FIT_SLACK` = 1e-3 A.  Measured: rebuilding with the *same*
  permutations gives the same `max_rmsd` to the last bit on 8 of 8
  builds, so there is no noise to allow for; the prototype's
  regression it has to catch was `nbo`/N466/E14, 0.562 -> 0.973.
* **Each joint is scored once.**  `_Score` caches attachments and
  joint costs by `(edge, orientation, orientation)`, summed in the
  same order, so every cost is the same float as before.  MFU-4l pcu
  x 2x2x2: search 0.88 -> **0.20 s**, `pair_cost` calls 15 096 ->
  2694, result unchanged (48.0 -> 0.0, four and four, 1.667 A).
  `dia`/N194/E1 x 2x2x2 through the face prototype: the search's
  share went from ~35 s to ~3.7 s (11.0 s as found, 14.7 s turned).
* Tests: `test_the_fit_s_own_orientation_is_always_a_candidate`,
  `test_a_second_pass_that_fits_worse_is_thrown_away`,
  `test_a_joint_is_scored_once_however_often_the_search_asks`.

### What Phase 2 changed

* **A face.**  `attach.face_of`: where the atom a single-atom point
  hangs off has exactly two neighbours that are not points, the
  point presents that plane as a virtual bidentate at +-*w*, *w* in
  the plane and across the atom->X bond.  Built first with the
  atom->point offset in the virtual members, and that was wrong: with
  the X tilted 0.5 A off the plane the face leaned 0.43 rad with it.
  The members are +-*w* alone now, less a 1e-6 hair back along the
  bond so `Attachment.axis` keeps a direction.
* **Where faces are read.**  `orient._Score` and `_attachment_at`
  fall back to the face; `choose_permutations`' refusal and
  `build._build`'s pass-1 gate ask `presents_face`; `align_edges`
  reads faces only with `faces=True`, which `build` passes under
  `consistent`.  `bond_joints` still asks `_is_polydentate`: a face is
  never bonded.
* **The pass-1 gate asks of the nodes.**  It asked whether *any*
  block had a frame while the rule scores only nodes, so `cds` on
  N307 (no face) and E3 (a face) reached the rule with nothing to
  score and the whole build raised.  The same hole was there for a
  polydentate linker between plain nodes; nothing shipped reached it.
* **MOF-5**, `pcu` x 2x2x2 on N16 and E14 under `consistent`: joints
  24.0 -> 0.000000, clusters four and four with every neighbour
  opposite, 0 degrees between the carboxylates on all 24 linkers and
  between each ring and its carboxylate on all 48, **0.101 A RMS /
  0.131 worst** onto `resources/samples/MOF-5.cif` (1.18 / 2.98
  before), 424 atoms and 48 joints as before.
* **Elsewhere under `consistent`**: `dia`/N623/E14 0.579 -> 0.000 A
  max RMSD, joints 17.6 -> 0 -- **wrong, and caught in Phase 3**: that
  pass 2 had collapsed the cell (*b* 25.2 -> 0.007 A), and a perfect
  fit is what a cell with no room looks like; `pcu`/N343/E32 x 2x2x2
  0.450 -> 0.395 (also a cell change, 4.6 % in volume);
  `nbo`/N466/E14 would have fitted 1.051 against 0.562 and Phase 1's
  guard kept the fit; `cds`/N161/E3 had nothing strictly better and
  only its linkers turned.  Every `as-found` build checked is byte
  for byte what it was.
* **Tests changed**: N59 is no longer a block with nothing to score
  (its carboxylates are faces), so the two tests that said so use
  N6, a B12 icosahedron whose borons have five neighbours, and E32,
  whose points hang off alkyne carbons.
* Tests added: `test_mof5_builds_with_its_nodes_alternating`,
  `test_every_mof5_linker_lies_flat_against_both_ends`,
  `test_mof5_overlays_the_sample_to_a_fifth_of_an_angstrom`,
  `test_mof5_has_the_joints_it_had` (`test_mof_targets.py`, 4 s
  together); `test_a_face_is_the_plane_of_the_atom_and_its_two_neighbours`,
  `test_a_face_does_not_care_where_its_x_was_written`,
  `test_a_linear_or_tetrahedral_point_presents_no_face`,
  `test_a_face_is_never_a_member`,
  `test_nodes_with_nothing_to_score_between_linkers_with_faces_keep_the_fit`
  (`test_mof_orientation.py`).

### What Phase 3 changed

* **`consistent` is the default** -- `BuildRequest`, `parse`, the
  `orientation` `Param` -- and `orient.RULES` offers it first; keys
  unchanged.  A MOF-5 build that names no rule, in the real window,
  comes back four and four, 0 degrees on 24 linkers and 48 rings, and
  0.101 A RMS onto the sample.  `as-found` stays, byte for byte
  PORMAKE's, and the upstream comparison asks for it by name.
* **A pass 2 that moves the cell is thrown away** (`orient.
  same_cell`, `CELL_SLACK` = 0.5 % in every length and in volume).
  Found by the spread: `dia`/N623/E14 took **368 s** against 0.9,
  because pass 2 had collapsed *b* from 25.2 A to 0.007 and PORMAKE's
  `write_cif` spent five minutes on the neighbour list of a 3.9 A^3
  cell.  Its blocks "fitted" to 1e-4, which is why the `max_rmsd`
  guard let it through, and why Phase 2 reported it as 0.579 ->
  0.000.  A tie cannot move the cell -- MOF-5's turned cell matches
  to 2e-16 -- and over the 23 builds that took pass 2, the ties moved
  it by at most 0.19 % and everything else by 0.74 % or more.  The
  cost is that `pcu`/N343, `dia`/N194, `lvt`/N50 and `sod`/N276 lose
  "better fits" that were PORMAKE relaxing to a different framework,
  not the rule breaking a tie.
* **The pass-1 gate reads the blocks as made, not as placed.**  A node
  placed with no linker beside it comes back without its X atoms but
  still naming them, and `face_of` indexed off the end: N59 on bare
  `pcu` raised.  `make_bbs_by_type` moved up a line and the gate reads
  that.
* **Results** gain *Joint twist left*, the node-to-node cost the rule
  could not remove: `pcu` x 1x1x1 on N16 reports 6.0 over 3 edges, the
  2x2x2 0 over 24; no row where no node had a face.
* **The dialog** opens *How it is built* when the rule is not the
  default *by name*, and falls back to it when none was saved.
* **The spread**, 52 builds on 17 nets, each in its own process:
  every net identifies as asked with the same atom count; none fits
  worse; 2 fit better (`tbo`/N48+N385 0.447 -> 0.445, `lvt`/N654
  0.007 -> 0.000); 34 change by linker spin or a tie at the same fit;
  16 are byte for byte `as-found`.  Time 48.0 s -> 52.2 s (x1.09),
  none slower than x1.5.
* Tests: `test_a_build_that_names_no_rule_is_built_consistent`,
  `test_as_found_builds_exactly_what_it_built_before` (was
  *the default rule*), `test_a_second_pass_that_moves_the_cell_is_thrown_away`,
  `test_a_cell_with_no_room_to_alternate_says_how_much_twist_is_left`,
  `test_the_orientation_form_offers_consistent_first`,
  `test_as_found_last_time_is_not_hidden_and_the_default_is`; the
  MOF-5 fixture names no rule, so its four tests are of the default.
* The TODO entry *A repeated net cannot be told to flip its
  neighbours* is deleted; CLAUDE.md's orientation invariant is
  rewritten for the new default.

---

## 4. Net search, and every RCSR layer net

Planned 2026-09-21. The MOF builder's topology list and the Net
builder get MOF+'s search (mofplus.org/nets/browse): **Name**,
**Coordination** with *Exclusive*, **Spg #**, and **Transitivity**
written `p q r s` with `*` matching anything. The 200 2-D nets in
`resources/topo/RCSRnets-2019-06-01.cgd` replace the four in
`xtal/mof/library/nets/`. The full plan, with its measurements, is
`~/.claude/plans/net-search-and-layers.md`.

**Measured**: 196 of the 200 layer nets build through the vendored
PORMAKE once written in 3-D at z = 0 with c = 10, in the plane group
plus the z-mirror (p6mm -> P6/mmm, p2gg -> Pbam, ...; derived with
`gemmi.find_spacegroup_by_ops`). The other four (`sde mtb-a mtc-a
fzh`) fail PORMAKE's own `check_validity`. Embedded this way, `hcb` is
its hand-written file line for line. p is the `NODE` count on all
2931 RCSR nets.

**Decided with Julius**: r and s (faces, tiles) are not known, so a
number there matches nothing and `*` matches all. Vendoring RCSR's
table is a later data change. A layer's Spg # is its plane group
number (hcb is 17).

| Phase | Delivers | Main files | Size |
|---|---|---|---|
| **1 — The query** | Shipped 2026-09-21 (51db3ed); `NetFacts`, `NetQuery.parse` / `matches`; `rcsr.LAYER_GROUPS`, `plane_group_number`, `as_layer` | `xtal/analysis/netsearch.py`, `xtal/analysis/rcsr.py` | M |
| **2 — Layers in the catalogue** | Shipped 2026-09-21; the 196 RCSR layers in memory, PORMAKE handed a file only at build time; `library/nets` and `library_nets()` deleted; Ni3(HITP)2 on `hcb` unchanged | `xtal/mof/catalog.py`, `packaging/bundle.py`, `xtalapp/selftest.py` | M |
| **3 — Facts on every topology** | Shipped 2026-09-21; `Topology.facts()`: p and q from the RCSR entry of the same name, else the file; group number by gemmi or plane group | `xtal/mof/catalog.py` | S |
| **4 — One search widget, both dialogs** | Shipped 2026-09-21; `NetSearch` in the MOF builder and the Net builder; the Net builder gains the 2D/3D boxes and draws layers | `xtalapp/widgets/net_search.py`, `xtalapp/dialogs/mof_build.py`, `xtalapp/dialogs/net_draw.py`, `xtal/build/topology.py` | M |

All four shipped on `features/net-search`; CLAUDE.md's invariant *A
layer net is stacked after it is built* was rewritten in Phase 2, when
the files went.  The faces and tiles it left unknown were filled on
2026-09-24 from the RCSR's own data (`scripts/rcsr_transitivity.py`),
which also corrected q on the 18 nets whose `.cgd` repeats an edge
kind.

---

## 5. The shell: the first minute, and not losing work

Planned 2026-09-22 from what `features/deep-review` left open once its
correctness, registry, MOF-builder and performance items had shipped:
nearly all of `review/reports/ui-ux.md`, plus the small silent
failures in `review/reports/edge-cases.md` §6-14.  The full plan, with
its measurements, is
`~/.claude/plans/the-branch-features-deep-review-has-imperative-pearl.md`.
Branch `ui/deep-review-shell`, off `perf/deep-review-findings`.

**Measured**: a fresh window on MOF-5 gives the viewport 388 of
1285 px (30 %), and 133 px at 1024x700.  `closeEvent` stops a run
before asking about unsaved edits, so Cancel does not bring it back.
Nothing is autosaved.  17 styles hard-code the light-theme amber.

**Every new string is a placeholder** for the next ui-text batch
(§ 1, Phase 2); tests assert on mechanism, never on wording.

| Phase | Delivers | Main files | Size |
|---|---|---|---|
| **0 — The silent class** | Shipped 2026-09-22 (98c005d). Non-object `workspace.json`, session paths outside the root, a BOM or Latin-1 byte, a second CIF block, a bond operation outside the group, two runs at once, `convert a a`, a misspelt `-p` | `xtal/workspace.py`, `xtal/io/text.py`, `xtal/io/cif_reader.py`, `xtal/cli.py` | S |
| **1 — The first minute** | Shipped 2026-09-22. The viewport gets 47 % of the window on a first run (603 of 1285 px, 342 at 1024 wide; Structure keeps its 380); a start pane (open, drop, samples) in the empty window | `xtalapp/layout.py`, `xtalapp/widgets/start_pane.py` | S |
| **2 — Say why** | Shipped 2026-09-22. A greyed module gets a row of its own in the Modules panel with its reason, opening Preferences ▸ Engines (the menu only gains visible tooltips, because the submenu stays greyed); a `NoticeBar` over the middle of the window explains  the first CIF-to-project save once; open and save errors are logged, and a missing file is said plainly | `xtalapp/menus.py`, `xtalapp/docks/modules.py`, `xtalapp/documents.py` | S |
| **3 — Don't lose work** | Shipped 2026-09-22. Quit asks before stopping a run; autosave to `<workspace>/.autosave/`, offered back as one undo step when the entry opens | `xtalapp/autosave.py`, `xtalapp/mainwindow.py`, `xtalapp/workspace_shell.py` | M |
| **4 — Both themes** | Shipped 2026-09-22. `xtalapp/widgets/tone.py`: hint, warning and warning-box tones worked out from the palette, 55 literals replaced, restyled on a theme change; *View ▸ Background ▸ Follow the system*, the default for a structure with no view of its own | `xtalapp/widgets/`, `xtalapp/view_settings.py` | S |
| **5 — The Workspace tree's menu** | Shipped 2026-09-22. Open, Reveal in Finder, Copy Path and Move to Trash (a run folder only, through `QFile.moveToTrash`), as four registry actions in `CONTEXT_MENUS["workspace"]` | `xtalapp/docks/filetree.py` | S |

All six shipped on `ui/deep-review-shell`, 2026-09-22.  CLAUDE.md
gained three invariants on the way: the autosave as a side file, the
order the quit asks its two questions in, and a colour nobody chose
being worked out from the palette.  What the UI review found and this
track did not take is in [docs/TODO.md](TODO.md) § Interface; every
new string is owed to the next ui-text batch (§ 1, Phase 2).

---

## 6. One decision, one place: the factoring track

Planned 2026-09-23 from `review/reports/factoring.md` on
`features/deep-review`, none of whose ten findings had been touched
once the performance and shell tracks shipped.  The recurring fault is
not tangle but **the same decision written down twice**, and every
pair the review checked had drifted -- two of them into live bugs.
Doing this before the uMLIPs and EQeq means each of those is written
once against a shared base, not copied a fifth time.  The full plan is
`~/.claude/plans/the-branch-features-deep-review-has-witty-dolphin.md`.
Branch `refactor/deep-review-factoring`, off `main`.

| Phase | Delivers | Main files | Size |
|---|---|---|---|
| **0 — One enablement rule** | Shipped 2026-09-23. `shell_state.selection_states` is the one answer for the selection's actions; both refresh paths apply it, so clicking an atom during playback no longer re-enables Cut, Duplicate and Delete | `xtalapp/shell_state.py`, `xtalapp/mainwindow.py` | S |
| **1 — A build is filed by the core** | Shipped 2026-09-23. `Workspace.adopt_build` takes the filesystem half of `ModuleRunner._file_build`; `xtal run mof.build --workspace` files a build the way the window does | `xtal/workspace.py`, `xtalapp/module_runner.py`, `xtal/cli.py` | M |
| **2 — A Force Field run is recorded by the core** | Shipped 2026-09-23. `xtal/ff/record.py` `open_run` / `close_run`, mirroring the modules'; the dock and the CLI call it, and the failure path exists once | `xtal/ff/record.py`, `xtalapp/docks/ff_panel.py`, `xtal/cli.py` | M |
| **3 — Chemistry out of the shell** | Shipped 2026-09-23. The MOF preview draws the block's own bonds (all 879 shipped blocks have them; the old rule drew 9401 they do not), or the core's rule for a block with none, `bond_distance` moves to `xtal.core.bonding`, and the headless test imports every core module | `xtalapp/dialogs/mof_preview.py`, `tests/test_core_is_headless.py` | S |
| **5 — Small decisions made twice** | Shipped 2026-09-23. One stop record in `OptimizationWorker`; `ff_panel.panel_options` the one reader of the engine panels, for the scan and the DFTB+ run; `xtal.workspace.resolved` the one "same file" answer | `xtalapp/workers.py`, `xtalapp/dialogs/scan.py`, `xtalapp/dialogs/dftb_run.py` | S |
| **4 — Engines share their plumbing** | Shipped 2026-09-23. `Engine.__call__` coerces; an `ExternalCalculator` base for DFTB+ and xTB; an `ASECalculatorEngine` base under MACE; one charge-source list | `xtal/ff/registry.py`, `xtal/ff/api.py`, `xtal/ff/*/calculator.py`, `xtalapp/docks/ff_panel.py` | M |
| **6 — One registry shape** | Shipped 2026-09-23. A `Registry` generic the three registries subclass; report blocks rendered by table, not `isinstance` | `xtal/params.py`, `xtal/*/registry.py`, `xtalapp/docks/results.py` | S-M |
| **7 — Split `mainwindow.py`** | Shipped 2026-09-23. A pure move into three mixins, one seam per commit: refresh/enable to `shell_state.ShellRefresh`, symmetry and cell to `symmetry_actions.SymmetryActions`, edit/select/measure to `edit_actions.EditActions`; 2014 -> 1093 lines | `xtalapp/mainwindow.py`, `xtalapp/shell_state.py` | M |

The table is in the order the phases are done; 5 comes before 4
because it is small and 4 is easier with the stop and panel readers
already single.  **After it**: uMLIPs on `ASECalculatorEngine` (ORB-v3,
then MatterSim and SevenNet), EQeq on the single charge-source list,
and the CCDC-headed sample files, which need a decision first because
`MFU4l.cif` is the suite's stress case.

---

## 7. More engines, EQeq, and a COD sample library

Planned 2026-09-23 as the fourth track from `features/deep-review`
(`review/PLAN.md` § Phase 2), and the one the factoring track's two
seams were built for: `xtal/ff/ase_engine.py` has MACE as its only
subclass, and `CHARGE_SOURCES` has nothing new in it.  Julius's
answers: all three licence-clean uMLIPs (UMA and eSEN are out -- gated
or research-only weights), EQeq alone (EQeq+C's table is paywalled),
and a COD library *beside* the shipped samples rather than replacing
them.  The full plan is
`~/.claude/plans/all-three-umlips-eqeq-wise-tiger.md`.  Branch
`features/deep-review-engines`, off `main`.

| Phase | Delivers | Main files | Size |
|---|---|---|---|
| **0 — Pin what the review found unpinned** | Shipped 2026-09-23. Tests only, each checked by putting its regression back: the QSettings scratch guard (`test_suite_guards.py`), the √2 strain metric (holding *b* of quartz in P1: 1e-14 scaled, 6.2 flat), the Zeo++ radii test reading an excerpt in `tests/data` instead of skipping, the workspace-switch question asked once | `tests/` | S |
| **1 — ORB-v3** | Shipped 2026-09-24. `xtal/ff/orb`, conservative models only, double precision by default (float32's error is a third of a 1e-4 A step's energy change), CPU or CUDA -- orb-models 0.7.0 cannot use mps. MOF-5 0.94 s an evaluation in float32 and 2.58 s in float64, against MACE-MPA-0's 3.32 s. Before it, Preferences > Engines was put right: rows for MACE and ase, and a command that names this interpreter and this checkout | `xtal/ff/orb/`, `pyproject.toml` | M |
| **2 — EQeq** | Shipped 2026-09-24. `ewald.pair_matrix` (every entry independent of the split, background included), EQeq on `qeq._solve` with the paper's charge centres, lambda 1.2 and hydrogen at -2 eV, one row in `CHARGE_SOURCES`. The table is package data, `xtal/ff/charges/data/ionization.csv`, written by `scripts/eqeq_table.py` from the NIST ASD ionisation export and PubChem's electron affinities (ASD has none), both kept in `tests/data/eqeq/`. MOF-5: Zn +1.210 against the authors' program's +1.211, no atom off by more than 0.05 e, 0.5 s | `xtal/ff/charges/`, `xtal/ff/ewald.py`, `scripts/eqeq_table.py` | M |
| **3 — MatterSim** | Shipped 2026-09-24. `xtal/ff/mattersim`, the 1M and 5M models, double precision by default (float32 gets a 1e-4 A step's energy change wrong by 7 %; float64 costs 1.5x), CPU or CUDA -- on macOS 13 MatterSim loads onto mps without asking and segfaults, so `torch_device(allow_mps=False)`, which ORB now shares. MOF-5 0.51 s an evaluation in float64, the fastest of the three. mattersim declares e3nn>=0.5 against MACE's pinned 0.4.4; its inference runs on 0.4.4, so `.venv` has it by `--no-deps` plus torch_runstats, loguru and deprecated, and Preferences > Engines says how | `xtal/ff/mattersim/`, `pyproject.toml` | S |
| **4 — SevenNet** | Dropped 2026-09-24, Julius's decision.  sevenn 0.13.0 refuses to import below e3nn 0.5 ("changes in CG coefficient convention") -- a real change, not metadata -- and every mace-torch release to 0.3.16 pins e3nn to exactly 0.4.4, so the two cannot share a Python.  Running it out of process was the alternative; ORB-v3 and MatterSim already cover the licence-clean universal potentials | -- | -- |
| **5 — COD library** | Shipped 2026-09-23. Six CC0 structures (COD 1516287, 4002052, 7249359, 4512072, 4000663, 7230579) in `resources/samples/cod/`, each the COD's CIF with `_refln`, `_diffrn`, embedded SHELX files and SQUEEZE removed whole item by whole loop and every other byte kept (UiO-66 286 KB to 13, NU-1000 301 to 15), written by `scripts/fetch_cod_samples.py`. Open Sample has them in a *From the COD* submenu and the start pane under a heading -- a section title is not drawn in a native macOS menu, and both groups have a MOF-5 -- and each entry is named with its number (`MOF-5_COD_1516287`). `PROVENANCE.md` names all sixteen files, with the CCDC decision. The bundle now walks subfolders of `resources/samples`, which it did not. MIL-101 is 16 000 atoms and opens in 2.9 s. Seven more asked for the same day: MIL-100(Fe) 7102029, MOF-74(Zn) 1517474, PCN-222(Fe) 4329555 (as MOF-545(Fe)), MOF-808 4121463, MIL-53(Cr) 1502688, MIL-88B(Cr) 7100637 and Mn-BTT 4111257; a powder profile is stripped too (MOF-74 104 KB to 9). MOF-303, Cu3(HHTP)2 and Cr-red-MOF-1 are not in the COD. Then cubic-EuHOTP 4134597, pbz-MOF-1 4130966 and Al-soc-MOF-1 4129499 (13 MB and 7.5 MB downloads, 17 KB and 12 KB stripped). With them the default style became Ball and stick (occupancy), and the Force Field panel's optimiser Smart, as the scan's already was | `resources/samples/cod/`, `xtalapp/samples.py`, `xtalapp/menus.py` | S-M |

Phases 1, 2 and 5 each downloaded something (weights, the NIST table,
the COD files) and asked before they did.  No model is ever loaded in the
test process; see CLAUDE.md "Aborted runs".

---

## 8. Porosity in seconds, beside Zeo++

Planned 2026-09-25, after asking why iRASPA reports surface area and
pore volume at once.  It reads everything off one grid, and we
already build that grid to draw the pore surface.  Zeo++'s `-volpo`
is 68-108 s per sample on this machine.  The grid's POAV on MFU-4l is
0.7805 against Zeo++'s 0.7792, in 0.5 s.  Where there are two
methods both are offered, and Julius's answer on placement: one
group, renamed **Porosity** (the key stays `zeopp`), with each
**"(faster)"** entry under the Zeo++ entry it replaces.  A missing
binary greys only the Zeo++ entries.  The full plan, with every
measurement, is `~/.claude/plans/fast-porosity.md`.  Branch
`features/fast-porosity`, off `main`.

What the measurements decided, so a phase can start from here:

* **Area by Monte Carlo on the spheres, not from the mesh.**  The
  marched mesh reads 2-3 % low (MOF-5 3626 Å² against Zeo++'s 3727),
  because tetrahedra flatten a sphere into chords.  Sampling the
  spheres is within 1 %.  The mesh stays the picture.
* **Two grid points are linked only when the segment between them
  is clear.**  Face neighbours alone gave HKUST-1 104 false pockets.
  All 26 neighbours on their endpoints let N2 through ZIF-8's 3.27 Å
  windows.  Asking the field at the segment's middle as well got both
  right (a half-step chord dips at most 0.005 Å into a sphere), in
  0.48 s on MFU-4l against 4.5 s for testing every atom along it.
* **A window within half a grid step of the probe is flagged, never
  guessed.**  UiO-66's windows clear N2 by 0.045 Å, and the grid's
  answer flips between 0.4 and 0.3 Å spacing.  The report names
  Zeo++'s Pore diameters entry as the way to settle it.
* **POAV counts a point as occupiable when it is within `g(a)` of an
  accessible grid point `a`, not within the probe radius.**  The
  distance field changes by at most 1 Å per Å, so there is accessible
  space between the grid points too.  The probe-radius criterion read
  ZIF-8's PONAV 0.021 low; this reads it 0.004 from Zeo++.
* **POAV reads above Zeo++'s `-volpo`, and Zeo++ is the one short.**
  MIL-53 0.659 against 0.651, HKUST-1 0.677 against 0.654.  Probe
  spheres centred on a 0.15 Å grid of real probe positions already
  cover 0.663 and 0.679, so the true value is at least that.  POAV is
  pinned to that brute force and to a lone sphere's exact geometry,
  not to Zeo++, and the report says so.

| Phase | Delivers | Main files | Size |
|---|---|---|---|
| **0 — Every core for the grid** | Shipped 2026-09-25. `distance_grid` queries the KD-tree with `workers=-1`: MFU-4l 1.03 s → 0.22 s, the same array | `xtal/analysis/grid.py` | S |
| **1 — Channels and pockets** | Shipped 2026-09-25. `voids.classify`: segment links gated at the middle, periodic union-find over component IDs (`findChannels`'s test), `borderline`. The Zeo++ volume run stops drawing pockets as channels | `xtal/analysis/voids.py`, `xtal/modules/zeopp.py` | M |
| **2 — The numbers off the grid** | Shipped 2026-09-25. `voids.surface_area` (Fibonacci points on the spheres, 0.1-0.9 % from Zeo++) / `voids.volume` (AV within 0.0035 of the cell; POAV by the bound above), returning `porosity.SurfaceArea` / `Volume`, and `poregrid.surface_area` / `volume` runs on Zeo++'s report with a grid note and a *Resolution* row when borderline; a radii file is read. MFU-4l: area 1.1 s against `-sa -ha`'s 7.5 s, POAV and its surface 1.7 s against `-volpo`'s 71 s. Zeo++'s numbers are recorded in `tests/data/zeopp_reference.json` | `xtal/analysis/voids.py`, `xtal/modules/poregrid.py` | M |
| **3 — The (faster) entries** | Shipped 2026-09-25. Module labelled Porosity (key still `zeopp`), the Zeo++ check per entry, **Surface area (faster)...** and **Accessible volume (faster)...** under their Zeo++ twins with no channel radius or accuracy switch and a grid spacing instead; the Modules panel greys entry by entry and `Module.blocked` keeps the reason row; `xtal run` now checks the entry as well as the module, and the window's availability refresh re-asks the entries, so naming the binary in Preferences lights them without a restart. MFU-4l's occupiable volume and surface in the window: 2.1 s | `xtal/modules/zeopp.py`, `xtalapp/docks/modules.py` | S-M |

All four shipped on `features/fast-porosity` and were merged to `main`
on 2026-09-25.

---

## 9. Prepare for simulation

Built 2026-09-24/25 on `features/prepare-for-simulation`, outside the
tracks above, and merged to `main` on 2026-09-25: Structure ▸ Prepare
for simulation… and `xtal prepare`, one rebuild and one undo step over
`xtal/core/prepare.py`.  CLAUDE.md's invariant *Preparing for
simulation is a rebuild* is the design; `git log -- xtal/core/prepare.py`
is what each step measured.  What it does, in order: sites written
twice merged, deuterium, the declared centring's primitive cell,
disorder ordered into whole components (including two orientations at
full occupancy, and an atom too close to an image of its own site),
solvent out, M3O trimers completed (`prepare.CHEMISTRY`, never a
default), hydrogens.  Every shipped COD framework prepares clash-free
with every hydrogen bonded; `resources/samples/prepared/` holds the
results, written by `scripts/prepare_samples.py`, and Open Sample ▸
*Prepared for simulation* opens them.  Nothing is left owed.

---

## 10. The deep review's hit list: engines, reliability, nets

Three pull requests from `review/HITLIST.md`, each a series of
one-change commits with its measurements in the PR, merged to `main`
together on 2026-09-25 after the full suite passed on the combination.
The decisions they asked for are in [docs/TODO.md](TODO.md).

| PR | Delivers | Main files |
|---|---|---|
| **#21 — Engines and charges** | EQeq centres for every metal at its common oxidation state (Al-soc-MOF-1 was Al +6.33), overridable, impossible charges named, 0.00016 e from the authors' own program on MOF-5. ORB-v3's and MatterSim's "double precision" was float32 geometry, now float64 end to end (slope against force 2e-3 → 6e-9). The MOFSimBench claims now say they are model + D3. **MACE-MP-MOF0**, fetched from a pinned commit and loaded only on a matching SHA-256, through its `pbe_d3` head, refusing its 26 elements' outsiders by name | `xtal/ff/charges/eqeq.py`, `xtal/ff/{orb,mattersim,mace}/` |
| **#22 — Reliability** | Return adopts in Find symmetry; deuterium computed as hydrogen by every engine but DFTB+'s modes; accented names keep their letters; an empty `.gen` refused; `--supercell` names its size. A run's program no longer outlives Ctrl+C, SIGTERM or the interpreter, and Stop no longer blocks the window. A stated bond order survives a cell-face crossing, and the Inspector's bond lengths are live. `--selftest` on the macOS CI runners | `xtal/modules/process.py`, `xtal/core/bonding.py`, `xtal/workspace.py`, `.github/workflows/ci.yml` |
| **#23 — Nets** | The RCSR's `p q r s` transitivity for 4001 nets, from its own data files (`scripts/rcsr_transitivity.py`), correcting q on 18; MOF-5's and rutile's exported `.cgd` run through Systre 19.6.0 (pcu, rtl) and kept as test data | `xtal/analysis/netsearch.py`, `tests/data/systre/` |

Merging the three onto today's `main` turned up one failure that CI
could not: #21's `test_every_model_offered_is_a_name_mace_knows` held
`mace-mp-mof0` to mace's name table, which it is not in, and CI has no
mace to run it.  Fixed on the merge; the gap is in
[docs/TODO.md](TODO.md) § Testing.

Also shipped on 2026-09-25, too small for a section: **Select ▸ Bonds
between elements…**, every bond joining two elements selected with no
atoms, so Delete and Bond type act on those bonds alone.

---

## 11. Powder refinement: peaks, indexing, Pawley, Rietveld, energies

Planned 2026-09-25.  Julius asked for refinements against a measured
pattern, TOPAS Academic the model: peak fitting, indexing over a
chosen set of Bravais lattices or space groups, Pawley, Rietveld that
can be watched, an automatic run through all of them, and Rietveld
with energies plus a Pareto search for its weight, as Materials
Studio has.  **The physics is wrapped, not written**: RietX 1.5
(MIT, pip, numpy/scipy/numba, `rx.Refinement`, `rietx.indexing`), as
a `refine` extra pinned below 1.6 -- 95 k lines is not a thing to
vendor.  Julius's TOPAS inputs are in `resources/pxrd/` (ignored).
The full plan, with its measurements, is
`~/.claude/plans/powder-refinement.md`.  Branch
`features/powder-refinement`, off `main`.

What the measurements decided, on RietX's own fluorapatite (lab Cu
Kα doublet, 5753 channels, swap at 13.5 GB so upper bounds):

* **Peak picking is seconds, indexing is a minute, Rietveld is two
  seconds.**  `pick_peaks` 6.6 s for 191 peaks; `index_pattern`
  restricted to hexagonal with a 60 s budget 62.6 s, top candidate
  a = 9.374, c = 6.888; a staged Rietveld 1.4-2.0 s.  So indexing is a
  worker with a budget box and Stop, never the GUI thread.
* **RietX will not name a winner its engines disagree on**:
  `best_or_none()` was None with the right cell ranked first.  The
  table shows its confidence column rather than inventing one.
* **An `eval` event carries the free values, never y_calc**, so a
  live frame is a shadow model's `predict`, throttled to the Force
  Field panel's preview interval; the atoms move through
  `Document.preview_positions`, as an optimisation's do.
* **There is no custom cost term in RietX's solver**, so Rietveld
  with energies is our L-BFGS over `SymmetryDOF`, the pattern term's
  gradient from RietX's (private) analytic Jacobian and the energy's
  from the Force Field panel's engine.  Only `xtal/powder/bridge.py`
  imports rietx.
* **RietX writes `.rietx/runs` into the working directory unless told
  otherwise**; every call is told the run folder, and a test holds it.

Julius's answers: RietX as an extra; a **Refinement workbench** window
(steps down the side, obs/calc/difference in the middle, the form on
the right); R+E moves the **atoms only** by default, the cell held;
the automatic run **stops at the ranked Pawley table** unless *Continue
to Rietveld* is ticked.

| Phase | Delivers | Main files | Size |
|---|---|---|---|
| **1 — Data, radiation, bridge** | Shipped 2026-09-25. `PowderData.from_xy` (σ from a third column only when every row has a positive one), `Radiation` onto RietX's own presets (no wavelength table of ours), `bridge.phase_of` / `apply_phase` site for site with dummies left out and remembered, `bridge.fit` never recording into the cwd. Re-measured: FAP's `mccusker_default` fit is 1.5 s (the 992 s was swap) -- **and that plan frees no atoms**, so Phase 5 builds on `mccusker_structural` or its own stages | `xtal/powder/data.py`, `xtal/powder/bridge.py`, `pyproject.toml` | S-M |
| **2 — Workbench and peak fitting** | Shipped 2026-09-25. Modules ▸ PXRD ▸ *Refine against a measured pattern…* (`refine_workbench`, one window per document; a `.xy` double-clicked in the workspace opens there too); obs/calc/background/difference on counts with a tick comb, updated in place for live frames; peak fitting after `a_peak.inp` (range, shoulders, Kβ/W flags, *fit only at*), a *Use* box per line that reaches indexing as RietX's own `excluded`. The steps are PXRD entries with `listed=False`, so `xtal run pxrd.peaks` runs headless; `Job.update` / `ModuleWorker.updated` carry frames; `JobResult.answer` carries the fit back. Found: RietX's windows can fit one line twice (rutile's 101) and can stop short of a Kα2, so a twin is flagged `duplicate` and the curve is redrawn from the fitted lines with the doublet put back -- rms 0.2 % of the tallest peak. TOPAS's background order and size/strain are Pawley's options, not this step's | `xtalapp/refine/`, `xtal/powder/peaks.py`, `xtal/modules/powder.py` | M-L |
| **3 — Indexing** | Shipped 2026-09-25. The workbench's *Index* step and `xtal run pxrd.index`: fourteen Bravais boxes (hP is RietX's hexagonal and trigonal P together), a space-group list that narrows the search to its lattices and keeps only the extinction classes holding a chosen group (compared by number, so C2221 matches A 21 2 2), zero-error allowance, largest volume, **longest axis** (RietX's 25 A default is short for a framework -- 31.5 A in Julius's b_indy -- and 6 A searches rutile in seconds), a time budget, and space groups ranked for the top *N* cells. The table is TOPAS's `.ndx` (`cells.csv`); a chosen row draws its lattice's lines under the peaks. RietX's `best_or_none` is the only winner shown, and on synthetic rutile it names none with the right cell first. `Job.given` hands the ticked peaks from one step to the next; Stop keeps the cells reached. Measured under 14 GB swap: tetragonal to 25 A 25 s, to 6 A 8 s; six systems to 10 A 58 s | `xtal/powder/index.py`, `xtalapp/refine/bravais.py` | M |
| **4 — Pawley** | Shipped 2026-09-25. The workbench's *Pawley* step and `xtal run pxrd.pawley`, after `c_paw.inp`: cell and group (filled from the chosen indexing row -- its best class's group, or the lattice's own when none was ranked -- or from the open structure), 2θ range, Chebyshev terms (8), zero (on), specimen displacement (off: RietX reports it ρ = 1.000 with zero on rutile, and never for a capillary), cell, size and strain. RietX's Le Bail scaffold, a plan in `pawley_default`'s order with only the asked stages. Result: Rwp/Rp/Rexp/GoF, the cell with esds in the last digit, the hkl list (`reflections.csv`, `fit.xy`). *Apply cell to the structure* is one undo step, fractional coordinates kept, offered only for the same system, centring and setting (every length within 5 %, every angle within 2°); *New structure from this cell* is File ▸ New with that cell and group. Rutile from indexing's 4.5948 / 2.9572: 4.59398(4) / 2.95897(3) against 4.594 / 2.959, GoF 1.02, 0.6-2 s | `xtal/powder/pawley.py` | M |
| **5 — Rietveld, live** | Shipped 2026-09-26. The workbench's *Rietveld* step and `xtal run pxrd.rietveld`, after `d_riet.inp`: boxes free, in McCusker's order, background (scale always), zero, displacement, the cell number by number, the peak shape, size, strain, positions (along each site's allowed directions), Biso, occupancies (off) and March-Dollase texture about a typed axis -- or one of RietX's four structural plans instead. Frames: a shadow model set to each accepted `eval`'s free values, **the atoms put back to the start first** (a coordinate is a step from where the atom is, so a shadow handed one step twice walked twice as far), throttled to the preview interval or three times the last frame's cost -- a frame is 5 ms on rutile and 0.7 s on MFU-4l under 13 GB swap. The atoms move by `preview_positions`; a finished fit is one `replace_structure` undo step on the document the window was opened over, Stop or a failure puts them back; site count and bonds checked, dummies never sent. Rutile from x(O) = 0.29: 0.3053, GoF 1.02, 0.2 s. Every box that refined something has its numbers beside it (`refined_notes`), the Pawley step too. | `xtal/powder/rietveld.py` | L |
| **6 — Automatic** | peaks → index → top cells × extinction classes → Pawley → ranked table, optionally → Rietveld on a matching open structure | `xtal/powder/auto.py` | M |
| **7 — Rietveld with energies** | `(1−w)·χ²/χ²₀ + w·(E−E₀)/ΔE` over the asymmetric unit, any engine the Force Field panel has | `xtal/powder/energy.py` | L |
| **8 — Pareto** | A weight sweep written point by point, the non-dominated front, the knee suggested; a point opens its structure | `xtal/modules/powder.py` | M |
| **9 — Packaging, CI, docs** | rietx and its data in the bundle, `NUMBA_CACHE_DIR` writable, `--selftest`; CI installs `refine` if the tests stay short | `packaging/`, `.github/workflows/ci.yml` | S-M |

Revised 2026-09-25 after Julius used phases 1-4.  The Peaks step
gained *Refine peaks* -- one least-squares fit of the lines in use
over a Chebyshev background of *Background terms*, the unticked lines
dropped (`peaks.refine_peaks`, ours on `scipy`: RietX has no
whole-pattern peak fit without a cell) -- lines placed by hand at typed
2θ, and each line drawn on its own with a toggle; *Run* says what the
step does.  Indexing: a box per crystal system, the zero allowance
0-1° in 0.1° steps defaulting to 1°, the longest axis to 50 Å, a GoF
column (M20, or M_sym under twenty lines) and sorting by GoF or GoF /
(unindexed + 1).  **Measured: at a 1° allowance a wrong cell ranks
first on rutile** (right up to 0.3°, wrong from 0.5°), and the tests
pin 0.  Pawley defaults to displacement, cell, size and strain free
and zero held.  Fit ranges start at the data's own.  The window no
longer falls behind the main one after Load .xy (a native dialog hands
activation back).

Revised again 2026-09-26, with Phase 5.  The zero allowance defaults to
0.3°, the widest that ranked rutile's right cell first.  Every plot --
the workbench's and the PXRD pattern window -- draws intensity linear,
square root (signed, so a dip below zero survives) or logarithmic; the
difference stays linear, and the tick combs moved to a strip of their
own, because a logarithm has no below zero to hang them in.  Ticking a
peak in or out keeps the zoom.  The Pawley cell is the numbers the
group leaves free (`xtal/powder/cell.py`: one length for cubic, three
and the unique angle for monoclinic, gemmi's qualifier saying which),
each with a Refine switch -- `hold` on the command line -- and the
tied ones derived; RietX is asked which cell paths are untied rather
than told, so a held number is never one it would refuse.

What the phases must keep: a refinement moves atoms and never adds,
removes or bonds them (site count asserted, `hold_perception`); dummy
atoms held back at the door; the result goes to the document the run
started from; a sweep writes each point as it finishes and an
unconverged one is NaN; R+E reads the engine, it does not configure
one.

---

## 12. What this plan does not do

* It does not touch the design principles in
  [docs/PLAN.md](PLAN.md) § 1.  Every phase keeps the core Qt-free,
  keeps every mutation a command, and adds capability through
  registries.
* It does not schedule volumetric data or SHELX round-trips.  Those
  are [docs/PLAN.md](PLAN.md) § 12 and stay there until they are asked
  for.  Rietveld was asked for, and is § 11.
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
