# The molecule builder

The molecule builder turns a SMILES string into a three-dimensional
molecule: a linker with connection points for the MOF builder, a
guest for a pore, or a molecule to look at on its own.  After this
section you can build one into a tab of its own or paste it into the
structure you have open, fill a framework's pores with copies of it,
and know what the builder relies on and what it does not promise.

```{index} single: molecule builder
```
```{index} single: SMILES
```
```{index} single: RDKit
```

## What it does

A SMILES string {cite}`weininger1988smiles` names a molecule's atoms
and bonds and nothing about where they are.  The builder hands it to
RDKit (<https://www.rdkit.org>), which embeds a conformer by distance
geometry with the ETKDG corrections {cite}`riniker2015etkdg` and, with
**Relax it** ticked, relaxes it with MMFF {cite}`halgren1996mmff` --
or with UFF where MMFF has no parameters for it.  The molecule opens
in a tab of its own, in a {term}`P1` box with enough vacuum around it
that its periodic images do not see each other, and is filed in the
{term}`workspace` as an entry the moment it appears, with no run
folder underneath: a build leaves nothing behind that the molecule
itself does not say.  The force field in the application takes the
geometry further if you want it to.

RDKit is an **optional extra**, `build`.  The check is whether the
package can be found, never an import, so the menu rebuilds cheaply;
when it is missing the entries are greyed and the tooltip says what
to install:

```text
RDKit is not installed, so there is nothing to build a molecule from -- "<python>" -m pip install -e "<source checkout>[build]"
```

### The sketcher

The canvas under the string is a sketcher, and needs nothing beyond
`build`.  What is drawn is the string, and what is typed is drawn:

- **Click** the page to place the chosen element, an atom to grow a
  bond from it (or change it to the chosen element), a bond to cycle
  single, double, triple.  **Drag** out of an atom to draw a bond.
- **Any element**: the common ones are buttons, the periodic table
  button gives the rest, transition metals included.
- **Hover an atom and type** its new symbol.  A second letter typed
  quickly makes a two-letter element (C then l is Cl), as one undo
  step.  `1`, `2`, `3` over a bond set its order; `+` and `-` set a
  charge; `*` makes a connection point.
- **Ctrl+A** selects every atom and bond, and a tool chosen with a
  selection applies to all of it: Ctrl+A then *Double* makes every
  bond double.  Delete removes the selection.
- **Rings** of 3 to 8 and benzene go on the empty page, on a lone
  atom (which becomes a corner), off an atom with bonds (as a
  substituent), or fused onto a bond.
- **Dative** bonds point from donor to metal.  An ordinary bond to a
  metal is drawn as what it is, so `N` on platinum is an amido NH2;
  an ammine is a dative bond, or an H count of three set with *H+*.

### Metals

A metal is built with the shape of its coordination: four neighbours
are square planar for Ni, Pd, Pt, Au, Rh, Ir and Cu and tetrahedral
otherwise; five are a square pyramid when one of them is a metal (a
paddlewheel) and a trigonal bipyramid otherwise; two, three, six,
seven and eight are linear, trigonal, octahedral, pentagonal
bipyramidal and square antiprismatic.  **Right-click a metal** to
choose another shape.  The metal and the atoms bonded to it are placed
on the shape first and the rest of the molecule is grown round them,
then relaxed with UFF4MOF holding the shape.  A molecule that cannot
be built within a few degrees of its shapes is refused with a reason,
never handed over bent, and so is a metal bonded to every atom of a
ring (a sandwich), which has no shape here.

### Connection points

A `*` in the string marks a {term}`connection point`, and `[*:1]`,
`[*:2]` say which is which.  MMFF has no parameters for an atom of
atomic number zero, so before anything touches the molecule each `*`
is capped with a hydrogen; the molecule is embedded and relaxed as an
ordinary organic molecule, and the caps are then relabelled `X` and
pulled in to 0.75 Å ({doc}`blocks`).  A hydrogen points exactly where
a substituent would, so the direction -- the whole of what a
connection point carries -- is right.  The one caveat is sterics: a
hydrogen is smaller than the carboxylate it stands in for, so a
crowded *ortho*-substituted linker relaxes a little more open than it
would with its real neighbours.  Guessing at the substituent would be
worse than being slightly loose; optimise the framework you build
from it afterwards in any case.

## Building a molecule

```{index} single: Molecule from SMILES
```

1. Open *Modules ▸ Molecule builder ▸*
   {ref}`Molecule from SMILES… <cmd-module.build.molecule>`
   ({numref}`fig-frameworks-molecule-builder`).
2. **Start from** offers the molecules worth not typing twice --
   solvents such as DMF, and linkers such as the *para*-phenylene strut
   `[*:1]c1ccc([*:2])cc1` -- or *(type it yourself)*.  Choosing one
   fills the boxes.
3. Type or draw the molecule.  The canvas and the **SMILES** box
   follow each other, a third of a second after you stop typing.
4. **Name** is what the tab, the entry and, for a block, the file are
   called; empty, it is the string itself.  **Relax it** is on by
   default.  **Conformer seed** decides which conformer comes out: it
   is fixed rather than random so that the same string twice is the
   same molecule, and changing it offers another one.
5. The footer says what pressing the button will do -- *C3H7NO, 12
   atom(s) -- opens in a tab of its own* -- or why it cannot, in
   RDKit's words, when the string is not a molecule.  Press **Build**.

:::{figure} /figures/frameworks/molecule-builder.png
:name: fig-frameworks-molecule-builder
:width: 60%

The molecule builder with DMF typed in: the library, the four
settings, the canvas, and the footer saying what Build will do.
:::

From the command line the same entry writes a file:

```console
$ xtal run build.molecule -p smiles='CN(C)C=O' -p name=DMF -o DMF.cif
built C3H7NO from CN(C)C=O
C3H7NO, 12 atom(s)
wrote DMF.cif
```

## Inserting a molecule into the open structure

```{index} single: Insert molecule
```

*Structure ▸* {ref}`Insert molecule… <cmd-insert_molecule>` is the
same dialog with **Insert** for its button: it builds the molecule
and pastes it into the structure you have open, rather than into a
tab of its own.  It arrives with the bonds the builder gave it and no
others -- nothing is perceived, which is the rule for any atom you
place -- and pasting into a group with symmetry multiplies it over
the {term}`orbit`; the footer says by how much before you press the
button.  The library here offers the solvents and hides the linkers,
because a molecule with connection points is not something to paste
into a cell.

## Filling pores

```{index} single: Fill pores with molecules
```

*Structure ▸* {ref}`Fill pores with molecules… <cmd-fill_pores>` puts
copies of a molecule into the empty space of the open structure, each
where it touches nothing.  The guest comes from somewhere else -- a
solvent built into a tab of its own, or a file -- because what is
wanted out of that tab is the molecule and not the box it was built
in:

Source, Molecule
: Any open tab or a file, and then each distinct molecule in it, by
  formula.  A framework in the source is not offered: it never
  closes, so it is not something a pore can hold.

Where
: *In the pores*, anywhere there is room, or *One beside each selected
  atom* -- a counter-ion by every charged site of a framework, a
  sodium by each carboxylate oxygen of an anionic MOF, which random
  insertion has no reason to put there.  Select the atoms first; the
  count is then the selection's and its box greys out.  Each copy's
  centre goes *Distance* (3.5 to 5.0 Å by default) from its atom,
  clear of everything, the other copies included, and bonded to
  nothing.  An atom with no room beside it is named afterwards, and
  the rest still get theirs.  Or *One at a point (fractional)*, below.

Count
: How many copies to try to place (20 by default).  The dialog quotes
  the most there could be room for, from the free volume; fewer are
  placed when there is no room, and the count you asked for is an
  upper bound, not a promise.

Overlap scale
: Two atoms clash when closer than this times the sum of their van der
  Waals radii.  At 1.0 nothing touches anything, which leaves a real
  solvent visibly too sparse -- molecules in a liquid sit inside each
  other's van der Waals spheres -- so 0.8 is the default.

Seed
: The same seed puts the same molecules in the same places.

Placing is random insertion, not packing: a trial centre is drawn from
the grid points clear of the host, the molecule is turned by a
uniformly random rotation, and the trial is kept when no atom of it is
inside any other atom -- against the framework across the cell's
faces, and against the guest's own images when the cell is small
enough for it to meet them.  It is what a first Monte Carlo step does,
and it stops being able to add anything well short of a liquid's
density.  Nothing is placed until **Fill** is pressed, and it is one
undo step.

:::{note}
A host with symmetry is **reduced to P1 first**, and the dialog says
so before you press the button: a structure that changes space group
on the way to having solvent put in it should not be a surprise found
afterwards.  Bonds are not recalculated -- a guest arrives with the
bonds it was drawn with and none to the framework it sits a contact
away from.
:::

### One molecule at a point

*Where ▸ One at a point (fractional)* puts a single copy with its
centre -- the centroid of its atoms -- on the fractional coordinates
in *Point*: a template in the cage it was found in, a guest a
diffraction study located, the molecule from one file put into the
structure of another.  *From selection* fills the point in with the
middle of the selected atoms, gathered across the cell's faces.

Turn for most room
: Off, the molecule goes the way round it was drawn in its source.
  On, the seeded orientation whose closest contact is furthest is
  kept, and as drawn is among those tried, so turning never leaves
  less room.

Keep the space group
: Off, a host with symmetry is reduced to P1 and gets this one
  molecule.  On, the molecule goes into the asymmetric unit and the
  group copies it to every equivalent point; the dialog says how many
  atoms that makes.  At a special position the copies fall on each
  other, and the count -- not the molecule times the group's order --
  is how that shows; it is said as a warning.

The preview is the placement itself and names the closest contact,
with how much of the two atoms' van der Waals contact it is.  **A
crowded point is inserted anyway**: the point was yours, so a molecule
inside the framework is a warning, before *Insert* and again after it,
and never a refusal.  Undo takes it back, the reduction to P1
included.

## Settings

The four parameters -- SMILES, name, relax, seed -- are listed under
{ref}`Molecule from SMILES… <mod-build-molecule>`, and the module under
{ref}`Molecule builder <mod-build>`; *Insert molecule…* and *Fill
pores with molecules…* are {ref}`described <cmd-insert_molecule>` with
the {doc}`Structure menu </essentials/structure>`.

## Limitations

- The geometry is RDKit's: one conformer, chosen by the seed, relaxed
  with MMFF or UFF.  It is a starting point for the application's own
  engines, not a result.
- A connection point's neighbourhood was relaxed with a hydrogen in
  its place, so a crowded linker comes out slightly loose.
- Filling is random insertion with a clash test, not a packing or an
  energy; the count reached is what fitted, and *Fill pores* says
  nothing about whether the arrangement is a likely one.
- The library is a list in the package (`data/fragments.json`); adding
  to it is a line in that file, not a setting.
