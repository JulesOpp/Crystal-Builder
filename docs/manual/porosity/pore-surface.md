# The Pore Surface

The pore surface is the boundary of everywhere a probe of the chosen
radius can put its centre, drawn over the crystal by the two
*Accessible volume* entries.  After this section you know what
surface it is and why it is one measurement with the volume beside
it, how it is marched and why over tetrahedra, why it covers channels
and not pockets, why it is never written into the project, and what
it costs.

```{index} single: pore surface
```
```{index} single: marching tetrahedra
```
```{index} single: isosurface; pore surface
```

## What it is

The surface is the $r$ level set of the distance grid of
{doc}`grid` -- the field of {eq}`grid-field` at the probe radius --
which is exactly the boundary of the accessible volume Zeo++'s `-vol`
measures.  It is built with the same radii table the run was given,
so the drawn surface and the quoted volume are one measurement.  A
run given a **Radii file** of its own is the one case the picture
cannot be matched to the number, and it says so in the log rather
than drawing a surface off somebody else's table.

Zeo++ does not supply it: its `-gridGAI` aborts on MFU-4l and its
`-gridG` runs for minutes writing nothing, which is why the grid is
the application's.  The surface appears when **Draw the accessible
surface** is on, which is the default on both {ref}`Accessible
volume… <mod-zeopp-volume>` (where the numbers are Zeo++'s and the
surface is computed here at the same probe and the same radii) and
{ref}`Accessible volume (faster)… <mod-zeopp-volume-grid>` (where
the numbers and the surface come off one grid).  *View ▸ Show ▸*
{ref}`Pore network <cmd-show_pores>` hides and shows it, and it lives
on the document under the same rules as the pore network: put there
by the run, saved in the {term}`session`, dropped when the atoms it
was measured on change, drawn on the document the run was started
from ({doc}`zeopp`).

## Marching tetrahedra, not cubes

The grid is turned into triangles by marching it.  Marching cubes
{cite}`lorensen1987marchingcubes` looks at the eight corners of each
grid cell and has 256 sign patterns, fourteen of which are
*ambiguous*: the same eight signs describe two different surfaces,
and choosing wrong leaves a hole.  Every published fix is a second
table.  A tetrahedron has sixteen patterns, three of them up to
symmetry, and none is ambiguous -- so each cube is split into six
tetrahedra about its main diagonal (the Kuhn decomposition, which
tiles the cube exactly and makes neighbouring cubes agree on the
faces they share) and the surface comes out watertight from a table
nobody has to trust.  It costs about twice the triangles, which for a
surface nobody is going to print is not a cost.

The march is periodic, which is most of the work: a surface marched
over the interior alone would be a box with six open faces, and one
closed by padding would be a box with six *flat* faces -- a cavity
sliced off square at the cell wall instead of continuing into the
next cell.  So the corner lookup wraps, and a triangle that crosses a
face comes out sticking a little way outside the cell, which is where
it belongs.

## Channels only

The number beside the surface is the accessible volume, and a sealed
pocket is not part of it, so a pocket drawn with the channels would
be a picture of a different quantity.  The grid is split into
channels and pockets as {doc}`grid` describes, and a pocket is pushed
just under the level so that the march closes it off.  A run in
which every void is a pocket draws nothing, and the log says so:
*nothing to draw: every void is a pocket the probe cannot reach*.  A
borderline window is noted in the same place -- *whether the drawn
surface passes through it is a matter of resolution*.

## Not written into the project

:::{note}
**The surface is not saved.**  MFU-4l's is 307 680 triangles and
96 MB of JSON, against 1.1 s to compute it again; the pore network's
nodes and edges are small enough for the session file, the surface
is not.  Open the project and the network comes back; run the entry
again for the surface.
:::

## Memory and time

The grid is single precision and the march goes a slab of cells at a
time, so MFU-4l's second peaks at about 90 MB rather than 400.  On
the Zeo++ entry the **Surface detail** setting is the grid spacing
the surface is marched at: 0.5 Å is a second and about 190 000
triangles on MFU-4l, and 0.3 Å is eight times that.  On the *(faster)*
entry the surface shares the numbers' **Grid spacing** (0.4 Å by
default: HKUST-1's surface at that spacing is 189 312 triangles on a
66×66×66 grid, from the run in {doc}`grid`).

## Worked example: ZIF-8 to hydrogen

{numref}`fig-pore-surface-zif8` is the shipped ZIF-8 (*File ▸ Open
Sample ▸* {ref}`ZIF-8 <cmd-sample_zif8>`) with the channel surface to
a hydrogen probe (1.48 Å) over it, at the default 0.4 Å spacing and
Zeo++'s radii: *an accessible surface of 26800 triangles at a 1.48 A
probe around 1 channel, 0 pockets, on a 37x37x37 grid*.  To nitrogen
the same cell is one pocket and nothing is drawn ({doc}`grid`).

:::{figure} /figures/porosity/pore-surface-zif8.png
:name: fig-pore-surface-zif8
:width: 80%

ZIF-8's sodalite cage with the pore surface to a hydrogen probe: the
boundary of where the probe's centre can sit, over the one channel
the probe can reach.
:::

## Settings

**Draw the accessible surface** and **Surface detail** under
{ref}`Accessible volume… <mod-zeopp-volume>`; **Draw the accessible
surface** and **Grid spacing** under {ref}`Accessible volume (faster)…
<mod-zeopp-volume-grid>`; the radii settings of either.

## Limitations

- It is the boundary of the *accessible* volume at the probe's
  radius over channels.  Pockets are not drawn; the pore network's
  sphere and skeleton are a different drawing, from Zeo++'s Voronoi
  nodes.
- It is not saved, and is recomputed by running the entry again.
- A run given a radii file draws no surface.
- Its resolution is the grid's: a window within half a grid step of
  the probe is flagged in the log, and whether the surface passes
  through it depends on the spacing.
