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

| Phase | Theme | Size |
|---|---|---|
| 9 | A builder's output has nowhere to live | S |
| 10 | Move mode, and what a click means | M |
| 11 | Two more draw styles | M |
| 6 | Force fields — UFF4MOF and GFN-FF/xTB | M |
| V | The engines answer in pictures | L |
| W | The klassengleiche half | L |

The argument is **wrong before missing, and small before large**.
Phase 9 is a bug wearing the clothes of a feature — a framework the
application builds and then forgets — and it is a file or two.  10
and 11 are the new capability, and 11 waits behind 10 because 10 is the
one somebody asked for in order to *use* the application rather than to
photograph it.  6 is data plus a registry entry and can be pulled
forward whenever a MOF needs typing.  V and W are where an external
tool and a piece of crystallography most users never reach are owed
work, and neither blocks anything above it.

**One cheap win is available at any time**: the `.cgd` writer for
Systre (Phase V, an afternoon).  It is listed last in priority and is
also the only way to *doubt* the net the Net panel names.

---

## 2. Phase 9 — a builder's output has nowhere to live

**Goal:** a framework or a molecule the application builds is in the
workspace when it opens, not after a trip through *Save As*.

| Item | TODO entry | Size |
|---|---|---|
| MOF and molecule builds land in the workspace | header | S |

Both builders are module actions with `needs_structure=False`
(`xtal/modules/mof.py:297`, `xtal/modules/build.py:148`), so both arrive
at `ModuleRunner._open_module_structure`, which opens a `Document` with
no path and says so.  That was right when there was nowhere to put one
and is wrong now: everything else in the tree got there without being
asked about, and a build is the case where the file the user would save
does not exist anywhere else yet.

`Workspace.add_document(name)` was written for this — "an entry for a
structure that has no file yet" — so the work is to take an entry when
a workspace is open, write the CIF into it, and `attach_workspace`.
The rule that survives is `_offer_workspace`'s: **with no workspace
open, nothing is created behind anybody's back.**  The build opens in a
tab as it does today and the status bar says why nothing was kept.

---

## 3. Phase 10 — Move mode, and what a click means

**Goal:** drag an atom or a selection where it should go, and stop a
click aimed at a net edge from deleting the chemistry under it.

| Item | TODO entry | Size |
|---|---|---|
| Click-and-drag move, bonding unchanged | header | M |
| A net edge under a bond cannot be clicked | Building | M |

**A mode, not a tool.**  `modes.register(MoveMode())` puts *Move* in
`Structure ▸ Mouse mode` and on the toolbar with no further change —
`menus.py:270` and `menus.py:669` both generate from `modes.names()` —
and its place beside *Draw net* is its place in the registration list
at the foot of `modes.py`.

The two pieces that do not already exist:

* **A drag that reports while it is happening.**  `DragEvent` is a
  press and a release with nothing in between, because the only mode
  that wanted one was the rubber band, and the viewport hard-wires
  press-drag-release to `_begin_band` / `_drag_band` / `_finish_band`.
  A mode has to be able to say what a drag *is* for it — the way
  `wants_move` was added so only the modes that need a ray pay for one
  — and get the intermediate positions.
* **A world position for a screen movement**, which is the same
  question `AddAtomMode` answers with `point_on_sphere`: a drag has no
  depth of its own, so the atom moves in the plane through it facing
  the camera unless a modifier says otherwise.

Everything downstream is built.  `MoveSites` merges while a gesture
continues and closes its window when the button comes up
(`docks/move.py`, `commands/atoms.py:265`), so forty frames of drag are
one Ctrl+Z — and a move that changes no bonding is what every command
in that file already does, so the invariant costs nothing here.

