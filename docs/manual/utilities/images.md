# Images

*Export Image…* writes the 3D view as a picture, at a size the dialog
states in pixels before it writes.  After this page you can make a
raster figure at the resolution a journal asks for, a transparent one
for a slide, or an SVG an illustrator can recolour atom by atom, and
you know which view settings the picture will carry.

## Exporting a picture of the view

```{index} single: export; image
```
```{index} single: figure; exporting
```

1. Set the view up first: the picture is exactly what the viewport
   shows, camera and all.  The section below says which settings
   matter.
2. Choose {ref}`Export Image… <cmd-export_image>` from the *File*
   menu ({numref}`fig-utilities-image-export-dialog`).
3. Pick a *Format*.  The line under the picker says what each one
   costs, in the application's own words:
   - **PNG image** -- *Lossless, and the only raster format here that
     keeps a transparent background at a sensible size.*
   - **JPEG image** -- *Lossy, and with no alpha channel -- small
     files, and soft edges anywhere the colour changes sharply.*  A
     ball-and-stick picture is almost entirely sharp edges.
   - **TIFF image** -- *Uncompressed and transparency-capable: what a
     journal usually asks for, at roughly ten times a PNG.*
   - **SVG (vector)** -- *One named, separately editable shape per
     atom, bond and cell edge.  Resolution-independent, so there is no
     size to set.*
4. Set the *Resolution*.  The spinner runs from 1x to 8x and starts at
   2x, and the label beside it is the size that will actually be
   written -- *3672 x 2628 pixels* on the machine this manual was made
   on.  For SVG the spinner is disabled and the label reads
   `<W> x <H> canvas, scales to any size`.
5. Tick *Transparent background* to write the background as
   transparent rather than as the view's colour, *so the picture drops
   onto any slide*.  It is greyed for JPEG, which has no alpha channel.
6. *Browse…* or type a path -- the suffix follows the format -- and
   press *Export*.  The status bar says `wrote <name>`.

:::{figure} /figures/utilities/image-export-dialog.png
:name: fig-utilities-image-export-dialog
:width: 75%

*File ▸ Export Image…* with PNG chosen.  The resolution is stated in
pixels, not as a magnification alone; here a 918 × 657 viewport on a
Retina display writes 3672 × 2628 at 2x.
:::

## What "resolution" means, and why it depends on the screen

```{index} single: export; image resolution
```
```{index} single: Retina display; image size
```

The *Resolution* control is a multiplier on the render window, and
the render window is not the size of the widget you see.  On a
high-resolution (Retina) display the render window is already twice
the widget's logical size in each direction, because that is how many
device pixels the widget covers.  The dialog is told the render
window's own size and multiplies it out, so the label is the pixel
count the file will have; a plain "2x" would have meant four times the
pixels somebody thought they asked for.  On this Mac the viewport was
918 × 657 logical pixels at a device pixel ratio of 2, so one
unmagnified grab is 1836 × 1314 and the default 2x is
3672 × 2628.  {doc}`The Essentials chapter </essentials/file>`
quotes *1600 x 1200 pixels* for the same control, which was a
800 × 600 render window on that occasion -- the number is a property
of your window and your screen, not of the application, which is why
the dialog computes it rather than the manual stating it.

For a figure of a given width, then: make the viewport the shape you
want, and choose the smallest multiplier whose label reaches the
pixel count you need.  On a Retina display 1x is already twice the
widget; on a conventional display it is the widget.

