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
| Arrow buttons on translate and rotate | Editing | S |
| Bonds inside polyhedra | Appearance | S |
| Cutoff and skin controls | Force field | S |
| Edit cell in the right-click menu | Editing | S |

Two more sat here until Phase F took them: *Invert the structure* and
*Invert Selection ignores symmetry*, both shipped.

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
from a script.  That is also what Phase D's process runner writes
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

## 7. Phase D — modules ✅

**Goal:** "what can I run" is a registry, and adding an engine touches
no existing file.

Shipped.  `Calculate` is gone and `Modules` is in its place, with a
submenu per module and a module tree dock beside the workspace tree --
what can be run on one side, what it produced on the other.  Neither is
written by hand: both are built from `xtal/modules/registry.py`, and
nothing in `xtalapp/mainwindow.py` names a module.

**The declaration is the whole of it**, `xtal/modules/registry.py`.  A
`Module` has a name, a label, an order in the tree, a `check` that says
whether it can run at all, and a tuple of `Action`s.  An `Action` names
the parameters it needs (`Param`, rendered into a form), the callable
that runs it, whether it wants a run folder, and what the middle word
of that folder's name is.  Registering one is:

```python
MODULES.register(Module(
    name="zeopp", label="Zeo++",
    check=lambda: NETWORK.availability(),
    actions=(Action(name="pore-diameter", label="Pore diameter...",
                    params=(Param("radii", "Radii file", kind="path"),),
                    run=zeo.pore_diameter),)))
```

and the menu entry, the tree leaf, the parameter dialog, the worker
thread, the run folder, the log and the Stop button all follow from it.
`xtal/plugins.py` calls the `crystal_builder.plugins` entry points at
start-up, so the same is true of a module installed from another
package -- which is what makes [docs/PLAN.md](PLAN.md) § 14's claim
that *no existing file changes* literally rather than nearly true.

**Forcefield moved rather than being rewritten.**  Its three entries
are the three that were under `Calculate`, they are the same QActions,
and `Ctrl+E` and `Ctrl+Shift+E` went with them.  They are declared with
a `shell` field naming the window action that performs them, because
the Force Field panel does three things a generic runner cannot -- it
moves the atoms as the geometry changes, plots the energy as it
arrives, and lands the whole run as one undoable command.  That field
is the one asymmetry in the design and it is recorded rather than
hidden: a module written after this one has `run` instead, and gets its
form and its thread for free.

**The process runner**, `xtal/modules/process.py`, is the part that was
worth the care, because DFTB+ and Zeo++ both go through it:

* *A missing binary is found before anything is launched.*  `Program`
  looks at an explicit path, then an environment variable, then PATH,
  and raises `MissingProgram` naming all three -- and the same call
  answers `Module.check`, so the tree greys the module out and says
  why before anybody clicks.
* *The log is live.*  Every line the child prints is written and
  flushed as it arrives, so the log of a run that hung is the evidence
  of where it hung, and the log viewer tails it while it runs.
* *Cancel reaches the process.*  Abandoning the reading thread leaves
  the binary running: still on the CPU, still writing into the run
  folder, still there when the next run starts.  Stop terminates the
  process *group* (a program launched through a wrapper script is a
  child of a child), waits five seconds, and kills what survives.
  Stop pressed before the launch does not launch it at all.
* *The exit status becomes a sentence.*  `returncode 1` tells nobody
  anything; the last twenty lines are kept and quoted, because the
  thing that went wrong is nearly always in them.

`Cancellation` is what lets one Stop button cover both kinds of job: an
in-process loop polls it (and sleeps on it, so a job resting ten
seconds still stops in milliseconds) while `ExternalProcess` registers
its terminator with it.  The button does not have to know which it is
stopping.

**The stub module**, `xtal/modules/stub.py`, is how all of that is
tested on a machine with nothing installed.  It counts, logs, writes a
file and can be told to fail, in two flavours -- one in the worker
thread and one in a child process, the second launching this
interpreter rather than a binary.  It is registered only when
`XTAL_STUB_MODULE` is set, because an entry called *Stub* in a shipped
menu is a confusing thing to find.

