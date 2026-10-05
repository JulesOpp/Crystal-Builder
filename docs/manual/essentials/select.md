# Select

The *Select* menu names atoms and bonds so that the next command has
something to act on.  After this page you can select by element, by
bond, by fragment or by symmetry orbit, and you know why inverting a
selection sometimes gives you more atoms than you expected.

## What a selection is

```{index} single: selection; what it holds
```

A selection holds atoms of the drawn cell, bonds, and net edges, and
remembers the order the atoms were picked in -- which is what makes
*Measure selection* an angle *about the middle one*.  The right-hand
end of the status bar summarises it (*nothing selected*, *1 atoms
(Zn)*), the *Sites* table highlights the sites behind it and the
*Inspector* shows the last one picked.

In the 3D view, in *Select* mode, a click selects an atom or a bond,
shift-click adds to the selection, a double-click takes the whole
connected fragment, and a click on nothing clears it.  *Box select*
drags a rectangle and takes everything inside it, front to back, bonds
included.  Both are on the {doc}`mouse modes <mouse-modes>` page.

## The commands

1. {ref}`Select all <cmd-select_all>` ({kbd}`Ctrl+A`) takes every atom
   and every bond between them -- but not the net edges, because
   *Delete* acts on the net before anything else and *Select all*
   followed by *Delete* should take the crystal apart, not the net.
2. {ref}`Select none <cmd-select_none>` clears it.  It has no key of
   its own: {kbd}`Esc` clears the selection once there is no gesture
   or mode to leave first.
3. {ref}`Invert selection <cmd-invert_selection>` ({kbd}`Ctrl+I`)
   takes everything that is not selected.  It works over whole
   orbits: the selection is grown to the orbits it touches first, so
   that the complement means what it says (see the note below).  In
   P1 that changes nothing.
4. {ref}`Select same element <cmd-select_same>` grows the selection to
   every atom of the elements already in it; *By element* lists the
   elements this structure has and selects one directly.
5. {ref}`Bonds between elements… <cmd-select_bonds>` asks for two
   elements -- only those in the structure are offered, and *Any
   element* stands for either end -- and selects every bond joining
   them, and no atoms.  The count beside the choice is the count the
   selection will have, so an empty pair is seen before *OK*.  The
   usual reason for an empty pair is bonds that were never perceived,
   and *Recalculate bonds* is yours to press.  With bonds and no atoms
   selected, *Delete* and *Set Bond Type* act on those bonds alone,
   which is how a whole class of bonds is deleted or typed in one
   step.
6. *Grow* extends what you have: {ref}`Grow to bonded neighbours
   <cmd-expand_bonded>` ({kbd}`Ctrl+G`) adds the atoms one bond away,
   and again on each press; {ref}`Grow to whole fragment
   <cmd-expand_fragment>` ({kbd}`Ctrl+Shift+G`) takes the connected
   molecule or framework; {ref}`Grow to symmetry orbit
   <cmd-expand_orbit>` adds every image of every site touched.  A
   grown selection takes the bonds inside it too.
   {ref}`Grow to neighbours only <cmd-expand_neighbours>` takes the
   atoms one bond away and lets go of the ones you had: select the
   zinc, and it leaves the oxygens on them.
7. {ref}`Advanced selection… <cmd-select_dialog>` is everything
   else, one rule at a time: an element or several, a label pattern
   (`O1*`, where the case counts), every image of one site, atoms with
   *n* bonds (or at least, or at most), atoms bonded to an element,
   atoms within *n* bonds or *r* Å of the selection, near a point, or
   inside a fractional box -- 0 to 1 on every axis is the whole cell
   -- and bonds or net edges by their elements, order, length and
   whether you drew them.  Below the rule, choose whether it
   *replaces* the
   selection, *adds* to it, *removes* from it or *intersects* with
   it: the four-coordinate zinc, then *Intersect* with a box, is the
   zinc of one layer.  The count beside *Apply* is what *Apply* will
   leave selected, and the dialog stays open for the next rule.  A
   line under each chooser says what the rule and the combine choice
   do, and *Example* unfolds a worked two-rule selection.
   Counts of bonds are the bond graph's, so they say what the bonds
   say now; lengths are the bonds' as the atoms stand.
8. *Functional group* in the same dialog lists the groups the
   structure has, each with its count -- a hydroxyl on a phenol or an
   alcohol, a carboxylic acid or carboxylate, a ketone or quinone, an
   aldehyde, an ether, ring ether or epoxide, an ester, lactone or
   anhydride, an amide, an amine, a C-F -- and takes the whole group
   or only its *handle*, the atom it is changed by: a hydroxyl's
   hydrogen, a C-F's fluorine.  Groups are read off the bonds, never
   off their lengths, so the oxygen of an acid that carries the
   hydrogen is the hydroxyl whichever bond a refinement wrote
   shorter; and each atom is in one group, so an acid is not also a
   hydroxyl and a carbonyl.
9. {ref}`Show only selected <cmd-show_only_selected>` in the View menu
   draws the selection and nothing else, and {ref}`Show all
   <cmd-show_all>` brings the rest back.  Only the picture changes:
   the hidden atoms are still in the structure, in every calculation
   and in every save, and hiding them is not an undo step.  The status
   bar says how many atoms are shown.  An edit keeps the same atoms
   hidden, and what it adds is shown: select every phenol's hydrogen,
   show only those, substitute them with an acetyl, and the picture is
   the new esters.

The four *Grow* entries and *Select same element* are also in the
context menu of an atom, and *Select all* and *Select none* in the
context menu of the background.

:::{note}
**A selection is atoms; an edit is sites.**  Every edit acts on whole
symmetry orbits, so a selection that holds part of an orbit is, for
the purpose of a delete or a move, the whole orbit.  *Delete* asks
before it takes more than you selected; *Invert selection* grows to
the orbit first so that its answer does not overlap the selection it
came from.  *Grow to symmetry orbit* shows you the orbit before you
act on it.
:::

Which selection actions are enabled follows the selection: the
reading ones (grow, select same, copy) need an atom; the editing ones
(cut, duplicate, change element, mark connection points) need an atom
and a structure that is not playing a trajectory; a centroid, a merge
and a single connection point need at least two.
