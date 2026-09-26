# Interpenetration

Interpenetration threads copies of a framework through its own pores.
After this section you know why the application enumerates placements
rather than predicting them, how each placement is scored and when one
is refused, what the copies carry with them, how the result is
verified, and how to make a two-fold MOF-5 from the *Structure* menu or
the MOF builder.

```{index} single: interpenetration
```
```{index} single: interpenetration; Class Ia and Class II
```
```{index} single: closest contact
```

## Enumerated, not theorised

**There is no topological test for which nets self-interpenetrate.**
The clean part of the theory is the balance surfaces: **pcu**, **dia**
and **srs** are the labyrinth nets of the P, D and G minimal surfaces,
which is why those three interpenetrate two-fold so readily and why
the second copy sits at a coset representative rather than anywhere.
Beyond that is Blatov's classification {cite}`blatov2004interpenetration`
-- **Class Ia**, copies related by a translation of the whole array,
so that one net's lattice is an index-$n$ sublattice of the array's;
**Class II**, copies related by a symmetry operation that is not a
translation -- and whether a given placement is *realisable* is
geometric: the voids have to be large enough.  So the application does
not theorise.  It **enumerates** candidates, measures each one, and
says which leave room.

At $n$-fold the candidates are:

- **Class Ia**: the superlattices of index $n$ of the structure's own
  lattice, each giving $n$ coset representatives for the copies to sit
  at.  One that contains a translation the structure already has -- a
  centring vector -- is left out, because its copy would land on the
  original.
- **Class II**, at two-fold: the copy is the original inverted through
  a point of the eighth-cell grid, and the inversion is then a symmetry
  of the array whatever the structure's own group.  For a
  centrosymmetric structure that copy *is* the original translated, by
  twice the point less the structure's own centre, and it is offered
  as that translation -- which is how 2-fold MOF-5 is found: its second
  copy is a quarter of the cell along the body diagonal, and no
  half-vector of its F-centred cell reaches it.

% TODO(Sam): the module docstring says "quarter-cell points" and the
% candidates() docstring and CLAUDE.md say "eighth-cell grid"; the
% page follows the latter.  Reported for the docstring.

Two placements that a symmetry of the structure carries onto each
other are the same array turned round, and are one row.  The symmetry
is **detected** on the P1 cell, not read off the label, because a
framework straight out of the builder is labelled P1 and is cubic.

Each candidate is **scored by the shortest contact between copies**,
looked for out to 6 Å (beyond that the report says *more than 6 A*).
A placement is refused by name when two atoms of different copies come
closer than the bond rules' own criterion -- a pair
{ref}`Recalculate bonds <cmd-recompute_bonds>` would join has fused the
copies, and the count of copies is then wrong -- or than 1.5 Å whatever
the rules say, because the rules let two hydrogens sit 0.7 Å apart.
Every framework in `resources/samples` has its closest non-bonded
contact between 1.996 and 2.170 Å, and a build whose blocks do not fit
their net comes out at 1.66; 1.5 is below all of it.

**The copies carry the bonds they had.**  Nothing is perceived: each
copy carries the explicit bonds, the stored perceived graph and the
drawn {term}`net` of the original, moved with it.  And the result is
**verified by the detector that was already here**: the array is
refused unless the count of independent periodic frameworks its bonds
make -- the sum of each component's net multiplicity, which is how two
copies written into one cell and one copy written into a doubled cell
both count two -- is $n$ times what the original counted.  The
generator is checked by code that was written to *find*
interpenetration and knows nothing about how this one was made.

:::{note}
The array stays in the cell it was given, and the result is in
{term}`P1`.  A Class Ia offset is a translation of order $n$ modulo
the structure's lattice, so the structure's cell already holds every
copy whole; the array's own, smaller, translation lattice is a symmetry
it has on top of that, and its group is not one copy's group.  A guess
at it here would be a symmetry nobody checked, so
{ref}`Find symmetry… <cmd-find_symmetry>` is where it is looked for.
:::

## Two doors

```{index} single: Interpenetrate...
```

*Structure ▸* {ref}`Interpenetrate… <cmd-interpenetrate>` opens a
list, not an answer ({numref}`fig-interpenetrate-mof5`):

1. Choose the number of **Copies** (2-fold up to 6-fold: ten-fold
   **dia** is the record for a real framework, and the index-$n$
   sublattices grow faster than $n$, so the bound is on the list and
   not on the chemistry).  Every placement at that fold is measured as
   the box changes.
