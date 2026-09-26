# Mouse modes

A mouse mode decides what a click in the 3D view does.  After this
page you can pick, box, place atoms, draw bonds and net edges, move
and turn a fragment with the mouse, and measure by clicking, and you
know what {kbd}`Esc` backs out of at each press.

## Choosing a mode

```{index} single: mouse modes
```

The seven modes are the middle group of the toolbar and the
*Structure ▸ Mouse mode* submenu; one is pressed at a time, and the
status bar shows the pressed mode's own hint -- what to click next.
The camera is never a mode: in every mode but *Box select* the left
button on empty space turns the crystal, the wheel zooms and the
middle button pans, so you can always turn the structure to see what
you are doing.

What a click hits is worked out exactly, against the drawn atoms and
bonds, in perspective and orthographic projection alike.  A drawn
atom knows which site of the cell it is and which lattice translation
put it there, so a click on a copy in the second cell acts on that
copy -- and in a structure with symmetry, on the site behind it.

## The modes

```{index} single: Select mode
```

**{ref}`Select <cmd-mode_select>`** -- *click an atom or bond ·
shift-click to add · double-click for the whole fragment*.  A click on
nothing clears the selection.  {kbd}`Shift` (or {kbd}`⌘` on macOS)
toggles the atom in and out of the selection instead of replacing it,
and a double-click grows to the connected fragment, which is the
fastest way to grab one molecule out of a cell.  A click on the span
of a net edge, where nothing else is under it, selects the edge, and
the status bar says *net edge selected -- Del removes it*.

```{index} single: Box select mode
```

**{ref}`Box select <cmd-mode_box_select>`** -- *drag a box over the
atoms - shift to add - everything inside is taken, bonds included,
front to back*.  The atoms hidden behind the ones you can see are
taken too, which is what makes a box useful for a slab, and the bonds
with both ends inside come with the atoms, so *Set Bond Type* after a
box acts on the linker that was boxed.  Rotating is not available
while this mode is active -- the left button cannot both draw a box
and turn the crystal -- but panning and zooming are.

```{index} single: Add atom mode
```

**{ref}`Add atom <cmd-mode_add_atom>`** -- *click to place an atom ·
click an atom to build from it, then keep clicking to chain · Escape
stops*.  The element is the box beside the button on the toolbar.  A
click on empty space places the atom on the plane the camera is
focused on, the only depth a single click can mean.  A click on an
atom *anchors* instead: the next click gives only a direction, the
new atom goes at the bond distance for the pair, and the bond goes
with it.  With exactly one atom selected, entering the mode starts
already anchored -- pick the carbon, press the button, point.  The
anchor then moves to the atom just placed, so a chain is click, point,
point, point; hovering an existing atom snaps to it, and the click
then bonds to that atom instead of placing a new one, which is how a
ring closes.  A ghost atom with its bond follows the cursor between
clicks.  {kbd}`Esc` ends the chain; a second {kbd}`Esc` leaves the
mode.

```{index} single: Add bond mode
```

**{ref}`Add bond <cmd-mode_add_bond>`** -- *click two atoms to bond
them · click a bond to remove it*.  The first atom stays selected
while it waits for the second.  The copy you clicked is the copy that
gets the bond, so in a view of several cells a bond to a neighbouring
image is drawn to that image.  A bond removed here is suppressed, like
*Delete bond*.

```{index} single: Draw net mode
```

**{ref}`Draw net <cmd-mode_topology>`** -- *click two atoms to draw a
net edge - click an edge to select it, Del removes it*.  A
{term}`net` is not a bond graph: it is what is left after deciding
which parts of a framework are nodes and which are linkers, and that
decision is a chemist's, not a distance criterion's.  This is where it
is made.  The edge expands over the symmetry orbit like every other
bond, so drawing one edge of a **pcu** net draws all six, and the
*Net* panel names what has been drawn against the RCSR
{cite}`okeeffe2008rcsr`.  A {term}`dummy atom` from *Add centroid…*
is a vertex like any other.

```{index} single: Move mode
```

