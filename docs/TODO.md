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

## Bonding

### Bond order set by hand, and drawn

Which bonds are double, triple or aromatic is chemistry, and a distance
criterion is not qualified to decide it: 1.39 A between two carbons is
aromatic in benzene and a stretched double bond in an unrelaxed
geometry, and nothing in the distance tells them apart.  The user has
to be able to say, once, and have it stay said.

Phase G built the half that draws it, and the plumbing underneath.
`bonding.orders` infers an order for every bond, `SceneModel` carries
it, the viewport draws two tubes for a double and three for a triple,
and an explicit `Bond` whose order the user set is honoured instead of
inferred.  What is missing is the way to *say it*.

* An order on a selected bond -- **single, aromatic, double, triple**
  -- from the bond context menu and from the Inspector.  `Bond.order`
  is already a float on the model and already round-trips through
  `bonds.json`, and the picture already shows it; what is missing is
  the control.
* **"Not stated" needs to be spellable.**  Perception currently treats
  an explicit bond left at the default order of 1.0 as *unstated* and
  infers it like any other, which is right for a bond drawn in the
  add-bond tool and wrong the moment somebody deliberately sets one to
  single.  A sentinel -- `order: float | None`, with `None` meaning
  "nobody said" -- is the honest model, and it needs a migration,
  because every bond already written to a `bonds.json` carries a
  literal 1.0 that must not become a statement.
* Symmetry, as everywhere else: setting the order on one bond sets it
  on the whole orbit, because it is the *pair* that is stored.
* The force field already reads `bonding.orders` rather than inferring
  its own, so a hand-set order reaches the energy the moment it can be
  set; see *The force field must never change the structure*
  (§ Force field) for why it must read this and never write it.

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
* The same rule for **bond order**.  UFF's bond orders are inferred
  today; once *Bond order set by hand* (§ Bonding) exists they are
  read from the graph, and the inference is only the fallback for a
  bond nobody has labelled.
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

### The same file can be opened twice at once

Opening a file that is already open gives a second tab over the same
bytes, and from then on there are two documents with two undo stacks
editing what the user thinks is one structure.  Whichever is saved
last wins and the other one's work is gone, with nothing having said
so.

* The test is the resolved path -- same location *and* same name --
  and not the file name alone: `data/a/MFU4l.cif` and
  `data/b/MFU4l.cif` are two different crystals that happen to share a
  name, and refusing to open the second would be worse than the bug.
  `Path.resolve()` also settles the symlink and the `/var` versus
  `/private/var` cases, which are the same file spelled two ways.
* What to do about it is to raise the tab that already has it, and say
  so in the status bar.  Not a dialog: the user asked to see that
  file, and showing it to them is the answer.
* It belongs in `MainWindow.open_path`, which is the one door every
  route in goes through -- the Open dialog, the recent list, the
  workspace tree, drag and drop, and the command line.
* The one case that is genuinely two documents is a file opened, then
  changed on disk by something else, then opened again to compare.
  That is rare enough to want an explicit "Open a second copy" rather
  than to be the default.

## Modules

### DFTB+

Periodic, DFT-like, and fast enough to relax a framework that UFF can
only approximate -- the natural second engine, and the one that makes
a UFF geometry checkable.

* It is an **external binary**, not a library, so it goes through the
  process runner Phase D wrote (`xtal/modules/process.py`): declare a
  `Program("dftb+")` so a missing binary greys the module out instead
  of failing inside a subprocess, write `dftb_in.hsd`, launch in the
  run folder, and read `detailed.out` and `geo_end.gen` back.  Nothing
  about it belongs in-process, and none of the launching, streaming or
  cancelling has to be written again.
* New I/O, both small and both worth having anyway: a `.gen` reader and
  writer in `xtal/io` (it is the simplest crystal format there is), and
  an HSD writer for the input.
* **The Slater-Koster parameter sets are what will actually block a
  user.**  They are separate downloads (3ob, mio, matsci, pbc), they
  are per-element-pair, and a run fails at the first missing pair.  So:
  a preference pointing at the set directory, and a check *before*
  launching that every element pair present has a file -- naming the
  missing ones, rather than letting DFTB+ fail inside a subprocess.
* Options that have to be in the form: SCC on/off and its tolerance,
  the k-point mesh (with a sensible default from the cell dimensions),
  the parameter set, dispersion, spin, and the run type -- single
  point, geometry optimisation, lattice optimisation, MD.
* Two ways in, and both are worth it: behind `ff/api.py::Calculator`
  for energies and forces, so the optimiser already here can drive it
  with the symmetry projection intact; and as its own module for the
  cases where DFTB+'s own driver is better -- its lattice relaxation
  and its MD.
* It runs for minutes to hours, so **cancel has to terminate the
  process**, not just abandon the thread, and the log has to be live or
  there is no way to tell a slow SCC cycle from a hang.
* With no binary installed the module says so plainly and points at the
  preference.  An external tool that is missing is the most common
  state it will be in.

### Zeo++

Pore-size distribution, accessible surface area, pore volume, channel
dimensionality, and the largest included and free spheres -- the
numbers a porous-materials paper reports, and the reason to build a MOF
in this application rather than look at one.

* Also an external binary (`network`), also through
  `xtal/modules/process.py`, and it shares every piece of that
  machinery with DFTB+ -- which is why the runner was written once, in
  Phase D, rather than twice here.
* Input is `.cssr` (or `.cuc`), so `xtal/io` gains a small writer, plus
  the radii file Zeo++ keys its atom radii from.  Getting the radii
  right is not a detail: every number Zeo++ returns is a function of
  them, and the default set is not the one every paper used.
* Output is a handful of small text files -- `.res`, `.sa`, `.vol`,
  `.psd_histogram` -- each of which parses into a table or a histogram.
  That is exactly the `Analysis` result shape [docs/PLAN.md](PLAN.md)
  § 14 describes, and the first real test of it.
* **The high-value half is drawing the answer back into the
  viewport**, not printing it: the accessible volume as an isosurface,
  the largest free sphere as a translucent ball where it actually sits.
  The polyhedra style already puts generated geometry into the scene
  and is the machinery to reuse.
* Everything it computes assumes a periodic structure with explicit
  atoms and full occupancy.  A disordered structure has to be resolved
  first, and the module should refuse and say why rather than hand
  Zeo++ something that will return a confident wrong number.

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
