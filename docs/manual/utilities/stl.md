# STL through Blender

*Export as STL…* turns one unit cell with its bonds into a mesh a 3D
printer can take, and Blender does the meshing.  After this page you
know what Blender is needed for and how the application finds it,
what each setting of the export changes, and exactly what the printed
cell will contain.

## What Blender is for

```{index} single: STL export
```
```{index} single: Blender
```
```{index} single: 3D printing
```

A crystal has no edges, and everything that makes a *thing* out of
one has to decide where the edges go.  The application's part of the
job is to cut one cell out of the crystal and hand it over; Blender's
is to make a solid of it.  The run is a module run like any other
({ref}`Blender ▸ Export as STL… <mod-blender-export-stl>` in the
reference), which is what gives it a run folder, a *Stop* that
reaches Blender, and a greyed entry that says when Blender was not
found.  In order:

1. The cell is cut out -- faces and corners included, with the bonds
   the document has -- and written as a PDB with a `CONECT` record
   for every bond.  The PDB is written for one reader above all,
   Blender's *Atomic Blender* importer, which draws sticks only from
   `CONECT` and never works a bond out for itself.
2. Blender runs headless (`--background --factory-startup`) on
   `pdb_to_printable_stl.py`, a script that ships unchanged with the
   application.  Atomic Blender imports balls and sticks; the
   instances are baked into one mesh; a voxel remesh welds it into a
   single watertight solid; the STL is written.
3. The STL is copied to where you asked for it.  A copy stays in the
   run folder beside the PDB it was made from and the log.

Blender itself is not part of the application.  It is a separate
install from [blender.org](https://www.blender.org/); the script's own
header asks for Blender 2.83 or later and the *Atomic Blender PDB/XYZ*
add-on, which Blender 3.x ships and 4.2 and later offer under *Get
Extensions*.  The script tries to enable the add-on itself; if that
fails, the run stops with *Blender could not enable the Atomic Blender
add-on, which reads the PDB* and the script's own sentence naming
where the add-on lives in your Blender version.

## Where Preferences points at it

```{index} single: Preferences; Blender
```

*Preferences ▸ Engines* ({ref}`Preferences… <cmd-preferences>`,
{kbd}`Ctrl+,`) has a row for Blender among the programs the
application shells out to, described there as *File > Export as STL,
which turns one cell into a printable mesh.  It needs the Atomic
Blender add-on: Blender 3.x ships it, 4.2 and later offer it under
Get Extensions.*  Under the field a status line says whether Blender
was found and, if not, where it looked.  Three places are tried: the
path set in this row, the environment variable `XTAL_BLENDER`, and
the `PATH`; on macOS the standard location
`/Applications/Blender.app/Contents/MacOS/Blender` is looked in on
its own, so a Blender installed from the disk image is found without
being named.  A preference beats the environment variable, because a
variable is what a shell set and a preference is what a person set
on purpose.  **Test** starts Blender for a moment and shows what it
printed, since a binary can be found and still not run.  Installation
in general is {doc}`/quickstart/installation`.

## Exporting a cell

```{index} single: export; STL
```

1. Open the structure and settle its bonds first: the mesh carries
   the bonds the document has, so a bond you have suppressed prints
   as no stick, and one you drew prints as one.  {ref}`Recalculate
   bonds <cmd-recompute_bonds>` if the structure has none.
2. Choose {ref}`Export as STL… <cmd-export_stl>` from the *File*
   menu, or *Modules ▸ Blender ▸ Export as STL…*; they are the same
   run, reached from *File* because that is where an export is looked
   for.  The dialog ({numref}`fig-utilities-stl-export-dialog`)
   suggests `<structure>.stl` in the directory you last used.
3. Set the mesh up.  Every setting, its range and its default is in
   the {ref}`reference <mod-blender-export-stl>`; what each is for:
   - *Complete bonds across the cell faces* brings in the atom at the
     far end of every bond that leaves the cell, so a linker cut by a
     face prints with both its ends rather than as a row of loose
     carbons along the face.  Only one layer is brought in; a
     partner's own partners would be the next cell.
   - *Ball scale* and *Hydrogen scale* multiply the atomic radii; the
     hydrogens are scaled again because at atomic radii they are too
     small to print.  *Stick radius* is the bond cylinder, in Å.
   - *Remesh into one solid* welds the balls and sticks into one
     watertight mesh.  Off leaves overlapping pieces, which most
     slicers refuse.  *Voxel size* is the remesh grid -- smaller keeps
     more detail and costs memory as the cube of it -- and *Triangle
     budget* coarsens the remesh until the mesh fits; a binary STL is
     about 50 bytes a triangle.
   - *Longest side* scales the model so its longest side is that many
     millimetres.  Left at 0, one ångström is one millimetre.
4. Press *Run*.  The status bar follows the script's own progress
   lines; when it finishes it says `wrote <name>.stl (<size> MB):
   <n> atoms, <m> bonds`.  *Stop* stops Blender.

:::{figure} /figures/utilities/stl-export-dialog.png
:name: fig-utilities-stl-export-dialog
:width: 70%

*File ▸ Export as STL…* on HKUST-1, at the defaults.  The form is the
module's parameters, so the same settings are available to `xtal run
blender.export-stl` on the command line.
:::

## What the STL contains

```{index} single: STL export; contents
```

- **One unit cell, faces and corners included** -- the same rule the
  viewport draws by default, so a cubic cell with an atom at the
  origin has eight of it.  That is what a person holding the model
  expects to see, and it is what makes the printed cell look like the
  picture.  A supercell is made first ({doc}`/essentials/cell`) if
  you want more than one.
- **The document's bonds, not a second opinion.**  They come from the
  structure as it is: a bond you suppressed stays gone, one you drew
  is there.  A bond is kept between two atoms that are both in the
  cut; one that leaves the cell is dropped unless *Complete bonds
  across the cell faces* brings its partner in.
- **No net edges and no markers.**  A {term}`topology bond` is not a
  bond and a {term}`dummy atom` is not an atom, and neither is cut.
- **No cell.**  The PDB carries no `CRYST1` record, because the cell
  has been cut out of the crystal and a reader that saw one would put
  the periodicity back.  The STL is a solid at 1 Å = 1 mm unless
  *Longest side* rescales it.

## On a machine without Blender

```{index} single: Blender; not installed
```

Blender is not installed on the machine this manual was written on.
The menu entry is still there -- it is enabled whenever a structure is
open and idle -- and choosing it does not open the dialog; the status
bar says instead:

```text
Blender is not installed, or not on PATH (XTAL_BLENDER is not set).  It is at https://www.blender.org/
```

The same sentence is what `xtal modules` prints beside `blender`, and
what *Preferences ▸ Engines* says under the empty field.  The dialog
in {numref}`fig-utilities-stl-export-dialog` was built directly for
the figure, which is why it shows at all.  Once Blender is installed
and found, the run proceeds as above.

% TODO(Sam): Blender is not installed here, so no run was made.  When
% it is, add the run's real output: the "cut one cell: N atoms, M
% bonds" status line, the "wrote ... MB" line, and the run folder's
% listing (structure.pdb, structure.stl, the log), and check the
% add-on sentence Blender prints when Atomic Blender is missing.

## Limitations

- Blender and the Atomic Blender add-on are your installs; the
  application ships neither, and the shipped script is used as its
  author wrote it.
- The remesh's memory grows as the cube of the voxel size, and a
  large cell at a fine voxel is a long run.  Start at the defaults and
  refine the voxel only if the print needs it.
