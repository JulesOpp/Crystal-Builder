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

### ORTEP draw style

A draw style that shows atoms as **thermal ellipsoids** rather than
spheres — the picture every crystallographer expects from a refined
structure, and the one that makes a bad refinement obvious at a glance.

* A new entry in `xtalapp/viewport/styles.py`, plus the geometry that
  fills it.  The registry is designed for exactly this, so no existing
  style changes.
* Needs anisotropic displacement parameters on the site, which
  `Site.u_iso` does not carry: `Site` needs a `u_aniso` (the U11, U22,
  U33, U12, U13, U23 of the CIF `_atom_site_aniso_*` loop), the CIF
  reader needs to read that loop, and the writer needs to write it
  back.  `Structure` already round-trips through gemmi, so the data is
  there to be picked up.
* Rendering is a sphere glyph with a per-atom 3×3 transform: VTK's
  tensor glyph mapper takes the U matrix directly, so the scene
  model gains an `(M, 3, 3)` array next to `radii` and the actor
  count does not change.
* The probability level (50%, 90%) is a view setting, not structure
  data, and belongs in `ViewSettings`.
* Sites with only `u_iso` fall back to a sphere of the equivalent
  radius; sites with neither fall back to the current ball-and-stick
  radius.  Both cases have to be visible in the picture rather than
  silently drawn as if they were measured.

### Depth cueing

Fade distant atoms towards the background so a thick slab reads as
having depth instead of as a flat mat of spheres.  Listed among the
plan's viewport overlays (§ viewport) and not yet built.

* VTK 9 has no `SetFog` on either the property or the renderer, so
  this is a render-pass job: an `vtkOpenGLRenderer` render-pass chain
  ending in a pass that attenuates by depth, or — simpler and enough
  for a viewer — a shader replacement on the two glyph mappers via
  `vtkShaderProperty.AddFragmentShaderReplacement`, mixing the
  fragment colour towards the background by `gl_FragCoord.z`.
  `vtkDepthOfFieldPass` exists but is a blur, not a fade, and is the
  wrong effect.
* Front and back distances default to the scene bounds along the view
  direction, so it needs no configuration and rescales when the
  display range grows.
* `ViewSettings` gains `depth_cue: bool` and a strength; a View menu
  toggle and a control in the style panel drive it.  It is view state,
  so it never touches the structure and never lands on the undo stack.
* Keep it off in `render_offscreen` unless asked for, or the
  documentation images and the render tests change under it.

### Bonds inside polyhedra

The polyhedral style draws hulls and no bonds at all, which is right
for a dense inorganic framework and wrong for a structure that is
partly polyhedral and partly molecular -- an MOF, where the metal nodes
want polyhedra and the linkers want sticks.

* `DrawStyle` already carries `draw_bonds` and `draw_polyhedra`
  independently, so the style entry itself is a one-line change; what
  is missing is the choice of *which* bonds.
* Drawing every bond leaves a cage of sticks inside each hull.  What is
  wanted is every bond except the ones from a polyhedron's centre to
  its own vertices -- those edges are the polyhedron.  `_emit_bonds`
  would need the set of (centre, vertex) pairs `_emit_polyhedra`
  consumed, which means running the polyhedra first and passing the
  set down.
* Offer it as a style ("Polyhedra and sticks") rather than a checkbox,
  so it stays a registry entry and the style menu keeps describing the
  whole picture.

### Bond order in the picture

A double bond is drawn as one tube, exactly like a single one, so a
structure looks identical whether what is in front of you is butadiene
or butane.  The information exists -- it is what the force field types
every bond with -- and none of it reaches the screen.

* The orders are inferred today by `xtal.ff.uff.typer`
  (`Typing.bond_orders`), which is the wrong place for the viewport to
  reach into.  Move the inference down into `xtal/core/bonding.py` so a
  `CellBond` carries an `order`, and let the typer consume it rather
  than produce it.  Counting pi bonds is chemistry, not UFF's business,
  and the scene builder should not have to import a force field to draw
  a line.
* An explicit `Bond` already has an `order` field, so a hand-drawn bond
  keeps whatever the user set it to and perception only fills in the
  rest.
* Two parallel tubes for a double, three for a triple, one tube with a
  dashed inner line for an aromatic 1.5.  `SceneModel` gains a per-bond
  `bond_orders` array beside `bond_starts` and `bond_ends`, and
  `vtk_scene` emits the extra tubes from it; the actor count stays the
  same.
