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

Phases A to I have shipped and their entries are gone from
[docs/TODO.md](TODO.md).  What follows is the plan for what is left,
rewritten around a change of priorities: the application can be
trusted, and the next thing it has to do is **make** something.

---

## 1. What comes first, and why in this order

Three things are wanted before anything else, and they are wanted for
different reasons.

**Breaking up `mainwindow.py` comes first**, and not because 2415
lines is unpleasant.  It comes first because two of the other five
phases land inside it: PORMAKE is a new branch in the module-run
plumbing and a dialog of its own, and the window rearrangement is a
rewrite of the layout code.  Doing the split afterwards means doing it
over code that has just been changed, with the diff of a pure move
tangled up in the diff of a feature — which is the one thing a pure
move must never be.  It is also the only phase here that adds no
capability at all, so it is the one worth getting behind us.

**PORMAKE next**, because it is the phase with a decision in it.  The
dependency question (`pymatgen` and `jax` in an application that today
installs four packages) has to be answered by trying it, and the answer
changes what Phase U is allowed to assume.  Everything else on this
list is work; this one is work plus a fact we do not have yet.

*The fact is now in: 889 MB, 44 packages, and a ten-second import.
Workable, as an extra and never on the import path — § 4.*

**Add Atom at a bond length third**, because it is the smallest of the
three and it does not block anything — but it builds the one piece of
machinery two later entries need: the viewport has no hover event at
all today, and the ghost atom, the tooltip and any future drag-preview
all want the same `on_move`.

*`Mode.on_move` is now there, along with `MoveEvent` and a
`wants_move` flag so only the modes that ask pay for the ray.
Phase T's tooltip inherits all of it — § 5.*

```
    P. split the shell ─┬──> the PORMAKE runner branch     (Phase Q)
                        ├──> the default layout            (Phase T)
                        └──> every phase after it

    Q. PORMAKE ─────────┬──> the dependency answer         (Phase U)
                        └──> "use the linker I drew"       (Phase U)

    R. hover events ────┬──> the ghost atom                (Phase R)
                        └──> the atom tooltip              (Phase T)
```

After those three the order is the user's stated one, with a single
rearrangement: the **half bonds at the boundary** ride in Phase S
rather than waiting, because they are a change to
`viewport/builder.py`, which is the file Phase S is already open in,
and because a net drawn on one cell of **pcu** showing three edges at a
six-coordinate vertex is a wrong picture rather than a missing feature.

---

## 2. Cheap wins, available at any time

Each of these is a day or less, depends on nothing, and can be pulled
out of its phase whenever the pain is worth a detour.

| Item | Phase it belongs to | Size |
|---|---|---|
| Edit cell in the right-click menu | T | S |
| Export a net as `.cgd` for Systre | V | S |

The `.cgd` writer is the one to notice: it is listed last in priority
and it is an afternoon, and Phase Q put a second consumer in front of
it — PORMAKE reads `.cgd` topologies, so a writer is also the route
from *a net the user drew* to *a framework built on it*.  Phase Q used
the **reader** and did not need the writer, so this is still owed and
is now the last piece of "build on the net I drew".


---

## 3. The TODO header, in front of V and W

`docs/TODO.md` gained a header of work raised while using the
application, and it takes priority over Phases V and W below, which
stay written and move behind it.  It is not one theme, so grouped by
area it is seven phases, each landing in one or two files with a green
suite between.

| Phase | Theme | Size | |
|---|---|---|---|
| 1 | Topologies, generated rather than stored | M | *shipped* |
| 2 | Image export | M | *shipped* |
| 3 | Appearance | M | *shipped* |
| 4 | Shell and menus, then a proposal | S | *shipped* |
| 5 | Structure editing | S–M | |
| 6 | Force fields — UFF4MOF and GFN-FF/xTB | M | |
| 7 | PXRD | L | |

**Phase 3 landed four entries and no new render path.**  The net and
the plane colours were module constants and are now settings with a
swatch each in the style panel; *Net only* is one more
`register(DrawStyle(...))` and needed no builder branch, because
`radius_factor = 0` already hides the atoms the way *Wireframe* does.

