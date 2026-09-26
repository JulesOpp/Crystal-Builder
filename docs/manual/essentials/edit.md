# Edit

The *Edit* menu is the undo stack, the clipboard and the three edits
that act on whatever is selected: delete, delete bond and change
element.  After this page you know what one undo step is, how a
fragment travels between tabs and programs, and what *Delete* takes
when symmetry ties atoms together.

## Undo and Redo

```{index} single: undo; what one step is
```

1. {ref}`Undo <cmd-undo>` ({kbd}`Ctrl+Z`) and {ref}`Redo <cmd-redo>`
   ({kbd}`Ctrl+Shift+Z`) name the step they would take: the menu reads
   *Undo Recalculate bonds*, *Undo Find symmetry*, *Undo Add
   centroid*.
2. Every change to the structure is one step, however much it
   touched: a symmetry operation that rewrote every site, a
   preparation for simulation with its seven steps, an optimisation.
   A gesture that repeats -- a drag in *Move* mode, a held arrow in
   the *Move* panel -- merges into one step while it lasts, so forty
   nudges come back on one {kbd}`Ctrl+Z`.
3. What is not on the stack: the view (style, range, background),
   measurements and planes, and a pore network drawn by a run.  These
   are notes about the crystal rather than changes to it, so undoing
   never touches them and they never mark the document modified.

Both entries are greyed while a trajectory is being played, and so
is every other edit: the atoms are showing a frame, and an edit made
against them would be wiped by the next one.

## Cut, Copy, Paste and Duplicate

```{index} single: clipboard; XYZ
```

1. {ref}`Copy <cmd-copy>` ({kbd}`Ctrl+C`) lifts the selected atoms out
   as a fragment, and puts the same atoms on the system clipboard as
   XYZ text.  The status bar says what was copied -- *copied 4 atoms
   (C2HN)* for a methylimidazolate fragment of ZIF-8.
2. {ref}`Paste <cmd-paste>` ({kbd}`Ctrl+V`) adds the fragment to the
   structure in front (*paste 4 atom(s)*), and leaves it selected so
   you can see where it landed.  If the clipboard holds XYZ text from
   another program, that is what is pasted, so a molecule copied out
   of anything that writes XYZ arrives here.  A fragment pasted into a
   structure with a space group is multiplied by the group's
   operations, and the message says so.
3. {ref}`Cut <cmd-cut>` ({kbd}`Ctrl+X`) is copy followed by delete.
4. {ref}`Duplicate <cmd-duplicate>` ({kbd}`Ctrl+D`) pastes a copy of
   the selection back into the same structure, 1 Å along *x* from
   where the selection is -- far enough to see, near enough to drag
   into place in *Move* mode.

A pasted fragment arrives with the bonds it had inside itself and no
bond to anything already there: see the note on the
{doc}`Structure <structure>` page.

## Delete

```{index} single: deleting; whole orbits
```

1. {ref}`Delete <cmd-delete_selection>` ({kbd}`Del`, or
   {kbd}`Backspace` on a keyboard without a forward-delete key) acts
   on whatever is selected: net edges when net edges are, otherwise
   bonds when bonds are, otherwise the sites behind the selected
   atoms.  One key for the three, so clicking a bond and pressing
   delete deletes the bond.
2. Right-click an atom and the entry says how much it will take --
   *Delete 2 atoms* -- because *Delete* and *Delete 14 atoms* are
   different promises.
3. {ref}`Delete bond <cmd-delete_bond>` suppresses the selected bonds
   and their whole symmetry orbit, whatever else is selected.

:::{note}
**Every edit acts on whole orbits.**  Symmetry ties an atom to its
images, so deleting one Zn of MOF-5's Fm-3m cell deletes the site and
all 32 atoms it generates.  If you selected part of an orbit you are
asked first -- *1 atom(s) selected, but they belong to 1 site(s)
totalling 32 atoms -- symmetry ties them together.  Delete the whole
orbit?* -- and the status bar reports what went: *deleted 1 site(s)
(32 atoms)*.  To delete one atom of an orbit and keep the rest,
*Symmetry ▸ Reduce to P1* first.
:::

:::{warning}
**A deleted bond stays deleted.**  A suppression is stored so that
*Recalculate bonds* cannot undo it, and it is saved with the project;
once the undo stack has gone, {ref}`Reset bonds to automatic
<cmd-reset_bonds>` ({kbd}`Ctrl+B`) is the only way back, and it drops
every bond you drew as well.
:::

## Change element

1. {ref}`Change element… <cmd-change_element>` asks for a symbol and
   gives it to the sites behind the selected atoms -- *changed 1
   site(s) to N*, undone as *Undo Change element to N*.  A string
   that is not an element symbol is refused with *'…' is not an
   element symbol* rather than accepted as a label.
2. The same edit is one click away in the *Inspector* panel, which
   shows the selected site's element, label, coordinates, occupancy,
   U{sub}`iso` and charge.