* **The offset direction is the whole problem.**  Two parallel tubes
  need a plane to lie in, and an arbitrary perpendicular to the bond
  flips as the camera turns -- the picture flickers on every orbit.
  Use the local pi plane: the normal of the atoms around the sp2
  centre.  A bare diatomic has no such plane; there, fall back to a
  perpendicular in the view plane and accept that it follows the
  camera, because there is nothing for it to be inconsistent with.
* `ViewSettings` gains `show_bond_orders`, and a View menu toggle.  A
  framework whose bonds are all single loses nothing by having it on,
  which is the right default; an MOF with 288 aromatic carbons is the
  case for being able to turn it off.

## Selection

### Invert Selection ignores symmetry

`Select ▸ Invert selection` inverts over the atoms of the P1 cell, but
every *edit* acts on whole symmetry orbits.  So inverting a partial
orbit gives a selection that overlaps the one it came from: the atoms
you had are still, in effect, selected, because their orbit-mates are.

* Grow to the symmetry orbit first, then invert
  (`Document.invert_selection` → `expand_selection("orbit")` then
  `Selection.invert`).  `sel.symmetry_orbit` already exists.
* The same argument applies to `Selection.invert` wherever it is
  reached from the UI; the core predicate should stay orbit-blind and
  the Document should be the thing that knows about symmetry, matching
  how delete and move already work.
* In P1 this is a no-op, which is the right way for it to degrade.

### Rectangular select

Drag a box over the viewport and take everything inside it — the
fastest way to grab a slab, a surface layer, or one end of a long
molecule, and the one selection gesture VESTA has that this does not.

* A new interaction mode (`xtalapp/viewport/modes.py`), so it slots in
  next to select / add-atom / add-bond without the viewport changing.
* Needs press-drag-release rather than the click the mode API carries
  today: `ClickEvent` gains a sibling `DragEvent` (press point, current
  point, modifiers), and `ViewportWidget.eventFilter` — which already
  distinguishes a drag from a click by `CLICK_SLOP` — feeds it.
* Hit test by projecting `SceneModel.positions` to display coordinates
  with the renderer's world-to-display transform and testing the
  rectangle; that is one vectorised pass and needs no VTK picking.
* Shift extends, as everywhere else.  A rubber band drawn over the
  render window (a `vtkBorderWidget`, or a plain Qt overlay widget) is
  what makes it feel like a selection rather than a guess.
* Whether the box takes only visible atoms or everything behind them
  too is a real choice: VESTA takes everything, which is what makes it
  useful for slabs. Do that, and say so in the status bar.

## Editing

### Arrow buttons on translate and rotate

The Move dock takes a number and applies it once.  Nudging — hold
the arrow, watch the fragment slide — is how the tool is actually
used, and it is missing.

* A pair of arrows per axis in the translate group, and a pair for the
  rotation angle: one step per click, auto-repeating while held.
* The command stack already merges repeated moves into one undo step
  (`Command.merge_with`), so a burst of nudges must arrive as one
  Ctrl+Z, not forty.  `MoveSites` merges today; check that it still
  does under auto-repeat and that the merge window ends when the button
  is released.
* The step size is the spinbox value, so the existing controls keep
  their meaning and the arrows are pure acceleration.
* Same treatment for rotation about the chosen axis.

### Make planar

A button that takes the selected atoms and **flattens them onto their
best-fit plane** — the fastest way to fix an aromatic ring that came
out of a builder or an optimiser slightly puckered.

* Best-fit plane by SVD of the mean-centred cartesian coordinates: the
  plane normal is the singular vector with the smallest singular value.
* Each selected atom moves along that normal onto the plane, which is
  the smallest displacement that makes them coplanar.
* Belongs in `xtal/core/transforms.py` as a free function, with a
  `PlanarizeSites` command over it in `xtal/commands/atoms.py` — the
  same shape as `TransformSites`, so it is undoable and scriptable.
* The button belongs in the Move dock next to mirror, and must report
  the largest displacement it made: "planarised 6 atoms, moved by up to
  0.08 Å" is the difference between a fix and a silent corruption.
* Symmetry: like every other move, this acts on whole orbits. Fewer
  than three atoms have no plane, and the button says so rather than
  doing nothing.

### Add hydrogens