**`xtal modules` and `xtal run`** list the registry and run an entry
from a script, through `xtal/modules/record.py` -- the same run folder
and the same log the window writes, which is Phase C's rule applied to
the registry.  It is also the proof the registry is headless: a module
that could only be run by clicking it is one whose parameters, run
folder and log could not be tested without a display.

**Two Qt traps, found by the tests and worth writing down.**  A
`QThread` whose last Python reference is dropped inside its own
`finished` slot is destroyed while still running, and Qt aborts the
process rather than raising -- so `start_in_thread` takes a parent and
C++ owns the thread.  And `QAction.menu()` hands ownership of the
submenu to the caller in PySide6, so a test that reached a submenu that
way destroyed it before asserting on it; menus are found among their
parent's children instead.

**Tests.** 96 new: the registry, parameters and cancellation
(`tests/test_modules.py`), the process runner end to end including
kill-on-cancel and a process that ignores SIGTERM
(`tests/test_process_runner.py`), the menu, the tree, the generated
form and a full run with its folder and log
(`tests/test_modules_ui.py`), and the two new CLI commands.

**Risk, as written before the phase.**  Over-generalising the
parameter form.  It stayed small: six parameter kinds, no layout
language, no conditional enabling, no validation beyond a range, and a
result that is a message and optionally a structure.  Tables, plots and
overlays are named in the plan as things a module will want to present
and are deliberately not there yet -- the first module that has one
gets to decide what the shape is.

---

## 8. Phase E — the force field, made readable and complete ✅

**Goal:** the one panel whose job is checking can be read, and a
lattice constant is something this application produces rather than
something it assumes.

Shipped.  The type table says *octahedral Ti(IV)* beside `Ti6+4`; an
X-ray structure gets its hydrogens back as one undoable edit with an
honest orbit count; and a cell relaxes under a symmetry-adapted strain,
with an external pressure, from the panel and from a script.

**The type in words**, `UFFParams.description`.  Built from the parts
of the five-character name and not from a table of 127 strings, so a
type added to `params.py` is readable the moment it exists.  The
geometry character is the whole trick: it is a coordination polyhedron
on a metal and a hybridisation in the main group, so the same `3` reads
as *tetrahedral* on zinc and *sp3* on oxygen, and nothing anywhere had
ever said so.  It goes **beside** the name and never replaces it -- the
name is what Rappe's Table 1 is indexed by, what an override is stored
as, and what anybody cross-checking against another program needs --
in the panel's new column, in the override dialog (`Fe3+2` and `Fe6+2`
is a choice between two strings; *tetrahedral* and *octahedral* is a
question about your crystal), in the Inspector, and in the run log,
which is the copy somebody reads three months later.

**Add hydrogens**, `xtal/ff/hydrogens.py`.  The coordination decides
where, the valence decides how many, the force field decides how far,
and symmetry decides how many there really are.

* Where: the typer's hybridisation, not a second geometry pass --
  `typer.Geometry` was made public rather than duplicated.  Benzene's
  hydrogens come out in the ring plane at 120 degrees, a methyl
  tetrahedral and *staggered* against the heaviest atom two bonds away,
  and a hydroxyl bent at 104.51 rather than straight, because the angle
  is read off the type (`O_3`'s own `theta0`) and not off the
  coordination number.
* How many: `elements.VALENCE` less the bond orders the typer inferred
  -- so an aromatic carbon is judged to be carrying 3.0 and gets one
  hydrogen, and a carboxylate oxygen already coordinating a metal gets
  none.  A metal gets none by rule, an element with no tabulated
  valence gets none and is **named**, and an atom with no neighbours at
  all gets none because there is no coordination to complete.
* How far: `terms.natural_bond_length(type, "H_", 1.0)`, so the
  hydrogen arrives at the minimum of the potential it is about to be
  relaxed in -- a relaxation afterwards moves it less than 0.05 A.  The
  X-ray distances are 0.1 A shorter for a real reason and are offered,
  not defaulted to.
* The count reported is the **orbit** count: "6 hydrogens on 2 atoms (4
  sites in the asymmetric unit)".  Two hydrogens either side of a
  mirror plane are one site, and a candidate that lands in an earlier
  one's orbit is dropped rather than generated twice.
