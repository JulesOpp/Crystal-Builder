# Export

*Export…* writes a file for another program to read, and cleans the
structure on the way out.  After this page you know what an exported
file does and does not contain, how to read the dialog's line about
what is lost, and how to hand a drawn net to Systre.

## One door out

```{index} single: export; what is cleaned
```

A CIF written *into the workspace* is the document -- it carries the
markers you placed and the net you drew, because that is what you
built and a file that loses half of it is not a copy of anything
({doc}`formats`).  A file written *for somebody else* is a crystal,
and three things do not belong in it.  Every export, in every format,
passes through the same cleaning before the writer sees it:

:::{note}
**Export cleans.**  A file written by *Export…* holds **no dummy
atoms**, **no net edges** and **no suppressed bonds**, whatever the
format.

- A {term}`dummy atom` is a marker and not chemistry, so a program
  that reads one gets an element it has never heard of sitting in the
  cell -- the same reason a force field holds markers back at the
  door and a module run sets them aside.  This is that rule at the one
  remaining door.
- A net edge ({term}`topology bond`) is not a bond.  It joins the
  centres of two building blocks through empty space, and anything
  that reads it as chemistry reads a framework held together by bonds
  four times too long.
- A {term}`suppressed bond` is the record of one deliberately
  deleted.  It is the absence of a bond, so writing it as a row in a
  bond loop says the opposite of what it means.

What survives is the chemistry: the atoms, and the bonds that are
bonds.  A crystal with no markers and no net -- every crystal anybody
has opened -- passes through untouched.
:::

The dialog says when this applies to the structure in front of you,
in the same place and the same voice as what the *format* drops,
because from where you stand it is the same question: *2 dummy atoms
and 12 net edges will not be written -- a marker is not chemistry
and a net edge is not a bond.*

## Exporting a structure

```{index} single: export; dialog
```

1. Choose {ref}`Export… <cmd-export>` from the *File* menu.  The
   dialog opens on CIF, with the file placed in the directory you last
   used and named after the document.
2. Pick a *Format*.  The picker offers every format the registry can
   write except the project ({numref}`fig-utilities-export-dialog`);
   changing it swaps the suffix on the path, and the line under it
   says what that format keeps and what is not written.  The six
   sentences are listed on {doc}`formats`; read the one for the
   format you chose before you go on.
3. For CIF, choose between *With symmetry (the asymmetric unit and
   the operations)* and *P1 (every atom written out)*.  Both are right
   and they are not the same file: the second is for a program that
   does not apply symmetry operations itself.  The box is shown for
   CIF only.
4. Tick *Selected atoms only* to write just the selection -- "export
   this molecule" is the second thing anybody wants after "export
   this".  The box is enabled only when something is selected, and its
   tooltip says how many atoms it will write (*Write the 12 selected
   atoms and nothing else*; *Nothing is selected* otherwise).
5. *Browse…* or type a path, then press *Export*.  The status bar
   says `exported <name>`, the directory is remembered for next time,
   and the *Workspace* tree refreshes if you wrote into it.

:::{figure} /figures/utilities/export-dialog.png
:name: fig-utilities-export-dialog
:width: 75%

*File ▸ Export…* on HKUST-1.  The line under the picker is computed
from the format's registry entry; the CIF box appears for CIF alone,
and *Selected atoms only* is greyed because nothing is selected.
:::

:::{note}
**An export never becomes the document.**  The tab keeps the file it
had, the modified flag is untouched, and the exported file is one
way: opening it again is opening another file.  {ref}`Save File
<cmd-save>` is the command that adopts a path, and it writes a project.
:::

On the command line, `xtal convert input output` writes any readable
file as any writable one, with `--p1`, `--supercell`, `--niggli` and
`--wrap` as transformations on the way -- but it does **not** clean:
see the warning at the end of {doc}`formats`.

## Exporting a net for Systre

```{index} single: export; net for Systre (.cgd)
```
```{index} single: Systre
```

The *Net* panel names the {term}`net` you have drawn from a canonical
key checked against the RCSR {cite}`okeeffe2008rcsr`, and neither of
those checks is made by anybody else.  Systre
{cite}`delgadofriedrichs2003systre` is the reference implementation,
and {ref}`Export Net for Systre… <cmd-export_net>` writes the net as
a `.cgd` file -- Systre's input format and the one the RCSR publishes
in -- so that it can be asked the same question.  How a net is drawn
and read, and what the panel's answer means, is
{doc}`/frameworks/nets`.

1. Draw the net.  The command is enabled only once a structure has
   topology bonds on it; with none, the status bar says *no net has
   been drawn*.
2. Choose *File ▸ Export Net for Systre…*, or *Export for Systre…* in
   the *Net* panel.  It is a plain save dialog rather than the
   *Export* one: the file holds a net and no structure, so format,
   selection and cleaning mean nothing for it.  A name without `.cgd`
   gets the suffix added.
3. The status bar says `wrote <name>.cgd -- run Systre on it for a
   second opinion on the name`.

What is written is the common dialect only, in `GROUP P1` over the
expanded cell: every vertex as a node and every edge as a pair of
points, so that nothing of this application's stands between the net
and the second opinion -- a space group would have to be spelled in a
setting Systre agrees with.  Two vertices so close that an endpoint
could be matched to either are refused by name (*Could not export
net*), because Systre finds an edge's ends by position and a file
that joins the wrong one describes a different net.

## Other files that leave

- {ref}`Export Image… <cmd-export_image>` writes a picture of the
  view: {doc}`images`.
- {ref}`Export as STL… <cmd-export_stl>` writes one cell as a mesh
  through Blender: {doc}`stl`.
- {ref}`Save as a building block… <cmd-save_building_block>` writes
  the open molecule, with its {term}`connection points <connection
  point>`, into the workspace's `blocks/` folder for the MOF builder:
  {doc}`/frameworks/blocks`.
- A run leaves its own files -- `trajectory.extxyz`, a log, a final
  structure, `report.json` -- in the workspace, under the structure
  it ran against; they are described with the run that makes them.