An X-ray structure has no hydrogens.  Every rule in the force field's
typer is written to survive that, and every one of them is guessing as
a result: a benzene carbon judged by two neighbours, a methyl carbon by
one.  Putting the hydrogens back is the single most useful thing that
can happen before an energy is computed.

* Where an H goes is the coordination completed.  A three-coordinate
  sp3 carbon takes the fourth tetrahedral direction, a two-coordinate
  sp2 the third in the plane of the other two, a one-coordinate carbon
  three at once.  `xtal.ff.uff.typer` already decides hybridisation,
  coordination and planarity and already writes the sentence explaining
  why, so it is the input to this and not a second geometry pass.
* How many: `elements.VALENCE` less the current bond orders.  That
  table covers only the main group, which is the right scope -- nobody
  wants hydrogens guessed onto a metal -- and an element missing from
  it is left alone and reported rather than skipped in silence.
* Lengths from `terms.natural_bond_length(type, "H_", 1.0)`, so C-H
  arrives at 1.109 and O-H at 0.990 and the result is already sitting
  at the force field's minimum.  Neutron and X-ray H positions differ
  by 0.1 A for real reasons; offer the short one, do not default to it.
* **A terminal group's torsion is genuinely undetermined.**  A
  hydroxyl, a methyl, an amine: the coordination fixes every angle and
  nothing fixes the rotation.  Place them staggered against the
  heaviest neighbour-of-the-neighbour, say that is what was assumed,
  and let a relaxation settle it.
* Symmetry is the trap.  This works in site space like every other
  edit, so one hydrogen added to a site on a mirror plane becomes two,
  and one added to a general position becomes the whole orbit.  The
  count reported has to be the orbit count -- "added 12 hydrogens to 2
  sites" -- and a hydrogen that lands on a special position of its own
  has to be recognised rather than generated twice.
* A `MacroCommand` over `AddSites`, so the lot is one Ctrl+Z, with a
  preview of the count before it runs -- the `StructureOperation` shape
  the symmetry dialogs already use.

## Bonding

### Topology bonds

The underlying net of a framework -- **pcu**, **fcu**, **soc** -- is
not its bond graph.  It is what is left after deciding which parts are
nodes and which are linkers, and that decision belongs to a chemist and
not to a distance criterion.  A topology bond is that decision, drawn.

* A third value of `Bond.kind`, beside `"explicit"` and
  `"suppressed"`.  The field is already a string and already round-trips
  through `bonds.json`, so the change to the data model is one value.
* It has to be **invisible to everything chemical**.
  `bonding.perceive` currently treats any stored bond that is not
  suppressed as a bond to draw and to hand onward, so a topology bond
  would land in the force field's topology, in coordination numbers and
  in valence checks, and be wrong in all three.  `perceive` filters them
  out; a separate `topology_graph(structure)` hands them back as their
  own `BondGraph`.
* Drawn as its own layer -- thicker, translucent, one flat colour --
  running over the real bonds rather than in place of them.  Seeing the
  net and the chemistry that justifies it at the same time is the whole
  point of drawing it rather than printing it.
* What it is *for* is the net's invariants, and those come from the
  periodic graph: the coordination sequence and the point symbol at
  each vertex, which is how RCSR names a net.  Both are a breadth-first
  walk over `(atom, offset)` pairs -- the same bookkeeping
  `BondGraph.fragments` already does to tell a molecule from a
  framework, and the same that tells a ring from a lattice repeat.
* A "Draw topology bond" interaction mode next to add-atom and
  add-bond, and `Del` on a selected one.  It expands over the symmetry
  orbit like every other bond, which is what makes drawing one edge of
  a **pcu** net draw all six.
* **The open question is whether a vertex is an atom or a cluster.**
  Between atoms is what this describes, and it is enough for a net
  whose nodes are single metals.  A Zn4O cluster or a Kuratowski node
  wants its centroid as the vertex, which means an endpoint that is a
  *set* of sites rather than one.  Start with atoms, and keep the
  endpoint type loose enough that the second case is an extension and
  not a rewrite.

## Symmetry

### Descend to a maximal subgroup

Changing the space group today means picking any of the 230 and asking
the structure to fit.  The move that actually comes up is the small
one: drop to a maximal subgroup so that an orbit splits and the atoms
in it become independent.  That is the first step of every distortion
model, every ordering model, and every displacive phase transition.