2. The table lists each placement with its **Relation** (Class Ia or
   Class II), its **Closest contact** and whether there is **Room**,
   best first.  The top row is selected, which is the answer for
   somebody who wants the one with the most room; the rest are there
   because the one with the most room is not always the one in the
   paper.  **The ones that collide stay in the list, greyed, with the
   reason** -- a dense framework offers nothing, and a list that had
   silently dropped everything could not say why; a row that names the
   two atoms that would land on each other can.
3. The line under the table names the two closest atoms of different
   copies for the selected row.  Press **Interpenetrate**; a row that
   collides cannot be chosen.

:::{figure} /figures/structure/interpenetrate-mof5.png
:name: fig-interpenetrate-mof5
:width: 90%

*Interpenetrate* on the COD structure of MOF-5 at 2-fold: one
placement with room, at ¼, ¼, ¼, and seven that collide, greyed.
:::

The result is one undo step, the status bar reads *2-fold
interpenetrated by translation by 1/4, 1/4, 1/4 (Class II): 848 atoms
in P1, closest contact between copies 3.67 A*, and a pore network
measured on the single framework is dropped, because atoms have
arrived.

The MOF builder's **Interpenetration** setting
({ref}`Build a framework… <mod-mof-build>`) does the same at build
time: *how many copies of the framework, threaded through one another
-- 2 for two-fold.  The copies go where the most room is, measured by
the closest contact between them, and a framework too dense for any
placement is refused rather than built crowded.*  It takes the best
placement without asking; *Structure ▸ Interpenetrate…* is where every
placement is listed.

## Worked example: 2-fold MOF-5

The COD structure of MOF-5 (*File ▸ Open Sample ▸ From the COD ▸*
{ref}`MOF-5 <cmd-sample_cod_mof5>`; Fm-3m, 424 atoms), run through the
core in a short script -- `candidates`, `best`, `build` and `copies`
from `xtal.analysis.interpenetrate` -- which prints what the dialog
shows:

```console
SpaceGroup(Fm-3m #225) 424 atoms
translation by 1/4, 1/4, 1/4 Class II       contact         3.67 A  room
translation by 0, 0, 1/4     Class II       contact         0.39 A  collides: puts Zn16 of one copy 0.60 A from C103 of another, close enough for Recalculate Bonds to join the two copies
translation by 0, 1/4, 1/2   Class II       contact         0.39 A  collides: puts C120 of one copy 0.60 A from Zn25 of another, close enough for Recalculate Bonds to join the two copies
translation by 1/4, 1/2, 1/2 Class II       contact         0.39 A  collides: puts C180 of one copy 0.60 A from Zn22 of another, close enough for Recalculate Bonds to join the two copies
translation by 0, 1/4, 1/4   Class II       contact         0.20 A  collides: puts C126 of one copy 0.20 A from C118 of another, close enough for Recalculate Bonds to join the two copies
translation by 1/4, 1/4, 1/2 Class II       contact         0.20 A  collides: puts C109 of one copy 0.20 A from C120 of another, close enough for Recalculate Bonds to join the two copies
translation by 0, 0, 1/2     Class Ia       contact         0.00 A  collides: puts C76 of one copy 0.00 A from C49 of another, close enough for Recalculate Bonds to join the two copies
translation by 1/2, 1/2, 1/2 Class Ia       contact         0.00 A  collides: puts C8 of one copy 0.00 A from C31 of another, close enough for Recalculate Bonds to join the two copies
best: translation by 1/4, 1/4, 1/4 Class II 3.67 A
built: 848 atoms SpaceGroup(P1 #1) copies 2 from 1
```

The two Class Ia half-vectors land a copy exactly on the original
(contact 0.00 Å), because MOF-5's F-centred cell already has them as
centring translations of the primitive lattice; the one placement with
room is the inversion through an eighth-cell point, offered as the
quarter-cell body-diagonal translation because the structure is
centrosymmetric.  The array is 848 atoms in P1, the copies' closest
atoms are two hydrogens 3.67 Å apart, and the detector counts two
independent frameworks where the original had one.  The whole
enumeration, build and check took under a second.

## Settings

{ref}`Interpenetrate… <cmd-interpenetrate>` under *Structure* has the
fold and the placement list; the MOF builder's setting is
**Interpenetration** under {ref}`Build a framework… <mod-mof-build>`.

## Limitations

- Placements are enumerated, not predicted: the list is every
  translation the lattice admits at that fold and, at two-fold, the
  inversions.  A real interpenetrated framework whose copies are
  related by a rotation or a screw (a Class II relation other than an
  inversion) is not in the list.
- The fold stops at six.
- The result is in P1; its symmetry is found with
  {ref}`Find symmetry… <cmd-find_symmetry>`, not assumed.
- The score is a contact distance.  Whether a placement with room is
  the one a synthesis gives is not a question the geometry answers.
