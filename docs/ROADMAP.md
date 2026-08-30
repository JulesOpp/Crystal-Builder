# Crystal Builder — delivery plan for the TODO

[docs/PLAN.md](PLAN.md) is the architecture and the roadmap that got
the application built; [docs/TODO.md](TODO.md) is everything that came
out of using it and has never been scheduled.  This file schedules it:
what order, what each phase delivers, what it is allowed to touch, and
what has to be true before the next one starts.

Every phase ends with something runnable and a green suite, which is
the same rule [docs/PLAN.md](PLAN.md) § 16 works to.  Sizes are orders
of magnitude, not estimates: **S** is a day or less, **M** a few days,
**L** a week or more, **XL** a project of its own.

---

## 1. Three foundations, and why the order matters

Most of TODO.md is small and independent.  Three things in it are not,
and nearly everything else is cheaper, smaller or more honest once they
exist.

**Change hints, honoured.**  `Document.structureChanged` already
carries a `Change` flag and two of its three receivers throw it away,
so every edit rebuilds every panel and re-derives everything the
structure caches.  That single fact is what makes the force field feel
slow, and it is also what will make trajectory playback feel slow, and
volumetric data, and anything else that moves atoms without changing
what they are.  Fix it once, at the bottom.

**A stored bond graph.**  Bonds are re-perceived from a distance
criterion after every mutation.  Until they are stored, the bond rules
dialog cannot show what *changes*, topology bonds have nowhere to live,
per-bond orders in the picture get recomputed under the camera, and the
viewport keeps rearranging itself while the user works.

**The module registry and the workspace.**  A module that runs an
external binary, writes a trajectory and a log into a folder, and
appears in a tree, is one piece of machinery.  DFTB+, Zeo++, the log
viewer, the trajectory player and the session tree are all consumers of
it.  Writing it once means the second external tool costs a fraction of
the first.

```
    1. change hints ─┬──> solver speed            (Phase A)
                     ├──> trajectory playback     (Phase C)
                     └──> large-structure edits   (everywhere)

    2. stored bonds ─┬──> bond rules dialog       (Phase B)
                     ├──> bond order in the view  (Phase G)
                     └──> topology bonds          (Phase G)

    3. modules and ──┬──> log viewer              (Phase C)
       the workspace ├──> trajectory artefacts    (Phase C)
                     ├──> Zeo++                   (Phase H)
                     └──> DFTB+                   (Phase H)
```

Foundation 3 is the one that gets split.  Phase C needs the workspace
half of it -- somewhere for artefacts to land -- before it needs the
registry half, so the workspace is built in C and the registry in D.
That is the only place the ordering here is a judgement rather than a
constraint; the alternative is building all of D first, and nothing
useful would be on screen for two phases.

---

## 2. Cheap wins, available at any time

Each of these is a day or less, depends on nothing, and can be pulled
out of its phase whenever the pain is worth a detour.

| Item | TODO section | Size |
|---|---|---|
| Readable UFF atom type descriptions | Force field | S |
| Invert the structure | Symmetry | S |
| Invert Selection ignores symmetry | Selection | S |
| Arrow buttons on translate and rotate | Editing | S |
| Bonds inside polyhedra | Appearance | S |
| Cutoff and skin controls | Force field | S |

---

## 3. Phase A — make it behave ✅

**Goal:** the application stops doing things nobody asked for, and an
optimisation is limited by the solver rather than by the redraw.

Shipped.  What it cost, measured on MFU-4l reduced to P1 and on its
2×2×2 supercell:

| | 648 sites | 5184 sites |
|---|---|---|
| solver step | 14 ms → 14 ms | 163 ms → 112 ms |
| redraw after a step | 100 ms → 4 ms | 800 ms → 63 ms |
| van der Waals pair list | — | 4.0 s → 0.49 s |

and the redraw no longer happens once per step at all: the solver
announces every step, the viewport draws whatever the geometry is when
its timer fires, and how often that is is a control in the panel with
"every step" and "not while it runs" at its ends.

What landed:

* **Backspace deletes**, along with Del, and VTK's own single-letter
  hotkeys (`e` and `q` closing the render window, `w`/`s` switching it
  to wireframe, `3` toggling stereo over our own "look along c") are
  swallowed before they reach it.
* **The window fits the screen it opens on**, on a first run and on a
  geometry restored from a bigger monitor -- which was the one with no
  way out of it -- and only the file tree and the Inspector are open,
  with `Window ▸ Reset layout` to get back.
