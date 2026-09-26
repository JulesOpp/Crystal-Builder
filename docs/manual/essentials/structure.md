# Structure

The *Structure* menu changes what the crystal is made of: atoms,
bonds, connection points and the criteria bonds are perceived by.
After this page you can add and merge atoms, put a centroid where a
net edge or a measurement needs one, control exactly when bonds are
recalculated, and give a bond a type the geometry would not have
guessed.

## Adding atoms

```{index} single: atoms; adding
```

1. {ref}`Add atom… <cmd-add_atom_dialog>` ({kbd}`Ctrl+Shift+A`) places
   one atom by its coordinates: element (with *Table…* for the
   periodic table), *Position* as fractional or cartesian -- switching
   converts what is typed rather than clearing it -- occupancy and
   label.  The atom arrives bonded to nothing.
2. The *Add atom* mouse mode places atoms by clicking, and draws a
   bond from each new atom to the atom it was built from; see
   {doc}`mouse modes <mouse-modes>`.
3. {ref}`Add centroid… <cmd-add_centroid>` puts an atom at the middle
   of the selected atoms (two or more).  By default it is a
   {term}`dummy atom`, `X`; the other radio button makes it an
   element.  The new atom is left selected, because a centroid lands
   inside the ring it was taken from, where an unhighlighted atom is
   hard to find.  The status bar says *centroid of 6 atoms added as
   X1*.
4. {ref}`Merge atoms <cmd-merge_atoms>` replaces the selected atoms
   with one at their middle: of their element when they all share
   one, a dummy atom when they do not, because a carbon and an oxygen
   averaged are neither.  Whole orbits go, as with *Delete*, and the
   new atom is bonded to nothing.  Two half-occupied positions of a
   disordered atom, or a cluster you want reduced to a single node,
   are what it is for.

:::{note}
**Bonds are recalculated only when you press Recalculate bonds.**
Not on load, not when the cell changes, not after an optimisation,
and not when an atom is placed: an atom arrives with the bonds you
gave it -- *Add atom* in the 3D view draws one to its anchor, a paste
brings the fragment's own -- and no others.  So two atoms that end up
on top of each other are not bonded, and a bond stretched to 4 Å is
still a bond, until you ask.  *Add hydrogens…* is the one deliberate
exception, because bonding what it adds is the whole operation.
:::

:::{note}
**A dummy atom is a marker, not chemistry.**  Perception never bonds
an `X`, a force field is built over the structure without it, and
*Add hydrogens* and every module run set it aside rather than
refusing to run.  Net edges and measurements take it like any other
atom, which is what it is for: the centre of a ring, the vertex of a
net, the point a connection is made at.
:::

## Building on the structure

```{index} single: hydrogens; adding
```

1. {ref}`Add hydrogens… <cmd-add_hydrogens>` completes every
   main-group coordination with the hydrogens an X-ray structure
   never had.  The plan is computed before you press *Add*: how many,
   counted over the orbit (*12 hydrogens on 2 sites*, not *2*), and
   every assumption behind it, including the atoms deliberately left
   alone.  On a structure that already has them it says *no hydrogens
   to add*.  The one choice is *X-ray bond lengths (0.10 A shorter)*,
   off by default because the longer, neutron-like lengths are what
   the force fields were parameterised against.
2. {ref}`Insert molecule… <cmd-insert_molecule>` builds a molecule
   from a SMILES string and pastes it in.  It needs the molecule
   builder's optional package; when that is missing the entry is
   greyed and its tooltip says what to install.  The dialog says by
   how much a group with symmetry will multiply the molecule before
   you press the button.
3. {ref}`Fill pores with molecules… <cmd-fill_pores>`,
   {ref}`Interpenetrate… <cmd-interpenetrate>` and
   {ref}`Prepare for simulation… <cmd-prepare_simulation>` rebuild the
   structure in larger ways -- guests placed where they touch nothing,
   copies of a framework threaded through its own pores, a deposited
   structure made ready for a calculation in one undo step.  Each has
   a section of its own in {doc}`Structure and Optimisation
   </structure/index>`.
4. {ref}`Mark connection points <cmd-mark_connection_points>` and
   {ref}`Mark as one connection point <cmd-mark_one_connection_point>`
   turn selected atoms into the {term}`connection points <connection
   point>` a {term}`building block` is joined by.  There is no
   *Unmark*: an `X` does not remember what it was, so the way back is
   {kbd}`Ctrl+Z`.  Drawing blocks is in {doc}`Frameworks and Nets
   </frameworks/index>`.