SVG has no resolution to set because it is shapes rather than pixels.
The atoms arrive as circles and the bonds as strokes, projected from
the scene itself rather than grabbed from the screen, which is the
whole point: the file is exported so that somebody can recolour one
atom in Illustrator.  Every element carries an `id` and a `class` --
Illustrator shows the id as the object's name in its Layers panel, and
the class is what "select all the bonds" comes down to -- and each
atom is named by the label the crystallographer knows it by, taken
from the {term}`P1` cell.  Depth is a painter's algorithm, every shape
sorted back to front, which for ball-and-stick and polyhedra is the
same picture as the screen.  The {ref}`Cartoon <cmd-style_cartoon>`
style is the one this exporter exists for: a lit atom is a circle
filled with a radial gradient, and a gradient is not a colour, while a
cartoon atom is a solid fill and a stroke -- one selection to
recolour.  The orientation axes, the element legend and the scale bar
are window chrome and stay behind.

## The view settings a figure carries

```{index} single: figure; view settings
```

A raster export is the pixels of the render window, so everything you
see is in the picture: the drawing style, the display range and
boundary, the depth cue, the axes, the labels, the cell, and the
background.  All of them are set from the *View* menu and the *Style*
panel, described in {doc}`/essentials/view`; the ones that most often
decide whether a figure is usable are these.

- **Style.**  *View ▸ Style* holds eleven ways to draw the same atoms.
  {ref}`Cartoon <cmd-style_cartoon>` -- flat colour inside a dark
  outline -- is the one meant for a figure an illustrator will
  recolour; {ref}`Space filling <cmd-style_spacefill>` for pores;
  {ref}`Thermal ellipsoids (ORTEP) <cmd-style_ortep>` for a refinement.
- **Background.**  *View ▸ Background* offers *Follow the system*,
  then *White*, *Black*, *Slate* and *Paper*, then *Custom…*.  A
  structure with no view of its own starts on *Follow the system*,
  which is white under a light theme and slate under a dark one.  For
  print, choose *White* or *Paper*, or tick *Transparent background*
  in the dialog and let the page supply it.
- **Depth cue.**  {ref}`Depth cue <cmd-depth_cue>` fades distant atoms
  towards the background, so a thick slab reads as having depth
  rather than as a flat mat of spheres; it fades towards whatever the
  background *is*, so set the background first.

:::{note}
**A colour you chose is never overwritten.**  Pick *White*, *Paper* or
a custom colour and the viewport keeps it through a theme change and
anything else; only *Follow the system* follows the theme.  The same
rule holds for every colour set by hand in the *Style* panel, so a
figure made today on a white background will still be white when the
project is opened on a dark desktop.
:::

Choosing a style or a background here changes this tab and no other;
what a *newly opened* structure is drawn as is *Preferences ▸ View
defaults* ({ref}`Preferences… <cmd-preferences>`).

## A figure for print

```{index} single: figure; light background
```

{numref}`fig-utilities-hkust1-white` is HKUST-1 as it opens from
*Open Sample*, on a white background, written through the same call
*Export Image…* makes.  It was produced by
`docs/manual/shots/utilities.py`, which does in code what you would
do by hand: open the sample, choose *View ▸ Background ▸ White* and
{ref}`Reset view <cmd-reset_view>` ({kbd}`Ctrl+0`), and export at 1x -- 1836 × 1314 pixels from the
918 × 657 viewport on this Retina display.  Nothing else about the
view was changed, so the style, the boundary and the axes are the
defaults a first-run window has.

:::{figure} /figures/utilities/hkust1-white.png
:name: fig-utilities-hkust1-white
:width: 90%

HKUST-1 (the shipped sample) down *c*, ball and stick on *White*,
exported at 1x.  A white or *Paper* background prints; the slate a
dark desktop gives *Follow the system* does not.
:::

## Limitations

- The picture is the render window: a viewport hidden behind another
  tab, or a window smaller than the figure you want, gives a smaller
  picture.  Resize the window before exporting rather than after.
- JPEG cannot carry transparency and softens edges; use it only when
  file size is the constraint.
- SVG is written from the scene model, not from the pixels: the
  orientation axes, the element legend and the scale bar are not in
  it, and a lit style's atoms are gradient-filled circles that are
  harder to recolour than the cartoon's flat ones.
