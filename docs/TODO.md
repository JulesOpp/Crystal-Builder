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
