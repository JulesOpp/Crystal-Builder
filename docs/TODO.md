# TODO

Work that is wanted but not yet scheduled into a phase.
[docs/PLAN.md](PLAN.md) holds the roadmap; this file holds everything
that came up while using the application and does not belong to a phase
yet.  An entry gets deleted when it ships, not ticked.

[docs/ROADMAP.md](ROADMAP.md) is the delivery plan for what is in
here: which phase each entry belongs to, in what order, and what has to
exist before it.

---

## Appearance

### A fixed scale bar, so a relaxing cell is seen to relax

Watching a variable-cell optimisation, the cell does not appear to
change.  It is changing -- that is the point of the run -- and the
picture hides it, because there is no fixed length on screen to judge
it against and the eye has nothing to hold on to but the box, which
fills the same fraction of the window throughout.

* **A scale bar**: a labelled ruler in Angstrom in a corner of the
  viewport, drawn in display coordinates from the camera's parallel
  scale, so it says how long a fixed number of pixels is.  Under an
  orthographic camera that is exact; under a perspective one it is
  the length at the focal plane and has to say so or be hidden.
* **It must not be rescaled during a run.**  A bar that renumbers
  itself every frame is the same failure as a camera that refits every
  frame: both keep the picture looking constant while the thing being
  drawn changes.  Fix the bar at the start of a relaxation and leave
  it, so a cell that contracts by 4% is a box that visibly shrinks
  against a ruler that does not.
* The camera is already right -- `ViewportWidget.rebuild` is called
  with `reset_camera=False` for everything except a new document -- so
  the zoom does hold.  What is missing is the reference length beside
  it.
* **And the drawn box has to follow the lattice.**
  `VtkScene.set_positions` updates atoms, bonds, polyhedra, highlights
  and labels, and not `_cell_poly`, so during a variable-cell preview
  the atoms move inside a cell frame that is still the old one.
  `_same_shape` compares `n_cell_lines`, which does not change when
  the cell merely changes *size*, so the fast path is taken and the
  box never moves.  The frame's points have to be refreshed alongside
  the atoms.
* `ViewSettings` gains `show_scale_bar`, with a View menu toggle, and
  it is view state: never on the undo stack, never in the structure.

### A plane you have defined is nowhere on screen

`Measure > Define plane from selection` fits a plane through the
selected atoms and puts a row in the Planes list, and that row is the
only evidence it exists.  The angle between two of them is a number in
a table; which two planes it is between, and whether either of them is
the plane the user meant, cannot be checked at all -- a least-squares
fit through six atoms of a buckled ring is a plausible answer to
several different questions, and the deviation column says how bad the
fit is without saying what it is a fit *to*.

* **Draw it as a translucent quad**, in the viewport, at the plane's
  own centroid and normal.  `measure.plane` already returns both
  (`Plane.centroid`, `Plane.normal`), so nothing has to be computed --
  it is the drawing that is missing.
* **Sized from its own atoms**, not from a fixed number: the extent of
  the atoms it was fitted through, projected onto the plane, plus a
  margin.  A plane through one ligand of a framework and a plane
  through the whole cell are different objects and should not be drawn
  the same size.
* **Only the ones the user is looking at.**  The Planes list is
  multi-select and already emits what is chosen (`_on_plane_chosen`);
  drawing the selected rows, and all of them when nothing is selected,
  is the rule that makes six planes usable.  Each one gets the normal
  as a short line, because two nearly parallel planes are told apart
  by their normals and not by their faces.
* Mechanically this is a new field on the scene model and a new actor
  in `VtkScene`, alongside `_set_polyhedra` -- which is the existing
  machinery for putting generated geometry into the scene and takes
  triangles and a colour, which is all a quad is.  The builder reads
  `document.planes` the way it already reads `document.selection`.
