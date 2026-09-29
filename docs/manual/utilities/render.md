# Rendering in Blender

*Render in Blender…* renders one unit cell with its bonds with
Blender's Cycles, in a lit scene the application builds, and keeps
that scene beside the picture so you can open it in Blender and take
it further.  After this page you know what the scene is, where the
camera goes, and what the run leaves behind.

## What the run does

```{index} single: Blender; rendering
```
```{index} single: render
```

It is the same kind of run as {doc}`stl` and shares its first half:
the cell is cut out -- faces and corners included, with the bonds the
document has -- and written as a PDB with a `CONECT` record for every
bond.  Blender is found the same way, in the same *Preferences ▸
Engines* row, and needs the same *Atomic Blender* add-on.  Then
Blender runs headless on `render_scene.py`, which:

1. removes every object from Blender's starting scene;
2. imports the PDB through Atomic Blender, at the importer's own
   defaults -- the balls and sticks you would get from *File ▸ Import*
   in Blender;
3. adds an area light, scaled up 100 times, 25 m above the origin, at
   100 000 W;
4. sets the engine to Cycles, with 10 samples in Blender's viewport
   and 50 for the picture, and turns *Simplify* and *Render Region*
   on;
5. adds a 40 mm camera turned to (70.7437°, 0.000522°, 146.958°);
6. saves `scene.blend`, then renders `render.png`.

The scene's values are constants at the top of the script.

## Where the camera goes

```{index} single: Blender; camera framing
```

The camera keeps its direction whatever the structure, and with
*Frame the whole structure* on (the default) it is moved along that
direction until everything drawn is in the picture, with a 5 % margin.
The render region is then set around where the atoms land, so Cycles
spends no samples on the empty corners of the frame.  The framing is
worked out from the corners of every ball and stick Blender drew, not
from one box around the whole cell: seen at an angle, a box's corners
are mostly empty space, and framing them leaves the structure small
and to one side.

With it off, the camera stands at the scene's fixed place,
(42.0251, 64.6089, 26.9517) m, which suits a cell about the size of
MOF-5's and no other.

## Rendering a cell

1. Open the structure and settle its bonds: the picture carries the
   bonds the document has.
2. Choose {ref}`Render in Blender… <cmd-render_blender>` from the
   *File* menu, or *Modules ▸ Blender ▸ Render in Blender…*.  The
   dialog suggests `<structure>.png` in the directory you last used.
3. Set the picture's size and samples.  Every setting, its range and
   its default is in the {ref}`reference <mod-blender-render>`.
4. Press *Run*.  On MOF-5 at 1920 × 1080 and 50 samples it takes a
   few seconds.  The status bar ends with `rendered <name>.png: <n>
   atoms, <m> bonds`.

The PNG is copied to where you asked.  The run folder keeps the PDB,
`scene.blend`, `render.png` and the log.

## Limitations

- The light stays 25 m above the origin whatever the cell's size; a
  cell taller than about 50 Å has its top above the light.
- The PDB is written centred on a point a few hundredths of an
  ångström off the origin, rather than exactly on it.  Atomic Blender
  3.4 divides by a stick's distance from the origin, so a symmetric
  cell centred exactly there fails inside Blender.