* **Change hints are honoured end to end.**  `Structure.cached` takes
  an invalidation mask, so a geometry change drops the P1 expansion and
  keeps the bond graph, the atom typing, the formula and the density;
  the viewport moves points rather than rebuilding actors
  (`VtkScene.set_positions`); the window refreshes the panels that
  show coordinates and leaves the rest; and previews travel on their
  own signal (`Document.previewChanged`) so they reach the viewport
  and nothing else.  `_on_structure_changed` was also calling
  `_update_ui`, which rebinds every panel and undid every skip.
* **The P1 expansion is array work**, 43 ms → 3 ms for 5184 sites: it
  is on the path of every geometry change and was a Python loop.
* **The pair list is array work**: `sparse_distance_matrix` instead of
  a loop over `query_ball_tree`'s lists, an int64 code per pair instead
  of a tuple for the exclusion test, and a per-type-pair table instead
  of two square roots per pair.
* **A context menu** on atoms, bonds and empty space, built from the
  action registry, which selects what was clicked when it was outside
  the selection and says how many it will take when it was inside.

Two things were pulled forward out of Phase B, because the phase was
incoherent without them: **bonds no longer change when atoms move**
(the memo does what the stored graph was going to do, minus
persistence -- see *Store the bond graph*), with `Structure ▸
Recalculate bonds` as the thing that changes them; and **Delete bond**
is its own action, which is what a right click on a bond needed to be
able to offer.

**Tests.** 769 passing, 53 of them new.  The pair-list rewrite is
pinned against a brute-force reference that looks at every image
(`tests/test_pair_lists.py`), the cache mask is enumerated flag by flag
(`tests/test_change_hints.py`), and the redraw claims are asserted by
counting calls rather than by timing anything.

## 4. Phase B — bonds you control ✅

**Goal:** the bond graph is a thing the user owns, and it survives
being saved.

Shipped.  Most of what this phase was for shipped in A; what landed
here is the half that needed a stored field rather than a memo.

**The graph is stored.**  `Structure.perceived` holds the
distance-perceived bonds of the P1 cell -- written on the first read,
saved into `bonds.json`, and from then on the answer.  Reopening a
project no longer re-perceives over whatever geometry it finds, so a
graph you recalculated is the graph you get back.  Three things travel
with it, and each of them stops a stored graph being quietly wrong
later: the `BondRules` signature it came from, so changing the rules
perceives again instead of being ignored; the cell's elements, so a
graph over a different crystal is recognised rather than reused; and
the wrap each atom was drawn at.

**Adding an atom perceives that atom.**  The expansion is site-major,
so an appended site appends its images -- which the store recognises as
a *prefix* and answers by searching from the new atoms only
(`neighbors.neighbor_pairs(..., subset=)`).  Everything already in the
graph is left exactly as it was, which is the behaviour that was
wanted and not merely the speed.

**`Recalculate bonds` is a command.**  Replacing a stored graph is a
change like any other, so `RecomputeBonds` is on the undo stack.

**A preference**, `Bonds follow the geometry`, off by default, for
people building by hand who want to drag two atoms together and see
the bond form.  It follows committed edits, not previews: re-perceiving
two hundred times during a relaxation would cost more than the
relaxation.

**The bond rules dialog**, `xtalapp/dialogs/bond_rules.py`, which
[docs/PLAN.md](PLAN.md) had been listing since before phase 1.  A
radius factor with the bond count beside it (the plateau from 1.05 to
1.45 and the jump at 1.6 are both invisible on a slider alone),
`allow_metal_metal` as a control of its own rather than a finer
tolerance, a per-pair table built from the elements actually present,
and a preview that says *what changes* -- "6 added, 2 removed" -- because
a total hides the setting that swaps one bond for another.  Previewing
passes the rules to `perceive` explicitly, which is a question and
neither reads nor overwrites the stored graph.

**A bond that crossed a cell face.**  Found while debugging a
relaxation of MFU-4l and fixed here because it is the same machinery:
`CellBond.image` counts lattice translations between *wrapped*
positions, so an atom relaxing past x = 0 is redrawn at x = 1 and every
bond it is in was left pointing at where it used to be -- a line the
full width of the crystal, and a bond count that flickered from frame
to frame.  The wrap is now carried with the graph and the images are
moved onto the current one (`bonding.rebase`).  Nothing crossed a face,
which is almost every frame, costs one array comparison.