A plane's colour did not stay a single setting for long.  The reason
to draw a quad at all is to see where two planes cross, and two quads
in one colour is the picture that cannot be read -- so the colour
rides on the `Plane`, set per row from the Measure dock, and
`ViewSettings.plane_color` is what a plane nobody has coloured falls
back to.  Stored as an override and not as a copy of the default, so
moving the default still moves every plane that was left alone.

The two hard ones both came down to the same fact — **there is no
per-atom mesh.**  Every ellipsoid is one instanced `vtkSphereSource`
under a scale and a quaternion, so ORTEP's octants could not be
per-point colours.  They are a second glyph over the same arrays
instead: one small source of three principal sections and two opposite
octants, which is right on every ellipsoid because every ellipsoid is
the same unit sphere transformed.  Two opposite octants and not
ORTEP's one, because a single octant fixed in the ellipsoid's frame
faces away from the camera half the time and an atom that loses its
shading as the structure turns reads as a different kind of atom.
They are drawn only where the refinement measured an orientation.

Occupancy pies could not take that route -- the angles differ per site
-- so they are real triangles from the builder, like a coordination
polyhedron, over the spheres they replace rather than instead of them:
every array in the scene model is indexed by drawn atom, and dropping
the occupants of a shared site would put the labels, the legend, the
picking and the selection flags out of step to save geometry that is
hidden anyway.  Both offsets are set by the tessellation and not by
taste, and the arithmetic is written down where they are.

**And a pie faces the camera**, which is the one thing in the builder
a camera gets a say in.  Cut about a fixed crystallographic axis the
same 60/40 site reads as any split at all from most directions, and a
pie chart that cannot be compared is not a pie chart.  It is still not
a scene rebuilt on every orbit: the builder emits the vertices once as
offsets from their own centre in a frame of the pie's own, and
`SceneModel.pie_geometry` turns them onto the camera's axes -- from a
render observer in the viewport, the way the depth cue and the scale
bar already work, and from the projection's own frame in the SVG
export, so the exported figure is not the one picture where the
wedges cannot be compared.

**The vector export also had its order wrong.**  A bond half was
painted at its *midpoint's* depth, which is nearer than the atom it
starts at whenever the bond runs towards the camera -- so half the
bonds in any figure were drawn across the faces of their own atoms.
A half carries its own atom's depth now, and the stable sort plus the
emission order in `render_svg` puts it immediately behind the sphere
it grows out of.

**Phase 4 was three fixes and one document.**  The axis letter is a
label beside each cell spin rather than the spinbox's prefix, which is
what had been drawing it inside the field where the number goes; a
cell-count change resets the camera, because growing 1x1x1 into 3x3x3
puts eight ninths of the picture outside a frame that was set for one
cell.  That rule is on the toolbar handler and deliberately not on
`Document.set_cells`: a camera belongs to a viewport, `set_cells` is
also called with nobody watching, and the second route to the same
ranges -- `DisplayRangeDialog` -- does not go through it anyway.  Nor
should it.  That dialog composes a picture with the camera already
placed on what is being looked at.

**Help is generated, not written.**  Every action already carries the
sentence it shows in the status bar and every module parameter carries
its own `help`, so `Help > Crystal Builder Help` reads both registries
and builds two pages at the moment it opens: every command grouped the
way the menu bar groups it, and every module with what each of its
settings accepts.  Prose typed beside them would have repeated all of
it and then drifted.  A command with no tip shows as a name and a key
and nothing else, which is honest and is also the list of tips still
owed.

**The menu and toolbar rearrangement was written as a proposal --
[docs/MENUS.md](MENUS.md) -- approved, and then built in the same
phase.**  Its first section was not a matter of taste: Window sat
after Help because `build_docks` appended a menu of its own after
`build_menus` had finished, so the menu bar's order was a property of
two files' call order rather than of either file's contents.
`build_menus` creates the Window menu now, in the place the bar should
read it, and `build_docks` fills it -- which is the only half that
needs the docks.