* **Translationengleiche subgroups only** (k-index 1) to begin with:
  same lattice, same cell, a subset of the operations.  It is the case
  where nothing moves -- the P1 cell is atom-for-atom what it was and
  only the asymmetric unit grows -- so it needs no coordinate
  transformation, no origin shift and no new cell, and that is exactly
  why it is the one worth having first.
* **It is not a relabel, and this is the part to get right.**  Simply
  putting the subgroup on the existing sites *loses atoms*: quartz's
  oxygen has multiplicity 6 in P3_221 and 3 in P3_2, so the same two
  sites expand to six atoms where there were nine.  The operation is
  expand to P1 under the parent, then find an asymmetric unit inside
  those atoms under the child -- which is exactly what
  `SetSpaceGroup(group, mode="impose")` already does, already previews
  and is already undoable.  The new work is choosing the group, not
  applying it.
* They can be computed rather than tabulated, and a prototype of this
  runs in well under a second.  Reduce the operations modulo the
  lattice translations, enumerate the subgroups generated by every
  subset of at most three of them (every crystallographic point group
  has a generating set that small), close each under composition, and
  keep the maximal proper ones.  **The reduction is not an
  optimisation, it is the algorithm**: Fm-3m has 192 operations and 48
  once the centring is divided out, and the difference between 48^3 and
  192^3 closures is the difference between instant and hopeless.
* What it finds is right.  P4_2/mnm gives 7 maximal subgroups of index
  2, P3_221 gives 4, Pa-3 gives 6, and Fm-3m gives 10 spread over
  indices 2, 3 and 4 -- including the F4/mmm and R-3 that a
  crystallographer would name for the tetragonal and rhombohedral
  distortions of rock salt.
* **Naming the result is the hard part, not finding it.**
  `gemmi.find_spacegroup_by_ops` named 11 of the 27 subgroups in that
  test and returned nothing for the other 16, because the operations
  come out in the parent's basis and most subgroups are not in their
  standard setting there.  Finding the transformation to a standard
  setting is the work this entry is really asking for; a subgroup that
  can only be offered as a list of operations is not something anyone
  can choose from.
* Show the index and what it costs: quartz in P3_221 has one oxygen
  site of multiplicity 6, and descending to P3_2 at index 2 leaves two
  independent oxygens of multiplicity 3.  That split is the reason
  anyone is doing this, so it is the thing to put in the list, and
  `p1.expand` gives it before anything is committed -- the same
  `preview` shape every symmetry command already has.
* Not every descent splits anything, and the list has to say so or
  most of its entries look broken.  Six of rutile's seven index-2
  subgroups leave both sites whole -- the site symmetry drops by the
  same factor as the group order, so what changes is the freedom each
  site has and not how many there are.  The seventh halves both, to one
  titanium and two oxygens.
* That seventh is also the one `gemmi` could not name, which is the
  argument for solving the naming rather than shipping only the
  subgroups that happen to come out in a standard setting.  The
  unnamed ones are not leftovers; here the only descent that does
  anything was hiding among them.
* Going the other way is `FindSymmetry` and exists already.  Say so in
  the dialog: "descend" and "raise the symmetry" look like a matched
  pair, and only one of them is a choice.  The other is a measurement.
* Klassengleiche subgroups split into two halves that are nothing like
  each other in difficulty, and the split is worth knowing before any
  of this is built.  **A lost centring needs no cell transformation
  at all** -- Fm-3m contains Pm-3m as a genuine subset of its
  operations, at index 4, in the same cubic cell -- and those fall out
  of the very same enumeration by simply *not* dividing the centring
  translations out first.  Rock salt descended that way puts its four
  sodiums and four chlorines on eight independent sites, which is the
  cation-ordering model, and it costs no new machinery.
* **A doubled cell is the half that needs the table.**  That is where
  superstructures and antiferromagnetic ordering live, and every
  relation carries its own cell transformation and origin shift --
  Bilbao's MAXSUB, not a computation.  Worth doing third, and worth
  not implying the earlier versions do it.
* One caveat on the enumeration if it is extended past the
  translationengleiche case: "generated by at most three elements" is
  a fact about crystallographic *point* groups, and it stops being
  safe once the centring translations are back in the set.  A run over
  Fm-3m's full 192 operations reports 96 maximal subgroups, and some
  of them are only maximal because the intermediate group needed a
  fourth generator and was never found.  Sound after the reduction,
  a starting point before it.

