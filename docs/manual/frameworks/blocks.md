# Building blocks and connection points

A building block is a molecule that says where the next block goes.
After this section you know what a connection point is and why it sits
where it does, when several atoms should share one, how to mark them
on a molecule you have open, how to draw a block for a slot, and where
the blocks you make are kept.

```{index} single: building block
```
```{index} single: connection point
```

## What a block is

A {term}`building block` is an `.xyz` file in the form PORMAKE
{cite}`lee2021pormake` reads: the atom count, a second line naming
which atoms are connection points, the atoms, and a **bond block** --
one line per bond, with a letter for its order -- after them.  Nodes
and linkers are the same kind of file; what tells them apart is how
many connection points they carry, and a block fits a slot of a net
when that number equals the slot's coordination.  PORMAKE ships 867
of them; the application adds twelve of its own and reads any you
make.

## A connection point

A {term}`connection point` is a {term}`dummy atom`, `X`, standing off
the atom or atoms of the block that the next block attaches to.
Where the next block goes is the direction from those atoms to the
`X`; how far away it is written is fixed:

:::{note}
**A connection point is 0.75 Å from the centroid of the atoms it
hangs off, not a bond length.**  The number was measured, not chosen:
over the 867 blocks PORMAKE ships, the 4256 distances from an `X` to
its body atom have a median of 0.750 Å and 70 % fall within 0.05 Å of
it.  Two blocks are joined by fusing their connection points, so a
block written with its points at a real bond length builds a
framework with every linker bond roughly twice too long -- and nothing
anywhere reports it.  That is why the application pulls every point it
writes in to 0.75 Å, keeping the direction and changing only the
length.
:::

Because a connection point is an `X`, everything that already sets
markers aside does so here too: a force field is built over the
structure without them and shows them with zero force, *Add
hydrogens* leaves them alone, and a module run drops them and puts
them back.  Net edges and measurements take them like any atom.

### An attachment: one point, one or more atoms

```{index} single: attachment
```
```{index} single: connection point; polydentate
```

**An {term}`attachment` is one `X` plus the distinct atoms bonded to it.**
Most connection points hang off one atom -- a carboxylate carbon, a
ring carbon -- and until September 2026 every one did.  Two real
materials showed why that is not enough.  MFU-4l's Zn{sub}`5`Cl{sub}`4`
kernel meets each triazolate through *two* ring atoms, and
Ni{sub}`3`(HITP){sub}`2`'s nickel meets each imine through two
nitrogens: a chelate meets its metal through two atoms.  Marked one
at a time, those blocks come out with twice the coordination number
they have and fit no net in the catalogue; marked as one point each,
they fit **pcu** and **hcb** exactly.

The grouping is the block's own bonds -- the bond block says which
atoms the `X` is bonded to -- so nothing new enters the file format,
and PORMAKE has always read it.  *Distinct* atoms, never the bond
count: 26 of the shipped blocks name one partner twice in their bond
block, and a centroid that counted the record twice would weight that
atom double for no reason.  With one member the centroid is that
atom, so every single-point block is written byte for byte as it was.

Three things are refused when a block is written, each named per
atom:

- a connection point bonded to another connection point;
- members of one attachment further than **5.0 Å** apart.  The four
  blocks this was built for span 1.405 to 2.861 Å; half of PORMAKE's
  blocks are more than 10 Å wide, so what the limit catches is two
  atoms marked at opposite ends of a molecule, and 5 Å catches that
  mis-click in 95 % of the database while leaving room for a
  tetradentate pocket;
- a point facing back into the molecule.  This is judged one bond
  in -- against the atoms the members are themselves bonded to -- and
  never against the block's middle, because a node's arms are
  concave: 77 of the 4256 shipped points face their own block's
  centroid, and every one of them is correct.

Two bonds on a connection point are *not* refused; they are a
bidentate attachment.

## Marking connection points on a molecule

```{index} single: Mark connection points
```
```{index} single: Mark as one connection point
```

With a molecule open -- built from SMILES, or cut from a crystal --
two commands in the *Structure* menu turn atoms into connection
points:

1. Select the atoms that will become connection points and choose
   *Structure ▸* {ref}`Mark connection points
   <cmd-mark_connection_points>`.  Each selected atom that has
   **exactly one bond** becomes an `X` 0.75 Å along that bond from its
   neighbour.  A hydrogen on a ring carbon is the usual case: the
   hydrogen already points where a substituent would.  An atom with
   no bond, or more than one, is refused with a sentence.
2. For a chelate, select the atoms that meet the next block
   *together* -- the two nitrogens, the two ring atoms -- and choose
   *Structure ▸* {ref}`Mark as one connection point
   <cmd-mark_one_connection_point>`.  The selection collapses into a
   single `X`, 0.75 Å from the middle of everything the atoms were
   bonded to, carrying those bonds.