**Tests.** 43 new, in `tests/test_stored_bonds.py` and
`tests/test_bond_rules_ui.py`.  A project round-trip keeps the graph
including the suppressions layered on it; an add perceives only the new
atom's bonds and gives the graph a full perception would; the drawn
length of a bond is asserted across a cell face.

**Risk, as written before the phase and still true.**  The rule about
which changes force a re-perception is a judgement, and getting it
wrong is invisible.  It is written down in
`xtal.core.structure.CHEMISTRY`, enumerated in
`tests/test_change_hints.py`, and now also in what
`bonding._by_distance` will and will not reconcile; keep it that way.

### Shipped alongside: two force-field bugs

Not Phase B, but found by the same MFU-4l relaxation and fixed with
it.  A user reduced MFU-4l to P1 and ran L-BFGS on defaults; the energy
stuck at the fourth step and the reported force wandered between 1 and
600 kcal/mol/A for two hundred iterations without the geometry moving a
thousandth of an Angstrom.

* **UFF names each metal type for its commonest geometry**, so `Zn3+2`
  reads as sp3 and collected a torsion for every Zn-N bond -- including,
  in the octahedral Kuratowski node, ones whose i-j-k is N-Zn-N at
  exactly 180 degrees.  `torsion_parameters` said in its own docstring
  that a bond to a metal has no torsion, and did not implement it.  It
  does now.
* **The degeneracy guard in the torsion and inversion gradients tested
  an area, not an angle.**  Both reach the coordinates through a cross
  product and divide by a sine on the way, and `|b1 x b2| > 1e-9` is
  satisfied a millionth of a degree off straight -- so the term was off
  at exactly 180 degrees and switched on one step later with a gradient
  four orders of magnitude larger than anything real.  The test is now
  on the sine (`terms.MIN_SINE`).

MFU-4l in P1 now converges in 25 steps.

## 5. Ship (PLAN § 16 phase 8) goes here

Phases A and B are the difference between an application that can be
handed to somebody else and one that cannot.  Nothing after this point
is a prerequisite for a build, and everything before it is.

---

## 6. Phase C — files, exports and the workspace ✅

**Goal:** a calculation leaves something behind, and it is findable.

Shipped.  Open a structure with a workspace open and it becomes the
root of one; run an optimisation and a run folder appears underneath it
holding the final structure, the trajectory and the log; click the
trajectory and scrub it, click the log and read it; save the project
and reopen it with all of that still attached.

**Save and Export are two things now.**  Save and Save As are about
the *project* and write `.xtalproj`, whatever extension is typed --
the same command either keeping a whole session or throwing most of it
away depending on three characters after a dot was not a command
anybody could predict.  `Save Project...` is gone, because that is
what Save is.  Export is one way: it never becomes the document's
path, never clears the modified flag, and says so in the status bar
the first time a CIF-opened document is saved.  *Export again* repeats
the last export, which gives back the quick round trip the split
costs.

**`File ▸ Export...`**, `xtalapp/dialogs/export.py`, replacing `Export
as P1 CIF...`: the format list comes from `FORMATS.writable()`, CIF
gets the *with symmetry* / *P1* pair that prompted this (both always
worked; one of them was reachable), there is a selection-only
checkbox, and `Format.keeps` -- which had existed since the registry
did and which nothing read -- is now the line under the picker saying
what the format drops.

**The workspace**, `xtal/workspace.py`.  A plain directory with a
`workspace.json` naming the format version and nothing else; a folder
per structure holding a *copy* of the file, because a tree of
references to files the user then moves is a tree of broken nodes; and
run folders named `<module>-<kind>-<nnn>`, numbered by looking at what
is already there.  Nothing in it is hidden, nothing needs this
application to read it, and deleting the folder in Finder is
supported.  The application never guesses one: with no workspace open a
structure still opens and still runs, it just leaves nothing behind,
and the status bar says so once rather than putting up a dialog on
every file.

**The run folders are written by the module that ran**, not by the
tree -- `RunFolder`, `RunLog` and `xtal/ff/record.py` -- so
`xtal optimize file.cif --workspace DIR` produces the identical layout
from a script.  That is also what Phase D's process runner will write
through.

**The log** is what makes a result defensible: the version, the engine
and every option, the full typing table with the confidence and the
*reason* for each assignment, the topology counts and warnings in
place, a line per step, and the per-term energy breakdown at both
ends.  It is written and flushed as the run goes, so the log of a run
that hung is the evidence of where it hung, and the viewer tails it
while it is live.