* One `AddSites` for the lot, so it is one Ctrl+Z, with the plan --
  and every assumption in it -- on screen before the button is pressed.
  Found and fixed on the way: `AddSites` asked the structure for a free
  label per site without counting the batch, so twelve hydrogens added
  at once were all called `H1`.

**Variable-cell relaxation.**  `SymmetryDOF` gained six strain
variables in the same flat vector, so FIRE and L-BFGS relax a lattice
constant without either of them changing a line.

* **The strain is symmetry-adapted by projection, not by a table.**  A
  displacement transforms as `u W` and a strain, one rank up, as
  `W^T e W`; averaging that over the point group is the projector onto
  the strains the group allows.  It leaves a cubic cell one free strain
  and a hexagonal or tetragonal one two, and a cubic cell relaxed
  through it comes back with `a = b = c` and three right angles
  *exactly* -- not to a tolerance, because there is no variable that
  could take it anywhere else.
* The stress is `Calculator.numeric_stress`, built in phase 7 and left
  unwired until now: twelve energy evaluations a step, which is what an
  engine with no analytic virial costs and the reason the analytic one
  is the next thing to write.
* External pressure as a `P V` term, in GPa, with the conversion
  written down once (`optimize.GPA`; 1 kcal/mol/A^3 is 6.9477 GPa) and
  tested by relaxing under 5 GPa and confirming the crystal is pushing
  back with exactly that.
* Two scalings keep the six new variables ordinary: the strain is
  stored times a cell length, so FIRE's step cap is a distance, and its
  gradient is divided by the atom count, so what is compared against
  the force tolerance is a force per atom.  `|F|max` still means what
  it always meant -- the cell's own convergence is reported beside it
  rather than folded into it, or two runs of the same structure would
  not be comparable.
* The cell travels with the coordinates in **one** command, or Ctrl+Z
  would put the atoms back into a cell they were never relaxed in; the
  trajectory frames carry it too; and `xtal optimize --relax-cell
  --pressure` does the same from a script.
* One control and one honest warning in the panel: a cell relaxed
  under UFF is a UFF cell, and for a framework it is routinely a few
  percent out.

A real bug the tests caught: the strain enters the variables additively
(`F + dF`) and the stress is the derivative of a strain applied to the
cell `F` already made (`F(I+d)`), which differ by `F^-1`.  With `F^T`
where `F^-T` belonged, every gradient was a few percent wrong -- it
still converged, to the wrong cell, which is the failure mode nothing
but a finite-difference check would ever have found.

**Tests.** 40 new: the descriptions (`tests/test_uff_params.py`), the
hydrogen geometry, the orbit count and the special-position case
(`tests/test_hydrogens.py`), the strain subspace, the finite-difference
check on the strain gradient, the pressure balance and the units
(`tests/test_variable_cell.py`), plus the panel, the dialog and the CLI.

**The lattice-constant regression is MFU-4l, not MOF-5.**
[docs/PLAN.md](PLAN.md) § 11 names MOF-5/IRMOF-1 and this repository
does not have one; transcribing a structure from memory and calling it
a regression would be worse than saying so.  MFU-4l makes exactly the
same claim on the framework that is here: 648 atoms, `Fm-3m`, 192
operations, relaxing from the deposited a = 31.057 A to 30.303 A --
2.4% in, which is the "few percent" the warning promises -- and staying
exactly cubic all the way.  It runs in nine seconds and is marked
`slow`.  Swap in MOF-5 when a trustworthy CIF is at hand.

**Not done, and small:** the type in words does not reach a viewport
tooltip, because there are no atom tooltips to put it in yet -- that is
a viewport feature and belongs with Phase G.

---

## 9. Phase F — symmetry ✅

| Item | Size | |
|---|---|---|
| Invert the structure | S | ✅ |
| Invert Selection ignores symmetry | S | ✅ |
| Descend to a maximal subgroup | L | ✅ translationengleiche |

The first two were a day between them and could have gone in any
phase; they were here so the subgroup work had company.  The subgroup
entry was the largest single piece of crystallography left in
TODO.md, and the budget was right: the hard part was naming a subgroup
in a standard setting, not finding it.

