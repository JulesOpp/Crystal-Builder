# Cell

The *Cell* menu changes the box the crystal is described in: its
parameters, its multiples, its basis and where the origin's cell
begins.  After this page you can strain a cell or add vacuum around a
molecule, build a supercell or a transformed cell, reduce a cell to
its shortest basis, and know which of these keep the space group and
which give you P1.

None of these commands changes the bonding.  The *Edit cell* dialog
says so at the bottom: *The bonds are unchanged by this.  Structure ▸
Recalculate bonds afterwards if the new cell should change them.*

## Edit cell

```{index} single: cell; editing parameters
```

{ref}`Edit cell… <cmd-edit_cell>` is the six cell parameters, with two
questions answered before you press *OK*
({numref}`fig-edit-cell`).

1. Type the parameters that are free.  A space group constrains the
   cell as well as describing it, so the parameters the group ties
   down are greyed and follow the ones that are not: for HKUST-1 in
   Fm-3m the note reads *Fm-3m is cubic: only a is free (b = a, c =
   a, alpha = 90, beta = 90, gamma = 90).  To edit the rest, change
   the space group or reduce to P1.*  Typing a non-cubic cell into a
   cubic group would not give a cubic crystal with an odd cell; it
   would give a structure its own operations no longer map onto
   itself.
2. Say what is held fixed.  **Keep fractional coordinates** drags the
   atoms with the cell: the crystal is scaled, bonds stretch, this is
   a strain.  **Keep cartesian coordinates** leaves every atom where
   it is in space and rescales the fractions: the crystal is
   unchanged, the box is not, and this is how vacuum is added around
   a molecule.  The preview says what each choice does to the volume
   and the density -- *V = 18280.821 A^3 (1x the current 18280.821);
   density scales by 1x -- the atoms move with the cell*.
3. *Reset* puts the parameters back; *OK* applies them as one undo
   step, and the status bar reads the new cell with *(fractional
   kept)* or *(cartesian kept)* after it.

:::{figure} /figures/essentials/edit-cell.png
:name: fig-edit-cell
:width: 55%

*Cell ▸ Edit cell…* on HKUST-1: the group leaves one parameter free,
and the dialog says what keeping fractional or cartesian coordinates
will do before you choose.
:::

## Supercell

```{index} single: supercell
```

{ref}`Supercell… <cmd-supercell>` builds a bigger cell, or a
differently shaped one, on two tabs.

1. **Multiples** is the everyday case: *n{sub}`a` × n{sub}`b` ×
   n{sub}`c`* of the cell you have, up to 20 along each axis, same
   shape, more atoms.
2. **Transformation** takes a general integer matrix *P* -- the new
   *a*, *b*, *c* as integer combinations of the old ones, entries up
   to 12 -- which is the only way to write the cells crystallographers
   want and cannot express as three multiples: a primitive cell out of
   a centred one, a √2 × √2 surface cell, the C-centred setting of a
   monoclinic structure.
3. The line under the tabs says what will come out before it comes
   out -- *supercell 1x1x1: 624 sites, 624 atoms, V = 18280.82 A^3*
   -- because 2 × 2 × 2 of a 648-atom framework is a number worth
   seeing first.

Both land in {term}`P1`: which sites are independent is a question
about a particular cell, and it stops meaning anything the moment the
cell changes.  *Symmetry ▸ Find symmetry…* recovers whatever symmetry
the supercell has.

## Reductions and wrapping

```{index} single: Niggli reduction
```
```{index} single: Delaunay reduction
```

1. {ref}`Niggli reduction <cmd-niggli>` and {ref}`Delaunay reduction
   <cmd-delaunay>` re-express the same crystal on the shortest, most
   nearly orthogonal basis there is -- the usual way to compare two
   descriptions of one lattice, or to tidy a cell a transformation
   left skewed.  The result is in P1: on MOF-5 in Fm-3m the status
   bar reads *niggli-reduced the cell: 424 sites, 424 atoms, V =
   17305.33 A^3*.
2. {ref}`Wrap atoms into the cell <cmd-wrap_cell>` folds every site
   back into the range 0 to 1 and keeps the group: *folded every site
   into the cell: 7 sites, 424 atoms*.  A molecule pasted or dragged
   across a cell face is drawn on the far side afterwards; nothing
   about the crystal changes.

How many cells are *drawn*, and what happens to a bond that crosses
the edge of the picture, are questions about the view and not the
cell: the toolbar's *cells* boxes and *View ▸ Display range…* are on
the {doc}`View <view>` page.

:::{note}
**Every command on this menu is one undo step**, whether it moved six
numbers or rebuilt the cell with eight times the atoms, and none of
them recalculates the bonds.  A supercell of a framework carries the
framework's bonds, expanded; a strained cell carries the bonds it had,
stretched.
:::
