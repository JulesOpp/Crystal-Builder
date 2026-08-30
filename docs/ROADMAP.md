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
| Save As / Export split | Files and calculations | S |
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

## 4. Phase B — bonds you control

**Goal:** the bond graph is a thing the user owns, and it survives
being saved.

| Item | Size |
|---|---|
| Store the bond graph | M |
| Bond rules dialog | M |

Most of what this phase was for shipped in A.  What is left is the
half that needs a stored field rather than a memo: a graph that
survives a save, an added atom that perceives bonds for itself without
re-perceiving the rest, and a preference for people who want
perception to follow the geometry.  Then the rules dialog, whose
"6 added, 2 removed" preview is only expressible against a graph that
is stored.

**Tests.** A project round-trip keeps the graph, including the
suppressions layered on it; an add perceives only the new atom's
bonds.

**Risk.** The rule about which changes force a re-perception is a
judgement, and getting it wrong is invisible.  It is written down in
`xtal.core.structure.CHEMISTRY` and enumerated in
`tests/test_change_hints.py`; keep it that way.

## 5. Ship (PLAN § 16 phase 8) goes here

Phases A and B are the difference between an application that can be
handed to somebody else and one that cannot.  Nothing after this point
is a prerequisite for a build, and everything before it is.

---

## 6. Phase C — files, exports and the workspace

**Goal:** a calculation leaves something behind, and it is findable.

| Item | Size |
|---|---|
| Save As saves a project; Export writes a structure | S |
| File ▸ Export... | M |
| A working folder, and the calculations underneath the structure | L |
| Show the log | S |
| Play the trajectory back | M |

**Deliverable.** Open `MFU4l.cif`; it appears as the root of a
workspace.  Run an optimisation; a run folder appears underneath it
holding the final structure, the trajectory and the log.  Click the
trajectory and scrub it; click the log and read it.  Save the project
and reopen it with all of that still attached.

**Tests.** Headless first — the workspace layout, the run-folder
writer and the multi-frame extxyz round trip all live in `xtal` and are
tested without Qt.  Then `pytest-qt` for the tree model and the
transport bar.  A project written and reread must produce the identical
tree.

**Risk.** The workspace is the entry in TODO.md most likely to sprawl.
Bound it explicitly: it is a directory layout, a tree model, and a rule
about where the directory lives.  It is not a database, not a job
queue, and not provenance tracking.  If it starts needing a schema
migration, it has grown past its brief.

---

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
| **B** | Bonds you control | S–M |
| — | **Ship** ([PLAN](PLAN.md) § 16 phase 8) | — |
| **C** | Files, exports, workspace | L |
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