## Bonds

```{index} single: bonds; recalculating
```
```{index} single: bond rules
```

1. {ref}`Bond rules… <cmd-bond_rules>` is the criteria perception
   works to: a *Radius factor* on the covalent radii, an *Extra
   allowance*, an *Ignore closer than* floor, *Allow metal-metal
   bonds*, and a table with one row per pair of elements in this
   structure where a distance range can be typed (blank means the
   covalent radii).  The count travels with the number -- *768 bonds
   -- no change from the current rules*, or so many added and so many
   removed -- because the count is flat over a wide range and then
   steps, and a factor set without seeing the step is a guess.  *Use
   these rules for structures opened from now on* makes them the
   default; *Preferences ▸ Bonding* reaches the same default with no
   structure open.
2. {ref}`Recalculate bonds <cmd-recompute_bonds>` -- also the button
   on the toolbar -- perceives the bonds again from the geometry as
   it is now.  It reports the difference, not the total: *bonds
   recalculated, unchanged: 512 bonds*, or *3 added, 1 removed*.  It
   keeps the bonds you drew and the ones you deleted, and says so
   when it does (*kept 2 you drew; Reset bonds is what drops them*),
   because a recalculation that silently gives back the same graph
   looks like a button that does nothing.  It is an undo step even
   when nothing changed.
3. {ref}`Reset bonds to automatic <cmd-reset_bonds>` ({kbd}`Ctrl+B`)
   drops every bond you drew and every one you deleted and takes what
   the criteria give.  The key is on the reset and not on the
   recalculation on purpose: after an afternoon of editing, the way
   back to a clean answer is the one worth a reflex, and it is a
   single command, so {kbd}`Ctrl+Z` is exactly one press.
4. {ref}`Bonds follow the geometry <cmd-bonds_follow>` is a toggle
   that re-perceives after every edit that moves an atom, instead of
   only when you ask.  It is the same setting as *Preferences ▸
   Bonding*, and it applies to the tabs already open.  Leave it off
   while you are drawing bonds by hand, because a re-perception is
   how a bond you meant to keep is lost.
5. *Set Bond Type ▸* {ref}`Single <cmd-bond_type_single>`,
   {ref}`Double <cmd-bond_type_double>`, {ref}`Triple
   <cmd-bond_type_triple>`, {ref}`Aromatic <cmd-bond_type_aromatic>`
   or {ref}`Automatic <cmd-bond_type_automatic>` states the order of
   the selected bonds and their whole orbit.  The submenu ticks what
   the selection already is, and ticks nothing when the selected
   bonds differ.  *Automatic* lets the geometry decide again.  The
   same submenu is in the context menu of a bond.

:::{note}
**A bond type you set takes precedence** over anything the distances
would say, and a bond you drew or deleted survives a recalculation.
These are the three kinds of information perception cannot produce,
so nothing but *Reset bonds to automatic* -- or {kbd}`Ctrl+Z` --
removes them.  The workspace copy of the structure carries them: a
CIF's `_geom_bond` loop says which site is bonded to which, under
which operation and translation, and the meaning of each bond rides
beside it.
:::

## The context menu

```{index} single: context menu
```

A right-click on an atom gathers the edits and selections that apply
to it ({numref}`fig-context-menu-atom`); on a bond it offers *Delete
bond*, *Set Bond Type*, the one measurement a bond admits, and
*Recalculate bonds*; on the background, the selection, the
{ref}`boundary <cmd-boundary_bonded>` answers, *Orthographic
projection*, *Reset view* and the *Style* submenu.  Every entry is the
same action the menu bar shows, enabled by the same rule, so nothing
in a context menu is reachable only there.  *Edit cell…* and *Display
range…* end all three, because the cell is always under the cursor.

:::{figure} /figures/essentials/context-menu-atom.png
:name: fig-context-menu-atom
:width: 45%

The context menu of an atom, with two atoms selected: *Delete* says
how many it will take, and the measurement entry is the one two atoms
admit.
:::

## Mouse mode

The *Mouse mode* submenu chooses what a click in the 3D view does --
*Select*, *Box select*, *Add atom*, *Add bond*, *Draw net*, *Move* or
*Measure*.  The same seven are the middle group of the toolbar, and
they have a page of their own: {doc}`mouse-modes`.