### Invert the structure

P4_1 and P4_3 are the same crystal in the two hands, and there is no
way to get from one to the other here.  It comes up constantly: a
structure solved in the wrong hand, an absolute configuration to check
against an anomalous-dispersion result, a chiral framework whose
mirror image is the one that was actually made.

* The operation is a change of hand on the coordinates **and** the
  matching change of space group.  Doing only the first is the bug:
  negating the coordinates while leaving P4_1 in place gives a
  structure whose atoms no longer obey their own symmetry, and the
  next P1 expansion is nonsense.
* gemmi already has both halves, which makes this much smaller than it
  looks.  `SpaceGroup.change_of_hand_op()` gives the coordinate
  transformation -- `-x,-y,-z` for most groups, but `-x+1/2,-y,-z` for
  I4_1 and `-x+1/4,-y+1/4,-z+1/4` for F4_132, because those need an
  origin shift to land back in the standard setting.  Using a bare
  `-x,-y,-z` would put 14 groups into a non-standard setting without
  saying so.
* The new group falls out of the operations rather than a table:
  conjugating by the inversion leaves the rotations alone and negates
  the translations, and `gemmi.find_spacegroup_by_ops` on the result
  names the partner correctly for all 11 enantiomorphic pairs
  (P4_1/P4_3, P4_122/P4_322, P4_12_12/P4_32_12, P3_1/P3_2, P3_112/
  P3_212, P3_121/P3_221, P6_1/P6_5, P6_2/P6_4, P6_122/P6_522,
  P6_222/P6_422, P4_132/P4_332) and returns the group unchanged for
  the other 194 that have one.  `SpaceGroup.is_enantiomorphic()` says
  which case this is before anything runs.
* So the action is: transform every site by the change-of-hand
  operation, set the group to the partner when there is one, and leave
  the lattice alone -- the cell parameters are unchanged and a
  right-handed cell stays right-handed.  One
  `StructureSnapshotCommand` in `xtal/commands/symmetry.py`, an entry
  in the Symmetry menu, and no new crystallography.
* **Say what it will do before it does it.**  For a centrosymmetric
  group inversion is already an operation of the group and the
  structure comes back identical; the dialog should say so rather than
  push an undo entry that changed nothing.  For a chiral group that is
  its own enantiomorph -- P2_12_12_1, I4_1, F4_132 -- the symbol does
  not change but the structure does, which is the case most likely to
  be mistaken for a no-op.
* Worth pairing with a read-out of the hand somewhere permanent: the
  Info dock saying "chiral, P4_1 (enantiomorph P4_3)" is the thing
  that makes anyone think to use this at all.

## Force field

### Variable-cell relaxation

The optimiser relaxes the atoms inside a cell it never touches.
Relaxing the cell as well is what turns UFF into something you can
predict a lattice constant with -- and the MOF-5 lattice-constant test
[docs/PLAN.md](PLAN.md) names in its UFF section cannot be written
until it exists.

* `Calculator.numeric_stress` is already there and already tested: six
  symmetric strains by central differences, twelve energy evaluations,
  and every engine gets it without anyone writing an analytic stress.
  It was built in phase 7 and deliberately left unwired.
* `SymmetryDOF` gains six strain variables alongside the site
  coordinates and hands the optimiser one flat vector, as it does now.
  FIRE and L-BFGS then relax the cell with no change to either.
* The strain has to be **symmetry-adapted** or the cell leaves its
  crystal system on the first step -- a cubic cell has one free strain
  and not six, a hexagonal one has two.  `dialogs/cell_edit.py` already
  works out which cell parameters a group leaves free and refuses to
  let you edit the others; the same argument gives the allowed strain
  components, and the same projector that keeps an atom on a special
  position applies to the strain tensor.
* External pressure, as a `P V` term, so that "what does this do at
  5 GPa" is a number in the panel rather than a separate script.  It
  also gives the units somewhere to be checked: energies here are
  kcal/mol and volumes A^3, and the conversion to GPa is the one place
  a factor quietly goes missing.
* Analytic stress afterwards.  Twelve extra energy evaluations per step
  is affordable for a few hundred atoms and is not for a few thousand,
  and every term already computes the pair vectors a virial needs.
* The panel needs one control ("relax the cell as well") and one honest
  warning: a cell relaxed under UFF is a UFF cell, and for a framework
  it is routinely a few percent out.

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