* A plane is re-fitted from its atoms whenever they move, so the drawn
  quad follows a relaxation for free.  It has to be rebuilt rather than
  moved -- its size and orientation both change -- which means
  `planesChanged` and a geometry change both reach the viewport, and
  today only the first of them does.
* It is **view state and not structure**: never on the undo stack,
  saved in the session beside the planes themselves, with a
  `View > Show planes` toggle so a picture for a paper can have the
  measurement without the scaffolding.

### An atom has nothing to say when you hover over it

There is no tooltip in the viewport, so everything the application
knows about an atom has to be gone and looked for: its label and
element are in the Sites dock, its UFF type and the reason for it are
in the Force Field dock, and its displacement parameters are nowhere at
all.  Hovering is how a person asks "what is this one?", and the
question currently has no cheap answer.

* A hover handler on `ViewportWidget`, over the picking that already
  exists -- `picking.pick` is exact and vectorised, and a mouse-move
  is not a hot loop, so nothing new is needed to find what is under
  the cursor.
* What goes in it is the interesting decision, and it should be what
  the *current* view is about: the label and element always; the UFF
  type and its reason when the Force Field dock is open; U_eq and
  whether it was refined anisotropically when the ORTEP style is
  drawn.  A tooltip that always says the same four things is one
  people learn to ignore.
* Phase E parked "the type in words does not reach a viewport tooltip"
  against Phase G, where it was never scheduled; this is that entry,
  sized as the feature it actually is.

### The window does not open the way it should

The default arrangement puts the two trees on the left and tabs seven
panels on the right, of which three are shown.  What a first run should
give is the arrangement somebody actually works in:

* **Top left: Structure** (`info_dock`) -- the formula, the cell, the
  space group, the hand.
* **Bottom left: Workspace** (`file_dock`) -- what is on disk and what
  has been run.
* **Middle: the structure itself**, which is already the central
  widget.
* **Right: Sites** (`sites_dock`) -- the asymmetric unit, editable.

* Mechanically this is `MainWindow.DEFAULT_VISIBLE` and
  `apply_default_layout`: `info_dock` and `file_dock` move to
  `left_docks` and are *split* vertically rather than tabbed --
  `splitDockWidget(self.info_dock, self.file_dock, Qt.Vertical)` --
  and `sites_dock` becomes the raised tab on the right.
* It is the *default*, not a rule: a saved layout still wins, which is
  what `restore_window` already does.  What changes is the state a new
  installation starts in, and `Reset layout` has to land on the same
  one or the menu item stops being a way back.

## Editing

### Add Atom should place the atom at a bond length

Add-atom drops the new atom wherever the click ray meets the view
plane, which is the right behaviour over empty space and the wrong one
over an existing atom: what a click on a carbon means is "another atom
bonded to this one", and landing it at whatever depth the plane
happened to be is never that.

* **Click an atom, then click a direction.**  The first click on an
  existing atom anchors the new one to it; the second click fixes the
  direction, and the atom is placed along it at the bond distance for
  that pair -- roughly 1.2 A for a C-C single bond, and properly the
  sum of the two covalent radii, which `xtal.core.elements` already
  carries and `bonding` already uses for perception.
* **It has to be visible while it is happening.**  Between the two
  clicks, a ghost atom at the fixed radius follows the cursor, with
  the bond drawn to it: the same interaction as add-bond, which
  already keeps a first endpoint between clicks
  (`AddBondMode.on_deactivate` clears it), so the state machine is
  the one that exists.
* The anchored distance is what makes the placement usable without a
  dialog, so the *direction* is all the second click has to carry:
  project the click ray onto the sphere of that radius around the
  anchor, and use the near intersection, falling back to the closest
  approach when the ray misses.
* A click on empty space keeps today's behaviour exactly, and
  `Escape` between the two clicks abandons the anchor.
* The bond it implies should be created with it, as an explicit bond,
  rather than left for perception to find -- the user has just said
  what it is bonded to.