**What shipped.**  `xtal/core/subgroups.py` enumerates the maximal
translationengleiche subgroups by walking the subgroup lattice upwards
from the cyclic subgroups over the operations reduced modulo the
centring — which finds every subgroup without assuming a bound on the
number of generators, and does Fm-3m in a tenth of a second.

**The naming was solved rather than worked around**, which is what
made the feature usable.  `gemmi.find_spacegroup_by_ops` names 11 of
the 27 maximal subgroups of the four fixture structures; building a
probe crystal — the orbits of two generic points of two different
species, in a cell of the parent's shape — and asking spglib to
identify it names all 27, *and* returns the transformation to the
standard setting along with the name.  Two generic points rather than
one because a single orbit can acquire an accidental inversion centre
about its own centroid, which is how a naive version calls P4_2nm
"P4_2/mnm".  Every answer is checked twice: spglib must report exactly
as many operations as it was asked about, and the named group's order
must equal the operation count times the volume ratio of the new cell,
or the subgroup comes back unnamed rather than mislabelled.

Applying a descent needed one new core routine,
`supercell.change_setting`: the general form of `transform_cell`, with
a rational basis and an origin shift, because a subgroup's standard
setting is generally not the parent's basis.  Rutile's Cmmm — the only
one of its seven that splits anything, and the one gemmi cannot name —
needs it.

**What did not ship** is the klassengleiche half, which is back in
TODO.md as its own entry.  The lost-centring case is the valuable one
(it is the rock-salt cation-ordering model) and it does *not* fall out
of the same enumeration for free, which is the one thing the original
entry got wrong: the centring reduction is load-bearing, and putting
the centring translations back invalidates the generating-set bound
that the cheap enumeration rests on.

---

## 10. Phase G — the picture ✅

| Item | Size | |
|---|---|---|
| Bonds inside polyhedra | S | ✅ |
| Bond order in the picture | M | ✅ |
| Depth cueing | M | ✅ |
| Rectangular select | M | ✅ |
| Arrow buttons on translate and rotate | S | ✅ |
| Make planar | S | ✅ |
| ORTEP draw style | L | ✅ |
| Topology bonds | L | ✅ |

Bond order in the picture needed the bond-order inference moved from
the UFF typer down into `xtal/core/bonding.py`, which is Phase B's
stored graph with one more field on it — so it was cheap here and
expensive before.  ORTEP needed `u_aniso` on `Site` and in the CIF
reader and writer, which is real I/O work and the reason it was an L.

**The bond-order move was the load-bearing one**, and it went further
than "cut and paste one function".  The old inference was expressed in
UFF's *type names* — `C_2` has one pi bond to place, `C_1` has two —
so moving it meant re-deriving those counts from the element and the
geometry instead: coordination, the angle at a two-coordinate atom, the
angle sum at a three-coordinate one.  The terminal-atom case had to be
rewritten outright, because UFF decided it by asking which of its own
types predicted the measured bond length, and the core has no types to
ask.  A ratio against the sum of the covalent radii does the same job
— a double bond runs about 0.9 of a single one and a triple about 0.8
— and it is what keeps butadiene's double bonds on the outside where
they belong.  `xtal/ff/uff/typer.py` now *reads* `bonding.orders` and
adds one thing of its own: UFF's amide C–N order of 1.41, which is a
convention of that force field and not a fact about the molecule.

**The offset direction was the whole of drawing a double bond**, as the
entry predicted.  Two parallel tubes need a plane to lie in, and it is
the local pi plane — the best-fit plane through the bond and the atoms
around both its ends — so the picture does not flicker as the camera
turns.  The direction is also *pointed at* the substituents, which is
what puts an aromatic ring's dashed inner line inside the ring rather
than outside it, where it would read as a bond to something that is not
there.  A bare diatomic has no such plane and is the one case allowed
to consult the camera: it is laid into the plane of the screen, fixed
when the scene is built and not while the camera moves.

