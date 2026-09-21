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