**The net-edge click rides in this phase** because it is the same file
and the same question.  Today an edge is taken only when the ray
reached nothing else, so a click on an edge crossing a bond lands on
the *bond* — and `Del` then suppresses that bond and its whole orbit:
aiming at one net edge on MOF-5 and pressing Del deletes 96 chemical
bonds and leaves the net on screen.  **Remove that outcome first**, and
it is separable from whatever the picking rule becomes.  The rule
worth trying is distance to the edge's axis rather than depth: inside a
fraction of the drawn radius means the edge even when a bond is nearer
the camera, outside means whatever is behind it.
`test_an_edge_never_wins_a_click_from_the_bond_under_it` pins the
current behaviour and is to be changed deliberately, not discovered.

---

## 4. Phase 11 — two more draw styles

**Goal:** the two pictures a paper wants that the application cannot
draw.

| Item | TODO entry | Size |
|---|---|---|
| PLATON / CheckCIF style | header | M |
| Cartoon style, made to vectorise | header | M |

A style is a record in `viewport/styles.py` and the builder never asks
which style it is — that is the rule polyhedra were the test of.  These
two are honestly more than a record, and the cost is worth stating
before the work starts: **there is no per-atom mesh**, so anything that
is not a radius, a colour or a flag on `SceneModel` is a second glyph
or real triangles, the way ORTEP's octants and the occupancy pies are.

* **PLATON/CheckCIF** is a displacement-ellipsoid plot in the
  convention every structure report is checked in: outlined atoms,
  thin bonds, no specular highlight, and the ellipsoids the ORTEP style
  already builds.  Most of it is fields — `ellipsoids=True`, a
  monochrome-ish palette, the material settings that already exist per
  actor in `vtk_scene.py`.  The outline is the new part.
* **The cartoon style is the one with a reason beyond taste**: flat
  fill plus a dark outline is *fewer* elements than the picture the SVG
  exporter writes today, which gives every sphere a radial gradient in
  `<defs>`.  A flat style exports as circles and strokes that
  Illustrator can recolour by class in one selection.  So this style is
  finished when `svg_export.py` draws it, not when the viewport does —
  and the exporter reads flags off `SceneModel` (`bond_render`,
  `ellipsoid_octants`), which is where the flag goes.

Take PLATON first: it shares everything with a style that already
works, and it says how much of "outline an instanced glyph" costs
before the cartoon style is committed to.

---

## 5. Phase 6 — force fields

**Goal:** the force field combo has something in it, and an MOF can be
typed.

| Item | TODO entry | Size |
|---|---|---|
| UFF4MOF | Phase 6 | M |
| GFN-FF / xTB | Phase 6 | M |
| Show the engines in the panel | Phase 6 | S |

Kept in [docs/TODO.md](TODO.md) with its file references; the schedule
is that **UFF4MOF goes first** because it is data.  `params.py`'s own
docstring says a type name is a record and adding one needs no code, so
the work is transcription, a typer rule where the geometry character is
not enough, and a validation test against published geometries.  It
makes a real MOF typable, which is the application's own stress case.

GFN-FF/xTB is a second `ENGINES.register(Engine(...))` following
`ff/dftb/calculator.py:451` exactly, including a `check` returning
`Availability` so the entry greys out naming what is missing.

Neither appears until `layout.py:86` lists it — `ForceFieldDock` hides
its combo when it is given one engine — so that one-line change is the
end of each of them, and it is what makes the phase visible at all.

---

## 6. Phase V — the engines answer in pictures

**Goal:** the half of the external tools that is a drawing rather than
a number, and the half of DFTB+ its own driver does better.

| Item | TODO entry | Size |
|---|---|---|
| Export a net as `.cgd` for Systre | Topology | S |
| Zeo++: draw the answer, do not only print it | Modules | M |
| DFTB+'s own driver | Modules | L |

**The `.cgd` writer is an afternoon.**  The Net panel says **pcu** and
the canonical key makes that a decision rather than a match, and there
is still no way to doubt it.  `xtal/io/cgd.py` reads the format and
does not write it; a writer and an action that saves the drawn net
through it is the only second opinion that does not come from the code
that produced the first.  One `CRYSTAL` block with `NAME`, `GROUP P1`,
`CELL`, and a `NODE` per vertex with an `EDGE` per edge — the net is
already in that shape.