**Depth cueing is a shader replacement** on the atom, bond and
polyhedron actors, mixing towards the background by `-vertexVCVSOutput.z`
— view-space distance, which is linear — rather than by
`gl_FragCoord.z`, which a perspective projection skews so heavily that
the whole scene lands in the last few thousandths of it and the fade is
either invisible or total.  The near and far distances are the scene's
own bounds along the view direction, refreshed from a renderer
`StartEvent` so they follow the camera instead of sliding off the
structure on the first zoom.  It is off by default, so no documentation
image and no render test changed under it.

**ORTEP's two traps were both real.**  The CIF's U^ij are defined
against the *reciprocal* basis and are not a cartesian tensor;
`Site.u_cartesian` converts them, and in an orthorhombic cell the two
agree exactly, which is why getting it wrong survives casual testing.
The second was the renderer: `vtkGlyph3DMapper` will scale a glyph by
three components and turn it by a quaternion, so one actor draws every
ellipsoid — but the split has to be `M = U S`, taking the *left*
singular vectors alone.  Using `U V^T`, which is the reflex answer for
"the rotation part of a matrix", pairs each axis length with the wrong
axis and points every ellipsoid somewhere else.  The three fallbacks
are each visible as themselves: an isotropic atom is a sphere, and an
atom with no displacement parameters at all is a small one that does
*not* grow when the probability level is raised, which is the tell.

**Topology bonds needed the identity of a stored bond widened.**
`Structure.add_bond` matched on the pair of points alone, so a net edge
and a chemical bond joining the same two atoms collided — which in a
net whose vertices are directly bonded metals is every edge.  The kind
is part of the identity now, and `explicit` and `suppressed`
deliberately still collide, because they are two answers to the same
question.  `perceive` filters the net out, `topology_graph` hands it
back on its own, and `coordination_sequence` and `point_symbol` give
**pcu** the 6, 18, 38, 66, 102 and the 4^12.6^3 that RCSR does.  The
open question from the entry stands: a vertex is an atom, and a Zn4O
cluster still wants its centroid.

**What did not ship** is the atom tooltip Phase E's write-up parked
here — the UFF type in words, shown on hover.  It was never one of this
phase's eight entries; it arrived as a sentence at the end of another
phase, which is not how work gets scheduled.  It is back in TODO.md as
its own entry, where it can be sized honestly: the tooltip is the
feature, and the type is only the first thing to put in it.

---

## 11. Phase H — external engines

| Item | Size |
|---|---|
| Zeo++ | M — shipped |
| DFTB+ | L — shipped as an engine; its own driver did not |

**Zeo++ first**, and not because it is more valuable.  It was the
smaller test of Phase D's runner: one binary, one input file, a handful
of small text outputs, and a run measured in seconds.  It found what
was missing cheaply, which is what it was for.

### Zeo++

Three entries — **Pore diameters**, **Surface area** and **Pore size
distribution** — under a module that greys itself out with a sentence
when `network` is not installed.  Measured on MFU-4l reduced by our own
P1 expansion: D_i 18.73 Å, D_f 9.18 Å, D_if 18.72 Å; 3198 m²/g to
nitrogen in one channel and no pockets; a distribution with two peaks,
at 11.5 Å and 18.7 Å, which is the two cavity sizes the framework has.
The same structure through Zeo++'s own CIF reader agrees to the fourth
decimal, which is the check that the CSSR writer is right.

**What was built.**

* **A `.cssr` writer and reader** (`xtal/io/cssr.py`), registered in
  `FORMATS`.  Written in P1 always: Zeo++ ignores the space-group field
  and treats what it is given as the whole cell, so writing an
  asymmetric unit into it would not be a lossy export but a wrong one.
* **The radii are a control, not a constant.**  Zeo++'s own table by
  default — it is what its papers used — or this application's van der
  Waals or covalent tables written out as a `.rad`, or a file of the
  user's own.  Whichever it was is in the log and in the result,
  because an area quoted without its radii and its probe is not
  reproducible.  A radii file that was named and is not there stops the
  run rather than falling back, which would silently be a different
  calculation.
* **The parsers** (`xtal/analysis/porosity.py`), tested against
  captured output rather than against a live binary.  The `.sa` and
  `.vol` files share a `Key: value` line whose value is sometimes
  *missing* — Zeo++ writes `Pocket_surface_area_A^2:` and then nothing
  when there are no pockets — and a parser that took the next token as
  its value read the following line's key as a number.