### Atom types nobody can read

The Force Field panel's second column says `Zn3+2`, `O_3_z`, `C_R`,
`Fe6+2`.  Those are UFF's names and they are correct, but nothing on
screen says that the `3` in `Zn3+2` means tetrahedral while the `3` in
`O_3_z` means sp3, or that `Fe6+2` is octahedral iron(II).  The one
column the user is being asked to *check* -- the panel exists so that
typing can be reviewed before an energy is believed -- is written in a
code the panel never explains.

* Everything needed is already parsed.  `params.UFFParams` has
  `.geometry`, `.coordination`, `.oxidation_state` and `.is_resonant`,
  and `GEOMETRY_COORDINATION` already maps the geometry character to a
  coordination number.  What is missing is the word:
  `1` linear, `2` trigonal planar, `3` tetrahedral, `4` square planar,
  `5` trigonal bipyramidal, `6` octahedral, `R` resonant.
* Add a `description` property to `UFFParams` returning "tetrahedral
  Zn(II)", "octahedral Fe(II)", "resonant carbon", "sp3 oxygen,
  zeolitic" -- built from the parts, not a table of 126 strings, so a
  type added to `params.py` still needs no code.
* **Show both, never one.**  The five-character name is what Rappe's
  Table 1 is indexed by, what an override is stored as, and what
  anybody cross-checking against the paper or another program needs.
  The panel gets a column: `Zn3+2` and beside it `tetrahedral Zn(II)`.
  Replacing the name with the description would make the table
  friendlier and the application harder to check, which is the wrong
  trade in the one panel whose job is checking.
* The override dialog wants the same treatment most of all -- offered
  `Fe3+2` and `Fe6+2` for an iron, the user is being asked to choose
  between two strings when the choice is between tetrahedral and
  octahedral, which they would answer instantly.
* The same applies to the type shown in the Inspector for a selected
  atom, and to the tooltip on an atom in the viewport once the context
  menu above exists.

## Files and calculations

### Save As saves a project; Export writes a structure

The File menu offers Save, Save As..., Save Project..., Export as P1
CIF... and Export Image..., and nothing on screen says how the first
three differ.  `Save As` dispatches on the extension the user typed:
`.cif` writes a CIF, `.xtalproj` writes a project, `.xyz` writes an
XYZ.  So the same command either keeps a whole working session or
throws most of it away, and which one happened depends on three
characters after a dot.

The split to settle on:

* **Save and Save As are about the project.**  They write
  `.xtalproj` -- the structure, the bonds drawn by hand, the view, the
  selection, the measurements, the atom-type overrides, and (below) the
  calculations that have been run against it.  The extension is not a
  choice, and `Save Project...` disappears because that is what Save
  now is.
* **Export is about producing a file for something else.**  It never
  becomes the document's path, never clears the modified flag, and
  never pretends to keep what the format cannot hold.  A CIF, an XYZ, a
  POSCAR, an image: all of them one-way.
* `Document.save` and `Document.export` are already two methods that
  already differ in exactly this way -- `save` adopts the path and
  marks the document clean, `export` does neither.  The work is which
  one each menu item calls, not new machinery.
* It is a behaviour change for anyone who has been opening a CIF and
  pressing Ctrl+S, so make it visible rather than silent: opening
  `MFU4l.cif` and saving offers `MFU4l.xtalproj` beside it, and says
  that the CIF has not been touched and `File ▸ Export` is how to write
  one back.
* The one thing lost is the quick round trip "open a CIF, nudge an
  atom, save the CIF".  Export with the last-used settings on a
  shortcut (`Ctrl+Shift+E` is taken by Optimise; `Ctrl+E` is Single
  point -- both are worth revisiting) gives it back without blurring
  what Save means.

### File ▸ Export...

One dialog, replacing `Export as P1 CIF...` and eventually absorbing
`Export Image...`.

* The format list comes from `FORMATS.writable()`, so `xtal/io` stays
  the only place a format is declared and a new writer appears in the
  dialog by being registered.
* Per-format options underneath the picker.  CIF gets the pair that
  prompted this: **with symmetry** (the asymmetric unit plus the
  operations) or **P1** (every atom written out).  Both already work --
  `cif_writer.write_cif` takes `expand_to_p1` -- and only one of them is
  reachable from the menu today.