The bar reads File · Edit · Select · **Structure · Symmetry · Cell** ·
**Measure · View** · Modules · Window · Help: what edits the crystal
together, what changes the picture together, and what is about the
application last.  The six mouse modes are a `Mouse mode` submenu
rather than six flat entries that made the bottom of Structure read as
though a mode were an edit, and Open Recent moved up beside Open
Sample from the far end of the menu.  On the toolbar the element combo
moved to the mode it belongs to -- it is the element Add atom places,
and it stood beside Recalculate bonds -- and Reset view moved out of
the undo group to close the bar with the three axis views, which were
on no toolbar at all.  Those are a letter wide there and still
`Along a` in the menu, because a toolbar button shows an action's icon
text.

**Nothing was renamed, so the expensive half was never paid.**  Six
test files assert action *text* and action *keys*; not one of them
changed, because every registry key is the key it was.  Nothing
asserted menu *order* before, which is what made the rearrangement
cheap -- and something does now, because the point of the fix is that
the order should be a thing a file states.

Items 18 and 21 were deleted from the TODO header without being built:
Preferences shipped some time ago as a five-page dialog on Ctrl+comma,
and the Supercell rename is withdrawn -- `Cell > Supercell...` builds
a genuinely periodic supercell, and the non-periodic replication is
the toolbar spins the same phase relabelled.

---

## 9. Phase V — the engines answer in pictures

**Goal:** the half of the external tools that is a drawing rather than
a number, and the half of DFTB+ that its own driver does better.

| Item | TODO section | Size |
|---|---|---|
| Export a net as `.cgd` for Systre | Topology | S |
| Zeo++: draw the answer, do not only print it | Modules | M |
| DFTB+'s own driver | Modules | L |

**The `.cgd` writer first, and it is an afternoon.**  The naming has
shipped — the Net panel says **pcu** and the canonical key makes that
a decision rather than a match — and there is still no way to *doubt*
it.  `xtal/io/cgd.py` reads the format and does not write it; a writer
and an action that saves the drawn net through it is the only way to
put a net in front of **Systre**, the reference implementation, and
get a second opinion that does not come from the code that produced
the first.  The format is one `CRYSTAL` block with `NAME`, `GROUP P1`,
`CELL` and one `NODE` per vertex with an `EDGE` per edge, and the net
is already in exactly that shape.  Take it in Phase Q instead if
PORMAKE's `.cgd` handling makes it fall out — but take it once.

**Zeo++ is the reason this phase exists.**  The three diameters are in
a table and the table is right, and a porous-materials application that
can only *print* 9.18 Å is a spreadsheet.  The largest free sphere
drawn where it actually sits is the picture somebody puts in a paper.
`-res` gives the diameter and not the position, so this needs `-chan`
or `-visVoro` and a new actor beside `_set_polyhedra` — which is the
same actor Phase S builds for planes, and is the argument for S coming
first.  Channel dimensionality (1D, 2D or 3D pores) falls out of
`-chan`'s output for free, and `-vol` is parsed already and wants an
action of its own.

**DFTB+'s own driver is a module, not an engine.**  Reached as an
engine it already does a single point and a geometry optimisation with
the symmetry projection intact; what its internal driver does better
is **lattice relaxation** — ours costs twelve extra energy evaluations
a step because no analytic stress is claimed — and **molecular
dynamics**, which has no route through `Calculator` at all: MD is a
trajectory DFTB+ produces, not a sequence of energies we ask for.

Most of it is already written.  `xtal/ff/dftb/hsd.py` writes the input
and checks the parameter set, `xtal/io/gen.py` reads the geometry back,
and `xtal/modules/process.py` runs, streams and cancels it.  What is
new is a `Driver` block, the parsing of a multi-step output, and the
trajectory read back into the transport bar.

**The cheaper half of the stress question is worth doing first**: read
DFTB+'s printed stress tensor and *check* it against `numeric_stress`
on a structure with a known answer.  If it agrees, the engine can claim
it and variable-cell relaxation gets twelve times cheaper without the
driver being written at all.