* **A results panel** (`xtalapp/docks/results.py`) and a histogram
  widget (`xtalapp/histogram.py`), drawn by hand for the same reason
  `plot.py` is.  The PSD draws the bars *and* the derivative of the
  cumulative distribution, because the bars are the sampling and the
  curve is the distribution, and either alone invites the wrong reading
  of the other.  Only the occupied range is shown: Zeo++ writes a
  thousand bins of 0.1 Å and a framework fills forty.
* **`JobResult` grew a report**, which its own docstring had reserved
  for the first module with an answer a sentence could not carry.  The
  shape is three frozen records — `Row`, `Table`, `Histogram` — and it
  prints as text into the run log and from the CLI as well as
  rendering into the dock.
* **A partially occupied site is refused**, in front of the writer.
  Zeo++ cannot express half an atom and handed one returns a confident
  number for a crystal that does not exist, which is worse than
  failing.

**What did not ship: the largest free sphere in the viewport.**  It is
the high-value half of the TODO entry and it is a different job —
`-res` gives the diameter and not where it sits, so it needs `-chan` or
`-visVoro` and a new actor in the scene.  It is back in TODO.md.

### DFTB+

**Reached as an engine, not as a module**, which is the decision the
phase turned on.  A `Calculator` in `ENGINES` gets the optimiser, the
symmetry projection, the worker thread, the live plot, the trajectory,
the frozen selection, the cell as a variable, Pause and Stop and the
single undoable command at the end — all of it, without any of those
learning what DFTB+ is.  Writing it as a module would have meant
rewriting every one of them.

* **`.gen` reader and writer** (`xtal/io/gen.py`), which is also how a
  DFTB+ relaxation comes back.
* **An HSD writer** (`xtal/ff/dftb/hsd.py`): Hamiltonian, SCC and its
  tolerance, third order with the 3ob Hubbard derivatives, Fermi
  filling, dispersion, and a Monkhorst-Pack mesh worked out from the
  cell — shifted when it is even and not when it is odd, because an odd
  mesh already contains Γ.
* **The parameter-set check runs before anything is launched.**  Every
  ordered element pair present is looked for in the Slater-Koster
  directory and the missing ones are named.  DFTB+ would have failed
  several seconds in, naming a file rather than a problem.
* **Nothing is guessed silently.**  A maximum angular momentum that had
  to be derived rather than looked up, and a Hubbard derivative DFTB3
  wanted that 3ob does not publish, are both answers that change the
  number without failing — so both are warnings on the calculator and
  both are in the log.
* **The charges carry over between steps** (`ReadInitialCharges`),
  which is most of the cost of an SCC cycle and the reason a DFTB+
  optimisation is affordable at all.

**Two things this phase moved to make room for it.**
`Param` and `Availability` left the module registry for `xtal/params.py`
— DFTB+ is an engine and needed the same declarations, and the
alternative was two of everything.  `Engine` then grew `options` and
`check`, so the Force Field panel builds a generated form for an engine
that declares one (DFTB+: Hamiltonian, parameter directory, dispersion,
charge, temperature, k-point spacing) and keeps UFF's two hand-built
controls for the engine that predates the mechanism.  That is the same
asymmetry `Action.shell` records, and it is recorded the same way
rather than hidden.

**What did not ship: DFTB+'s own driver.**  Its lattice relaxation and
its MD are the cases where the internal driver beats ours, and they are
a module rather than an engine — a second way in, worth having and not
what "the same features as the force field" asked for.  It is back in
TODO.md.

**Tests.** 79 new, none of which need either binary installed: Zeo++
and DFTB+ are both driven through a stand-in named by their environment
variable, which writes the output the real one would.  The one test
that does use `network` checks the single thing a stand-in cannot — that
Zeo++ accepts the CSSR this application writes — and skips when it is
absent.

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
| **D** | Modules | ✅ done |
| **E** | Force field | ✅ done |
| **F** | Symmetry | ✅ done |
| **G** | The picture | L |
| **H** | Zeo++, then DFTB+ | ✅ done |
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
