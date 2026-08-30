# TODO

Work that is wanted but not yet scheduled into a phase.
[docs/PLAN.md](PLAN.md) holds the roadmap; this file holds everything
that came up while using the application and does not belong to a phase
yet.  An entry gets deleted when it ships, not ticked.

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

### Delete bond as its own action

Deleting a bond means switching to the Add Bond tool and clicking the
bond, which is not discoverable and is a strange place for it: a tool
called *Add* is where deleting lives.

* A `Delete bond` entry in the Edit menu, enabled when the selection
  holds bonds, running the `SuppressBond` command that already exists.
  `Selection.bonds` is already populated by clicking a bond in Select
  mode, so the wiring is short.
* `Del` should delete the selected bonds when bonds are what is
  selected, and the selected sites otherwise -- one key, whichever
  thing is in hand, which is what the Inspector's Delete button should
  do too.
* Say what happened, and say it in orbit terms: suppressing one bond
  suppresses its whole symmetry orbit, so "removed 4 Ti-O bonds" is the
  honest message and "bond removed" is not.
* The Inspector already describes a selected bond; it should grow the
  button next to that description.

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

### Bond rules dialog

Bond perception has settings and no way to reach them.  `BondRules`
already carries all of it -- `scale`, `delta`, `min_distance`,
`pair_ranges`, `forbidden`, `allow_metal_metal`; `Structure.bond_rules`
stores it, `SetBondRules` makes a change undoable, and `bonds.json`
saves it.  The only missing piece is the dialog, which
[docs/PLAN.md](PLAN.md) has been listing as `dialogs/bond_rules.py`
since before phase 1.

* A tolerance control on `scale`, with the bond count updating as it
  moves.  The count is the whole feedback loop, and it is not linear in
  the way people expect: rutile keeps exactly its 12 Ti-O bonds
  anywhere from 1.05 to 1.45 and then jumps to 28 at 1.6 when the
  second coordination shell arrives.  A slider with no number beside it
  would make that plateau invisible and the cliff a surprise.
* `allow_metal_metal` as its own checkbox, and it deserves to be
  prominent rather than tucked away, because it is a different control
  from the tolerance and not a finer version of one.  No amount of
  loosening `scale` gives rutile a Ti-Ti bond while the flag is off;
  turning it on at the default 1.15 takes the cell from 12 bonds to 22.
  An alloy or an intermetallic needs it first and needs it findable.
* A per-pair table built from the elements actually present -- one row
  per unordered pair, a checkbox that writes `forbidden`, and an
  optional explicit min/max that writes `pair_ranges`.  That is the
  "which atoms are included" control, and keying it on the pairs in the
  structure rather than on the periodic table keeps it to a handful of
  rows for anything real.
* The preview has to show what *changes*, not the total.  "6 bonds
  added, 2 removed" against the current rules; a count alone hides a
  setting that swaps one bond for another and looks like it did
  nothing.
* Per structure, not global.  The rules are a field on `Structure` and
  travel with the project.  A default for new documents belongs in
  `AppSettings`, and the dialog should offer "use these from now on"
  rather than quietly making it so.

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