**Phase I's redraw rule applies here in full.**  Whatever DFTB+ writes
into its run folder has to be a function of the run and not of what the
window was showing: no frame skipped because nobody was looking, and
the trajectory after a headless `xtal run` byte-for-byte the same as
after a watched one.

---

## 10. Phase W — the klassengleiche half

**Goal:** *Descend to a subgroup* offers the subgroups that split an
orbit without touching the cell, and then the ones that double it.

| Item | TODO section | Size |
|---|---|---|
| A lost centring, in the same cell | Symmetry | M |
| A doubled cell, from the table | Symmetry | L |

One TODO entry, two pieces that are nothing like each other, and they
are separated here because the first is a computation and the second is
a data set.

**A lost centring needs no cell transformation at all.**  Fm-3m
contains Pm-3m as a genuine subset of its operations, at index 4, in
the same cubic cell; rock salt descended that way puts its four sodiums
and four chlorines on eight independent sites, which is the
cation-ordering model.  It is also why halite is the one fixture in the
suite where no descent splits anything.

**It does not fall out of the existing enumeration** by not dividing
the centring out.  `xtal/core/subgroups.py` reduces modulo the centring
translations on purpose: the reduction is what makes the closure
affordable, and the "generated by at most three elements" shortcut — a
fact about crystallographic *point* groups — stops being safe the
moment the translations are back in.  A run that assumes it over
Fm-3m's 192 operations reports 96 maximal subgroups, some maximal only
because the intermediate group needed a fourth generator and was never
found.  The tractable route keeps the reduction: enumerate the
subgroups of the *centring* group that the point group leaves
invariant, lift the reduced generators through each coset
representative, and close.  For F that is a handful of closures.
Naming and application need nothing new.

**The doubled cell is the table.**  Superstructures and
antiferromagnetic ordering live there, every relation carries its own
cell transformation and origin shift, and that is Bilbao's MAXSUB
rather than a computation.  Worth doing last, and worth not implying
the earlier versions do it — the dialog says *translationengleiche*
and no cell is doubled, which stays true until this lands.

---

## 11. Summary

| Phase | Theme | Rough size | |
|---|---|---|---|
| **1–7** | The TODO header, by area — § 3 | M–L | *3 of 7 shipped* |
| **V** | The engines answer in pictures | L | |
| **W** | The klassengleiche half | L | |

The header phases and V and W together schedule **every entry left in
[docs/TODO.md](TODO.md)**, and nothing else.  P is the one phase with
no TODO entry behind it, because nobody using the application ever
asked for it and nobody using it will see it.  An entry ships when its
phase does; a new entry arriving in TODO.md joins the phase it belongs
to rather than starting a new one, and the day one does not fit any of
them is the day this file is wrong and gets rewritten again.

The order is one argument, and it has changed since the last version of
this file.  It used to be *a wrong number is worse than a missing one*,
and those phases have shipped.  It is now: **clear the ground, then
build something new, then make what is already there easier to see.**
P cleared the ground and Q built the first thing; U is the other
phase that produces a structure rather than trusting one; R, S and T
are the ordinary hour;
V and W are the two places where an external tool and a piece of
crystallography most users will never reach are still owed work.

## 12. What this plan does not do

* It does not schedule PXRD, volumetric data, SHELX round-trips or
  Rietveld.  Those are in [docs/PLAN.md](PLAN.md) § 12 and stay there
  until something in this list is finished.
* It does not promise the 2D sketcher.  It promises the 3D builder
  underneath it, a text route into it, and — in Phase Q — a builder for
  the one class of material where the 2D half is not needed at all.
* It does not write a reticular builder.  Phase Q integrates one, and
  the argument for that is in the phase.
* It does not touch the design principles in
  [docs/PLAN.md](PLAN.md) § 1.  Every phase above keeps the core
  Qt-free, keeps every mutation a command, and adds capability through
  registries — and where an entry in TODO.md is expensive, it is
  usually because it is being made to obey those rules rather than go
  around them.
