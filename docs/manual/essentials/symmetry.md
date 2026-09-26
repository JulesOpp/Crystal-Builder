# Symmetry

The *Symmetry* menu finds, sets, lowers and removes the
{term}`space group` a structure is described in.  After this page you
can recover the group of a structure written in P1, choose a group and
generate or impose it, descend to a subgroup to make two sites out of
one, label Wyckoff positions, and take a structure to P1 when you need
to edit one atom of an orbit.

:::{note}
This page is a draft awaiting the author's review.  What it says about
symmetry is what the application's dialogs, help text and code say;
where they stop, so does the page.
:::

## What the group does for you

```{index} single: symmetry; asymmetric unit and orbits
```

A structure with a space group lists only its {term}`asymmetric
unit`, and the group generates the rest: the status bar for HKUST-1
reads *Fm-3m (#225) · 6 sites / 624 atoms*.  Every edit you make to a
site is made to its whole orbit, which is why one atom moved in a
symmetric structure moves 32 or 96 of them, and why a structure that
should not be that symmetric is easier to edit after *Reduce to P1*.
Finding the symmetry again afterwards is one dialog.

:::{note}
**A site is on a {term}`special position` when its coordinates say it
is**, to within 0.05 Å.  That is not a numerical tolerance: four
decimal places on a thirty-Ångström cell is 0.003 Å, and a drag or an
optimiser step is larger still.  A site written a rounding place off
its mirror is treated as being on it, so an operation that should map
it onto itself does, rather than generating a second copy a hundredth
of an Ångström away.  Where the atom *goes* is not changed by this;
snapping it exactly onto the position is what *Standardise cell*
does.
:::

## Find symmetry

```{index} single: symmetry; finding
```

{ref}`Find symmetry… <cmd-find_symmetry>` ({kbd}`Ctrl+Shift+F`) asks
what symmetry these coordinates have, with the tolerance in plain
sight ({numref}`fig-find-symmetry`), and adopts the answer only when
you say so.  Detection is spglib's {cite}`togo2024spglib`.

1. Pick a *Tolerance (A)*: how far an atom may be from its symmetric
   position.  The presets run from `1e-5` to `0.1`, and `0.1` is the
   default, because the structures this dialog is opened on are
   rarely refined ones -- a framework drawn by hand, dragged or
   relaxed by a force field sits a few hundredths of an Ångström off
   its group.  A published CIF still finds its group at `0.1`; the
   tighter presets exist to tell two close groups apart.  The
   detected group follows the tolerance live.
2. Read the summary and the table underneath.  For MOF-5 as shipped,
   written in P1 with 424 sites, the summary reads *Fm-3m (#225), 192
   operations, 7 independent sites [symprec=0.1]*, and the table
   gives each independent site its {term}`Wyckoff position`, site
   symmetry and multiplicity -- Zn1 on 32f with site symmetry .3m, O1
   on 8c, and so on.  A chemist recognises *Ti on 2a, O on 4f* long
   before a wrong Hall symbol.
3. Leave *Re-express the cell in the standard setting first* ticked
   unless you have a reason to keep the cell as given.  When the cell
   is not in the standard setting of the group found, the note says
   so, and adopting the group then moves the atoms; untick the box to
   keep the cell, at the price of not being able to adopt the group
   in that setting.  When the structure already has that group the
   note reads *Already Fm-3m -- adopting reduces the cell to its
   asymmetric unit*.
4. Press **Adopt this group** to keep the group and reduce the cell
   to its asymmetric unit.  The status bar reports *Fm-3m (#225): 424
   atoms -> 7 independent sites*.  The operation checks itself by
   expanding the result again: if the asymmetric unit does not
   regenerate the cell it started from, you get the original
   structure back and a message, never a plausible wrong answer.  If
   the cell was re-expressed the view is reset, because the camera
   that framed the old setting frames the new one badly.
5. Press **Label Wyckoff only** to write the Wyckoff letters onto the
   sites and change nothing else -- the same as {ref}`Assign Wyckoff
   letters <cmd-wyckoff>` at this tolerance.

:::{figure} /figures/essentials/find-symmetry.png
:name: fig-find-symmetry
:width: 70%

*Symmetry ▸ Find symmetry…* on the MOF-5 sample: Fm-3m found at
0.1 Å, with the Wyckoff table that says whether it is the answer you
expected.
:::

## Set space group

```{index} single: space group; setting
```

{ref}`Set space group… <cmd-set_space_group>` chooses a group by hand
and says what choosing it means.

1. Search by number, Hermann--Mauguin symbol, Hall symbol or crystal
   system.  The list is every *setting*, not every group -- P2{sub}`1`/c
   and P2{sub}`1`/n are the same group down different axes, and Fd-3m
   has two origin choices whose atoms are a quarter of a cell apart
   -- so the Hall symbol is shown beside each entry and travels with
   the choice.
2. Say how to apply it.  **Generate: the sites are the asymmetric
   unit** lets the group generate the rest of the cell; the atom count
   goes up, and it is what you want after typing in or building an
   asymmetric unit.  **Impose: the sites are already the whole cell**
   finds an asymmetric unit inside the atoms you have; the count goes
   down, and atoms the group cannot explain are reported, not dropped.
3. The line under the list shows the count before anything happens:
   *6 sites generate 624 atoms in Fm-3m*.

## Descend to a subgroup

```{index} single: subgroup; descending to
```

{ref}`Descend to a subgroup… <cmd-subgroup>` lowers the symmetry so
that an orbit splits and its atoms become independent -- the first
step of an ordering model or a distortion.  Raising the symmetry is a
measurement of the coordinates with one answer; lowering it is a
choice between subgroups the coordinates cannot make for you, which is
why this is a dialog and *Find symmetry* is a button.

1. Read the heading: *Subgroups of F m -3 m (#225), 192 operations*.
   The dialog's own text explains the two kinds: a **t** descent gives
   up rotations and keeps every translation; a **k** descent keeps the
   rotations and gives up translations, either part of the centring
   in the same cell or enough of the lattice that the cell grows,
   which is a superstructure.  Every subgroup is listed, not only the
   maximal ones, with the maximal step marked in the *Step* column;
   the *Kind* box filters (*All (237)*, *t (32)*, *k (2)*, *t + k
   (203)* for HKUST-1).
2. Subgroups that differ only in orientation give the same crystal
   and share one row; *Same by symmetry* says *1 of 3* when a row
   stands for three.  *Axes and origin* says how the new cell sits in
   the old one.
3. Select a row and read *What splits*, worked out by performing the
   descent on a copy: for HKUST-1 the first row, F m -3, reads *6 ->
   7 sites: O1 into 2*, and the detail underneath says *O1 (O),
   multiplicity 192, becomes 2 independent sites*
   ({numref}`fig-descend-to-subgroup`).  Most descents split nothing,
   because the site symmetry drops by the same factor as the group
   order and what changes is the freedom each site has, not how many
   there are; the column is what tells you which row does what you
   came for.
4. Press **Descend**.  Every atom stays where it is; the view is reset
   because the cell may have changed shape or axes.

:::{figure} /figures/essentials/descend-to-subgroup.png
:name: fig-descend-to-subgroup
:width: 100%

*Symmetry ▸ Descend to a subgroup…* on HKUST-1: 237 subgroups of
Fm-3m, the maximal ones marked, and the split the selected row would
make.
:::

## Cell settings, Wyckoff letters, duplicates and hand

```{index} single: cell; standard setting
```
```{index} single: primitive cell
```

1. {ref}`Standardise cell <cmd-standardize>` rebuilds the cell in the
   conventional setting of the detected group, and
   {ref}`Reduce to primitive cell <cmd-primitive>` in its primitive
   setting.  Both come back in {term}`P1`: on MOF-5 in Fm-3m the
   status bar reads *standardised to the conventional cell: 424
   atoms, V = 17305.33 A^3* and *standardised to the primitive cell:
   106 atoms, V = 4326.33 A^3*.  Run *Find symmetry…* afterwards to
   get the group back on the new cell.  Standardising also idealises
   the coordinates, which is where a site a rounding place off its
   special position is snapped onto it.
2. {ref}`Assign Wyckoff letters <cmd-wyckoff>` writes the Wyckoff
   letter of every site -- *7 sites on 32f, 48g, 8c, 96k positions*
   -- and changes no coordinate.  The *Sites* table shows them.
3. {ref}`Merge duplicate sites… <cmd-merge_duplicates>` merges sites
   of the same element that are the same atom, symmetry images
   included -- what a CIF that repeats an orbit, or a structure
   refined twice into two places 0.2 Å apart, needs.  The tolerance is
   yours to set, from 0.001 to 0.5 Å, with the count of atoms it
   would merge beside it: the right tolerance is a property of the
   file, and the count is flat over a range and then steps.  On a
   clean file it says *no duplicates within 0.05 A*.
4. {ref}`Invert the structure <cmd-invert>` gives the same crystal in
   the other hand: the coordinates and the space group move together
   and the cell is left alone.  On a centrosymmetric group it tells
   you that inversion is already one of the group's operations and
   changes nothing; otherwise it says what will change -- the symbol,
   the structure, or both -- and asks.  The *Structure* panel names
   the hand (*centrosymmetric (achiral)* for Fm-3m).

:::{warning}
**Merge duplicate sites cannot see a site duplicated by its own
group.**  It compares a site against *other* sites' images, never
against its own.  A site written far enough off a special position
for the group to generate two copies of it -- further than the 0.05 Å
above -- is reported as *no duplicates* at any tolerance, and *Reduce
to P1* is the first thing that draws both copies.  If a P1 expansion
has more atoms than the formula says, look for a site just off a
mirror or an axis, and either move it onto the position or
*Standardise cell*.
:::

## Reduce to P1

```{index} single: P1; reducing to
```

{ref}`Reduce to P1 <cmd-reduce_p1>` expands every orbit into
independent sites and drops the group: *expanded Fm-3m to P1: 424
independent sites*.  Reach for it when you need to edit one atom of an
orbit -- delete one linker, move one guest, scan one distance the
group would hold fixed -- and find the symmetry again when you are
done.  The bonds come too: every bond drawn, deleted or typed, and
every net edge, is written down again between the new sites, and
nothing is perceived afresh.  The same command is on the *Inspector*
panel.
