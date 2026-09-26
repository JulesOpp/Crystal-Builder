# File

The *File* menu opens, saves and exports structures, and chooses the
{term}`workspace` they live in.  After this page you can open a file
or a sample, save a session as a project, write a CIF or a picture for
another program to read, and move between workspaces without losing
tabs to a question you did not expect.

## Opening a structure

```{index} single: opening; a structure
```

There are four doors into the window, and every one of them ends with
the structure filed in the workspace:

1. {ref}`New <cmd-new>` ({kbd}`Ctrl+N`) starts an empty structure.
   It gets an entry in the workspace at once -- `untitled`, then
   `untitled-2` -- so that the first calculation run against it has
   somewhere to land.
2. {ref}`Open… <cmd-open>` ({kbd}`Ctrl+O`) opens a file from
   anywhere on disk.  The file is copied into the workspace and the
   tab follows the copy; where it came from is remembered, and names
   the tab when the same file is opened again.  Dropping a file on
   the window does the same, and so does double-clicking a file in
   the *Workspace* panel.
3. *Open Recent* lists the files opened lately by name, with *Clear*
   at the bottom.  It reads *Nothing yet* on a first run.
4. *Open Sample* opens one of the structures that ship with the
   application: seven at the top of the submenu, from
   {ref}`MOF-5 <cmd-sample_mof5>` -- written in {term}`P1`, so that
   *Symmetry ▸ Find symmetry…* has Fm-3m to recover from it -- to
   {ref}`CFA-1 in P1 <cmd-sample_cfa1_p1>`; sixteen more under
   *From the COD*, as deposited in the Crystallography Open Database
   {cite}`grazulis2012cod`; and the same sixteen under *Prepared for
   simulation*, as `resources/samples/prepared/` holds them.  The
   reference describes each one in a line.  A sample is copied into
   the workspace like any other file, so saving it never writes into
   the application itself.

:::{note}
**Every document has an entry in the workspace**, whichever door it
came through.  A file opened from outside is copied in, and the copy
is what the tab is; the original is never touched again.
:::

## Saving

```{index} single: saving; Save File converts
```
```{index} single: project file (.xtalproj)
```

1. {ref}`Save File <cmd-save>` ({kbd}`Ctrl+S`) writes the session --
   the structure, the bonds you drew, the view, the selection and the
   measurements -- over the file the tab is.  It does not ask where.
2. {ref}`Save As… <cmd-save_as>` ({kbd}`Ctrl+Shift+S`) writes the same
   session under another name.  Whatever extension you type, the file
   written is a {term}`project file`.

:::{note}
**Save File converts, and never asks where.**  A document opened as a
CIF becomes the `.xtalproj` of the same name beside it on its first
save, and the CIF is left exactly where it is.  A CIF cannot hold a
measurement, a plane or the view you were looking at it in, so the
session goes to a file that can.  Overwriting is silent by default;
*Preferences ▸ General ▸ Ask before Save File writes over an existing
file* adds a confirmation, and only ever for a file that already
exists.
:::

Between saves, every tab edited since the last tick is
{term}`autosaved <autosave>`.
The interval is *Preferences ▸ General ▸ Keep unsaved changes every …
min* (two minutes to start with; *never* turns it off), and the copy
goes to the workspace's `.autosave/` folder, mirroring the file's
place in the workspace -- never over the file itself.  It is deleted
when the document is clean again, saved or undone back to the file,
and when you deliberately discard the work by closing the tab or
answering *yes* to the quit question.

:::{note}
**An autosave is offered back, never applied.**  Opening a file with
a newer autosave puts a notice bar across the window with *Restore*
and *Discard* on it.  Restore is one undo step with the project's own
bonds, so {kbd}`Ctrl+Z` is the file as it was saved.
:::

## Exporting

```{index} single: export; formats
```

An export is a file for something else to read, and it never becomes
the document's file.

1. {ref}`Export… <cmd-export>` offers a format, its options and a
   path.  The formats are CIF (`.cif`, `.mcif`), VASP POSCAR/CONTCAR,
   pymatgen Structure (JSON), CSSR, DFTB+ geometry (`.gen`) and
   Extended XYZ.  The line under the picker says what the chosen
   format keeps and what it drops -- for CIF, *CIF keeps symmetry,
   occupancy, displacement parameters and charges; bonds and the view
   are not written*; for XYZ, *XYZ keeps occupancy; symmetry,
   displacement parameters, charges, bonds and the view are not
   written*.  A CIF is written *With symmetry (the asymmetric unit and
   the operations)* or as *P1 (every atom written out)*, and every
   format takes *Selected atoms only*.
