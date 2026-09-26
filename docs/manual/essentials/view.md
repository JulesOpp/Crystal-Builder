# View

The *View* menu decides how the structure in front is drawn: its
style, what is shown over it, the background, how many cells, and
where the camera is.  After this page you can choose a drawing style
for the question you are asking, draw a slab or a half cell, decide
what happens to bonds at the edge of the picture, and look down an
axis with one key.

Everything on this menu is view state.  It belongs to the document --
choosing a style here changes this tab and no other -- it is saved
with the project, and it is never an undo step.  What a *newly
opened* structure starts as is *Preferences ▸ View defaults*, not
this menu.

## Style

```{index} single: drawing style
```

*Style* holds eleven ways to draw the same atoms, one ticked at a
time; the same submenu is in the context menu of the background, and
the *Style* panel holds the sizes, colours and labels that go with
them.  Which to choose:

- {ref}`Ball and stick <cmd-style_ball_stick>` for editing, and
  {ref}`Ball and stick (occupancy) <cmd-style_ball_stick_occupancy>`
  when a site is shared or partly empty -- each such site is cut into
  wedges, one per occupant and a grey one for the vacancy.
- {ref}`Stick <cmd-style_stick>` and {ref}`Wireframe
  <cmd-style_wireframe>` for a framework too dense to read as balls.
- {ref}`Net only <cmd-style_net>` for the {term}`net` a framework
  reduces to: the topology and nothing else.
- {ref}`Space filling <cmd-style_spacefill>` for pores and contacts,
  atoms at their van der Waals radius.
- {ref}`Thermal ellipsoids (ORTEP) <cmd-style_ortep>` and
  {ref}`Ellipsoid plot (PLATON) <cmd-style_platon>` for a refinement:
  displacement ellipsoids at the probability level set in the *Style*
  panel, in the two conventions structure reports use.
- {ref}`Polyhedra and sticks <cmd-style_polyhedra_stick>` and
  {ref}`Polyhedra <cmd-style_polyhedra>` for coordination: the metals'
  polyhedra with the linkers as tubes, or the polyhedra alone as
  translucent hulls.
- {ref}`Cartoon <cmd-style_cartoon>` for a figure an illustrator will
  recolour: flat colour inside a dark outline, and the one style that
  exports to SVG as plain circles and strokes.

## Show

```{index} single: overlays; showing and hiding
```

*Show* is a list of toggles over the picture: {ref}`Atoms
<cmd-show_atoms>`, {ref}`Bonds <cmd-show_bonds>`, {ref}`Bond orders
<cmd-show_bond_orders>` (a double bond as two tubes, a triple as
three, an inner dashed line for an aromatic one), {ref}`Net (topology
bonds) <cmd-show_topology>` (the {term}`topology bonds <topology
bond>` drawn thicker and translucent over the real ones), {ref}`Unit
cell <cmd-show_cell>`, {ref}`Cell axes (a, b, c) <cmd-show_axes>` (the
triad in the corner), {ref}`Planes <cmd-show_planes>`, {ref}`Pore
network <cmd-show_pores>` (nothing until a porosity run has answered),
{ref}`Labels <cmd-labels>`, {ref}`Element legend <cmd-show_legend>`
and {ref}`Scale bar <cmd-show_scale_bar>`, a ruler in Ångström that
measures the camera and not the crystal, so a cell that contracts
during a relaxation is seen to contract against it.

{ref}`Clear charges and orbital <cmd-clear_overlays>` takes a DFTB+
run's atom colouring and orbital lobes off the picture; they go by
themselves when the atoms move, as does a pore network, because
neither can be refitted to a crystal that has changed.

## Background

```{index} single: background colour
```

*Background* offers *Follow the system*, then *White*, *Black*,
*Slate* and *Paper*, then *Custom…* for any colour.  A structure with
no view of its own starts on *Follow the system*, which is white
under a light theme and slate under a dark one and changes with the
theme from then on.

:::{note}
**A colour you chose is never overwritten.**  Pick *White* or a custom
colour and the viewport keeps it through a theme change and anything
else; only *Follow the system* follows.  The same rule holds for
every colour a person sets in the *Style* panel.
:::

## Display range and the boundary

```{index} single: display range
```
```{index} single: bonds; at the boundary
```

The toolbar's three *cells* boxes draw whole cells from the origin
along *a*, *b* and *c*; fractions can be typed (`1.5` is half a cell
more of a framework) and the arrows step whole cells.
{ref}`Display range… <cmd-display_range>` ({kbd}`Ctrl+R`) covers the
rest:

1. Type a *from* and *to* along each axis, in fractional coordinates.
   A range that starts below zero completes the origin corner; a slab
   is one cell thick in *c* and three wide in *a*; a half cell looks
   inside a framework.  Ranges are inclusive at both ends, so with a
   range of 0 to 1 the atom at *x* = 0 is drawn again at *x* = 1 and
   the cell closes.  The line underneath counts what will be drawn --
   *1 x 1 x 1 cells -- roughly 624 atoms of the 624 in one cell, plus
   the closing faces* -- and *One whole cell* puts the range back.
2. Choose what happens to a bond whose far atom is outside the range.
   The three answers are the *Bonds at the boundary* submenu of the
   *View* menu and of the background's context menu as well:
   {ref}`Drop bonds at the boundary <cmd-boundary_in_range>` draws
   only atoms inside the range, so every atom on the surface of the
   picture is under-coordinated; {ref}`Complete bonds at the boundary
   <cmd-boundary_bonded>` draws the far atom as well, the only way a
   coordination polyhedron at the cell edge stays whole, at the cost
   of a halo of atoms around the box; {ref}`Draw half bonds at the
   boundary <cmd-boundary_half>` draws the near half and nothing on
   the end of it -- the usual notation for a bond that leaves the
   picture, and the only one that draws a six-coordinate net vertex
   with six edges.

Nothing here touches the structure.  A drawn atom outside the first
cell is an image of a site, and selecting or dragging it acts on the
site like any other copy.

## Projection, depth and the camera

```{index} single: camera; axis views
```

1. {ref}`Orthographic projection <cmd-orthographic>` removes
   perspective, which is what a view down an axis needs to show the
   channels of a framework as the straight tubes they are.
2. {ref}`Depth cueing <cmd-depth_cue>` fades distant atoms towards
   the background, so a thick slab reads as having depth instead of
   as a flat mat of spheres.
3. {ref}`Along a <cmd-view_a>`, {ref}`Along b <cmd-view_b>` and
   {ref}`Along c <cmd-view_c>` ({kbd}`1`, {kbd}`2`, {kbd}`3`) look
   down each axis, and {ref}`Reset view <cmd-reset_view>`
   ({kbd}`Ctrl+0`) frames the whole of what is drawn again.  All four
   are on the right of the toolbar, the axis views labelled by their
   letter after the word *along*.

In every mouse mode the left button on the background turns the
crystal, the wheel zooms and the middle button pans; *Box select* is
the one mode that takes the left button for itself.