**The trajectory** is multi-frame extended XYZ
(`xtal/io/trajectory.py`), written a frame at a time as the steps
arrive -- 5184 sites is 124 kB a frame and 200 steps is 25 MB, which
is fine on disk and not fine in a signal queue.  Extxyz rather than an
invented format means it opens in OVITO, VMD and ASE without a
converter, and that a trajectory from any of them opens here.

**Playback** is a transport bar with play, loop, step, a frame slider
and a speed control, driving `Document.preview_positions` -- so
scrubbing touches neither the undo stack nor the modified flag.
Clicking the energy trace jumps to that frame and the frame being
played is marked on the trace, because the plot and the trajectory are
the same run seen two ways.  A frame is not an editable structure: a
document with a trajectory open refuses edits (`PlaybackActive`, with
the editing actions disabled so the refusal is never reached), and
*Adopt this frame* is the one way out that keeps a geometry, as a
single undoable command.

The interesting part is the mapping.  A trajectory holds the **P1
cell**, because that is what another program reads; a document varies
its **asymmetric unit**.  `p1.parent_frac` carries each frame back
through the operations that generated it, so a structure in P4_2/mnm
plays back in P4_2/mnm rather than being silently reduced to P1 by
being watched.

**Tests.** 58 new.  Headless first: the extxyz round trip and the
streaming writer (`tests/test_trajectory.py`), the workspace layout,
the run-folder writer, the log's contents and the CLI producing the
same layout (`tests/test_workspace.py`).  Then `pytest-qt` for the
tree model, the transport bar, the log viewer and the save/export
split (`tests/test_workspace_ui.py`), including the roadmap's own
demand that a project written and reread produce the identical tree.

**Risk, as written before the phase.**  The workspace was the entry in
TODO.md most likely to sprawl, bounded explicitly to a directory
layout, a tree model and a rule about where the directory lives.  It
stayed inside that: there is no database, no job queue, no provenance
tracking and no schema beyond a version number, and the tree is read
from the filesystem on every refresh rather than cached -- an index
would be a second answer to the same question, and the one that goes
stale when somebody moves a folder in Finder.

## 7. Phase D — modules

**Goal:** "what can I run" is a registry, and adding an engine touches
no existing file.

| Item | Size |
|---|---|
| A Modules menu and a module tree | M |
| Forcefield moved under it, unchanged | S |
| An external-process runner, written once | M |

The process runner is the part worth care: launch in a run folder,
stream stdout into `run.log` live, cancel by terminating the process
rather than abandoning a thread, detect a missing binary before
launching rather than inside a subprocess failure, and surface the exit
status as something a user can act on.

**Deliverable.** A Modules menu and a module tree dock, both built from
the registry, with UFF as the first module and its three entries
working exactly as they did.  A stub module — one that sleeps, logs and
writes a file — proves the registry, the form generation, the worker
and the cancel path without needing a binary installed.

This is also [docs/PLAN.md](PLAN.md) § 16 phase 9 done for real: a
DFTB+ module added later without touching core is the evidence that
phase asks for, and it is better evidence than a PXRD module written
by the same person who wrote the registry.

**Risk.** Over-generalising the parameter form.  Three modules is not
enough to know what the fourth needs; keep the declaration small and
let it grow when a real module strains it.

---

## 8. Phase E — the force field, made readable and complete

| Item | Size |
|---|---|
| Atom types nobody can read | S |
| Add hydrogens | M |
| Variable-cell relaxation | L |

Add hydrogens comes before variable cell for a reason that is easy to
miss: relaxing a cell around a structure with no hydrogens optimises a
UFF energy computed from typings that were all guesses.  Getting a
lattice constant out of that and believing it is the failure mode the
whole force field section of TODO.md keeps warning about.

**Deliverable.** The type table says "tetrahedral Zn(II)" beside
`Zn3+2`; an X-ray structure can have its hydrogens put back with an
honest orbit count; a cell relaxes under symmetry-adapted strain with
an optional external pressure.

**Tests.** The MOF-5 lattice-constant regression named in
[docs/PLAN.md](PLAN.md) § 11, which cannot be written until variable
cell exists and is the reason it is on this list.  Symmetry-adapted
strain must keep a cubic cell cubic and a hexagonal cell hexagonal
across a full relaxation.