* Whether the default distance should follow the element pair or be a
  single number in the Add Atom dialog is worth deciding before
  building: the pair-wise number is right and the dialog is where a
  user would look to override it.

### Editing the cell must not re-perceive the bonds

`Cell > Edit cell` changes the lattice, and the bonds come back
different.  That is right when it is asked for and wrong as a side
effect: a user who nudges *c* by a hundredth of an Angstrom to match a
refinement has not asked for their bond graph to be rebuilt, and if a
bond they drew by hand disappears at that moment they have no reason
to connect the two.

* **Recalculate bonds is the only thing that recalculates bonds.**
  The button and `Ctrl+B` mean it; nothing else does.  The one
  exception stays the `Bonds follow the geometry` preference, which is
  off by default and exists to be switched on deliberately.
* Mechanically this is `Document._after_change`: a `Change.CELL` must
  not drop the perceived bonds or the `bonds:` cache the way a
  `Change.POSITIONS` does under the preference.  The stored graph is
  what the bonds are; perception is what fills it in when asked.
* The same argument covers every other edit that changes the cell
  without moving an atom in it -- `SetLattice` with fractional
  coordinates kept, a Niggli reduction, a change of setting.
* Say it in the dialog, once: "the bonds are unchanged; recalculate
  them if the new cell should change them".  A user who *does* want
  them rebuilt after stretching a cell by 20% needs to be told the
  button is there.

### Measure from the right-click menu

Distance, angle and torsion already exist -- `xtal.core.measure`
computes all three and the Measure dock lists them -- but reaching
them means switching into a measuring mode and clicking the atoms
again, in order, having already selected them.

* With **2, 3 or 4 atoms** selected, a right click on any of them
  offers the measurement that number of atoms admits: *Measure
  distance* at two, *Measure angle* at three, *Measure dihedral* at
  four.  One entry, not three, and it is absent at any other count
  rather than greyed out.