* **Say what the format drops.**  `Format.keeps` exists for this and
  nothing reads it: a line under the picker, computed from the set,
  reading "XYZ keeps occupancy; symmetry, bonds and charges are not
  written".  Exporting a partially occupied structure to a format with
  nowhere to put the occupancies should not be a silent loss.
* A "selection only" checkbox.  "Export just this molecule" is the
  second thing anybody wants after "export this".
* Designed so that the formats named in [docs/PLAN.md](PLAN.md) -- VASP
  POSCAR, SHELX `.res`, PDB, the `.gen` DFTB+ wants and the `.cssr`
  Zeo++ wants -- are each one module plus one registration line and no
  change here.

### A working folder, and the calculations underneath the structure

Opening `MFU4l.cif` shows one file in a tree rooted at whatever folder
it came from.  Running an optimisation produces a trajectory, a log and
a final structure, and all three exist only inside the panel until the
window closes.  There is nothing that says *this run belongs to that
structure*, and nothing on disk to go back to.

What is wanted: opening a file creates a **workspace** for it, and
every calculation run against it lands underneath it.

```
MFU4l                            the structure, as opened
├── MFU4l.cif                    a copy, so the workspace is whole
├── uff-optimise-001
│   ├── final.cif                the relaxed structure
│   ├── trajectory.extxyz        every step
│   └── run.log                  what happened, in order
└── uff-single-point-002
    └── run.log
```

* The current `FileTreeDock` is a `QFileSystemModel` filtered to
  structure extensions.  It cannot express "this run belongs to that
  structure", so this replaces it with a real model over a `Workspace`
  object rather than over a directory listing.  Keep a "browse the
  filesystem" mode beside it -- opening a file from somewhere else is
  still how everything starts.
* Copy the opened file into the workspace rather than referencing it.
  A workspace that points at a file the user then edits or moves is a
  tree full of broken nodes; the copy costs kilobytes and the original
  path goes in `structure.meta["source"]`.
* **The user picks the workspace, and the application never guesses.**
  A scratch folder cleaned on exit will one day throw away a six-hour
  run; a folder chosen for the user somewhere under
  `~/Library/Application Support` is a folder they cannot find from
  Finder when they want the trajectory.  So: an explicit workspace,
  chosen by the user, the way a project directory is chosen in every
  other piece of scientific software.
  * `File ▸ Open Workspace...` and `File ▸ New Workspace...`, a
    workspace switcher in the tree's header, and a recent-workspaces
    list beside the recent-files one.
  * On first run, ask once and remember -- a default suggestion of
    `~/Crystal Builder` in the dialog, not silently created behind
    their back.
  * Opening a structure with no workspace open offers to make one
    beside the file, which is the answer nine times out of ten.
  * A workspace is a plain directory with a small `workspace.json` at
    its root naming the format version and nothing else.  Nothing
    inside it is hidden, everything in it is a real file with a real
    name, and deleting the folder in Finder is a supported way to
    clean up.
  * `AppSettings` remembers the last workspace and reopens it, exactly
    as it remembers the last directory today.
* Clicking a node opens the right thing: a structure in a viewport tab,
  a trajectory in a viewport with a transport bar, a log in a text
  view.  That dispatch is a small registry keyed on what the artefact
  is, not on its extension, because a `.cif` that is a run's output and
  a `.cif` that is the input want the same viewer but different
  labelling.
* The run folders are written by the module that ran, not by the tree
  -- so the CLI produces the identical layout, and a run started from a
  script is openable in the window.  That means the writing belongs in
  `xtal`, and only the tree belongs in `xtalapp`.

### Play the trajectory back

The optimiser produces a frame per step, the panel draws each one and
throws it away, and when the run ends the only thing left is the final
geometry.  Watching the relaxation again -- which is how anyone works
out *why* it went somewhere odd -- is impossible.

* `OptimizationWorker` already receives every `Step`; it keeps
  `(iteration, energy, max_force)` and drops `step.frac`.  Write the
  frames out as they arrive rather than holding them: 5184 sites is
  124 kB a frame and 200 steps is 25 MB, which is fine on disk and not
  fine in a signal queue.
* Multi-frame extended XYZ, with the cell and the energy on each
  comment line.  `xtal/io/xyz.py` writes single frames already.
  Choosing extxyz rather than an invented format means the trajectory
  opens in OVITO, VMD and ASE without a converter, which is most of
  what a trajectory is for.