**{ref}`Move <cmd-mode_move>`** -- *drag an atom to move it, or any
atom of the selection to move all of it - alt-drag turns the
selection - shift-alt-drag moves it in depth - the background still
turns the crystal*.  The three gestures are below.

```{index} single: Measure mode
```

**{ref}`Measure <cmd-mode_measure>`** -- *click a bond for its length,
or 2 atoms for a distance, 3 for an angle, 4 for a torsion*.  How many
atoms you pick is the whole of the choice; the chooser at the top of
the *Measure* panel sets how many clicks a run takes, and the status
bar counts down.  Clicking the bond itself is one click whatever the
target, because a bond already names its two atoms.  The picks stay
selected while they accumulate.

## The Move gestures

```{index} single: Move mode; drag, Alt-drag, Shift-Alt-drag
```

A press on an atom takes the drag; a press on the background is left
to the camera, so the view is never stuck.  What is dragged is the
selection when the atom is in it -- pick a fragment, then drag any
atom of it and the whole fragment goes -- and the atom alone, which
becomes the selection, when it is not.  {kbd}`Shift` adds the atom to
the selection and drags them together.  The whole gesture is one undo
step.

1. **A plain drag translates** in the plane through the point you
   picked up, facing the camera.  A drag has no depth of its own --
   the cursor is a ray, not a point -- so this is the only plane a
   screen movement means without being asked twice.
2. **An Alt-drag turns the selection about its own middle**: a
   trackball over the selection, across the picture about the
   camera's up axis and up-and-down about its right, one radius of the
   selection's travel to the radian, so it feels the same on a linker
   and on a framework.  The pivot is the middle of the selection as it
   is drawn, taken when the button goes down and held for the
   gesture.  A single atom has no orientation, and an Alt-drag on one
   says so.
3. **A Shift-Alt-drag moves along the view axis**, towards and away
   from you -- the half of a placement a plane cannot reach.  Turning
   the crystal first and dragging in the new plane is the other way to
   get there.

:::{note}
**Alt claims a Move drag, and Shift is then read inside it.**  Shift
means *extend the selection* only when Alt is not held: a gesture that
turns a fragment is not one in which adding an atom to it means
anything.
:::

:::{note}
**A drag moves the copy the cursor has hold of.**  Move mode
displaces *sites*, so in a structure with symmetry the whole orbit
moves, but the displacement is worked out for the drawn atom under
the cursor -- the site moves by the inverse of the operation that
generated that copy -- so the atom you are holding follows the cursor
in every space group.  A number typed into the *Move* panel is a
displacement of the site itself.  Where two images of one site are
selected, the first wins.  The bonding does not change: two atoms
dragged onto each other are not bonded, and a bond stretched to 4 Å
is still a bond, until *Recalculate bonds*.
:::

## What a click on a net edge selects

```{index} single: net edge; picking
```

A net edge is drawn over the bonds and is thicker than they are, so on
depth alone it would win every click near a framework edge and the
bond underneath could never be selected.  So it never competes on
depth.

:::{note}
**A click inside a net edge is the net edge**, whatever chemistry
crosses under it.  Within the inner half of the tube's radius the
edge wins even when a bond is nearer the camera; out towards the rim,
whatever is behind it wins; and an atom always wins, because an
edge runs centre to centre and its own ends are inside the core.  In
*Draw net* the edge is preferred outright, except that an endpoint in
front of its own edge is still the atom, so the second edge of a net
can start where the first one ended.
:::

## Escape

```{index} single: Escape key
```

{kbd}`Esc` ({ref}`Cancel the current gesture <cmd-cancel_gesture>`)
backs out one rung at a time: first a half-finished gesture -- an
add-atom chain, the first end of a bond, the first vertex of a net
edge, the atoms of a measurement -- then a mode that is not *Select*,
then the selection itself.  The key never does nothing while there is
still something to back out of.  A gesture is also put down by itself
when an edit adds or removes atoms between two of its clicks, because
the atoms it was holding may have been renumbered; a move keeps the
numbering and keeps the gesture.