* The order is the selection order, which means `Selection` has to
  keep one.  It stores a set today, and for three atoms picked as
  A-B-C the vertex is B and no other reading is right -- so this needs
  an ordered selection or a stated rule ("the order you clicked
  them"), and stating the rule without keeping the order is a lie.
* It lands in the Measure dock like any other measurement, and it
  uses `measure.unwrapped_positions` so a measurement across a
  periodic boundary is the short one and not the one through the cell.
* This is a new entry in `MainWindow.CONTEXT_MENUS["atom"]`, built at
  click time because it depends on the count -- the same shape as
  `COUNTED_ACTIONS`, which already rewords an entry to say how much it
  will take.

### Edit cell from the right-click menu

`CONTEXT_MENUS["view"]` offers what to draw and where the camera is,
and nothing about the box everything sits in.  The cell is the one
thing that is always under the cursor, whatever was clicked, so
**Edit cell** belongs in every one of the three menus -- atom, bond
and view -- not only the one for empty space.

* One name in three lists; the action already exists, is already
  undoable and already has a dialog that previews.
* Worth the same treatment for `display_range`, which is in the view
  menu only for the same accident.

## Symmetry

### Descend to a klassengleiche subgroup

`Symmetry ▸ Descend to a subgroup` offers the **translationengleiche**
subgroups -- same lattice, a subset of the operations -- and those are
the ones that split an orbit without touching the cell.  The
klassengleiche half is not offered, and it splits into two pieces that
are nothing like each other in difficulty.

* **A lost centring needs no cell transformation at all.**  Fm-3m
  contains Pm-3m as a genuine subset of its operations, at index 4, in
  the same cubic cell.  Rock salt descended that way puts its four
  sodiums and four chlorines on eight independent sites, which is the
  cation-ordering model -- and it is the reason halite is the one
  fixture in the suite where no descent currently splits anything.
* It does *not* fall out of the existing enumeration by simply not
  dividing the centring out first.  `xtal/core/subgroups.py` reduces
  the operations modulo the centring translations on purpose, and the
  reduction is what makes the closure affordable: over Fm-3m's full
  192 operations the subgroup-lattice walk is a different size of
  problem, and the familiar "generated by at most three elements"
  shortcut -- a fact about crystallographic *point* groups -- stops
  being safe the moment the centring translations are back in the set.
  A run that assumes it over 192 operations reports 96 maximal
  subgroups, some of them maximal only because the intermediate group
  needed a fourth generator and was never found.
* The tractable route keeps the reduction: enumerate the subgroups of
  the *centring* group that the point group leaves invariant, lift the
  reduced group's generators through each choice of coset
  representative, and close.  For F that is a handful of closures, not
  a walk over 192 elements.  The naming and the application are
  already built and need nothing new -- `_name` and
  `supercell.change_setting` do not care where the operation list came
  from.
* **A doubled cell is the half that needs the table.**  That is where
  superstructures and antiferromagnetic ordering live, and every
  relation carries its own cell transformation and origin shift --
  Bilbao's MAXSUB, not a computation.  Worth doing last, and worth not
  implying the earlier versions do it: the dialog currently says
  "translationengleiche" and no cell is doubled, which stays true
  until this lands.

### Merge duplicates never looks at the symmetry

`Ni2Cl2BTDD.cif` is the case that shows it.  The CIF was written with
a full cell's worth of coordinates under `H-3m`, so `C1` and `C1X` are
the same carbon written twice -- and `Structure ▸ Merge duplicate
sites` reports "no duplicates found" at every tolerance.

* `symmetry.merge_duplicates` compares the fractional coordinates of
  the asymmetric-unit sites **directly**, so it only ever finds sites
  that were written on top of each other.  `C1` and `C1X` are 7.2 A
  apart as written; the closest *image* of `C1` is 2e-5 A from `C1X`,
  which is what makes them the same atom.  The comparison has to be
  against the orbit, not against the parent: expand the sites kept so
  far and ask whether the candidate lands on any of their images.
* The scale of what is being missed is worth stating.  Expanding that
  file gives 1188 atoms in the cell, of which 2150 pairs are within
  half an Angstrom of each other -- the structure is several complete
  copies of itself, and every derived number computed from it (the
  formula, the density, the energy) is wrong by that factor without
  anything on screen saying so.
* **A tolerance control.**  The function already takes `tol` and
  defaults to 0.05 A; the menu item calls it with the default and
  offers no way to change it.  Experimental coordinates from a
  refinement that placed the same atom twice are rarely closer than
  that, so the setting that matters most is not reachable.  A small
  dialog with the tolerance and the count it would merge beside it --
  the same shape as the bond-rules dialog's radius factor -- is what
  this needs, because the right tolerance is a property of the file
  and not of the application.
* Merging by orbit has a consequence to get right: the site that is
  kept must be the one whose Wyckoff position is the more special, or
  the multiplicity of what is kept changes the formula.  Keeping the
  first site written is right when both are general and wrong when one
  of them sits on the axis.

## Force field

### The force field must never change the structure

A force field reads a structure and returns numbers.  It does not get
to add atoms, remove them, or decide what is bonded to what -- and
where it does that today it is doing the user's job without being
asked, which makes the result of a calculation depend on something
nobody chose and nobody can see.

* **Hydrogens are the case that shows it.**  `xtal/ff/hydrogens.py`
  exists so that a structure missing its hydrogens can be typed and
  relaxed, and adding them is a perfectly good thing to *offer* -- as
  `Structure > Add hydrogens`, on the undo stack, visible in the
  Sites panel, with the user looking at what it did.  It is not a
  good thing to do inside `single point` or inside an optimisation,
  because then the geometry that comes back is not the geometry that
  went in and the energy is not the energy of what is on screen.
* The same rule for **bond perception**.  The force field needs a
  topology; it must take the one the structure has, and if that
  topology is wrong the fix is for the user to press Recalculate
  bonds or draw the bond, not for the calculation to quietly perceive
  a different one.  A force field that re-perceives is also a force
  field whose answer changes when its own cutoffs change.
* The same rule for **bond order**.  UFF reads `bonding.orders`, which
  honours a bond the user typed by hand and infers only the ones
  nobody has labelled -- so what the force field must not do is
  re-decide an order the user stated.
* **What it may do is refuse.**  A structure the force field cannot
  type -- missing hydrogens, an element with no parameters, an
  unbonded fragment -- gets a clear refusal naming the atoms and
  offering the command that would fix it.  "Add the 24 hydrogens this
  needs?" as a question, with the answer applied as an ordinary
  undoable edit before the run starts, is the whole of what the
  current behaviour was reaching for, and it leaves the user holding
  the pen.
* Concretely: `ff/api.py` and the optimiser take the structure as
  given, `ff/hydrogens.py` is reachable only from the Structure menu
  and its dialog, and every FF entry point that currently mutates
  becomes a check that reports.

### The cutoff and the skin have no controls

The van der Waals pair list is built with arrays now -- 4.0 s down to
0.49 s for a 5184-atom cell -- and what is left is the two numbers that
decide how big the job is in the first place.  Both are on
`UFFOptions`, neither is reachable.

* **The skin** (2.0 A) decides how often the list is rebuilt: it is
  rebuilt whenever any atom has moved half of it, which early in a
  relaxation from a hand-built geometry is every few steps.  A larger
  skin trades memory for rebuilds and is the cheapest knob there is.
* **The cutoff** (12 A) decides how large the list is, and the count
  goes as the cube of it: 10 A is 42% fewer pairs for an LJ tail worth
  about a thousandth of a kcal/mol per pair.
* Both belong in the Force Field panel next to the electrostatics
  controls, with what they cost said plainly rather than left for
  somebody to discover.

## Files and calculations

### The redraw rate must never decide what is recorded

The Force Field panel's **Redraw** control has "Not while it runs" at
one end, and it is the setting a user reaches for on a large cell --
the picture is the expensive part, and turning it off is how a long
relaxation is made to go at the solver's speed rather than the
renderer's.  What it must never do is cost them the trajectory.  A run
watched as a plot and a run watched as a moving crystal have to leave
*the same files behind*: every frame in `trajectory.extxyz`, every step
in the log, and the trajectory playable from the workspace tree
afterwards.

* The rule is one sentence: **the redraw rate is a property of the
  viewport and of nothing else.**  Every step is announced, the
  recorder is on the worker thread and writes each frame as it
  arrives, and the only thing the control changes is how often the
  scene repaints.  It is true of the force field today
  (`xtalapp/viewport/widget.py` throttles `previewChanged`;
  `xtalapp/workers.py` records unconditionally) -- this entry exists so
  it stays true and is asserted rather than assumed.
* **It is not asserted anywhere.**  A test that runs an optimisation
  with the interval at -1 and counts the frames in the written
  trajectory is the whole of it, and it is what stops a later
  "optimisation: skip the preview entirely when nobody is drawing it"
  from quietly deleting the record.
* The final geometry has to be drawn when the run ends whatever the
  setting says, which is a separate thing from the frames and equally
  easy to lose: the commit goes out on `structureChanged`, not on
  `previewChanged`, and only the latter is throttled.
* **The same applies to every engine that follows, DFTB+ first.**  Its
  geometry optimisation streams frames too -- read back from
  `geo_end.xyz` or from the driver's output as it runs -- and it will
  have the same control for the same reason.  Whatever it writes into
  its run folder has to be a function of the run and not of what the
  window happened to be showing: no frame is skipped because nobody
  was looking at it, and the trajectory in the tree after a headless
  `xtal run` and after a watched one are byte-for-byte the same file.
  The DFTB+ entry under *Modules* inherits this; so does anything
  driven through `ff/api.py`, which is the path that gets the
  throttling for free and the recording for free with it.

## Modules

### DFTB+'s own driver

DFTB+ is here as an *engine*: a `Calculator` in `ENGINES`, so the
optimiser already in this application drives it with the symmetry
projection intact and the panel, the plot, the trajectory and Stop all
work unchanged.  That is the right way in for a single point and for a
geometry optimisation, and it is the wrong way in for two things
DFTB+'s internal driver does better.

* **Lattice relaxation.**  Ours costs twelve extra energy evaluations
  a step because no analytic stress is claimed -- DFTB+ prints one and
  its sign and volume conventions were not worth guessing at, since a
  stress read the wrong way round relaxes a cell in the wrong
  direction and reports converging while it does it.  DFTB+'s own
  `Driver = ConjugateGradient { MovedAtoms ... LatticeOpt = Yes }`
  uses it directly.  Either that, or read the block and *check* it
  against a numeric stress on a structure with a known answer, which
  is the cheaper of the two and would let the engine claim it.
* **Molecular dynamics**, which has no route through `Calculator` at
  all: it is a trajectory DFTB+ produces, not a sequence of energies
  we ask for.
* As a **module** rather than an engine, then: one entry per driver,
  the run folder holding `dftb_in.hsd`, `detailed.out`, `geo_end.gen`
  and `md.out`, and the trajectory read back into the transport bar --
  which already plays anything `xtal/io/trajectory.py` can read.
* The parts that would be reused rather than rewritten are most of it:
  `xtal/ff/dftb/hsd.py` writes the input and checks the parameter set,
  `xtal/io/gen.py` reads the geometry back, and
  `xtal/modules/process.py` runs, streams and cancels it.  What is new
  is a `Driver` block and the parsing of a multi-step output.

### Zeo++: draw the answer, do not only print it

The three diameters, the surface area and the pore size distribution
are numbers in a table, and the table is right.  What is missing is the
half of the TODO entry that made this worth building for a
porous-materials application rather than a spreadsheet:

* **The largest free sphere where it actually sits**, as a translucent
  ball in the viewport.  `-res` gives its *diameter* and not its
  position, so this needs `-chan` (which writes the channel network) or
  `-visVoro` (which writes the accessible Voronoi nodes as xyz), and a
  new actor beside `VtkScene._set_polyhedra` -- which is already the
  machinery for putting generated geometry into the scene.
* **The accessible volume as an isosurface**, from `-vol`'s sampling or
  from `-gridBOV`'s distance grid.  Bigger, and the thing a paper
  figure actually wants.
* `-vol` and `-volpo` are parsed already
  (`xtal.analysis.porosity.Volume`) and have no entry of their own,
  because nothing yet asked for one.  A fourth action is eight lines
  the day somebody does.
* **Channel dimensionality** -- whether the pores form a 1D, 2D or 3D
  network -- is in `-chan`'s output and is one of the numbers a paper
  reports.  It comes free with whatever reads `-chan` for the sphere
  above.

## Building

### Draw in 2D, build in 3D

Maestro's sketcher: draw a molecule the way you would on paper, press a
button, and get it in 3D.  For this application the case is putting a
linker into a framework -- there is no way at all to make a benzoate
today except placing eleven atoms by hand and hoping.

It is two separate problems and they are worth keeping separate,
because one of them is solved and the other is a product.

**The 3D half is the tractable one.**  Connectivity plus element plus
bond order in, coordinates out.

* Build by fragments and torsions rather than by distance geometry:
  place each atom from the neighbour that put it there, using
  `terms.natural_bond_length(type_i, type_j, order)` for the distance
  and the type's own `theta0` for the angle, with staggered torsions.
  Every one of those numbers is already in `xtal/ff/uff` and is
  already the geometry UFF wants, so the result starts at the force
  field's minimum instead of somewhere that has to be dragged there.
* Then relax it with UFF, which is here, is tested, and covers the
  whole periodic table.  A molecule in vacuum is a molecule in a box
  large enough that the periodic images do not see each other --
  Coulomb is off by default and the vdW is cutoff-limited, so this
  needs no new code path, only a cell.
* Rings are the part the naive placement gets wrong: a six-ring closed
  by torsions does not close.  Place ring systems from templates
  (planar regular polygons for aromatics, a chair for cyclohexane) and
  hang the substituents off them, which is what every builder does and
  is enough for anything a linker is made of.
* Lives in a new `xtal/build/`, headless and testable: graph in,
  `Structure` out, no Qt anywhere near it.

**The 2D half should not be written here at all.**  A canvas of atom
and bond items, an element palette, click-to-cycle bond order, ring
templates, charges, implicit hydrogen counts, and the dozen
interactions that make drawing feel like drawing -- ChemDraw is a
product, and writing a small one is months that buy nothing this
application is for.  Take an existing editor.

* **[rdEditor](https://github.com/EBjerrum/rdeditor) is the candidate
  to try first.**  It is a molecule editor written in Python on
  **PySide6** with **RDKit** underneath, weak-copyleft licensed, still
  maintained (there is a 2024 software note describing it), and --
  the part that matters -- it is written so that its widgets are
  reusable: it is an editor *component* plus a shell around it, not a
  monolithic application.  Embedding its canvas widget in a dialog and
  taking the `Mol` back out is the shape to aim for.  What has to be
  checked before committing: that the editor widget really does come
  apart from its main window, and that its Qt version tracks ours
  rather than pinning us.
* **[BKChem](https://bkchem.zirael.org/) is the wrong shape for this.**
  It is GPL-2+, which is the wrong licence to link into an LGPL Qt
  application, it is Tkinter rather than Qt so it cannot be embedded at
  all, and the original project stopped in 2010 (a Python 3 port
  exists, which fixes the least important of those three problems).
  Worth naming here only so nobody spends a day rediscovering it.
* **Ketcher** (EPAM, Apache-2.0, actively maintained) is the serious
  alternative: a full sketcher in JavaScript, embedded in a
  `QWebEngineView`, handing SMILES or molfile back over its API.  It is
  the best editor of the three by some distance; the cost is
  QtWebEngine in the bundle, which is not small.  If rdEditor's widget
  turns out not to be separable, this is the fallback, not writing a
  canvas.
* **The cheap version that gets most of the value is a text box, and
  it comes first regardless.**  Accept a SMILES string, build it in 3D,
  drop it into the cell.  It is a hundred lines, it answers "put a
  benzoate linker in this cell", and whichever editor is chosen later
  produces the same graph and reuses the whole 3D half.  Ship this,
  live with it, and let the editor be a later decision made with
  evidence.
* **RDKit is the dependency question underneath all of it.**  It solves
  the 3D half too (`MolFromSmiles`, `EmbedMolecule` with ETKDG,
  `MMFFOptimizeMolecule`), and rdEditor requires it anyway, so choosing
  rdEditor is choosing RDKit.  The argument against making it required
  is packaging: it is a large wheel and would become the biggest thing
  in the PyInstaller bundle.  So: a `[build]` extra, RDKit-backed when
  installed, the native fragment builder as the fallback, one
  interface over both -- and the sketcher simply absent without the
  extra, which is honest and is how optional features should degrade.
* Where the result lands needs deciding.  A molecule has no cell.
  Building into an open structure means picking a position -- the
  camera's focal plane, as Add Atom already does -- and a
  `PasteFragment`, which exists and is already undoable.  Building into
  an empty document means generating a box with enough vacuum around
  it, which `supercell.add_vacuum` can already do.
* A fragment library is the same machinery pointed at a folder of saved
  graphs, and is listed in [docs/PLAN.md](PLAN.md) § 12 already.  Once
  SMILES works, the library is a JSON file of names and strings.