* Playback is a transport bar under the viewport -- play, pause, step,
  a frame slider, a speed control -- driving `Document.preview_positions`,
  which exists for exactly this, already avoids the undo stack and
  already avoids marking the document modified.
* Tie it to the energy plot: clicking a point on the trace jumps to
  that frame.  The plot and the trajectory are the same run seen two
  ways and should behave like it.
* **A frame is not an editable structure.**  Scrubbing while an edit is
  half-made loses the edit at the next frame.  Playback should put the
  document into a preview state that refuses edits, with an explicit
  "adopt this frame" command -- the same `ApplyOptimizedGeometry` the
  panel already pushes -- as the way out of it.
* Once a trajectory is a thing the application can open, a trajectory
  from somewhere else opens too: an ASE run, a DFTB+ MD, a LAMMPS dump
  converted to extxyz.  That is worth having for its own sake.

### Show the log

Nothing is written down.  The report `QTextEdit` in the Force Field
panel is cleared on the next run, and the reasons behind every typing
decision -- which the typer computes and the panel shows -- are gone
with it.

* Every module writes `run.log` into its own run folder, as it goes,
  and the tree shows it.  Selecting it opens a read-only monospaced
  viewer that tails the file while the run is live.
* What it has to contain to be worth keeping three months later: the
  version, the engine and every option it was given, the full typing
  table with the confidence and the *reason* for each assignment, the
  topology counts, the per-step line (`Step.line()` already formats
  it), and the per-term energy breakdown at the start and at the end.
* Warnings go in it, in place, rather than only into a status bar
  message that lasted four seconds.
* This is also what makes a result defensible.  "Why is this number
  what it is" is answered by a text file next to the structure, and by
  nothing else.

## Modules

### A Modules menu and a module tree

The menu bar has `Calculate`, holding a single point, an optimisation
and a panel toggle -- three entries that are all UFF, in a menu whose
name suggests it holds everything that computes.  Everything else that
is going to compute (DFTB+, Zeo++, PXRD, whatever comes after) has
nowhere to go that does not make that menu a flat list of unrelated
things.

* Replace `Calculate` with **Modules**, and give it a tree:

  ```
  Modules
  ├── Forcefield
  │   ├── Setup and atom types...
  │   ├── Single point energy
  │   └── Optimise geometry
  ├── DFTB+
  │   └── ...
  └── Zeo++
      └── ...
  ```

  The three entries under Forcefield are exactly what `Calculate` has
  now, moved unchanged.  Nothing about UFF changes in this step.
* The same tree as a dock, beside the file tree -- the module tree the
  user picks *what to run* from, and the file tree showing *what it
  produced*.  Those two panels next to each other are the whole
  workflow.
* **A module is a registry entry, not a menu item.**
  [docs/PLAN.md](PLAN.md) § 14 already names the shape --
  `ANALYSES.register(Analysis)`, `CALCULATORS.register(Calculator)` --
  and this is the thing that finally uses it.  A module declares its
  name, its place in the tree, the parameters it needs (rendered into a
  form rather than a hand-built dialog), whether it wants a worker
  thread, and what it produces: a structure, a trajectory, a log, a
  table, a plot, an overlay.  The menu and the dock are both built from
  the registry, so a plugin appears in both without either file
  changing.
* **Every module writes into the workspace of the structure it ran
  on.**  That is the sentence that ties the module tree to the file
  tree, and it is the one piece of shared machinery all three modules
  need before any of them is written.
* Keep the line clear: a module *runs* something and leaves artefacts
  behind.  Symmetry, Cell, Structure and Select edit the structure in
  place and stay where they are.
* `Ctrl+E` and `Ctrl+Shift+E` follow the UFF entries into the new menu.

### DFTB+

Periodic, DFT-like, and fast enough to relax a framework that UFF can
only approximate -- the natural second engine, and the one that makes
a UFF geometry checkable.

* It is an **external binary**, not a library, so this is a process
  runner: write `dftb_in.hsd`, launch `dftb+` in the run folder, stream
  its stdout into `run.log`, and read `detailed.out` and `geo_end.gen`
  back.  Nothing about it belongs in-process.
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

* Also an external binary (`network`), also a process runner, and it
  shares every piece of that machinery with DFTB+ -- which is an
  argument for writing the runner once, carefully, as part of the
  module registry rather than twice.
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