**Zeo++ is the reason this phase exists.**  A porous-materials
application that can only *print* 9.18 Å is a spreadsheet.  `-res`
gives the diameter and not the position, so the largest free sphere
drawn where it sits needs `-chan` or `-visVoro` and a new actor beside
`_set_polyhedra`.  Channel dimensionality falls out of `-chan` for
free, and `-vol` is parsed already and wants an action of its own.

**DFTB+'s own driver is a module, not an engine** — and per the note in
[docs/TODO.md](TODO.md), a wrapper over what DFTB+ already does rather
than a reimplementation of any of it.  As an engine it does a single
point and a geometry optimisation with the symmetry projection intact;
what the internal driver does better is **lattice relaxation** (ours
costs twelve extra energy evaluations a step because no analytic stress
is claimed) and **molecular dynamics**, which has no route through
`Calculator` at all.  `ff/dftb/hsd.py` writes the input, `io/gen.py`
reads the geometry back and `modules/process.py` runs, streams and
cancels it; what is new is a `Driver` block, a multi-step output parser
and the trajectory read into the transport bar.

**The cheaper half of the stress question comes first**: read DFTB+'s
printed stress tensor and *check* it against `numeric_stress` on a
structure with a known answer.  If it agrees, the engine claims it and
variable-cell relaxation gets twelve times cheaper with no driver
written.  Phase I's redraw rule applies in full — what lands in the run
folder is a function of the run and not of what the window was showing.

---

## 7. Phase W — the klassengleiche half

**Goal:** *Descend to a subgroup* offers the subgroups that split an
orbit without touching the cell, and then the ones that double it.

| Item | TODO entry | Size |
|---|---|---|
| A lost centring, in the same cell | Symmetry | M |
| A doubled cell, from the table | Symmetry | L |

**A lost centring needs no cell transformation.**  Fm-3m contains
Pm-3m as a genuine subset of its operations, at index 4, in the same
cubic cell; rock salt descended that way puts its sodiums and chlorines
on eight independent sites, which is the cation-ordering model — and it
is why halite is the one fixture where no descent splits anything.

**It does not fall out of the existing enumeration** by not dividing
the centring out.  `core/subgroups.py` reduces modulo the centring
translations on purpose: the reduction is what makes the closure
affordable, and the "generated by at most three elements" shortcut is a
fact about crystallographic *point* groups that stops being safe the
moment the translations are back in.  The tractable route keeps the
reduction — enumerate the subgroups of the *centring* group the point
group leaves invariant, lift the reduced generators through each coset
representative, and close.  Naming and application need nothing new.

**The doubled cell is a table, not a computation.**  Superstructures
and antiferromagnetic ordering live there and every relation carries
its own cell transformation and origin shift: Bilbao's MAXSUB.  Last,
and worth not implying the earlier versions do it — the dialog says
*translationengleiche* and no cell is doubled, which stays true until
this lands.

---

## 8. What this plan does not do

* It does not schedule the **parallel-suite hang**
  ([docs/TODO.md](TODO.md) § Testing).  Serial is the default and the
  suite is green; the hang costs 60 s a run, not correctness, and the
  diagnosis in [CLAUDE.md](../CLAUDE.md) is where it waits for someone
  with an afternoon and a `faulthandler` dump.
* It does not schedule volumetric data, SHELX round-trips or Rietveld.
  Those are [docs/PLAN.md](PLAN.md) § 12 and stay there until this
  list is finished.  PXRD shipped and is deliberately not Rietveld.
* It does not promise the 2D sketcher — it promises the 3D builder
  under it and a text route into it.
* It does not touch the design principles in
  [docs/PLAN.md](PLAN.md) § 1.  Every phase above keeps the core
  Qt-free, keeps every mutation a command, and adds capability through
  registries — and where an entry is expensive, it is usually because
  it is being made to obey those rules rather than go around them.