Each is one undo step for both halves -- the element and the position
-- so {kbd}`Ctrl+Z` gives back the atom you had.  If the bond that
decided the direction was only perceived, it is written down as your
own before the element changes, because perception never bonds a
dummy atom and the marked atom would otherwise float free of its
molecule on the next read of the graph.

:::{note}
**There is no Unmark.**  An `X` does not remember what it was: the
element is gone and the atom has moved, and a command claiming to
reverse that would have to guess an element and a bond length --
guessing carbon at 1.09 Å is how a marked hydrogen comes back as
something you never had.  The way back is {kbd}`Ctrl+Z`.  The same
holds for *Mark as one connection point*: the grouping is the
structure's own bonds, not a state on the marker, so there is nothing
to unmark there either.
:::

The twelve blocks the application ships were made this way: the
Kuratowski node and BTDD linker of MFU-4l, and the NiN{sub}`4`
and triphenylene of Ni{sub}`3`(HITP){sub}`2`, cut out of the sample
CIFs with *Mark as one connection point*, and their relatives written
by script in the same shape.  In the picker they are the
**Polydentate** ones.

% TODO(Sam): a step-by-step recipe for cutting a node out of an open
% crystal (select the cluster, take it into a document of its own,
% mark) has not been walked through in the app for this page; the
% library docstring says the shipped blocks were made "by the gesture
% Mark as one connection point" and no more.  Confirm the route with
% Julius before adding numbered steps.

## Drawing a block for a slot

```{index} single: building block; drawing
```
```{index} single: SMILES; connection points in
```

The quickest way to a new linker or node is the **Draw…** button on a
slot row of the MOF builder ({numref}`fig-frameworks-draw-block`).  It
opens the molecule builder's own SMILES box and canvas, aimed at that
slot:

1. Type the SMILES with a `*` for each connection point --
   `*c1ccc(*)cc1` is a *para*-phenylene, `*c1cc(*)cc(*)c1` a
   1,3,5-substituted benzene -- or draw it on the canvas.  `[*:1]` and
   `[*:2]` say which point is which when that matters.
2. Read the footer.  It names the formula, the atom count and the
   connection points, and says whether they fit: *C6H3, 12 atom(s),
   3 connection point(s) -- fits node 1, 3-connected*, or *Node 1,
   3-connected needs 3, not 2*.  **Save and use** is enabled only when
   they do.
3. Give it a name -- the file's name, which is what the picker shows
   -- and press **Save and use**.  The block is written, the row that
   asked selects it, and *Build* builds with it.

:::{figure} /figures/frameworks/draw-block.png
:name: fig-frameworks-draw-block
:width: 55%

*Draw a building block* for a 3-connected node slot: the SMILES, the
canvas, and the footer saying the three connection points fit.
:::

The molecule is embedded with each `*` capped by a hydrogen, relaxed,
and the caps are then relabelled `X` and pulled in to 0.75 Å -- a
hydrogen points exactly where a substituent would, so the direction is
right; the one caveat is sterics, since a hydrogen is smaller than the
carboxylate it stands in for, and a crowded linker relaxes a little
more open than it would with its real neighbours ({doc}`molecule-builder`).

For a molecule already open in a tab -- one you marked by hand --
*File ▸* {ref}`Save as a building block… <cmd-save_building_block>`
writes it to the same folder.  Its dialog shows everything that stops
the structure being a block *before* you press Save: a point that is
bonded to another point, members too far apart, two molecules in the
cell, no connection points at all.

:::{note}
**A block you draw goes to `blocks/` in your workspace**, and the
catalogue reads that folder alongside PORMAKE's database, so the block
appears in the picker with nothing further clicked.  It is an
ordinary folder of the {term}`workspace`, so the *Workspace* panel
shows it, and because there is always a workspace, *Draw…* never asks
you to name a folder first.  A block of yours with the same name as
one of PORMAKE's replaces it.  The *Extra building blocks* folder
under *Your own topologies and building blocks* is a second place to
read from -- a shared folder, say -- and `xtal run mof.build
--workspace` finds the workspace's `blocks/` by walking up from the
run folder, so a command-line build uses the same blocks the window
does.
:::

## Settings

The block file format, the two folders and the picker's fields are
those of {ref}`Build a framework… <mod-mof-build>`; the drawing
dialog's four fields are the molecule builder's, listed under
{ref}`Molecule from SMILES… <mod-build-molecule>`.

## Limitations

- A chelate's joint comes out about 0.3 Å long, for the reason given
  in {doc}`mof-builder`: the 0.75 Å was measured over one atom meeting
  one atom.  The application's `docs/TODO.md` records the two ways out
  and why neither has been taken.
- A block written with no bond block says nothing about which atom a
  connection point hangs off; such a block has no attachments the
  orientation rule can score and takes the path PORMAKE always took.