2. {ref}`Export Image… <cmd-export_image>` writes the 3D view as PNG,
   JPEG, TIFF or SVG.  The *Resolution* control shows the pixel size
   that will actually be written -- *1600 x 1200 pixels* -- rather
   than a magnification, because on a high-resolution screen the
   render is already twice the size of the viewport and a "2x" would
   be four times the pixels you thought you asked for.  *Transparent
   background* is offered where the
   format can carry it (PNG, TIFF and SVG; JPEG cannot).  SVG has no
   resolution to set: it is one named, separately editable shape per
   atom, bond and cell edge.
3. {ref}`Export as STL… <cmd-export_stl>` turns one unit cell with its
   bonds into a mesh a 3D printer can take.  Blender does the meshing,
   so it has to be installed and named in *Preferences ▸ Engines*.
4. {ref}`Export Net for Systre… <cmd-export_net>` writes the
   {term}`net` drawn over the structure as a `.cgd` file for Systre
   {cite}`delgadofriedrichs2003systre` to name -- a second opinion on
   the *Net* panel that does not come from the code that gave the
   first.  It is enabled only when a net has been drawn.
5. {ref}`Save as a building block… <cmd-save_building_block>` writes
   the open molecule into the workspace's `blocks/` folder, where the
   MOF builder's picker reads it beside the 867 blocks PORMAKE ships.
   It needs {term}`connection points <connection point>` on the
   molecule, and the dialog says what is missing; {doc}`Building
   blocks and connection points </frameworks/blocks>` is where blocks
   are made.

:::{note}
**The workspace copy carries what the export cleans.**  The CIF in the
workspace holds the markers you placed and the net you drew, because
that copy *is* the document.  A file written by *Export…* holds no
{term}`dummy atoms <dummy atom>`, no net edges and no suppressed
bonds, because the program reading it would take them for chemistry.
Going the other way, a CIF from elsewhere that carries a `_geom_bond`
loop is not read as bonding: that loop is nearly always a refinement's
distance table, and *Structure ▸ Recalculate bonds* stays in charge of
what is bonded.
:::

## Workspaces

```{index} single: workspace; switching
```

1. {ref}`New Workspace… <cmd-new_workspace>` makes a folder and opens
   it.  {ref}`Open Workspace… <cmd-open_workspace>` opens a folder
   that already is one.
2. Either way the new workspace is opened *first*, so a folder that
   turns out not to be one costs you nothing.

:::{note}
**Changing workspace closes every tab.**  A tab is a structure *of*
the workspace it was opened in -- its runs are filed there -- so a
tab carried across a switch would file its next run into the folder
you had walked away from.  If anything is unsaved you are asked once,
*Some structures have unsaved changes. Leave this workspace anyway?*,
and then everything closes.  A workspace remembers its own tabs, so
the one you open comes back with the tabs it was left with.
:::

What a workspace holds, and how the tree shows it, is in
{doc}`the GUI </quickstart/gui>`.

## Closing and preferences

1. {ref}`Close <cmd-close_tab>` ({kbd}`Ctrl+W`) closes the tab in
   front; a modified one asks first.  {ref}`Close All
   <cmd-close_all_tabs>` ({kbd}`Ctrl+Shift+W`) closes every tab, and
   each modified one still asks.
2. {ref}`Preferences… <cmd-preferences>` ({kbd}`Ctrl+,`) holds
   everything the application remembers between sessions, on four
   pages: *General* (saving, autosave, where new workspaces go, the
   recent list), *View defaults* (what a newly opened structure is
   drawn as), *Bonding* (whether bonds follow the geometry, and the
   criteria new structures start from) and *Engines* (where the
   external programs and optional Python packages are, and whether
   each was found).
3. {ref}`Quit <cmd-quit>` ({kbd}`Ctrl+Q`) leaves the application.

On macOS, *Preferences…* and *Quit* are in the application menu rather
than under *File*, as the platform expects.

:::{note}
**Quitting asks before it stops anything.**  If a calculation is
running you are asked whether to stop it first, and about unsaved
work second; the run is stopped only once both answers are yes.  A
*No* to either leaves the window, the edits and the run exactly as
they were.
:::