---

## 9. Phase F — symmetry

| Item | Size |
|---|---|
| Invert the structure | S |
| Invert Selection ignores symmetry | S |
| Descend to a maximal subgroup | L |

The first two are a day between them and could go in any phase; they
are here so the subgroup work has company.  The subgroup entry is the
largest single piece of crystallography left in TODO.md, and its hard
part is naming a subgroup in a standard setting, not finding it — so
budget the phase around the naming and treat the enumeration as done.

---

## 10. Phase G — the picture

| Item | Size |
|---|---|
| Bonds inside polyhedra | S |
| Bond order in the picture | M |
| Depth cueing | M |
| Rectangular select | M |
| Arrow buttons on translate and rotate | S |
| Make planar | S |
| ORTEP draw style | L |
| Topology bonds | L |

Bond order in the picture needs the bond-order inference moved from the
UFF typer down into `xtal/core/bonding.py`, which is Phase B's stored
graph with one more field on it — so it is cheap here and expensive
before.  ORTEP needs `u_aniso` on `Site` and in the CIF reader and
writer, which is real I/O work and the reason it is an L.

---

## 11. Phase H — external engines

| Item | Size |
|---|---|
| Zeo++ | M |
| DFTB+ | L |

**Zeo++ first**, and not because it is more valuable.  It is the
smaller test of Phase D's runner: one binary, one input file, a handful
of small text outputs, and a run measured in seconds.  Everything that
is wrong with the runner will be found by it cheaply.  DFTB+ brings
Slater-Koster parameter sets, k-point meshes, hour-long runs and a
`Calculator` implementation, and is much better attempted second.

**Deliverable, Zeo++.** A `.cssr` writer, a radii file the user can
choose, the parsers for `.res`/`.sa`/`.vol`/`.psd_histogram`, a results
table and histogram, and the largest free sphere drawn in the viewport
where it actually sits.

**Deliverable, DFTB+.** A `.gen` reader and writer, an HSD writer, a
parameter-set check that names missing element pairs before launching,
single point and geometry optimisation both through `ff/api.py` and
through DFTB+'s own driver, live log, working cancel.

---

## 12. Phase I — building

| Item | Size |
|---|---|
| SMILES to 3D, into the open cell | M |
| Fragment library | S |
| An embedded 2D editor (rdEditor, or Ketcher) | M |

Do the first two, live with them, and only then take the editor.  A
text box that turns `c1ccccc1C(=O)[O-]` into a benzoate sitting in the
cell is a few days of work and covers most of what the sketcher was
wanted for.

The editor itself is an **integration, not a build**.  rdEditor is
PySide6, RDKit-backed, weak-copyleft and written as reusable widgets;
the spike that decides the phase is half a day -- put its editor widget
in a bare dialog and get a `Mol` back out.  If the widget does not come
apart from its shell, Ketcher in a `QWebEngineView` is the fallback.
Writing a canvas from scratch is not on this list.

Decide the RDKit question before starting, because it decides the rest:
choosing rdEditor is choosing RDKit, and RDKit also solves the 3D half.
An optional `[build]` extra -- RDKit-backed when installed, the native
fragment builder when not, one interface over both -- keeps it out of
the default bundle, which is the only real argument against it.

---

## 13. Summary

| Phase | Theme | Rough size |
|---|---|---|
| **A** | Make it behave | ✅ done |
| **B** | Bonds you control | ✅ done |
| — | **Ship** ([PLAN](PLAN.md) § 16 phase 8) | — |
| **C** | Files, exports, workspace | ✅ done |
| **D** | Modules | M |
| **E** | Force field | L |
| **F** | Symmetry | L |
| **G** | The picture | L |
| **H** | Zeo++, then DFTB+ | L |
| **I** | Building | M (XL with the sketcher) |

## 14. What this plan does not do

* It does not schedule PXRD, volumetric data, SHELX round-trips or
  Rietveld.  Those are in [docs/PLAN.md](PLAN.md) § 12 and stay there
  until something in this list is finished.
* It does not promise the 2D sketcher.  It promises the 3D builder
  underneath it and a text route into it.
* It does not touch the design principles in
  [docs/PLAN.md](PLAN.md) § 1.  Every phase above keeps the core
  Qt-free, keeps every mutation a command, and adds capability through
  registries — and where an entry in TODO.md is expensive, it is
  usually because it is being made to obey those rules rather than go
  around them.
